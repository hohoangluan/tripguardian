import { useFrame } from '@react-three/fiber'
import { useMemo, useRef } from 'react'
import * as THREE from 'three'
import { BAD_ORDER, CHOSEN, GOOD_ORDER, routeCurve } from './places'
import { heightAt } from './heightfield'
import { smooth, span, story } from './story'

const SEGMENTS = 400
const RADIAL = 6

function tube(order: number[]) {
  return new THREE.TubeGeometry(routeCurve(order), SEGMENTS, 0.16, RADIAL, false)
}

// Reveal a tube from its start: TubeGeometry indices run along the path.
function reveal(g: THREE.TubeGeometry, t: number) {
  g.setDrawRange(0, Math.floor(SEGMENTS * t) * RADIAL * 6)
}

export function Route({ scene }: { scene: { p: number } }) {
  const bad = useMemo(() => tube(BAD_ORDER), [])
  const good = useMemo(() => tube(GOOD_ORDER), [])
  const badMat = useRef<THREE.MeshBasicMaterial>(null)
  const ring = useRef<THREE.Mesh>(null)

  // The conflict sits on the place reached too late in the bad order.
  const conflict = CHOSEN[2]
  const conflictY = heightAt(conflict.x, conflict.z) + 0.3

  useFrame(({ clock }) => {
    const p = scene.p
    const t = story.reducedMotion ? 0 : clock.elapsedTime
    const badDraw = smooth(span(p, 0.64, 0.74))
    const badFade = 1 - smooth(span(p, 0.83, 0.87))
    reveal(bad, badDraw)
    reveal(good, smooth(span(p, 0.85, 0.94)))
    if (badMat.current) badMat.current.opacity = 0.9 * badFade
    if (ring.current) {
      const on = span(p, 0.72, 0.75) * badFade
      const pulse = 1 + ((t * 1.2) % 1) * 1.6
      ring.current.scale.setScalar(Math.max(on * pulse, 0.0001))
      ;(ring.current.material as THREE.MeshBasicMaterial).opacity = on * (1 - ((t * 1.2) % 1))
    }
  })

  return (
    <group>
      <mesh geometry={bad}>
        <meshBasicMaterial ref={badMat} color="#c0533f" transparent toneMapped={false} fog={false} />
      </mesh>
      <mesh geometry={good}>
        <meshBasicMaterial color="#f2b31b" toneMapped={false} fog={false} />
      </mesh>
      <mesh ref={ring} position={[conflict.x, conflictY, conflict.z]} rotation-x={-Math.PI / 2}>
        <ringGeometry args={[1.2, 1.45, 48]} />
        <meshBasicMaterial color="#c0533f" transparent depthWrite={false} toneMapped={false} />
      </mesh>
    </group>
  )
}
