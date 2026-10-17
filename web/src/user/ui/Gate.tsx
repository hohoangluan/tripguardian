import * as Dialog from '@radix-ui/react-dialog'
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react'
import { DeckIssues, ExtraInputs, TAB_ICON, clockOf, useDeckForm, type DeckForm } from '../screens/understand/Deck'
import type { Deck, DeckAnswers, DeckIssue, Option, ReadbackLine } from '../tu/types'
import { Icon, type IconName } from './icons'

// The questions before planning (docs/UI_SPEC_USER_WEB.md, "Trước khi lập lịch"): the questions are a fan of pastel cards, the
// one being answered in front and the rest peeking out on both sides (click one to bring it forward); what is already noted
// runs as one horizontal bar under the cards. The paper colours live in gate.css.

// The card colours: the Petal Ritual palette (petal flush #F2D4D6, blue veil #C9D8E5, tangerine mist #F4CB82, olive cream #D8D1BE,
// milk tint #FDFBF9) plus a lilac and a peach mixed from two of them, in an order where neighbours never look alike.
const TINTS = ['#f2d4d6', '#c9d8e5', '#f4cb82', '#d8d1be', '#fdfbf9', '#dfd6e0', '#f3ceaa']
const VISIBLE = 3 // cards fanned out on each side of the front one; the rest wait behind the last
const SPRING = { k: 190, c: 24 } // slightly under-damped: the card that arrives overshoots a hair, then settles
const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, n))
const ICONS: Record<ReadbackLine['tab'], IconName> = { trip: 'calendar', companions: 'users', mobility: 'car', care: 'heart', pace: 'gauge', budget: 'wallet', lodging: 'bed', more: 'star' }
export const MARKERS: Record<ReadbackLine['kind'], string> = { said: 'Bạn nói', guess: 'Mình đoán', default: 'Mặc định', check: 'Cần xem lại' }

export const KINDS = ['said', 'guess', 'default', 'check'] as const

// a line without the kind the mark already shows ("Mặc định: …"), first letter up
const tidy = (text: string) => { const t = text.replace(/^(Mặc định|Tự kiểm|Mình đoán|Bạn nói)\s*:\s*/i, ''); return t.charAt(0).toUpperCase() + t.slice(1) }

// "Bạn ở đâu? Mấy giờ?" -> the first question upright, the rest in italics.
const split = (question: string): [string, string] => {
  const i = question.indexOf('?')
  if (i < 0 || i >= question.length - 1) return [question, '']
  return [question.slice(0, i + 1), question.slice(i + 1).trim()]
}

export function LedgerList({ lines, busy, onEdit, onDrop }: { lines: ReadbackLine[]; busy: boolean; onEdit: () => void; onDrop: (target: string) => void }) {
  return <ul className="tg-gt__ledger">{lines.map((line, i) => <li className={`is-${line.kind}`} key={`${line.tab}-${i}`}>
    <span className="tg-gt__mark" aria-hidden="true"><Icon name={ICONS[line.tab] ?? 'star'} size={18} /></span>
    <button type="button" className="tg-gt__line" disabled={busy} onClick={onEdit} aria-label={`Sửa: ${line.text}`} title={tidy(line.text)}><small>{MARKERS[line.kind]}</small><span>{tidy(line.text)}</span></button>
    {line.kind === 'guess' && line.undo && <button type="button" className="tg-gt__undo" disabled={busy} aria-label={`Bỏ suy luận: ${line.text}`} title="Bỏ điều mình đoán" onClick={() => onDrop(line.undo!)}><Icon name="x" size={14} /></button>}
  </li>)}</ul>
}

// What TripGuardian has already written down: a bar of icons under the cards, one per line, joined by a thin route; the words
// come in a tip on hover or focus, a tap edits it in Tìm hiểu.
function Checklist({ lines, busy, changed, onEdit, onDrop }: { lines: ReadbackLine[]; busy: boolean; changed: boolean; onEdit: () => void; onDrop: (target: string) => void }) {
  return <section className="tg-gt__check" aria-label="Những điều mình đã ghi nhận">
    {changed && <p className="tg-gt__sr" role="status">Vừa có thay đổi, bạn xem lại nhé</p>}
    {lines.length ? <ul>{lines.map((line, i) => <li className={`is-${line.kind}`} key={`${line.tab}-${i}`}>
      <button type="button" className="tg-gt__dot" disabled={busy} onClick={onEdit} aria-label={`${MARKERS[line.kind]}: ${tidy(line.text)}. Bấm để sửa`}><Icon name={ICONS[line.tab] ?? 'star'} size={20} /></button>
      <span className="tg-gt__tip" aria-hidden="true"><small>{MARKERS[line.kind]}</small>{tidy(line.text)}</span>
      {line.kind === 'guess' && line.undo && <button type="button" className="tg-gt__undo" disabled={busy} aria-label={`Bỏ suy luận: ${line.text}`} title="Bỏ điều mình đoán" onClick={() => onDrop(line.undo!)}><Icon name="x" size={12} /></button>}
    </li>)}</ul> : <p className="tg-gt__check-none">Trả lời đến đâu, mình ghi lại ở đây đến đó.</p>}
  </section>
}

// The hand of cards as one continuous position: `pos` (a card index, fractional while moving) chases the card being answered
// on a spring, and every card is laid out from its distance to it, so the next card slides in over the one it replaces
// instead of jumping. Dragging, a sideways wheel and the arrow keys move it too. Written straight to the elements each frame
// (no React render per frame); the lengths are calc() on --step, so the app's px->rem scale applies.
function useFan(count: number, at: number, goTo: (i: number) => void) {
  const stage = useRef<HTMLDivElement>(null)
  const cards = useRef<(HTMLDivElement | null)[]>([])
  const live = useRef({ pos: at, vel: 0, target: at, dir: 1, motion: 0, raf: 0, last: 0, drag: null as null | { x: number; pos: number; moved: boolean; id: number; marks: { x: number; t: number }[] }, onSettle: () => {} })
  const latest = useRef({ at, count, goTo })
  latest.current = { at, count, goTo }
  const reduced = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches

  const paint = useCallback(() => {
    const s = live.current, n = latest.current.count
    const shift = (clamp(s.pos, 0, VISIBLE) - clamp(n - 1 - s.pos, 0, VISIBLE)) * 0.5 // the hand stays centred when one side is short
    cards.current.forEach((el, i) => {
      if (!el) return
      const o = i - s.pos, t = Math.abs(o), side = Math.sign(o)
      const far = Math.min(t, VISIBLE + 1)
      const x = shift + side * Math.min(t, VISIBLE)
      const rot = side * (t <= 1 ? t * 3 : 3 + (t - 1) * 1.4)
      const lift = s.motion * Math.max(0, 1 - t) // the card crossing the middle swells and rises
      el.style.transform = `translateX(calc(var(--step) * ${x.toFixed(4)})) translateY(calc(var(--step) * ${(far * 0.12 - lift * 0.12).toFixed(4)})) rotate(${rot.toFixed(3)}deg) scale(${(1 - far * 0.03 + lift * 0.05).toFixed(4)})`
      el.style.zIndex = String(Math.round(1000 - t * 100 + s.dir * side * 5))
      el.style.opacity = String(clamp(VISIBLE + 1 - t, 0, 1))
      el.style.pointerEvents = t > VISIBLE + 0.5 ? 'none' : ''
      el.style.setProperty('--strip', String(clamp((t - 0.03) * 3, 0, 1)))
      el.style.setProperty('--face', String(clamp(1 - t * 2.5, 0, 1)))
      el.dataset.side = side < 0 ? 'l' : 'r'
    })
  }, [])

  const run = useCallback(() => {
    const s = live.current
    if (s.raf) return
    s.last = performance.now()
    const tick = (now: number) => {
      const dt = Math.min(0.032, (now - s.last) / 1000)
      s.last = now
      if (!s.drag?.moved) {
        s.vel += (-SPRING.k * (s.pos - s.target) - SPRING.c * s.vel) * dt
        s.pos += s.vel * dt
      }
      s.motion = Math.min(1, Math.abs(s.vel) / 3)
      const rest = !s.drag?.moved && Math.abs(s.pos - s.target) < 0.003 && Math.abs(s.vel) < 0.03 // under a quarter of a pixel off
      if (rest) { s.pos = s.target; s.vel = 0; s.motion = 0 }
      paint()
      if (rest) { s.raf = 0; s.onSettle(); return }
      s.raf = requestAnimationFrame(tick)
    }
    s.raf = requestAnimationFrame(tick)
  }, [paint])

  useLayoutEffect(() => { paint() }) // a re-render must not leave a card without its layout
  useEffect(() => {
    const s = live.current
    s.target = at
    if (reduced) { s.pos = at; s.vel = 0; s.motion = 0; paint(); return }
    s.dir = Math.sign(at - s.pos) || s.dir
    run()
  }, [at, reduced, paint, run])
  useEffect(() => () => cancelAnimationFrame(live.current.raf), [])

  const settle = (fn: () => void) => { live.current.onSettle = fn }
  const unit = () => (stage.current?.clientWidth ?? 800) * 0.22 // a card's worth of dragging
  const dragEnd = useRef(0) // a drag ends in a click on whatever was under the finger: swallow it
  const handlers = {
    onPointerDown: (e: ReactPointerEvent) => {
      if (e.button !== 0 || (e.target as Element).closest('input, textarea, select')) return
      live.current.drag = { x: e.clientX, pos: live.current.pos, moved: false, id: e.pointerId, marks: [{ x: e.clientX, t: e.timeStamp }] }
    },
    onPointerMove: (e: ReactPointerEvent) => {
      const s = live.current, d = s.drag
      if (!d) return
      const dx = e.clientX - d.x
      if (!d.moved) {
        if (Math.abs(dx) < 8) return
        d.moved = true
        stage.current?.setPointerCapture(d.id)
        s.vel = 0
      }
      d.marks.push({ x: e.clientX, t: e.timeStamp }); if (d.marks.length > 6) d.marks.shift()
      s.pos = clamp(d.pos - dx / unit(), -0.35, latest.current.count - 0.65) // a little give past either end
      s.dir = Math.sign(-dx) || s.dir
      s.motion = 0.5
      paint()
    },
    onPointerUp: (e: ReactPointerEvent) => {
      const s = live.current, d = s.drag
      s.drag = null
      if (!d?.moved) return
      dragEnd.current = Date.now()
      stage.current?.releasePointerCapture(d.id)
      const m = d.marks, first = m[0], lastMark = m[m.length - 1]
      const v = lastMark.t > first.t ? -(lastMark.x - first.x) / (lastMark.t - first.t) * 1000 / unit() : 0 // cards per second
      const to = clamp(Math.round(s.pos + v * 0.14), 0, latest.current.count - 1)
      s.vel = v * 0.4
      s.target = to
      s.dir = Math.sign(to - s.pos) || s.dir
      if (to !== latest.current.at) latest.current.goTo(to); else run()
      e.preventDefault()
    },
    onPointerCancel: () => { live.current.drag = null; live.current.target = latest.current.at; run() },
    onClickCapture: (e: React.MouseEvent) => { if (Date.now() - dragEnd.current < 80) { e.preventDefault(); e.stopPropagation() } },
  }
  const wheel = useRef(0)
  const onWheel = (e: React.WheelEvent) => {
    if (Math.abs(e.deltaX) < 24 || Math.abs(e.deltaX) < Math.abs(e.deltaY) || e.timeStamp - wheel.current < 420) return
    const to = clamp(latest.current.at + Math.sign(e.deltaX), 0, latest.current.count - 1)
    if (to === latest.current.at) return
    wheel.current = e.timeStamp
    latest.current.goTo(to)
  }
  return { stage, cards, handlers: { ...handlers, onWheel }, settle }
}


export function GateAsk({ deck, busy, issues, lines, changed, error, onAnswer, onOther, onDrop }: {
  deck: Deck; busy: boolean; issues: DeckIssue[]; lines: ReadbackLine[]; changed: boolean; error: string | null
  onAnswer: (answers: DeckAnswers) => void; onOther: () => void; onDrop: (target: string) => void
}) {
  const [at, setAt] = useState(0)
  const [ghost, setGhost] = useState<{ i: number; html: string } | null>(null) // the card just left, still showing its words while it slides away
  const front = useRef<HTMLDivElement>(null)
  const goTo = (i: number) => {
    if (i === at) return
    setGhost(front.current ? { i: at, html: front.current.innerHTML } : null)
    setAt(i)
    requestAnimationFrame(() => front.current?.focus({ preventScroll: true }))
  }
  const fan = useFan(deck.tabs.length, at, goTo)
  fan.settle(() => setGhost(null))
  const form = useDeckForm(deck, at)
  const { tab, selected, choose, skip, answers } = form
  if (!tab) return null
  const last = at >= deck.tabs.length - 1
  const normal = tab.options.filter(o => !['other', 'skip'].includes(o.id))
  const reasons = Array.from(new Set(tab.options.filter(o => o.prefilled && selected.includes(o.id) && o.because).map(o => o.because)))
  const notes = issues.filter(i => i.key === tab.qid || i.key.startsWith(`${tab.qid}.`))
  const rest = issues.filter(i => !deck.tabs.some(t => i.key === t.qid || i.key.startsWith(`${t.qid}.`)))
  const answered = (qid: string) => Object.keys(answers).some(k => k === qid || k.startsWith(`${qid}.`))
  const leftHere = deck.tabs.filter(t => !answered(t.qid)).length // the same set the cards show, falling as the user answers
  const [lead, tail] = split(tab.question)
  const bringForward = goTo
  const chips = (options: Option[]): ReactNode => <div className="tg-gt__opts">{options.map(o => <button type="button" key={o.id} className={`tg-gt__opt ${selected.includes(o.id) ? 'is-on' : ''}`} disabled={busy} aria-pressed={selected.includes(o.id)} onClick={() => choose(o)}>
    <b>{o.prefilled && <Icon name="edit" size={13} aria-label="Mình đoán" />}{o.label}</b>
    {o.description && <span>{o.description}</span>}
  </button>)}</div>
  return <div className="tg-gt__page tg-gt__fan" aria-busy={busy}>
    <header className="tg-gt__top">
      <div>
        <p className="tg-gt__kicker">Trước khi lên lịch</p>
        <Dialog.Title className="tg-gt__heading">Còn {leftHere} câu hỏi nữa thôi!</Dialog.Title>
        <Dialog.Description className="tg-gt__sub">Cho mình biết thêm một chút để lên lịch trình thật hợp ý bạn nhé.</Dialog.Description>
      </div>
      <span className="tg-gt__meter" role="img" aria-label={`Còn ${leftHere} trên ${deck.tabs.length} câu`}>Còn {leftHere}/{deck.tabs.length}<i><b style={{ width: `${(deck.tabs.length - leftHere) / deck.tabs.length * 100}%` }} /></i></span>
    </header>
    <div className={`tg-gt__stage ${deck.tabs[at]?.qid === 'lodging' ? 'is-lodging' : ''}`} role="group" aria-label="Các câu hỏi" ref={fan.stage} {...fan.handlers}>
      {deck.tabs.map((t, i) => {
        const on = i === at, done = answered(t.qid)
        return <div key={t.qid} ref={el => { fan.cards.current[i] = el }} className={`tg-gt__card ${on ? 'is-front' : ''} ${done ? 'is-done' : ''}`} style={{ '--tint': TINTS[i % TINTS.length] } as CSSProperties}>
          <button type="button" className="tg-gt__strip" disabled={busy || on} tabIndex={on ? -1 : 0} aria-hidden={on || undefined} onClick={() => goTo(i)} aria-label={`Câu ${i + 1}: ${t.header}${done ? ', đã trả lời' : ''}`}>
            <i>{done ? <Icon name="check" size={16} /> : <Icon name={TAB_ICON[t.qid] ?? 'sparkle'} size={18} />}</i>
            <span>{t.header}</span>
            <small>{i + 1}</small>
          </button>
          {!on && ghost?.i !== i && <div className="tg-gt__front is-peek" aria-hidden="true"><p className="tg-gt__cat"><span className="tg-gt__ico"><Icon name={TAB_ICON[t.qid] ?? 'sparkle'} size={20} /></span><b>{t.header}</b><small>{i + 1}/{deck.tabs.length}</small></p></div>}
          {ghost?.i === i && !on && <div className="tg-gt__front is-ghost" aria-hidden="true" ref={el => { if (el) el.inert = true }} dangerouslySetInnerHTML={{ __html: ghost.html }} />}
          {on && <div className="tg-gt__front" key={tab.qid} ref={front} tabIndex={-1} aria-current="step" aria-label={`Câu ${i + 1}: ${t.header}`}
            onKeyDown={e => { if (e.target !== e.currentTarget) return; if (e.key === 'ArrowRight') { e.preventDefault(); goTo(Math.min(at + 1, deck.tabs.length - 1)) } else if (e.key === 'ArrowLeft') { e.preventDefault(); goTo(Math.max(at - 1, 0)) } }}>
            <p className="tg-gt__cat"><span className="tg-gt__ico"><Icon name={TAB_ICON[t.qid] ?? 'sparkle'} size={20} /></span><b>{t.header}</b><small>{i + 1}/{deck.tabs.length}</small>{tab.multi && <em>Chọn được nhiều ý</em>}</p>
            <h2 className="tg-gt__q"><span>{lead}</span>{tail && <> <em>{tail}</em></>}</h2>
            {tab.why && <p className="tg-gt__why">{tab.why}</p>}
            <div className={`tg-gt__answer ${tab.qid === 'trip' ? 'is-trip' : ''}`}>
              {tab.qid === 'trip' && tab.kind === 'required' ? <GateTrip form={form} busy={busy} />
                : tab.visual ? <div className="tg-gt__pics">{normal.map(o => <button type="button" key={o.id} className={`tg-gt__pic ${selected.includes(o.id) ? 'is-on' : ''}`} disabled={busy} aria-pressed={selected.includes(o.id)} onClick={() => choose(o)}>
                  <span className="tg-gt__pic-img">{o.photo ? <img src={o.photo.url} alt={o.photo.name} loading="lazy" /> : <em>Chưa có ảnh</em>}<Icon name="check" size={18} /></span>
                  <b>{o.prefilled ? '✎ ' : ''}{o.label}</b>
                  <small>{o.count !== null ? `${o.count.toLocaleString('vi-VN')} nơi` : ''}</small>
                </button>)}</div> : chips(normal)}
              <ExtraInputs form={form} busy={busy} ranked />
              <DeckIssues issues={notes} />
              {tab.qid !== 'lodging' && (tab.options.some(o => o.id === 'other') || tab.options.some(o => o.id === 'skip')) && <div className="tg-gt__soft">
                {tab.options.some(o => o.id === 'other') && <button type="button" disabled={busy} onClick={onOther}>Khác, tự gõ</button>}
                {tab.options.some(o => o.id === 'skip') && <button type="button" disabled={busy} onClick={() => { skip(); if (!last) goTo(at + 1) }}>Bỏ qua{selected.includes('skip') ? ' ✓' : ''}</button>}
              </div>}
              {!!reasons.length && <p className="tg-gt__note"><Icon name="edit" size={15} />{reasons.join(' · ')}</p>}
            </div>
          </div>}
        </div>
      })}
    </div>
    <Checklist lines={lines} busy={busy} changed={changed} onEdit={onOther} onDrop={onDrop} />
    <footer className="tg-gt__foot">
      <div className="tg-gt__foot-l"><button type="button" className="tg-gt__link" disabled={busy} onClick={onOther}><Icon name="edit" size={16} />Sửa trong Tìm hiểu</button></div>
      <div className="tg-gt__foot-r">
        {error && <span className="tg-gt__err" role="alert">{error}</span>}
        <DeckIssues issues={rest} />
        <span className="tg-gt__hint">Trả lời xong là xếp lịch được</span>
        {!last && <button type="button" className="tg-gt__next" disabled={busy} onClick={() => bringForward(at + 1)}>Tiếp<Icon name="chevronRight" size={17} /></button>}
        <button type="button" className="tg-gt__go" disabled={busy || !Object.keys(answers).length} onClick={() => onAnswer(answers)}>Xong<Icon name="check" size={18} /></button>
      </div>
    </footer>
    {busy && <div className="tg-gt__wait" role="status"><span className="tg-dots"><i /><i /><i /></span><p>Đang ghi nhận lựa chọn của bạn…</p></div>}
  </div>
}

// ---- the trip tab: a calendar for the dates and a stepper for each hour, instead of the browser's own date and time boxes ----

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const fromIso = (value: string) => { const [y, m, d] = value.split('-').map(Number); return new Date(y, m - 1, d) }
const WEEK = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN']

function RangeCalendar({ from, to, busy, onPick }: { from: string; to: string; busy: boolean; onPick: (day: string) => void }) {
  const today = iso(new Date())
  const [shown, setShown] = useState(() => { const d = from ? fromIso(from) : new Date(); return new Date(d.getFullYear(), d.getMonth(), 1) })
  const lead = (shown.getDay() + 6) % 7 // Monday first
  const count = new Date(shown.getFullYear(), shown.getMonth() + 1, 0).getDate()
  const cells = [...Array<null>(lead).fill(null), ...Array.from({ length: count }, (_, i) => iso(new Date(shown.getFullYear(), shown.getMonth(), i + 1)))]
  const step = (n: number) => setShown(new Date(shown.getFullYear(), shown.getMonth() + n, 1))
  return <div className="tg-gt__cal">
    <div className="tg-gt__cal-head">
      <button type="button" aria-label="Tháng trước" onClick={() => step(-1)}><Icon name="chevronLeft" size={18} /></button>
      <b>Tháng {shown.getMonth() + 1}, {shown.getFullYear()}</b>
      <button type="button" aria-label="Tháng sau" onClick={() => step(1)}><Icon name="chevronRight" size={18} /></button>
    </div>
    <div className="tg-gt__cal-grid" role="grid" aria-label="Chọn ngày đến và ngày về">
      {WEEK.map(w => <span key={w} className="tg-gt__cal-w" aria-hidden="true">{w}</span>)}
      {cells.map((day, i) => day === null ? <span key={`b${i}`} /> : <button type="button" key={day} disabled={busy || day < today}
        className={`${day === from ? 'is-from' : ''} ${day === to ? 'is-to' : ''} ${from && to && day > from && day < to ? 'is-in' : ''} ${day === today ? 'is-today' : ''} ${from && to && from !== to && (day === from || day === to) ? 'is-edge' : ''}`}
        aria-pressed={day === from || day === to} aria-label={fromIso(day).toLocaleDateString('vi-VN', { weekday: 'long', day: 'numeric', month: 'long' })} onClick={() => onPick(day)}>{Number(day.slice(8))}</button>)}
    </div>
  </div>
}

function HourStepper({ label, value, options, selected, busy, onStep, onPreset }: { label: string; value: string; options: Option[]; selected: string[]; busy: boolean; onStep: (delta: number) => void; onPreset: (o: Option) => void }) {
  return <div className="tg-gt__hour">
    <span className="tg-gt__hour-l">{label}</span>
    <div className="tg-gt__hour-v">
      <button type="button" disabled={busy} aria-label="Sớm hơn 30 phút" onClick={() => onStep(-30)}><Icon name="minus" size={18} /></button>
      <output aria-live="polite">{value || '--:--'}</output>
      <button type="button" disabled={busy} aria-label="Muộn hơn 30 phút" onClick={() => onStep(30)}><Icon name="plus" size={18} /></button>
    </div>
    {!!options.length && <div className="tg-gt__hour-p">{options.map(o => <button type="button" key={o.id} disabled={busy} className={selected.includes(o.id) ? 'is-on' : ''} aria-pressed={selected.includes(o.id)} title={o.description || undefined} onClick={() => onPreset(o)}>{o.label.replace(/^(Bắt đầu|Kết thúc)\s*/i, '')}</button>)}</div>}
  </div>
}

function GateTrip({ form, busy }: { form: DeckForm; busy: boolean }) {
  const { tab, fields, selected, toggleInput, choose } = form
  const normal = tab.options.filter(o => !['other', 'skip'].includes(o.id))
  const from = fields.dateFrom ?? '', to = fields.dateTo ?? ''
  const pick = (day: string) => {
    if (!from || to) { toggleInput('dateFrom', day, 'dates.'); toggleInput('dateTo', '', 'dates.') }
    else if (day < from) toggleInput('dateFrom', day, 'dates.')
    else toggleInput('dateTo', day, 'dates.')
  }
  const days = from && to ? Math.round((fromIso(to).getTime() - fromIso(from).getTime()) / 86_400_000) + 1 : 0
  const shortDay = (d: string) => fromIso(d).toLocaleDateString('vi-VN', { day: 'numeric', month: 'numeric' })
  const dateOptions = normal.filter(o => o.id.startsWith('dates.'))
  const hour = (slot: 'start' | 'end') => fields[`trip.${slot}`] ?? clockOf(normal.find(o => selected.includes(o.id) && o.id.startsWith(`${slot}.`)) ?? { label: '', description: '', id: '' } as Option) ?? ''
  const nudge = (slot: 'start' | 'end', delta: number) => {
    const [h, m] = (hour(slot) || (slot === 'start' ? '08:00' : '18:00')).split(':').map(Number)
    const total = ((h * 60 + m + delta) % 1440 + 1440) % 1440
    toggleInput(`trip.${slot}`, `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`, `${slot}.`)
  }
  return <>
    {tab.inputs.includes('dates') && <div className="tg-gt__when">
      <p className="tg-gt__range" aria-live="polite">{from ? <><b>{shortDay(from)}</b><Icon name="arrow" size={18} /><b>{to ? shortDay(to) : 'Ngày về'}</b>{days > 0 && <small>{days} ngày</small>}</> : <span>Chọn ngày đến, rồi ngày về</span>}</p>
      <RangeCalendar from={from} to={to} busy={busy} onPick={pick} />
      {!!dateOptions.length && <div className="tg-gt__hour-p">{dateOptions.map(o => <button type="button" key={o.id} disabled={busy} className={selected.includes(o.id) ? 'is-on' : ''} aria-pressed={selected.includes(o.id)} onClick={() => choose(o)}>{o.prefilled && <Icon name="edit" size={13} aria-label="Mình đoán" />}{o.label}</button>)}</div>}
    </div>}
    <div className="tg-gt__hours">
      {(['start', 'end'] as const).filter(slot => tab.inputs.includes(slot)).map(slot => <HourStepper key={slot} label={slot === 'start' ? 'Ngày đầu bắt đầu lúc' : 'Ngày cuối kết thúc lúc'} value={hour(slot)}
        options={normal.filter(o => o.id.startsWith(`${slot}.`))} selected={selected} busy={busy} onStep={d => nudge(slot, d)} onPreset={choose} />)}
    </div>
  </>
}
