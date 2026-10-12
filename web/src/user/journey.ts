export type Stage = 'trip' | 'decision' | 'planning'
export interface JourneyView { id: string; stage: Stage; revision: number; sessions: Partial<Record<Stage, string>>; outputs: Record<string, unknown>; result: unknown }
type Operation = 'turn' | 'act' | 'advance' | 'back' | 'confirm' | 'recommend'
interface Request { request_id: string; stage: Stage; operation: Operation; expected_revision: number; payload: unknown }
export class JourneyError extends Error {
  constructor(public status: number, public detail = '') { super(`Journey API ${status}: ${detail}`) }
}
const BASE = '/api/harness/sessions'
const queues = new Map<string, Promise<unknown>>()
const revisions = new Map<string, number>()
const stageEntries = new Map<string, Stage>()
export function requestStageEntry(id: string, stage: Stage) { stageEntries.set(id, stage) }
export function consumeStageEntry(id: string) {
  const stage = stageEntries.get(id)
  stageEntries.delete(id)
  return stage
}
function remember(view: JourneyView) {
  revisions.set(view.id, Math.max(revisions.get(view.id) ?? 0, view.revision))
  return view
}
export function acceptsRevision(id: string, revision: number) {
  return Number.isInteger(revision) && revision >= (revisions.get(id) ?? 0)
}
const pending = new Map<string, Request>()
const key = (id: string) => `tg.journey.pending.${id}`
function saved(id: string): Request | undefined {
  try { return pending.get(id) ?? JSON.parse(localStorage.getItem(key(id)) ?? 'null') ?? undefined } catch { return pending.get(id) }
}
function persist(id: string, req?: Request) {
  if (req) pending.set(id, req); else pending.delete(id)
  try { if (req) localStorage.setItem(key(id), JSON.stringify(req)); else localStorage.removeItem(key(id)) } catch { /* memory recovery remains available */ }
}
export async function json<T>(res: Response): Promise<T> {
  if (!res.ok) { const body = await res.json().catch(() => ({})); throw new JourneyError(res.status, body.error ?? '') }
  return res.json()
}
export const createJourney = (experience: string | null, start_with: string | null) => fetch(BASE, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ experience, start_with }) }).then(json<JourneyView>)
export const loadJourney = (id: string, stage?: Stage) => fetch(`${BASE}/${id}${stage ? `?stage=${stage}` : ''}`).then(json<JourneyView>).then(remember)
export const readJourney = <T>(id: string, path: string) => fetch(`${BASE}/${id}/read/${path}`).then(json<T>)
function serial<T>(id: string, run: () => Promise<T>): Promise<T> {
  const next = (queues.get(id) ?? Promise.resolve()).catch(() => {}).then(run)
  queues.set(id, next)
  return next
}
async function post(id: string, req: Request, handlers?: Record<string, ((data: any) => void) | undefined>): Promise<JourneyView> {
  const path = typeof location === 'undefined' ? '' : location.pathname + location.search
  const active = () => typeof location === 'undefined' || path === location.pathname + location.search
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const res = await fetch(`${BASE}/${id}/request`, { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: handlers ? 'text/event-stream' : 'application/json' }, body: JSON.stringify(req) })
      if (!handlers) return await json<JourneyView>(res)
      if (!res.ok) return await json<JourneyView>(res)
      if (!res.body) throw new Error('Missing stream')
      const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
      let buf = ''; let result: JourneyView | undefined
      for (;;) {
        const { value, done } = await reader.read()
        if (done) break
        buf += value
        let cut: number
        while ((cut = buf.indexOf('\n\n')) >= 0) {
          const block = buf.slice(0, cut); buf = buf.slice(cut + 2)
          const data = block.split('\n').filter(l => l.startsWith('data: ')).map(l => l.slice(6)).join('\n')
          if (!data) continue
          const e = JSON.parse(data)
          if (e.request_id !== req.request_id || e.stage !== req.stage || e.revision < req.expected_revision || e.revision > req.expected_revision + 1) continue
          if (e.event === 'journey') result = e.data
          else if (e.event === 'error') throw new JourneyError(e.data.status ?? 500, e.data.message)
          else if (active()) handlers[e.event]?.(e.data)
        }
      }
      if (!result) throw new Error('Stream ended without receipt')
      return result
    } catch (e) { if (e instanceof JourneyError || attempt === 1) throw e }
  }
  throw new Error('Missing receipt')
}
async function execute(id: string, req: Request, h?: Record<string, ((data: any) => void) | undefined>) {
  persist(id, req)
  try { const view = remember(await post(id, req, h)); persist(id); return view }
  catch (e) { if (e instanceof JourneyError && e.status < 500) persist(id); throw e }
}
async function recover(id: string) { const old = saved(id); if (old) await execute(id, old) }
export const resumeJourney = (id: string) => serial(id, async () => {
  const request = saved(id)
  await recover(id)
  return { view: await loadJourney(id), recoveredOperation: request?.operation }
})
async function stageReady(id: string, stage: Stage) {
  let current = await loadJourney(id)
  while (current.stage !== stage) {
    if (current.stage === 'trip' || (current.stage === 'decision' && stage === 'planning')) throw new JourneyError(409, 'Advance this journey explicitly first')
    current = await execute(id, { request_id: crypto.randomUUID(), stage: current.stage, operation: 'back', expected_revision: current.revision, payload: {} })
  }
  return current
}
export const enterStage = (id: string, stage: Stage) => serial(id, async () => { await recover(id); return stageReady(id, stage) })
export function mutateJourney(id: string, stage: Stage, operation: Operation, payload: unknown = {}, handlers?: Record<string, ((data: any) => void) | undefined>) {
  return serial(id, async () => {
    const old = saved(id)
    if (old && old.stage === stage && old.operation === operation && JSON.stringify(old.payload) === JSON.stringify(payload)) return execute(id, old, handlers)
    await recover(id)
    const current = await stageReady(id, stage)
    return execute(id, { request_id: crypto.randomUUID(), stage, operation, expected_revision: current.revision, payload }, handlers)
  })
}
