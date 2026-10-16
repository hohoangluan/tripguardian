// Isolated browser fixtures verify the chat workspace without model or database calls.
import assert from 'node:assert/strict'
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { chromium } from 'playwright-core'

const base = process.argv[2] ?? 'http://127.0.0.1:5173'
const out = resolve(import.meta.dirname, '../../frontend_images')
mkdirSync(out, { recursive: true })
const required = ['trip', 'companions', 'mobility', 'care', 'pace', 'budget', 'lodging'].map(key => ({ key, label: key === 'lodging' ? 'chỗ ở' : key, done: false }))
const empty = () => ({ required, readback: null, purpose: null, trip: [], anchors: [], hard: [], soft: [], pace: null, max_leg_min: null, crowd_tolerance: null, novelty: null, budget_vnd: null, unknowns: [], unmapped: [], safety_pending: false, ready: false, missing: [], matching: 3208, total: 3208, board: { ids: [], vibe: [] }, vibes: [] })
const browser = await chromium.launch({ executablePath: resolve(import.meta.dirname, '../../.cache/ms-playwright/chromium-1169/chrome-linux/chrome'), args: ['--no-sandbox'] })
try {
  const page = await browser.newPage({ viewport: { width: 1680, height: 940 }, reducedMotion: 'reduce' })
  const errors = []
  page.on('pageerror', e => errors.push(e.message))
  const sessions = new Map()
  const turns = []
  let failSession = false
  let failHistory = false
  const make = id => ({ id, stage: 'trip', revision: 0, sessions: {}, outputs: {}, result: { id, transcript: [], card: null, phase: 'chat', understanding: empty() } })
  sessions.set('existing', make('existing'))
  sessions.get('existing').result.transcript = [{ role: 'user', text: 'Mình muốn đi cùng gia đình', turn: 1 }]
  const summaries = () => [...sessions.keys()].map(id => ({ id, stage: 'trip', revision: 0, days: id === 'existing' ? 5 : null, title: id === 'existing' ? 'Mình muốn đi cùng gia đình' : null, people: null, start_date: null, places: [], confirmed: false }))
  await page.route('**/data/*.json', r => r.fulfill({ json: { places: [], stats: {} } }))
  await page.route('**/api/**', async route => {
    const req = route.request()
    const url = new URL(req.url())
    const path = url.pathname
    if (path === '/api/harness/me') return route.fulfill({ json: { id: 'workspace-test', name: 'Ngọc Hương', guest: false, needs_consent: false, consents: {} } })
    if (path === '/api/harness/trips') return route.fulfill({ status: failHistory ? 503 : 200, json: failHistory ? {} : summaries() })
    if (path === '/api/harness/sessions' && req.method() === 'POST') {
      const id = `new-${sessions.size}`
      sessions.set(id, make(id))
      return route.fulfill({ json: sessions.get(id) })
    }
    const match = path.match(/^\/api\/harness\/sessions\/([^/]+)(\/request)?$/)
    if (match) {
      if (failSession) return route.fulfill({ status: 503, json: {} })
      const journey = sessions.get(match[1])
      if (!journey) return route.fulfill({ status: 404, json: {} })
      if (!match[2]) return route.fulfill({ json: journey })
      const input = req.postDataJSON()
      turns.push(input.payload)
      journey.revision++
      const u = empty()
      u.required = required.map(g => ({ ...g, done: g.key === 'lodging' }))
      u.trip = [{ target: 'days', value: 3, mark: false }, { target: 'lodging', value: { text: 'Khách sạn đã đặt', lat: 11.94, lng: 108.44 }, mark: false }]
      journey.result.understanding = u
      const events = [['say', { delta: 'Mình đã ghi nhận chuyến đi của bạn.' }], ['state', { understanding: u }], ['done', { search_input: null }], ['journey', journey]]
      return route.fulfill({ contentType: 'text/event-stream', body: events.map(([event, data]) => `data: ${JSON.stringify({ event, data, stage: input.stage, revision: journey.revision, request_id: input.request_id })}\n\n`).join('') })
    }
    return route.fulfill({ json: {} })
  })
  await page.goto(base + '/app/understand')
  await page.getByRole('heading', { name: /Chào Ngọc Hương/ }).waitFor({ timeout: 20000 }).catch(async error => {
    console.error('Workspace diagnostic:', errors, await page.locator('body').innerText())
    await page.screenshot({ path: resolve(out, 'understand-error.png') })
    throw error
  })
  await page.getByRole('heading', { name: 'Lịch sử chat' }).waitFor()
  await page.getByRole('heading', { name: 'Những nơi đang hợp' }).waitFor()
  assert.equal(await page.locator('.tg-cx__steps2 > li').count(), 7)
  assert.equal(await page.getByRole('progressbar').getAttribute('aria-valuenow'), '0')
  await page.screenshot({ path: resolve(out, 'understand-welcome.png') })
  await page.getByRole('textbox', { name: 'Tìm trong lịch sử' }).fill('gia đình')
  assert.equal(await page.locator('.tg-history__entry').count(), 1)
  await page.locator('.tg-history__entry').click()
  await page.getByText('Mình muốn đi cùng gia đình', { exact: true }).waitFor()
  assert.equal(await page.getByRole('heading', { name: /Chào Ngọc Hương/ }).count(), 0)
  await page.getByRole('button', { name: 'Tạo chuyến đi mới' }).click()
  await page.getByRole('heading', { name: /Chào Ngọc Hương/ }).waitFor()
  await page.getByRole('textbox', { name: 'Tìm trong lịch sử' }).fill('không có chuyến này')
  await page.getByText('Không tìm thấy chuyến phù hợp.', { exact: true }).waitFor()
  await page.getByRole('textbox', { name: 'Tìm trong lịch sử' }).fill('')
  await page.getByRole('textbox', { name: 'Tin nhắn' }).fill('3 ngày, mình đã đặt khách sạn')
  await page.getByRole('textbox', { name: 'Tin nhắn' }).press('Enter')
  await page.getByText('Mình đã ghi nhận chuyến đi của bạn.', { exact: true }).waitFor()
  assert.equal(await page.locator('.tg-cx__steps2 > li').count(), 7)
  assert.equal(await page.locator('.tg-cx__steps2 > .is-done').count(), 1)
  assert.equal(await page.getByRole('progressbar').getAttribute('aria-valuenow'), '14')
  await page.getByRole('button', { name: 'Sửa chỗ ở' }).click()
  await page.getByRole('dialog').waitFor()
  await page.keyboard.press('Escape')
  await page.getByRole('dialog').waitFor({ state: 'hidden' })
  await page.locator('.tg-cx__composer input[type=file]').first().setInputFiles({ name: 'places.txt', mimeType: 'text/plain', buffer: Buffer.from('Hồ Xuân Hương') })
  await page.getByRole('button', { name: 'Bỏ places.txt' }).waitFor()
  await page.getByRole('button', { name: 'Bỏ places.txt' }).click()
  assert.equal(await page.getByRole('button', { name: 'Bỏ places.txt' }).count(), 0)
  await page.getByRole('button', { name: 'Tiếp tục đến chọn nơi' }).click()
  await page.waitForFunction(() => !document.querySelector('.tg-cx__m[aria-busy="true"]'))
  assert.equal(turns.at(-1).kind, 'show')
  await page.screenshot({ path: resolve(out, 'understand-chat.png') })
  for (const width of [1680, 1440, 1024]) {
    await page.setViewportSize({ width, height: 940 })
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `No overflow at ${width}`)
    const composer = await page.locator('.tg-cx__pill').boundingBox()
    assert.ok(composer && composer.y >= 0 && composer.y + composer.height <= 940, `Composer visible at ${width}`)
    await page.screenshot({ path: resolve(out, `understand-${width}.png`) })
  }
  failHistory = true
  await page.reload()
  await page.getByText('Chưa tải được lịch sử.', { exact: true }).waitFor()
  failHistory = false
  await page.locator('.tg-history').getByRole('button', { name: 'Thử lại' }).click()
  await page.locator('.tg-history__entry').first().waitFor()
  failSession = true
  await page.reload()
  await page.getByRole('heading', { name: 'Chưa kết nối được trợ lý' }).waitFor()
  assert.equal(await page.getByRole('navigation', { name: 'Điều hướng chính' }).count(), 1)
  assert.equal(await page.locator('.tg-flowbar').count(), 0)
  failSession = false
  await page.locator('.tg-workspace__state').getByRole('button', { name: 'Thử lại' }).click()
  await page.getByRole('textbox', { name: 'Tin nhắn' }).waitFor()
  assert.deepEqual(errors, [])
  console.log('Understand workspace: greeting, history/search/retry, switching, new journey, SSE, editing, attachments, show action, backend-required progress, offline recovery and desktop layouts passed')
} finally {
  await browser.close()
}
