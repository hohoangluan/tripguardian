import { useSyncExternalStore } from 'react'

// The signed-in account, kept by the harness in Postgres (docs/ACCOUNTS.md). Sign-in is Google (/api/auth/google/start
// sends the browser to Google and back) or an email and a password; both end in an HttpOnly session cookie.
// undefined = still asking the server; null = signed out. Any /api/harness call answered 401 signs out here too.

export type Mobility = 'motorbike' | 'car' | 'walk'
export type Companions = 'solo' | 'partner' | 'friends' | 'kids' | 'parents'

export type Me = {
  id: string
  email: string | null
  name: string
  avatar: string | null
  nickname: string | null // how friends find this account (unique, a-z 0-9 . _)
  bio: string
  guest: boolean // no Google account: plans like anyone, keeps nothing after 24 idle hours (docs/ACCOUNTS.md §Khách)
  role: 'user' | 'admin'
  home_city: string | null
  usual_mobility: Mobility | null
  usual_companions: Companions | null
  consents: Record<string, { version: string; at: string } | boolean>
  needs_consent: boolean
  calendar: boolean
  terms_version: string
}

export type Account = { kind: 'user' } & Me

export class AccountError extends Error {
  constructor(public status: number, message: string) { super(message) }
}

const EVENT = 'tg:account'
let current: Account | null | undefined

function set(next: Account | null | undefined) {
  current = next
  dispatchEvent(new Event(EVENT))
}

const subscribe = (cb: () => void) => {
  addEventListener(EVENT, cb)
  return () => removeEventListener(EVENT, cb)
}

export function useAccount() {
  return useSyncExternalStore(subscribe, () => current)
}

async function answer(res: Response): Promise<Me> {
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new AccountError(res.status, body.error ?? `HTTP ${res.status}`)
  return body as Me
}

const keep = (me: Me) => {
  set({ kind: 'user', ...me })
  return me
}

// A guest session lives while any tab of this browser has it open. Each tab marks itself in sessionStorage (it survives
// a reload) and in a shared list in localStorage with a heartbeat. A guest cookie met by a tab that has neither its own
// mark nor another live tab is a closed guest session coming back: it is ended, never resumed. The tab that closes
// last is the one that tells the server the guest is gone.
const TAB = 'tg.guest.tab'
const LIVE = 'tg.guest.live'
const LIVE_MS = 10 * 60 * 1000 // a tab that has not beaten for this long is taken for dead (crashed)
const tabId = Math.random().toString(36).slice(2)
const tabGuest = (on?: boolean) => {
  try {
    if (on === undefined) return sessionStorage.getItem(TAB) === '1'
    if (on) sessionStorage.setItem(TAB, '1'); else sessionStorage.removeItem(TAB)
  } catch { /* no sessionStorage: a reload then ends the guest, the safe side */ }
  return on === true
}
function liveTabs(): Record<string, number> {
  try {
    const all = JSON.parse(localStorage.getItem(LIVE) ?? '{}') as Record<string, number>
    return Object.fromEntries(Object.entries(all).filter(([, at]) => Date.now() - at < LIVE_MS))
  } catch { return {} }
}
function beat(on: boolean) {
  const tabs = liveTabs()
  if (on) tabs[tabId] = Date.now(); else delete tabs[tabId]
  try { localStorage.setItem(LIVE, JSON.stringify(tabs)) } catch { /* the heartbeat is only a help */ }
}
const othersOpen = () => Object.keys(liveTabs()).some((id) => id !== tabId)

export async function refreshAccount() {
  try {
    const res = await fetch('/api/harness/me')
    if (res.status === 401) return set(null)
    const me = keep(await answer(res))
    if (me.guest) {
      if (!tabGuest() && !othersOpen()) { // nobody has this guest open: a closed session, never resumed
        forgetLocalState()
        await signOut()
        return
      }
      tabGuest(true)
      beat(true)
    }
    if (!me.guest && restoreLocalState(me.id)) location.reload() // back from a guest session: the account's own state returns
  } catch {
    set(null)
  }
}

// A session that expires mid-visit: the next harness call answers 401 and the app shows sign-in again.
if (typeof window !== 'undefined') {
  const raw = window.fetch.bind(window)
  window.fetch = async (input, init) => {
    const res = await raw(input, init)
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    if (res.status === 401 && url.includes('/api/harness/') && current) set(null)
    return res
  }
  void refreshAccount()

  // A guest's page closing tells the server, which deletes the guest soon after unless the same guest reappears
  // (a reload) or another tab of the guest is open. While a page is open it says it is alive: that undoes a mark left by a
  // reload that raced it.
  const guestPing = (what: 'leave' | 'alive') => {
    if (!current?.guest) return
    if (what === 'leave') navigator.sendBeacon?.('/api/auth/guest/leave', new Blob(['{}'], { type: 'application/json' }))
    else void fetch('/api/auth/guest/alive', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}', keepalive: true }).catch(() => {})
  }
  addEventListener('pagehide', () => {
    if (!current?.guest || signingIn) return
    beat(false)
    if (!othersOpen()) guestPing('leave') // the last tab of the guest closes
  })
  addEventListener('pageshow', () => { if (current?.guest) { beat(true); guestPing('alive') } })
  setInterval(() => { if (current?.guest) { beat(true); guestPing('alive') } }, 20000)
}

// A guest on their way to Google leaves this page without leaving the visit: the guest stays until they are back.
let signingIn = false
export const holdGuest = () => { signingIn = true; setTimeout(() => { signingIn = false }, 10000) }

// Only a path on this site comes back from Google (the server checks it again).
export const signInHref = (next: string) => `/api/auth/google/start?next=${encodeURIComponent(next.startsWith('/') ? next : '/app')}`

// Sign up or sign in with an email and a password; the server answers 400 / 401 / 409 / 429 with a readable `error`.
async function withEmail(path: string, body: Record<string, string>) {
  const res = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!res.ok) throw new AccountError(res.status, (await res.json().catch(() => ({}))).error ?? '')
  await refreshAccount()
}
export const registerWithEmail = (email: string, password: string, name: string) => withEmail('/api/auth/register', { email, password, name })
export const loginWithEmail = (email: string, password: string) => withEmail('/api/auth/login', { email, password })

// Everything this browser remembers about a trip or a person: a new guest starts from nothing, like a first visit.
const LOCAL_KEYS = ['tg.trip.v1', 'tg.trips.v1', 'tg.tu.v1', 'tg.saved.v1']
const isLocalKey = (k: string) => LOCAL_KEYS.includes(k) || k.startsWith('tg.journey.')
const STASH = 'tg.stash.'
export const FORGET_EVENT = 'tg:forget'
export function forgetLocalState() {
  try {
    for (const k of Object.keys(localStorage)) if (isLocalKey(k)) localStorage.removeItem(k)
  } catch { /* storage unavailable: nothing was kept */ }
  dispatchEvent(new Event(FORGET_EVENT)) // the trip and the library held in memory reset too
}

// A signed-in person who steps into a guest session leaves their own state untouched: it is set aside under their
// id and put back when they sign in again (the server keeps the account itself).
function stashLocalState(id: string) {
  try {
    const kept: Record<string, string> = {}
    for (const k of Object.keys(localStorage)) if (isLocalKey(k)) kept[k] = localStorage.getItem(k) ?? ''
    localStorage.setItem(STASH + id, JSON.stringify(kept))
  } catch { /* storage unavailable: the account still has everything on the server */ }
}
function restoreLocalState(id: string) {
  try {
    const raw = localStorage.getItem(STASH + id)
    if (!raw) return false
    for (const k of Object.keys(localStorage)) if (isLocalKey(k)) localStorage.removeItem(k)
    for (const [k, v] of Object.entries(JSON.parse(raw) as Record<string, string>)) if (isLocalKey(k)) localStorage.setItem(k, v)
    localStorage.removeItem(STASH + id)
    return true
  } catch { return false }
}

// A visitor without an account: the server always makes a new guest (an empty profile, its own 24-hour session);
// a session already open in this browser ends first (an account's own data stays on the server and in its stash).
// `/me` then answers with `guest: true`.
export async function startGuest() {
  const before = current
  const res = await fetch('/api/auth/guest', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
  if (!res.ok) throw new AccountError(res.status, (await res.json().catch(() => ({}))).error ?? '')
  if (before && !before.guest) stashLocalState(before.id)
  tabGuest(true)
  forgetLocalState()
  await refreshAccount()
}

export async function signOut() {
  tabGuest(false)
  beat(false)
  await fetch('/api/auth/logout', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }).catch(() => {})
  set(null)
}

const send = (method: string, path: string, body: unknown) =>
  fetch(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(answer)

export const acceptTerms = (version: string) => send('POST', '/api/harness/me/consent', { version }).then(keep)

export const updateProfile = (patch: Partial<Pick<Me, 'home_city' | 'usual_mobility' | 'usual_companions' | 'nickname' | 'bio'>> & { display_name?: string | null }) =>
  send('PATCH', '/api/harness/me', patch).then(keep)

export const uploadAvatar = (file: File) =>
  fetch('/api/harness/me/avatar', { method: 'POST', headers: { 'Content-Type': file.type || 'application/octet-stream' }, body: file }).then(answer).then(keep)

export async function deleteAccount() {
  const res = await fetch('/api/harness/me', { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ confirm: true }) })
  if (!res.ok) throw new AccountError(res.status, (await res.json().catch(() => ({}))).error ?? '')
  set(null)
}

export const initialOf = (a: Account | null | undefined) => (a ? (a.guest ? 'K' : ((a.name || a.email || '?').trim()[0] ?? '?').toUpperCase()) : null)
