import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { impression } from '../events'
import * as Popover from '@radix-ui/react-popover'
import { createPortal } from 'react-dom'
import { fmtMin, fmtRange, fmtVnd, info, priceText } from '../lib'
import { useDecision } from '../pd/decision'
import type { LodgingCandidate } from '../planning/types'
import { LODGING_TAB, useLodgingChange, useLodgingMore, type LodgingList } from '../screens/Lodging'
import type { Card, Group } from '../pd/types'
import { useDetail } from '../../data/store'
import { toggleSaved, useUi } from '../store'
import { cardLines } from './cardLines'
import { Photo } from './common'
import { HeartFill, Icon, type IconName } from './icons'
import { openPlace } from './PlaceSheet'

const BLADES = 7 // wedges on the half disc at most (3 above, the active one, 3 below): each photo stays large and clear;
// fewer places get wider wedges (180° / count, up to MAX_STEP)
const MAX_STEP = 45
const NARROW = '(max-width: 900px)'
// One place per wheel turn: quick enough to flick through the list, slow enough that each place is read as it passes.
// The wheel's own rotation (disc.css) is 360 ms, so a turn every 230 ms keeps the disc always moving and never stacking up.
const TURN_GAP_MS = 230
const TURN_AT = 24 // wheel distance that makes one turn; a mouse notch (100) passes it at once, a trackpad adds up to it in a moment
const IDLE_MS = 140 // a pause this long forgets a leftover half-turn
const ICONS: IconName[] = ['tree', 'flag', 'coffee', 'suitcase', 'utensils', 'compass']

// A stay as the card the wheel shows for a place: the wheel, the photos and the facts read it the same way.
const stayCard = (c: LodgingCandidate, chosenId: string | null, top: boolean): Card => ({
  id: c.id, name: c.name, category: c.category ?? null, area: c.area ?? null, role: 'experience', group: 'stay', status: 'main', score: 0, parts: {},
  why: c.why ?? [], tradeoffs: c.tradeoffs ?? [], visit: null, location: { center: c.location?.center ?? '', km: c.location?.km ?? null, minutes: c.location?.minutes ?? null },
  price: c.price_vnd ? `${fmtVnd(c.price_vnd)}/đêm` : null, confidence: c.confidence ?? { level: 'low', reason: '' }, declined: false, depends_on_unknown: null,
  warnings: [], unverified: c.unverified ?? [], failed: [], chosen: chosenId === c.id, locked: false, anchor: false, alternatives: [], suggested: false, top,
}) as unknown as Card

// Full-screen rotary wheel pinned to the left edge: the places are wedges fanned over a half disc, the active one points
// straight at the user. It is a loop with no first place: turning past the last one comes back to the first.
// The hub holds the place groups. Wheel or drag on the disc, ↑ ↓, or a click on a wedge turn it; ← → browse the photos.
// The rest of the layer scrolls like a page.
export function DiscPicker({ groups, tab, onTab, cmp, onCmp, onDrop, onBack, lodging }: { groups: Group[]; tab: string; onTab: (t: string) => void; cmp: string[]; onCmp: (id: string) => void; onDrop: (c: Card) => void; onBack: () => void; lodging: LodgingList | null }) {
  const { act, busy } = useDecision()
  const stay = useLodgingChange()
  const stayMore = useLodgingMore(lodging ?? { opts: null, setOpts: () => {}, failed: false })
  const onStay = Boolean(lodging) && tab === LODGING_TAB
  const group = onStay ? undefined : groups.find((g) => g.id === tab)
  const stays = lodging?.opts?.candidates ?? []
  const stayId = stay.chosen?.id ?? stay.booked?.id ?? null
  const cards = onStay ? stays.map((x, k) => stayCard(x, stayId, k === 0 && Boolean(x.fit?.length))) : group?.cards ?? []
  const ids = cards.map((c) => c.id)
  // The place on show is followed by id, so a list rebuilt around it keeps it in the middle; the index is the
  // fallback for when that place left the list.
  const [active, setActive] = useState(0)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [g, setG] = useState(0)
  const root = useRef<HTMLDivElement>(null)
  const zone = useRef<HTMLDivElement>(null)
  const wheel = useRef<HTMLDivElement>(null)
  const bigRef = useRef<HTMLDivElement>(null)
  const acc = useRef(0)
  const last = useRef(0)
  const seen = useRef(0)
  const drag = useRef<{ y: number; moved: boolean } | null>(null)
  const narrow = useMedia(NARROW)
  const saved = useUi((u) => u.saved)
  const n = ids.length
  const found = activeId ? ids.indexOf(activeId) : -1
  const i = found >= 0 ? found : Math.min(active, Math.max(0, n - 1))
  const c = n ? cards[i] : null
  useDetail(c ? [c.id] : []) // the quote under the photo comes with the evidence
  const p = c ? info(c.id) : null
  const photos = p?.photos ?? []
  const shots = photos.length
  useEffect(() => { setActive(0); setActiveId(null) }, [tab, n === 0])
  useEffect(() => { setG(0) }, [i, tab])
  useEffect(() => { if (c && !onStay) impression(c.id, tab, i + 1) }, [c?.id, tab]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (found >= 0 && found !== active) setActive(found) }, [found, active])
  useEffect(() => { if (onStay && stayMore.more && i >= n - 4) stayMore.load() }, [onStay, stayMore.more, stayMore.loading, n, i]) // eslint-disable-line react-hooks/exhaustive-deps
  const show = (k: number) => { setActive(k); setActiveId(ids[k] ?? null) }
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

  // The layer scrolls like a page and the page behind it does not; the wheel over the disc turns the disc instead.
  useEffect(() => {
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    root.current?.focus({ preventScroll: true })
    return () => { document.body.style.overflow = prev }
  }, [])
  useEffect(() => {
    const el = root.current // anywhere on the disc layer turns the wheel, not only over the wheel itself
    if (!el || narrow) return
    const on = (e: WheelEvent) => {
      if (e.ctrlKey || (e.target as HTMLElement).closest('input, textarea, [role="dialog"], .tg-disc__menu')) return // pinch-zoom, typing, a dialog
      e.preventDefault()
      const now = performance.now()
      if (now - seen.current > IDLE_MS) acc.current = 0
      seen.current = now
      acc.current += Math.abs(e.deltaY) >= Math.abs(e.deltaX) ? e.deltaY : e.deltaX
      if (Math.abs(acc.current) < TURN_AT) return
      if (now - last.current < TURN_GAP_MS) { acc.current = Math.sign(acc.current) * TURN_AT * 0.5; return } // too soon: keep a little, so a long flick carries on at the pace of the gap
      last.current = now
      turnRef.current(acc.current > 0 ? 1 : -1)
      acc.current = 0
    }
    el.addEventListener('wheel', on, { passive: false })
    return () => el.removeEventListener('wheel', on)
  }, [narrow, n === 0]) // eslint-disable-line react-hooks/exhaustive-deps
  // Drag up or down on the disc to turn it, a wedge per 36 px; a drag never counts as a click on a wedge.
  const dragOn = narrow ? {} : {
    onPointerDown: (e: React.PointerEvent) => { if (e.button === 0) drag.current = { y: e.clientY, moved: false } },
    onPointerMove: (e: React.PointerEvent) => {
      const d = drag.current
      if (!d || !(e.buttons & 1)) return
      const dy = d.y - e.clientY
      if (Math.abs(dy) < 36) return
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
          <Icon name={ICONS[k % ICONS.length]} size={16} />{t.label}<b>{t.total}</b>
        </button>
      ))}
      {lodging && (
        <button type="button" role="tab" className="tg-tab" aria-selected={onStay} onClick={() => onTab(LODGING_TAB)}>
          <Icon name="bed" size={16} />Nơi lưu trú{lodging.opts?.total ? <b>{lodging.opts.total}</b> : lodging.failed ? null : <b className="tg-tab__wait" aria-label="Đang đếm"><i /></b>}
        </button>
      )}
    </div>
  )
  const back = <button type="button" className="tg-disc__back" onClick={onBack} aria-label="Quay lại dạng lưới" title="Quay lại dạng lưới"><Icon name="arrowLeft" size={22} /></button>

  const shell = (inner: ReactNode) => createPortal(
    <div className="tg tg-disc" ref={root} tabIndex={-1} aria-label="Chọn nơi bằng đĩa xoay"
      onKeyDown={(e) => {
        if ((e.target as HTMLElement).closest('input, textarea')) return
        if (e.key === 'ArrowDown' || e.key === 'PageDown') { e.preventDefault(); turn(1) }
        else if (e.key === 'ArrowUp' || e.key === 'PageUp') { e.preventDefault(); turn(-1) }
        else if (e.key === 'ArrowRight') { e.preventDefault(); browse(1) }
        else if (e.key === 'ArrowLeft') { e.preventDefault(); browse(-1) }
        else if (e.key === 'Home') { e.preventDefault(); show(0) }
        else if (e.key === 'End') { e.preventDefault(); show(Math.max(0, n - 1)) }
        else if (e.key === 'Escape') { e.preventDefault(); onBack() }
      }}>{inner}</div>, document.body)

  if (!c) {
    return shell(
      <div className="tg-disc__field">
        {back}
        <div className="tg-disc__zone">{hub}</div>
        <section className="tg-disc__main">{tabs}<p className="tg-disc__none">{onStay ? (lodging?.failed ? 'Chưa tải được danh sách nơi lưu trú. Thử lại sau ít phút.' : lodging?.opts ? 'Chưa có nơi lưu trú nào khớp với chuyến này.' : 'Đang tải nơi lưu trú…') : 'Chưa có nơi nào ở nhóm này. Thử nhóm khác.'}</p></section>
      </div>,
    )
  }
  const { why, trade, alerts } = cardLines(c) // the grid card's lines: one logic, drawn for the disc
  const isSel = c.chosen
  const isLock = c.locked
  const quote = p?.quotes[0]?.text ? clip(p.quotes[0].text, 130) : null
  const others = photos.map((_, j) => j).filter((j) => j !== g).slice(0, 3)
  return shell(
    <div className="tg-disc__field">
      {back}
      <div className="tg-disc__zone" ref={zone} title="Lăn chuột hoặc kéo để xoay; ↑ ↓ cũng được" {...dragOn}>
        {hub}
        {!narrow && n > 1 && (
          <p className="tg-disc__hint" role="note">
            <span aria-hidden="true"><Icon name="chevronDown" size={16} style={{ rotate: '180deg' }} /><Icon name="chevronDown" size={16} /></span>
            Lăn chuột lên hoặc xuống để xoay đĩa
          </p>
        )}
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
        {tabs}
        <div className="tg-disc__show" key={c.id}>
          <div className="tg-disc__copy">
            <p className="tg-disc__kick"><i />{[c.category, p?.area ?? c.area].filter(Boolean).join(' · ')}</p>
            <h2>{c.name}</h2>
            {quote && <p className="tg-disc__quote">“{quote}”<small>Trích từ đánh giá của người đã đến</small></p>}
            {c.top && <p className="tg-disc__meta"><span className="tg-tag tg-pc__top tg-disc__top">Hợp nhất</span></p>}
            {why.length ? (
              <ul className="tg-disc__why" aria-label="Vì sao phù hợp">
                {why.map((r) => <li key={r.text}><Icon name="check" size={15} />{r.text}</li>)}
              </ul>
            ) : <p className="tg-faint">Chưa có lý do rõ.</p>}
            {trade ? <p className="tg-disc__trade"><Icon name="warn" size={15} /><span><b>Đánh đổi:</b> {trade}</span></p> : <p className="tg-faint">Chưa thấy điều gì đáng ngại.</p>}
            {alerts.map((n) => <p key={n} className="tg-disc__alert"><Icon name="warn" size={14} />{n}</p>)}
            <div className="tg-disc__act">
              <button type="button" className="tg-disc__cta" onClick={() => openPlace(c.id, bigRef.current)}>Xem chi tiết <Icon name="arrow" size={18} /></button>
              {onStay ? (
                <button type="button" className={`tg-disc__ic ${isSel ? 'is-sel' : ''}`} onClick={() => stay.change({ type: 'set_lodging', lodging: { kind: 'corpus', id: c.id } }, c.name)} disabled={busy || isSel} aria-pressed={isSel} aria-label={isSel ? 'Đang chọn nơi lưu trú này' : stay.current ? 'Đổi sang nơi lưu trú này' : 'Chọn nơi lưu trú này'} title={isSel ? 'Bạn đang ở đây' : stay.current ? 'Đổi sang nơi này' : 'Chọn nơi lưu trú này'}><Icon name={isSel ? 'check' : stay.current ? 'swap' : 'plus'} size={20} /></button>
              ) : (
              <button type="button" className={`tg-disc__ic ${isSel ? 'is-sel' : ''}`} onClick={() => (isSel ? onDrop(c) : act({ type: 'select', place_id: c.id }))} disabled={busy || (c.anchor && isSel)} aria-pressed={isSel} aria-label={isSel ? 'Bỏ khỏi chuyến' : 'Thêm vào chuyến'} title={isSel ? 'Đã trong chuyến, bấm để bỏ' : 'Thêm vào chuyến'}><Icon name={isSel ? 'check' : 'plus'} size={20} /></button>
              )}
              <button type="button" className={`tg-disc__ic ${saved.includes(c.id) ? 'is-on' : ''}`} onClick={() => toggleSaved(c.id, c.name)} aria-pressed={saved.includes(c.id)} aria-label="Lưu" title="Lưu">{saved.includes(c.id) ? <HeartFill size={18} /> : <Icon name="heart" size={18} />}</button>
              {!onStay && <Popover.Root>
                <Popover.Trigger asChild><button type="button" className="tg-disc__ic" aria-label="Thêm tùy chọn" title="Thêm"><Icon name="sliders" size={18} /></button></Popover.Trigger>
                <Popover.Portal>
                  <Popover.Content className="tg tg-disc__menu" side="top" align="start" sideOffset={8} collisionPadding={16}>
                    <button type="button" onClick={() => act({ type: isLock ? 'unlock' : 'lock', place_id: c.id })} aria-pressed={isLock}><Icon name={isLock ? 'lock' : 'unlock'} size={16} />{isLock ? 'Bỏ khóa nơi này' : 'Khóa nơi này'}</button>
                    <button type="button" onClick={() => onCmp(c.id)} aria-pressed={cmp.includes(c.id)}><Icon name="swap" size={16} />{cmp.includes(c.id) ? 'Bỏ khỏi so sánh' : 'Thêm vào so sánh'}</button>
                    <button type="button" onClick={() => onDrop(c)}><Icon name="x" size={16} />Bỏ nơi này</button>
                  </Popover.Content>
                </Popover.Portal>
              </Popover.Root>}
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
          <div><dt>Đánh giá</dt><dd>{p?.rating ? `${p.rating.toFixed(1).replace('.', ',')}${p.reviews ? ` · ${p.reviews.toLocaleString('vi-VN')} lượt` : ''}` : 'Chưa có'}</dd></div>
          {onStay ? <div><dt>Cách trung tâm</dt><dd>{c.location.minutes != null ? `≈ ${c.location.minutes} phút` : 'Chưa có'}</dd></div> : <div><dt>Giờ mở cửa</dt><dd>{p?.hours ?? 'Chưa rõ'}</dd></div>}
          {onStay ? <div><dt>Tới các nơi đã chọn</dt><dd>{stays[i]?.avg_min != null ? `≈ ${fmtMin(stays[i].avg_min as number)}` : 'Chưa có'}</dd></div> : <div><dt>Thời gian tham quan</dt><dd>{c.visit ? `≈ ${fmtRange(c.visit.short, c.visit.long)}` : 'Chưa có'}</dd></div>}
          <div><dt>{onStay ? 'Giá mỗi đêm' : 'Giá'}</dt><dd>{c.price ?? priceText(p?.price) ?? 'Chưa có dữ liệu'}</dd></div>
        </dl>
        {stay.dialog}

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
