import gsap from 'gsap'
import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import { Landing } from './pages/Landing'
import { navigate, usePath } from './router'
import { story } from './scene/story'
import { UserApp } from './user/UserApp'

const AdminApp = lazy(() => import('./admin/AdminApp'))
// The 3D world (three.js) belongs to the landing; a visit straight to /app never downloads it.
const World = lazy(() => import('./scene/World').then((m) => ({ default: m.World })))

type Surface = 'landing' | 'app' | 'admin'
const surfaceOf = (path: string): Surface => (path.startsWith('/admin') ? 'admin' : path.startsWith('/app') ? 'app' : 'landing')

export function App() {
  const path = usePath()
  const surface = surfaceOf(path)
  if (surface !== 'admin') story.mode = surface
  // Mounted on the first landing visit, then kept: /app-only visitors never load it.
  // Phones never run the 3D (UI_SPEC_LANDING §4): .world shows a still of the same scene instead.
  const [wide] = useState(() => matchMedia('(min-width: 901px)').matches)
  const [worldOn, setWorldOn] = useState(surface === 'landing' && wide)
  useEffect(() => {
    if (surface === 'landing' && wide) setWorldOn(true)
  }, [surface, wide])

  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      story.pointer.x = (e.clientX / innerWidth) * 2 - 1
      story.pointer.y = -((e.clientY / innerHeight) * 2 - 1)
    }
    addEventListener('pointermove', onMove)
    return () => removeEventListener('pointermove', onMove)
  }, [])

  // Landing -> app: the camera dives into the mist, the page swaps while
  // everything is white, then the veil lifts. The 3D world lives on the landing
  // only, so app -> landing fades to white first and the world surfaces from the mist.
  const dive = useCallback((to: string) => {
    const swap = () => {
      navigate(to)
      window.scrollTo(0, 0)
    }
    if (story.reducedMotion) return swap()
    const fromLanding = surfaceOf(location.pathname) === 'landing'
    const tl = gsap.timeline()
    if (fromLanding) tl.to(story, { dive: 1, duration: 0.9, ease: 'power3.in' }).to('.veil', { opacity: 1, duration: 0.35, ease: 'power1.in' }, '-=0.45')
    else tl.to('.veil', { opacity: 1, duration: 0.4, ease: 'power1.in' }).set(story, { dive: 1 })
    tl.add(swap)
      .to(story, { dive: 0, duration: 1.4, ease: 'power3.out' }, '+=0.1')
      .to('.veil', { opacity: 0, duration: fromLanding ? 0.6 : 0.9, ease: 'power2.out' }, '<0.15')
  }, [])

  if (surface === 'admin') {
    return (
      <Suspense fallback={<div className="admin-boot">Đang mở Admin</div>}>
        <AdminApp />
      </Suspense>
    )
  }

  return (
    <>
      {worldOn ? (
        <Suspense fallback={<div className="world" />}>
          <World active={surface === 'landing'} />
        </Suspense>
      ) : (
        surface === 'landing' && <div className="world" aria-hidden="true" />
      )}
      <div className="veil" aria-hidden="true" />
      {surface === 'landing' ? <Landing onStart={() => dive('/app')} /> : <UserApp path={path} onHome={() => dive('/')} />}
    </>
  )
}
