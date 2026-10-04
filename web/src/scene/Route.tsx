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
    // Beat 4 (feasibility): the first order crosses the valley twice and runs late; beat 5: the fixed route.
    const badDraw = smooth(span(p, 0.58, 0.65))
    const badFade = 1 - smooth(span(p, 0.7, 0.74))
    reveal(bad, badDraw)
    reveal(good, smooth(span(p, 0.74, 0.84)))
    if (badMat.current) badMat.current.opacity = 0.9 * badFade
    if (ring.current) {
      const on = span(p, 0.63, 0.67) * badFade
      const pulse = 1 + ((t * 1.2) % 1) * 1.6
      ring.current.scale.setScalar(Math.max(on * pulse, 0.0001))
      ;(ring.current.material as THREE.MeshBasicMaterial).opacity = on * (1 - ((t * 1.2) % 1))
    }
  })

  return (
    <group>
      <mesh geometry={bad}>
        <meshBasicMaterial ref={badMat} color="#b06a12" transparent toneMapped={false} fog={false} />
      </mesh>
      <mesh geometry={good}>
        <meshBasicMaterial color="#c97890" toneMapped={false} fog={false} />
      </mesh>
      <mesh ref={ring} position={[conflict.x, conflictY, conflict.z]} rotation-x={-Math.PI / 2}>
        <ringGeometry args={[1.2, 1.45, 48]} />
        <meshBasicMaterial color="#b06a12" transparent depthWrite={false} toneMapped={false} />
      </mesh>
    </group>
  )
}
