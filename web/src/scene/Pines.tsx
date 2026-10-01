import { useLayoutEffect, useMemo, useRef } from 'react'
import * as THREE from 'three'
import { CHOSEN } from './places'
import { heightAt, rng, WATER_Y } from './heightfield'

const COUNT = 2600

export function Pines() {
  const ref = useRef<THREE.InstancedMesh>(null)

  const geometry = useMemo(() => {
    // Two stacked cones read as a pine at low poly.
    const lower = new THREE.ConeGeometry(0.62, 1.6, 6)
    lower.translate(0, 0.8, 0)
    const upper = new THREE.ConeGeometry(0.42, 1.3, 6)
    upper.translate(0, 1.75, 0)
    const merged = new THREE.BufferGeometry()
    const a = lower.toNonIndexed()
    const b = upper.toNonIndexed()
    const pos = new Float32Array(a.attributes.position.array.length + b.attributes.position.array.length)
    pos.set(a.attributes.position.array as Float32Array, 0)
    pos.set(b.attributes.position.array as Float32Array, a.attributes.position.array.length)
    merged.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    merged.computeVertexNormals()
    return merged
  }, [])

  useLayoutEffect(() => {
    const mesh = ref.current
    if (!mesh) return
    const rand = rng(42)
    const m = new THREE.Matrix4()
    const q = new THREE.Quaternion()
    const s = new THREE.Vector3()
    const p = new THREE.Vector3()
    const c = new THREE.Color()
    const up = new THREE.Vector3(0, 1, 0)
    let n = 0
    let guard = 0
    while (n < COUNT && guard++ < COUNT * 20) {
      const x = (rand() - 0.5) * 150
      const z = -30 + (rand() - 0.5) * 150
      const h = heightAt(x, z)
      if (h < WATER_Y + 0.9) continue
      // Patchy forests with clearings, like the hills around Da Lat.
      const mask = Math.sin(x * 0.11) + Math.cos(z * 0.09 + x * 0.04) + Math.sin((x + z) * 0.05)
      if (mask < -0.4) continue
      if (z > 16 && Math.abs(x) < 16) continue
      if (CHOSEN.some((pl) => Math.hypot(pl.x - x, pl.z - z) < 2.2)) continue
      const k = 0.7 + rand() * 0.9 + Math.max(0, h) * 0.02
      p.set(x, h - 0.1, z)
      q.setFromAxisAngle(up, rand() * Math.PI * 2)
      s.set(k, k * (0.9 + rand() * 0.5), k)
      m.compose(p, q, s)
      mesh.setMatrixAt(n, m)
      c.setHSL(0.42 + rand() * 0.05, 0.28 + rand() * 0.12, 0.13 + rand() * 0.07)
      mesh.setColorAt(n, c)
      n++
    }
    mesh.count = n
    mesh.instanceMatrix.needsUpdate = true
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
  }, [])

  return (
    <instancedMesh ref={ref} args={[geometry, undefined, COUNT]}>
      <meshStandardMaterial flatShading roughness={1} />
    </instancedMesh>
  )
}
