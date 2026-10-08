// Walks the user web against the real harness (landing -> Khám phá -> Hiểu chuyến đi -> Chọn nơi -> Lịch trình -> Phản hồi)
// and saves a screenshot per screen. Needs `python -m harness serve` and the Vite dev server running.
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
  await page.getByRole('button', { name: /Dùng thử/ }).click()
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
  for (let i = 0; i < 14 && !page.url().includes('/explore'); i++) {
    await page.waitForFunction(() => !document.querySelector('.tg-ask__card[aria-busy="true"], .tg-deck.is-waiting') || location.pathname.includes('/explore'), null, { timeout: 120000 })
    if (page.url().includes('/explore')) break
    const done = await page.$('.tg-ask__done .tg-btn--primary')
    if (done) { step('show'); await done.click(); await page.waitForTimeout(1500); continue }
    const date = await page.$('.tg-ask__date input')
    if (date) { await date.fill('2026-11-12'); await page.click('.tg-ask__ok'); await page.waitForTimeout(1200); continue }
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
  }
  await page.waitForURL(/\/app\/explore/, { timeout: 180000 })
  await page.waitForSelector('.tg-pc', { timeout: 120000 })
  await shot('explore')
  step('explore: scroll loads more')
  const before = await page.locator('.tg-grid [data-place]').count()
  await page.locator('.tg-grid__more').scrollIntoViewIfNeeded()
  await page.waitForFunction((n) => document.querySelectorAll('.tg-grid [data-place]').length > n, before, { timeout: 30000 })
  await shot('explore-more')
  await page.evaluate(() => window.scrollTo(0, 0))
  step('explore: narrow by chat')
  await page.getByRole('button', { name: 'Chat để thu hẹp' }).click()
  await page.fill('#tg-asst-in', 'mình muốn chỗ yên tĩnh hơn, không thích quán đông')
  await page.keyboard.press('Enter')
  await page.waitForSelector('.tg-pc.is-enter, .tg-pc.is-leave, .tg-grid.is-replacing', { timeout: 120000 }).catch(() => {})
  await shot('explore-narrowing')
  await page.waitForFunction(() => !document.querySelector('.tg-asst [aria-busy="true"], .tg-asst .is-busy'), null, { timeout: 120000 }).catch(() => {})
  await page.waitForTimeout(1500)
  await shot('explore-narrowed')
  await page.keyboard.press('Escape')
  // the group with most cards, so compare has two places to put side by side
  const tabs = await page.$$('.tg-tab')
  let best = null, most = -1
  for (const t of tabs) { const n = Number((await t.$eval('b', (b) => b.textContent)) ?? 0); if (n > most) { most = n; best = t } }
  if (best) { await best.click(); await page.waitForTimeout(400) }
  const adds = await page.$$('.tg-pc .tg-btn--primary')
  for (const b of adds.slice(0, 3)) { await b.click(); await page.waitForTimeout(1500) }
  await page.waitForTimeout(2500)
  await shot('explore-selected')
  await page.click('.tg-bar__main')
  await shot('selected-panel')
  await page.keyboard.press('Escape')
  await page.click('.tg-pc__open')
  await page.waitForSelector('.tg-detail', { timeout: 30000 })
  await shot('place-detail')
  await page.goBack()
  await page.waitForSelector('.tg-pc')
  const cmps = await page.$$('.tg-pc__ic[title="So sánh"]')
  if (cmps.length >= 2) {
    await cmps[0].click(); await cmps[1].click()
    await page.click('.tg-float-cmp')
    await page.waitForSelector('.tg-cmp, .tg-empty', { timeout: 30000 })
    await shot('compare')
    await page.goBack()
    await page.waitForSelector('.tg-pc')
  }
  await page.click('.tg-fab')
  await shot('assistant')
  await page.keyboard.press('Escape')
  const go = page.locator('.tg-bar > .tg-btn--primary')
  if (await go.isEnabled()) {
    await go.click()
    await page.waitForURL(/\/app\/plan/, { timeout: 180000 })
    await page.waitForSelector('.tg-journey, .tg-plan__cols, .tg-empty', { timeout: 120000 })
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
