// Shapes of the Planning API (src/planning/engine.py, session.py, output.py, robustness.py, objectives.py).

// A warning is {code, text} (src/planning/build.py _warn); text is the Vietnamese sentence to show.
export interface Warning {
  code: string
  text: string
}

export type DropReason = 'far' | 'crowded' | 'pricey' | 'dislike' | 'visited'
export type Pace = 'slow' | 'normal' | 'packed'

// Backend Item kinds (src/planning/model.py): visit | travel | wait | free | rest | meal_free (travel carries its buffer as note "+N"; rest note "home" = rest at the lodging).
export interface ItineraryItem {
  kind: 'visit' | 'travel' | 'wait' | 'free' | 'buffer' | 'rest' | 'meal_free'
  start: string
  end: string
  place_id?: string
  name?: string
  from?: string
  to?: string
  mode?: string
  note?: string
}

export interface ItineraryDay {
  day: number // 1-based
  date: string | null
  weekday: string
  window: [string, string]
  method: string
  items: ItineraryItem[]
}

export interface TravelLoadDay {
  day: number
  travel_min: number
  wait_min: number
  longest_leg_min: number
}

export interface TimeSuitabilityDay {
  day: number
  penalty: number
  estimated: boolean
  overload_min: number
  places: { place_id: string; activity: string | null; visit: [string, string]; penalty: number;
    shortened_min: number; reasons: { reason: string; text: string; source: string;
      windows: [string, string][]; fit: number | null }[] }[]
}

export interface TimeRecommendation {
  kind: 'gap' | 'overload'
  day: number
  optional: boolean
  text: string
  period?: string
  windows?: [string, string][]
  alternatives: { id: string; name: string; activity: string | null; trial_visit: [string, string];
    requires_relayout: boolean; cost_unknown: boolean }[]
}

export interface Robustness {
  level: 'solid' | 'feasible' | 'fragile' // src/planning/robustness.py; label carries the Vietnamese text
  label: string
  reasons: string[]
  scenarios: Record<string, unknown>[]
}

export interface VariantLodging {
  id: string | null
  name: string | null
  price_vnd: number | null
}

// src/planning/backup.py backups(): a stand-in per place that may fail on its day, and what to drop first when late.
export interface Backups {
  places: { day: number; place_id: string; name: string; reasons: string[]; text: string; none_text: string | null;
    alternatives: { id: string; name: string; minutes_rough: number | null; for_this: boolean; reason: string | null }[] }[]
  on_delay: { day: number; place_id: string; name: string }[]
}

// src/planning/details.py plan_notes(): what to prepare for a stop (bring, book, watch for, season, fog).
export interface ChecklistItem {
  day: number
  place_id: string
  name: string
  kind: 'bring' | 'booking' | 'scam' | 'cold' | 'fog' | 'schedule' | 'season'
  text: string
}

export interface Variant {
  id: string
  objective: string
  preset?: null // retired: the overload directions are told apart by id (main | fit | travel | cost)
  gain?: string | null
  label: string
  definition?: string
  why?: string
  tradeoff?: string
  status?: 'available' | 'unavailable'
  confirmable?: boolean
  unavailable_reason?: string | null
  same_as?: string[]
  kept?: string[]
  delta_vs_selection?: { places: number; travel_min: number | null; cost_vnd: number | null }
  dropped_by_plan?: { place_id: string; name: string; reason: string; text: string; saved_min: number | null;
    saved_vnd: number | null; regret: number | null; source: 'data' | 'plan' }[]
  score: number[]
  metrics: { meal_cost_unknown?: number; scheduled_min?: number; meal_min?: number; travel_min: number; cost_vnd: number; cost_unknown: number; rain_exposed: number;
    exposure_unknown: number; repeats: number; pref_risk: number; places?: number; visit_min?: number;
    visit_density?: number; wish_coverage?: number | null; value_share?: number; estimated_cost_vnd?: number;
    cost_basis?: string; extras_max_vnd?: number; utility?: number; duration_loss_min?: number; transport_cost_vnd?: number | null }
  itinerary: ItineraryDay[]
  travel_load: TravelLoadDay[]
  time_suitability?: TimeSuitabilityDay[]
  recommendations?: TimeRecommendation[]
  robustness: Robustness
  backups: Backups
  warnings: Warning[]
  checklist?: ChecklistItem[]
  lodging: VariantLodging
}

export interface LodgingCandidate {
  id: string
  name: string
  price_vnd: number | null
  // Taste ranking (docs/PLANNING.md ⓐ): absent on an older view, then the screen shows only what is here.
  source?: 'corpus'
  address?: string | null
  rating?: number | null
  reviews?: number | null
  fit?: { text: string; mentions: number | null; quote: string | null }[] // "hợp vì": a liked feature with evidence
  unverified?: string[] // hard limits with no evidence either way ("chưa xác minh: …")
  avg_min?: number | null // mean minutes to the chosen places
  category?: string | null // the kind of stay ("Khách sạn 3 sao")
  area?: string | null
  // The same lines a Place Decision card carries (pd/types.ts Card), so one PlaceCard look serves every group.
  why?: { text: string; sid: string | null }[]
  tradeoffs?: { text: string; sid: string | null }[]
  location?: { center: string | null; km: number | null; minutes: number | null }
  confidence?: { level: 'high' | 'medium' | 'low'; reason: string }
  price_at?: string | null // the day Maps' hotel list showed that price a night (a reference, not the trip's dates)
}

export interface Lodging {
  status: 'pending' | 'ready' | 'unavailable' | 'booked' // booked: the user's own lodging (state.lodging_point), no candidates
  candidates: LodgingCandidate[]
}

export interface SessionState {
  chosen_variant: string | null
  plan_dropped?: string[]
  restored?: string[]
  lodging_touched: boolean
  lodging_id: string | null
  lodging_point: Record<string, unknown> | null
  budget_override: number | null
  visit_duration_override?: Record<string, number>
  assignment: Record<string, number>
  order_override: Record<string, string[]>
  dropped: { place_id: string; reason: DropReason | null }[]
  locked: string[]
  pace_override: Pace | null
  objective_override: string | null
  day_window_override: Record<string, [number, number]>
  relaxed: { place_id: string; feature: string }[]
  last: string | null
}

// What the date itself changes (src/planning/conditions.py describe()): facts, never a promise.
export interface DayConditions {
  day: number
  date: string | null
  weather: 'none' | 'heavy' | 'severe'
  storm: boolean
  rain_mm: number | null
  gust_kmh: number | null
  day_type: 'weekday' | 'weekend' | 'holiday'
  crowd: 'normal' | 'busy' | 'peak'
  crowd_reasons: string[]
  closure_risk: string | null
  advisories: { kind: string; severity: string; note: string; source: string }[]
}

export interface CrowdTip {
  place_id: string
  name: string
  text: string
}

export interface View {
  duration_range?: [number, number]
  needs_hotel?: boolean
  chunk_assignments?: Record<string, number>
  chunks?: { id: number; start_day: number; end_day: number; places: string[] }[]
  ok: boolean
  variants: Variant[]
  active_variant?: Variant | null
  overload?: { level: 'tight' | 'overloaded'; estimated: boolean; needed: number; available: number;
    binding: string[]; selection_places: number; keep_all_valid: boolean; text: string } | null
  keep_all?: Variant & { violations: { kind: string; day: number | null; place_id: string | null; detail: string }[] } | null
  comparison: Record<string, unknown>[]
  warnings: Warning[]
  back_to_decision: { reason: string; places: string[] } | null
  lodging: Lodging
  itinerary: ItineraryDay[] | null
  travel_load: TravelLoadDay[] | null
  time_suitability?: TimeSuitabilityDay[] | null
  recommendations?: TimeRecommendation[] | null
  suggestions?: Suggestions
  metrics?: Variant['metrics'] | null
  robustness?: Robustness | null
  backups?: Backups | null
  violations?: { kind: string; day: number | null; place_id: string | null; detail: string }[]
  day_conditions?: DayConditions[]
  crowd_tips?: CrowdTip[]
  state: SessionState
}

export interface Suggestions {
  status: 'pending' | 'ready' | 'unavailable'
  token: string
  session_id: string
  items: TimeRecommendation[]
}

export type Action = (
  | { type: 'pick_variant'; id: string }
  | { type: 'pick_lodging'; id: string }
  | { type: 'clear_lodging' }
  | { type: 'set_lodging'; text: string; lat?: number; lng?: number }
  | { type: 'set_lodging_budget'; max_per_night: number | null }
  | { type: 'move_place'; place: string; day: number }
  | { type: 'reorder'; day: number; order: string[] }
  | { type: 'drop_place'; place: string; reason?: DropReason | null }
  | { type: 'add_from_backup'; place: string; day: number }
  | { type: 'swap'; place: string; with: string }
  | { type: 'lock_slot'; place: string }
  | { type: 'unlock'; place: string }
  | { type: 'set_pace'; level: Pace }
  | { type: 'set_visit_duration'; place: string; minutes: number | null }
  | { type: 'set_objective'; name: string }
  | { type: 'set_day_window'; day: number; start: string; end: string }
  | { type: 'relax'; feature: string; place_id?: string; place_ids?: string[]; scope?: 'whole_trip' }
  | { type: 'reoptimize' }
  | { type: 'make_room'; edit: { type: 'move_place'; place: string; day: number } | { type: 'add_from_backup'; place: string; day: number } | { type: 'swap'; place: string; with: string }; drop_places: string[] }
  | { type: 'undo' }
  | { type: 'redo' }
) & { _preview_token?: string }

export interface ActPreview {
  token: string
  action: Action
  view: View
  delta: Record<string, number | null>
  violations: { kind: string; day: number | null; place_id: string | null; detail: string }[]
  confirmable: boolean
  make_room: Action[]
}

export interface Diff {
  affected_chunks?: number[]
  scope: 'none' | 'relayout' | 'variant' | 'lodging_home' | 'lodging_fetch'
}

export interface ActResult {
  view: View
  diff: Diff
}

export interface TurnHandlers {
  say?: (d: { delta?: string; replace?: string }) => void
  view?: (d: ActResult) => void
  done?: () => void
  error?: (d: { message: string }) => void
}

export interface ProgressEvent {
  stage: string
  candidates: LodgingCandidate[]
  baseline_travel_min: number | null
}

// src/planning/engine.py routes(): the OSRM path of each day through its stops (coords are [lat, lng]); route is null when
// the day has fewer than two known points or the routing source is down, and the map then draws no line.
export interface DayRouteEnd { id: string | null; name: string | null; home: boolean }
export interface DayRoute {
  day: number // 1-based
  start: DayRouteEnd // where the day opens: the lodging (home), or the entry point on day one
  end: DayRouteEnd
  route: { coords: [number, number][]; minutes: number; source: string; fetched_at: string } | null
}

export interface PlanOutput {
  variants: Record<string, unknown>[]
  chosen: string
  itinerary: ItineraryDay[]
  route: Record<string, unknown>[]
  lodging: { chosen: VariantLodging; candidates: LodgingCandidate[] }
  cost: Record<string, unknown>
  travel_load: TravelLoadDay[]
  time_suitability?: TimeSuitabilityDay[]
  recommendations?: TimeRecommendation[]
  reasons: string[]
  tradeoffs: Record<string, unknown>[]
  warnings: Warning[]
  uncertainty: Record<string, unknown>
  robustness: Robustness
  backups: Record<string, unknown>[]
  provenance: Record<string, unknown>
}
