import { useFrame } from '@react-three/fiber'
import { useMemo, useRef } from 'react'
import * as THREE from 'three'
import { rng } from './heightfield'
import { story } from './story'

function softDot() {
  const size = 64
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = size
  const ctx = canvas.getContext('2d')!
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
  g.addColorStop(0, 'rgba(255,255,255,1)')
  g.addColorStop(1, 'rgba(255,255,255,0)')
  ctx.fillStyle = g
  ctx.fillRect(0, 0, size, size)
  return new THREE.CanvasTexture(canvas)
}

// Drifting mist banks. Thins out as the plan comes together.
export function Mist({ scene }: { scene: { p: number } }) {
  const group = useRef<THREE.Group>(null)
  const material = useRef<THREE.PointsMaterial>(null)

  const [geometry, texture] = useMemo(() => {
    const rand = rng(3)
    const n = 520
    const pos = new Float32Array(n * 3)
    for (let i = 0; i < n; i++) {
      pos[i * 3] = (rand() - 0.5) * 130
      pos[i * 3 + 1] = 1 + rand() * 16
      pos[i * 3 + 2] = -30 + (rand() - 0.5) * 140
    }
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    return [g, softDot()]
  }, [])

  useFrame(({ clock }) => {
    const t = story.reducedMotion ? 0 : clock.elapsedTime
    if (group.current) {
      group.current.position.x = Math.sin(t * 0.04) * 6
      group.current.position.z = Math.cos(t * 0.03) * 3
    }
    if (material.current) {
      material.current.opacity = story.reducedMotion ? 0 : 0.42 * (1 - scene.p * 0.75) + story.dive * 0.4
    }
  })

  return (
    <group ref={group}>
      <points geometry={geometry}>
        <pointsMaterial
          ref={material}
          map={texture}
          size={16}
          sizeAttenuation
          transparent
          depthWrite={false}
          color="#fcedec"
        />
      </points>
    </group>
  )
}
