// Friends and direct messages (harness /api/harness/{users,friends,messages}; docs/ACCOUNTS.md §Bạn bè).
// The friends list is one shared store, polled every 30 s while the page is visible: that poll is also what keeps
// this account "online" for its friends. Guests have no friends (the server answers 403).
import { useEffect, useSyncExternalStore } from 'react'
import { json } from './journey'

export interface Person {
  id: string
  nickname: string | null
  name: string
  bio: string
  online: boolean
  avatar: string | null
  unread?: number
  relation?: 'none' | 'friend' | 'sent' | 'received'
}
export interface Friends { friends: Person[]; incoming: Person[]; outgoing: Person[] }
export interface Message { id: number; mine: boolean; body: string; journey: string | null; imported: string | null; at: string; read: boolean }

const post = <T,>(path: string, body: unknown = {}, method = 'POST') =>
  fetch(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(json<T>)

const EVENT = 'tg:friends'
let current: Friends | null = null
const keep = (f: Friends) => {
  current = f
  dispatchEvent(new Event(EVENT))
  return f
}
export const refreshFriends = () => fetch('/api/harness/friends').then(json<Friends>).then(keep)

let watchers = 0
let timer: number | undefined
// Mount once per visible friends surface; the first one starts the poll, the last one stops it.
export function useFriends(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return
    watchers++
    const tick = () => { if (document.visibilityState === 'visible') refreshFriends().catch(() => {}) }
    if (watchers === 1) { tick(); timer = window.setInterval(tick, 30_000); addEventListener('visibilitychange', tick) }
    return () => { if (--watchers === 0) { clearInterval(timer); removeEventListener('visibilitychange', tick) } }
  }, [enabled])
  return useSyncExternalStore((cb) => { addEventListener(EVENT, cb); return () => removeEventListener(EVENT, cb) }, () => current)
}

export const searchPeople = (q: string) => fetch(`/api/harness/users?q=${encodeURIComponent(q)}`).then(json<Person[]>)
export const requestFriend = (id: string) => post<Friends>('/api/harness/friends', { to: id }).then(keep)
export const acceptFriend = (id: string) => post<Friends>(`/api/harness/friends/${id}/accept`).then(keep)
export const removeFriend = (id: string) => post<Friends>(`/api/harness/friends/${id}`, {}, 'DELETE').then(keep)

export const loadThread = (id: string, after = 0) => fetch(`/api/harness/messages/${id}?after=${after}`).then(json<Message[]>)
export const sendMessage = (id: string, text: string, journey?: string) => post<Message>(`/api/harness/messages/${id}`, journey ? { text, journey } : { text })
// "Typing...": the caller tells the friend's open chat they are typing (it lapses on the server after a few seconds).
export const sendTyping = (id: string, on: boolean) => post<{ ok: boolean }>(`/api/harness/messages/${id}/typing`, { on }).catch(() => {})
export const friendTyping = (id: string) => fetch(`/api/harness/messages/${id}/typing`).then(json<{ typing: boolean }>).then((r) => r.typing, () => false)
// A trip a friend sent becomes a copy of the caller's own: { id, stage } of the new journey.
export const importTrip = (messageId: number) => post<{ id: string; stage: 'trip' | 'decision' | 'planning' }>(`/api/harness/messages/${messageId}/import`)

export const initials = (p: { name: string; nickname?: string | null }) =>
  (p.name || p.nickname || '?').trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase()
