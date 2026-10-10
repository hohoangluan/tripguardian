import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
// Compile journey.ts with tsc into this path before running this test.
const source = readFileSync(process.env.JOURNEY_JS ?? '/tmp/tg-journey/journey.js', 'utf8')
let moduleId = 0
const client = () => import(`data:text/javascript;base64,${Buffer.from(source + `\n// ${moduleId++}`).toString('base64')}`)
const storage = new Map()
globalThis.localStorage = { getItem: k => storage.get(k) ?? null, setItem: (k,v) => storage.set(k,v), removeItem: k => storage.delete(k) }
const view = (revision = 0, stage = 'decision') => ({ id: 'journey', stage, revision, sessions: {}, outputs: {}, result: {} })
const response = v => Response.json(v)
test('lost response retries identical request and revision, then clears pending receipt', async () => {
  const api = await client(); const requests = []
  globalThis.fetch = async (_url, options) => {
    if (!options) return response(view())
    const req = JSON.parse(options.body); requests.push(req)
    if (requests.length === 1) throw new TypeError('connection lost after commit')
    return response(view(1))
  }
  await api.mutateJourney('lost', 'decision', 'act', { type: 'select', id: 'place' })
  assert.equal(requests.length, 2); assert.deepEqual(requests[0], requests[1]); assert.equal(storage.has('tg.journey.pending.lost'), false)
})
test('browser restart recovers persisted request before a different mutation', async () => {
  const previous = { request_id: 'stable', stage: 'decision', operation: 'act', expected_revision: 0, payload: {type:'select'} }
  storage.set('tg.journey.pending.restart', JSON.stringify(previous))
  const api = await client(); const requests = []
  globalThis.fetch = async (_url, options) => {
    if (!options) return response(view(1))
    requests.push(JSON.parse(options.body)); return response(view(requests.length))
  }
  await api.mutateJourney('restart', 'decision', 'act', {type:'lock'})
  assert.deepEqual(requests[0], previous); assert.equal(requests[1].expected_revision, 1)
})
test('concurrent mutations use committed revisions in order', async () => {
  const api = await client(); let revision = 0; const requests = []
  globalThis.fetch = async (_url, options) => {
    if (!options) return response(view(revision))
    requests.push(JSON.parse(options.body)); await new Promise(r => setTimeout(r, 5)); return response(view(++revision))
  }
  await Promise.all([api.mutateJourney('queue', 'decision', 'act', {a:1}), api.mutateJourney('queue', 'decision', 'act', {a:2})])
  assert.deepEqual(requests.map(r => r.expected_revision), [0,1])
})
test('stream filters wrong request/stage/revision and waits for final receipt', async () => {
  const api = await client(); const events = []
  globalThis.fetch = async (_url, options) => {
    if (!options) return response(view(0,'trip'))
    const req = JSON.parse(options.body)
    const envelope = (event, data, extra = {}) => `event: event\ndata: ${JSON.stringify({request_id:req.request_id, stage:'trip', revision:1, event, data, ...extra})}\n\n`
    return new Response(envelope('say',{delta:'bad'},{request_id:'old'}) + envelope('say',{delta:'bad'},{stage:'decision'}) + envelope('say',{delta:'bad'},{revision:3}) + envelope('done',{search_input:{}}) + envelope('journey',view(1,'trip')), {headers:{'Content-Type':'text/event-stream'}})
  }
  const result = await api.mutateJourney('stream','trip','turn',{}, {say:d=>events.push(d),done:d=>events.push(d)})
  assert.deepEqual(events,[{search_input:{}}]); assert.equal(result.revision,1)
})
test('earlier stage is entered through explicit back; later stage never auto advances', async () => {
  const api = await client(); const operations = []
  globalThis.fetch = async (_url, options) => { if (!options) return response(view(2,'planning')); const req=JSON.parse(options.body);operations.push(req.operation);return response(view(3,'decision')) }
  await api.enterStage('back','decision'); assert.deepEqual(operations,['back'])
  globalThis.fetch = async () => response(view(0,'trip'))
  await assert.rejects(api.mutateJourney('no-advance','decision','act',{}), e=>e.status===409)
})
test('resume recovers pending advance before reading its destination without backing away', async () => {
  const req = { request_id: 'handoff', stage: 'trip', operation: 'advance', expected_revision: 0, payload: {} }
  storage.set('tg.journey.pending.resume-advance', JSON.stringify(req))
  const api = await client(); const calls = []; let current = view(0, 'trip')
  globalThis.fetch = async (_url, options) => {
    if (options) { calls.push(JSON.parse(options.body).operation); current = view(1, 'decision') }
    else calls.push('read')
    return response(current)
  }
  const recovered = await api.resumeJourney('resume-advance')
  assert.equal(recovered.recoveredOperation, 'advance')
  assert.equal(recovered.view.stage, 'decision')
  assert.deepEqual(calls, ['advance', 'read'])
})
test('resume reads updated Trip turn and its compiled output after pending receipt recovery', async () => {
  const req = { request_id: 'compiled', stage: 'trip', operation: 'turn', expected_revision: 0, payload: {kind:'show'} }
  storage.set('tg.journey.pending.resume-turn', JSON.stringify(req))
  const api = await client(); let current = view(0, 'trip'); const calls = []
  globalThis.fetch = async (_url, options) => {
    if (options) {
      calls.push('turn')
      current = { ...view(1, 'trip'), result: {understanding:{days:3}}, outputs:{trip:{context:{days:3}}} }
    } else calls.push('read')
    return response(current)
  }
  const recovered = await api.resumeJourney('resume-turn')
  assert.equal(recovered.recoveredOperation, 'turn')
  assert.deepEqual(recovered.view.outputs.trip, {context:{days:3}})
  assert.deepEqual(recovered.view.result.understanding, {days:3})
  assert.deepEqual(calls, ['turn', 'read'])
})
test('lodging revision watermark follows both reads and mutation receipts', async () => {
  const api = await client(); let revision = 5
  globalThis.fetch = async (_url, options) => response(view(options ? ++revision : revision, 'planning'))
  await api.loadJourney('journey')
  assert.equal(api.acceptsRevision('journey', 4), false)
  assert.equal(api.acceptsRevision('journey', 5), true)
  await api.mutateJourney('journey', 'planning', 'act', {type:'pick_variant',id:'baseline'})
  assert.equal(api.acceptsRevision('journey', 5), false)
  assert.equal(api.acceptsRevision('journey', 6), true)
  revision = 2
  await api.loadJourney('journey')
  assert.equal(api.acceptsRevision('journey', 5), false)
})
test('navigation suppresses late streamed handoff callbacks while preserving the receipt', async () => {
  const api = await client(); const callbacks = []
  globalThis.location = {pathname:'/app/understand',search:''}
  globalThis.fetch = async (_url, options) => {
    if (!options) return response(view(0, 'trip'))
    const req = JSON.parse(options.body)
    const envelope = (event, data) => `event: event\ndata: ${JSON.stringify({request_id:req.request_id,stage:'trip',revision:1,event,data})}\n\n`
    return new Response(new ReadableStream({start(controller) {
      globalThis.location.pathname = '/app/home'
      controller.enqueue(new TextEncoder().encode(envelope('say',{delta:'late'}) + envelope('done',{search_input:{}}) + envelope('journey',view(1,'trip'))))
      controller.close()
    }}))
  }
  try {
    const result = await api.mutateJourney('navigated', 'trip', 'turn', {}, {say:d=>callbacks.push(d),done:d=>callbacks.push(d)})
    assert.deepEqual(callbacks, [])
    assert.equal(result.revision, 1)
  } finally { delete globalThis.location }
})
test('SSE stale revision clears its pending request and permits a fresh mutation', async () => {
  const api = await client(); let revision = 0; const requests = []
  globalThis.fetch = async (_url, options) => {
    if (!options) return response(view(revision, 'trip'))
    const req = JSON.parse(options.body); requests.push(req)
    if (requests.length === 1) {
      revision = 1
      return new Response(`event: event\ndata: ${JSON.stringify({request_id:req.request_id,stage:'trip',revision:0,event:'error',data:{status:409,message:'stale revision'}})}\n\n`)
    }
    return response(view(2, 'trip'))
  }
  await assert.rejects(api.mutateJourney('stale', 'trip', 'turn', {kind:'show'}, {}), e=>e.status===409)
  assert.equal(storage.has('tg.journey.pending.stale'), false)
  await api.mutateJourney('stale', 'trip', 'turn', {kind:'show'})
  assert.equal(requests[1].expected_revision, 1)
  assert.notEqual(requests[0].request_id, requests[1].request_id)
})
test('explicit stage entry is scoped to one journey and consumed once without surviving reload', async () => {
  const api = await client()
  api.requestStageEntry('explicit', 'trip')
  assert.equal(api.consumeStageEntry('other'), undefined)
  assert.equal(api.consumeStageEntry('explicit'), 'trip')
  assert.equal(api.consumeStageEntry('explicit'), undefined)
  api.requestStageEntry('explicit', 'trip')
  const restarted = await client()
  assert.equal(restarted.consumeStageEntry('explicit'), undefined)
})

// ---- shared journey cache (key `${journey}:${stage}`; see journey.ts) ----
test('cache: hit is fresh for CACHE_FRESH_MS, then stale but still served', async () => {
  const api = await client(); const realNow = Date.now; let now = 1_000_000
  Date.now = () => now
  try {
    api.cachePut('c1', 'planning', { v: 1 })
    assert.deepEqual(api.cacheGet('c1', 'planning'), { value: { v: 1 }, fresh: true })
    assert.equal(api.cacheGet('c1', 'decision'), undefined) // the stage is part of the key
    assert.equal(api.cacheGet('other', 'planning'), undefined) // so is the journey
    now += api.CACHE_FRESH_MS + 1
    assert.equal(api.cacheGet('c1', 'planning').fresh, false)
  } finally { Date.now = realNow }
})
test('cache: any mutation (act, confirm, back...) empties that journey only, and a failed one too', async () => {
  const api = await client(); let fail = false
  globalThis.fetch = async (_url, options) => {
    if (!options) return response(view(0, 'planning'))
    if (fail) return new Response(JSON.stringify({ error: 'bad act' }), { status: 400 })
    return response(view(1, 'planning'))
  }
  api.cachePut('m1', 'planning', { v: 1 }); api.cachePut('m1', 'decision', { v: 2 }); api.cachePut('m2', 'planning', { v: 3 })
  await api.mutateJourney('m1', 'planning', 'act', { type: 'pick_variant', id: 'x' })
  assert.equal(api.cacheGet('m1', 'planning'), undefined)
  assert.equal(api.cacheGet('m1', 'decision'), undefined)
  assert.deepEqual(api.cacheGet('m2', 'planning').value, { v: 3 })
  api.cachePut('m1', 'planning', { v: 4 }) // the caller stores the answer of its own mutation
  assert.deepEqual(api.cacheGet('m1', 'planning').value, { v: 4 })
  fail = true
  await assert.rejects(api.mutateJourney('m1', 'planning', 'act', { type: 'pick_variant', id: 'y' }))
  assert.equal(api.cacheGet('m1', 'planning'), undefined)
})
test('cache: a read that began before an edit cannot store its old answer', async () => {
  const api = await client()
  globalThis.fetch = async (_url, options) => response(view(options ? 1 : 0, 'planning'))
  const epoch = api.cacheEpoch('r1') // the read starts here ...
  await api.mutateJourney('r1', 'planning', 'act', { type: 'unpick' }) // ... an edit lands ...
  api.cachePut('r1', 'planning', { old: true }, epoch) // ... the slow read answers
  assert.equal(api.cacheGet('r1', 'planning'), undefined)
  api.cachePut('r1', 'planning', { fresh: true }, api.cacheEpoch('r1'))
  assert.deepEqual(api.cacheGet('r1', 'planning').value, { fresh: true })
})
test('cache: while a mutation is queued or running nothing is served or stored', async () => {
  const api = await client(); let release
  globalThis.fetch = async (_url, options) => { if (!options) return response(view(0, 'planning')); await new Promise((r) => { release = r }); return response(view(1, 'planning')) }
  api.cachePut('q1', 'planning', { v: 1 })
  const running = api.mutateJourney('q1', 'planning', 'act', {})
  await new Promise((r) => setTimeout(r, 5))
  assert.equal(api.cacheGet('q1', 'planning'), undefined)
  api.cachePut('q1', 'planning', { stale: true })
  release(); await running
  assert.equal(api.cacheGet('q1', 'planning'), undefined) // the stale put was refused
})
test('cache: sign-out or another account empties everything; the first bind only records who signed in', async () => {
  const api = await client()
  api.bindCacheAccount('alice')
  api.cachePut('s1', 'planning', { v: 1 })
  api.bindCacheAccount('alice')
  assert.ok(api.cacheGet('s1', 'planning'))
  api.bindCacheAccount(null)
  assert.equal(api.cacheGet('s1', 'planning'), undefined)
  api.cachePut('s1', 'planning', { v: 2 })
  api.bindCacheAccount('bob')
  assert.equal(api.cacheGet('s1', 'planning'), undefined)
})
