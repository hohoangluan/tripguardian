import * as THREE from 'three'
import { GRID, WORLD } from '../../src/user/landing/geo'
import { coverAt, fbm, groundAt, heightAt, HOUSES, inBounds, lakeAt, LAKES, LANDMARKS, ROADS, smoothstep, toLatLng, toXZ, TOWN_Y } from './gen'

// Bakes the Đà Lạt landscape into web/public/world/dalat.bin (see src/user/landing/terrain.ts for the layout).
// Run with `npm run bake:landscape`; the output is deterministic (seeded), so it only changes when the data or the
// palette below changes. The palette is the landing's soft rose system (css/landing.css).

const HORIZON = '#fbd9d6' // the colour the map edge melts into; matches the scene's fog
const BANDS: [number, string][] = [
  [0.5, '#f1d9d2'],
  [TOWN_Y - 0.4, '#f4d6d2'],
  [TOWN_Y + 1.2, '#ecc0c3'],
  [6.5, '#dba3b0'],
  [10, '#c487a0'],
  [15, '#a96d8c'],
  [26, '#e9cdd8'],
]
// land cover over the relief: forest, farmland and greenhouses, town, park
const COVER_TINT: Record<number, [string, number]> = { 1: ['#8a4f6c', 0.7], 2: ['#f7dde6', 0.65], 3: ['#f8e4dc', 0.7], 4: ['#f0bfc6', 0.55] }
const TREES = 15000
const ROAD_Q = 20 // road points in 5 cm steps
const HSCALE = 50 // heights in 0.02 steps

function rng(seed: number) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

type Section = { name: string; type: 'f32' | 'i16' | 'u16' | 'u8' | 'u32'; data: ArrayLike<number>; scale?: number }

function encode(sections: Section[], lakes: unknown) {
  const head = new TextEncoder().encode(JSON.stringify({ sections: sections.map((s) => ({ name: s.name, type: s.type, length: s.data.length, scale: s.scale })), lakes }))
  const size = (s: Section) => s.data.length * (s.type === 'u8' ? 1 : s.type === 'i16' || s.type === 'u16' ? 2 : 4)
  const pad = (n: number) => n + ((4 - (n % 4)) % 4)
  let total = pad(8 + head.length)
  for (const s of sections) total += pad(size(s))
  const out = new ArrayBuffer(total)
  const dv = new DataView(out)
  dv.setUint32(0, 0x54474c31)
  dv.setUint32(4, head.length)
  new Uint8Array(out, 8, head.length).set(head)
  let off = pad(8 + head.length)
  for (const s of sections) {
    const d = s.data
    if (s.type === 'f32') new Float32Array(out, off, d.length).set(d as ArrayLike<number>)
    else if (s.type === 'u32') new Uint32Array(out, off, d.length).set(d as ArrayLike<number>)
    else if (s.type === 'u8') new Uint8Array(out, off, d.length).set(d as ArrayLike<number>)
    else if (s.type === 'u16') {
      const a = new Uint16Array(out, off, d.length)
      for (let i = 0; i < d.length; i++) a[i] = Math.round(d[i] * (s.scale ?? 1))
    } else {
      const a = new Int16Array(out, off, d.length)
      for (let i = 0; i < d.length; i++) a[i] = Math.round(d[i] * (s.scale ?? 1))
    }
    off += pad(size(s))
  }
  return new Uint8Array(out)
}

export function bakeLandscape() {
  const { nx, nz } = GRID
  const cols = nx + 1, rows = nz + 1
  const height = new Float32Array(cols * rows), ground = new Float32Array(cols * rows), color = new Uint8Array(cols * rows * 3)
  const c = new THREE.Color(), c1 = new THREE.Color(), tint = new THREE.Color(), fade = new THREE.Color(HORIZON), pine = new THREE.Color(COVER_TINT[1][0])
  const bands = BANDS.map(([h, hex]) => [h, new THREE.Color(hex)] as const)
  const rgb = { r: 0, g: 0, b: 0 }
  let maxH = 0
  for (let iz = 0; iz < rows; iz++) {
    for (let ix = 0; ix < cols; ix++) {
      const x = (ix / nx) * WORLD.w - WORLD.w / 2, z = (iz / nz) * WORLD.d - WORLD.d / 2
      const i = iz * cols + ix
      const h = heightAt(x, z)
      height[i] = h
      ground[i] = groundAt(x, z)
      maxH = Math.max(maxH, Math.abs(h))
      if (h <= bands[0][0]) c.copy(bands[0][1])
      else {
        c.copy(bands[bands.length - 1][1])
        for (let b = 1; b < bands.length; b++) {
          if (h <= bands[b][0]) {
            c.copy(bands[b - 1][1]).lerp(c1.copy(bands[b][1]), (h - bands[b - 1][0]) / (bands[b][0] - bands[b - 1][0]))
            break
          }
        }
      }
      // land cover from the map; hills with no tag still carry Đà Lạt's pines where the ground is not worked
      const [hex, amount] = COVER_TINT[coverAt(x, z)] ?? ['#000000', 0]
      if (amount) c.lerp(tint.set(hex), amount * (0.8 + 0.2 * fbm(x * 0.5, z * 0.5)))
      else if (h > TOWN_Y + 0.4) c.lerp(pine, 0.55 * smoothstep(0.42, 0.62, fbm(x * 0.07 + 20, z * 0.07 + 3)))
      c.offsetHSL(0, 0, (fbm(x * 0.8, z * 0.8) - 0.5) * 0.04)
      // the edge of the map melts into the horizon, so the world has no visible end
      const edge = Math.min(WORLD.w / 2 - Math.abs(x), WORLD.d / 2 - Math.abs(z))
      c.lerp(fade, 1 - smoothstep(0, 38, edge))
      c.getRGB(rgb, THREE.SRGBColorSpace)
      color[i * 3] = Math.round(rgb.r * 255)
      color[i * 3 + 1] = Math.round(rgb.g * 255)
      color[i * 3 + 2] = Math.round(rgb.b * 255)
    }
  }
  if (maxH > 30) throw new Error(`height ${maxH} does not fit the int16 scale`)
  // Neighbouring vertices are alike: store each against the one to its left (or above, at a row start), which
  // compresses far better than the raw values. terrain.ts undoes it.
  const hq = new Int16Array(cols * rows), hd = new Int16Array(cols * rows), cd = new Uint8Array(cols * rows * 3)
  for (let i = 0; i < hq.length; i++) hq[i] = Math.round(height[i] * HSCALE)
  // colours keep their top 6 bits: the per-vertex grain below that costs bytes and cannot be seen
  const cq = color.map((v) => Math.min(255, (v + 2) & 0xfc))
  for (let iz = 0; iz < rows; iz++)
    for (let ix = 0; ix < cols; ix++) {
      const i = iz * cols + ix, pi = ix ? i - 1 : iz ? i - cols : -1
      hd[i] = hq[i] - (pi < 0 ? 0 : hq[pi])
      for (let c = 0; c < 3; c++) cd[i * 3 + c] = (cq[i * 3 + c] - (pi < 0 ? 0 : cq[pi * 3 + c])) & 255
    }

  // pines: where the map says forest, and on the unworked hills around the town
  const rnd = rng(20261008)
  const treeXZ = new Float32Array(TREES * 2)
  const reach = { x: WORLD.w / 2 - 20, z: WORLD.d / 2 - 20 }
  let nt = 0
  for (let tries = 0; tries < TREES * 14 && nt < TREES; tries++) {
    const x = (rnd() * 2 - 1) * reach.x, z = (rnd() * 2 - 1) * reach.z
    const h = heightAt(x, z)
    if (lakeAt(x, z) > 0.02 || h < TOWN_Y - 3) continue
    const cv = coverAt(x, z)
    const chance = cv === 1 ? 1 : cv === 0 ? 0.85 * smoothstep(0.4, 0.58, fbm(x * 0.07 + 20, z * 0.07 + 3)) : 0
    if (rnd() > chance) continue
    treeXZ.set([x, z], nt * 2)
    nt++
  }

  // villas at the mapped buildings
  const houseXZ: number[] = []
  for (const [lat, lng] of HOUSES) {
    if (!inBounds(lat, lng)) continue
    const [x, z] = toXZ(lat, lng)
    if (lakeAt(x, z) > 0.02) continue
    houseXZ.push(x, z)
  }

  // cherry trees along the shores of the lakes in the valley (a bank is ~1 unit wide, so they stand just beyond it)
  // and scattered through the town
  const spots: [number, number][] = []
  for (const lake of LAKES) {
    const [la, ln] = toLatLng(lake.cx, lake.cz)
    if (!inBounds(la, ln) || lake.ring.length < 8) continue
    const step = Math.max(1, Math.floor(lake.ring.length / 26))
    for (let i = 0; i < lake.ring.length; i += step) {
      const [x, z] = lake.ring[i]
      const dx = x - lake.cx, dz = z - lake.cz, len = Math.hypot(dx, dz) || 1
      const off = 1.5 + ((i * 7) % 5) * 0.25
      spots.push([x + (dx / len) * off, z + (dz / len) * off])
    }
  }
  const shore = spots.length
  for (const [lat, lng] of HOUSES) {
    if (spots.length - shore > 420) break
    if ((lat * 9973 + lng * 7919) % 1 < 0.82) continue
    const [x, z] = toXZ(lat, lng)
    spots.push([x + 0.3, z + 0.3])
  }
  const blossomXZ: number[] = []
  for (const [x, z] of spots) {
    if (lakeAt(x, z) > 0.05 || !inBounds(...toLatLng(x, z))) continue
    blossomXZ.push(x, z)
  }

  // main roads: the centre line of each (the browser lays the ribbon on the ground), 5 cm precision, stored as steps
  const widthOf: Record<string, number> = { trunk: 34, primary: 30, secondary: 22, tertiary: 16 } // hundredths of a unit
  const roadD: number[] = [], roadRuns: number[] = [], roadW: number[] = []
  let px0 = 0, pz0 = 0
  for (const r of ROADS) {
    const line = r.p.map(([lat, lng]) => toXZ(lat, lng)).filter(([x, z]) => Math.abs(x) < WORLD.w / 2 - 4 && Math.abs(z) < WORLD.d / 2 - 4)
    if (line.length < 2) continue
    for (const [x, z] of line) {
      const qx = Math.round(x * ROAD_Q), qz = Math.round(z * ROAD_Q)
      roadD.push(qx - px0, qz - pz0)
      px0 = qx
      pz0 = qz
    }
    roadRuns.push(line.length)
    roadW.push(widthOf[r.k] ?? 16)
  }

  // every lake triangulated: x, z in hundredths (the level is per lake, in the header), `waterRuns` vertices per lake
  const waterXZ: number[] = [], waterRuns: number[] = [], waterIdx: number[] = []
  const lakes: { level: number; box: number[]; cx: number; cz: number }[] = []
  for (const lake of LAKES) {
    if (lake.ring.length < 4) continue
    const [x0, x1, z0, z1] = lake.box
    // a lake across the map edge would float past the ground: keep only those fully inside
    if (x0 < -WORLD.w / 2 + 2 || x1 > WORLD.w / 2 - 2 || z0 < -WORLD.d / 2 + 2 || z1 > WORLD.d / 2 - 2) continue
    let pts = lake.ring.map(([x, z]) => new THREE.Vector2(x, -z))
    if (!THREE.ShapeUtils.isClockWise(pts)) pts = pts.reverse()
    const base = waterXZ.length / 2
    for (const p of pts) waterXZ.push(p.x, -p.y)
    for (const f of THREE.ShapeUtils.triangulateShape(pts, [])) waterIdx.push(base + f[0], base + f[1], base + f[2])
    waterRuns.push(pts.length)
    lakes.push({ level: lake.level, box: lake.box, cx: lake.cx, cz: lake.cz })
  }
  if (waterXZ.length / 2 > 65535) throw new Error('too many lake vertices for u16 indices')

  // ground equals the height except on lake cells, which stand at their water level: store only those
  const gIdx: number[] = [], gVal: number[] = []
  for (let i = 0; i < ground.length; i++) if (Math.abs(ground[i] - height[i]) > 0.0005) { gIdx.push(i); gVal.push(ground[i]) }

  void LANDMARKS
  const out = encode([
    { name: 'heightD', type: 'i16', data: hd },
    { name: 'groundIdx', type: 'u32', data: gIdx },
    { name: 'groundVal', type: 'i16', data: gVal, scale: 1000 },
    { name: 'colorD', type: 'u8', data: cd },
    { name: 'treeXZ', type: 'i16', data: treeXZ.subarray(0, nt * 2), scale: 20 },
    { name: 'houseXZ', type: 'i16', data: houseXZ, scale: 20 },
    { name: 'blossomXZ', type: 'i16', data: blossomXZ, scale: 20 },
    { name: 'roadD', type: 'i16', data: roadD },
    { name: 'roadRuns', type: 'u16', data: roadRuns },
    { name: 'roadW', type: 'u8', data: roadW },
    { name: 'waterXZ', type: 'i16', data: waterXZ, scale: 100 },
    { name: 'waterRuns', type: 'u16', data: waterRuns },
    { name: 'waterIdx', type: 'u16', data: waterIdx },
  ], lakes)
  console.log(`trees ${nt}, houses ${houseXZ.length / 2}, blossoms ${blossomXZ.length / 2}, road points ${roadD.length / 2}, lakes ${lakes.length}, lake cells ${gIdx.length}, water tris ${waterIdx.length / 3}`)
  return out
}
