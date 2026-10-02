// Shapes of the Trip Understanding API (src/trip/engine.py, understanding.py, state.py SearchInput).

export interface Chip {
  id: string
  label: string
  row: string | null
}

export interface Card {
  qid: string
  group: string
  text: string
  reason: string
  chips: Chip[]
  multi: boolean
  single_rows: string[]
  tier: number
  input: 'none' | 'text' | 'date' | 'place'
  input_field: string | null
  exits: boolean
  custom: boolean
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
}

export interface SearchInput {
  ontology_version: number
  context: {
    start_date: string | null
    month: number | null
    days: number | null
    base: { place_id: string | null; text: string } | null
    mobility: 'motorbike' | 'car' | 'ride' | null
    companions: string[]
    people: number | null
    arrive_at: string | null
    leave_at: string | null
    day_end: string | null
    budget_vnd: number | null
    experience: 'first' | 'returning' | null
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
  | { kind: 'answer'; qid: string; chips: string[]; text?: string; value?: string | null }
  | { kind: 'edit'; target: string; value: string | null }
  | { kind: 'show' }

export interface Handlers {
  preview?: (d: { fields: { target: string; value: unknown; quote: string }[] }) => void
  say?: (d: { delta?: string; replace?: string }) => void
  state?: (d: { understanding: Understanding }) => void
  card?: (d: Card | null) => void
  done?: (d: { search_input: SearchInput }) => void
  error?: (d: { message: string }) => void
}
