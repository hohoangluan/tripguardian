import type { TripState, Who } from '../trip'
import type { SearchInput } from './types'

// SearchInput -> the TripState the existing Shortlist / planner read. Lossy on purpose: what TripState cannot hold
// (unknown_policy, time contexts, unmapped wishes) stays in trip.searchInput for the real Place Decision.
export function fromSearchInput(si: SearchInput): Partial<TripState> {
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
      dayEnd: c.day_end ?? '',
    },
  }
  patch.startDate = c.start_date ?? ''
  patch.days = c.days
  patch.people = c.people
  patch.vehicle = c.mobility
  patch.who = c.companions as Who[]
  patch.lodging = c.lodging?.place_id ?? c.lodging?.text ?? c.base?.place_id ?? null
  patch.arriveAt = c.frame?.days[0]?.start ?? c.checkin_at ?? ''
  patch.leaveAt = c.frame?.days.at(-1)?.end ?? c.checkout_at ?? ''
  patch.pace = si.pace.level
  return patch
}
