import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import * as Popover from '@radix-ui/react-popover'
import { createPortal } from 'react-dom'
import { fmtRange, info, priceText } from '../lib'
import { useDecision } from '../pd/decision'
import type { Card, Group } from '../pd/types'
import { toggleSaved, useUi } from '../store'
import { go, Hint, Photo, placeHref } from './common'
import { HeartFill, Icon, type IconName } from './icons'

const STEP = 13 // degrees between two wedges; keep equal to --step in disc.css
const NEAR = 6 // wedges further than this from the active one are not drawn on desktop
const ICONS: IconName[] = ['tree', 'flag', 'coffee', 'suitcase', 'utensils', 'compass']

// How many of the trip's wishes a card's reasons speak to; qualitative on purpose, never a bare percentage.
const fitOf = (c: Card) => ({ level: c.why.length >= 3 ? 'Rất hợp' : c.why.length === 2 ? 'Hợp' : c.why.length === 1 ? 'Khá hợp' : 'Tạm được', matched: c.why.map((w) => w.text) })

// Full-screen rotary wheel pinned to the left edge: every place is a wedge of the rim, the active one points straight at the user.
// The hub of the wheel holds the place groups. ↑ ↓ / wheel / click a wedge turn it; ← → browse the photos of the active place.
export function DiscPicker({ groups, tab, onTab, cmp, onCmp, onDrop, onBack }: { groups: Group[]; tab: string; onTab: (t: string) => void; cmp: string[]; onCmp: (id: string) => void; onDrop: (c: Card) => void; onBack: () => void }) {
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
  const acc = useRef(0)
  const last = useRef(0)
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
  useEffect(() => { if (found >= 0 && found !== active) setActive(found) }, [found, active])
  // Near the end of the loaded places: load the group's next page.
  useEffect(() => { if (group && n < group.total && i >= n - 4) more(group.id) }, [group, n, i, more])
  const show = (k: number) => { setActive(k); setActiveId(ids[k] ?? null) }
  const turn = (d: number) => show(Math.min(Math.max(0, i + d), Math.max(0, n - 1)))
  const browse = (d: number) => setG((v) => (shots ? (v + d + shots) % shots : 0))
  const turnRef = useRef(turn)
  turnRef.current = turn

  // The layer owns the wheel and the page behind it does not scroll.
  useEffect(() => {
    const el = root.current
    if (!el) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    el.focus({ preventScroll: true })
    const on = (e: WheelEvent) => {
      if (e.ctrlKey) return // pinch-zoom
      if (matchMedia('(max-width: 900px)').matches) return // the layer scrolls itself on small screens
      e.preventDefault()
      acc.current += e.deltaY
      const now = performance.now()
      if (Math.abs(acc.current) < 40 || now - last.current < 230) return
      last.current = now
      turnRef.current(acc.current > 0 ? 1 : -1)
      acc.current = 0
    }
    el.addEventListener('wheel', on, { passive: false })
    return () => { el.removeEventListener('wheel', on); document.body.style.overflow = prev }
  }, [])

  // Small screens: the wheel is a strip, keep the active wedge in view.
  useEffect(() => {
    if (!matchMedia('(max-width: 900px)').matches) return
    wheel.current?.querySelector<HTMLElement>(`[data-k="${i}"]`)?.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' })
  }, [i, tab])

  // The hub of the wheel: the four place groups sit on its inner arc as small icons; the name shows on hover or focus.
  const hub = (
    <div className="tg-disc__hub" role="group" aria-label="Nhóm địa điểm">
      {groups.map((t, k) => (
        <button key={t.id} type="button" className="tg-disc__cat" aria-pressed={tab === t.id} aria-label={`${t.label}, ${t.total} nơi`} style={{ '--ha': `${(k - (groups.length - 1) / 2) * 24}deg` } as CSSProperties} onClick={() => onTab(t.id)}>
          <Icon name={ICONS[k % ICONS.length]} size={18} />
          <span className="tg-disc__tip" aria-hidden="true">{t.label} <b>{t.total}</b></span>
        </button>
      ))}
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
        <p className="tg-disc__none">Chưa có nơi nào ở nhóm này.</p>
      </div>,
    )
  }
  const fit = fitOf(c)
  const isSel = c.chosen
  const isLock = c.locked
  const quote = p?.quotes[0]?.text ? clip(p.quotes[0].text, 130) : null
  const others = photos.map((_, j) => j).filter((j) => j !== g).slice(0, 3)
  const hint = (
    <>
      <b>{fit.level} với chuyến của bạn.</b> {fit.matched.length ? `Lý do: ${fit.matched.join('; ')}.` : 'Chưa khớp rõ với sở thích nào bạn đã nói.'} Đây là mức khớp sở thích, không phải điểm chất lượng.
    </>
  )
  return shell(
    <div className="tg-disc__field">
      {back}
      <div className="tg-disc__zone">
        {hub}
        <div className="tg-disc__wheel" key={tab} ref={wheel} role="listbox" aria-label="Danh sách nơi" aria-activedescendant={`tg-disc-${c.id}`} style={{ '--rot': `${-i * STEP}deg` } as CSSProperties}>
          {ids.map((id, k) => {
            const d = k - i
            const pl = cards[k]
            const ph = info(id)?.photos[0]
            const on = d === 0
            return (
              <div key={id} id={`tg-disc-${id}`} role="option" aria-selected={on} data-k={k} data-far={Math.abs(d) > NEAR || undefined}
                className={`tg-disc__wedge ${on ? 'is-on' : ''}`}
                style={{ '--a': `${k * STEP}deg`, '--fade': on ? 1 : Math.max(0.3, 1 - Math.abs(d) * 0.16) } as CSSProperties}>
                <button type="button" className="tg-disc__cut" onClick={() => show(k)} tabIndex={-1} aria-label={on ? pl.name : `Xoay tới ${pl.name}`}>
                  <Photo photo={ph} alt="" className="tg-disc__ph" eager />
                  <span className="tg-disc__nm">{pl.name}</span>
                  {pl.chosen && <i className="tg-disc__check"><Icon name="check" size={12} /></i>}
                </button>
              </div>
            )
          })}
        </div>
      </div>

      <section className="tg-disc__main" aria-live="polite">
        <div className="tg-disc__show" key={c.id}>
          <div className="tg-disc__copy">
            <p className="tg-disc__kick"><i />{[c.category, p?.area ?? c.area].filter(Boolean).join(' · ')}</p>
            <h2>{c.name}</h2>
            {quote && <p className="tg-disc__quote">“{quote}”<small>Trích từ đánh giá của người đã đến</small></p>}
            <p className="tg-disc__meta">
              <Hint label={hint}><span className={`tg-disc__fit is-${fit.level === 'Rất hợp' ? 'a' : fit.level === 'Hợp' ? 'b' : 'c'}`}><Icon name="heart" size={14} />{fit.level} với bạn<Icon name="info" size={13} /></span></Hint>
              {c.top && <span className="tg-tag tg-pc__top tg-disc__top">Hợp nhất</span>}
            </p>
            {c.tradeoffs[0] && <p className="tg-disc__trade"><Icon name="warn" size={15} />{c.tradeoffs[0].text}</p>}
            <div className="tg-disc__act">
              <button type="button" className="tg-disc__cta" onClick={() => go(placeHref(c.id))}>Xem chi tiết <Icon name="arrow" size={18} /></button>
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
            <div className="tg-disc__big">
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
          <div><dt>Giờ mở cửa</dt><dd>{p?.hours ?? 'Chưa rõ'}</dd></div>
          <div><dt>Thời gian tham quan</dt><dd>{c.visit ? `≈ ${fmtRange(c.visit.short, c.visit.long)}` : 'Chưa có'}</dd></div>
          <div><dt>Giá</dt><dd>{c.price ?? priceText(p?.price) ?? 'Chưa có dữ liệu'}</dd></div>
        </dl>

        <div className="tg-disc__nav">
          <button type="button" className="tg-btn tg-btn--ghost tg-btn--sm" onClick={() => turn(-1)} disabled={i === 0}><Icon name="chevronUp" size={16} /> Nơi trước</button>
          <span className="tg-mono" aria-label={`Nơi ${i + 1} trên ${n}`}>{i + 1} / {n}</span>
          <button type="button" className="tg-btn tg-btn--ghost tg-btn--sm" onClick={() => turn(1)} disabled={i >= n - 1}>Nơi sau <Icon name="chevronDown" size={16} /></button>
          <p className="tg-disc__hint"><kbd>↑</kbd><kbd>↓</kbd> hoặc cuộn: đổi nơi <i /> <kbd>←</kbd><kbd>→</kbd>: xem ảnh</p>
        </div>
      </section>
    </div>,
  )
}

const clip = (s: string, max: number) => {
  const t = s.replace(/\s+/g, ' ').trim()
  if (t.length <= max) return t
  return t.slice(0, max).replace(/\s+\S*$/, '') + '…'
}
