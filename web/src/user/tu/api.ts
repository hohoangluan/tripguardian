import type { Handlers, TurnInput, View } from './types'
import { createJourney, loadJourney, mutateJourney, json } from '../journey'
export { JourneyError as ApiError } from '../journey'
export const createSession = async (experience: string | null, startWith: string | null) => { const j = await createJourney(experience, startWith); return { ...(j.result as View), id: j.id } }
export const getSession = async (id: string) => { const j = await loadJourney(id, 'trip'); return { ...(j.result as View), id: j.id } }
export const searchPlaces = (q: string) => fetch(`/api/harness/places?q=${encodeURIComponent(q)}`).then(json<{ id: string; name: string; category: string | null }[]>)
export async function sendTurn(id: string, input: TurnInput, h: Handlers): Promise<void> { await mutateJourney(id, 'trip', 'turn', input, h as Record<string, ((d: any) => void) | undefined>) }
