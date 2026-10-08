// Production-only step after `vite build` (./run.sh prod): what web/server.mjs sends through the tunnel.
//  1. dist/data/snapshot.json keeps only what the user web reads; /admin is never public, so its fields go
//     (review queue, decisions, build/system, per-signal breakdowns). public/data stays complete for dev and admin.
//  2. Every text file in dist gets .br and .gz siblings; server.mjs serves them to clients that accept them.
//     Results are cached by content hash, so an unchanged snapshot is not recompressed on every deploy.
import { createHash } from 'node:crypto'
import { existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { extname, join, resolve } from 'node:path'
import { brotliCompressSync, constants, gzipSync } from 'node:zlib'

const DIST = resolve(import.meta.dirname, '../dist')
const CACHE = resolve(import.meta.dirname, '../node_modules/.cache/tg-prod')
const TEXT = new Set(['.html', '.js', '.css', '.json', '.svg', '.txt', '.bin'])
const DROP_TOP = ['review', 'decisions', 'system', 'build']
const DROP_PLACE = ['proposed', 'attributes', 'ratingTrend', 'coverage', 'closure', 'googleStatus']
const DROP_SIGNAL = ['distribution', 'bySource', 'byContext', 'mentionRate', 'trend', 'authority', 'rawStatus']

function slimSnapshot() {
  const file = join(DIST, 'data/snapshot.json')
  if (!existsSync(file)) return console.warn('[prod] no dist/data/snapshot.json')
  const before = statSync(file).size
  const s = JSON.parse(readFileSync(file, 'utf8'))
  for (const k of DROP_TOP) delete s[k]
  for (const p of s.places) {
    for (const k of DROP_PLACE) delete p[k]
    // NEEDS_REVIEW / DISABLED signals are never shown to users (data/store.ts visible()).
    p.features = p.features.filter((f) => f.status !== 'NEEDS_REVIEW' && f.status !== 'DISABLED')
    for (const f of p.features) for (const k of DROP_SIGNAL) delete f[k]
  }
  writeFileSync(file, JSON.stringify(s))
  console.log(`[prod] snapshot ${(before / 1e6).toFixed(1)} MB -> ${(statSync(file).size / 1e6).toFixed(1)} MB`)
}

function* walk(dir) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name)
    if (e.isDirectory()) yield* walk(p)
    else if (TEXT.has(extname(e.name))) yield p
  }
}

function cached(buf, kind, make) {
  const f = join(CACHE, `${createHash('sha1').update(buf).digest('hex')}.${kind}`)
  if (existsSync(f)) return readFileSync(f)
  const out = make()
  writeFileSync(f, out)
  return out
}

function compressAll() {
  mkdirSync(CACHE, { recursive: true })
  let raw = 0
  let br = 0
  for (const file of walk(DIST)) {
    const buf = readFileSync(file)
    if (buf.length < 1024) continue
    const b = cached(buf, 'br', () => brotliCompressSync(buf, { params: { [constants.BROTLI_PARAM_QUALITY]: 11, [constants.BROTLI_PARAM_SIZE_HINT]: buf.length } }))
    writeFileSync(file + '.br', b)
    writeFileSync(file + '.gz', cached(buf, 'gz', () => gzipSync(buf, { level: 9 })))
    raw += buf.length
    br += b.length
  }
  console.log(`[prod] precompressed ${(raw / 1e6).toFixed(1)} MB -> ${(br / 1e6).toFixed(1)} MB brotli`)
}

slimSnapshot()
compressAll()
