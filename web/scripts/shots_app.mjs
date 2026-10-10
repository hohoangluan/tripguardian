// Walks the user web against the real harness (landing -> Khám phá -> Hiểu chuyến đi -> Chọn nơi -> Lịch trình -> Phản hồi)
// and saves a screenshot per screen. Signs in through the harness test route (TG_TEST_LOGIN=1, APP_BASE_URL on http). The logistics questions take the flight path: origin Quận 1 -> Máy bay -> the first
// flight each way -> no lodging yet -> "Bạn ở đâu?" picks the first lodging before the schedule. Needs `python -m harness serve` and the Vite dev server running.
// usage: node web/scripts/shots_app.mjs [base url, default http://127.0.0.1:5173] [width, default 1440]
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { chromium } from 'playwright-core'

const BASE = process.argv[2] ?? 'http://127.0.0.1:5173'
const W = Number(process.argv[3] ?? 1440)
const OUT = resolve(import.meta.dirname, '../shots/app')
mkdirSync(OUT, { recursive: true })
// The headless shell hangs on the shared server; the full Chromium (new headless) does not.
const exe = resolve(import.meta.dirname, '../../.cache/ms-playwright/chromium-1169/chrome-linux/chrome')
const browser = await chromium.launch({ executablePath: exe })
const page = await browser.newPage({ viewport: { width: W, height: 900 } })
const errors = []
page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`))
page.on('console', (m) => { if (m.type() === 'error') errors.push(`console: ${m.text()}`) })
let n = 0
const shot = async (name) => { await page.waitForTimeout(600); await page.screenshot({ path: `${OUT}/${String(++n).padStart(2, '0')}-${name}.png`, fullPage: false }); console.log('shot', name) }
const step = (s) => console.log('·', s)

try {
  await page.goto(BASE + '/', { waitUntil: 'networkidle' })
  await shot('landing')
  await page.goto(BASE + '/app', { waitUntil: 'networkidle' })
  await shot('auth')
  // Google sign-in cannot run headless: the harness started with TG_TEST_LOGIN=1 (http base URL) signs in a test account.
  await page.goto(BASE + '/api/auth/test/login?email=walker@test.local&next=/app', { waitUntil: 'networkidle' })
  if (await page.locator('.tg-auth__check input').count()) {
    await shot('consent')
    await page.check('.tg-auth__check input')
    await page.getByRole('button', { name: /Bắt đầu/ }).click()
  }
  await page.waitForSelector('#tg-start-input', { timeout: 60000 })
  await shot('discover')
  await page.fill('#tg-start-input', '3 ngày ở Đà Lạt cho hai người, đi xe máy, thích chill, cà phê, săn mây')
  await page.keyboard.press('Enter')
  step('understand: first turn')
  // The opening question is a conversation: wait for "Mình đã hiểu như này", then agree to go on.
  await page.waitForSelector('.tg-chat__sum', { timeout: 120000 })
  await shot('understand-chat')
  await page.click('.tg-chat__go .tg-btn')
  await page.waitForSelector('.tg-ask__card:not(.tg-chat), .tg-ask__done', { timeout: 120000 })
  await shot('understand')
  // Answer whatever the agent asks with the first option (or skip) until it hands over to Chọn nơi.
  for (let i = 0; i < 20 && !page.url().includes('/explore'); i++) {
    await page.waitForFunction(() => !document.querySelector('.tg-ask__card[aria-busy="true"], .tg-deck.is-waiting') || location.pathname.includes('/explore'), null, { timeout: 120000 })
    if (page.url().includes('/explore')) break
    const done = await page.$('.tg-ask__done .tg-btn--primary')
    if (done) { step('show'); await done.click(); await page.waitForTimeout(1500); continue }
    const date = await page.$('.tg-ask__date input')
    if (date) { await date.fill('2026-11-12'); await page.click('.tg-ask__ok'); await page.waitForTimeout(1200); continue }
    const qid = await page.locator('.tg-ask__intent b').innerText().catch(() => '')
    if (await page.$('.tg-ask__card .tg-pin input')) {
      // origin (Xuất phát) or a booked lodging (Chỗ ở): type, wait for the suggestions, pick the first
      const lodging = /CHỖ Ở/.test(qid)
      if (lodging) { step('lodging: none yet'); await shot('understand-lodging'); await page.getByRole('button', { name: 'Chưa có, gợi ý giúp mình' }).click() }
      else {
        step('origin: Quận 1')
        await page.fill('.tg-ask__card .tg-pin input', 'Quận 1, Hồ Chí Minh')
        await page.waitForSelector('.tg-pin__list [role="option"]', { timeout: 30000 })
        await shot('understand-origin')
        await page.keyboard.press('Enter')
      }
      await page.waitForTimeout(1200)
      continue
    }
    if (/PHƯƠNG TIỆN/.test(qid)) { step('arrival: plane'); await page.getByRole('button', { name: /Máy bay/ }).click(); await page.waitForTimeout(1200); continue }
    if (await page.$('.tg-ask__card .tg-trn')) {
      step(`transit: ${qid}`)
      await page.waitForSelector('.tg-trn__row, .tg-trn__none', { timeout: 180000 })
      await shot(`understand-${/VỀ/.test(qid) ? 'outbound' : 'inbound'}`)
      const pick = await page.$('.tg-trn__row .tg-btn--primary')
      if (pick) await pick.click()
      else { await page.fill('.tg-trn__time input', /VỀ/.test(qid) ? '15:00' : '09:00'); await page.click('.tg-trn__time .tg-btn') }
      await page.waitForTimeout(1200)
      continue
    }
    const opt = await page.$('.tg-ask__card .tg-opt:not(.is-soft), .tg-ask__card .tg-basics__chips .tg-chip')
    if (opt) {
      step(`answer ${i + 1}: ${(await opt.innerText()).split('\n')[0]}`)
      await opt.click()
      const ok = await page.$('.tg-ask__ok')
      if (ok && (await ok.isEnabled())) await ok.click()
    } else {
      const skip = await page.$('.tg-ask__skip')
      if (skip) await skip.click()
      else break
    }
    await page.waitForTimeout(1200)
    if (i === 2) await shot('understand-delta')
  }
  await page.waitForURL(/\/app\/explore/, { timeout: 180000 })
  await page.waitForSelector('.tg-disc__wedge.is-on', { timeout: 120000 })
  await shot('explore-disc-hint')
  step('disc: wheel on the disc turns it, the layer does not scroll')
  const name0 = await page.locator('.tg-disc__copy h2').innerText()
  const zone = await page.locator('.tg-disc__zone').boundingBox()
  await page.mouse.move(zone.x + zone.width * 0.6, zone.y + zone.height / 2)
  for (let k = 0; k < 3; k++) { await page.mouse.wheel(0, 120); await page.waitForTimeout(260) }
  const name1 = await page.locator('.tg-disc__copy h2').innerText()
  const top1 = await page.locator('.tg-disc').evaluate((el) => el.scrollTop)
  console.log('disc turned:', name0 !== name1, '| hint gone after turning:', (await page.locator('.tg-disc__tip').count()) === 0, '| layer scrollTop after wheel on disc:', top1)
  await shot('disc-turned')
  for (let k = 0; k < 4; k++) { await page.mouse.wheel(0, -120); await page.waitForTimeout(260) }
  await shot('disc-wrapped')
  const main = await page.locator('.tg-disc__main').boundingBox()
  await page.mouse.move(main.x + main.width / 2, main.y + main.height / 2)
  await page.mouse.wheel(0, 400)
  await page.waitForTimeout(400)
  const fits = await page.locator('.tg-disc').evaluate((el) => ({ top: el.scrollTop, overflow: el.scrollHeight - el.clientHeight }))
  console.log('wheel on content scrolls the layer:', fits)
  await shot('disc-content-scrolled')
  await page.setViewportSize({ width: 1280, height: 720 })
  await page.waitForTimeout(500)
  await shot('disc-1280x720')
  await page.setViewportSize({ width: W, height: 900 })
  step('explore: narrow by chat inside the disc')
  await page.locator('.tg-disc').evaluate((el) => el.scrollTo(0, 0))
  await page.getByRole('button', { name: 'Chat để thu hẹp' }).click()
  await page.waitForSelector('.tg-disc__chat #tg-asst-in')
  await page.fill('#tg-asst-in', 'mình muốn chỗ yên tĩnh hơn, không thích quán đông')
  await page.keyboard.press('Enter')
  await page.waitForTimeout(1500)
  await shot('explore-narrowing')
  await page.waitForFunction(() => !document.querySelector('.tg-asst [aria-busy="true"], .tg-asst .is-busy'), null, { timeout: 120000 }).catch(() => {})
  await page.waitForTimeout(1500)
  await shot('explore-narrowed')
  await page.locator('.tg-asst header button').last().click()
  // add three places to the trip, turning the disc between them
  for (let k = 0; k < 3; k++) {
    const add = page.locator('.tg-disc__ic[aria-label="Thêm vào chuyến"]')
    if (await add.count()) await add.click()
    await page.waitForTimeout(1500)
    await page.keyboard.press('ArrowDown')
    await page.waitForTimeout(500)
  }
  await page.waitForTimeout(2500)
  await shot('explore-selected')
  await page.click('.tg-bar__main')
  await shot('selected-panel')
  await page.keyboard.press('Escape')
  await page.click('.tg-disc__cta')
  await page.waitForSelector('.tg-ps.is-modal', { timeout: 30000 })
  await shot('place-sheet')
  await page.keyboard.press('Escape')
  await page.waitForSelector('.tg-ps', { state: 'detached', timeout: 10000 })
  await page.click('.tg-fab')
  await shot('assistant')
  await page.locator('.tg-asst header button').last().click()
  const go = page.locator('.tg-bar > .tg-btn--primary')
  if (await go.isEnabled()) {
    await go.click()
    await page.waitForURL(/\/app\/plan/, { timeout: 180000 })
    await page.waitForSelector('.tg-lod, .tg-journey, .tg-plan__cols:not([aria-busy]), .tg-empty', { timeout: 120000 })
    if (await page.$('.tg-lod')) {
      step('lodging screen: pick the first')
      await page.waitForSelector('.tg-lod__card, .tg-lod__empty', { timeout: 180000 })
      await shot('plan-lodging')
      const here = await page.$('.tg-lod__card .tg-btn--primary')
      if (here) await here.click()
      else await page.getByRole('button', { name: /Cứ xếp giúp/ }).click()
      await page.waitForSelector('.tg-journey, .tg-plan__cols:not([aria-busy]), .tg-empty', { timeout: 120000 })
    }
    await shot('plan-choose')
    const j = await page.$('.tg-journey')
    if (j) { await j.click(); await page.waitForSelector('.tg-daytab', { timeout: 60000 }) }
    await shot('plan-day')
    await page.click('.tg-plan__viewbar button:nth-child(2)')
    await shot('plan-route')
    await page.click('.tg-confirm .tg-btn--primary')
    await page.waitForURL(/\/app\/done/, { timeout: 60000 })
    await shot('done')
    await page.click('.tg-scale__b >> nth=3')
    await page.click('.tg-done__act .tg-btn--primary')
    await page.waitForSelector('.tg-done__hero.is-sent', { timeout: 30000 })
    await shot('done-sent')
  } else console.log('! bar button disabled:', await page.locator('.tg-bar').innerText())
  await page.goto(BASE + '/app/trips', { waitUntil: 'networkidle' })
  await page.waitForTimeout(1500)
  await shot('trips')
  await page.goto(BASE + '/app/saved', { waitUntil: 'networkidle' })
  await shot('saved')
  await page.goto(BASE + '/app/profile', { waitUntil: 'networkidle' })
  await shot('profile')
} catch (e) {
  console.log('FAILED at', page.url(), String(e).split('\n')[0])
  await page.screenshot({ path: `${OUT}/zz-failure.png` })
} finally {
  console.log(errors.length ? errors.slice(0, 15).join('\n') : 'no page errors')
  await browser.close()
}
