// Render the source miniature loop (14 s, 24 fps, 1920x1080) to PNG frames.
const { createRequire } = require('module')
const req = createRequire(require('path').join(__dirname, '../../package.json'))
const { chromium } = req('playwright-core')
const path = require('path')
const fs = require('fs')
const out = path.join(__dirname, 'mini')
fs.mkdirSync(out, { recursive: true })
;(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    args: ['--allow-file-access-from-files', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'],
  })
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } })
  page.on('pageerror', console.error)
  // Source scene ships in tripguardian/TripGuardian-3D-Source (untracked, from the 3D handoff zip).
  await page.goto('file:///' + path.resolve(__dirname, '../../../TripGuardian-3D-Source/TripGuardian-3D/scene.html').replace(/\\/g, '/'))
  await page.waitForFunction(() => window.sceneReady, { timeout: 120000 })
  page.setDefaultTimeout(180000)
  for (let i = 0; i < 336; i++) {
    const f = path.join(out, String(i).padStart(4, '0') + '.png')
    if (fs.existsSync(f) && fs.statSync(f).size > 0) continue
    await page.evaluate((t) => window.setFrame(t), i / 24)
    await page.screenshot({ path: f })
    if (i % 48 === 0) console.log('frame', i)
  }
  await browser.close()
})().catch((e) => { console.error(e); process.exit(1) })
