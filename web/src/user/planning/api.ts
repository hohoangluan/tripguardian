import type { Action, ActResult, PlanOutput, ProgressEvent, TurnHandlers, View } from './types'

const BASE = '/api/planning/sessions'

export class PlanningError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(`Planning API ${status}: ${detail}`)
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
    throw new PlanningError(res.status, detail)
  }
  return res.json() as Promise<T>
}

const post = (url: string, body: unknown) =>
  fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const createPlanning = (decisionOutput: unknown) =>
  post(BASE, { decision_output: decisionOutput }).then((r) => json<{ id: string; view: View }>(r))

export const loadPlanning = (id: string) => fetch(`${BASE}/${id}`).then((r) => json<{ id: string; view: View }>(r))

export const act = (id: string, a: Action) => post(`${BASE}/${id}/act`, a).then((r) => json<ActResult>(r))

export const confirm = (id: string) => post(`${BASE}/${id}/confirm`, {}).then((r) => json<PlanOutput>(r))

// POST + server-sent events: EventSource cannot POST, so the stream is read by hand (as in pd/api.ts, tu/api.ts).
export async function sendText(id: string, text: string, h: TurnHandlers): Promise<void> {
  const res = await post(`${BASE}/${id}/turn`, { text })
  if (!res.ok || !res.body) throw new PlanningError(res.status, '')
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

// GET + SSE: this route takes no body, so the native EventSource works (unlike /turn above).
export function watchLodging(id: string, onEvent: (e: { event: 'progress' | 'view' | 'done' | 'error'; data: unknown }) => void) {
  const es = new EventSource(`${BASE}/${id}/lodging/events`)
  const forward = (event: 'progress' | 'view' | 'done' | 'error') => (ev: MessageEvent) =>
    onEvent({ event, data: ev.data ? JSON.parse(ev.data) : null }) // a transport drop fires a bare error Event with no data
  es.addEventListener('progress', forward('progress') as EventListener)
  es.addEventListener('view', forward('view') as EventListener)
  es.addEventListener('done', forward('done') as EventListener)
  es.addEventListener('error', forward('error') as EventListener)
  es.onerror = () => es.close() // the server closes the stream itself once done/error fires; a transport drop just stops silently
  return () => es.close()
}

export type { ProgressEvent }
