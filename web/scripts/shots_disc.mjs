// Screenshots of Chọn nơi in the rotary-disc view for a journey already at that step, at several window sizes.
// usage: node web/scripts/shots_disc.mjs <base url> <journey id> [out dir]
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { chromium } from 'playwright-core'

const [BASE, JID, OUT = resolve(import.meta.dirname, '../shots/disc')] = process.argv.slice(2)
mkdirSync(OUT, { recursive: true })
const exe = resolve(import.meta.dirname, '../../.cache/ms-playwright/chromium-1169/chrome-linux/chrome')
const browser = await chromium.launch({ executablePath: exe })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const errors = []
page.on('pageerror', (e) => errors.push(e.message))
try {
  await page.goto(BASE + '/app', { waitUntil: 'networkidle' })
  const tryIt = page.getByRole('button', { name: /Dùng thử/ })
  if (await tryIt.count()) await tryIt.first().click()
  await page.evaluate((id) => localStorage.setItem('tg.trip.v1', JSON.stringify({ journeyId: id, decisionId: id })), JID)
  await page.goto(BASE + '/app/explore', { waitUntil: 'networkidle' })
  await page.waitForSelector('.tg-pc', { timeout: 60000 })
  await page.getByRole('button', { name: /Đĩa xoay/ }).click()
  await page.waitForSelector('.tg-disc__wedge.is-on', { timeout: 20000 })
  for (const [w, h] of [[1440, 900], [1280, 720], [1920, 1080]]) {
    await page.setViewportSize({ width: w, height: h })
    await page.waitForTimeout(700)
    await page.screenshot({ path: `${OUT}/disc-${w}x${h}.png` })
    const fit = await page.locator('.tg-disc').evaluate((el) => el.scrollHeight - el.clientHeight)
    console.log(`${w}x${h}: wedges ${await page.locator('.tg-disc__wedge').count()}, overflow ${fit}px`)
  }
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.waitForTimeout(500)
  const zone = await page.locator('.tg-disc__zone').boundingBox()
  await page.mouse.move(zone.x + zone.width * 0.6, zone.y + zone.height / 2)
  await page.mouse.wheel(0, 120)
  await page.waitForTimeout(250)
  await page.screenshot({ path: `${OUT}/disc-turning.png` })
  await page.waitForTimeout(500)
  await page.screenshot({ path: `${OUT}/disc-turned.png` })
} catch (e) {
  console.log('FAILED', String(e).split('\n')[0])
  await page.screenshot({ path: `${OUT}/failure.png` })
} finally {
  console.log(errors.length ? errors.join('\n') : 'no page errors')
  await browser.close()
}
