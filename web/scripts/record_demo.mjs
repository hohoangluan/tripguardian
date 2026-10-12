// Record the landing's demo video (public/media/demo.mp4 + demo.jpg) by driving the real /app on a phone viewport.
// Usage (from web/): node scripts/record_demo.mjs   (./run.sh start first: web on :5173 and the three APIs; ffmpeg on PATH)
import { execFileSync } from 'node:child_process'
import { mkdirSync, readdirSync, renameSync, rmSync } from 'node:fs'
import { chromium } from 'playwright-core'

const W = 390
const H = 844
const B = 'http://localhost:5173'
const TMP = 'shots/_video'
// Places the planner can lay out together (one per group), so the video ends on a real schedule.
const PLAN_SET = ['Công Viên Yersin', 'Chùa Linh Sơn', 'Coffee Em và Trịnh', 'Chạm cà phê & kem bơ Đà Lạt']
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
  await page.locator(sel).first().click({ timeout: 40000 })
  await wait(pause)
}
const scroll = async (dy, steps = 12) => {
  for (let i = 0; i < steps; i++) await page.mouse.wheel(0, dy / steps), await wait(40)
  await wait(500)
}

await page.goto(`${B}/app`, { waitUntil: 'networkidle' })
await page.evaluate(() => localStorage.clear())
await page.goto(`${B}/app`, { waitUntil: 'networkidle' })
await wait(1500)
await tap('.auth__guest', 1400)
await tap('.start2__card >> nth=0', 2500)

// Understanding: the frame question, then the first real option of every turn until "Xem gợi ý".
for (const c of ['3 ngày', 'Người yêu, vợ chồng', 'Xe máy']) await tap(`button.chip >> text=${c}`, 450)
await tap('.q__done', 4000)
for (let i = 0; i < 10 && page.url().includes('/understand'); i++) {
  await page.locator('.q__cards .qcard:enabled, .q__rows .chip:enabled, .q__go .btn:enabled').first().waitFor({ timeout: 40000 })
  if (await page.locator('.q__go .btn').count()) {
    await tap('.q__go .btn', 6000)
    break
  }
  const card = page.locator('.q__cards .qcard:not(.qcard--unsure):enabled')
  const chip = page.locator('.q__rows .chip:not(.chip--unsure):enabled')
  if (await card.count()) await card.first().click()
  else await chip.first().click()
  await wait(500)
  if (await page.locator('.q__done:enabled').count()) await tap('.q__done', 300)
  await wait(3500)
}

// Shortlist: keep exactly the plannable set, tab by tab.
await page.evaluate(async (names) => {
  const did = JSON.parse(localStorage.getItem('tg.trip.v1')).decisionId
  const v = await fetch(`/api/decision/sessions/${did}`).then((r) => r.json())
  const ids = v.view.groups.flatMap((g) => g.cards).filter((c) => names.includes(c.name)).map((c) => c.id)
  for (const id of v.view.selected) if (!ids.includes(id)) await fetch(`/api/decision/sessions/${did}/act`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ type: 'drop', place_id: id }) })
}, PLAN_SET)
await page.reload({ waitUntil: 'networkidle' })
await wait(1500)
const tabs = await page.locator('.sl-tabs button').count()
for (let t = 0; t < tabs; t++) {
  await tap(`.sl-tabs button >> nth=${t}`, 900)
  for (const name of PLAN_SET) {
    const card = page.locator('.pcard', { hasText: name }).first()
    if (!(await card.count())) continue
    await card.scrollIntoViewIfNeeded()
    await wait(500)
    const add = card.locator('.pcard__actions .btn:not(.btn--chosen)')
    if (await add.count()) await add.click(), await wait(1300)
  }
  await page.evaluate(() => scrollTo({ top: 0, behavior: 'smooth' }))
  await wait(600)
}
await tap('.curate .btn', 2600)
await scroll(500)
await tap('.pfoot .btn', 5000)
if (await page.locator('.vtabs button').count() && !(await page.locator('.dtabs').count())) await tap('.vtabs button >> nth=0', 3000)
await scroll(700)
await wait(1500)
await scroll(700)
await wait(1500)
await ctx.close()
await browser.close()

const webm = `${TMP}/${readdirSync(TMP)[0]}`
renameSync(webm, `${TMP}/raw.webm`)
const ff = (args) => execFileSync('ffmpeg', ['-y', '-loglevel', 'error', ...args])
// Trim the blank first frames, play at 1.6x so the whole flow fits about 45 s, encode for every browser.
ff(['-ss', '1.2', '-i', `${TMP}/raw.webm`, '-vf', 'setpts=PTS/1.6,scale=600:-2:flags=lanczos,fps=30', '-c:v', 'libx264', '-preset', 'slow', '-crf', '32', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-an', 'public/media/demo.mp4'])
ff(['-sseof', '-6', '-i', 'public/media/demo.mp4', '-frames:v', '1', '-q:v', '4', 'public/media/demo.jpg'])
rmSync(TMP, { recursive: true, force: true })
