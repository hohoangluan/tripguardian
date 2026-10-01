import { useSyncExternalStore } from 'react'

// Prototype accounts. Nothing leaves the browser: sign-in is simulated and only
// the session (and the emails registered here, never a password) is stored.
// A real auth backend replaces this module and keeps its exports.

export type Provider = 'google' | 'zalo' | 'facebook' | 'apple' | 'tiktok' | 'email'

export type Account = { kind: 'guest' } | { kind: 'user'; name: string; email: string | null; provider: Provider }

export const PROVIDER_LABEL: Record<Provider, string> = {
  google: 'Google',
  zalo: 'Zalo',
  facebook: 'Facebook',
  apple: 'Apple',
  tiktok: 'TikTok',
  email: 'Email',
}

const KEY = 'tg.account.v1'
const KNOWN = 'tg.account.emails.v1'
const EVENT = 'tg:account'

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

function write(key: string, value: unknown) {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* storage blocked: the session lasts until reload */
  }
}

let current: Account | null = read<Account | null>(KEY, null)

function set(next: Account | null) {
  current = next
  write(KEY, next)
  dispatchEvent(new Event(EVENT))
}

const subscribe = (cb: () => void) => {
  addEventListener(EVENT, cb)
  return () => removeEventListener(EVENT, cb)
}

export function useAccount() {
  return useSyncExternalStore(subscribe, () => current)
}

export const continueAsGuest = () => set({ kind: 'guest' })

export const signInWith = (provider: Exclude<Provider, 'email'>) => set({ kind: 'user', name: `Bạn (${PROVIDER_LABEL[provider]})`, email: null, provider })

export const signOut = () => set(null)

export const isEmail = (s: string) => /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(s.trim())

const known = () => read<Record<string, string>>(KNOWN, {})

export type AuthError = { field: 'email' | 'password' | 'name'; text: string }

export function signUp(name: string, email: string, password: string): AuthError | null {
  const e = email.trim().toLowerCase()
  if (!name.trim()) return { field: 'name', text: 'Cho mình biết tên bạn.' }
  if (!isEmail(e)) return { field: 'email', text: 'Email chưa đúng dạng, ví dụ ban@gmail.com.' }
  if (password.length < 8) return { field: 'password', text: 'Mật khẩu cần ít nhất 8 ký tự.' }
  if (known()[e]) return { field: 'email', text: 'Email này đã có tài khoản. Chuyển sang Đăng nhập nhé.' }
  write(KNOWN, { ...known(), [e]: name.trim() })
  set({ kind: 'user', name: name.trim(), email: e, provider: 'email' })
  return null
}

export function signIn(email: string, password: string): AuthError | null {
  const e = email.trim().toLowerCase()
  if (!isEmail(e)) return { field: 'email', text: 'Email chưa đúng dạng, ví dụ ban@gmail.com.' }
  if (!password) return { field: 'password', text: 'Nhập mật khẩu của bạn.' }
  const name = known()[e]
  if (!name) return { field: 'email', text: 'Chưa có tài khoản với email này. Bạn muốn Đăng ký?' }
  set({ kind: 'user', name, email: e, provider: 'email' })
  return null
}

export const initialOf = (a: Account | null) => (a?.kind === 'user' ? (a.name.trim()[0] ?? '?').toUpperCase() : null)
