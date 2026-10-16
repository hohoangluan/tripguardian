import type { LodgingCandidate } from '../planning/types'
import type { Action, ActResult, CompareResult, PlanPreview, SearchResult, TripSummary, TurnHandlers, View, WhyNot } from './types'
import { json, loadJourney, mutateJourney, readJourney, resumeJourney } from '../journey'
export { JourneyError as DecisionError } from '../journey'
export const loadDecision = async (id: string) => {
  const recovery = await resumeJourney(id)
  const j = await loadJourney(id, 'decision')
  return { ...(j.result as {view: View}), id: j.id, stage: j.stage, recoveredHandoff: recovery.recoveredOperation === 'advance' && recovery.view.stage === 'planning' ? recovery.view : undefined }
}
export const act = async (id: string, a: Action) => (await mutateJourney(id, 'decision', 'act', a)).result as ActResult
export const compare = (id: string, a: string, b: string) => readJourney<CompareResult>(id, `decision/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`)
// Page n (1 = first) of one tab; without n the next page.
export const gotoPage = (id: string, group: string, n?: number) => readJourney<{ view: View }>(id, `decision/page?group=${encodeURIComponent(group)}${n ? `&n=${n}` : ''}`)
export const searchList = (id: string, q: string) => readJourney<SearchResult>(id, `decision/search?q=${encodeURIComponent(q)}`)
export const whyNot = (id: string, place: string) => readJourney<WhyNot>(id, `decision/why-not?place=${encodeURIComponent(place)}`)
export async function sendText(id: string, text: string, h: TurnHandlers): Promise<void> { await mutateJourney(id, 'decision', 'turn', {text}, h as Record<string, ((d: any) => void) | undefined>) }
// Served stays around the places chosen so far, ranked by Planning; "empty" until a place is chosen.
// Every served stay, one page at a time (`total` of them): those around the chosen places first.
export const lodgingOptions = (id: string, offset = 0) => readJourney<{ status: 'empty' | 'ready' | 'unavailable'; candidates: LodgingCandidate[]; total?: number }>(id, `decision/lodging?offset=${offset}`)
export const previewPlan = (id: string) => fetch(`/api/harness/sessions/${id}/preview`).then(json<PlanPreview>)
export const deleteTrip = (id: string) => fetch(`/api/harness/sessions/${id}`, { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: '{}' }).then(json<{ deleted: boolean }>)
export const tripSummaries = () => fetch('/api/harness/trips').then(json<TripSummary[]>)
