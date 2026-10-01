import { useFrame, useThree } from '@react-three/fiber'
import { useMemo, useRef } from 'react'
import * as THREE from 'three'
import { smooth, story } from './story'

// One camera stop per landing section; section i sits at progress i / 5.
const POS = [
  [0, 15, 42],
  [6, 15, 26],
  [-12, 17, 12],
  [13, 21, 6],
  [10, 34, 8],
  [-2, 46, 12],
].map((v) => new THREE.Vector3(...v))
const LOOK = [
  [0, 7, -20],
  [0, 12, -6],
  [0, 1, -14],
  [2, 0, -14],
  [4, 0, -15],
  [3, 0, -14],
].map((v) => new THREE.Vector3(...v))

const posCurve = new THREE.CatmullRomCurve3(POS, false, 'centripetal')
const lookCurve = new THREE.CatmullRomCurve3(LOOK, false, 'centripetal')

const MIST = new THREE.Color('#d5dee0')
const CLEAR = new THREE.Color('#bcd5df')

export function Director({ scene }: { scene: { p: number } }) {
  const { camera, scene: three, size } = useThree()
  const look = useRef(new THREE.Vector3().copy(LOOK[0]))
  const angle = useRef(0)
  const shift = useRef(0)
  const sun = useRef<THREE.DirectionalLight>(null)
  const tmp = useMemo(() => ({ pos: new THREE.Vector3(), tgt: new THREE.Vector3(), col: new THREE.Color() }), [])

  const fog = useMemo(() => new THREE.FogExp2(MIST.getHex(), 0.05), [])
  three.fog = fog
  three.background = fog.color

  useFrame(({ clock }, dt) => {
    const k = 1 - Math.exp(-dt * (story.reducedMotion ? 30 : 3.2))
    const t = story.reducedMotion ? 0 : clock.elapsedTime
    const target = story.mode === 'landing' ? story.progress : story.appScene
    scene.p += (target - scene.p) * (story.mode === 'landing' ? k : 1 - Math.exp(-dt * 1.2))
    const p = scene.p
    const { pos, tgt, col } = tmp

    if (story.mode === 'landing') {
      posCurve.getPoint(p, pos)
      lookCurve.getPoint(p, tgt)
      pos.x += story.pointer.x * 1.6
      pos.y += story.pointer.y * 0.9
    } else {
      angle.current += (story.appStep * 0.7 - angle.current) * (1 - Math.exp(-dt * 1.5))
      const a = angle.current + t * 0.02
      pos.set(Math.sin(a) * 34, 20 + Math.sin(t * 0.2) * 1.2, -12 + Math.cos(a) * 34)
      tgt.set(0, 9, -10)
    }
    // Dive: pull the camera most of the way to its target, into the mist.
    pos.lerp(tgt, story.dive * 0.8)

    camera.position.lerp(pos, k)
    look.current.lerp(tgt, k)
    camera.lookAt(look.current)

    const pc = camera as THREE.PerspectiveCamera
    const fov = size.width < size.height ? 62 : 46
    if (pc.fov !== fov) {
      pc.fov = fov
      pc.updateProjectionMatrix()
    }
    // On wide screens the copy sits left, so frame the scene to the right.
    const wantShift = story.mode === 'landing' && size.width > 900 ? 0.17 : 0
    shift.current += (wantShift - shift.current) * k
    pc.setViewOffset(size.width, size.height, -size.width * shift.current, 0, size.width, size.height)

    const clear = smooth(p)
    fog.density = THREE.MathUtils.lerp(0.036, 0.0065, clear) + story.dive * 0.2
    col.copy(MIST).lerp(CLEAR, clear)
    fog.color.copy(col)
    if (sun.current) sun.current.intensity = 0.9 + clear * 1.6
  })

  return (
    <>
      <hemisphereLight args={['#eef4f4', '#1e3a34', 1.4]} />
      <directionalLight ref={sun} position={[-30, 40, 10]} color="#ffe3ad" intensity={1} />
    </>
  )
}
