// Screenshots of the "Xem chi tiết" sheet opened from the rotary disc and from the grid, one per tab, for a journey
// already at Lựa chọn. Read only: never selects or drops a place.
// usage: node web/scripts/shots_sheet.mjs <base url> <journey id> [out dir] [width]
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { chromium } from 'playwright-core'

const [BASE, JID, OUT = resolve(import.meta.dirname, '../shots/sheet'), W = '1440'] = process.argv.slice(2)
mkdirSync(OUT, { recursive: true })
const exe = resolve(import.meta.dirname, '../../.cache/ms-playwright/chromium-1169/chrome-linux/chrome')
const browser = await chromium.launch({ executablePath: exe })
const page = await browser.newPage({ viewport: { width: Number(W), height: 900 } })
const errors = []
page.on('pageerror', (e) => errors.push(e.message))
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
const shot = (name) => page.screenshot({ path: `${OUT}/${W}-${name}.png` })
try {
  await page.goto(BASE + '/app', { waitUntil: 'networkidle' })
  const tryIt = page.getByRole('button', { name: /Dùng thử/ })
  if (await tryIt.count()) await tryIt.first().click()
  await page.evaluate((id) => localStorage.setItem('tg.trip.v1', JSON.stringify({ journeyId: id, decisionId: id })), JID)
  await page.goto(BASE + '/app/explore', { waitUntil: 'networkidle' })
  await page.waitForSelector('.tg-pc', { timeout: 60000 })
  await shot('grid')
  await page.getByRole('button', { name: /Đĩa xoay/ }).click()
  await page.waitForSelector('.tg-disc__wedge.is-on', { timeout: 20000 })
  await page.waitForTimeout(800)
  await shot('disc')
  await page.getByRole('button', { name: /Xem chi tiết/ }).first().click()
  await page.waitForTimeout(150)
  await shot('disc-opening')
  await page.waitForSelector('.tg-ps.is-modal')
  await page.waitForTimeout(700)
  console.log('url', page.url())
  await shot('sheet-overview')
  for (const [name, label] of [['photos', 'Hình ảnh'], ['plan', 'Gợi ý lịch trình'], ['reviews', 'Đánh giá']]) {
    await page.locator('.tg-ps__tabs').getByRole('tab', { name: label }).click()
    await page.waitForTimeout(300)
    await shot(`sheet-${name}`)
  }
  await page.keyboard.press('Escape')
  await page.waitForTimeout(700)
  console.log('closed', await page.locator('.tg-ps').count() === 0, page.url())
  await shot('disc-closed')
  await page.locator('.tg-disc__back').click()
  await page.waitForSelector('.tg-pc')
  await page.locator('.tg-pc__open').first().click()
  await page.waitForSelector('.tg-ps.is-modal')
  await page.waitForTimeout(700)
  await shot('grid-sheet')
  await page.goBack()
  await page.waitForTimeout(700)
  console.log('back closes', await page.locator('.tg-ps').count() === 0, page.url())
} catch (e) {
  console.log('FAILED', String(e).split('\n')[0])
}
console.log(errors.length ? `errors:\n${errors.join('\n')}` : 'no page errors')
await browser.close()
