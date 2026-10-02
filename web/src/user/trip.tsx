import { createContext, useContext, useEffect, useReducer, type ReactNode } from 'react'
import type { Vehicle } from '../data/store'
import type { SearchInput } from './tu/types'

export type Who = 'partner' | 'friends' | 'kids' | 'parents' | 'solo'
export type Weight = 'love' | 'avoid'
export type DropReason = 'far' | 'crowded' | 'pricey' | 'dislike' | 'visited'

export interface Pref {
  weight: Weight
  from: 'answer' | 'profile'
}

export interface TripState {
  experience: 'first' | 'returning' | null
  startWith: string | null
  startDate: string
  days: number
  who: Who[]
  people: number
  vehicle: Vehicle | null
  lodging: string | null // place id or free text address
  mustVisit: string[]
  arriveAt: string // first day, HH:MM
  leaveAt: string // last day, HH:MM (hard rule)
  rules: { maxLegMin: number | null; avoidSteep: boolean; dayEnd: string }
  prefs: Record<string, Pref>
  pace: 'slow' | 'normal' | 'packed' | null
  answered: string[]
  selected: string[]
  locked: string[]
  dropped: { id: string; reason: DropReason | null }[]
  moved: Record<string, number> // place id -> day index chosen by a fix
  relaxed: string[] // rule keys the user agreed to relax
  feedback: Record<string, string>
  searchInput?: SearchInput // from Trip Understanding; Place Decision reads it later
  decisionId: string | null // Place Decision session (src/decision); the backend holds the curation state
}

const today = () => {
  const d = new Date()
  d.setDate(d.getDate() + 14)
  return d.toISOString().slice(0, 10)
}

export const initialTrip: TripState = {
  experience: null,
  startWith: null,
  startDate: today(),
  days: 3,
  who: [],
  people: 2,
  vehicle: null,
  lodging: null,
  mustVisit: [],
  arriveAt: '09:00',
  leaveAt: '15:00',
  rules: { maxLegMin: null, avoidSteep: false, dayEnd: '21:30' },
  prefs: {},
  pace: null,
  answered: [],
  selected: [],
  locked: [],
  dropped: [],
  moved: {},
  relaxed: [],
  feedback: {},
  decisionId: null,
}

export type Action =
  | { type: 'set'; patch: Partial<TripState> }
  | { type: 'rules'; patch: Partial<TripState['rules']> }
  | { type: 'pref'; id: string; pref: Pref | null }
  | { type: 'answer'; key: string }
  | { type: 'select'; id: string }
  | { type: 'unselect'; id: string; reason?: DropReason | null }
  | { type: 'lock'; id: string }
  | { type: 'move'; id: string; day: number }
  | { type: 'relax'; key: string }
  | { type: 'reset' }

function reducer(s: TripState, a: Action): TripState {
  switch (a.type) {
    case 'set':
      return { ...s, ...a.patch }
    case 'rules':
      return { ...s, rules: { ...s.rules, ...a.patch } }
    case 'pref': {
      const prefs = { ...s.prefs }
      if (a.pref) prefs[a.id] = a.pref
      else delete prefs[a.id]
      return { ...s, prefs }
    }
    case 'answer':
      return s.answered.includes(a.key) ? s : { ...s, answered: [...s.answered, a.key] }
    case 'select':
      return s.selected.includes(a.id)
        ? s
        : { ...s, selected: [...s.selected, a.id], dropped: s.dropped.filter((d) => d.id !== a.id) }
    case 'unselect':
      return {
        ...s,
        selected: s.selected.filter((x) => x !== a.id),
        locked: s.locked.filter((x) => x !== a.id),
        dropped: [...s.dropped.filter((d) => d.id !== a.id), { id: a.id, reason: a.reason ?? null }],
      }
    case 'lock':
      return {
        ...s,
        locked: s.locked.includes(a.id) ? s.locked.filter((x) => x !== a.id) : [...s.locked, a.id],
        selected: s.selected.includes(a.id) ? s.selected : [...s.selected, a.id],
      }
    case 'move':
      return { ...s, moved: { ...s.moved, [a.id]: a.day } }
    case 'relax':
      return { ...s, relaxed: [...new Set([...s.relaxed, a.key])] }
    case 'reset':
      return initialTrip
  }
}

const KEY = 'tg.trip.v1'

function restore(): TripState {
  try {
    const raw = localStorage.getItem(KEY)
    if (raw) return { ...initialTrip, ...JSON.parse(raw) }
  } catch {
    /* storage unavailable: start fresh */
  }
  return initialTrip
}

const Ctx = createContext<{ trip: TripState; dispatch: (a: Action) => void } | null>(null)

export function TripProvider({ children }: { children: ReactNode }) {
  const [trip, dispatch] = useReducer(reducer, undefined, restore)
  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(trip))
    } catch {
      /* not persisted: fine for a session */
    }
  }, [trip])
  return <Ctx.Provider value={{ trip, dispatch }}>{children}</Ctx.Provider>
}

export function useTrip() {
  const c = useContext(Ctx)
  if (!c) throw new Error('useTrip outside TripProvider')
  return c
}

export const WHO_LABEL: Record<Who, string> = {
  partner: 'Người yêu',
  friends: 'Bạn bè',
  kids: 'Có trẻ em',
  parents: 'Bố mẹ',
  solo: 'Một mình',
}

export const DROP_LABEL: Record<DropReason, string> = {
  far: 'Quá xa',
  crowded: 'Quá đông',
  pricey: 'Quá đắt',
  dislike: 'Không thích',
  visited: 'Đã đi rồi',
}
