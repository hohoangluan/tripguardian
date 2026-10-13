// Shapes of the Trip Understanding API (src/trip/engine.py, understanding.py, state.py SearchInput).

export interface Chip {
  id: string
  label: string
  row: string | null
  effect?: number | null // places the "Đang hợp với bạn" count gains (+) or loses (−) if this chip alone is chosen
}

export interface Card {
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
  ready: boolean // the minimum is known: Next is allowed (decided by the server, not by the agent)
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
  card: Card | null
  phase: 'chat' | 'quiz' | 'review'
}

export interface SearchInput {
  ontology_version: number
  context: {
    start_date: string | null
    month: number | null
    days: number | null
    base: Base | null
    mobility: 'motorbike' | 'car' | 'walk' | null
    companions: string[]
    people: number | null
    arrive_at: string | null
    leave_at: string | null
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
  | { kind: 'text'; text: string }
  | { kind: 'answer'; qid: string; chips: string[]; value?: string | null }
  | { kind: 'edit'; target: string; value: string | null }
  | { kind: 'show' }
  | { kind: 'image'; value: string; text?: string } // value: a data URL of the photo, ≤ ~45 KB (harness body limit)

export interface Handlers {
  preview?: (d: { fields: { target: string; value: unknown; quote: string }[] }) => void
  say?: (d: { delta?: string; replace?: string }) => void
  state?: (d: { understanding: Understanding }) => void
  card?: (d: Card | null) => void
  progress?: (d: { steps: Step[]; sources: WebSource[] }) => void
  done?: (d: { search_input: SearchInput }) => void
  error?: (d: { message: string }) => void
}
