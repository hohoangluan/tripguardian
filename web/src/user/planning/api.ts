import type { Action, ActResult, PlanOutput, ProgressEvent, View } from './types'
import { acceptsRevision, cacheDrop, cacheEpoch, cacheGet, cachePut, loadJourney, mutateJourney, readJourney, resumeJourney, type JourneyView } from '../journey'
import { setOptimized } from '../store'
export { JourneyError as PlanningError } from '../journey'
// What Lịch trình shows, as the cache (journey.ts) keeps it under `${journey}:planning`.
// confirmedTrip: the journey already has a confirmed plan (the trip runs on it until the next confirm).
// current: nothing changed the journey while this was being read (false = a newer view may already be on screen).
export interface Loaded { view: View; id: string; confirmedTrip: boolean; revision: number }
export const peekPlanning = (id: string) => cacheGet<Loaded>(id, 'planning')
export const forgetPlanning = (id: string) => cacheDrop(id)
const keep = (j: JourneyView, view: View) => cachePut(j.id, 'planning', { view, id: j.id, confirmedTrip: 'planning' in j.outputs, revision: j.revision } satisfies Loaded)
// A view that arrived on the lodging stream (the crawl finished): the journey did not change through this client.
export const rememberPlanning = (id: string, view: View, confirmedTrip: boolean, revision: number) => cachePut(id, 'planning', { view, id, confirmedTrip, revision } satisfies Loaded)
export const loadPlanning = async (id: string): Promise<Loaded & { current: boolean }> => {
  await resumeJourney(id)
  const epoch = cacheEpoch(id)
  const j = await loadJourney(id, 'planning')
  const out: Loaded = { ...(j.result as { view: View }), id: j.id, confirmedTrip: 'planning' in j.outputs, revision: j.revision }
  cachePut(id, 'planning', out, epoch)
  return { ...out, current: epoch === cacheEpoch(id) }
}
export const act = async (id: string, a: Action) => {
  const j = await mutateJourney(id, 'planning', 'act', a)
  const r = j.result as ActResult
  keep(j, r.view)
  return r
}
// A confirm changes `confirmed` and the plan the trip runs on, so the cache is left empty: the next visit reads it again.
export const confirm = async (id: string) => (await mutateJourney(id, 'planning', 'confirm')).result as PlanOutput
// Card.fit ("Hợp với bạn") of places the plan only suggests, read from Place Decision (src/decision/engine.py fits), never
// computed here. null: the trip names no taste, or the place is not a candidate. Cached under `${journey}:fits`, which any
// change to the journey empties (the selection moves the fit).
export type Fit = { stars: number; level: string } | null
export async function loadFits(id: string, places: string[]): Promise<Record<string, Fit>> {
  const epoch = cacheEpoch(id)
  const known = cacheGet<Record<string, Fit>>(id, 'fits')?.value ?? {}
  const need = places.filter((p) => !(p in known))
  if (!need.length) return known
  const all = { ...known }
  for (let i = 0; i < need.length; i += 50) // the server takes at most 60 ids per read
    Object.assign(all, (await readJourney<{ fits: Record<string, Fit> }>(id, `decision/fit?places=${encodeURIComponent(need.slice(i, i + 50).join(','))}`)).fits)
  cachePut(id, 'fits', all, epoch)
  return all
}
// GET + SSE: this route takes no body, so the native EventSource works (unlike /turn above).
export function watchLodging(id: string, onEvent: (e: { event: 'progress' | 'view' | 'done' | 'error'; data: unknown; revision: number }) => void) {
  const es = new EventSource(`/api/harness/sessions/${id}/planning/lodging/events`)
  let active = true
  const path = location.pathname + location.search
  const forward = (ev: MessageEvent) => {
    if (!active || path !== location.pathname + location.search || !ev.data) return
    const envelope = JSON.parse(ev.data)
    if (envelope.stage === 'planning' && acceptsRevision(id, envelope.revision)) onEvent({ event: envelope.event, data: envelope.data, revision: envelope.revision })
  }
  es.addEventListener('event', forward as EventListener)
  es.onerror = () => es.close() // the server closes the stream itself once done/error fires; a transport drop just stops silently
  return () => { active = false; es.close() }
}

export type { ProgressEvent }

const travelOf = (v: View) => {
  const chosen = v.variants.find((x) => x.id === v.state.chosen_variant) ?? v.variants[0]
  return v.travel_load ? v.travel_load.reduce((n, d) => n + d.travel_min, 0) : chosen?.metrics.travel_min ?? 0
}
// One proposal from the Planning Agent over the deterministic baseline; the server keeps it only when it is valid and
// not worse (docs/P4_PLANNING.md). Remembers the before / after travel so Lịch trình can say what changed and offer undo.
export async function runRecommend(id: string, before: View | null) {
  try {
    const j = await mutateJourney(id, 'planning', 'recommend')
    const r = j.result as { view: View; proposal: { status: 'accepted' | 'fallback'; diagnostics: string[] } }
    keep(j, r.view)
    const base = before && before.variants.length ? (before.state.chosen_variant ? travelOf(before) : before.variants[0].metrics.travel_min) : travelOf(r.view)
    setOptimized(id, { status: r.proposal.status, before: base, after: travelOf(r.view), diagnostics: r.proposal.diagnostics, seen: false })
    return r
  } catch {
    return null
  }
}
