import { Html } from '@react-three/drei'
import { useFrame } from '@react-three/fiber'
import { useMemo, useRef } from 'react'
import * as THREE from 'three'
import { buildPins, CHOSEN } from './places'
import { smooth, span, story } from './story'

const FEED = new THREE.Color('#c9a7ae')
const WHITE = new THREE.Color('#a98e95')
const VIOLET = new THREE.Color('#b98c92')
const CHOSEN_C = new THREE.Color('#c97890')
const DIM = new THREE.Color('#e3d0d3')

export function Pins({ scene }: { scene: { p: number } }) {
  const pins = useMemo(buildPins, [])
  // Pins frame the centred landing copy rather than compete with it; smaller still on phones.
  const size = useMemo(() => (innerWidth < 720 ? 0.55 : 0.75), [])
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
    // Hero: dozens of faint pins on the hills. Beat 1 (842 -> 5): they light up together, then all but five go out.
    const verify = smooth(span(p, 0.05, 0.11))
    const choose = smooth(span(p, 0.11, 0.17))
    const { m, q, s, v, c, e } = tmp
    const im = mesh.current
    if (!im) return

    pins.forEach((pin, i) => {
      v.copy(pin.ground)
      v.y += Math.sin(t * 0.9 + i) * 0.12

      let k = 0.55 + 0.45 * verify
      if (pin.chosen < 0) k *= 1 - 0.92 * choose
      else k *= 1 + 0.7 * choose

      c.copy(FEED).lerp(pin.status === 'uncertain' ? VIOLET : WHITE, verify)
      if (pin.chosen >= 0) c.lerp(CHOSEN_C, choose)
      else c.lerp(DIM, choose * 0.7)

      e.set(0, t * 0.7 + i, 0)
      q.setFromEuler(e)
      s.setScalar(Math.max(k * size, 0.0001))
      m.compose(v, q, s)
      im.setMatrixAt(i, m)
      im.setColorAt(i, c)
    })
    im.instanceMatrix.needsUpdate = true
    if (im.instanceColor) im.instanceColor.needsUpdate = true

    // Light columns mark the shortlist; labels arrive with the itinerary.
    // Landing labels name demo places; never show them behind the real app.
    const labelIn = story.mode === 'landing' ? Math.max(smooth(span(p, 0.14, 0.18)) * (1 - smooth(span(p, 0.26, 0.3))), smooth(span(p, 0.78, 0.84)) * (1 - smooth(span(p, 0.92, 0.96)))) : 0
    CHOSEN.forEach((_, i) => {
      const beam = beams.current[i]
      if (beam) {
        const mat = beam.material as THREE.MeshBasicMaterial
        mat.opacity = choose * (0.3 + 0.08 * Math.sin(t * 2 + i))
        beam.scale.y = Math.max(choose, 0.0001)
      }
      const label = labels.current[i]
      if (label) {
        label.style.opacity = String(labelIn)
        label.dataset.phase = p < 0.5 ? 'name' : 'full'
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
              <meshBasicMaterial color="#c97890" transparent depthWrite={false} toneMapped={false} fog={false} />
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
