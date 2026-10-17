import { useEffect, useRef, useState, type CSSProperties, type KeyboardEvent } from 'react'
import { createPortal } from 'react-dom'
import type { Deck, DeckAnswers, DeckIssue, Option, Tab } from '../../tu/types'
import { CardImg, preloadPhotos } from '../../ui/common'
import { Icon } from '../../ui/icons'
import { DeckIssues, ExtraInputs, TAB_ICON, TripInputs, useDeckForm } from './Deck'

// The chat's one question (docs/UI_SPEC_USER_WEB.md Trang 3). The question itself is a line of the chat (Turn); the
// card under it is a short numbered list like an assistant's quick question: at most three options, a fourth row to
// type another answer. A single choice with nothing else to fill sends at once. A photo question opens a stage over
// the blurred screen so the user looks at the places, not the chat.

const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches

export function AskCard({ deck, busy, issues = [], onAnswer, onText }: {
  deck: Deck; busy: boolean; issues?: DeckIssue[]
  onAnswer: (answers: DeckAnswers, shown: string) => void
  onText: (text: string) => void
}) {
  const form = useDeckForm(deck, 0)
  const { tab, selected, choose, answers } = form
  const [typed, setTyped] = useState('')
  const [sent, setSent] = useState<string | null>(null)
  const root = useRef<HTMLElement>(null)
  if (!tab) return null
  const normal = tab.options.filter(o => !['other', 'skip'].includes(o.id))
  const grouped = tab.qid === 'trip' && tab.kind === 'required'
  const instant = !tab.multi && !grouped && !tab.inputs.length // one tap answers it
  // a row to type another answer only makes sense next to options: a card that asks only for a number, a date or a stay has none
  const canOther = tab.options.some(o => o.id === 'other') && normal.length > 0
  const canSkip = tab.options.some(o => o.id === 'skip')
  const reasons = tab.options.filter(o => o.prefilled && selected.includes(o.id) && o.because).map(o => o.because)
  const pick = (o: Option) => {
    if (busy || sent) return
    if (instant) {
      setSent(o.id)
      window.setTimeout(() => onAnswer({ [tab.qid]: [o.id] }, o.label), reduced() ? 0 : 180) // the row confirms before the turn starts
      return
    }
    choose(o)
  }
  const other = () => {
    const text = typed.trim()
    if (!text || busy) return
    setTyped('')
    onText(text)
  }
  const keys = (e: KeyboardEvent<HTMLElement>) => {
    if ((e.target as HTMLElement).tagName === 'INPUT') return
    const n = Number(e.key)
    if (n >= 1 && n <= normal.length) { e.preventDefault(); pick(normal[n - 1]) }
    if (n === normal.length + 1 && canOther) { e.preventDefault(); root.current?.querySelector<HTMLInputElement>('.tg-qa__other input')?.focus() }
  }
  const chips = (options: Option[]) => <div className="tg-qa__chips">{options.map(o => <button type="button" key={o.id} className={`tg-qa__chip ${selected.includes(o.id) ? 'is-on' : ''}`} disabled={busy} aria-pressed={selected.includes(o.id)} onClick={() => choose(o)}>{o.prefilled && <span aria-label="Mình đoán">✎ </span>}{o.label}</button>)}</div>
  return <section ref={root} className={`tg-qa ${busy ? 'is-waiting' : ''} ${sent ? 'is-sent' : ''}`} data-deck-qid={tab.qid} aria-label={tab.header} onKeyDown={keys}>
    <header className="tg-qa__head">
      <Icon name={TAB_ICON[tab.qid] ?? 'sparkle'} size={16} />
      <b>{tab.header}</b>
      <span>{!normal.length ? 'Nhập hoặc chọn' : tab.multi ? 'Chọn một hoặc nhiều' : grouped ? 'Chọn hoặc nhập' : 'Chọn một'}</span>
    </header>
    {grouped && <div className="tg-qa__fill"><TripInputs form={form} busy={busy} chips={chips} /></div>}
    <ol className="tg-qa__list" role="list">
      {!grouped && normal.map((o, i) => {
        const on = sent === o.id || selected.includes(o.id)
        return <li key={o.id} style={{ '--i': i } as CSSProperties}>
          <button type="button" className={`tg-qa__opt ${on ? 'is-on' : ''}`} disabled={busy || !!sent} aria-pressed={on} onClick={() => pick(o)}>
            <kbd aria-hidden="true">{i + 1}</kbd>
            <span className="tg-qa__txt"><b>{o.prefilled && <span className="tg-qa__guess" aria-label="Mình đoán">✎</span>}{o.label}</b>{o.description && <small>{o.description}</small>}</span>
            <span className="tg-qa__tick" aria-hidden="true"><Icon name="check" size={14} strokeWidth={2.4} /></span>
          </button>
        </li>
      })}
      {canOther && <li className="tg-qa__other" style={{ '--i': grouped ? 0 : normal.length } as CSSProperties}>
        <kbd aria-hidden="true">{grouped ? '✎' : normal.length + 1}</kbd>
        <input type="text" value={typed} disabled={busy || !!sent} placeholder="Khác: gõ câu trả lời của bạn…" aria-label="Câu trả lời khác"
          onChange={e => setTyped(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing) { e.preventDefault(); other() } }} />
        <button type="button" className="tg-qa__send" disabled={busy || !typed.trim()} aria-label="Gửi câu trả lời khác" onClick={other}><Icon name="send" size={16} /></button>
      </li>}
    </ol>
    {!grouped && <ExtraInputs form={form} busy={busy} send={onAnswer} />}
    {!!reasons.length && <p className="tg-qa__why">✎ {Array.from(new Set(reasons)).join(' · ')}</p>}
    <DeckIssues issues={issues} />
    {(canSkip || !instant) && <footer className="tg-qa__foot">
      {canSkip && <button type="button" className="tg-qa__skip" disabled={busy || !!sent} onClick={() => { setSent('skip'); onAnswer({ [tab.qid]: ['skip'] }, 'Bỏ qua') }}>Bỏ qua</button>}
      {!instant && <button type="button" className="tg-btn tg-btn--primary tg-qa__go" disabled={busy || !Object.keys(answers).length} onClick={() => onAnswer(answers, shownOf(tab, form.selected, form.fields))}>Gửi <Icon name="arrow" size={16} /></button>}
    </footer>}
  </section>
}

// What the user filled in, as the line the answered card folds into.
function shownOf(tab: Tab, selected: string[], fields: Record<string, string>) {
  const day = (d: string) => d.slice(8, 10) + '/' + d.slice(5, 7)
  const parts = tab.options.filter(o => selected.includes(o.id) && !/^(start|end)\./.test(o.id)).map(o => o.label)
  if (fields.dateFrom && fields.dateTo) parts.unshift(`${day(fields.dateFrom)} – ${day(fields.dateTo)}`)
  if (fields['trip.start']) parts.push(`bắt đầu ${fields['trip.start']}`)
  if (fields['trip.end']) parts.push(`xong ${fields['trip.end']}`)
  if (fields['companions.people']) parts.push(`${fields['companions.people']} người`)
  if (fields['budget.amount']) parts.push(`${fields['budget.amount']} triệu`)
  if (fields.lodging) parts.push(JSON.parse(fields.lodging).text)
  return parts.join(' · ') || tab.header
}

// A photo question: real places of each kind on cards, the middle one in front, the screen behind blurred.
export function PhotoStage({ deck, busy, onAnswer, onText }: {
  deck: Deck; busy: boolean
  onAnswer: (answers: DeckAnswers, shown: string) => void
  onText: (text: string) => void
}) {
  const tab = deck.tabs[0]
  const options = tab.options.filter(o => !['other', 'skip'].includes(o.id))
  useEffect(() => preloadPhotos(options.map(o => o.photo?.url)), [deck]) // eslint-disable-line react-hooks/exhaustive-deps
  const [open, setOpen] = useState(true)
  const [at, setAt] = useState(() => Math.max(0, Math.floor((options.length - 1) / 2)))
  const [chosen, setChosen] = useState<string[]>(() => options.filter(o => o.prefilled).map(o => o.id))
  const [typed, setTyped] = useState('')
  const [leaving, setLeaving] = useState(false)
  const panel = useRef<HTMLDivElement>(null)
  const ring = useRef<HTMLDivElement>(null)
  const opener = useRef<HTMLButtonElement>(null)
  // The mouse wheel turns the row one card per notch; a short rest between turns keeps a trackpad from racing through.
  useEffect(() => {
    const el = ring.current
    if (!open || !el) return
    let rest = 0, sum = 0
    const turn = (e: WheelEvent) => {
      e.preventDefault()
      sum += Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY
      const now = performance.now()
      if (Math.abs(sum) < 40 || now < rest) return
      const step = Math.sign(sum) // read now: the updater below runs later, after sum is reset
      setAt(i => Math.max(0, Math.min(options.length - 1, i + step)))
      sum = 0; rest = now + 260
    }
    el.addEventListener('wheel', turn, { passive: false })
    return () => el.removeEventListener('wheel', turn)
  }, [open, options.length])
  // The screen behind is blurred by filtering the app root: backdrop-filter on the veil is dropped by some browsers.
  useEffect(() => {
    if (!open) return
    document.documentElement.classList.add('tg-stage-open')
    return () => document.documentElement.classList.remove('tg-stage-open')
  }, [open])
  useEffect(() => {
    if (!open) return
    const last = document.activeElement as HTMLElement | null
    panel.current?.focus()
    return () => last?.focus?.()
  }, [open])
  const close = () => {
    if (reduced()) { setOpen(false); return }
    setLeaving(true)
    window.setTimeout(() => { setLeaving(false); setOpen(false) }, 220) // leaving is quicker than arriving
  }
  const toggle = (id: string) => setChosen(c => c.includes(id) ? c.filter(x => x !== id) : tab.multi ? [...c, id] : [id])
  const send = (answers: DeckAnswers, shown: string) => { close(); onAnswer(answers, shown) }
  const keys = (e: KeyboardEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).tagName === 'INPUT') return
    if (e.key === 'Escape') { e.preventDefault(); close() }
    if (e.key === 'ArrowRight') { e.preventDefault(); setAt(i => Math.min(options.length - 1, i + 1)) }
    if (e.key === 'ArrowLeft') { e.preventDefault(); setAt(i => Math.max(0, i - 1)) }
    if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); if (options[at]) toggle(options[at].id) }
    if (e.key === 'Tab') { // keep the focus inside the stage
      const items = [...(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled)') ?? [])]
      if (!items.length) return
      const i = items.indexOf(document.activeElement as HTMLElement)
      const next = e.shiftKey ? (i <= 0 ? items.length - 1 : i - 1) : (i === items.length - 1 ? 0 : i + 1)
      e.preventDefault(); items[next].focus()
    }
  }
  const summary = <button ref={opener} type="button" className="tg-stage__reopen" disabled={busy} onClick={() => setOpen(true)}>
    <span className="tg-stage__thumbs" aria-hidden="true">{options.slice(0, 3).map(o => o.photo ? <CardImg key={o.id} src={o.photo.url} alt="" /> : <i key={o.id} />)}</span>
    <span><b>{tab.header}</b><small>{options.length} kiểu nơi có ảnh thật · bấm để chọn</small></span>
    <Icon name="chevronRight" size={18} />
  </button>
  return <>
    {summary}
    {open && createPortal(<div className={`tg tg-stage-overlay ${leaving ? 'is-leaving' : ''}`} onKeyDown={keys}>
      <div className="tg-stage__veil" aria-hidden="true" onClick={close} />
      <div ref={panel} className="tg-stage__panel" role="dialog" aria-modal="true" aria-labelledby="tg-stage-q" tabIndex={-1}>
        <header className="tg-stage__head">
          <span className="tg-stage__kicker"><Icon name="image" size={15} />{tab.header}</span>
          <h3 id="tg-stage-q">{tab.question}</h3>
          {tab.why && <p>{tab.why}</p>}
          <button type="button" className="tg-stage__x" aria-label="Để sau" onClick={close}><Icon name="x" size={18} /></button>
        </header>
        <div ref={ring} className="tg-stage__ring" role="listbox" aria-label="Các kiểu nơi" aria-multiselectable={tab.multi}>
          {options.map((o, i) => {
            const d = i - at
            const on = chosen.includes(o.id)
            return <div key={o.id} role="option" aria-selected={on} className={`tg-stage__card ${d === 0 ? 'is-front' : ''} ${on ? 'is-on' : ''}`}
              style={{ '--d': d, '--a': Math.abs(d), '--n': i, ...(Math.abs(d) > 2 ? { '--far': 'hidden' } : {}) } as CSSProperties}
              onClick={() => (d === 0 ? toggle(o.id) : setAt(i))}>
              <div className="tg-stage__photo">{o.photo ? <CardImg src={o.photo.url} alt={o.photo.name} draggable={false} /> : <span>Chưa có ảnh</span>}</div>
              <div className="tg-stage__body">
                <b>{o.label}</b>
                <small><Icon name="pin" size={13} />{o.count !== null ? `${o.count.toLocaleString('vi-VN')} nơi` : 'Nơi thật'}{o.photo?.name ? ` · ${o.photo.name}` : ''}</small>
              </div>
              <button type="button" className="tg-stage__pick" tabIndex={d === 0 ? 0 : -1} aria-label={on ? `Bỏ chọn ${o.label}` : `Chọn ${o.label}`} aria-pressed={on} disabled={busy}
                onClick={e => { e.stopPropagation(); setAt(i); toggle(o.id) }}><Icon name={on ? 'check' : 'plus'} size={18} strokeWidth={2.2} /></button>
            </div>
          })}
          {at > 0 && <button type="button" className="tg-stage__nav is-prev" aria-label="Kiểu trước" onClick={() => setAt(at - 1)}><Icon name="chevronLeft" size={20} /></button>}
          {at < options.length - 1 && <button type="button" className="tg-stage__nav is-next" aria-label="Kiểu sau" onClick={() => setAt(at + 1)}><Icon name="chevronRight" size={20} /></button>}
        </div>
        <div className="tg-stage__dots" aria-hidden="true">{options.map((o, i) => <i key={o.id} className={`${i === at ? 'is-at' : ''} ${chosen.includes(o.id) ? 'is-on' : ''}`} />)}</div>
        <p className="tg-stage__hint"><span className="tg-stage__mouse"><Icon name="mouse" size={18} /></span>Lăn chuột hoặc dùng ← → để xoay · bấm thẻ giữa để chọn · {at + 1}/{options.length}</p>
        <footer className="tg-stage__foot">
          {tab.options.some(o => o.id === 'other') && <label className="tg-stage__other">
            <input type="text" value={typed} placeholder="Khác: tả kiểu bạn thích…" disabled={busy} onChange={e => setTyped(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && typed.trim() && !e.nativeEvent.isComposing) { e.preventDefault(); close(); onText(typed.trim()) } }} />
          </label>}
          {tab.options.some(o => o.id === 'skip') && <button type="button" className="tg-btn tg-btn--ghost" disabled={busy} onClick={() => send({ [tab.qid]: ['skip'] }, 'Bỏ qua')}>Bỏ qua</button>}
          {typed.trim()
            ? <button type="button" className="tg-btn tg-btn--primary" disabled={busy} onClick={() => { close(); onText(typed.trim()) }}>Gửi ý của bạn <Icon name="send" size={16} /></button>
            : <button type="button" className="tg-btn tg-btn--primary" disabled={busy || !chosen.length} onClick={() => send({ [tab.qid]: chosen }, options.filter(o => chosen.includes(o.id)).map(o => o.label).join(' · '))}>
              {chosen.length ? `Chọn ${chosen.length} kiểu` : 'Chọn ít nhất một'} <Icon name="check" size={16} />
            </button>}
        </footer>
      </div>
    </div>, document.body)}
  </>
}
