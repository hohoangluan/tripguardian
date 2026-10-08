import { GRID, WORLD } from './geo'

// The baked Đà Lạt landscape (web/public/world/dalat.bin, made by `npm run bake:landscape` from SRTM elevation and
// OpenStreetMap): ground heights and colours, tree / house / blossom placements, road ribbons and lake meshes.
// Everything heavy is computed offline; here the browser only decodes typed arrays and samples the height grid.

export interface Lake { level: number; box: [number, number, number, number]; cx: number; cz: number }
export interface Landscape {
  cols: number
  rows: number
  height: Float32Array // cols × rows, row 0 = north edge
  ground: Float32Array // same grid; lake cells at their water level (where a pin can stand)
  color: Uint8Array // sRGB per vertex
  trees: Float32Array // x, z, width scale, height scale, turn (5 per tree)
  treeTone: Uint8Array
  houses: Float32Array
  houseTone: Uint8Array
  blossoms: Float32Array
  blossomTone: Uint8Array
  roadXZ: Float32Array // centre line points, x, z
  roadRuns: Uint16Array // points per road
  roadW: Float32Array // ribbon width per road
  waterPos: Float32Array // x, y, z; one mesh for every lake
  waterIdx: Uint16Array
  lakes: Lake[]
}

interface Header { sections: { name: string; type: 'f32' | 'i16' | 'u16' | 'u8' | 'u32'; length: number; scale?: number }[]; lakes: Lake[] }

const pad = (n: number) => n + ((4 - (n % 4)) % 4)
const HSCALE = 50 // heights are stored in 0.02 steps (scripts/landscape/bake.ts)
const ROAD_Q = 20 // road points in 5 cm steps

// Seeded, so every visitor sees the same valley: the sizes and turns of trees and houses are not stored.
function mulberry32(seed: number) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export function decodeLandscape(buf: ArrayBuffer): Landscape {
  const dv = new DataView(buf)
  if (dv.getUint32(0) !== 0x54474c31) throw new Error('not a landscape file') // "TGL1"
  const hl = dv.getUint32(4)
  const header = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 8, hl))) as Header
  let off = pad(8 + hl)
  const f: Record<string, Float32Array | Uint8Array | Uint32Array | Uint16Array | Int16Array> = {}
  for (const s of header.sections) {
    const n = s.length
    if (s.type === 'f32') f[s.name] = new Float32Array(buf, off, n), (off += n * 4)
    else if (s.type === 'u32') f[s.name] = new Uint32Array(buf, off, n), (off += n * 4)
    else if (s.type === 'u16') f[s.name] = new Uint16Array(buf, off, n), (off += n * 2)
    else if (s.type === 'u8') f[s.name] = new Uint8Array(buf, off, n), (off += n)
    else {
      const raw = new Int16Array(buf, off, n)
      if (s.scale) {
        const out = new Float32Array(n)
        for (let i = 0; i < n; i++) out[i] = raw[i] / s.scale
        f[s.name] = out
      } else f[s.name] = raw
      off += n * 2
    }
    off = pad(off)
  }
  const { cols, rows } = { cols: GRID.nx + 1, rows: GRID.nz + 1 }

  // heights and colours were stored as steps from the vertex to the left (or above, at a row start)
  const hd = f.heightD as Int16Array, cd = f.colorD as Uint8Array
  const height = new Float32Array(cols * rows), color = new Uint8Array(cols * rows * 3)
  const hq = new Int32Array(cols * rows)
  for (let iz = 0, i = 0; iz < rows; iz++)
    for (let ix = 0; ix < cols; ix++, i++) {
      const pi = ix ? i - 1 : iz ? i - cols : -1
      hq[i] = hd[i] + (pi < 0 ? 0 : hq[pi])
      height[i] = hq[i] / HSCALE
      for (let c = 0; c < 3; c++) color[i * 3 + c] = (cd[i * 3 + c] + (pi < 0 ? 0 : color[pi * 3 + c])) & 255
    }
  const ground = height.slice()
  const gi = f.groundIdx as Uint32Array, gv = f.groundVal as Float32Array
  for (let i = 0; i < gi.length; i++) ground[gi[i]] = gv[i]

  // instances: positions are stored; sizes, turns and tones come from a seeded generator
  const inst = (xz: Float32Array, seed: number, size: [number, number], tall: number, tones: number) => {
    const n = xz.length / 2, a = new Float32Array(n * 5), tone = new Uint8Array(n)
    const r = mulberry32(seed)
    for (let i = 0; i < n; i++) {
      const sc = size[0] + r() * size[1]
      a.set([xz[i * 2], xz[i * 2 + 1], sc, tall ? sc * (0.95 + r() * tall) : sc, r() * Math.PI], i * 5)
      tone[i] = i % tones
    }
    return { a, tone }
  }
  const trees = inst(f.treeXZ as Float32Array, 11, [0.42, 0.46], 0.7, 5)
  const houses = inst(f.houseXZ as Float32Array, 12, [0.8, 0.5], 0, 4)
  const blossoms = inst(f.blossomXZ as Float32Array, 13, [0.75, 0.7], 0, 5)

  // roads: back from steps to points
  const rd = f.roadD as Int16Array, roadXZ = new Float32Array(rd.length)
  for (let i = 0, x = 0, z = 0; i < rd.length; i += 2) {
    x += rd[i]
    z += rd[i + 1]
    roadXZ[i] = x / ROAD_Q
    roadXZ[i + 1] = z / ROAD_Q
  }
  const roadW = Float32Array.from(f.roadW as Uint8Array, (w) => w / 100)

  // lakes: each at its own level
  const wxz = f.waterXZ as Float32Array, wr = f.waterRuns as Uint16Array
  const waterPos = new Float32Array((wxz.length / 2) * 3)
  for (let li = 0, v = 0; li < wr.length; li++)
    for (let k = 0; k < wr[li]; k++, v++) waterPos.set([wxz[v * 2], header.lakes[li].level, wxz[v * 2 + 1]], v * 3)

  return {
    cols, rows, height, ground, color,
    trees: trees.a, treeTone: trees.tone, houses: houses.a, houseTone: houses.tone, blossoms: blossoms.a, blossomTone: blossoms.tone,
    roadXZ, roadRuns: f.roadRuns as Uint16Array, roadW, waterPos, waterIdx: f.waterIdx as Uint16Array, lakes: header.lakes,
  }
}

let land: Landscape | null = null
export const setLandscape = (l: Landscape) => { land = l }
export const landscape = () => land!

function sample(g: Float32Array, x: number, z: number) {
  const { cols, rows } = land!
  const fc = Math.min(cols - 1.001, Math.max(0, ((x + WORLD.w / 2) / WORLD.w) * (cols - 1)))
  const fr = Math.min(rows - 1.001, Math.max(0, ((z + WORLD.d / 2) / WORLD.d) * (rows - 1)))
  const c = Math.floor(fc), r = Math.floor(fr), u = fc - c, v = fr - r
  const i = r * cols + c
  return g[i] * (1 - u) * (1 - v) + g[i + 1] * u * (1 - v) + g[i + cols] * (1 - u) * v + g[i + cols + 1] * u * v
}
export const heightAt = (x: number, z: number) => sample(land!.height, x, z)
// surface height where a pin can stand: on the water, never under it
export const groundAt = (x: number, z: number) => sample(land!.ground, x, z)
