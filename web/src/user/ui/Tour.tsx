import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useReducedMotion } from '../lib'
import { Icon } from './icons'
import { hasSeen, markSeen } from './seen'
import '../css/tour.css'

// A guided tour that never blocks the page: a ring around a real element plus a popover next to it.
// The page underneath stays clickable and scrollable; the tour follows the element, and the user can skip at any step.
//
//   const tour = useTour('home-tour', { auto: true })
//   <Tour steps={STEPS} open={tour.open} onClose={tour.close} />
//   <button onClick={tour.start}>Replay</button>
//
// A step points at an element with a CSS selector (`[data-tour="x"]` by convention). A step without `anchor`, or whose
// anchor is not on the page when the tour opens: no anchor = a note in the corner, anchor missing = the step is dropped.
export type TourStep = { anchor?: string; side?: Side; title: string; body: ReactNode }
type Side = 'top' | 'bottom' | 'left' | 'right'

const GAP = 14
const MARGIN = 16
const PAD = 8
const WIDTH = 344

function anchorOf(step: TourStep): HTMLElement | null {
  if (!step.anchor) return null
  const el = document.querySelector<HTMLElement>(step.anchor)
  return el && el.getClientRects().length > 0 ? el : null
}

// `auto`: open once, shortly after mount, if this browser has not seen the tour and the user has not started typing.
// Closing in any way (skip, finish, Esc) marks it seen.
export function useTour(key: string, opts: { auto?: boolean; delay?: number } = {}) {
  const { auto = false, delay = 700 } = opts
  const [open, setOpen] = useState(false)
  useEffect(() => {
    if (!auto || hasSeen(key)) return
    const t = window.setTimeout(() => {
      const a = document.activeElement
      const typing = a instanceof HTMLTextAreaElement || a instanceof HTMLInputElement
      if (!typing || !(a as HTMLTextAreaElement | HTMLInputElement).value) setOpen(true)
    }, delay)
    return () => window.clearTimeout(t)
  }, [auto, delay, key])
  const start = useCallback(() => setOpen(true), [])
  const close = useCallback(() => { markSeen(key); setOpen(false) }, [key])
  return { open, start, close }
}

type Place = { ring: { top: number; left: number; width: number; height: number } | null; top: number; left: number }

function layout(target: HTMLElement | null, pw: number, ph: number, prefer?: Side): Place {
  const vw = window.innerWidth
  const vh = window.innerHeight
  const clampX = (x: number) => Math.max(MARGIN, Math.min(x, vw - pw - MARGIN))
  const clampY = (y: number) => Math.max(MARGIN, Math.min(y, vh - ph - MARGIN))
  // No element to point at: the popover waits in the corner, away from the page's main input.
  if (!target) return { ring: null, top: clampY(vh - ph - MARGIN), left: clampX(vw - pw - MARGIN) }
  const r = target.getBoundingClientRect()
  // Only the part of the element on screen is ringed; a block taller than the screen gets the popover in the corner.
  const top = Math.max(r.top, 0)
  const bottom = Math.min(r.bottom, vh)
  const left = Math.max(r.left, 0)
  const right = Math.min(r.right, vw)
  const rt = Math.max(top - PAD, 3)
  const rl = Math.max(left - PAD, 3)
  const ring = { top: rt, left: rl, width: Math.min(right + PAD, vw - 3) - rl, height: Math.min(bottom + PAD, vh - 3) - rt }
  const corner = { ring, top: clampY(vh - ph - MARGIN), left: clampX(vw - pw - MARGIN) }
  if (bottom - top > vh * 0.62 && right - left > vw * 0.4) return corner // a wide block taller than the screen
  const cx = left + (right - left) / 2 - pw / 2
  const cy = top + (bottom - top) / 2 - ph / 2
  const at: Record<Side, Place> = {
    bottom: { ring, top: ring.top + ring.height + GAP, left: clampX(cx) },
    top: { ring, top: ring.top - GAP - ph, left: clampX(cx) },
    right: { ring, top: clampY(cy), left: ring.left + ring.width + GAP },
    left: { ring, top: clampY(cy), left: ring.left - GAP - pw },
  }
  const order: Side[] = ['bottom', 'top', 'right', 'left']
  const tries = (prefer ? [prefer, ...order.filter((o) => o !== prefer)] : order).map((o) => at[o])
  const fits = (p: Place) => p.top >= MARGIN && p.left >= MARGIN && p.top + ph <= vh - MARGIN && p.left + pw <= vw - MARGIN
  return tries.find(fits) ?? corner
}

export function Tour({ steps, open, onClose, label = 'Hướng dẫn' }: { steps: TourStep[]; open: boolean; onClose: () => void; label?: string }) {
  const reduced = useReducedMotion()
  const [live, setLive] = useState<TourStep[]>([])
  const [i, setI] = useState(0)
  const [place, setPlace] = useState<Place | null>(null)
  const pop = useRef<HTMLDivElement>(null)
  const next = useRef<HTMLButtonElement>(null)
  const before = useRef<Element | null>(null)

  // Freeze the step list on open: steps whose anchor is not on the page are dropped.
  useEffect(() => {
    if (!open) return
    before.current = document.activeElement
    setLive(steps.filter((s) => !s.anchor || anchorOf(s)))
    setI(0)
    setPlace(null)
    return () => {
      const el = before.current
      if (el instanceof HTMLElement && el.isConnected) el.focus({ preventScroll: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const step = open ? live[i] : undefined

  const update = useCallback(() => {
    const el = pop.current
    if (!el || !step) return
    setPlace(layout(anchorOf(step), el.offsetWidth, el.offsetHeight, step.side))
  }, [step])

  // Bring the element into view, place the popover, and keep both following the element while the page moves.
  useLayoutEffect(() => {
    if (!step) return
    const target = anchorOf(step)
    if (target) {
      const r = target.getBoundingClientRect()
      const tall = r.height > window.innerHeight * 0.55
      if (r.top < 0 || r.bottom > window.innerHeight) target.scrollIntoView({ block: tall ? 'start' : 'center', behavior: reduced ? 'auto' : 'smooth' })
    }
    update()
    let raf = 0
    const on = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(update) }
    window.addEventListener('scroll', on, true)
    window.addEventListener('resize', on)
    const ro = target ? new ResizeObserver(on) : null
    if (target) ro?.observe(target)
    return () => { cancelAnimationFrame(raf); window.removeEventListener('scroll', on, true); window.removeEventListener('resize', on); ro?.disconnect() }
  }, [step, update, reduced])

  // Keyboard focus follows the tour; arrow keys and Esc work unless the user is typing.
  useEffect(() => { if (step) next.current?.focus({ preventScroll: true }) }, [step])
  const last = i >= live.length - 1
  useEffect(() => {
    if (!open || !live.length) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); onClose(); return }
      const t = e.target
      if (t instanceof HTMLElement && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return
      if (e.key === 'ArrowRight') { e.preventDefault(); if (last) onClose(); else setI((n) => n + 1) }
      if (e.key === 'ArrowLeft') { e.preventDefault(); setI((n) => Math.max(0, n - 1)) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, live.length, last, onClose])

  if (!open || !step) return null
  const root = document.querySelector('.tg') ?? document.body
  const ring = place?.ring
  return createPortal(
    <>
      {ring && <div className="tg-tour__ring" aria-hidden="true" style={{ top: ring.top, left: ring.left, width: ring.width, height: ring.height }} />}
      <div
        ref={pop}
        className="tg-tour__pop"
        role="dialog"
        aria-modal="false"
        aria-label={label}
        aria-describedby="tg-tour-body"
        style={{ width: WIDTH, top: place?.top ?? 0, left: place?.left ?? 0, visibility: place ? 'visible' : 'hidden' }}
      >
        <button type="button" className="tg-tour__x" aria-label="Bỏ qua hướng dẫn" onClick={onClose}><Icon name="x" size={16} /></button>
        <p className="tg-tour__n" aria-hidden="true">{i + 1} / {live.length}</p>
        <h2 className="tg-tour__t">{step.title}</h2>
        <div className="tg-tour__b" id="tg-tour-body">{step.body}</div>
        <div className="tg-tour__dots" aria-hidden="true">{live.map((_, k) => <i key={k} className={k === i ? 'is-now' : k < i ? 'is-done' : ''} />)}</div>
        <div className="tg-tour__foot">
          {last ? <span /> : <button type="button" className="tg-link tg-link--quiet" onClick={onClose}>Bỏ qua</button>}
          <span className="tg-tour__nav">
            {i > 0 && <button type="button" className="tg-btn tg-btn--ghost tg-btn--sm" onClick={() => setI(i - 1)}>Trước</button>}
            <button ref={next} type="button" className="tg-btn tg-btn--primary tg-btn--sm" onClick={() => (last ? onClose() : setI(i + 1))}>{last ? 'Xong' : 'Tiếp'}{!last && <Icon name="arrow" size={16} />}</button>
          </span>
        </div>
      </div>
    </>,
    root,
  )
}
