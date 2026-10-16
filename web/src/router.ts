import { useSyncExternalStore } from 'react'
import { flushSync } from 'react-dom'
import { startTransition } from './viewTransition'

// Minimal path router: one source of truth (location), one event.
const EVENT = 'tg:navigate'

const subscribe = (cb: () => void) => {
  addEventListener('popstate', cb)
  addEventListener(EVENT, cb)
  return () => {
    removeEventListener('popstate', cb)
    removeEventListener(EVENT, cb)
  }
}

const snapshot = () => location.pathname + location.search

export function usePath() {
  return useSyncExternalStore(subscribe, snapshot)
}

// A move to another page cross-fades (View Transitions): the old page stays on screen until the new one has rendered, so a
// heavy page never stutters mid-animation. Same page with another query (the place sheet), a replace, the admin, and a move made
// inside another transition change at once.
export function navigate(to: string, { replace = false } = {}) {
  if (to === snapshot()) return
  const apply = () => {
    if (replace) history.replaceState(null, '', to)
    else history.pushState(null, '', to)
    dispatchEvent(new Event(EVENT))
  }
  const next = new URL(to, location.href).pathname
  const plain = replace || next === location.pathname || next.startsWith('/admin') || location.pathname.startsWith('/admin')
  if (plain || !startTransition(() => flushSync(apply), 'tg-nav')) apply()
}

// "/app/place/abc" against "/app/place/:id" -> { id: "abc" }
export function match(path: string, pattern: string): Record<string, string> | null {
  const a = path.split('?')[0].split('/').filter(Boolean)
  const b = pattern.split('/').filter(Boolean)
  if (a.length !== b.length) return null
  const out: Record<string, string> = {}
  for (let i = 0; i < b.length; i++) {
    if (b[i].startsWith(':')) out[b[i].slice(1)] = decodeURIComponent(a[i])
    else if (a[i] !== b[i]) return null
  }
  return out
}

export const query = (path: string) => new URLSearchParams(path.split('?')[1] ?? '')
