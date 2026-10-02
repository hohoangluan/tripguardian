import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { OrthographicCamera } from 'three'
import { story } from '../story'
import { buildMiniature } from './build'

// Scroll progress of the "choose" section, written by the page, read every frame.
export type ChooseProgress = { current: number }

// Fit the plinth (radius ~4.7, seen isometrically) whatever the canvas shape.
function Fit() {
  const camera = useThree((s) => s.camera) as OrthographicCamera
  const { width, height } = useThree((s) => s.size)
  useLayoutEffect(() => {
    const aspect = width / height
    let halfH = 4.1
    let halfW = halfH * aspect
    if (halfW < 5.3) {
      halfW = 5.3
      halfH = halfW / aspect
    }
    Object.assign(camera, { left: -halfW, right: halfW, top: halfH + 0.2, bottom: -halfH + 0.2, zoom: 1 })
    camera.position.set(12, 16, 20)
    camera.lookAt(0, 0, 0)
    camera.updateProjectionMatrix()
  }, [camera, width, height])
  return null
}

function Table({ progress }: { progress: ChooseProgress }) {
  const mini = useMemo(buildMiniature, [])
  const shown = useRef(story.reducedMotion ? 1 : 0)
  useEffect(() => mini.dispose, [mini])
  useFrame((s, dt) => {
    // Damped toward the scroll, so a flick of the wheel still reads as a gesture.
    shown.current += (progress.current - shown.current) * (1 - Math.exp(-dt * 5))
    mini.update(shown.current, story.reducedMotion ? 0 : s.clock.elapsedTime)
  })
  return <primitive object={mini.group} />
}

export default function MiniatureCanvas({ progress }: { progress: ChooseProgress }) {
  const box = useRef<HTMLDivElement>(null)
  const [onScreen, setOnScreen] = useState(false)

  // Render only while the section is on screen.
  useEffect(() => {
    const el = box.current
    if (!el) return
    const io = new IntersectionObserver(([e]) => setOnScreen(e.isIntersecting))
    io.observe(el)
    return () => io.disconnect()
  }, [])

  return (
    <div className="choose__canvas" ref={box} aria-hidden="true">
      <Canvas
        orthographic
        shadows="soft"
        frameloop={!onScreen ? 'never' : story.reducedMotion ? 'demand' : 'always'}
        dpr={[1, 1.75]}
        camera={{ position: [12, 16, 20], near: 0.1, far: 100 }}
        gl={{ antialias: true, alpha: true, toneMappingExposure: 1.22 }}
      >
        <Fit />
        <hemisphereLight args={['#fff9ee', '#aaa58f', 2.1]} />
        <directionalLight
          position={[-6, 12, 6]}
          intensity={3.4}
          color="#ffead3"
          castShadow
          shadow-mapSize={[2048, 2048]}
          shadow-bias={-0.0004}
          shadow-normalBias={0.02}
          shadow-camera-left={-8}
          shadow-camera-right={8}
          shadow-camera-top={8}
          shadow-camera-bottom={-8}
          shadow-camera-near={0.1}
          shadow-camera-far={40}
        />
        <directionalLight position={[8, 7, -10]} intensity={1.1} color="#e0ecf0" />
        <Table progress={progress} />
      </Canvas>
    </div>
  )
}
