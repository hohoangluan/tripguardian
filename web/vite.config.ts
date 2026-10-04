import { createReadStream, statSync } from 'node:fs'
import { resolve, sep } from 'node:path'
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

const MEDIA: Record<string, string> = {
  '/media/tiktok': resolve(__dirname, '../data/tiktok/videos'),
  '/media/gmaps': resolve(__dirname, '../data/gmaps/places'),
}
const TYPES: Record<string, string> = { mp4: 'video/mp4', jpg: 'image/jpeg' }

// Dev only: serves crawled TikTok clips and frames (/media/tiktok/<id>/<file>) and Google Maps photos
// (/media/gmaps/<place dir>/photos/<file>) from data/, with Range support so the browser can seek.
function clips(): Plugin {
  return {
    name: 'tg-media',
    configureServer(server) {
      for (const [mount, root] of Object.entries(MEDIA))
        server.middlewares.use(mount, (req, res, next) => {
          const rel = decodeURIComponent((req.url ?? '').split('?')[0])
          const file = resolve(root, '.' + rel)
          const type = TYPES[file.split('.').pop() ?? '']
          if (!file.startsWith(root + sep) || !type) return next()
          let size: number
          try {
            size = statSync(file).size
          } catch {
            res.statusCode = 404
            return res.end()
          }
          const range = /bytes=(\d*)-(\d*)/.exec(req.headers.range ?? '')
          res.setHeader('Content-Type', type)
          res.setHeader('Accept-Ranges', 'bytes')
          res.setHeader('Cache-Control', 'max-age=3600')
          if (!range) {
            res.setHeader('Content-Length', size)
            return createReadStream(file).pipe(res)
          }
          const start = range[1] ? Number(range[1]) : 0
          const end = range[2] ? Math.min(Number(range[2]), size - 1) : size - 1
          res.statusCode = 206
          res.setHeader('Content-Range', `bytes ${start}-${end}/${size}`)
          res.setHeader('Content-Length', end - start + 1)
          createReadStream(file, { start, end }).pipe(res)
        })
    },
  }
}

export default defineConfig({
  plugins: [react(), clips()],
  // /api/decision: `python -m decision serve` (src/decision/server.py, Place Decision).
  // /api/planning: `python -m planning serve` (src/planning/server.py, Planning & Validation).
  // /api/trip: `python -m trip serve` (src/trip/server.py, Trip Understanding).
  // /api: `python -m corpus review` (src/corpus/review/server.py): decisions and gold labels.
  server: {
    proxy: {
      '/api/decision': 'http://127.0.0.1:8767',
      '/api/planning': 'http://127.0.0.1:8768',
      '/api/trip': 'http://127.0.0.1:8766',
      '/api': 'http://127.0.0.1:8765',
    },
  },
})
