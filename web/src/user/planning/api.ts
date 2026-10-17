import type { Action, ActPreview, ActResult, DayRoute, PlanOutput, ProgressEvent, Suggestions, View } from './types'
import { acceptsRevision, loadJourney, mutateJourney, readJourney, resumeJourney, type JourneyView } from '../journey'
import { setOptimized } from '../store'
export { JourneyError as PlanningError } from '../journey'
// Lựa chọn starts the first read of this stage the moment it has advanced (see pd/api primeDecision): no resume step, no wait for the route.
const primed = new Map<string, Promise<JourneyView>>()
export const primePlanning = (id: string) => {
  const read = loadJourney(id, 'planning')
  read.catch(() => {})
  primed.set(id, read)
  setTimeout(() => primed.delete(id), 30_000)
}
export const loadPlanning = async (id: string) => {
  const early = primed.get(id)
  primed.delete(id)
  let j: JourneyView | undefined
  if (early) j = await early.catch(() => undefined) // the full read below reports a real error
  if (!j) { await resumeJourney(id); j = await loadJourney(id, 'planning') }
  return { ...(j.result as {view: View}), id: j.id, revision: j.revision }
}
export const act = async (id: string, a: Action) => { const j = await mutateJourney(id, 'planning', 'act', a); return { ...(j.result as ActResult), revision: j.revision } }
export const readSuggestions = (id: string) => readJourney<Suggestions & { revision: number }>(id, 'planning/suggestions')
export const previewAct = (id: string, action: Action) => readJourney<ActPreview & { revision: number }>(id, `planning/preview-act?action=${encodeURIComponent(JSON.stringify(action))}`)
export const readRoutes = (id: string) => readJourney<{ days: DayRoute[] }>(id, 'planning/routes')
export { acceptsRevision }
export const confirm = async (id: string) => (await mutateJourney(id, 'planning', 'confirm')).result as PlanOutput
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
// not worse (docs/PLANNING.md). Remembers the before / after travel so Lịch trình can say what changed and offer undo.
export async function runRecommend(id: string, before: View | null) {
  try {
    const j = await mutateJourney(id, 'planning', 'recommend')
    const r = { ...(j.result as { view: View; proposal: { status: 'accepted' | 'fallback'; diagnostics: string[] } }), revision: j.revision }
    const base = before && before.variants.length ? (before.state.chosen_variant ? travelOf(before) : before.variants[0].metrics.travel_min) : travelOf(r.view)
    setOptimized(id, { status: r.proposal.status, before: base, after: travelOf(r.view), diagnostics: r.proposal.diagnostics, seen: false })
    return r
  } catch {
    return null
  }
}
