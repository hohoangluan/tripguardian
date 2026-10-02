import type { Handlers, TurnInput, View } from './types'

const BASE = '/api/trip'

export class ApiError extends Error {
  constructor(public status: number) {
    super(`Trip API ${status}`)
  }
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new ApiError(res.status)
  return res.json() as Promise<T>
}

export const createSession = (experience: string | null, startWith: string | null) =>
  fetch(`${BASE}/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ experience, start_with: startWith }),
  }).then((r) => json<View>(r))

export const getSession = (id: string) => fetch(`${BASE}/sessions/${id}`).then((r) => json<View>(r))

export const searchPlaces = (q: string) =>
  fetch(`${BASE}/places?q=${encodeURIComponent(q)}`).then((r) => json<{ id: string; name: string; category: string | null }[]>(r))

// POST + server-sent events: EventSource cannot POST, so the stream is read by hand.
export async function sendTurn(id: string, input: TurnInput, h: Handlers): Promise<void> {
  const res = await fetch(`${BASE}/sessions/${id}/turn`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (!res.ok || !res.body) throw new ApiError(res.status)
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

function dispatch(block: string, h: Handlers) {
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
