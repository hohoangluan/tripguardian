import type { Action, ActResult, PlanOutput, ProgressEvent, View } from './types'
import { acceptsRevision, loadJourney, mutateJourney, resumeJourney } from '../journey'
import { setOptimized } from '../store'
export { JourneyError as PlanningError } from '../journey'
export const loadPlanning = async (id: string) => { await resumeJourney(id); const j = await loadJourney(id, 'planning'); return { ...(j.result as {view: View}), id: j.id } }
export const act = async (id: string, a: Action) => (await mutateJourney(id, 'planning', 'act', a)).result as ActResult
export const confirm = async (id: string) => (await mutateJourney(id, 'planning', 'confirm')).result as PlanOutput
// GET + SSE: this route takes no body, so the native EventSource works (unlike /turn above).
export function watchLodging(id: string, onEvent: (e: { event: 'progress' | 'view' | 'done' | 'error'; data: unknown }) => void) {
  const es = new EventSource(`/api/harness/sessions/${id}/planning/lodging/events`)
  let active = true
  const path = location.pathname + location.search
  const forward = (ev: MessageEvent) => {
    if (!active || path !== location.pathname + location.search || !ev.data) return
    const envelope = JSON.parse(ev.data)
    if (envelope.stage === 'planning' && acceptsRevision(id, envelope.revision)) onEvent({ event: envelope.event, data: envelope.data })
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
    const r = (await mutateJourney(id, 'planning', 'recommend')).result as { view: View; proposal: { status: 'accepted' | 'fallback'; diagnostics: string[] } }
    const base = before && before.variants.length ? (before.state.chosen_variant ? travelOf(before) : before.variants[0].metrics.travel_min) : travelOf(r.view)
    setOptimized(id, { status: r.proposal.status, before: base, after: travelOf(r.view), diagnostics: r.proposal.diagnostics, seen: false })
    return r
  } catch {
    return null
  }
}
