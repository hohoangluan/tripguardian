import { BASE_M, DEM, EXAG, inBounds, LANDMARKS, toLatLng, toXZ, TOWN_Y, WORLD } from '../../src/user/landing/geo'
import dem from './dem.json'
import osm from './osm.json'

export { inBounds, LANDMARKS, toLatLng, toXZ, TOWN_Y, WORLD }

// Đà Lạt as it is: SRTM elevation (30 m, sampled every ~330 m), lake outlines, roads, forest / farm / town cover and
// building positions from OpenStreetMap, all baked by web/scripts/export_landscape.py. Only the fine relief detail
// (a little noise on top of the 330 m grid) and the vertical exaggeration are invented. Positions of places are real.

const [DLAT0, DLAT1, DLNG0, DLNG1] = [dem.lat0, dem.lat1, dem.lng0, dem.lng1]
if (DLAT0 !== DEM.lat0 || DLAT1 !== DEM.lat1 || DLNG0 !== DEM.lng0 || DLNG1 !== DEM.lng1) throw new Error('dem.json does not match geo.ts DEM')
export const WATER_Y = TOWN_Y - 1.2 // fallback for places that have no lake under them

const hash = (x: number, y: number) => {
  const s = Math.sin(x * 127.1 + y * 311.7) * 43758.5453
  return s - Math.floor(s)
}
const ease = (t: number) => t * t * (3 - 2 * t)
function noise(x: number, y: number) {
  const xi = Math.floor(x), yi = Math.floor(y)
  const u = ease(x - xi), v = ease(y - yi)
  const a = hash(xi, yi), b = hash(xi + 1, yi), c = hash(xi, yi + 1), d = hash(xi + 1, yi + 1)
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v
}
export function fbm(x: number, y: number) {
  let s = 0, amp = 0.5, f = 1
  for (let i = 0; i < 4; i++) {
    s += amp * noise(x * f, y * f)
    f *= 2.03
    amp *= 0.5
  }
  return s / 0.9375
}
export const smoothstep = (a: number, b: number, x: number) => ease(Math.min(1, Math.max(0, (x - a) / (b - a))))

// ---- elevation ----
const bytes = (b64: string) => Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))
const grid = (() => {
  const raw = bytes(dem.data)
  const v = new DataView(raw.buffer)
  const g = new Float32Array(dem.cols * dem.rows)
  for (let i = 0; i < g.length; i++) g[i] = v.getInt16(i * 2, true)
  // one light blur: a 30 m sample taken every 330 m is spiky on ridges
  const out = new Float32Array(g.length)
  for (let r = 0; r < dem.rows; r++)
    for (let c = 0; c < dem.cols; c++) {
      let s = 0, n = 0
      for (let dr = -1; dr <= 1; dr++)
        for (let dc = -1; dc <= 1; dc++) {
          const rr = r + dr, cc = c + dc
          if (rr < 0 || cc < 0 || rr >= dem.rows || cc >= dem.cols) continue
          const w = (dr ? 1 : 2) * (dc ? 1 : 2)
          s += g[rr * dem.cols + cc] * w
          n += w
        }
      out[r * dem.cols + c] = s / n
    }
  return out
})()

export function elevAt(lat: number, lng: number) {
  const fc = Math.min(dem.cols - 1.001, Math.max(0, ((lng - DLNG0) / (DLNG1 - DLNG0)) * (dem.cols - 1)))
  const fr = Math.min(dem.rows - 1.001, Math.max(0, ((DLAT1 - lat) / (DLAT1 - DLAT0)) * (dem.rows - 1)))
  const c = Math.floor(fc), r = Math.floor(fr), u = fc - c, v = fr - r
  const g = (rr: number, cc: number) => grid[rr * dem.cols + cc]
  return g(r, c) * (1 - u) * (1 - v) + g(r, c + 1) * u * (1 - v) + g(r + 1, c) * (1 - u) * v + g(r + 1, c + 1) * u * v
}
const heightOfElev = (m: number) => TOWN_Y + ((m - BASE_M) / 200) * EXAG

// ---- land cover: 0 open, 1 forest / scrub, 2 farmland and greenhouses, 3 town, 4 park / meadow ----
const cover = { ...osm.cover, data: bytes(osm.cover.data) }
export function coverAt(x: number, z: number) {
  const [lat, lng] = toLatLng(x, z)
  const c = Math.round(((lng - osm.bounds[2]) / (osm.bounds[3] - osm.bounds[2])) * (cover.w - 1))
  const r = Math.round(((osm.bounds[1] - lat) / (osm.bounds[1] - osm.bounds[0])) * (cover.h - 1))
  if (c < 0 || r < 0 || c >= cover.w || r >= cover.h) return 0
  return cover.data[r * cover.w + c]
}

// ---- lakes: real outlines, each held at its own level (Xuân Hương and Tuyền Lâm are 80 m apart in height) ----
interface Lake { name: string | null; ring: [number, number][]; level: number; box: [number, number, number, number]; cx: number; cz: number }
export const LAKES: Lake[] = (osm.lakes as { name: string | null; ring: number[][] }[]).map((l) => {
  const ring = l.ring.map(([lat, lng]) => toXZ(lat, lng))
  const m = l.ring.map(([lat, lng]) => elevAt(lat, lng)).sort((a, b) => a - b)
  const level = heightOfElev(m[Math.floor(m.length * 0.35)]) - 0.15 // the shore sits just above the water
  const xs = ring.map((p) => p[0]), zs = ring.map((p) => p[1])
  const box: [number, number, number, number] = [Math.min(...xs), Math.max(...xs), Math.min(...zs), Math.max(...zs)]
  return { name: l.name, ring, level, box, cx: (box[0] + box[1]) / 2, cz: (box[2] + box[3]) / 2 }
})

function inside(ring: [number, number][], x: number, z: number) {
  let c = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, zi] = ring[i], [xj, zj] = ring[j]
    if (zi > z !== zj > z && x < ((xj - xi) * (z - zi)) / (zj - zi) + xi) c = !c
  }
  return c
}
function edgeDist(ring: [number, number][], x: number, z: number) {
  let best = Infinity
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [ax, az] = ring[j], [bx, bz] = ring[i]
    const dx = bx - ax, dz = bz - az
    const t = Math.min(1, Math.max(0, ((x - ax) * dx + (z - az) * dz) / (dx * dx + dz * dz || 1)))
    best = Math.min(best, Math.hypot(x - ax - t * dx, z - az - t * dz))
  }
  return best
}
const SHORE = 1.1 // scene units over which the bank slopes into the water
// lake under (x, z): 1 inside, fading to 0 across the bank, with the lake's level
export function lakeNear(x: number, z: number): { m: number; level: number } {
  for (const l of LAKES) {
    const b = l.box
    if (x < b[0] - SHORE || x > b[1] + SHORE || z < b[2] - SHORE || z > b[3] + SHORE) continue
    if (inside(l.ring, x, z)) return { m: 1, level: l.level }
    const d = edgeDist(l.ring, x, z)
    if (d < SHORE) return { m: 1 - smoothstep(0, SHORE, d), level: l.level }
  }
  return { m: 0, level: 0 }
}
export const lakeAt = (x: number, z: number) => lakeNear(x, z).m

export function heightAt(x: number, z: number) {
  const [lat, lng] = toLatLng(x, z)
  let h = heightOfElev(elevAt(lat, lng)) + (fbm(x * 0.35 + 5, z * 0.35 + 2) - 0.5) * 0.5
  const lk = lakeNear(x, z)
  if (lk.m > 0) h = h * (1 - lk.m) + (lk.level - 0.7) * lk.m // the bed under the water sheet
  return h
}
// surface height where a pin can stand: on the water, never under it
export function groundAt(x: number, z: number) {
  const lk = lakeNear(x, z)
  const h = heightAt(x, z)
  return lk.m > 0.5 ? Math.max(h, lk.level) : h
}

export const cityCenter = LANDMARKS.centre

export const ROADS = osm.roads as { k: string; p: number[][] }[]
export const HOUSES = osm.houses as number[][]
