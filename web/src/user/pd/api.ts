import type { Action, ActResult, CompareResult, PlanPreview, TripSummary, TurnHandlers, View, WhyNot } from './types'
import { json, loadJourney, mutateJourney, readJourney, resumeJourney } from '../journey'
export { JourneyError as DecisionError } from '../journey'
export const loadDecision = async (id: string) => {
  const recovery = await resumeJourney(id)
  const j = await loadJourney(id, 'decision')
  return { ...(j.result as {view: View}), id: j.id, stage: j.stage, recoveredHandoff: recovery.recoveredOperation === 'advance' && recovery.view.stage === 'planning' ? recovery.view : undefined }
}
export const act = async (id: string, a: Action) => (await mutateJourney(id, 'decision', 'act', a)).result as ActResult
export const compare = (id: string, a: string, b: string) => readJourney<CompareResult>(id, `decision/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`)
export const morePlaces = (id: string, group: string) => readJourney<{ view: View }>(id, `decision/page?group=${encodeURIComponent(group)}`)
export const whyNot = (id: string, place: string) => readJourney<WhyNot>(id, `decision/why-not?place=${encodeURIComponent(place)}`)
export async function sendText(id: string, text: string, h: TurnHandlers): Promise<void> { await mutateJourney(id, 'decision', 'turn', {text}, h as Record<string, ((d: any) => void) | undefined>) }
export const previewPlan = (id: string) => fetch(`/api/harness/sessions/${id}/preview`).then(json<PlanPreview>)
export const tripSummaries = (ids: string[]) => (ids.length ? fetch(`/api/harness/trips?ids=${ids.join(',')}`).then(json<TripSummary[]>) : Promise.resolve([]))
