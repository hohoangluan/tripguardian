import type { TripState, Who } from '../trip'
import type { SearchInput } from './types'

// SearchInput -> the TripState the existing Shortlist / planner read. Lossy on purpose: what TripState cannot hold
// (unknown_policy, time contexts, unmapped wishes) stays in trip.searchInput for the real Place Decision.
export function fromSearchInput(si: SearchInput, today = new Date()): Partial<TripState> {
  const c = si.context
  const must = si.anchors.filter((a) => a.priority === 'must').map((a) => a.place_id)
  const prefs: TripState['prefs'] = {}
  for (const w of si.soft_weights) {
    if (w.weight === 0) continue
    prefs[w.feature] = { weight: w.weight > 0 ? 'love' : 'avoid', from: w.source === 'profile' ? 'profile' : 'answer' }
  }
  const patch: Partial<TripState> = {
    searchInput: si,
    prefs,
    mustVisit: must,
    locked: must,
    selected: must,
    rules: {
      maxLegMin: si.pace.max_leg_min,
      avoidSteep: si.hard_filters.some((h) => h.feature === 'steep_or_stairs' && h.op === 'ne' && h.value === 'present'),
      dayEnd: c.day_end ?? '21:30',
    },
  }
  if (c.start_date) patch.startDate = c.start_date
  else if (c.month) patch.startDate = firstOfMonth(c.month, today)
  if (c.days) patch.days = c.days
  if (c.people) patch.people = c.people
  if (c.mobility) patch.vehicle = c.mobility
  if (c.companions.length) patch.who = c.companions as Who[]
  if (c.base?.place_id) patch.lodging = c.base.place_id
  if (c.arrive_at) patch.arriveAt = c.arrive_at
  if (c.leave_at) patch.leaveAt = c.leave_at
  if (si.pace.level) patch.pace = si.pace.level
  return patch
}

// "tháng 12" without a day: the 1st of the next such month (an estimate the user can change later).
function firstOfMonth(month: number, today: Date) {
  const year = month - 1 < today.getMonth() ? today.getFullYear() + 1 : today.getFullYear()
  return `${year}-${String(month).padStart(2, '0')}-01`
}
