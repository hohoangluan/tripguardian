// Pre-renders the landing's 3D story into short videos (docs/UI_SPEC_LANDING.md §2): every visitor, on any machine,
// gets the same picture as a strong GPU without running WebGL. Per chapter i: idle-i.mp4 (the cloud alive at rest,
// played forth and back so it loops without a seam), and between chapters to-i.mp4 (i -> i + 1) and back-i.mp4
// (its reverse, for scrolling up). track.json holds, for every frame, the labels' places, the cloud's box and how far
// the day has got, so the page's DOM labels and itinerary follow the video.
// Needs its own Vite dev server (the shared :5173 serves stale files on NFS) and ffmpeg with libx264.
// usage: node web/scripts/render_landing.mjs [base url, default http://127.0.0.1:5391] [only clip name ...]
import { execFileSync } from 'node:child_process'
import { mkdirSync, rmSync, writeFileSync, readFileSync, existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { chromium } from 'playwright-core'

const BASE = process.argv[2] ?? 'http://127.0.0.1:5391'
const ONLY = new Set(process.argv.slice(3))
const ROOT = resolve(import.meta.dirname, '../..')
const OUT = resolve(import.meta.dirname, '../public/landing/clips')
const TMP = resolve(import.meta.dirname, '../shots/clips')
// the same numbers as src/user/landing/story.ts (read from the file, so the two never drift)
const story = readFileSync(resolve(import.meta.dirname, '../src/user/landing/story.ts'), 'utf8')
const read = (name) => JSON.parse(new RegExp(`export const ${name} = ([^\\n]+)`).exec(story)[1].replace(/\s*\/\/.*$/, ''))
const REST = read('REST'), MOVE_S = read('MOVE_S'), FPS = read('FPS'), IDLE_S = read('IDLE_S'), W = read('CLIP_W'), H = read('CLIP_H')
const T0 = 10 // the clock every clip starts at (past the dots' fade-in), so an idle loop and the move out of it meet
const WARM = 45 // frames drawn before recording: the cloud settles into its pose for the chapter
const smooth = (x) => x * x * (3 - 2 * x)

mkdirSync(OUT, { recursive: true })
const exe = resolve(ROOT, '.cache/ms-playwright/chromium-1169/chrome-linux/chrome')
const browser = await chromium.launch({ executablePath: exe, args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] })
const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 })
page.on('pageerror', (e) => console.error('page:', e.message))
await page.goto(`${BASE}/capture.html`, { waitUntil: 'load' })
await page.waitForFunction(() => window.__cap?.ready(), null, { timeout: 180000, polling: 500 })

const trackFile = resolve(OUT, 'track.json')
const track = existsSync(trackFile) ? JSON.parse(readFileSync(trackFile, 'utf8')) : { clips: {} }
Object.assign(track, { w: W, h: H, fps: FPS })

const draw = (time, t, shot) => page.evaluate(([time, t, dt, shot]) => window.__cap.frame(time, t, dt, shot), [time, t, 1 / FPS, shot])
async function record(name, times) {
  const dir = resolve(TMP, name)
  rmSync(dir, { recursive: true, force: true })
  mkdirSync(dir, { recursive: true })
  for (let k = 0; k < WARM; k++) await draw(times[0], T0 - (WARM - k) / FPS, false)
  const frames = []
  for (let n = 0; n < times.length; n++) {
    const out = await draw(times[n], T0 + n / FPS, true)
    writeFileSync(resolve(dir, `${String(n).padStart(4, '0')}.png`), Buffer.from(out.png.split(',')[1], 'base64'))
    track.stops = out.stops
    frames.push({ l: out.labels, m: out.mascot && { x: Math.round(out.mascot.x), y: Math.round(out.mascot.y), h: Math.round(out.mascot.h) }, tr: Math.round(out.tr * 1000) / 1000 })
  }
  return { dir, frames }
}
function encode(dir, file, filter) {
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-framerate', String(FPS), '-i', `${dir}/%04d.png`,
    ...(filter ? ['-filter_complex', filter] : []),
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '28', '-tune', 'animation', '-pix_fmt', 'yuv420p', '-g', String(FPS), '-movflags', '+faststart',
    resolve(OUT, file)])
}

const want = (name) => !ONLY.size || ONLY.has(name)
for (let i = 0; i < REST.length; i++) {
  if (want(`idle-${i}`)) {
    const { dir, frames } = await record(`idle-${i}`, Array.from({ length: IDLE_S * FPS }, () => REST[i]))
    // forth and back: the last frame of each half is not repeated, so the loop has no stutter
    encode(dir, `idle-${i}.mp4`, `[0]split[a][b];[b]reverse,trim=start_frame=1,setpts=PTS-STARTPTS[r];` +
      `[a][r]concat=n=2:v=1,trim=end_frame=${2 * frames.length - 2},setpts=PTS-STARTPTS`)
    track.clips[`idle-${i}`] = [...frames, ...frames.slice(1, -1).reverse()]
    console.log('idle', i, frames.length)
  }
  if (i < REST.length - 1 && (want(`to-${i}`) || want(`back-${i}`))) {
    const n = Math.round(MOVE_S[i] * FPS) + 1
    const times = Array.from({ length: n }, (_, k) => REST[i] + (REST[i + 1] - REST[i]) * smooth(k / (n - 1)))
    const { dir, frames } = await record(`to-${i}`, times)
    encode(dir, `to-${i}.mp4`)
    encode(dir, `back-${i}.mp4`, '[0]reverse')
    track.clips[`to-${i}`] = frames
    track.clips[`back-${i}`] = [...frames].reverse()
    console.log('move', i, n)
  }
  writeFileSync(trackFile, JSON.stringify(track))
}
await browser.close()
rmSync(TMP, { recursive: true, force: true })
console.log('wrote', OUT)
