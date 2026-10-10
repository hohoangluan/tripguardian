// Browser-side state of the user web that is not a module's business state: the journeys this browser started, the
// assistant panel, toasts, and the in-memory copy of the account's saved places. The backend (harness) owns trips,
// selections, schedules and the saved places themselves.
import { useSyncExternalStore } from 'react'

export interface Msg {
  id: number
  role: 'user' | 'bot'
  text: string
  places?: string[]
  files?: string[] // names of the files sent with it
}

// What the Planning Agent's one proposal did to a journey's schedule (journey id -> outcome); see P4_PLANNING.md.
export interface Optimized {
  status: 'accepted' | 'fallback'
  before: number // travel minutes of the baseline
  after: number // travel minutes now
  diagnostics: string[]
  seen: boolean
}

interface Ui {
  optimized: Record<string, Optimized>
  saved: string[]
  trips: string[]
  toast: string | null
  flashId: string | null
  tab: string | null
  cmp: string[] // places picked for comparison (up to 3), from the grid, the disc or the place sheet
  assistant: { open: boolean; pinned: boolean; msgs: Msg[]; nudge: string | null; nudgeSeen: boolean }
}

const read = <T,>(k: string, fallback: T): T => {
  try {
    const raw = localStorage.getItem(k)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}
const write = (k: string, v: unknown) => {
  try {
    localStorage.setItem(k, JSON.stringify(v))
  } catch {
    /* private mode: lasts until reload */
  }
}

const SAVED = 'tg.saved.v1' // the list from before saved places lived in the account: merged once, then removed
const TRIPS = 'tg.trips.v1' // the list before it was kept per account: dropped once an account is known
const OWNER = 'tg.owner'
// What this browser keeps about one account's trips. Another account (or a guest) never sees it.
const OWNED_KEYS = ['tg.tu.v1', 'tg.trip.v1']
const OWNED_PREFIXES = ['tg.tu.hist.', 'tg.lodging.asked.', 'tg.journey.pending.']
let owner: { id: string; guest: boolean } | null = null
const tripsKey = (id: string) => `${TRIPS}.${id}`

let ui: Ui = {
  optimized: {},
  saved: [],
  trips: [],
  toast: null,
  flashId: null,
  tab: null,
  cmp: [],
  assistant: { open: read('tg.asst.open', false), pinned: read('tg.asst.pin', false), msgs: [], nudge: null, nudgeSeen: false },
}
const subs = new Set<() => void>()
export function setUi(patch: Partial<Ui> | ((u: Ui) => Partial<Ui>)) {
  ui = { ...ui, ...(typeof patch === 'function' ? patch(ui) : patch) }
  subs.forEach((f) => f())
}
export const getUi = () => ui
export function useUi<T>(sel: (u: Ui) => T): T {
  return useSyncExternalStore(
    (cb) => {
      subs.add(cb)
      return () => subs.delete(cb)
    },
    () => sel(ui),
  )
}

export const toggleCmp = (id: string) =>
  setUi((u) => ({ cmp: u.cmp.includes(id) ? u.cmp.filter((x) => x !== id) : u.cmp.length >= 3 ? [...u.cmp.slice(1), id] : [...u.cmp, id] }))

let toastTimer: ReturnType<typeof setTimeout> | undefined
export function toast(text: string, ms = 2400) {
  clearTimeout(toastTimer)
  setUi({ toast: text })
  toastTimer = setTimeout(() => setUi({ toast: null }), ms)
}

let flashTimer: ReturnType<typeof setTimeout> | undefined
export function flash(id: string | null) {
  clearTimeout(flashTimer)
  setUi({ flashId: id })
  flashTimer = setTimeout(() => setUi({ flashId: null }), 1200)
}

// Saved places belong to the account (docs/ACCOUNTS.md §3); they never enter a trip on their own.
const SAVED_API = '/api/harness/me/saved'
const savedCall = async (method: 'GET' | 'POST' | 'DELETE', body?: unknown, id?: string) => {
  const res = await fetch(id ? `${SAVED_API}/${encodeURIComponent(id)}` : SAVED_API, body === undefined ? { method } : { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!res.ok) throw new Error(`saved ${res.status}`)
  return ((await res.json()) as { saved: string[] }).saved
}

// After sign-in: the account's list; a list this browser kept before is merged into the account once, then dropped.
export async function loadSaved() {
  try {
    const local = read<string[]>(SAVED, []).filter((x) => typeof x === 'string')
    let saved = await savedCall('GET')
    if (local.length) {
      saved = await savedCall('POST', { place_ids: local.slice(0, 500) })
      try { localStorage.removeItem(SAVED) } catch { /* private mode: nothing kept */ }
    }
    setUi({ saved })
  } catch {
    /* hearts start empty; the next toggle still writes to the account */
  }
}

export const clearSaved = () => setUi({ saved: [] })

// Optimistic: the heart changes at once; a failed write puts it back and says so.
export function toggleSaved(id: string, name?: string) {
  if (owner?.guest) { toast('Đăng nhập để lưu nơi này; bản dùng thử không lưu được'); return } // the server refuses a guest's list
  const on = ui.saved.includes(id)
  setUi((u) => ({ saved: on ? u.saved.filter((x) => x !== id) : [id, ...u.saved.filter((x) => x !== id)] }))
  if (!on) toast(`Đã lưu ${name ?? 'nơi này'}`)
  ;(on ? savedCall('DELETE', undefined, id) : savedCall('POST', { place_ids: [id] })).catch(() => {
    setUi((u) => ({ saved: on ? [id, ...u.saved.filter((x) => x !== id)] : u.saved.filter((x) => x !== id) }))
    toast(on ? 'Chưa bỏ lưu được, bạn thử lại nhé' : 'Chưa lưu được nơi này, bạn thử lại nhé')
  })
}

// Journeys started in this browser, newest first: what "Chuyến của tôi" asks the server about.
// A guest has no history, so nothing is listed or written for one.
export function rememberTrip(id: string) {
  if (!owner || owner.guest) return
  const trips = [id, ...ui.trips.filter((x) => x !== id)].slice(0, 20)
  write(tripsKey(owner.id), trips)
  setUi({ trips })
}
export function forgetTrip(id: string) {
  if (!owner || owner.guest) return
  const trips = ui.trips.filter((x) => x !== id)
  write(tripsKey(owner.id), trips)
  setUi({ trips })
}

// Who this browser's trip data belongs to. When it is another account (or a guest, or nobody) the previous one's
// open trip, chat history and unsent requests are removed; returns true then, so the app can reset what it holds.
export function bindOwner(id: string | null, guest: boolean): boolean {
  let changed = false
  try {
    const prev = localStorage.getItem(OWNER) ?? ''
    changed = prev !== (id ?? '')
    if (changed) {
      const drop = [...OWNED_KEYS, TRIPS]
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i)
        if (k && OWNED_PREFIXES.some((p) => k.startsWith(p))) drop.push(k)
      }
      drop.forEach((k) => localStorage.removeItem(k))
      if (id) localStorage.setItem(OWNER, id)
      else localStorage.removeItem(OWNER)
    }
  } catch { /* private mode: nothing is kept between visits anyway */ }
  owner = id ? { id, guest } : null
  setUi({ trips: id && !guest ? read<string[]>(tripsKey(id), []) : [] })
  return changed
}

export const setOptimized = (id: string, o: Optimized | null) =>
  setUi((u) => {
    const optimized = { ...u.optimized }
    if (o) optimized[id] = o
    else delete optimized[id]
    return { optimized }
  })

export function openAssistant(open?: boolean) {
  const v = open ?? !ui.assistant.open
  write('tg.asst.open', v)
  setUi((u) => ({ assistant: { ...u.assistant, open: v, nudgeSeen: v ? true : u.assistant.nudgeSeen } }))
}
export function pinAssistant(v: boolean) {
  write('tg.asst.pin', v)
  setUi((u) => ({ assistant: { ...u.assistant, pinned: v } }))
}
export const dismissNudge = () => setUi((u) => ({ assistant: { ...u.assistant, nudge: null, nudgeSeen: true } }))
export const nudge = (text: string) => setUi((u) => (u.assistant.nudgeSeen || u.assistant.open ? {} : { assistant: { ...u.assistant, nudge: text } }))
let msgId = 1
export function pushMsg(m: Omit<Msg, 'id'>) {
  const id = msgId++
  setUi((u) => ({ assistant: { ...u.assistant, msgs: [...u.assistant.msgs, { ...m, id }] } }))
  return id
}
export function editMsg(id: number, patch: Partial<Msg>) {
  setUi((u) => ({ assistant: { ...u.assistant, msgs: u.assistant.msgs.map((m) => (m.id === id ? { ...m, ...patch } : m)) } }))
}
export const clearMsgs = () => setUi((u) => ({ assistant: { ...u.assistant, msgs: [] } }))
