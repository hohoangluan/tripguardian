import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { execFileSync } from 'node:child_process'
const dir = mkdtempSync(join(tmpdir(), 'tg-preview-'))
try {
  execFileSync(process.execPath, ['node_modules/typescript/bin/tsc', 'src/user/pd/previewQueue.ts', '--ignoreConfig', '--target', 'ES2022', '--module', 'ES2022', '--outDir', dir])
  const source = readFileSync(join(dir, 'previewQueue.js'), 'utf8')
  const { PreviewQueue, previewKey } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`)
  const pause = () => new Promise(r => setTimeout(r, 5))
  test('in-flight preview is followed only by the latest selection', async () => {
    const queue = new PreviewQueue(0)
    const results = [], calls = []
    let finish
    queue.request('a', () => { calls.push('a'); return new Promise(r => { finish = r }) }, r => results.push(r), () => {})
    await pause()
    queue.request('b', async () => { calls.push('b'); return 'b' }, r => results.push(r), () => {})
    queue.request('c', async () => { calls.push('c'); return 'c' }, r => results.push(r), () => {})
    await pause()
    assert.deepEqual(calls, ['a'])
    finish('a')
    await pause()
    assert.deepEqual(calls, ['a', 'c'])
    assert.deepEqual(results, ['c'])
    queue.cancel()
  })
  test('cancel prevents stale completion and cancels a pending request', async () => {
    const queue = new PreviewQueue(0)
    let finish
    const results = [], calls = []
    queue.request('a', () => new Promise(r => { finish = r }), r => results.push(r), () => {})
    await pause()
    queue.request('b', async () => { calls.push('b'); return 'b' }, r => results.push(r), () => {})
    queue.cancel()
    finish('a')
    await pause()
    assert.deepEqual(results, [])
    assert.deepEqual(calls, [])
  })
  test('duplicate dependency keys do not refetch a completed preview', async () => {
    const queue = new PreviewQueue(0)
    const calls = []
    queue.request('a', async () => { calls.push(1); return 'a' }, () => {}, () => {})
    await pause()
    queue.request('a', async () => { calls.push(1); return 'a' }, () => {}, () => {})
    await pause()
    assert.deepEqual(calls, [1])
    queue.cancel()
  })
  test('debounce sends only the latest dependency set', async () => {
    const queue = new PreviewQueue(15)
    const calls = []
    queue.request('a', async () => { calls.push('a'); return 'a' }, () => {}, () => {})
    queue.request('b', async () => { calls.push('b'); return 'b' }, () => {}, () => {})
    await new Promise(r => setTimeout(r, 25))
    assert.deepEqual(calls, ['b'])
    queue.cancel()
  })
  test('a failed preview can retry the same dependencies', async () => {
    const queue = new PreviewQueue(0)
    const errors = [], results = []
    queue.request('a', async () => { throw new Error('offline') }, () => {}, e => errors.push(e.message))
    await pause()
    queue.request('a', async () => 'ready', r => results.push(r), () => {})
    await pause()
    assert.deepEqual(errors, ['offline'])
    assert.deepEqual(results, ['ready'])
    queue.cancel()
  })
  test('cancel and reenter never accept the previous stage response', async () => {
    const queue = new PreviewQueue(0)
    const results = [], calls = []
    let finish
    queue.request('a', () => new Promise(r => { finish = r }), r => results.push(r), () => {})
    await pause()
    queue.cancel()
    queue.request('a', async () => { calls.push('new'); return 'new' }, r => results.push(r), () => {})
    await pause()
    assert.deepEqual(calls, [])
    finish('old')
    await pause()
    assert.deepEqual(results, ['new'])
    assert.deepEqual(calls, ['new'])
    queue.cancel()
  })
  test('preview key includes places, locks and constraints with stable object ordering', () => {
    assert.equal(previewKey('j', ['a', 'b'], [], {days: 2, hard: {x: 1, y: 2}}), previewKey('j', ['b', 'a'], [], {hard: {y: 2, x: 1}, days: 2}))
    const key = previewKey('j', ['a'], [], {days: 2})
    assert.notEqual(key, previewKey('j', ['b'], [], {days: 2}))
    assert.notEqual(key, previewKey('j', ['a'], ['a'], {days: 2}))
    assert.notEqual(key, previewKey('j', ['a'], [], {days: 3}))
    assert.notEqual(key, previewKey('k', ['a'], [], {days: 2}))
  })
} finally {
  rmSync(dir, { recursive: true, force: true })
}
