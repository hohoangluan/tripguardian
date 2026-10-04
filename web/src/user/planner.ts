// Client-side trip estimate, now used only by the admin debug view (web/src/admin/screens/Sessions.tsx), which
// previews a user's trip from a local snapshot with no live Planning session to query. The real user-facing
// schedule is web/src/user/screens/Itinerary.tsx, backed by python -m planning serve (docs/PLANNING.md).
// Every number here is still an estimate and is labelled as one in the admin UI.
import { featureLabel } from '../data/labels'
import { CENTER, DAYS, fmtDuration, fmtTime, has, openWindows, placeById, travelMin, visible, visitRange } from '../data/store'
import type { Place } from '../data/types'
import type { Action, TripState } from './trip'

export const anchorOf = (t: TripState) => {
  const p = t.lodging ? placeById(t.lodging) : undefined
  return p ? { lat: p.lat, lng: p.lng, name: p.name } : { ...CENTER, name: 'trung tâm Đà Lạt' }
}

const toMin = (hhmm: string) => {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + (m || 0)
}

// ---------- feasibility + schedule ----------

export interface Stop {
  place: Place
  arrive: number
  leave: number
  travelIn: number
  wait: number
  flags: string[]
}

export interface Day {
  index: number
  date: Date
  start: number
  end: number
  stops: Stop[]
  finish: number
  travel: number
  slack: number
  robustness: 'Vững' | 'Khả thi' | 'Mong manh'
  robustReason: string
}

export interface Fix {
  label: string
  effect: string
  action: Action
}

export interface Conflict {
  id: string
  physical: boolean
  placeId?: string
  title: string
  rule: string
  fixes: Fix[]
}

export interface Plan {
  status: 'feasible' | 'partial' | 'infeasible'
  days: Day[]
  conflicts: Conflict[]
  totals: { places: number; visit: number; travel: number; available: number; needed: number }
  reasons: string[]
}

const paceVisit = (r: [number, number], pace: TripState['pace']) =>
  pace === 'slow' ? r[1] : pace === 'packed' ? r[0] : Math.round((r[0] + r[1]) / 2)

function nearestOrder(points: Place[], from: { lat: number; lng: number }) {
  const rest = [...points]
  const out: Place[] = []
  let cur = from
  while (rest.length) {
    let bi = 0
    let bd = Infinity
    rest.forEach((p, i) => {
      const d = (p.lat - cur.lat) ** 2 + (p.lng - cur.lng) ** 2
      if (d < bd) {
        bd = d
        bi = i
      }
    })
    cur = rest[bi]
    out.push(rest.splice(bi, 1)[0])
  }
  return out
}

export function dayWindows(t: TripState) {
  return Array.from({ length: t.days }, (_, i) => {
    const date = new Date(t.startDate + 'T00:00:00')
    date.setDate(date.getDate() + i)
    const start = i === 0 ? Math.max(toMin(t.arriveAt), 7 * 60) : 7 * 60 + 30
    const end = i === t.days - 1 ? toMin(t.leaveAt) : toMin(t.rules.dayEnd)
    return { date, start, end }
  })
}

export function plan(t: TripState): Plan {
  const v = t.vehicle ?? 'motorbike'
  const anchor = anchorOf(t)
  const places = t.selected.map((id) => placeById(id)).filter((p): p is Place => !!p)
  const windows = dayWindows(t)
  const available = windows.reduce((a, w) => a + Math.max(0, w.end - w.start), 0)

  // Day assignment: explicit moves first, then nearest-neighbour fill by time budget.
  const buckets: Place[][] = windows.map(() => [])
  const free: Place[] = []
  for (const p of places) {
    const d = t.moved[p.id]
    if (d !== undefined && d < windows.length) buckets[d].push(p)
    else free.push(p)
  }
  const ordered = nearestOrder(free, anchor)
  // Spread evenly: each day takes about its share of the total, never more than it can hold.
  const needOf = (p: Place) => paceVisit(visitRange(p), t.pace) + 30
  const capacity = windows.map((w) => Math.max(0, w.end - w.start))
  const share = (ordered.reduce((a, p) => a + needOf(p), 0) + buckets.flat().reduce((a, p) => a + needOf(p), 0)) / windows.length
  const used = buckets.map((b) => b.reduce((a, p) => a + needOf(p), 0))
  let di = 0
  for (const p of ordered) {
    const need = needOf(p)
    while (di < windows.length - 1 && (used[di] + need > capacity[di] || (used[di] > 0 && used[di] + need > share * 1.15))) di++
    buckets[di].push(p)
    used[di] += need
  }

  const conflicts: Conflict[] = []
  const days: Day[] = windows.map((w, i) => {
    const order = nearestOrder(buckets[i], anchor)
    const stops: Stop[] = []
    let clock = w.start
    let cur: { lat: number; lng: number } = anchor
    let travel = 0
    const dayKey = DAYS[w.date.getDay()]
    for (const p of order) {
      const leg = travelMin(cur, p, v)
      travel += leg
      let arrive = clock + leg
      let wait = 0
      const flags: string[] = []
      const win = openWindows(p, dayKey)
      const stay = paceVisit(visitRange(p), t.pace)
      if (win === null) flags.push('Giờ mở cửa chưa có thông tin, kiểm tra trước khi đi')
      else if (win.length === 0) {
        flags.push('Đóng cửa ngày này theo Google')
        conflicts.push(closedConflict(p, i, windows))
      } else {
        const open = win.find(([a, b]) => arrive < b - 20 && a <= arrive + 120)
        if (!open) {
          const later = win.find(([a]) => a > arrive)
          flags.push(later ? `Mở lúc ${fmtTime(later[0])}` : `Tới lúc ${fmtTime(arrive)}, đã đóng cửa`)
          if (!later) conflicts.push(closedConflict(p, i, windows, arrive, win))
        } else if (open[0] > arrive) {
          wait = open[0] - arrive
          arrive = open[0]
          if (wait > 15) flags.push(`Chờ ${wait} phút tới giờ mở cửa`)
        }
        if (open && arrive + stay > open[1]) flags.push(`Đóng cửa lúc ${fmtTime(open[1])}, chỉ còn ${Math.max(0, open[1] - arrive)} phút`)
      }
      const uncertain = visible(p).filter((s) => s.status === 'UNCERTAIN' && ['booking_needed', 'entry_fee'].includes(s.id))
      for (const s of uncertain) flags.push(`${featureLabel(s.id)} chưa xác nhận`)
      if (has(p, 'weather_exposed')) flags.push('Ngoài trời, phụ thuộc thời tiết')
      if (t.rules.maxLegMin && !t.relaxed.includes('maxLeg') && leg > t.rules.maxLegMin) {
        conflicts.push({
          id: `leg-${p.id}`,
          physical: false,
          placeId: p.id,
          title: `${p.name}: chặng đi ${leg} phút`,
          rule: `Bạn đặt mỗi chặng tối đa ${t.rules.maxLegMin} phút.`,
          fixes: [
            { label: `Nới giới hạn lên ${Math.ceil(leg / 5) * 5} phút`, effect: 'Giữ nguyên lịch, chặng này dài hơn bạn muốn', action: { type: 'relax', key: 'maxLeg' } },
            { label: `Bỏ ${p.name}`, effect: `Tiết kiệm khoảng ${leg + stay} phút`, action: { type: 'unselect', id: p.id } },
          ],
        })
      }
      if (t.rules.avoidSteep && !t.relaxed.includes('avoidSteep') && has(p, 'steep_or_stairs')) {
        conflicts.push({
          id: `steep-${p.id}`,
          physical: false,
          placeId: p.id,
          title: `${p.name} phải leo dốc hoặc nhiều bậc`,
          rule: 'Bạn chọn tránh đường dốc.',
          fixes: [
            { label: 'Vẫn giữ, nới quy tắc này', effect: 'Chấp nhận leo dốc ở nơi này', action: { type: 'relax', key: 'avoidSteep' } },
            { label: `Bỏ ${p.name}`, effect: 'Giữ đúng quy tắc', action: { type: 'unselect', id: p.id } },
          ],
        })
      }
      stops.push({ place: p, arrive, leave: arrive + stay, travelIn: leg, wait, flags })
      clock = arrive + stay
      cur = p
    }
    const back = order.length ? travelMin(cur, anchor, v) : 0
    travel += back
    const finish = clock + back
    const slack = w.end - finish
    const robustness = slack >= 60 ? 'Vững' : slack >= 15 ? 'Khả thi' : 'Mong manh'
    const exposed = stops.filter((s) => has(s.place, 'weather_exposed')).length
    const robustReason =
      slack < 0
        ? `Vượt ${fmtDuration(-slack)} so với giờ kết thúc ngày`
        : robustness === 'Vững'
          ? `Còn dư ${fmtDuration(slack)}${exposed ? `, nhưng ${exposed} nơi ngoài trời` : ''}`
          : `Chỉ dư ${fmtDuration(slack)}, trễ một chút là phải bỏ bớt`
    return { index: i, date: w.date, start: w.start, end: w.end, stops, finish, travel, slack, robustness, robustReason }
  })

  for (const d of days) {
    if (d.slack >= 0 || !d.stops.length) continue
    const removable = d.stops.filter((s) => !t.locked.includes(s.place.id) && !t.mustVisit.includes(s.place.id))
    const target = removable.sort((a, b) => b.leave - b.arrive - (a.leave - a.arrive))[0]
    const other = days.filter((x) => x.index !== d.index).sort((a, b) => b.slack - a.slack)[0]
    const fixes: Fix[] = []
    if (target) {
      const save = target.leave - target.arrive + target.travelIn
      fixes.push({
        label: `Bỏ ${target.place.name}`,
        effect: `Tiết kiệm khoảng ${fmtDuration(save)}, ngày ${d.index + 1} ${save >= -d.slack ? 'ổn' : 'vẫn quá tải'}`,
        action: { type: 'unselect', id: target.place.id },
      })
      if (other && other.slack > target.leave - target.arrive + 30) {
        fixes.push({
          label: `Dời ${target.place.name} sang ngày ${other.index + 1}`,
          effect: `Ngày ${other.index + 1} còn dư ${fmtDuration(other.slack)}`,
          action: { type: 'move', id: target.place.id, day: other.index },
        })
      }
    }
    if (d.index === days.length - 1)
      fixes.push({
        label: 'Rời Đà Lạt muộn hơn 2 giờ',
        effect: 'Nới giờ rời đi do bạn đặt',
        action: { type: 'set', patch: { leaveAt: fmtTime(toMin(t.leaveAt) + 120) } },
      })
    conflicts.push({
      id: `overload-${d.index}`,
      physical: true,
      title: `Ngày ${d.index + 1} quá tải ${fmtDuration(-d.slack)}`,
      rule: `Cần tới ${fmtTime(d.finish)}, nhưng ngày này kết thúc lúc ${fmtTime(d.end)}.`,
      fixes,
    })
  }

  const visit = days.reduce((a, d) => a + d.stops.reduce((b, s) => b + s.leave - s.arrive, 0), 0)
  const travelSum = days.reduce((a, d) => a + d.travel, 0)
  const needed = visit + travelSum
  const reasons: string[] = []
  let status: Plan['status'] = conflicts.length ? 'partial' : 'feasible'
  if (needed > available * 1.35) {
    status = 'infeasible'
    reasons.push(`Cần khoảng ${fmtDuration(needed)}, chuyến đi chỉ có ${fmtDuration(available)}`)
  }
  return { status, days, conflicts, totals: { places: places.length, visit, travel: travelSum, available, needed }, reasons }
}


function closedConflict(p: Place, day: number, windows: ReturnType<typeof dayWindows>, arrive?: number, win?: [number, number][]): Conflict {
  const alt = windows.findIndex((w, i) => i !== day && (openWindows(p, DAYS[w.date.getDay()]) ?? []).length > 0)
  const fixes: Fix[] = []
  if (alt >= 0) fixes.push({ label: `Dời sang ngày ${alt + 1}`, effect: 'Ngày đó nơi này mở cửa', action: { type: 'move', id: p.id, day: alt } })
  fixes.push({ label: `Bỏ ${p.name}`, effect: 'Giải phóng thời gian cho các nơi khác', action: { type: 'unselect', id: p.id } })
  return {
    id: `closed-${p.id}-${day}`,
    physical: true,
    placeId: p.id,
    title: arrive !== undefined ? `${p.name}: tới lúc ${fmtTime(arrive)}` : `${p.name} đóng cửa ngày ${day + 1}`,
    rule:
      win && win.length
        ? `Theo Google, nơi này mở ${win.map(([a, b]) => `${fmtTime(a)}–${fmtTime(b)}`).join(', ')}.`
        : 'Theo Google, nơi này nghỉ ngày đó.',
    fixes,
  }
}

// Rain plan for exposed stops: a sheltered or indoor pick nearby from the shortlist.
export function rainBackup(stop: Stop, pool: Place[]) {
  if (!has(stop.place, 'weather_exposed')) return null
  const alt = pool
    .filter((p) => p.id !== stop.place.id && (has(p, 'weather_exposed', 'sheltered') || has(p, 'setting', 'indoor')))
    .sort((a, b) => travelMin(stop.place, a, 'motorbike') - travelMin(stop.place, b, 'motorbike'))[0]
  return alt ?? null
}
