import type { GeoHit, Handlers, LodgingHit, TurnInput, View } from './types'
import { createJourney, loadJourney, mutateJourney, json } from '../journey'
export { JourneyError as ApiError } from '../journey'
export const createSession = async (experience: string | null, startWith: string | null) => { const j = await createJourney(experience, startWith); return { ...(j.result as View), id: j.id } }
export const getSession = async (id: string) => { const j = await loadJourney(id, 'trip'); return { ...(j.result as View), id: j.id } }
export const searchPlaces = (q: string) => fetch(`/api/harness/places?q=${encodeURIComponent(q)}`).then(json<{ id: string; name: string; category: string | null }[]>)
export async function sendTurn(id: string, input: TurnInput, h: Handlers): Promise<void> { await mutateJourney(id, 'trip', 'turn', input, h as Record<string, ((d: any) => void) | undefined>) }

// Logistics lookups (docs/AGENT_HARNESS.md): no journey needed.
export const geoSearch = (q: string, signal?: AbortSignal) => fetch(`/api/harness/geo?q=${encodeURIComponent(q)}`, { signal }).then(json<GeoHit[]>)
// the best stays as cards, before any place is chosen (no query): what the lodging question shows instead of a search box
export const lodgingTop = (n = 8, signal?: AbortSignal) => fetch(`/api/harness/lodging/suggest?q=&top=${n}`, { signal }).then(json<LodgingHit[]>)
export const lodgingSuggest = (q: string, signal?: AbortSignal) => fetch(`/api/harness/lodging/suggest?q=${encodeURIComponent(q)}`, { signal }).then(json<LodgingHit[]>)
