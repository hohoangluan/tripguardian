// Procedural Da Lat-like terrain: rolling pine hills around a lake basin.
// Deterministic so pins, pines and the route can sit exactly on the surface.

function hash(x: number, y: number) {
  let h = Math.imul(x, 374761393) + Math.imul(y, 668265263)
  h = Math.imul(h ^ (h >>> 13), 1274126177)
  return ((h ^ (h >>> 16)) >>> 0) / 4294967295
}

function valueNoise(x: number, y: number) {
  const xi = Math.floor(x)
  const yi = Math.floor(y)
  const xf = x - xi
  const yf = y - yi
  const u = xf * xf * (3 - 2 * xf)
  const v = yf * yf * (3 - 2 * yf)
  const a = hash(xi, yi)
  const b = hash(xi + 1, yi)
  const c = hash(xi, yi + 1)
  const d = hash(xi + 1, yi + 1)
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v
}

function fbm(x: number, y: number) {
  let sum = 0
  let amp = 0.5
  let freq = 1
  for (let i = 0; i < 5; i++) {
    sum += amp * valueNoise(x * freq, y * freq)
    freq *= 2.03
    amp *= 0.5
  }
  return sum
}

export const LAKE = { x: 3, z: -14, r: 11 }
export const TERRAIN = { width: 160, depth: 160, cx: 0, cz: -30 }

export function heightAt(x: number, z: number) {
  let h = fbm(x * 0.045 + 10, z * 0.045 + 3) * 14 - 4
  // Taller ridges towards the horizon frame the valley.
  const far = Math.max(0, -z - 40) / 40
  h += far * far * 10
  const side = Math.max(0, Math.abs(x) - 35) / 30
  h += side * side * 8
  // Lake basin.
  const d = Math.hypot(x - LAKE.x, (z - LAKE.z) * 1.3) / LAKE.r
  if (d < 1.6) h -= (1 - d / 1.6) ** 2 * 7
  return h
}

// Seeded PRNG for repeatable scatter.
export function rng(seed: number) {
  let s = seed >>> 0
  return () => {
    s = (s + 0x6d2b79f5) >>> 0
    let t = s
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export const WATER_Y = -0.6
