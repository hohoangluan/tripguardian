import type { GeoHit, Handlers, LodgingHit, TransitParams, TransitResult, TurnInput, View } from './types'
import { createJourney, loadJourney, mutateJourney, json } from '../journey'
export { JourneyError as ApiError } from '../journey'
export const createSession = async (experience: string | null, startWith: string | null) => { const j = await createJourney(experience, startWith); return { ...(j.result as View), id: j.id } }
export const getSession = async (id: string) => { const j = await loadJourney(id, 'trip'); return { ...(j.result as View), id: j.id } }
export const searchPlaces = (q: string) => fetch(`/api/harness/places?q=${encodeURIComponent(q)}`).then(json<{ id: string; name: string; category: string | null }[]>)
export async function sendTurn(id: string, input: TurnInput, h: Handlers): Promise<void> { await mutateJourney(id, 'trip', 'turn', input, h as Record<string, ((d: any) => void) | undefined>) }

// Logistics lookups (docs/AGENT_HARNESS.md): no journey needed.
export const geoSearch = (q: string, signal?: AbortSignal) => fetch(`/api/harness/geo?q=${encodeURIComponent(q)}`, { signal }).then(json<GeoHit[]>)
export const lodgingSuggest = (q: string, signal?: AbortSignal) => fetch(`/api/harness/lodging/suggest?q=${encodeURIComponent(q)}`, { signal }).then(json<LodgingHit[]>)
const transitQuery = (p: TransitParams) =>
  new URLSearchParams({ mode: p.mode, from: p.from, to: p.to, date: p.date, ...(p.lat != null && p.lng != null ? { lat: String(p.lat), lng: String(p.lng) } : {}) }).toString()
export const findTransit = (p: TransitParams) => fetch(`/api/harness/transit?${transitQuery(p)}`).then(json<TransitResult>)
// A route missing from the cache is crawled live; the stream pushes one result when it is done.
export function watchTransit(p: TransitParams, onResult: (r: TransitResult) => void) {
  const es = new EventSource(`/api/harness/transit/events?${transitQuery(p)}`)
  let active = true
  const forward = (ev: MessageEvent) => {
    if (!active || !ev.data) return
    const d = JSON.parse(ev.data)
    const r = (d && 'status' in d ? d : d?.data) as TransitResult | undefined
    if (r && 'status' in r && r.status !== 'pending') { active = false; es.close(); onResult(r) }
  }
  es.addEventListener('event', forward as EventListener)
  es.onmessage = forward
  es.onerror = () => { es.close(); if (active) onResult({ status: 'unavailable', trips: [], book_url: null }) }
  return () => { active = false; es.close() }
}
