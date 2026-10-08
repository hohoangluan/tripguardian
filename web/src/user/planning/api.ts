import type { Action, ActResult, PlanOutput, ProgressEvent, View } from './types'
import { acceptsRevision, loadJourney, mutateJourney, resumeJourney } from '../journey'
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
