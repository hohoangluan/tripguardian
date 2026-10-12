// Real HTTP fixture supplied by tests/harness/test_overload_browser.py.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { chromium } from 'playwright-core'

const [base, seedFile] = process.argv.slice(2)
const seed = JSON.parse(readFileSync(seedFile, 'utf8'))
const browser = await chromium.launch({ executablePath: resolve('../.cache/ms-playwright/chromium-1169/chrome-linux/chrome'), args: ['--no-sandbox'] })
try {
  const context = await browser.newContext()
  await context.addCookies([{ name: 'tg_session', value: 'tok-a', url: base }])
  await context.addInitScript(seed => localStorage.setItem('tg.trip.v1', JSON.stringify(seed)), seed)
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', e => errors.push(e.message))
  await page.route('**/api/harness/me', r => r.fulfill({ json: { id: 'a'.repeat(32), name: 'Fixture', needs_consent: false, consents: {} } }))
  await page.goto(base + '/app/explore')
  await page.getByRole('button', { name: 'Xem 3 hướng lập lịch' }).click()
  await page.waitForSelector('.tg-journey')
  assert.equal(await page.locator('.tg-journey').count(), 3)
  assert.ok(await page.locator('.tg-journey:not([disabled])').count())
  await page.locator('.tg-journey:not([disabled])').first().click()
  await page.getByRole('button', { name: 'Chốt kế hoạch này' }).waitFor()
  await page.getByText('So với danh sách đã chọn', { exact: false }).waitFor()
  await page.getByText('Giữ tất cả · Đối chiếu danh sách ban đầu', { exact: true }).click()
  assert.ok(await page.locator('details[open] ol li').count())
  await page.getByText('Giữ tất cả · Đối chiếu danh sách ban đầu', { exact: true }).click()
  await page.getByRole('button', { name: 'Xem trước khi khôi phục' }).first().click()
  await page.getByRole('dialog').waitFor()
  const room = page.getByRole('button', { name: 'Xem cách này', exact: true })
  if (await room.count()) {
    await room.first().click()
    await page.getByRole('button', { name: 'Áp dụng thay đổi đã xem' }).waitFor()
  }
  await page.getByRole('button', { name: 'Áp dụng thay đổi đã xem' }).click()
  await page.waitForSelector('[role="dialog"]', { state: 'hidden' })
  await page.getByRole('tab', { name: 'Gọn tuyến', exact: true }).click()
  await page.getByRole('button', { name: 'Tối ưu lại quanh lựa chọn của tôi' }).click()
  await page.getByRole('dialog').waitFor()
  await page.getByRole('button', { name: 'Để sau', exact: true }).click()
  await page.getByRole('button', { name: 'Chốt kế hoạch này' }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'Chốt kế hoạch này' }).isEnabled(), true)
  await page.getByRole('button', { name: 'Chốt kế hoạch này' }).click()
  await page.waitForURL('**/app/done')
  assert.deepEqual(errors, [])
  console.log('overload browser flow passed')
} finally {
  await browser.close()
}
