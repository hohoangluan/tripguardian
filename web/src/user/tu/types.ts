// Shapes of the public Trip Understanding API.

export interface Chip {
  id: string
  label: string
  row: string | null
  effect?: number | null // places the "Đang hợp với bạn" count gains (+) or loses (−) if this chip alone is chosen
}

export interface Card {
  kind?: 'card'
  qid: string
  group: string
  text: string
  reason: string
  placeholder?: string // an example answer written by the agent for this question
  chips: Chip[]
  multi: boolean
  single_rows: string[]
  tier: number
  input: 'none' | 'text' | 'date' | 'place' | 'geo' | 'lodging' | 'transit' | 'rental' | 'cues' | 'kinds' | 'photo_pick'
  input_field: string | null
  exits: boolean
  custom: boolean
  params?: Record<string, any> // cues / kinds / photo_pick: see VibeParams
}

export interface Option {
  id: string
  label: string
  description: string
  prefilled: boolean
  because: string
  count: number | null
  photo: { place_id: string; name: string; url: string } | null
  cues: string[]
  places: string[]
}

export interface Tab {
  qid: string
  kind: 'required' | 'drill' | 'confirm' | 'agent' | 'maybe'
  header: string
  question: string
  why: string
  visual: boolean
  multi: boolean
  inputs: string[]
  options: Option[]
}

export interface Deck { kind: 'deck'; tabs: Tab[]; left: number; total: number }
export interface DeckIssue { key: string; code: 'past_date' | 'end_before_start' | 'too_long' | 'people_below_groups' | 'contradicts_said' | 'invalid' }
export interface ReadbackLine {
  kind: 'said' | 'guess' | 'default' | 'check'
  text: string
  tab: 'trip' | 'companions' | 'mobility' | 'care' | 'pace' | 'budget' | 'lodging' | 'more'
  undo?: string | null
}
export interface Readback { lines: ReadbackLine[]; digest: string | null; ok: boolean; missing?: string[]; deck?: Deck | null }
export type DeckAnswers = Record<string, string | string[]>

// One look-alike kind of a look (corpus.index): real places, real photos (src/trip/domain/vibes.py).
export interface VibeKind {
  id: string
  label: string
  style: string | null
  count: number
  places: { id: string; name: string }[]
  photos: { place_id: string; name: string; url: string }[]
}
export interface WebSource { url: string; title: string; domain: string }
export interface VibeParams {
  vibe: number
  phrase?: string
  cues?: string[]
  removed?: string[]
  matched?: number
  total?: number
  kinds?: VibeKind[]
  chosen?: string[]
  sources?: WebSource[]
  image?: boolean
  place?: { id: string; name: string; photo: string | null }
}
export interface VibeRow {
  target: string
  phrase: string
  status: 'cues' | 'kinds' | 'done' | 'none'
  cues: string[]
  chosen: string[]
  image: boolean
  picked: string | null
  places: number
}
export interface Step { id: string; label: string; status: 'run' | 'ok' | 'fail' }

// One coach or flight from a crawl (src/trip/domain/state.py Transit); times are local "YYYY-MM-DDTHH:MM".
export interface Transit {
  mode: 'plane' | 'bus'
  carrier: string
  depart_at: string
  arrive_at: string
  from_point: string
  to_point: string
  price_vnd: number | null
  source: string
  fetched_at: string
}

// A picked point (Trip State Base): origin, a booked lodging.
export interface GeoHit {
  text: string
  address: string
  province: string | null
  lat: number
  lng: number
  source: string
  fetched_at: string
}

export interface LodgingHit {
  kind: 'corpus' | 'live' | 'address'
  id?: string
  text: string
  address: string
  rating?: number | null
  lat: number
  lng: number
  // what a card shows (only on the top list): a missing value is shown as missing, never guessed
  price_vnd?: number | null
  price_at?: string | null
  category?: string | null
  area?: string | null
  reviews?: number | null
}

export interface Base {
  place_id: string | null
  text: string
  lat?: number | null
  lng?: number | null
  province?: string | null
  kind?: 'corpus' | 'live' | 'address' | null
}

export interface Row {
  target: string
  value: any
  mark: boolean
  confidence: 'high' | 'medium' | 'low'
  solo?: boolean | null // budget_vnd only: one traveller, so "cho 1 người"
}

export interface AnchorRow {
  target: string
  text: string
  place_id: string | null
  name: string | null
  state: 'matched' | 'choose' | 'missing'
  priority: 'must' | 'want'
}

export interface HardRow {
  target: string
  feature: string
  op: 'ne' | 'eq'
  value: string
  unknown_policy: 'exclude' | 'flag' | null
  coverage: { passed: number; failed: number; unknown: number; level: 'enough' | 'thin' | 'none' }
}

export interface SoftRow {
  target: string
  key: string
  feature: string
  value: string
  context: Record<string, string>
  weight: 'love' | 'avoid' | 'off'
  mark: boolean
  like: string | null // the place the user compared to ("không thích quán giống X"), when this taste came from it
}

export interface Understanding {
  readback: Readback | null
  required: { key: string; title: string; label: string; done: boolean }[] // title: short name; label: the sentence form
  purpose: Row | null
  trip: Row[]
  anchors: AnchorRow[]
  hard: HardRow[]
  soft: SoftRow[]
  pace: Row | null
  max_leg_min: Row | null
  crowd_tolerance: Row | null
  novelty: Row | null
  budget_vnd: Row | null
  unknowns: string[]
  unmapped: { target: string; phrase: string }[]
  safety_pending: boolean
  ready: boolean // no unresolved safety signal blocks choosing places; planning completion is required[].done
  missing: { target: string; label: string }[]
  matching: number // places passing the hard limits now (a fact, not a forecast)
  total: number
  board: { ids: string[]; vibe: string[] } // the places that fit now, best first (a chosen look's places lead)
  vibes: VibeRow[]
}

export interface Turn {
  role: 'user' | 'agent'
  text: string
  turn: number
}

export interface View {
  id: string
  transcript: Turn[]
  understanding: Understanding
  card: Card | Deck | null
  phase: 'chat' | 'quiz' | 'review'
}

export type Source = 'user' | 'anchor' | 'profile' | 'inferred' | 'default'
export interface Evidence { turn: number; quote?: string | null; tool?: string | null }
export type BudgetScope = 'trip_total' | 'per_day' | 'per_person' | 'per_person_day'
export interface Moment { at: string; how: 'self' | 'bus' | 'plane' }
export interface CompiledFrame {
  days: { date: string; start: string; end: string; busy: { start: string; end: string; kinds: string[]; labels: string[]; where: string | null }[]; intensity: 'light' | 'normal' | 'full' | 'free' }[]
  arrive: Moment | null
  leave: Moment | null
  drive_day_min: number | null
  periods: { period: string; kinds: string[]; activity: string | null; weight: number }[]
  visit: Record<string, number>
  meals: { skip: string[]; breakfast_at_lodging: boolean; snacks: boolean; shift_min: number }
  rest: { every_min: number; rest_min: number } | null
  pattern: 'interleave_kids' | null
  issues: { code: string; day: number }[]
}

export interface SearchInput {
  ontology_version: number
  readiness?: { missing: string[]; readback_ok: boolean } | null
  sources?: Record<string, Source>
  wishes?: { dishes: { dish: string; quote: string; place_ids: string[] }[]; kinds: { kind: string; quote: string; place_ids: string[] }[]; like: { place_id: string; but: string[]; quote: string }[] }
  corpus_binding?: Record<string, unknown> | null
  liked_groups?: string[]
  activities?: Record<string, string>
  time_preferences?: { place_id: string | null; activity: string | null; period: string; weight: number; evidence: Evidence[] }[]
  vibes?: { phrase: string; cues: string[]; styles: string[]; places: string[] }[]
  context: {
    start_date: string | null
    month_part?: 'early' | 'mid' | 'late' | null
    nights?: number | null
    driver?: 'self' | 'hired' | null
    companions_other?: string[]
    budget_unlimited?: boolean | null
    budget_intent?: { amount: number; currency: 'VND'; scope: BudgetScope; scope_guessed: boolean; source: Source; scope_source: Source; evidence: Evidence[]; scope_evidence: Evidence[] } | null
    frame?: CompiledFrame | null
    purpose?: string | null
    entry_point?: Base | null
    exit_point?: Base | null
    month: number | null
    days: number | null
    base: Base | null
    mobility: 'motorbike' | 'car' | 'walk' | null
    companions: string[]
    people: number | null
    checkin_at: string | null
    checkout_at: string | null
    day_end: string | null
    budget_vnd: number | null
    experience: 'first' | 'returning' | null
    origin?: Base | null
    arrival_mode?: 'self' | 'bus' | 'plane' | null
    inbound?: Transit | null
    outbound?: Transit | null
    lodging_booked?: 'yes' | 'no' | null
    lodging?: Base | null
  }
  hard_filters: { feature: string; op: 'ne' | 'eq'; value: string; unknown_policy: 'exclude' | 'flag' }[]
  anchors: { place_id: string; priority: 'must' | 'want' }[]
  soft_weights: { feature: string; value: string; context: Record<string, string> | null; weight: 1 | -1 | 0; source: string }[]
  pace: { level: 'slow' | 'normal' | 'packed' | null; max_leg_min: number | null; crowd_tolerance: string | null }
  novelty: { level: string | null; visited: string[] }
  unknowns: string[]
  unmapped: string[]
}

export type TurnInput =
  | { kind: 'deck'; answers: DeckAnswers }
  | { kind: 'drop'; target: string }
  | { kind: 'readback_ok'; value: string }
  | { kind: 'text'; text: string }
  | { kind: 'answer'; qid: string; chips: string[]; value?: string | null }
  | { kind: 'edit'; target: string; value: string | null }
  | { kind: 'show' }
  | { kind: 'image'; value: string; text?: string } // value: a data URL of the photo, ≤ ~45 KB (harness body limit)

export interface Handlers {
  preview?: (d: { fields: { target: string; value: unknown; quote: string }[] }) => void
  say?: (d: { delta?: string; replace?: string }) => void
  state?: (d: { understanding: Understanding }) => void
  card?: (d: Card | Deck | null) => void
  deck_issues?: (d: { issues: DeckIssue[] }) => void
  readback?: (d: Readback) => void
  progress?: (d: { steps: Step[]; sources: WebSource[] }) => void
  done?: (d: { search_input: SearchInput }) => void
  error?: (d: { message: string }) => void
}
