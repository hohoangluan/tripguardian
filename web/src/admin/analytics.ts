// Private analytics server (`python -m analytics serve`, src/analytics; docs/ANALYTICS.md). Vite proxies /api/analytics.
import { useEffect, useState } from 'react'

export type Filters = { from?: string; to?: string; start_with?: string; app_version?: string }
export type Step = { key: string; label: string; journeys: number; kept: number | null; median_min: number | null; stopped: number; last_before_stop: [string, number][] }
export type Funnel = { range: [string, string]; top: { landing: number; cta: number; logins: number }; steps: Step[] }
export type DecisionNums = {
  acts: { action: string; n: number }[]
  drop_reasons: { reason: string; n: number }[]
  previews: { status: string; n: number }[]
  counts: { page_more: number; why_not: number; compare_open: number; outbound_click: number }
  ranks: { rank: number; shown: number; chosen: number }[]
  search_misses: { q: string; n: number }[]
  acts_per_journey_median: number | null
}
export type SessionRow = { id: string; stage: string; revision: number; created_at: string; updated_at: string; app_version: string | null; email: string | null; display_name: string | null; errors: number; min_score: number | null; confirmed: boolean; start_with: string | null }
export type Event = { at: string; source: string; name: string; props: Record<string, unknown>; app_version: string | null }
export type SessionDetail = {
  id: string; stage: string; revision: number; created_at: string; updated_at: string; app_version: string | null; email: string | null; name: string | null
  trip_transcript: { role: string; text: string; turn: number }[]
  decision_log: { action: Record<string, unknown>; at?: string }[]
  planning_log: { action: Record<string, unknown>; at?: string }[]
  receipts: { request_id: string; at: string | null; revision: number; stage: string; events: string[] }[]
  outputs: string[]; events: Event[]; feedback: { at: string; scores: Record<string, number>; more_search: boolean | null; note: string }[]
}
export type Today = { day: string; journeys: number; confirmed: number; feedback: number; errors: number; fallbacks: number; active_users: number; new_users: number }

const qs = (f: Record<string, string | undefined>) => {
  const p = new URLSearchParams(Object.entries(f).filter((e): e is [string, string] => !!e[1]))
  return p.size ? `?${p}` : ''
}

export async function get<T>(path: string, f: Record<string, string | undefined> = {}): Promise<T> {
  const res = await fetch(`/api/analytics/${path}${qs(f)}`)
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error ?? `HTTP ${res.status}`)
  return res.json()
}

// { data, error } for one analytics read; reloads when `key` changes.
export function useAnalytics<T>(path: string, f: Record<string, string | undefined> = {}) {
  const key = path + qs(f)
  const [state, setState] = useState<{ key: string; data?: T; error?: string }>({ key })
  useEffect(() => {
    let live = true
    get<T>(path, f).then((data) => live && setState({ key, data }), (e: Error) => live && setState({ key, error: e.message }))
    return () => { live = false }
  }, [key]) // eslint-disable-line react-hooks/exhaustive-deps
  return state.key === key ? state : { key }
}

export const fmtTime = (s: string | null | undefined) => (s ? new Date(s).toLocaleString('vi-VN', { dateStyle: 'short', timeStyle: 'short' }) : '—')
export const pct = (x: number | null) => (x == null ? '—' : `${Math.round(x * 100)}%`)
