import { useMemo, useRef, useState, type ReactNode } from 'react'
import { dayLabel, fmtMin, info, toMin } from '../../lib'
import type { CrowdTip, DayConditions, DayRoute, ItineraryDay, ItineraryItem } from '../../planning/types'
import { PlacePhoto } from '../../ui/common'
import { Icon } from '../../ui/icons'
import { FlowBar } from '../../ui/Shell'
import { Conditions, VisitDuration } from './parts'
import { useSlide, useStopDrag } from './reorder'
import { BLOCK, BLOCK_NOTE, MEAL_LABEL, dayAreas, shortDate, visits } from './shared'
import { MapsLink, TripMap } from './TripMap'

// Mẫu ui_mock_for_design/designs/itinerary (màn từng ngày): the day's stops on the left, its route on the right.
// The day bar stays put, the list scrolls on its own. Order is changed by dragging a card or with the up / down buttons;
// the server lays the day out again (times and legs) and sends it back.

interface Stop { id: string; it: ItineraryItem; leg: number; mode: string | undefined; pre: ItineraryItem[] }

function stopsOf(d: ItineraryDay) {
  const stops: Stop[] = []
  let leg = 0
  let mode: string | undefined
  let pre: ItineraryItem[] = []
  for (const it of d.items) {
    if (it.kind === 'travel') { leg += toMin(it.end) - toMin(it.start); mode = it.mode }
    else if (it.kind === 'visit' && it.place_id) { stops.push({ id: it.place_id, it, leg, mode, pre }); leg = 0; mode = undefined; pre = [] }
    else pre.push(it)
  }
  return { stops, tail: pre }
}

function Block({ it }: { it: ItineraryItem }) {
  const dur = toMin(it.end) - toMin(it.start)
  const label = it.kind === 'meal_free' ? MEAL_LABEL[it.name ?? ''] ?? BLOCK.meal_free : it.name ?? BLOCK[it.kind] ?? it.kind
  return <div className="tg-it-block" title={BLOCK_NOTE[it.kind]}><Icon name={it.kind === 'meal_free' ? 'utensils' : it.kind === 'wait' ? 'clock' : 'coffee'} size={14} /><time className="tg-mono">{it.start}</time><span>{label}</span><small>{dur} phút{it.kind === 'meal_free' ? ' · Tự chọn' : ''}</small></div>
}

const MODE_ICON: Record<string, 'walk' | 'bike' | 'car'> = { walk: 'walk', motorbike: 'bike', car: 'car' }

export function DayView({ days, dayIdx, week, onDay, busy, locked, durationRange, durationOverrides, cond, tips, vehicle, extras, footer, summary, route,
  onBack, onOpen, onSwap, onDrop, onMoveDay, onReorder, onDuration }: {
  days: ItineraryDay[]; dayIdx: number; week: number; onDay: (i: number) => void; busy: boolean; locked: string[]
  durationRange?: [number, number]; durationOverrides: Record<string, number>; cond: DayConditions | undefined; tips: CrowdTip[]
  vehicle: string; extras: ReactNode; footer: ReactNode; summary: string
  route: DayRoute | null // this day's road from planning/routes; null while it loads or when the day has none
  onBack: () => void; onOpen: (id: string) => void; onSwap: (place: string | null) => void; onDrop: (place: string) => void
  onMoveDay: (place: string, day: number) => void; onReorder: (day: number, order: string[]) => Promise<boolean>
  onDuration: (place: string, minutes: number | null) => void
}) {
  const d = days[dayIdx]
  const [allMap, setAllMap] = useState(false)
  const [hot, setHot] = useState<string | null>(null)
  const { stops, tail } = useMemo(() => (d ? stopsOf(d) : { stops: [], tail: [] }), [d])
  const byId = useMemo(() => new Map(stops.map((s) => [s.id, s])), [stops])
  const baseOrder = useMemo(() => stops.map((s) => s.id), [stops])
  const [dragOrder, setDragOrder] = useState<string[] | null>(null)
  const [wait, setWait] = useState<{ day: number; order: string[] } | null>(null)
  const waiting = wait && d && wait.day === d.day ? wait.order : null
  const shown = dragOrder ?? waiting ?? baseOrder
  const order = [...shown.filter((id) => byId.has(id)), ...baseOrder.filter((id) => !shown.includes(id))]
  const stale = !!dragOrder || !!waiting
  const listRef = useRef<HTMLOListElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  const commit = async (next: string[]) => {
    setDragOrder(null)
    if (!d || next.join('|') === baseOrder.join('|')) return
    setWait({ day: d.day, order: next })
    await onReorder(d.day - 1, next)
    setWait(null)
  }
  const drag = useStopDrag({ listRef, scrollRef, order, enabled: !busy && !waiting, onPreview: setDragOrder, onCommit: commit })
  useSlide(listRef, scrollRef, order.join('|'), drag.landing, drag.landed)
  const moveBy = (id: string, delta: number) => {
    const at = order.indexOf(id)
    const to = at + delta
    if (at < 0 || to < 0 || to >= order.length || busy || waiting) return
    const next = [...order]
    next.splice(at, 1)
    next.splice(to, 0, id)
    void commit(next)
  }

  const weekDays = days.map((x, i) => ({ x, i })).filter(({ i }) => days.length <= 7 || Math.floor(i / 7) === week)
  const dayIds = order
  const tripIds = days.flatMap((x, i) => (i === dayIdx ? order : visits(x).map((it) => it.place_id!)))
  const l = d ? dayLabel(d.date) : null
  const totalLeg = d ? stops.reduce((n, s) => n + s.leg, 0) : 0
  const totalStay = d ? stops.reduce((n, s) => n + toMin(s.it.end) - toMin(s.it.start), 0) : 0
  // the day's own road: only while the order on screen is the order the road was drawn for
  const road = route?.route && !stale && !allMap ? route.route : null
  const mapRoutes = useMemo(() => (allMap ? undefined : [road]), [allMap, road])
  const first = d?.items[0]
  const last = d?.items[d.items.length - 1]
  const startName = route?.start.name ?? 'Điểm xuất phát'
  const endName = route?.end.name ?? 'Điểm kết thúc'
  return (
    <>
      <FlowBar step="plan" />
      <main className="tg-it-day">
        <section className="tg-it-day__pane" aria-label={`Lịch ngày ${d?.day ?? ''}`}>
          <div className="tg-it-crumb">
            <button type="button" className="tg-it-crumb__back" aria-label="Về tổng quan" onClick={onBack}><Icon name="arrowLeft" size={18} /></button>
            <button type="button" onClick={onBack}>Tổng quan</button><Icon name="chevronRight" size={14} /><strong>Lịch trình</strong>
          </div>
          <div className="tg-it-tabs">
            <button type="button" className="tg-it-round" aria-label="Ngày trước" disabled={dayIdx === 0} onClick={() => onDay(dayIdx - 1)}><Icon name="chevronLeft" size={16} /></button>
            <div role="tablist" aria-label="Ngày" onKeyDown={(e) => {
              if (!days.length || !['ArrowRight', 'ArrowLeft'].includes(e.key)) return
              e.preventDefault()
              const bar = e.currentTarget
              const next = (dayIdx + (e.key === 'ArrowRight' ? 1 : days.length - 1)) % days.length
              onDay(next)
              requestAnimationFrame(() => bar.querySelector<HTMLButtonElement>(`[data-day="${next}"]`)?.focus())
            }}>
              {weekDays.map(({ x, i }) => <button key={x.day} type="button" role="tab" data-day={i} aria-selected={i === dayIdx} tabIndex={i === dayIdx ? 0 : -1} className="tg-it-tab" onClick={() => onDay(i)}>{shortDate(x.date, x.day)}</button>)}
            </div>
            <button type="button" className="tg-it-round" aria-label="Ngày sau" disabled={dayIdx >= days.length - 1} onClick={() => onDay(dayIdx + 1)}><Icon name="chevronRight" size={16} /></button>
          </div>
          <div className={`tg-it-scroll ${drag.dragging ? 'is-reordering' : ''}`} ref={scrollRef}>
            {d && <div className="tg-it-dayhead" key={d.day}>
              <div>
                <h1>Ngày {d.day}</h1>
                <p>{l ? `${l.wd} · ${shortDate(d.date)}` : d.weekday || 'Chưa có ngày'}{dayAreas(d).length ? ` · ${dayAreas(d).join(', ')}` : ''}</p>
                <small>{summary}</small>
              </div>
              {stops.length > 1 && <span className="tg-it-hint"><Icon name="grip" size={15} strokeWidth={3.2} />Nhấn giữ thẻ để kéo</span>}
            </div>}
            {d && stops.length > 0 && <dl className="tg-it-stats is-day" aria-label={`Tóm tắt ngày ${d.day}`}>
              <div><dt>Điểm dừng</dt><dd>{stops.length}</dd></div>
              <div><dt>Di chuyển</dt><dd>{totalLeg ? `≈ ${fmtMin(totalLeg)}` : '—'}</dd></div>
              <div><dt>Ở lại</dt><dd>{fmtMin(totalStay)}</dd></div>
              {vehicle && <div><dt>Đi bằng</dt><dd>{vehicle}</dd></div>}
            </dl>}
            <Conditions c={cond} tips={tips} />
            {waiting && <p className="tg-it-warn" role="status"><Icon name="clock" size={14} />Đã đổi thứ tự · đang tính lại giờ và chặng đi…</p>}
            <ol className="tg-it-list" ref={listRef} onPointerDown={drag.onPointerDown} onDragStart={(e) => e.preventDefault()}>
              {stops.length > 0 && <li className={`tg-it-endrow is-start ${stale ? 'is-stale' : ''}`}><span className="tg-it-node" aria-hidden="true" /><small>Xuất phát{first ? ` · ${first.start}` : ''}</small><b>{startName}</b></li>}
              {order.map((id, i) => {
                const s = byId.get(id)!
                const p = info(id)
                const name = s.it.name ?? p?.name ?? id
                const dur = toMin(s.it.end) - toMin(s.it.start)
                const fixed = locked.includes(id)
                const manual = durationOverrides[id] !== undefined
                return (
                  <li key={id} data-stop={id} onMouseEnter={() => setHot(id)} onMouseLeave={() => setHot(null)} onFocus={() => setHot(id)} onBlur={() => setHot(null)} className={`tg-it-stop ${hot === id ? 'is-hot' : ''} ${drag.dragging === id ? 'is-slot' : ''} ${stale ? 'is-stale' : ''}`}>
                    {s.pre.map((b, k) => <Block key={k} it={b} />)}
                    {s.leg > 0 && <p className="tg-it-leg"><Icon name={MODE_ICON[s.mode ?? ''] ?? 'bike'} size={14} />≈ {s.leg} phút{vehicle ? ` ${vehicle}` : ''} di chuyển</p>}
                    <article className="tg-it-card">
                      <div className="tg-it-card__top">
                        <div className="tg-it-grip" aria-hidden="true"><Icon name="grip" size={20} strokeWidth={3.6} /><span>{i + 1}</span></div>
                        <button type="button" className="tg-it-card__photo" data-drag-ok aria-label={`Xem chi tiết ${name}`} onClick={() => { if (!drag.justDragged()) onOpen(id) }}>
                          <PlacePhoto id={id} name={name} sizes="132px" />
                        </button>
                        <div className="tg-it-card__info">
                          <div className="tg-it-card__cat">{p?.category ?? 'Địa điểm'}</div>
                          <h2><button type="button" onClick={() => onOpen(id)}>{name}</button></h2>
                          <div className="tg-it-card__meta">
                            <span className="tg-it-rate"><Icon name="star" size={14} />{p?.rating != null ? <><b>{p.rating.toFixed(1)}</b>{p.reviews != null && <span>({p.reviews.toLocaleString('vi-VN')})</span>}</> : <span>Chưa có đánh giá</span>}</span>
                            <span className="tg-it-sub"><Icon name="pin" size={14} />{p?.area ?? 'Đà Lạt'}</span>
                            <span className="tg-it-sub"><Icon name="clock" size={14} />Ở lại ≈ {fmtMin(dur)}</span>
                          </div>
                        </div>
                      </div>
                      <div className="tg-it-card__bottom">
                        <div className="tg-it-when">
                          <span className="tg-it-time">{waiting ? 'Giờ ghé đang tính lại' : <><b className="tg-mono">{s.it.start}</b> · Ước tính</>}</span>
                          <div className="tg-it-moves">
                            <button type="button" aria-label={`Đưa ${name} lên trên`} title="Đưa lên trên" disabled={i === 0 || busy || !!waiting} onClick={() => moveBy(id, -1)}><Icon name="chevronUp" size={16} /></button>
                            <button type="button" aria-label={`Đưa ${name} xuống dưới`} title="Đưa xuống dưới" disabled={i === order.length - 1 || busy || !!waiting} onClick={() => moveBy(id, 1)}><Icon name="chevronDown" size={16} /></button>
                          </div>
                        </div>
                        <div className="tg-it-acts">
                          {fixed ? <span className="tg-it-locked"><Icon name="lock" size={13} />Nơi bắt buộc</span> : <>
                            <button type="button" className="tg-it-outline" disabled={busy} onClick={() => onSwap(id)}><Icon name="swap" size={15} />Đổi</button>
                            <button type="button" className="tg-it-round" aria-label={`Bỏ ${name}`} title="Tạm bỏ" disabled={busy} onClick={() => onDrop(id)}><Icon name="trash" size={16} /></button>
                          </>}
                        </div>
                      </div>
                      <div className="tg-it-card__more">
                        {days.length > 1 && <label className="tg-faint">Ngày ghé <select aria-label={`Ngày ghé ${name}`} disabled={busy || fixed} value={d.day - 1} onChange={(e) => onMoveDay(id, Number(e.target.value))}>{Array.from({ length: Math.ceil(days.length / 7) }, (_, w) => <optgroup key={w} label={`Tuần ${w + 1}`}>{days.filter((x) => Math.floor((x.day - 1) / 7) === w).map((x) => <option key={x.day} value={x.day - 1}>Ngày {x.day}</option>)}</optgroup>)}</select></label>}
                        <VisitDuration key={`${id}:${dur}`} place={id} name={name} minutes={dur} bounds={durationRange} manual={manual} disabled={busy || fixed} onPreview={onDuration} />
                      </div>
                      {s.it.note && s.it.note.includes(' ') && <p className="tg-it-warn"><Icon name="warn" size={14} />{s.it.note}</p>}
                    </article>
                  </li>
                )
              })}
              {tail.map((b, k) => <li key={`t${k}`} className={`tg-it-tail ${stale ? 'is-stale' : ''}`}><Block it={b} /></li>)}
              {stops.length > 0 && <li className={`tg-it-endrow is-end ${stale ? 'is-stale' : ''}`}><span className="tg-it-node" aria-hidden="true" /><small>Kết thúc ngày{last ? ` · ${last.end}` : ''}</small><b>{endName}</b></li>}
            </ol>
            {!stops.length && <p className="tg-it-empty">Ngày tự do: bạn có thể nghỉ, tự khám phá hoặc thêm một nơi muốn ghé.</p>}
            <div className="tg-it-add"><button type="button" aria-label="Thêm trải nghiệm" disabled={busy} onClick={() => onSwap(null)}><Icon name="plus" size={20} /></button><span>Thêm trải nghiệm</span></div>
            <div className="tg-it-extras">{extras}</div>
            <p className="tg-it-small">Giờ giấc và đường đi là ước tính. Ảnh và đánh giá: catalog Google Maps.</p>
          </div>
          {footer}
        </section>
        <section className="tg-it-day__map" aria-label="Bản đồ">
          <TripMap groups={allMap ? days.map((x, i) => (i === dayIdx ? order : visits(x).map((it) => it.place_id!))) : [dayIds]} title={allMap ? 'Lộ trình cả chuyến' : `Lộ trình ngày ${d?.day ?? ''}`} className={allMap ? '' : 'is-main'} hot={hot} onHot={setHot} onOpen={onOpen}
            routes={mapRoutes} ends={road ? { start: startName, end: endName } : undefined}>
            <div className="tg-it-map__top">
              <span className="tg-it-chip is-label">{allMap ? 'Cả chuyến' : `Ngày ${d?.day ?? ''}`} · {(allMap ? tripIds : dayIds).length} điểm dừng</span>
              <div><button type="button" className="tg-it-chip" aria-pressed={allMap} onClick={() => setAllMap((v) => !v)}>Cả chuyến</button><MapsLink ids={allMap ? tripIds : dayIds} /></div>
            </div>
            <span className="tg-it-map__note">{road ? `Đường đi ước tính ≈ ${fmtMin(road.minutes)} · không phải chỉ đường` : 'Đường nối minh họa thứ tự · không phải chỉ đường'}</span>
          </TripMap>
        </section>
      </main>
    </>
  )
}

