import { useState } from 'react'
import { mapsRouteEmbed } from '../../data/store'
import { dayLabel, fmtMin, fmtVnd, info, toMin } from '../lib'
import { usePlanning } from '../planning/planning'
import type { Action, Backups, CrowdTip, DayConditions, ItineraryDay, ItineraryItem, Slot, Variant, View, Warning } from '../planning/types'
import { ADVISORY, groupNotes, LEG_ICON, LEG_WORD, legMode, NOTE_ICON, RENTAL_NOTE, rentalStep } from '../planning/view'
import { lodgingSuggest } from '../tu/api'
import type { LodgingHit } from '../tu/types'
import { Link, placeHref, PlacePhoto } from '../ui/common'
import { Icon } from '../ui/icons'
import { PlaceInput, lodgingRow } from '../ui/PlaceInput'
import { SlotPick } from '../ui/SlotPick'
import { lodgingAct } from './Lodging'

// The by-hour page of Lịch trình ("Xem chi tiết theo giờ"): one day at a time as a timeline with a Google map, and the
// lodging, backups and trip notes beside it. The journey page (Plan.tsx) is the main view; this is where a traveller
// reads and edits the clock (docs/WEB.md Trang 8).

const BLOCK: Record<string, string> = { meal_free: 'Ăn (tự chọn)', rest: 'Nghỉ', wait: 'Chờ', buffer: 'Đệm' }
const MEAL: Record<string, string> = { lunch: 'Ăn trưa', dinner: 'Ăn tối' }
export const SLOT: Record<Slot, string> = { dawn: 'Bình minh', sunset: 'Hoàng hôn', evening: 'Buổi tối', any: 'Giờ khác' }
const BLOCK_NOTE: Record<string, string> = { meal_free: 'Bạn tự chọn quán, mình gợi ý vài quán gần đó đang mở.', rest: 'Nghỉ chân, về chỗ ở hoặc ngồi lại.', wait: 'Chờ nơi tiếp theo mở cửa.', buffer: 'Thời gian dự phòng, trễ một chút vẫn ổn.' }
const TRAVELMODE: Record<string, string> = { motorbike: 'two-wheeler', car: 'driving', walk: 'walking' }
// Google Maps directions for the trip's own vehicle (Maps URLs: travelmode two-wheeler is the motorbike mode).
const routeLink = (stops: { lat: number; lng: number }[], vehicle: string | null) => {
  const pt = (s: { lat: number; lng: number }) => `${s.lat},${s.lng}`
  const q = new URLSearchParams({ api: '1', origin: pt(stops[0]), destination: pt(stops[stops.length - 1]), travelmode: TRAVELMODE[vehicle ?? ''] ?? 'driving' })
  if (stops.length > 2) q.set('waypoints', stops.slice(1, -1).map(pt).join('|'))
  return `https://www.google.com/maps/dir/?${q}`
}

const visits = (d: ItineraryDay) => d.items.filter((it) => it.kind === 'visit' && it.place_id)
type Fit = { stars: number; level: string } | null | undefined

export function PlanDetail({ days, view, variant, warnings, hot, setHot, onEdit, busy, act, fitOf, ctx, vehicle, onAdd }: {
  days: ItineraryDay[]; view: View; variant: Variant | null; warnings: Warning[]; hot: string | null; setHot: (v: string | null) => void; onEdit: (id: string) => void
  busy: boolean; act: (a: Action) => Promise<void>; fitOf: (id: string) => Fit; ctx: Parameters<typeof rentalStep>[0]; vehicle: string | null; onAdd: () => void
}) {
  const [picked, setDayIdx] = useState<number | null>(null) // null: the first day that has a stop
  const dayIdx = picked ?? Math.max(0, days.findIndex((x) => visits(x).length > 0))
  const d = days[Math.min(dayIdx, days.length - 1)]
  return (
    <div className="tg-plan__cols">
      <section aria-label="Ngày" className="tg-days">
        <div className="tg-daytabs" role="tablist" aria-label="Ngày" onKeyDown={(e) => { if (e.key === 'ArrowRight') setDayIdx((dayIdx + 1) % days.length); if (e.key === 'ArrowLeft') setDayIdx((dayIdx + days.length - 1) % days.length) }}>
          {days.map((x, i) => {
            const l = dayLabel(x.date)
            const load = view.travel_load?.[i]
            return <button key={x.day} type="button" role="tab" aria-selected={d?.day === x.day} tabIndex={d?.day === x.day ? 0 : -1} className="tg-daytab" onClick={() => setDayIdx(i)}><b>Ngày {x.day}</b><span>{l ? `${l.wd} · ${l.dm}` : x.weekday || 'Chưa có ngày'}</span>{load && <em className="tg-mono">≈{fmtMin(load.travel_min)} đi</em>}</button>
          })}
        </div>
        {d && <DayBlock d={d} cond={view.day_conditions?.find((c) => c.day === d.day)} tips={view.crowd_tips ?? []} hot={hot} setHot={setHot} slots={view.slots ?? {}} state={view.state} onEdit={onEdit} busy={busy} act={act} fitOf={fitOf} rental={rentalStep(ctx, Math.min(dayIdx, days.length - 1), days.length)} />}
        <div className="tg-plan__links"><button type="button" className="tg-link" disabled={busy} onClick={onAdd}><Icon name="plus" size={14} /> Thêm nơi</button><button type="button" className="tg-link tg-link--quiet" disabled={busy} onClick={onAdd}>Quay lại chọn nơi</button></div>
      </section>
      <section aria-label="Bản đồ" className="tg-plan__map"><DayMap d={d} vehicle={vehicle} /></section>
      <aside aria-label="Chỗ nghỉ và dự phòng" className="tg-side">
        <SideLodging />
        <BackupCard b={variant?.backups} day={d?.day ?? 1} busy={busy} onSwap={(place, w) => act({ type: 'swap', place, with: w })} />
        <TripNotes warnings={warnings} />
      </aside>
    </div>
  )
}

// Facts about the date, from live sources and hand-entered notices; no notice is not the same as "all clear".
function Conditions({ c, tips }: { c: DayConditions | undefined; tips: CrowdTip[] }) {
  const items: { icon: 'rain' | 'cloud' | 'users' | 'calendar' | 'warn' | 'info' | 'clock'; text: string; warn: boolean }[] = []
  if (c) {
    if (c.weather !== 'none') {
      const what = [c.storm ? 'dông' : '', c.rain_mm ? `mưa ~${Math.round(c.rain_mm)} mm` : '', c.gust_kmh ? `gió giật ~${Math.round(c.gust_kmh)} km/h` : ''].filter(Boolean).join(', ')
      items.push({ icon: 'rain', text: `${c.weather === 'severe' ? 'Thời tiết rất xấu' : 'Mưa lớn hoặc dông'}${what ? ` (${what})` : ''}`, warn: true })
    } else items.push({ icon: 'cloud', text: c.rain_mm === null ? 'Chưa có số liệu thời tiết cho ngày này' : 'Dự báo không có mưa lớn', warn: false })
    for (const a of c.advisories) items.push({ icon: 'warn', text: `Thông báo ${ADVISORY[a.kind] ?? a.kind}: ${a.note || 'xem nguồn'} (${a.source})`, warn: true })
    if (c.crowd !== 'normal') items.push({ icon: 'users', text: `${c.crowd === 'peak' ? 'Rất đông' : 'Đông hơn thường'}: ${c.crowd_reasons.join(', ')}`, warn: true })
    if (c.day_type !== 'weekday') items.push({ icon: 'calendar', text: c.day_type === 'holiday' ? 'Ngày lễ' : 'Cuối tuần', warn: c.day_type === 'holiday' })
    if (c.closure_risk) items.push({ icon: 'warn', text: `Dịp ${c.closure_risk}: nhiều quán đóng cửa hoặc đổi giờ, gọi xác nhận trước`, warn: true })
    if (c.crowd !== 'normal') tips.slice(0, 2).forEach((t) => items.push({ icon: 'clock', text: t.text, warn: false }))
  }
  if (!c || (!c.advisories.length && c.crowd === 'normal' && !c.closure_risk)) items.push({ icon: 'info', text: 'Chưa có thông báo hay sự kiện ghi nhận cho ngày này (không có nghĩa là chắc chắn bình thường).', warn: false })
  return <ul className="tg-cond" aria-label="Điều kiện ngày">{items.map((x) => <li key={x.text} className={x.warn ? 'is-warn' : ''}><Icon name={x.icon} size={16} />{x.text}</li>)}</ul>
}

function DayBlock({ d, cond, tips, hot, setHot, slots, state, onEdit, busy, act, fitOf, rental }: { d: ItineraryDay; cond: DayConditions | undefined; tips: CrowdTip[]; hot: string | null; setHot: (v: string | null) => void; slots: NonNullable<View['slots']>; state: View['state']; onEdit: (id: string) => void; busy: boolean; act: (a: Action) => Promise<void>; fitOf: (id: string) => Fit; rental: 'pickup' | 'return' | 'both' | null }) {
  let n = 0
  let leg = 0
  let parts: { mode?: string; min: number }[] = []
  const rows: { it: ItineraryItem; leg: number; mode: string | null; n: number }[] = []
  for (const it of d.items) {
    if (it.kind === 'travel') { const min = toMin(it.end) - toMin(it.start); leg += min; parts.push({ mode: it.mode, min }); continue }
    rows.push({ it, leg, mode: legMode(parts), n: it.kind === 'visit' ? ++n : 0 })
    leg = 0
    parts = []
  }
  return (
    <div className="tg-day" key={d.day}>
      <div className="tg-day__top"><span className="tg-muted">{d.window[0]}–{d.window[1]}</span></div>
      {rental && <p className="tg-day__rental"><Icon name="bike" size={15} />{RENTAL_NOTE[rental]}</p>}
      <Conditions c={cond} tips={tips} />
      <ol className="tg-tl">
        {rows.map(({ it, leg: l, mode, n: k }, i) => {
          const dur = toMin(it.end) - toMin(it.start)
          if (it.kind !== 'visit' || !it.place_id) {
            const meal = it.kind === 'meal_free' ? (MEAL[it.name ?? ''] ?? BLOCK.meal_free) : null
            return (
              <li key={i} className="tg-tl__blk" style={{ ['--i' as string]: i }}>
                <time className="tg-mono">{it.start}</time>
                <div><Icon name={it.kind === 'meal_free' ? 'utensils' : it.kind === 'wait' ? 'clock' : 'moon'} size={16} />{meal || BLOCK[it.kind] || it.kind}<span className="tg-faint">{dur} phút · {it.kind === 'meal_free' && !it.options?.length ? 'Ăn ở khu gần đó, bạn tự chọn quán.' : BLOCK_NOTE[it.kind] ?? ''}</span></div>
                {it.options && it.options.length > 0 && (
                  <p className="tg-tl__meals">
                    <SlotPick title={`${meal}: ${it.options.length} quán gợi ý`} options={it.options} fitOf={fitOf} className="tg-pickbtn"><Icon name="utensils" size={14} /> Chọn quán · {it.options.length} gợi ý</SlotPick>
                  </p>
                )}
              </li>
            )
          }
          const p = info(it.place_id)
          return (
            <li key={i} className="tg-tl__stop" style={{ ['--i' as string]: i }} onMouseEnter={() => setHot(it.place_id!)} onMouseLeave={() => setHot(null)}>
              {l > 0 && <p className="tg-tl__leg"><Icon name={LEG_ICON[mode ?? ''] ?? 'bike'} size={15} />{LEG_WORD[mode ?? ''] ?? 'Đi'} ≈ {l} phút</p>}
              <time className="tg-mono">{it.start}</time>
              <div className={`tg-pstop ${hot === it.place_id ? 'is-hot' : ''}`}>
                <i className="tg-pstop__n" aria-hidden="true">{k}</i>
                <PlacePhoto id={it.place_id} name={it.name} className="tg-pstop__ph" />
                <div className="tg-pstop__txt"><Link to={placeHref(it.place_id)} className="tg-pstop__name">{it.name ?? p?.name}</Link><span className="tg-faint">{p?.area ? `${p.area} · ` : ''}ở lại {state.visit_overrides?.[it.place_id]?.duration_min != null || state.locked_visits?.[it.place_id]?.duration_min != null ? '' : '≈ '}<span className="tg-mono">{fmtMin(dur)}</span></span><button type="button" className="tg-link tg-visit-link" disabled={busy} onClick={() => onEdit(it.place_id!)}>Chỉnh giờ và thứ tự{state.locked.includes(it.place_id) ? ' · Đã khóa' : state.visit_overrides?.[it.place_id] ? ' · Giờ bạn chọn' : ''}</button></div>
              </div>
              {it.note && it.note.includes(' ') && <p className="tg-tl__warn"><Icon name="warn" size={14} />{it.note}</p>}
              {slots[it.place_id] && (
                <div className="tg-seg tg-seg--slot" role="group" aria-label={`Giờ ghé ${it.name ?? p?.name ?? ''}`}>
                  {slots[it.place_id].options.map((o) => <button key={o} type="button" aria-pressed={slots[it.place_id!].current === o} disabled={busy} onClick={() => slots[it.place_id!].current !== o && act({ type: 'set_slot', place_id: it.place_id!, slot: o })}>{SLOT[o]}</button>)}
                </div>
              )}
            </li>
          )
        })}
        {d.night && (
          <li className="tg-tl__blk is-night" style={{ ['--i' as string]: rows.length }}>
            <time className="tg-mono">{d.night.start}</time>
            <div><Icon name="moon" size={16} />Đêm {d.night.night}<span className="tg-faint">{d.night.start}–{d.night.end} · {d.night.empty ? d.night.text : 'Buổi tối tự do, mình gợi ý vài nơi gần chặng cuối ngày.'}</span></div>
            {d.night.options.length > 0 && (
              <p className="tg-tl__meals">
                <SlotPick title={`Đêm ${d.night.night}: ${d.night.options.length} nơi gợi ý`} options={d.night.options} fitOf={fitOf} className="tg-pickbtn"><Icon name="moon" size={14} /> Chọn nơi · {d.night.options.length} gợi ý</SlotPick>
              </p>
            )}
          </li>
        )}
        {n === 0 && <li className="tg-faint">Ngày này chưa có nơi nào. Thêm nơi ở bước Lựa chọn.</li>}
      </ol>
    </div>
  )
}

// The embedded map can only draw car directions; on a motorbike trip it says so, and the link opens the motorbike route.
function DayMap({ d, vehicle }: { d: ItineraryDay | undefined; vehicle: string | null }) {
  const stops = (d ? visits(d) : []).map((it) => info(it.place_id!)).filter((p): p is NonNullable<typeof p> => !!p)
  const bike = vehicle === 'motorbike'
  return (
    <div className="tg-map">
      {stops.length ? <iframe className="tg-map__frame" title={`Lộ trình ngày ${d?.day}`} src={mapsRouteEmbed(stops)} loading="lazy" referrerPolicy="no-referrer-when-downgrade" /> : <div className="tg-map__none tg-faint">Chưa có điểm nào để vẽ đường.</div>}
      <div className="tg-map__foot"><span><Icon name="route" size={16} /> {stops.length} điểm dừng</span>{stops.length > 1 && <a href={routeLink(stops, vehicle)} target="_blank" rel="noreferrer" className="tg-link">{bike ? 'Xem đường xe máy trên Google Maps' : 'Mở trên Google Maps'} <Icon name="external" size={14} /></a>}</div>
      <p className="tg-map__note tg-faint">{bike ? 'Bản đồ nhúng chỉ vẽ được đường ô tô nên số phút trên bản đồ là của ô tô. Giờ trong lịch đã tính cho xe máy và là ước tính.' : 'Bản đồ Google Maps. Đường đi và giờ giấc trong lịch là ước tính.'}</p>
    </div>
  )
}

// Trip-wide notes, grouped by what the reader has to do: check before going, or just how rough the plan is. Nothing is cut off.
function TripNotes({ warnings }: { warnings: Warning[] }) {
  const { need, rough } = groupNotes(warnings)
  const item = (n: { code: string; lead: string | null; text: string }, i: number, tone: 'need' | 'rough') => (
    <li key={`${n.code}-${i}`}><Icon name={tone === 'need' ? NOTE_ICON[n.code] ?? 'warn' : 'info'} size={16} /><p>{n.lead && <b>{n.lead}{n.lead.endsWith(')') ? '. ' : ': '}</b>}{n.text}</p></li>
  )
  return (
    <section className="tg-sidecard tg-nl" aria-labelledby="tg-nt-h">
      <h2 id="tg-nt-h"><Icon name="info" size={18} /> Lưu ý cả chuyến</h2>
      {need.length === 0 && rough.length === 0 && <p className="tg-faint">Chưa có lưu ý nào.</p>}
      {need.length > 0 && <div className="tg-nl__need"><h3>Cần để ý trước khi đi · {need.length}</h3><ul>{need.map((n, i) => item(n, i, 'need'))}</ul></div>}
      {rough.length > 0 && <details className="tg-nl__rough" open={need.length === 0}><summary>Chỉ là ước tính · {rough.length}</summary><ul>{rough.map((n, i) => item(n, i, 'rough'))}</ul></details>}
    </section>
  )
}

function SideLodging() {
  const { view, lodgingProgress, act, busy } = usePlanning()
  if (!view) return null
  const status = view.lodging.status
  const candidates = status === 'pending' && lodgingProgress ? lodgingProgress.candidates : view.lodging.candidates
  const chosen = view.state.lodging_id
  return (
    <section className="tg-sidecard" aria-labelledby="tg-lod-h">
      <h2 id="tg-lod-h"><Icon name="bed" size={18} /> Chỗ nghỉ đêm</h2>
      {status === 'pending' && <p className="tg-faint">Đang tra giá chỗ ở quanh lịch trình… có thể mất ~10 giây.</p>}
      {status === 'unavailable' && <p className="tg-faint">Chưa tra được chỗ ở, lịch dùng điểm xuất phát làm neo.</p>}
      {status === 'booked' && view.state.lodging_point && <p><b>{String(view.state.lodging_point.text ?? '')}</b><br /><small className="tg-faint">Chỗ bạn đã đặt, mọi ngày bắt đầu và kết thúc ở đây.</small></p>}
      {candidates.length > 0 && (
        <ul>
          {candidates.slice(0, 5).map((c) => (
            <li key={c.id}><label className={`tg-radio ${chosen === c.id ? 'is-on' : ''}`}>
              <input type="radio" name="lodging" checked={chosen === c.id} disabled={busy} onChange={() => act({ type: 'pick_lodging', id: c.id })} />
              <span><b>{c.name}</b><small className="tg-faint">{c.price_vnd ? `${fmtVnd(c.price_vnd)}/đêm` : 'Chưa có giá'}</small></span>
            </label></li>
          ))}
        </ul>
      )}
      <div className="tg-sidecard__lookup">
        <PlaceInput<LodgingHit> label="Chỗ bạn ở" placeholder="Gõ tên khách sạn, homestay hoặc địa chỉ" icon="bed" disabled={busy} fetcher={lodgingSuggest}
          row={lodgingRow}
          onPick={(h) => act(h.id && candidates.some((c) => c.id === h.id) ? { type: 'pick_lodging', id: h.id } : lodgingAct(h))} />
      </div>
      <p className="tg-faint tg-sidecard__mini">Đổi chỗ nghỉ thì giờ di chuyển được tính lại. Giá là của Google Maps, chưa xác minh.</p>
    </section>
  )
}

// Backups of the day on screen (all days on "Cả chuyến"): a stand-in for a place that may fail (rain, hours) and what to drop first when late.
export function BackupCard({ b, day, busy, onSwap }: { b: Backups | undefined; day: number | 'all'; busy: boolean; onSwap: (place: string, w: string) => void }) {
  const items = b?.places.filter((x) => day === 'all' || x.day === day) ?? []
  const late = b?.on_delay.filter((x) => day === 'all' || x.day === day) ?? []
  return (
    <section className="tg-sidecard tg-backups" aria-labelledby="tg-bk-h">
      <h2 id="tg-bk-h"><Icon name="shield" size={18} /> Phương án dự phòng{day === 'all' ? '' : ` · Ngày ${day}`}</h2>
      {items.length === 0 && late.length === 0 && <p className="tg-faint">{day === 'all' ? 'Chưa có nơi nào cần dự phòng.' : 'Ngày này chưa có nơi nào cần dự phòng.'}</p>}
      {items.slice(0, 3).map((x) => (
        <div key={x.place_id} className="tg-backup">
          <b>{day === 'all' && <em className="tg-tag">Ngày {x.day}</em>} {x.text ? `Nếu ${x.text.toLowerCase()}` : x.name}</b>
          <span>{x.name}{x.alternatives.length ? ' → ' : ''}{x.alternatives.length ? '' : ` · ${x.none_text ?? 'Không có phương án thay.'}`}</span>
          {x.alternatives.slice(0, 2).map((a) => <button key={a.id} type="button" className="tg-btn tg-btn--soft tg-btn--sm" disabled={busy} onClick={() => onSwap(x.place_id, a.id)}>Thay bằng {a.name}{a.minutes_rough ? ` (≈${a.minutes_rough}′)` : ''}</button>)}
        </div>
      ))}
      {late.map((l) => <div key={l.day} className="tg-backup"><b>{day === 'all' && <em className="tg-tag">Ngày {l.day}</em>} Bị trễ</b><span>Bỏ {l.name} trước, giữ phần còn lại</span></div>)}
      <p className="tg-faint tg-sidecard__mini">Chỉ thay khi bạn bấm chọn.</p>
    </section>
  )
}
