import { useLayoutEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent, type RefObject } from 'react'
import { reducedMotion } from '../../lib'

// Reordering the stops of a day (mẫu ui_mock_for_design/designs/itinerary): press and hold the card or its photo (or just drag),
// the card floats under the pointer, the others slide aside while it moves, the dropped card slides into its place.
// Esc cancels. The cards are keyed rows `[data-stop=<place id>]` in a list; the screen owns the order and renders it.

const EASE = 'cubic-bezier(.2,.8,.2,1)'
const HOLD_MS = 150
const MOVE_PX = 5

interface Drag {
  id: string
  pointer: number
  sx: number
  sy: number
  x: number
  y: number
  active: boolean
  ox: number
  oy: number
  timer: number
  raf: number
  ghost: HTMLElement | null
}

interface Landing { id: string; rect: DOMRect }

const rowOf = (list: HTMLElement | null, id: string) => list?.querySelector<HTMLElement>(`[data-stop="${CSS.escape(id)}"]`) ?? null

export function useStopDrag({ listRef, scrollRef, order, enabled, onPreview, onCommit }: {
  listRef: RefObject<HTMLElement | null>; scrollRef: RefObject<HTMLElement | null>; order: string[]; enabled: boolean
  onPreview: (order: string[] | null) => void; onCommit: (order: string[]) => void
}) {
  const [dragging, setDragging] = useState<string | null>(null)
  const state = useRef<Drag | null>(null)
  const suppressUntil = useRef(0)
  const landing = useRef<Landing | null>(null)
  const [landed, setLanded] = useState(0)
  const live = useRef({ order, enabled, onPreview, onCommit })
  live.current = { order, enabled, onPreview, onCommit }

  // Built once: the window listeners it adds and removes must be the same functions for the whole drag.
  const core = useMemo(() => {
    const moveGhost = () => {
      const d = state.current
      if (d?.ghost) { d.ghost.style.left = `${d.x - d.ox}px`; d.ghost.style.top = `${d.y - d.oy}px` }
    }

    const preview = () => {
      const d = state.current
      const list = listRef.current
      if (!d || !list) return
      const { order: cur } = live.current
      const others = cur.filter((x) => x !== d.id)
      let at = others.findIndex((o) => {
        const r = rowOf(list, o)?.getBoundingClientRect()
        return r ? d.y < r.top + r.height / 2 : false
      })
      if (at < 0) at = others.length
      const next = [...others]
      next.splice(at, 0, d.id)
      if (next.join('|') !== cur.join('|')) live.current.onPreview(next)
    }

    const begin = () => {
      const d = state.current
      const list = listRef.current
      if (!d || d.active || !list) return
      const card = rowOf(list, d.id)?.querySelector<HTMLElement>('.tg-it-card')
      const root = list.closest<HTMLElement>('.tg')
      if (!card || !root) return
      d.active = true
      suppressUntil.current = Infinity
      const r = card.getBoundingClientRect()
      d.ox = d.sx - r.left
      d.oy = d.sy - r.top
      const ghost = card.cloneNode(true) as HTMLElement
      ghost.querySelectorAll('[id]').forEach((el) => el.removeAttribute('id'))
      ghost.classList.add('tg-it-ghost')
      ghost.setAttribute('aria-hidden', 'true')
      ghost.style.width = `${r.width}px`
      root.appendChild(ghost)
      d.ghost = ghost
      document.body.classList.add('tg-it-dragging')
      setDragging(d.id)
      if (!reducedMotion()) ghost.animate([{ transform: 'scale(1)', opacity: 0.8 }, { transform: 'scale(1.015)', opacity: 1 }], { duration: 180, easing: EASE, fill: 'forwards' })
      moveGhost()
      scrollLoop()
    }

    // near the top or bottom edge of the list the list keeps scrolling while the pointer stays there
    const scrollLoop = () => {
      const d = state.current
      const sc = scrollRef.current
      if (!d?.active || !sc) return
      const r = sc.getBoundingClientRect()
      const speed = d.y < r.top + 60 ? -Math.min(18, (r.top + 60 - d.y) / 3 + 4) : d.y > r.bottom - 60 ? Math.min(18, (d.y - (r.bottom - 60)) / 3 + 4) : 0
      if (speed) { sc.scrollTop += speed; preview() }
      d.raf = requestAnimationFrame(scrollLoop)
    }

    const end = (commit: boolean) => {
      const d = state.current
      if (!d) return
      window.clearTimeout(d.timer)
      cancelAnimationFrame(d.raf)
      removeEventListener('pointermove', onMove)
      removeEventListener('pointerup', onUp)
      removeEventListener('pointercancel', onCancel)
      removeEventListener('keydown', onKey)
      state.current = null
      if (!d.active) return
      const rect = d.ghost!.getBoundingClientRect()
      d.ghost!.remove()
      document.body.classList.remove('tg-it-dragging')
      setDragging(null)
      suppressUntil.current = Date.now() + 400
      if (commit) {
        landing.current = { id: d.id, rect }
        setLanded((n) => n + 1)
        live.current.onCommit(live.current.order)
      } else live.current.onPreview(null)
    }

    function onMove(e: PointerEvent) {
      const d = state.current
      if (!d || d.pointer !== e.pointerId) return
      d.x = e.clientX
      d.y = e.clientY
      if (!d.active && Math.hypot(d.x - d.sx, d.y - d.sy) > MOVE_PX) begin()
      if (!d.active) return
      e.preventDefault()
      moveGhost()
      preview()
    }
    function onUp(e: PointerEvent) { if (state.current?.pointer === e.pointerId) end(true) }
    function onCancel() { end(false) }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && state.current?.active) { e.preventDefault(); end(false) }
    }

    const onPointerDown = (e: ReactPointerEvent<HTMLElement>) => {
      if (!live.current.enabled || e.button !== 0 || state.current) return
      const target = e.target as HTMLElement
      const row = target.closest<HTMLElement>('[data-stop]')
      if (!row || !listRef.current?.contains(row)) return
      const control = target.closest('button, a, input, select, textarea, summary, label, details')
      if (control && !control.hasAttribute('data-drag-ok')) return
      const d: Drag = { id: row.dataset.stop!, pointer: e.pointerId, sx: e.clientX, sy: e.clientY, x: e.clientX, y: e.clientY, active: false, ox: 0, oy: 0, timer: 0, raf: 0, ghost: null }
      d.timer = window.setTimeout(begin, HOLD_MS)
      state.current = d
      addEventListener('pointermove', onMove)
      addEventListener('pointerup', onUp)
      addEventListener('pointercancel', onCancel)
      addEventListener('keydown', onKey)
    }


    return { onPointerDown }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // a click that ends a drag must not open the place
  const justDragged = () => Date.now() < suppressUntil.current
  return { dragging, onPointerDown: core.onPointerDown, justDragged, landing, landed }
}

// Slide the rows from where they were to where they are now (FLIP), and land a dropped card from the floating copy's spot.
export function useSlide(listRef: RefObject<HTMLElement | null>, scrollRef: RefObject<HTMLElement | null>, key: string, landing: RefObject<Landing | null>, landed: number) {
  const before = useRef(new Map<string, { top: number; left: number }>())
  const lastKey = useRef(key)
  const lastLanded = useRef(landed)
  useLayoutEffect(() => {
    const list = listRef.current
    const sc = scrollRef.current
    if (!list || !sc) return
    const base = sc.getBoundingClientRect()
    const at = (r: DOMRect) => ({ top: r.top - base.top + sc.scrollTop, left: r.left - base.left })
    const rows = [...list.querySelectorAll<HTMLElement>('[data-stop]')]
    const now = new Map(rows.map((el) => [el.dataset.stop!, at(el.getBoundingClientRect())]))
    const land = lastLanded.current !== landed ? landing.current : null
    if (land) (landing as { current: Landing | null }).current = null
    if (!reducedMotion() && (lastKey.current !== key || land)) {
      for (const el of rows) {
        const id = el.dataset.stop!
        const was = land?.id === id ? at(land.rect) : before.current.get(id)
        const p = now.get(id)!
        if (!was) continue
        const dx = was.left - p.left
        const dy = was.top - p.top
        const dropped = land?.id === id
        if (!dropped && Math.abs(dx) + Math.abs(dy) < 1) continue
        el.getAnimations().forEach((a) => a.cancel())
        el.animate([{ transform: `translate(${dx}px, ${dy}px) scale(${dropped ? 1.012 : 1})` }, { transform: 'translate(0, 0) scale(1)' }], { duration: dropped ? 420 : 300, easing: EASE })
        if (dropped) el.querySelector('.tg-it-card')?.animate([{ boxShadow: '0 12px 34px rgba(0, 0, 0, .18)' }, { boxShadow: '0 0 0 rgba(0, 0, 0, 0)' }], { duration: 650, easing: EASE })
      }
    }
    lastKey.current = key
    lastLanded.current = landed
    before.current = now
  })
}
