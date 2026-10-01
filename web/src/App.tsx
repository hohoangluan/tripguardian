import gsap from 'gsap'
import { lazy, Suspense, useCallback, useEffect } from 'react'
import { Landing } from './pages/Landing'
import { navigate, usePath } from './router'
import { World } from './scene/World'
import { story } from './scene/story'
import { UserApp } from './user/UserApp'

const AdminApp = lazy(() => import('./admin/AdminApp'))

type Surface = 'landing' | 'app' | 'admin'
const surfaceOf = (path: string): Surface => (path.startsWith('/admin') ? 'admin' : path.startsWith('/app') ? 'app' : 'landing')

export function App() {
  const path = usePath()
  const surface = surfaceOf(path)
  if (surface !== 'admin') story.mode = surface

  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      story.pointer.x = (e.clientX / innerWidth) * 2 - 1
      story.pointer.y = -((e.clientY / innerHeight) * 2 - 1)
    }
    addEventListener('pointermove', onMove)
    return () => removeEventListener('pointermove', onMove)
  }, [])

  // Landing <-> app: the camera dives into the mist, the page swaps while
  // everything is white, then the mist lets go.
  const dive = useCallback((to: string) => {
    const swap = () => {
      navigate(to)
      window.scrollTo(0, 0)
    }
    if (story.reducedMotion) return swap()
    gsap
      .timeline()
      .to(story, { dive: 1, duration: 0.9, ease: 'power3.in' })
      .to('.veil', { opacity: 1, duration: 0.35, ease: 'power1.in' }, '-=0.45')
      .add(swap)
      .to(story, { dive: 0, duration: 1.4, ease: 'power3.out' }, '+=0.1')
      .to('.veil', { opacity: 0, duration: 0.9, ease: 'power2.out' }, '<0.15')
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
      <World />
      <div className="veil" aria-hidden="true" />
      {surface === 'landing' ? <Landing onStart={() => dive('/app')} /> : <UserApp path={path} onHome={() => dive('/')} />}
    </>
  )
}
