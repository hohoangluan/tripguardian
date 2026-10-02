import type { SearchInput } from '../tu/types'
import type { Action, ActResult, CompareResult, DecisionOutput, TurnHandlers, View, WhyNot } from './types'

const BASE = '/api/decision/sessions'

export class DecisionError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(`Decision API ${status}: ${detail}`)
  }
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = ''
    try {
      detail = ((await res.json()) as { error?: string }).error ?? ''
    } catch {
      /* not JSON */
    }
    throw new DecisionError(res.status, detail)
  }
  return res.json() as Promise<T>
}

const post = (url: string, body: unknown) =>
  fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const createDecision = (searchInput: SearchInput, tripSession: string | null) =>
  post(BASE, { search_input: searchInput, trip_session: tripSession }).then((r) => json<{ id: string; view: View }>(r))

export const loadDecision = (id: string) => fetch(`${BASE}/${id}`).then((r) => json<{ id: string; view: View }>(r))

export const act = (id: string, a: Action) => post(`${BASE}/${id}/act`, a).then((r) => json<ActResult>(r))

export const compare = (id: string, a: string, b: string) =>
  fetch(`${BASE}/${id}/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`).then((r) => json<CompareResult>(r))

export const whyNot = (id: string, place: string) =>
  fetch(`${BASE}/${id}/why-not/${encodeURIComponent(place)}`).then((r) => json<WhyNot>(r))

export const confirm = (id: string) => post(`${BASE}/${id}/confirm`, {}).then((r) => json<DecisionOutput>(r))

// POST + server-sent events: EventSource cannot POST, so the stream is read by hand (as in tu/api.ts).
export async function sendText(id: string, text: string, h: TurnHandlers): Promise<void> {
  const res = await post(`${BASE}/${id}/turn`, { text })
  if (!res.ok || !res.body) throw new DecisionError(res.status, '')
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += value
    let cut: number
    while ((cut = buf.indexOf('\n\n')) >= 0) {
      dispatch(buf.slice(0, cut), h)
      buf = buf.slice(cut + 2)
    }
  }
}

function dispatch(block: string, h: TurnHandlers) {
  let event = 'message'
  let data = ''
  for (const line of block.split('\n')) {
    if (line.startsWith('event: ')) event = line.slice(7)
    else if (line.startsWith('data: ')) data += line.slice(6)
  }
  if (!data) return
  const fn = (h as Record<string, ((d: unknown) => void) | undefined>)[event]
  fn?.(JSON.parse(data))
}
