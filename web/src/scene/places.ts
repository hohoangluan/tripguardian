import * as THREE from 'three'
import { heightAt, rng, WATER_Y } from './heightfield'

export type PinStatus = 'verified' | 'uncertain' | 'review'

export interface Pin {
  ground: THREE.Vector3
  air: THREE.Vector3
  status: PinStatus
  chosen: number // index into CHOSEN, or -1
  delay: number // 0..1 stagger for drop animation
}

// The five places the demo user ends up with, in itinerary order.
// Scene positions are stylised, not geographic.
export const CHOSEN = [
  { name: 'Thiền viện Trúc Lâm', time: 'Ngày 1, 07:30', x: -15, z: -6 },
  { name: 'Hồ Tuyền Lâm', time: 'Ngày 1, 09:30', x: -7, z: -28 },
  { name: 'Đồi chè Cầu Đất', time: 'Ngày 2, 06:00', x: 15, z: -32 },
  { name: 'Quảng trường Lâm Viên', time: 'Ngày 2, 16:30', x: 21, z: -8 },
  { name: 'Chợ Đà Lạt', time: 'Ngày 2, 19:00', x: 6, z: 3 },
]

// Order tried first in the feasibility beat: it crosses the valley twice.
export const BAD_ORDER = [0, 2, 1, 3, 4]
export const GOOD_ORDER = [0, 1, 2, 3, 4]

const PIN_COUNT = 60

function onLand(x: number, z: number) {
  return heightAt(x, z) > WATER_Y + 0.6
}

export function buildPins(): Pin[] {
  const rand = rng(7)
  const pins: Pin[] = []
  CHOSEN.forEach((c, i) => {
    pins.push(makePin(c.x, c.z, 'verified', i, rand))
  })
  while (pins.length < PIN_COUNT) {
    const x = (rand() - 0.5) * 60
    const z = -12 + (rand() - 0.5) * 56
    if (!onLand(x, z)) continue
    if (pins.some((p) => Math.hypot(p.ground.x - x, p.ground.z - z) < 3.2)) continue
    const r = rand()
    const status: PinStatus = r < 0.6 ? 'verified' : r < 0.88 ? 'uncertain' : 'review'
    pins.push(makePin(x, z, status, -1, rand))
  }
  return pins
}

function makePin(x: number, z: number, status: PinStatus, chosen: number, rand: () => number): Pin {
  const ground = new THREE.Vector3(x, heightAt(x, z) + 1.1, z)
  // Floating "feed" cloud in front of the second camera stop.
  const air = new THREE.Vector3(
    (rand() - 0.5) * 34,
    9 + rand() * 14,
    -4 + (rand() - 0.5) * 26,
  )
  return { ground, air, status, chosen, delay: rand() }
}

// A path that hugs the terrain between consecutive places.
export function routeCurve(order: number[]) {
  const pts: THREE.Vector3[] = []
  for (let i = 0; i < order.length - 1; i++) {
    const a = CHOSEN[order[i]]
    const b = CHOSEN[order[i + 1]]
    const steps = 14
    for (let s = 0; s < steps; s++) {
      const t = s / steps
      // Bow the segment sideways so roads read as roads, not rulers.
      const nx = -(b.z - a.z)
      const nz = b.x - a.x
      const bow = Math.sin(t * Math.PI) * 0.18
      const x = a.x + (b.x - a.x) * t + nx * bow
      const z = a.z + (b.z - a.z) * t + nz * bow
      pts.push(new THREE.Vector3(x, Math.max(heightAt(x, z), WATER_Y) + 0.45, z))
    }
  }
  const last = CHOSEN[order[order.length - 1]]
  pts.push(new THREE.Vector3(last.x, heightAt(last.x, last.z) + 0.45, last.z))
  return new THREE.CatmullRomCurve3(pts, false, 'centripetal')
}
