import { useMemo } from 'react'
import * as THREE from 'three'
import { heightAt, LAKE, TERRAIN, WATER_Y } from './heightfield'

const BANDS: [number, THREE.Color][] = [
  [WATER_Y + 0.2, new THREE.Color('#e8cfc6')], // shore
  [1.5, new THREE.Color('#dcb6ae')], // meadow
  [5, new THREE.Color('#b98c92')], // pine slope
  [11, new THREE.Color('#7e5a68')], // deep forest
  [18, new THREE.Color('#c9a7ae')], // misty crest
]

function colorFor(h: number, out: THREE.Color) {
  if (h <= BANDS[0][0]) return out.copy(BANDS[0][1])
  for (let i = 1; i < BANDS.length; i++) {
    const [h1, c1] = BANDS[i]
    if (h <= h1) {
      const [h0, c0] = BANDS[i - 1]
      return out.copy(c0).lerp(c1, (h - h0) / (h1 - h0))
    }
  }
  return out.copy(BANDS[BANDS.length - 1][1])
}

export function Terrain() {
  const geometry = useMemo(() => {
    const g = new THREE.PlaneGeometry(TERRAIN.width, TERRAIN.depth, 150, 150)
    g.rotateX(-Math.PI / 2)
    g.translate(TERRAIN.cx, 0, TERRAIN.cz)
    const pos = g.attributes.position as THREE.BufferAttribute
    const colors = new Float32Array(pos.count * 3)
    const c = new THREE.Color()
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i)
      const z = pos.getZ(i)
      const h = heightAt(x, z)
      pos.setY(i, h)
      colorFor(h, c)
      // Small per-vertex jitter breaks up banding on the facets.
      const j = (Math.sin(x * 12.9898 + z * 78.233) * 43758.5453) % 1
      c.offsetHSL(0, 0, j * 0.025)
      c.toArray(colors, i * 3)
    }
    g.setAttribute('color', new THREE.BufferAttribute(colors, 3))
    g.computeVertexNormals()
    return g
  }, [])

  return (
    <group>
      <mesh geometry={geometry}>
        <meshStandardMaterial vertexColors flatShading roughness={0.95} metalness={0} />
      </mesh>
      <mesh rotation-x={-Math.PI / 2} position={[LAKE.x, WATER_Y, LAKE.z]}>
        <circleGeometry args={[LAKE.r * 2.2, 64]} />
        <meshStandardMaterial color="#f3dde0" roughness={0.12} metalness={0.25} />
      </mesh>
    </group>
  )
}
