import { Html } from '@react-three/drei'
import { useFrame } from '@react-three/fiber'
import { useMemo, useRef } from 'react'
import * as THREE from 'three'
import { buildPins, CHOSEN } from './places'
import { smooth, span, story } from './story'

const FEED = new THREE.Color('#3a6a78')
const WHITE = new THREE.Color('#f4f6f2')
const VIOLET = new THREE.Color('#9a7cc9')
const YELLOW = new THREE.Color('#f2b31b')
const DIM = new THREE.Color('#56706a')

export function Pins({ scene }: { scene: { p: number } }) {
  const pins = useMemo(buildPins, [])
  const mesh = useRef<THREE.InstancedMesh>(null)
  const beams = useRef<(THREE.Mesh | null)[]>([])
  const labels = useRef<(HTMLDivElement | null)[]>([])

  const geometry = useMemo(() => {
    const g = new THREE.OctahedronGeometry(0.5, 0)
    g.scale(1, 1.7, 1)
    return g
  }, [])

  const tmp = useMemo(
    () => ({ m: new THREE.Matrix4(), q: new THREE.Quaternion(), s: new THREE.Vector3(), v: new THREE.Vector3(), c: new THREE.Color(), e: new THREE.Euler() }),
    [],
  )

  useFrame(({ clock }) => {
    const p = scene.p
    const t = story.reducedMotion ? 0 : clock.elapsedTime
    const appear = smooth(span(p, 0.08, 0.2))
    const verify = smooth(span(p, 0.36, 0.46))
    const choose = smooth(span(p, 0.52, 0.62))
    const { m, q, s, v, c, e } = tmp
    const im = mesh.current
    if (!im) return

    pins.forEach((pin, i) => {
      const drop = smooth(span(p, 0.24 + pin.delay * 0.08, 0.32 + pin.delay * 0.08))
      v.lerpVectors(pin.air, pin.ground, drop)
      v.y += Math.sin(drop * Math.PI) * 2.5 + Math.sin(t * 0.9 + i) * 0.5 * (1 - drop)

      let k = appear
      if (pin.status === 'review') k *= 1 - verify
      k *= 0.7 + 0.65 * drop * (pin.chosen < 0 ? 1 - 0.5 * choose : 1 + 0.6 * choose)

      c.copy(FEED).lerp(pin.status === 'uncertain' ? VIOLET : WHITE, verify)
      if (pin.chosen >= 0) c.lerp(YELLOW, choose)
      else c.lerp(DIM, choose * 0.7)

      e.set(0, t * 0.7 + i, (1 - drop) * Math.sin(t * 0.5 + i) * 0.4)
      q.setFromEuler(e)
      s.setScalar(Math.max(k, 0.0001))
      m.compose(v, q, s)
      im.setMatrixAt(i, m)
      im.setColorAt(i, c)
    })
    im.instanceMatrix.needsUpdate = true
    if (im.instanceColor) im.instanceColor.needsUpdate = true

    // Light columns mark the shortlist; labels arrive with the itinerary.
    // Landing labels name demo places; never show them behind the real app.
    const labelIn = story.mode === 'landing' ? smooth(span(p, 0.92, 0.98)) : 0
    CHOSEN.forEach((_, i) => {
      const beam = beams.current[i]
      if (beam) {
        const mat = beam.material as THREE.MeshBasicMaterial
        mat.opacity = choose * (0.35 + 0.1 * Math.sin(t * 2 + i))
        beam.scale.y = Math.max(choose, 0.0001)
      }
      const label = labels.current[i]
      if (label) {
        label.style.opacity = String(labelIn)
        label.style.transform = `translateY(${(1 - labelIn) * 8}px)`
      }
    })
  })

  return (
    <group>
      <instancedMesh ref={mesh} args={[geometry, undefined, pins.length]} frustumCulled={false}>
        <meshBasicMaterial toneMapped={false} fog={false} />
      </instancedMesh>
      {CHOSEN.map((place, i) => {
        const g = pins[i].ground
        return (
          <group key={place.name} position={[g.x, g.y, g.z]}>
            <mesh ref={(el) => void (beams.current[i] = el)} position={[0, 2.6, 0]}>
              <cylinderGeometry args={[0.05, 0.22, 5.2, 8, 1, true]} />
              <meshBasicMaterial color="#f2b31b" transparent depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false} fog={false} />
            </mesh>
            <Html position={[0, 2.2, 0]} center zIndexRange={[5, 0]} style={{ pointerEvents: 'none' }}>
              <div className="place-label" ref={(el) => void (labels.current[i] = el)} style={{ opacity: 0 }}>
                <span className="place-label__time">{place.time}</span>
                <span className="place-label__name">{place.name}</span>
              </div>
            </Html>
          </group>
        )
      })}
    </group>
  )
}
