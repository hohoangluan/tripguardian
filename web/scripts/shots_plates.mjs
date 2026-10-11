// Makes the light landing's chapter pictures (public/img/landing-p1..p5.webp) from the live 3D model: one frame per
// chapter, with the page's own text and labels hidden. The hero picture is landing-poster.webp (scripts/ in docs/UI_SPEC_LANDING.md §3).
// Needs the Vite dev server running and Python with Pillow (.venv).  usage: node web/scripts/shots_plates.mjs [base url, default http://127.0.0.1:5173]
import { execFileSync } from 'node:child_process'
import { mkdirSync, rmSync } from 'node:fs'
import { resolve } from 'node:path'
import { chromium } from 'playwright-core'

const BASE = process.argv[2] ?? 'http://127.0.0.1:5173'
const ROOT = resolve(import.meta.dirname, '../..')
const OUT = resolve(import.meta.dirname, '../public/img')
const TMP = resolve(import.meta.dirname, '../shots/plates')
mkdirSync(TMP, { recursive: true })
const exe = resolve(ROOT, '.cache/ms-playwright/chromium-1169/chrome-linux/chrome')
const browser = await chromium.launch({ executablePath: exe, args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] })
const page = await browser.newPage({ viewport: { width: 1440, height: 860 } })
await page.goto(`${BASE}/?3d=on`, { waitUntil: 'load' })
await page.waitForFunction(() => performance.getEntriesByName('tg-scene-first-frame').length > 0, null, { timeout: 180000 })
await page.addStyleTag({ content: '.tg-ln,.tg-l3__chs,.tg-l3__veil,.tg-l3__labels,.tg-l3__rail,.tg-l3__turn,.tg-l3__down,.tg-l3__stage::before,.tg-l3__poster{display:none!important}' })
// scroll positions of the chapters (timeline time i of 5.5)
for (let i = 1; i <= 5; i++) {
  await page.evaluate((f) => { const s = document.querySelector('.tg-l3'); window.scrollTo(0, s.offsetTop + f * (s.offsetHeight - innerHeight) + 4) }, i / 5.5)
  await page.waitForTimeout(4500)
  await page.screenshot({ path: `${TMP}/p${i}.png` })
  console.log('plate', i)
}
await browser.close()
execFileSync(resolve(ROOT, '.venv/bin/python'), ['-c', `
from PIL import Image
for i in range(1, 6):
    Image.open('${TMP}/p%d.png' % i).convert('RGB').save('${OUT}/landing-p%d.webp' % i, 'WEBP', quality=72, method=6)
`])
rmSync(TMP, { recursive: true, force: true })
console.log('wrote', OUT)
