import { useSyncExternalStore } from 'react'

// The signed-in account, kept by the harness in Postgres (docs/ACCOUNTS.md). Sign-in is Google only:
// /api/auth/google/start sends the browser to Google and back with an HttpOnly session cookie.
// undefined = still asking the server; null = signed out. Any /api/harness call answered 401 signs out here too.

export type Mobility = 'motorbike' | 'car' | 'ride'
export type Companions = 'solo' | 'partner' | 'friends' | 'kids' | 'parents'

export type Me = {
  id: string
  email: string | null
  name: string
  avatar: string | null
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

export async function refreshAccount() {
  try {
    const res = await fetch('/api/harness/me')
    if (res.status === 401) return set(null)
    keep(await answer(res))
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
}

// Only a path on this site comes back from Google (the server checks it again).
export const signInHref = (next: string) => `/api/auth/google/start?next=${encodeURIComponent(next.startsWith('/') ? next : '/app')}`

export async function signOut() {
  await fetch('/api/auth/logout', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }).catch(() => {})
  set(null)
}

const send = (method: string, path: string, body: unknown) =>
  fetch(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(answer)

export const acceptTerms = (version: string) => send('POST', '/api/harness/me/consent', { version }).then(keep)

export const updateProfile = (patch: Partial<Pick<Me, 'home_city' | 'usual_mobility' | 'usual_companions'>> & { display_name?: string | null }) =>
  send('PATCH', '/api/harness/me', patch).then(keep)

export const uploadAvatar = (file: File) =>
  fetch('/api/harness/me/avatar', { method: 'POST', headers: { 'Content-Type': file.type || 'application/octet-stream' }, body: file }).then(answer).then(keep)

export async function deleteAccount() {
  const res = await fetch('/api/harness/me', { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ confirm: true }) })
  if (!res.ok) throw new AccountError(res.status, (await res.json().catch(() => ({}))).error ?? '')
  set(null)
}

export const initialOf = (a: Account | null | undefined) => (a ? ((a.name || a.email || '?').trim()[0] ?? '?').toUpperCase() : null)
