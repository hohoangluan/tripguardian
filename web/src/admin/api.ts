// Review API of `python -m corpus review` (src/corpus/review/server.py). Vite proxies /api to it in dev.

export interface LabelItem {
  id: string
  place: string
  placeName: string | null
  feature: string
  value: string
  quote: string
  context: Record<string, string>
  observedAt: string | null
  text: string
  definition: { hint: string; claim: string | null; values: string[] }
  review: {
    rating: string | null
    published: string | null
    author: string | null
    details: string[]
    likes: number | string | null
    photos: number | string | null
    list: 'newest' | 'relevant' | null
  } | null
  placeInfo: {
    category: string | null
    address: string | null
    url: string | null
    rating: string | null
    review_count: string | null
    price: string | null
    status: string | null
    description: string | null
    attributes: string[]
  }
  others: { value: string; quote: string; source: string; rating: string | null; published: string | null }[]
  othersCount: Record<string, number>
}

export type Label = 'correct' | 'wrong' | 'unsure'

export interface LabelRow {
  feature: string
  value: string
  observations: number
  correct: number
  wrong: number
  unsure: number
  precision: number | null
  lower: number
  gate: boolean
  needed: number
}

export interface LabelStats {
  gate: { min_n: number; lower: number }
  rows: LabelRow[]
  labelled: number
  total: number
}

export interface ServerDecision {
  at: string
  kind: string
  id: string
  decision: string
  note: string
}

async function call<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, body === undefined ? undefined : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  const text = await r.text()
  let json: unknown = null
  try {
    json = JSON.parse(text)
  } catch {
    /* the dev server answered with a page, not the API */
  }
  if (!r.ok || json === null) throw new Error((json as { error?: string } | null)?.error ?? `API ${r.status}`)
  return json as T
}

export const nextLabels = (n: number, feature?: string) =>
  call<{ items: LabelItem[] }>(`/api/labels/next?n=${n}${feature ? `&feature=${encodeURIComponent(feature)}` : ''}`).then((r) => r.items)
export const sendLabel = (id: string, label: Label, note = '') => call<ServerDecision>('/api/labels', { id, label, note })
export const labelStats = () => call<LabelStats>('/api/labels/stats')
export const featureDecisions = () => call<{ decisions: Record<string, ServerDecision> }>('/api/decisions?kind=feature_review').then((r) => r.decisions)
export const sendDecision = (id: string, decision: string, note = '') => call<ServerDecision>('/api/decision', { kind: 'feature_review', id, decision, note })
