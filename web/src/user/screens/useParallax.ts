import { useEffect, type RefObject } from 'react'
import { useReducedMotion } from '../lib'

// Moves every [data-depth] child of `ref` a few px against the pointer. Off under reduced motion.
export function useParallax(ref: RefObject<HTMLElement | null>) {
  const reduced = useReducedMotion()
  useEffect(() => {
    const el = ref.current
    if (!el || reduced) return
    let raf = 0
    const layers = Array.from(el.querySelectorAll<HTMLElement>('[data-depth]'))
    const on = (e: PointerEvent) => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(() => {
        const r = el.getBoundingClientRect()
        const x = (e.clientX - r.left) / r.width - 0.5
        const y = (e.clientY - r.top) / r.height - 0.5
        layers.forEach((l) => { const d = Number(l.dataset.depth); l.style.transform = `translate3d(${-x * d}px, ${-y * d}px, 0) scale(1.06)` })
      })
    }
    el.addEventListener('pointermove', on)
    return () => { el.removeEventListener('pointermove', on); cancelAnimationFrame(raf) }
  }, [ref, reduced])
}
