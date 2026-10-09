// Public server for the built web (web/dist): what a Cloudflare tunnel may expose, and nothing else.
//   public : landing, /app (SPA), /assets, /img, /data (snapshot, covers), /media photos (jpg only),
//            /media/thumb WebP thumbnails (web/scripts/make_thumbs.py), /media/tiktok/<id>/video.mp4 clips (Range),
//            /api/harness/* and /api/auth/* (Google sign-in) proxied to the harness on 127.0.0.1:8769 (JSON and SSE).
//   private: /admin, every other /api/* (review server, module dev APIs), any other video file -> 404.
// Speed: .br/.gz made by web/scripts/prod_assets.mjs are sent to clients that accept them (the tunnel carries
// compressed bytes); every file has an ETag, so a revisit costs a 304; the harness is reached over keep-alive.
// usage: npm run build:prod --prefix web && node web/server.mjs [port, default 28899]
import { createReadStream, existsSync, statSync } from 'node:fs'
import { Agent, createServer, request } from 'node:http'
import { extname, resolve, sep } from 'node:path'

const PORT = Number(process.argv[2] ?? process.env.PORT ?? 28899)
const HARNESS = { host: '127.0.0.1', port: Number(process.env.HARNESS_PORT ?? 8769), agent: new Agent({ keepAlive: true, maxSockets: 64 }) }
const DIST = resolve(import.meta.dirname, 'dist')
const MEDIA = {
  '/media/thumb/': resolve(import.meta.dirname, '../data/thumbs'),
  '/media/gmaps/': resolve(import.meta.dirname, '../data/gmaps/places'),
  '/media/tiktok/': resolve(import.meta.dirname, '../data/tiktok/videos'),
}
const TYPES = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8', '.webp': 'image/webp', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
  '.png': 'image/png', '.bin': 'application/octet-stream', '.svg': 'image/svg+xml', '.ico': 'image/x-icon', '.woff2': 'font/woff2', '.txt': 'text/plain; charset=utf-8',
  '.webmanifest': 'application/manifest+json',
}
const MEDIA_TYPES = new Set(['.jpg', '.jpeg', '.webp', '.png'])
// Clips a place card plays (corpus tiktok clips): only the mp4 of a video directory, sent in ranges so it can seek.
const CLIP = /^\/media\/tiktok\/\d+\/video\.mp4$/
// Data files change only on a deploy: browsers and Cloudflare may reuse them briefly, then revalidate (ETag).
const DATA_CACHE = 'public, max-age=300, stale-while-revalidate=86400'

function notFound(res) {
  res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' })
  res.end('Not found')
}

// A file strictly inside `root`, or null (no path escapes, no directories).
function inside(root, rel) {
  const file = resolve(root, '.' + rel)
  if (!file.startsWith(root + sep)) return null
  try {
    return statSync(file).isFile() ? file : null
  } catch {
    return null
  }
}

// The precompressed sibling the client accepts, if prod_assets.mjs made one.
function encoded(req, file) {
  const accept = String(req.headers['accept-encoding'] ?? '')
  for (const [enc, ext] of [['br', '.br'], ['gzip', '.gz']]) {
    if (!accept.includes(enc)) continue
    try {
      const st = statSync(file + ext)
      if (st.isFile()) return { enc, path: file + ext, st }
    } catch { /* not precompressed */ }
  }
  return null
}

function sendFile(req, res, file, cache) {
  const type = TYPES[extname(file).toLowerCase()] ?? 'application/octet-stream'
  const st = statSync(file)
  const etag = `"${st.size.toString(36)}-${Math.floor(st.mtimeMs).toString(36)}"`
  const head = { 'Content-Type': type, 'Cache-Control': cache, ETag: etag, 'Last-Modified': st.mtime.toUTCString(), 'X-Content-Type-Options': 'nosniff' }
  if (TYPES[extname(file).toLowerCase()]?.match(/text|json|svg|octet/)) head.Vary = 'Accept-Encoding'
  if (req.headers['if-none-match'] === etag) {
    res.writeHead(304, head)
    return res.end()
  }
  const z = encoded(req, file)
  res.writeHead(200, { ...head, 'Content-Length': (z?.st ?? st).size, ...(z && { 'Content-Encoding': z.enc }) })
  if (req.method === 'HEAD') return res.end()
  createReadStream(z?.path ?? file).pipe(res)
}

function sendRange(req, res, file) {
  const st = statSync(file)
  const head = { 'Content-Type': 'video/mp4', 'Accept-Ranges': 'bytes', 'Cache-Control': 'public, max-age=604800', 'X-Content-Type-Options': 'nosniff' }
  const m = /^bytes=(\d*)-(\d*)$/.exec(String(req.headers.range ?? ''))
  if (!m || (!m[1] && !m[2])) {
    res.writeHead(200, { ...head, 'Content-Length': st.size })
    return req.method === 'HEAD' ? res.end() : createReadStream(file).pipe(res)
  }
  const start = m[1] ? Number(m[1]) : Math.max(0, st.size - Number(m[2]))
  const end = m[1] && m[2] ? Math.min(Number(m[2]), st.size - 1) : st.size - 1
  if (start > end || start >= st.size) {
    res.writeHead(416, { ...head, 'Content-Range': `bytes */${st.size}` })
    return res.end()
  }
  res.writeHead(206, { ...head, 'Content-Range': `bytes ${start}-${end}/${st.size}`, 'Content-Length': end - start + 1 })
  return req.method === 'HEAD' ? res.end() : createReadStream(file, { start, end }).pipe(res)
}

function proxy(req, res) {
  const up = request({ ...HARNESS, method: req.method, path: req.url, headers: { ...req.headers, host: `${HARNESS.host}:${HARNESS.port}` } }, (r) => {
    res.writeHead(r.statusCode ?? 502, r.headers)
    r.pipe(res) // streams SSE through unbuffered
  })
  up.on('error', () => {
    if (!res.headersSent) res.writeHead(502, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify({ error: 'journey server unavailable' }))
  })
  req.pipe(up)
}

createServer((req, res) => {
  const path = decodeURIComponent((req.url ?? '/').split('?')[0])
  if (path.startsWith('/api/harness/') || path.startsWith('/api/auth/')) return proxy(req, res)
  if (path.startsWith('/api') || path === '/admin' || path.startsWith('/admin/')) return notFound(res)
  if (req.method !== 'GET' && req.method !== 'HEAD') return notFound(res)
  if (CLIP.test(path)) {
    const file = inside(MEDIA['/media/tiktok/'], path.slice('/media/tiktok'.length))
    return file ? sendRange(req, res, file) : notFound(res)
  }
  for (const [mount, root] of Object.entries(MEDIA)) {
    if (!path.startsWith(mount)) continue
    const file = MEDIA_TYPES.has(extname(path).toLowerCase()) && inside(root, path.slice(mount.length - 1))
    return file ? sendFile(req, res, file, 'public, max-age=604800, stale-while-revalidate=86400') : notFound(res)
  }
  const file = inside(DIST, path)
  if (file) return sendFile(req, res, file, path.startsWith('/assets/') ? 'public, max-age=31536000, immutable' : path.startsWith('/data/') ? DATA_CACHE : path.startsWith('/img/') || path.startsWith('/world/') ? 'public, max-age=86400' : 'no-cache')
  if (extname(path)) return notFound(res)
  // SPA routes (/, /app/...): the shell page
  sendFile(req, res, resolve(DIST, 'index.html'), 'no-cache')
}).listen(PORT, '127.0.0.1', () => {
  if (!existsSync(resolve(DIST, 'index.html'))) console.warn('web/dist is missing: run npm run build --prefix web')
  console.log(`TripGuardian public web: http://127.0.0.1:${PORT} (harness ${HARNESS.host}:${HARNESS.port})`)
})
