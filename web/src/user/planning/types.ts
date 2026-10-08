// Shapes of the Planning API (src/planning/engine.py, session.py, output.py, robustness.py, objectives.py).

// A warning is {code, text} (src/planning/build.py _warn); text is the Vietnamese sentence to show.
export interface Warning {
  code: string
  text: string
}

export type DropReason = 'far' | 'crowded' | 'pricey' | 'dislike' | 'visited'
export type Pace = 'slow' | 'normal' | 'packed'

// Backend Item kinds (src/planning/model.py): visit | travel | wait | buffer | rest | meal_free.
export interface ItineraryItem {
  kind: 'visit' | 'travel' | 'wait' | 'buffer' | 'rest' | 'meal_free'
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

export interface Variant {
  id: string
  objective: string
  label: string
  score: [number, number]
  metrics: { travel_min: number; cost_vnd: number; cost_unknown: number; rain_exposed: number;
    exposure_unknown: number; repeats: number; pref_risk: number }
  itinerary: ItineraryDay[]
  travel_load: TravelLoadDay[]
  robustness: Robustness
  backups: Record<string, unknown>[]
  warnings: Warning[]
  lodging: VariantLodging
}

export interface LodgingCandidate {
  id: string
  name: string
  price_vnd: number | null
}

export interface Lodging {
  status: 'pending' | 'ready' | 'unavailable'
  candidates: LodgingCandidate[]
}

export interface SessionState {
  chosen_variant: string | null
  lodging_touched: boolean
  lodging_id: string | null
  lodging_point: Record<string, unknown> | null
  budget_override: number | null
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
  ok: boolean
  variants: Variant[]
  comparison: Record<string, unknown>[]
  warnings: Warning[]
  back_to_decision: { reason: string; places: string[] } | null
  lodging: Lodging
  itinerary: ItineraryDay[] | null
  travel_load: TravelLoadDay[] | null
  day_conditions?: DayConditions[]
  crowd_tips?: CrowdTip[]
  state: SessionState
}

export type Action =
  | { type: 'pick_variant'; id: string }
  | { type: 'pick_lodging'; id: string }
  | { type: 'clear_lodging' }
  | { type: 'set_lodging'; text: string }
  | { type: 'set_lodging_budget'; max_per_night: number | null }
  | { type: 'move_place'; place: string; day: number }
  | { type: 'reorder'; day: number; order: string[] }
  | { type: 'drop_place'; place: string; reason?: DropReason | null }
  | { type: 'add_from_backup'; place: string; day: number }
  | { type: 'swap'; place: string; with: string }
  | { type: 'lock_slot'; place: string }
  | { type: 'unlock'; place: string }
  | { type: 'set_pace'; level: Pace }
  | { type: 'set_objective'; name: string }
  | { type: 'set_day_window'; day: number; start: string; end: string }
  | { type: 'relax'; feature: string; place_id?: string; place_ids?: string[]; scope?: 'whole_trip' }
  | { type: 'undo' }
  | { type: 'redo' }

export interface Diff {
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

export interface PlanOutput {
  variants: Record<string, unknown>[]
  chosen: string
  itinerary: ItineraryDay[]
  route: Record<string, unknown>[]
  lodging: { chosen: VariantLodging; candidates: LodgingCandidate[] }
  cost: Record<string, unknown>
  travel_load: TravelLoadDay[]
  reasons: string[]
  tradeoffs: Record<string, unknown>[]
  warnings: Warning[]
  uncertainty: Record<string, unknown>
  robustness: Robustness
  backups: Record<string, unknown>[]
  provenance: Record<string, unknown>
}
