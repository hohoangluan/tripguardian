// Local HTTP regression tests for public proxy isolation; no external services or secrets.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { createServer, request } from 'node:http'
import { test } from 'node:test'

test('public server blocks private files and handles interrupted upstream responses', async (t) => {
  const upstream = createServer((req, res) => {
    if (req.url === '/api/harness/interrupted') {
      res.writeHead(200, { 'Content-Type': 'text/event-stream' })
      res.write('event: say\ndata: {}\n\n')
      return setTimeout(() => res.socket.destroy(), 10)
    }
    res.setHeader('Content-Type', 'application/json')
    res.end(JSON.stringify(req.headers))
  })
  upstream.listen(0, '127.0.0.1')
  await once(upstream, 'listening')
  const reserve = createServer()
  reserve.listen(0, '127.0.0.1')
  await once(reserve, 'listening')
  const port = reserve.address().port
  await new Promise(resolve => reserve.close(resolve))
  const child = spawn(process.execPath, [new URL('../server.mjs', import.meta.url).pathname, String(port)], {
    env: { ...process.env, HARNESS_PORT: String(upstream.address().port) }, stdio: ['ignore', 'pipe', 'pipe'],
  })
  t.after(async () => {
    child.kill()
    await once(child, 'exit')
    upstream.closeAllConnections()
    await new Promise(resolve => upstream.close(resolve))
  })
  await Promise.race([once(child.stdout, 'data'), once(child, 'exit').then(() => { throw new Error('server exited') })])
  function call(path, headers = {}) {
    return new Promise((resolve, reject) => {
      const req = request({ host: '127.0.0.1', port, path, headers }, res => {
        const chunks = []
        res.on('data', chunk => chunks.push(chunk))
        res.on('end', () => resolve({ status: res.statusCode, body: Buffer.concat(chunks).toString() }))
        res.on('error', reject)
      })
      req.on('error', reject)
      req.setTimeout(2000, () => req.destroy(new Error('timeout')))
      req.end()
    })
  }
  for (const path of ['/.env', '/.git/config', '/assets/app.js.map', '/admin', '/api/trip/sessions', '/%2e%2e/etc/passwd']) {
    assert.equal((await call(path)).status, 404, path)
  }
  assert.equal((await call('/%zz')).status, 400)
  const forwarded = JSON.parse((await call('/api/harness/headers', {
    'x-tg-client-ip': '9.9.9.9', 'x-forwarded-for': '9.9.9.9', 'cf-connecting-ip': '1.2.3.4',
  })).body)
  assert.equal(forwarded['x-tg-client-ip'], '1.2.3.4')
  assert.equal(forwarded['x-forwarded-for'], undefined)
  assert.equal(forwarded['cf-connecting-ip'], undefined)
  // Every interrupted SSE must close promptly and return its slot, even after more than the 64-slot quota.
  for (let i = 0; i < 65; i++) {
    await assert.rejects(call('/api/harness/interrupted'), /aborted|reset|closed/i)
  }
  assert.equal((await call('/api/harness/headers')).status, 200)
})
