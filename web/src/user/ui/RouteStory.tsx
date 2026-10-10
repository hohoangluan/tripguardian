import { useMemo, useState } from 'react'
import { fmtClock, toMin } from '../lib'
import type { ItineraryDay } from '../planning/types'
import { LEG_ICON, LEG_WORD, legMode, placeAt, type MealOption } from '../planning/view'
import { Link, placeHref, PlacePhoto } from './common'
import { Icon } from './icons'
import { SlotPick } from './SlotPick'

// visit: a place of the plan. meal / night: a timed block the plan only suggests for (never added to the plan).
interface Node { kind: 'home' | 'visit' | 'meal' | 'night'; id: string | null; day: number; start: number; end: number; travel: number; first: boolean; label: string; mode: string | null; num: number; options: MealOption[]; text: string | null }
type Fit = { stars: number; level: string } | null | undefined

const MEAL: Record<string, string> = { lunch: 'Ăn trưa', dinner: 'Ăn tối' }
// What a drag carries: where it came from, so a day tab or another card knows what was dropped on it.
export const DRAG_TYPE = 'application/x-tg-stop'
export const dragged = (e: React.DragEvent): { day: number; id: string } | null => {
  try { const v = JSON.parse(e.dataTransfer.getData(DRAG_TYPE)); return typeof v?.id === 'string' && typeof v?.day === 'number' ? v : null } catch { return null }
}

// Infographic view of a day (or the whole trip): photo cards pinned along a dashed route, alternating above / below.
// Every stop shows its estimated clock time. A stop is moved by dragging it onto another stop (before / after it), by the
// two arrows under it (Alt + ← / → on the keyboard), or onto a day tab (Plan.tsx) to change its day; the plan decides
// whether the move is allowed and the card stays where it was when it is not.
export function RouteStory({ days, day, home, homeSet, hot, setHot, fitOf, busy, pinned, onEdit, onReorder, onMove }: {
  days: ItineraryDay[]; day: number | 'all'; home: string; homeSet: boolean; hot: string | null; setHot: (v: string | null) => void; fitOf: (id: string) => Fit
  busy: boolean; pinned: Record<string, 'locked' | 'chosen'>; onEdit: (id: string) => void; onReorder: (day: number, order: string[]) => void; onMove: (place: string, day: number) => void
}) {
  const [drag, setDrag] = useState<{ day: number; id: string } | null>(null)
  const [over, setOver] = useState<{ id: string; side: 'before' | 'after' } | null>(null)
  const nodes = useMemo<Node[]>(() => {
    const shown = day === 'all' ? days : [days[day]].filter(Boolean)
    const out: Node[] = [{ kind: 'home', id: null, day: shown[0]?.day ?? 1, start: shown[0] ? toMin(shown[0].window[0]) : 0, end: 0, travel: 0, first: false, label: home, mode: null, num: 0, options: [], text: null }]
    let num = 0
    shown.forEach((d) => {
      let leg = 0
      let parts: { mode?: string; min: number }[] = []
      let first = true
      d.items.forEach((it) => {
        if (it.kind === 'travel') { const min = toMin(it.end) - toMin(it.start); leg += min; parts.push({ mode: it.mode, min }) }
        if (it.kind === 'visit' && it.place_id) {
          out.push({ kind: 'visit', id: it.place_id, day: d.day, start: toMin(it.start), end: toMin(it.end), travel: leg, first, label: it.name ?? '', mode: legMode(parts), num: ++num, options: [], text: null })
          leg = 0
          parts = []
          first = false
        }
        if (it.kind === 'meal_free') out.push({ kind: 'meal', id: null, day: d.day, start: toMin(it.start), end: toMin(it.end), travel: 0, first: false, label: MEAL[it.name ?? ''] ?? 'Ăn tự chọn', mode: null, num: 0, options: it.options ?? [], text: null })
      })
      if (d.night) out.push({ kind: 'night', id: null, day: d.day, start: toMin(d.night.start), end: toMin(d.night.end), travel: 0, first: false, label: `Đêm ${d.night.night}`, mode: null, num: 0, options: d.night.options, text: d.night.text })
    })
    return out
  }, [days, day, home])
  const n = nodes.length
  const W = 1000, H = 400
  const pts = nodes.map((_, i) => ({ x: n === 1 ? W / 2 : 70 + (i * (W - 140)) / (n - 1), y: H / 2 + (i % 2 === 0 ? 22 : -22) + Math.sin(i * 1.3) * 18 }))
  const d = pts.map((p, i) => {
    if (i === 0) return `M${p.x} ${p.y}`
    const a = pts[i - 1]
    const mx = (a.x + p.x) / 2
    return `C${mx} ${a.y} ${mx} ${p.y} ${p.x} ${p.y}`
  }).join(' ')
  const cur = day === 'all' ? null : days[day]
  const title = cur ? `Ngày ${cur.day}${cur.weekday ? ` · ${cur.weekday}` : ''}` : 'Cả chuyến'
  const orderOf = (dayNo: number) => (days.find((x) => x.day === dayNo)?.items ?? []).filter((it) => it.kind === 'visit' && it.place_id).map((it) => it.place_id!)

  // Move `id` next to `target`: inside its own day it is a new order, onto a stop of another day it is a change of day.
  const drop = (from: { day: number; id: string }, nd: Node, side: 'before' | 'after') => {
    setDrag(null)
    setOver(null)
    if (!nd.id) return
    if (nd.day !== from.day) { onMove(from.id, nd.day); return }
    const next = placeAt(orderOf(from.day), from.id, nd.id, side)
    if (next) onReorder(from.day, next)
  }
  const step = (nd: Node, by: -1 | 1) => {
    const order = orderOf(nd.day)
    const at = order.indexOf(nd.id!)
    const next = order[at + by]
    const moved = next ? placeAt(order, nd.id!, next, by < 0 ? 'before' : 'after') : null
    if (moved) onReorder(nd.day, moved)
  }
  return (
    <div className="tg-rs" style={{ minWidth: Math.max(860, n * 190) }}>
      <h3 className="tg-rs__title">{title}</h3>
      <div className="tg-rs__stage" role="group" aria-label={`Hành trình ${title}: ${nodes.map((x) => x.label).join(' → ')}.`}>
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
          <g className="tg-rs__blobs">
            <path d="M40 90c40-50 120-60 150-20s0 90-50 100-130-30-100-80Z" /><path d="M560 300c50-40 120-40 160 0s10 80-50 80-150-10-110-80Z" /><path d="M820 60c40-30 100-20 120 20s-20 80-80 80-80-70-40-100Z" />
          </g>
          <path key={d} className="tg-rs__route" d={d} pathLength={1} vectorEffect="non-scaling-stroke" />
        </svg>
        {nodes.map((nd, i) => {
          const mid = i > 0 ? { x: (pts[i - 1].x + pts[i].x) / 2, y: (pts[i - 1].y + pts[i].y) / 2 } : null
          const on = hot === nd.id && nd.id
          const slot = nd.kind === 'meal' || nd.kind === 'night'
          const pick = slot && nd.options.length > 0
          const pin = nd.id ? pinned[nd.id] : undefined
          const movable = nd.kind === 'visit' && !!nd.id && !busy && pin !== 'locked'
          const sameDay = nodes.filter((x) => x.kind === 'visit' && x.day === nd.day)
          const at = sameDay.indexOf(nd)
          const cls = [i % 2 === 1 ? 'is-above' : 'is-below', nd.kind === 'home' ? 'is-home' : '', on ? 'is-hot' : '', drag?.id === nd.id && nd.id ? 'is-dragging' : '', over?.id === nd.id && nd.id && drag && drag.id !== nd.id ? `is-drop-${over.side}` : ''].filter(Boolean).join(' ')
          return (
            <div key={`${nd.id}-${i}`}>
              {mid && nd.travel > 0 && (homeSet || !nd.first) && <span className="tg-rs__leg" style={{ left: `${(mid.x / W) * 100}%`, top: `${(mid.y / H) * 100}%` }}><Icon name={LEG_ICON[nd.mode ?? ''] ?? 'bike'} size={13} /><span className="tg-sr">{LEG_WORD[nd.mode ?? ''] ?? 'Đi'} </span>≈{nd.travel}′</span>}
              <span className={`tg-rs__dot ${nd.kind === 'home' ? 'is-home' : ''} ${slot ? 'is-slot' : ''} ${pick ? 'tg-pulse-dot' : ''} ${on ? 'is-hot' : ''}`} style={{ left: `${(pts[i].x / W) * 100}%`, top: `${(pts[i].y / H) * 100}%` }}>{nd.kind === 'home' ? <Icon name="bed" size={14} /> : slot ? <Icon name={nd.kind === 'meal' ? 'utensils' : 'moon'} size={13} /> : nd.num}</span>
              <div
                className={`tg-rs__card ${cls}`} style={{ left: `${(pts[i].x / W) * 100}%`, top: `${(pts[i].y / H) * 100}%`, ['--i' as string]: i }}
                onMouseEnter={() => nd.id && setHot(nd.id)} onMouseLeave={() => setHot(null)}
                draggable={movable}
                onDragStart={(e) => { if (!nd.id) return; const from = { day: nd.day, id: nd.id }; e.dataTransfer.setData(DRAG_TYPE, JSON.stringify(from)); e.dataTransfer.effectAllowed = 'move'; setDrag(from) }}
                onDragEnd={() => { setDrag(null); setOver(null) }}
                onDragOver={(e) => { if (!drag || !nd.id || nd.kind !== 'visit') return; e.preventDefault(); const r = e.currentTarget.getBoundingClientRect(); setOver({ id: nd.id, side: e.clientX < r.left + r.width / 2 ? 'before' : 'after' }) }}
                onDrop={(e) => { const from = dragged(e); if (!from || !nd.id || nd.kind !== 'visit') return; e.preventDefault(); const r = e.currentTarget.getBoundingClientRect(); drop(from, nd, e.clientX < r.left + r.width / 2 ? 'before' : 'after') }}
                onKeyDown={(e) => { if (movable && e.altKey && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) { e.preventDefault(); step(nd, e.key === 'ArrowLeft' ? -1 : 1) } }}
              >
                {nd.kind === 'visit' && nd.id ? (
                  <>
                    <Link to={placeHref(nd.id)} className="tg-rs__frame" draggable={false}>
                      <PlacePhoto id={nd.id} name={nd.label} className="tg-rs__ph" />
                      <b>{pin === 'locked' && <Icon name="lock" size={13} />} {nd.label}</b>
                      <span className="tg-mono tg-rs__time">{fmtClock(nd.start)}–{fmtClock(nd.end)}</span>
                      <span>{nd.end - nd.start} phút{pin === 'chosen' ? ' · giờ bạn chọn' : ''}</span>
                      {day === 'all' && <em className="tg-tag">Ngày {nd.day}</em>}
                    </Link>
                    <div className="tg-rs__tools" role="group" aria-label={`Chỉnh ${nd.label}`}>
                      {movable && <button type="button" className="tg-icon-btn" disabled={at <= 0} onClick={() => step(nd, -1)} aria-label={`Đưa ${nd.label} đi trước một điểm`}><Icon name="arrow" size={15} style={{ rotate: '180deg' }} /></button>}
                      <button type="button" className="tg-icon-btn" disabled={busy} onClick={() => onEdit(nd.id!)} aria-label={`Chỉnh giờ ${nd.label}`}><Icon name="clock" size={15} /></button>
                      {movable && <button type="button" className="tg-icon-btn" disabled={at < 0 || at >= sameDay.length - 1} onClick={() => step(nd, 1)} aria-label={`Đưa ${nd.label} đi sau một điểm`}><Icon name="arrow" size={15} /></button>}
                    </div>
                  </>
                ) : pick ? (
                  <SlotPick title={`${nd.label}: ${nd.options.length} gợi ý`} options={nd.options} fitOf={fitOf} className="tg-rs__frame is-slot">
                    <Icon name={nd.kind === 'meal' ? 'utensils' : 'moon'} size={22} />
                    <b>{nd.label}</b>
                    <span className="tg-mono tg-rs__time">{fmtClock(nd.start)}–{fmtClock(nd.end)}</span>
                    <span>bấm để chọn · {nd.options.length} gợi ý</span>
                    {day === 'all' && <em className="tg-tag">Ngày {nd.day}</em>}
                  </SlotPick>
                ) : slot ? (
                  <div className="tg-rs__frame is-slot is-quiet">
                    <Icon name={nd.kind === 'meal' ? 'utensils' : 'moon'} size={22} />
                    <b>{nd.label}</b>
                    <span className="tg-mono tg-rs__time">{fmtClock(nd.start)}–{fmtClock(nd.end)}</span>
                    <span>{nd.text ?? 'Bạn tự chọn quán ở khu gần đó.'}</span>
                  </div>
                ) : (
                  <div className={`tg-rs__frame is-home ${homeSet ? '' : 'is-unset'}`}><Icon name="bed" size={22} /><b>{homeSet ? nd.label : 'Chọn chỗ ở'}</b><span>{homeSet ? 'Mỗi ngày bắt đầu và kết thúc ở đây' : 'Chưa có chỗ ở nên chưa tính đường từ đây'}</span></div>
                )}
              </div>
            </div>
          )
        })}
      </div>
      <p className="tg-faint tg-rs__note">Sơ đồ minh họa thứ tự đi, không đúng tỉ lệ bản đồ. Giờ giấc và đường đi là ước tính, mình tính lại sau mỗi lần bạn đổi.</p>
    </div>
  )
}
