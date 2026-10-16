// Splits <dir>/snapshot.json for priority loading (data/store.ts):
//  snapshot-lite.json  every place without its evidence (features, videos, details) plus `ck`, the chunk that holds it: small, loaded first
//  detail/NNN.json     { <place id>: { features, videos, details } } for CHUNK places each, most-reviewed places first,
//                      so the first chunks hold what people see first; the page asks for the rest in the order it shows them
// usage: node web/scripts/split_snapshot.mjs [dir, default web/public/data] [--drop-full]
import { mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'

const CHUNK = 150
const HEAVY = ['features', 'videos', 'details']

export function splitSnapshot(dir, dropFull = false) {
  const file = join(dir, 'snapshot.json')
  const { places, ...head } = JSON.parse(readFileSync(file, 'utf8'))
  const order = places.map((_, i) => i).sort((a, b) => (places[b].reviewCount ?? 0) - (places[a].reviewCount ?? 0) || a - b)
  // NFS keeps a file a live server still streams as .nfsXXXX and refuses to remove its folder: the chunks are rewritten in place below.
  try { rmSync(join(dir, 'detail'), { recursive: true, force: true }) } catch (e) { if (e.code !== '' && e.code !== 'EBUSY' && e.code !== 'ENOTEMPTY') throw e }
  mkdirSync(join(dir, 'detail'), { recursive: true })
  const lite = new Array(places.length)
  for (let c = 0; c * CHUNK < order.length; c++) {
    const body = {}
    for (const i of order.slice(c * CHUNK, (c + 1) * CHUNK)) {
      const p = places[i]
      const heavy = {}
      for (const k of HEAVY) if (p[k] != null && !(Array.isArray(p[k]) && !p[k].length)) heavy[k] = p[k]
      body[p.id] = heavy
      const rest = { ...p }
      for (const k of HEAVY) delete rest[k]
      lite[i] = { ...rest, ck: c }
    }
    writeFileSync(join(dir, 'detail', `${String(c).padStart(3, '0')}.json`), JSON.stringify(body))
  }
  writeFileSync(join(dir, 'snapshot-lite.json'), JSON.stringify({ ...head, chunks: Math.ceil(order.length / CHUNK), places: lite }))
  if (dropFull) rmSync(file)
  console.log(`[split] ${places.length} places -> snapshot-lite.json + ${Math.ceil(order.length / CHUNK)} detail chunks`)
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const args = process.argv.slice(2)
  splitSnapshot(resolve(args.find((a) => !a.startsWith('--')) ?? resolve(import.meta.dirname, '../public/data')), args.includes('--drop-full'))
}
