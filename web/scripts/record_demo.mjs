// Record the landing's demo video (public/media/demo.mp4) and the hero phone shot
// (public/img/landing-app.webp) by driving the real /app on a phone viewport.
// Usage (from web/): node scripts/record_demo.mjs   (dev server on :5173; ffmpeg on PATH)
import { execFileSync } from 'node:child_process'
import { mkdirSync, readdirSync, renameSync, rmSync } from 'node:fs'
import { chromium } from 'playwright-core'

const W = 390
const H = 844
const TMP = 'shots/_video'
rmSync(TMP, { recursive: true, force: true })
mkdirSync('public/media', { recursive: true })

const browser = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' })
const ctx = await browser.newContext({
  viewport: { width: W, height: H },
  deviceScaleFactor: 2,
  isMobile: true,
  hasTouch: true,
  // The screencast is captured at CSS pixels: a larger frame leaves the page in one corner.
  recordVideo: { dir: TMP, size: { width: W, height: H } },
})
const page = await ctx.newPage()
const wait = (ms) => page.waitForTimeout(ms)
const tap = async (sel, pause = 700) => {
  await page.locator(sel).first().click()
  await wait(pause)
}
const scroll = async (dy, steps = 12) => {
  for (let i = 0; i < steps; i++) await page.mouse.wheel(0, dy / steps), await wait(40)
  await wait(500)
}

await page.goto('http://localhost:5173/app', { waitUntil: 'networkidle' })
await page.evaluate(() => localStorage.clear())
await page.goto('http://localhost:5173/app', { waitUntil: 'networkidle' })
await wait(1800)
await tap('.auth__guest', 1400)
await tap('.choice >> text=Đây là lần đầu', 1100)
await tap('.choice >> text=Chưa có ý tưởng gì', 1500)
await tap('button.chip >> text=Người yêu')
await tap('.seg button >> text=Xe máy', 900)
await scroll(700)
await wait(500)
await tap('.pfoot .btn', 1300)
for (const c of ['View đồi núi', 'Săn mây', 'Cà phê xinh, ngồi lâu']) await tap(`button.chip >> text=${c}`, 450)
await tap('button >> text=Xong câu này', 900)
await tap('button.chip >> text=Yên tĩnh', 900)
await tap('button.chip >> text=Vừa phải', 900)
await tap('button.chip >> text=Ổn cả', 900)
await tap('button >> text=Gợi ý trước đi', 1200)
await scroll(500)
await tap('button >> text=Tìm địa điểm', 2200)
await scroll(420)
const adds = page.locator('.pcard__actions .btn >> text=Thêm')
for (let i = 0; i < 2 && (await adds.count()); i++) await adds.first().click(), await wait(1100)
await scroll(500)
await tap('.tabs button >> nth=2', 1200)
for (let i = 0; i < 2 && (await adds.count()); i++) await adds.first().click(), await wait(1100)
await wait(1500)
await page.screenshot({ path: 'shots/_hero.png' })
await scroll(-2000, 8)
await wait(800)
await tap('.curate .btn', 2400)
for (let i = 0; i < 3 && (await page.locator('.fix').count()); i++) await page.locator('.fix').first().click(), await wait(1000)
await scroll(600)
await tap('.pfoot .btn', 2400)
await scroll(500)
await wait(1500)
await ctx.close()
await browser.close()

const webm = `${TMP}/${readdirSync(TMP)[0]}`
renameSync(webm, `${TMP}/raw.webm`)
const ff = (args) => execFileSync('ffmpeg', ['-y', '-loglevel', 'error', ...args])
// Trim the blank first frames, encode for every browser.
ff(['-ss', '1.2', '-i', `${TMP}/raw.webm`, '-vf', 'scale=600:-2:flags=lanczos,fps=30', '-c:v', 'libx264', '-preset', 'slow', '-crf', '32', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-an', 'public/media/demo.mp4'])
ff(['-ss', '20', '-i', 'public/media/demo.mp4', '-frames:v', '1', '-q:v', '4', 'public/media/demo.jpg'])
ff(['-i', 'shots/_hero.png', '-vf', 'scale=780:-2', '-quality', '82', 'public/img/landing-app.webp'])
rmSync(TMP, { recursive: true, force: true })
rmSync('shots/_hero.png', { force: true })
console.log('demo.mp4, demo.jpg, landing-app.webp written')
