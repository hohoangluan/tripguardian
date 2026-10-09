// Shapes of the Place Decision API (src/decision/engine.py, pipeline.py, cards.py, feasibility.py).

export type DropReason = 'far' | 'crowded' | 'pricey' | 'dislike' | 'visited'

export interface Claim {
  text: string
  sid: string | null
}

export interface Card {
  id: string
  name: string
  category: string | null
  area: string | null
  role: 'experience' | 'meal'
  group: string
  status: 'main' | 'unverified' | 'excluded'
  score: number
  parts: Record<string, number>
  why: Claim[]
  tradeoffs: Claim[]
  visit: { short: number; typical: number; long: number; source: string } | null
  location: { center: string; km: number | null; minutes: number | null }
  price: string | null
  confidence: { level: 'high' | 'medium' | 'low'; reason: string }
  declined: boolean
  depends_on_unknown: string | null
  warnings: string[]
  unverified: string[]
  failed: string[]
  chosen: boolean
  locked: boolean
  anchor: boolean
  alternatives: { id: string; name: string }[]
  suggested: boolean
  top: boolean
}

export interface Group {
  id: string
  label: string
  cards: Card[]
  total: number
}

// How one display group's shown window changed in the last rebuild (src/decision/window.py).
export interface Change { kept: number; added: number; removed: number; replaced_all: boolean }

export type Action =
  | { type: 'select' | 'lock' | 'unlock' | 'wishlist'; place_id: string }
  | { type: 'drop'; place_id: string; reason?: DropReason | null }
  | { type: 'swap'; place_id: string; with_id: string }
  | { type: 'relax'; place_id: string; feature: string }
  | { type: 'answer'; qid: string; chip: string }
  | { type: 'undo' }

export interface Fix {
  label: string
  effect: string
  action: Action | null
}

export interface Conflict {
  id: string
  check: string
  physical: boolean
  title: string
  rule: string
  places: string[]
  fixes: Fix[]
}

export interface Feasibility {
  status: 'feasible' | 'partial' | 'infeasible' | 'unknown'
  known_days: boolean
  totals: { places: number; visit: number; buffer: number; travel: number; needed: number; available: number }
  slack: number | null
  conflicts: Conflict[]
  warnings: string[]
}

export interface Pending {
  qid: string
  text: string
  reason: string
  chips: { id: string; label: string }[]
  data: Record<string, unknown>
}

export interface View {
  version: number
  groups: Group[]
  change: Record<string, Change>
  shortlist: string[]
  selected: string[]
  locked: string[]
  unverified: { count: number; open: boolean; cards: Card[] }
  excluded: { by_rule: { rule: string; label: string; count: number }[] }
  wishlist: { id: string; name: string; reason: string }[]
  dropped: { id: string; name: string; reason: DropReason | null }[]
  feasibility: Feasibility
  pending: Pending | null
  profile: Record<string, unknown>
  known_days: boolean
  days: { index: number; date: string | null; weekday: string | null }[]
  unknowns: string[]
  unmapped: string[]
}

export interface Diff {
  added: string[]
  removed: string[]
  status: [string, string]
  delta: { places: number; visit: number; travel: number }
  text: string
  scope: { from: string | null; keep: string[] } | null
}

export interface ActResult {
  view: View
  diff: Diff
  goto?: 'understand'
}

export interface CompareRow {
  aspect: string
  label: string
  a: string
  b: string
  better: 'a' | 'b' | 'none' | 'unknown'
}

export interface CompareResult {
  a: { id: string; name: string }
  b: { id: string; name: string }
  rows: CompareRow[]
  sacrifice: CompareRow[]
}

export interface WhyNot {
  id: string
  name: string | null
  known: boolean
  listed?: boolean // in the suggestions, maybe below what is loaded yet
  status: string | null
  reasons: string[]
}

export interface DecisionOutput {
  confirmed: { id: string; name: string; role: 'anchor' | 'locked' | 'selected'; flags: string[]; relaxed: string[] }[]
  backup_pool: { id: string; name: string; for: string | null; reason: string }[]
  wishlist: { id: string; name: string; reason: string }[]
}

export interface TurnHandlers {
  say?: (d: { delta?: string; replace?: string }) => void
  view?: (d: ActResult) => void
  done?: () => void
  error?: (d: { message: string }) => void
}

// GET /api/harness/sessions/<id>/preview: the schedule the current selection would get (src/harness/dispatch.py preview).
export interface PreviewVariant {
  id: string
  objective: string
  label: string
  metrics: { travel_min: number; cost_vnd: number; cost_unknown: number }
  robustness: { level: 'solid' | 'feasible' | 'fragile'; label: string }
  places: string[][] // place ids per day
}

export interface PlanPreview {
  revision: number
  status: 'ready' | 'failed' | 'blocked' | 'empty'
  plan: { ok: boolean; days: number; warnings: { code: string; text: string }[]; back_to_decision: { reason: string; places: string[] } | null; variants: PreviewVariant[] } | null
}

// GET /api/harness/trips: one line per journey of the signed-in account, newest first.
export interface TripSummary {
  id: string
  stage: 'trip' | 'decision' | 'planning'
  revision: number
  start_date: string | null
  days: number | null
  people: number | null
  places: string[]
  confirmed: boolean
}
