// Client-side estimates for the prototype: ranking, feasibility, schedule.
// Every number here is an estimate and is labelled as one in the UI.
import { featureLabel, isNegative, signalPhrase, TIME_VI } from '../data/labels'
import {
  CENTER,
  confidenceOf,
  DAYS,
  fmtDuration,
  fmtTime,
  has,
  openWindows,
  placeById,
  sectionOf,
  signal,
  travelMin,
  visible,
  visitRange,
  type Confidence,
  type Section,
} from '../data/store'
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

// ---------- shortlist ----------

// One line on a card; `sid` points at the signal that backs it, so it opens its evidence.
export interface Claim {
  text: string
  sid?: string
}

export interface Candidate {
  place: Place
  section: Section
  score: number
  why: Claim[]
  tradeoffs: Claim[]
  visit: [number, number]
  confidence: { level: Confidence; reason: string }
  fromAnchor: number
}

export interface Shortlist {
  bySection: Record<Section, Candidate[]>
  extra: Record<Section, Candidate[]> // inventory only: no experience evidence yet
  excludedByRule: { rule: string; count: number }[]
}

const SECTIONS: Section[] = ['sight', 'nature', 'food', 'shop']

export function evaluate(p: Place, t: TripState): Candidate | null {
  const section = sectionOf(p)
  if (!section) return null
  const anchor = anchorOf(t)
  const fromAnchor = travelMin(anchor, p, t.vehicle ?? 'motorbike')
  const why: Claim[] = []
  const tradeoffs: Claim[] = []
  let score = Math.log10((p.voices ?? 5) + 10)

  if (t.mustVisit.includes(p.id)) {
    score += 100
    why.push({ text: 'Nơi bạn nhất định phải đến' })
  }
  for (const [id, pref] of Object.entries(t.prefs)) {
    const s = signal(p, id)
    if (!s) continue
    const positive = !isNegative(id, s.value) && s.value !== 'absent'
    const weight = s.agreement * Math.min(1, s.n / 5) * (s.status === 'VERIFIED' ? 1 : 0.6)
    if (pref.weight === 'love' && positive) {
      score += 3 * weight
      why.push({ text: signalPhrase(id, s.value) + (s.status === 'UNCERTAIN' ? ' (chưa chắc)' : ''), sid: id })
    }
    if (pref.weight === 'avoid' && s.value !== 'absent' && s.value !== 'no') {
      score -= 2.5 * weight
      tradeoffs.push({ text: `Có ${featureLabel(id).toLowerCase()}, điều bạn muốn tránh`, sid: id })
    }
  }
  if (fromAnchor <= 12) why.push({ text: `Gần ${anchor.name}, ≈${fromAnchor} phút đi` })
  if (fromAnchor >= 25) {
    score -= 0.8
    tradeoffs.push({ text: `Thêm khoảng ${fromAnchor} phút đi từ ${anchor.name}, ước tính` })
  }
  for (const s of visible(p)) {
    if (!isNegative(s.id, s.value) || s.n < 2) continue
    if (s.id === 'crowd') {
      const ctx = Object.entries(s.byContext).find(([, d]) => (d.high ?? 0) > 0)
      const when = ctx ? ' ' + (TIME_VI[ctx[0].split('=')[1]] ?? '') : ''
      tradeoffs.push({ text: `Đông${when}, theo ${s.n} người`, sid: s.id })
    } else if (s.id !== 'kids' && s.id !== 'elderly') {
      tradeoffs.push({ text: `${signalPhrase(s.id, s.value)}, theo ${s.n} người`, sid: s.id })
    }
    score -= 0.4
  }
  if (t.who.includes('kids') && has(p, 'kids', 'unsuitable')) {
    score -= 3
    tradeoffs.push({ text: 'Có người nói không hợp trẻ em', sid: 'kids' })
  }
  if (t.who.includes('parents') && (has(p, 'steep_or_stairs') || has(p, 'long_walk'))) {
    score -= 1.5
    tradeoffs.push({ text: 'Phải leo dốc hoặc đi bộ xa, cân nhắc với bố mẹ', sid: has(p, 'steep_or_stairs') ? 'steep_or_stairs' : 'long_walk' })
  }
  if (!openWindows(p, 'sat') && !openWindows(p, 'mon')) tradeoffs.push({ text: 'Giờ mở cửa chưa có thông tin' })
  if (p.kind === 'experience' && why.length === 0) {
    const best = visible(p)
      .filter((s) => s.status === 'VERIFIED' && !isNegative(s.id, s.value) && s.value !== 'absent' && s.n >= 3)
      .sort((a, b) => b.n - a.n)[0]
    if (best) why.push({ text: `${signalPhrase(best.id, best.value)}, ${best.n} người nhắc`, sid: best.id })
  }
  return { place: p, section, score, why: why.slice(0, 3), tradeoffs: tradeoffs.slice(0, 2), visit: visitRange(p), confidence: confidenceOf(p), fromAnchor }
}

export function buildShortlist(places: Place[], t: TripState): Shortlist {
  const bySection = { sight: [], nature: [], food: [], shop: [] } as Record<Section, Candidate[]>
  const extra = { sight: [], nature: [], food: [], shop: [] } as Record<Section, Candidate[]>
  let steep = 0
  const dropped = new Set(t.dropped.map((d) => d.id))
  for (const p of places) {
    if (dropped.has(p.id)) continue
    if (p.googleStatus && /đóng cửa vĩnh viễn|tạm thời đóng cửa/i.test(p.googleStatus)) continue
    if (t.rules.avoidSteep && !t.relaxed.includes('avoidSteep') && has(p, 'steep_or_stairs')) {
      steep++
      continue
    }
    const c = evaluate(p, t)
    if (!c) continue
    ;(p.kind === 'experience' || t.mustVisit.includes(p.id) ? bySection : extra)[c.section].push(c)
  }
  for (const s of SECTIONS) {
    bySection[s].sort((a, b) => b.score - a.score)
    bySection[s] = bySection[s].slice(0, 8)
    extra[s].sort((a, b) => (b.place.reviewCount ?? 0) - (a.place.reviewCount ?? 0))
    extra[s] = extra[s].slice(0, 6)
  }
  return { bySection, extra, excludedByRule: steep ? [{ rule: 'Tránh đường dốc', count: steep }] : [] }
}

// Near-duplicates: same kind of place sharing two or more strong experiences.
export function similarGroups(cands: Candidate[]): Candidate[][] {
  const key = (c: Candidate) =>
    new Set(
      visible(c.place)
        .filter((s) => s.n >= 3 && s.status === 'VERIFIED' && !isNegative(s.id, s.value))
        .map((s) => s.id)
        .filter((id) => !['food_quality', 'drink_quality', 'service_attitude', 'service_quality', 'value_for_money', 'cleanliness'].includes(id)),
    )
  const groups: Candidate[][] = []
  const used = new Set<string>()
  for (let i = 0; i < cands.length; i++) {
    if (used.has(cands[i].place.id)) continue
    const ki = key(cands[i])
    const g = [cands[i]]
    for (let j = i + 1; j < cands.length; j++) {
      if (used.has(cands[j].place.id)) continue
      if ((cands[i].place.category ?? '') !== (cands[j].place.category ?? '')) continue
      const shared = [...key(cands[j])].filter((x) => ki.has(x))
      if (shared.length >= 2) g.push(cands[j])
    }
    if (g.length > 1) {
      g.forEach((c) => used.add(c.place.id))
      groups.push(g.slice(0, 3))
    }
  }
  return groups
}

// Which one to keep inside a near-duplicate group, and the one-line reason (UX brief §3.1).
export function keepPick(group: Candidate[]): { keep: Candidate; reason: string } {
  const [keep, other] = [...group].sort((a, b) => b.score - a.score)
  const reasons: string[] = []
  if (keep.why.length > other.why.length) reasons.push('hợp với sở thích của bạn hơn')
  if (keep.fromAnchor + 10 < other.fromAnchor) reasons.push(`gần hơn khoảng ${other.fromAnchor - keep.fromAnchor} phút`)
  if (keep.tradeoffs.length < other.tradeoffs.length) reasons.push('ít điểm phải đánh đổi hơn')
  if ((keep.place.voices ?? 0) > (other.place.voices ?? 0) * 1.5) reasons.push('nhiều người nhắc tới hơn')
  return { keep, reason: reasons.length ? reasons.slice(0, 2).join(', ') : 'điểm phù hợp nhỉnh hơn một chút' }
}

export function sharedTraits(group: Candidate[]) {
  const sets = group.map((c) => new Set(visible(c.place).filter((s) => s.n >= 2 && !isNegative(s.id, s.value)).map((s) => s.id)))
  return [...sets[0]].filter((id) => sets.every((s) => s.has(id))).slice(0, 2)
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

// One-line difference after a curation change (§2.8).
export function deltaLine(before: Plan, after: Plan) {
  const dp = after.totals.places - before.totals.places
  const dv = after.totals.visit - before.totals.visit
  const dt = after.totals.travel - before.totals.travel
  const sign = (n: number) => (n > 0 ? `+${n}` : `${n}`)
  const parts = [`${sign(dp)} nơi`, `${sign(dv)} phút tham quan`, `${sign(dt)} phút di chuyển`]
  const tight = after.days.find((d) => d.slack < 0)
  const note = tight ? `Ngày ${tight.index + 1} có thể quá tải.` : after.days.some((d) => d.robustness === 'Mong manh') ? 'Có ngày hơi sát giờ.' : 'Vẫn trong khả năng.'
  return { text: parts.join(', '), note, warn: !!tight }
}

// Rain plan for exposed stops: a sheltered or indoor pick nearby from the shortlist.
export function rainBackup(stop: Stop, pool: Place[]) {
  if (!has(stop.place, 'weather_exposed')) return null
  const alt = pool
    .filter((p) => p.id !== stop.place.id && (has(p, 'weather_exposed', 'sheltered') || has(p, 'setting', 'indoor')))
    .sort((a, b) => travelMin(stop.place, a, 'motorbike') - travelMin(stop.place, b, 'motorbike'))[0]
  return alt ?? null
}
