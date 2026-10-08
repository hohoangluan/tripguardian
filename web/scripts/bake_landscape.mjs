// Bakes web/public/world/dalat.bin from scripts/landscape/{dem,osm}.json (made by export_landscape.py).
// usage: npm run bake:landscape --prefix web
import { mkdirSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createServer } from 'vite'

const root = resolve(import.meta.dirname, '..')
const server = await createServer({ root, configFile: false, logLevel: 'error', server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' })
try {
  const { bakeLandscape } = await server.ssrLoadModule('/scripts/landscape/bake.ts')
  const t0 = Date.now()
  const bytes = bakeLandscape()
  mkdirSync(resolve(root, 'public/world'), { recursive: true })
  writeFileSync(resolve(root, 'public/world/dalat.bin'), bytes)
  console.log(`public/world/dalat.bin ${(bytes.length / 1024).toFixed(0)} KB in ${((Date.now() - t0) / 1000).toFixed(1)} s`)
} finally {
  await server.close()
}
