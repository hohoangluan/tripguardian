import gsap from 'gsap'
import { useCallback, useEffect, useState } from 'react'
import { Landing } from './pages/Landing'
import { Start } from './pages/Start'
import { World } from './scene/World'
import { story } from './scene/story'

type Route = 'landing' | 'app'

const routeOf = (path: string): Route => (path.startsWith('/app') ? 'app' : 'landing')

export function App() {
  const [route, setRoute] = useState<Route>(() => routeOf(location.pathname))
  story.mode = route

  useEffect(() => {
    const onPop = () => setRoute(routeOf(location.pathname))
    const onMove = (e: PointerEvent) => {
      story.pointer.x = (e.clientX / innerWidth) * 2 - 1
      story.pointer.y = -((e.clientY / innerHeight) * 2 - 1)
    }
    addEventListener('popstate', onPop)
    addEventListener('pointermove', onMove)
    return () => {
      removeEventListener('popstate', onPop)
      removeEventListener('pointermove', onMove)
    }
  }, [])

  // Page change = the camera dives into the mist, the page swaps while
  // everything is white, then the mist lets go.
  const go = useCallback((next: Route) => {
    const swap = () => {
      history.pushState(null, '', next === 'app' ? '/app' : '/')
      window.scrollTo(0, 0)
      setRoute(next)
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

  return (
    <>
      <World />
      <div className="veil" aria-hidden="true" />
      {route === 'landing' ? <Landing onStart={() => go('app')} /> : <Start onHome={() => go('landing')} />}
    </>
  )
}
