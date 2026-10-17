// One place that starts View Transitions, so two never overlap (a second one skips the first) and the app knows when one is running.
// `cls` (one class, or several separated by spaces) is put on <html> while it runs, so its CSS (user/css/motion.css) can style that transition alone.
type VT = { finished: Promise<unknown> }
type Doc = Document & { startViewTransition?: (cb: () => void | Promise<void>) => VT }

const doc = document as Doc
const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches
let running = false

export const canTransition = () => typeof doc.startViewTransition === 'function' && !reduced()

// Marks <html> once, so CSS can drop the fallback fades that the browser's own transition replaces.
if (typeof doc.startViewTransition === 'function') document.documentElement.dataset.vt = ''

// Returns null (and does nothing) when the browser cannot, the visitor asked for less motion, or another transition is running:
// the caller then makes the change plainly.
export function startTransition(update: () => void | Promise<void>, cls?: string): VT | null {
  if (!canTransition() || running) return null
  running = true
  const root = document.documentElement
  const classes = cls ? cls.split(' ') : []
  root.classList.add(...classes)
  const t = doc.startViewTransition!(update)
  const done = () => { running = false; root.classList.remove(...classes) }
  t.finished.then(done, done)
  return t
}

export const transitionRunning = () => running
