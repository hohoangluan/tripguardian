import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { impression } from '../events'
import * as Popover from '@radix-ui/react-popover'
import { createPortal } from 'react-dom'
import { fmtRange, info, priceText } from '../lib'
import { useDecision } from '../pd/decision'
import type { Card, Group } from '../pd/types'
import { toggleSaved, useUi } from '../store'
import { Hint, Photo } from './common'
import { FitStars } from './FitStars'
import { HeartFill, Icon, type IconName } from './icons'
import { openPlace } from './PlaceSheet'
import { hasSeen, markSeen } from './seen'

const BLADES = 7 // wedges on the half disc at most (3 above, the active one, 3 below): each photo stays large and clear;
// fewer places get wider wedges (180° / count, up to MAX_STEP)
const MAX_STEP = 45
const NARROW = '(max-width: 900px)'
// One-time hint on how to turn the disc (ui/seen.ts).
const TIP = 'disc-rotate'
const ICONS: IconName[] = ['tree', 'flag', 'coffee', 'suitcase', 'utensils', 'compass']

// The stars say how well the place fits this trip's wishes (server score, src/decision/rank.py), never its quality;
// the reasons always sit beside them.
const band = (stars: number) => (stars >= 4.5 ? 'a' : stars >= 3.5 ? 'b' : 'c')

// Full-screen rotary wheel pinned to the left edge: the places are wedges fanned over a half disc, the active one points
// straight at the user. It is a loop with no first place: turning past the last one comes back to the first.
// Wheel or drag on the disc, ↑ ↓, or a click on a wedge turn it; ← → browse the photos.
// The layer is the whole screen and, on a wide one, never scrolls: the wheel turns the disc. `lead` sits above the group tabs,
// `foot` below the place (it scrolls on its own if it outgrows its share); the open chat is a column of its own beside the place.
type Props = { groups: Group[]; tab: string; onTab: (t: string) => void; fresh: Record<string, number>; cmp: string[]; onCmp: (id: string) => void; onDrop: (c: Card) => void; conflicted: Set<string>; lead: ReactNode; foot: ReactNode; chat: ReactNode }
export function DiscPicker({ groups, tab, onTab, fresh, cmp, onCmp, onDrop, conflicted, lead, foot, chat }: Props) {
  const { act, busy, more } = useDecision()
  const group = groups.find((g) => g.id === tab)
  const cards = group?.cards ?? []
  const ids = cards.map((c) => c.id)
  // The place on show is followed by id, so a list rebuilt around it keeps it in the middle; the index is the
  // fallback for when that place left the list.
  const [active, setActive] = useState(0)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [g, setG] = useState(0)
  const root = useRef<HTMLDivElement>(null)
  const wheel = useRef<HTMLDivElement>(null)
  const bigRef = useRef<HTMLDivElement>(null)
  const chatOpen = useRef(Boolean(chat))
  const acc = useRef(0)
  const last = useRef(0)
  const drag = useRef<{ y: number; moved: boolean } | null>(null)
  const narrow = useMedia(NARROW)
  const saved = useUi((u) => u.saved)
  const n = ids.length
  const found = activeId ? ids.indexOf(activeId) : -1
  const i = found >= 0 ? found : Math.min(active, Math.max(0, n - 1))
  const c = n ? cards[i] : null
  const p = c ? info(c.id) : null
  const photos = p?.photos ?? []
  const shots = photos.length
  useEffect(() => { setActive(0); setActiveId(null) }, [tab, n === 0])
  useEffect(() => { setG(0) }, [i, tab])
  useEffect(() => { if (c) impression(c.id, tab, i + 1) }, [c?.id, tab]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (found >= 0 && found !== active) setActive(found) }, [found, active])
  // Near the end of the loaded places: load the group's next page.
  useEffect(() => { if (group && n < group.total && i >= n - 4) more(group.id) }, [group, n, i, more])
  const [tip, setTip] = useState(() => !hasSeen(TIP))
  const dismissTip = () => { markSeen(TIP); setTip(false) }
  const show = (k: number) => { dismissTip(); setActive(k); setActiveId(ids[k] ?? null) }
  const turn = (d: number) => { if (n > 1) show((((i + d) % n) + n) % n) }
  // The half disc: up to BLADES wedges around the active one, each placed by its shortest way round the loop.
  const blades = Math.min(n, BLADES)
  const step = Math.min(MAX_STEP, 180 / Math.max(blades, 1))
  const reach = Math.floor(blades / 2)
  const rel = (k: number) => { const d = (((k - i) % n) + n) % n; return d > n / 2 ? d - n : d }
  // A wedge that wraps from one end of the half disc to the other must jump, not sweep across the whole wheel.
  const before = useRef(new Map<string, number>())
  useEffect(() => { before.current = new Map(ids.map((id, k) => [id, rel(k)])) })
  const browse = (d: number) => setG((v) => (shots ? (v + d + shots) % shots : 0))
  const turnRef = useRef(turn)
  turnRef.current = turn

  // The layer holds still on a wide screen: scrolling anywhere on it turns the disc. Only the chat and the foot (when it has
  // more than fits) keep their own scroll.
  useEffect(() => {
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    if (!chatOpen.current) root.current?.focus({ preventScroll: true }) // an open chat keeps the focus it took
    return () => { document.body.style.overflow = prev }
  }, [])
  useEffect(() => {
    const el = root.current
    if (!el || narrow) return
    const on = (e: WheelEvent) => {
      if (e.ctrlKey) return // pinch-zoom
      const t = e.target as HTMLElement
      if (t.closest('.tg-disc__chat')) return
      const sc = t.closest<HTMLElement>('.tg-disc__foot')
      if (sc && (e.deltaY > 0 ? sc.scrollTop + sc.clientHeight < sc.scrollHeight - 1 : sc.scrollTop > 0)) return
      e.preventDefault()
      acc.current += Math.abs(e.deltaY) >= Math.abs(e.deltaX) ? e.deltaY : e.deltaX
      const now = performance.now()
      if (Math.abs(acc.current) < 30 || now - last.current < 140) return
      last.current = now
      turnRef.current(acc.current > 0 ? 1 : -1)
      acc.current = 0
    }
    el.addEventListener('wheel', on, { passive: false })
    return () => el.removeEventListener('wheel', on)
  }, [narrow])
  // Drag up or down on the disc to turn it, a wedge per 44 px; a drag never counts as a click on a wedge.
  const dragOn = narrow ? {} : {
    onPointerDown: (e: React.PointerEvent) => { if (e.button === 0) drag.current = { y: e.clientY, moved: false } },
    onPointerMove: (e: React.PointerEvent) => {
      const d = drag.current
      if (!d || !(e.buttons & 1)) return
      const dy = d.y - e.clientY
      if (Math.abs(dy) < 44) return
      d.y = e.clientY
      d.moved = true
      turn(dy > 0 ? 1 : -1)
    },
    onPointerUp: () => { window.setTimeout(() => { drag.current = null }, 0) },
    onPointerLeave: () => { drag.current = null },
  }

  // Small screens: the wheel is a strip, keep the active wedge in view.
  useEffect(() => {
    if (!narrow) return
    wheel.current?.querySelector<HTMLElement>(`[data-k="${i}"]`)?.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' })
  }, [i, tab, narrow])

  // The hub is the still centre of the wheel; the place groups are named tabs above the place, readable at any size.
  const hub = <div className="tg-disc__hub" aria-hidden="true" />
  const tabs = (
    <div className="tg-disc__tabs" role="tablist" aria-label="Nhóm địa điểm">
      {groups.map((t, k) => (
        <button key={t.id} type="button" role="tab" className="tg-tab" aria-selected={tab === t.id} onClick={() => onTab(t.id)}>
          <Icon name={ICONS[k % ICONS.length]} size={16} />{t.label}<b>{t.total}</b>{fresh[t.id] ? <i className="tg-tab__new" aria-label={`${fresh[t.id]} nơi mới`}>+{fresh[t.id]} mới</i> : null}
        </button>
      ))}
    </div>
  )
  // First visit only: a hand swipes up and down over the wheel to say it turns; it goes after a few swipes or the first turn.
  const hand = tip && n > 1 && !narrow && (
    <div className="tg-disc__hand" aria-hidden="true" onAnimationEnd={dismissTip}>
      <Icon name="chevronUp" size={18} /><Icon name="hand" size={40} /><Icon name="chevronDown" size={18} />
    </div>
  )

  const shell = (inner: ReactNode) => createPortal(
    <div className={`tg tg-disc ${chat ? 'has-chat' : ''}`} ref={root} tabIndex={-1} aria-label="Chọn nơi bằng đĩa xoay"
      onKeyDown={(e) => {
        if ((e.target as HTMLElement).closest('input, textarea, .tg-disc__chat')) return
        if (e.key === 'ArrowDown' || e.key === 'PageDown') { e.preventDefault(); turn(1) }
        else if (e.key === 'ArrowUp' || e.key === 'PageUp') { e.preventDefault(); turn(-1) }
        else if (e.key === 'ArrowRight') { e.preventDefault(); browse(1) }
        else if (e.key === 'ArrowLeft') { e.preventDefault(); browse(-1) }
        else if (e.key === 'Home') { e.preventDefault(); show(0) }
        else if (e.key === 'End') { e.preventDefault(); show(Math.max(0, n - 1)) }
      }}>{inner}{chat && <div className="tg-disc__chat">{chat}</div>}</div>, document.body)

  if (!c) {
    return shell(
      <div className="tg-disc__field">
        <div className="tg-disc__zone">{hub}</div>
        <section className="tg-disc__main">{lead}{tabs}<p className="tg-disc__none">Chưa có nơi nào ở nhóm này. Thử nhóm khác.</p><div className="tg-disc__foot">{foot}</div></section>
      </div>,
    )
  }
  const fit = c.fit
  const why = c.why.map((w) => w.text)
  const isSel = c.chosen
  const isLock = c.locked
  const quote = p?.quotes[0]?.text ? clip(p.quotes[0].text, 130) : null
  const others = photos.map((_, j) => j).filter((j) => j !== g).slice(0, 3)
  const hint = (
    <>
      <b>{fit?.level} với chuyến của bạn ({fit?.stars.toFixed(1)}/5 sao).</b> {why.length ? `Lý do: ${why.join('; ')}.` : 'Chưa khớp rõ với sở thích nào bạn đã nói.'} Đây là mức khớp sở thích, không phải điểm chất lượng.
    </>
  )
  return shell(
    <div className="tg-disc__field">
      <div className="tg-disc__zone" title="Lăn chuột hoặc kéo để xoay; ↑ ↓ cũng được" {...dragOn}>
        {hub}
        {hand}
        <div className="tg-disc__wheel" key={tab} ref={wheel} role="listbox" aria-label="Danh sách nơi" aria-activedescendant={`tg-disc-${c.id}`} style={{ '--step': `${step}deg` } as CSSProperties}>
          {ids.map((id, k) => {
            const d = narrow ? k - i : rel(k)
            if (!narrow && Math.abs(d) > reach) return null
            const pl = cards[k]
            const ph = info(id)?.photos[0]
            const on = d === 0
            const was = before.current.get(id)
            const jump = was === undefined || Math.abs(was - d) > 1
            return (
              <div key={id} id={`tg-disc-${id}`} role="option" aria-selected={on} data-k={k}
                className={`tg-disc__wedge ${on ? 'is-on' : ''} ${jump ? 'is-jump' : ''}`}
                style={{ '--d': d, '--fade': on ? 1 : Math.max(0.82, 1 - Math.abs(d) * 0.05) } as CSSProperties}>
                <button type="button" className="tg-disc__cut" onClick={() => { if (!drag.current?.moved) show(k) }} tabIndex={-1} aria-label={on ? pl.name : `Xoay tới ${pl.name}`}>
                  <Photo photo={ph} alt="" className="tg-disc__ph" eager sizes="(max-width: 900px) 168px, 560px" />
                  <span className="tg-disc__nm">{pl.name}</span>
                  {pl.chosen && <i className="tg-disc__check"><Icon name="check" size={12} /></i>}
                </button>
              </div>
            )
          })}
        </div>
      </div>

      <section className="tg-disc__main" aria-live="polite">
        {lead}
        {tabs}
        <div className="tg-disc__show" key={c.id}>
          <div className="tg-disc__copy">
            <p className="tg-disc__kick"><i />{[c.category, p?.area ?? c.area].filter(Boolean).join(' · ')}</p>
            <h2>{c.name}</h2>
            {quote && <p className="tg-disc__quote">“{quote}”<small>Trích từ đánh giá của người đã đến</small></p>}
            <p className="tg-disc__meta">
              {fit && <Hint label={hint}><span className={`tg-disc__fit is-${band(fit.stars)}`}><FitStars stars={fit.stars} />{fit.level} với bạn<Icon name="info" size={13} /></span></Hint>}
              {fit && why.length > 0 && <span className="tg-disc__why">{why.slice(0, 2).join(' · ')}</span>}
              {c.top && <span className="tg-tag tg-pc__top tg-disc__top">Hợp nhất</span>}
            </p>
            {(c.tradeoffs[0] || conflicted.has(c.id)) && <p className="tg-disc__trade"><Icon name="warn" size={15} />{c.tradeoffs[0]?.text ?? 'Đang vướng một chỗ cần chú ý'}</p>}
            <div className="tg-disc__act">
              <button type="button" className="tg-disc__cta" onClick={() => openPlace(c.id, bigRef.current)}>Xem chi tiết <Icon name="arrow" size={18} /></button>
              <button type="button" className={`tg-disc__ic ${isSel ? 'is-sel' : ''}`} onClick={() => (isSel ? onDrop(c) : act({ type: 'select', place_id: c.id }))} disabled={busy || (c.anchor && isSel)} aria-pressed={isSel} aria-label={isSel ? 'Bỏ khỏi chuyến' : 'Thêm vào chuyến'} title={isSel ? 'Đã trong chuyến, bấm để bỏ' : 'Thêm vào chuyến'}><Icon name={isSel ? 'check' : 'plus'} size={20} /></button>
              <button type="button" className={`tg-disc__ic ${saved.includes(c.id) ? 'is-on' : ''}`} onClick={() => toggleSaved(c.id, c.name)} aria-pressed={saved.includes(c.id)} aria-label="Lưu" title="Lưu">{saved.includes(c.id) ? <HeartFill size={18} /> : <Icon name="heart" size={18} />}</button>
              <Popover.Root>
                <Popover.Trigger asChild><button type="button" className="tg-disc__ic" aria-label="Thêm tùy chọn" title="Thêm"><Icon name="sliders" size={18} /></button></Popover.Trigger>
                <Popover.Portal>
                  <Popover.Content className="tg tg-disc__menu" side="top" align="start" sideOffset={8} collisionPadding={16}>
                    <button type="button" onClick={() => act({ type: isLock ? 'unlock' : 'lock', place_id: c.id })} aria-pressed={isLock}><Icon name={isLock ? 'lock' : 'unlock'} size={16} />{isLock ? 'Bỏ khóa nơi này' : 'Khóa nơi này'}</button>
                    <button type="button" onClick={() => onCmp(c.id)} aria-pressed={cmp.includes(c.id)}><Icon name="swap" size={16} />{cmp.includes(c.id) ? 'Bỏ khỏi so sánh' : 'Thêm vào so sánh'}</button>
                    <button type="button" onClick={() => onDrop(c)}><Icon name="x" size={16} />Bỏ nơi này</button>
                  </Popover.Content>
                </Popover.Portal>
              </Popover.Root>
            </div>
          </div>

          <div className="tg-disc__media">
            <div className="tg-disc__big" ref={bigRef}>
              <Photo key={g} photo={photos[g]} alt={`${c.name}, ảnh ${g + 1} trên ${shots}`} className="tg-disc__ph is-fade" eager sizes="(max-width: 900px) 92vw, 640px" />
              {isSel && <i className="tg-disc__chip"><Icon name="check" size={14} /> Đã chọn</i>}
              {shots > 0 && <span className="tg-disc__credit">Ảnh: {photos[g].credit} · {g + 1}/{shots}</span>}
            </div>
            {others.length > 0 && (
              <div className="tg-disc__thumbs">
                {others.map((j) => (
                  <button key={j} type="button" className="tg-disc__thumb" onClick={() => setG(j)} aria-label={`Xem ảnh ${j + 1} trên ${shots}`}>
                    <Photo photo={photos[j]} alt="" className="tg-disc__ph" eager />
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <dl className="tg-disc__stats">
          <div><dt>Điểm Google</dt><dd>{p?.rating ? `${p.rating.toFixed(1).replace('.', ',')}${p.reviews ? ` · ${p.reviews.toLocaleString('vi-VN')} lượt` : ''}` : 'Chưa có'}</dd></div>
          <div><dt>Giờ mở cửa</dt><dd>{p?.hours ? (p.hoursVary ? `${p.hours} (hôm nay)` : p.hours) : 'Chưa rõ'}</dd></div>
          <div><dt>Thời gian tham quan</dt><dd>{c.visit ? `≈ ${fmtRange(c.visit.short, c.visit.long)}` : 'Chưa có'}</dd></div>
          <div><dt>Giá</dt><dd>{c.price ?? priceText(p?.price) ?? 'Chưa có dữ liệu'}</dd></div>
        </dl>
        <div className="tg-disc__foot">{foot}</div>
      </section>
    </div>,
  )
}

const clip = (s: string, max: number) => {
  const t = s.replace(/\s+/g, ' ').trim()
  if (t.length <= max) return t
  return t.slice(0, max).replace(/\s+\S*$/, '') + '…'
}

function useMedia(query: string) {
  const [on, setOn] = useState(() => matchMedia(query).matches)
  useEffect(() => {
    const m = matchMedia(query)
    const f = () => setOn(m.matches)
    m.addEventListener('change', f)
    return () => m.removeEventListener('change', f)
  }, [query])
  return on
}
