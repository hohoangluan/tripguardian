import gsap from 'gsap'
import { useEffect, useRef } from 'react'
import { useReducedMotion } from '../lib'

export function CountUp({ from, to, render, delay = 0.15 }: { from: number; to: number; render: (n: number) => string; delay?: number }) {
  const ref = useRef<HTMLSpanElement>(null)
  const reduced = useReducedMotion()
  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (reduced) { el.textContent = render(to); return }
    const o = { v: from }
    el.textContent = render(from)
    const t = gsap.to(o, { v: to, duration: 0.9, delay, ease: 'power2.out', onUpdate: () => { el.textContent = render(Math.round(o.v)) } })
    return () => { t.kill() }
  }, [from, to, reduced]) // eslint-disable-line react-hooks/exhaustive-deps
  return <span ref={ref} className="pv-mono">{render(to)}</span>
}
