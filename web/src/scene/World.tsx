import { Canvas } from '@react-three/fiber'
import { useMemo } from 'react'
import { Director } from './Director'
import { Mist } from './Mist'
import { Pines } from './Pines'
import { Pins } from './Pins'
import { Route } from './Route'
import { Terrain } from './Terrain'

// One persistent canvas behind the landing, so navigation is a camera move,
// not a reload. Off the landing it stays mounted (unmounting tears drei's
// labels out from under React) but hidden and not rendering.
export function World({ active }: { active: boolean }) {
  // Damped scene progress, written by Director, read by everything else.
  const scene = useMemo(() => ({ p: 0 }), [])
  return (
    <div className="world" aria-hidden="true" hidden={!active}>
      <Canvas frameloop={active ? 'always' : 'never'} dpr={[1, 1.75]} camera={{ position: [0, 8, 40], fov: 46, near: 0.5, far: 400 }} gl={{ antialias: true, powerPreference: 'high-performance' }}>
        <Director scene={scene} />
        <Terrain />
        <Pines />
        <Pins scene={scene} />
        <Route scene={scene} />
        <Mist scene={scene} />
      </Canvas>
    </div>
  )
}
