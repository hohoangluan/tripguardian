// Browser-side state of the user web that is not a module's business state: saved places, the journeys this
// browser started, the assistant panel, toasts. The backend (harness) owns trips, selections and schedules.
import { useSyncExternalStore } from 'react'

export interface Msg {
  id: number
  role: 'user' | 'bot'
  text: string
  places?: string[]
}

// What the Planning Agent's one proposal did to a journey's schedule (journey id -> outcome); see PLANNING.md.
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

const SAVED = 'tg.saved.v1'
const TRIPS = 'tg.trips.v1'

let ui: Ui = {
  optimized: {},
  saved: read<string[]>(SAVED, []),
  trips: read<string[]>(TRIPS, []),
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

// Saved places live in this browser (no account backend yet); they never enter a trip on their own.
export function toggleSaved(id: string, name?: string) {
  const on = ui.saved.includes(id)
  const saved = on ? ui.saved.filter((x) => x !== id) : [id, ...ui.saved]
  write(SAVED, saved)
  setUi({ saved })
  if (!on) toast(`Đã lưu ${name ?? 'nơi này'}`)
}

// Journeys started in this browser, newest first: what "Chuyến của tôi" asks the server about.
export function rememberTrip(id: string) {
  const trips = [id, ...ui.trips.filter((x) => x !== id)].slice(0, 20)
  write(TRIPS, trips)
  setUi({ trips })
}
export function forgetTrip(id: string) {
  const trips = ui.trips.filter((x) => x !== id)
  write(TRIPS, trips)
  setUi({ trips })
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
