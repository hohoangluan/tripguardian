import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import * as api from './api'
import type { Action, Diff, PlanOutput, ProgressEvent, View } from './types'
import { useTrip } from '../trip'

interface PlanningCtx {
  view: View | null
  diff: Diff | null
  lodgingProgress: ProgressEvent | null
  error: string | null
  busy: boolean
  confirmedTrip: boolean // the journey has a confirmed plan; the one on screen may be an edit of it
  act: (a: Action) => Promise<void>
  confirm: () => Promise<PlanOutput | null>
  optimize: () => Promise<void>
  reload: () => void
}

const Ctx = createContext<PlanningCtx | null>(null)
const OFFLINE = 'Không kết nối được máy chủ xếp lịch. Bạn thử lại nhé.'

export function PlanningProvider({ children }: { children: ReactNode }) {
  const { trip } = useTrip()
  const id = trip.planningId
  // Back from another tab: the last view is on screen at once (journey.ts cache); it is read again only when it is old.
  const [view, setView] = useState<View | null>(() => (id ? api.peekPlanning(id)?.value.view ?? null : null))
  const [diff, setDiff] = useState<Diff | null>(null)
  const [lodgingProgress, setLodgingProgress] = useState<ProgressEvent | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [confirmedTrip, setConfirmedTrip] = useState(() => (id ? api.peekPlanning(id)?.value.confirmedTrip ?? false : false))
  const [tick, setTick] = useState(0)

  useEffect(() => {
    if (!id) {
      setView(null)
      return
    }
    let live = true
    // reload() (tick > 0) skips the cache. A view whose lodging is still being crawled is never taken as fresh.
    const hit = tick === 0 ? api.peekPlanning(id) : undefined
    if (hit) {
      setView(hit.value.view)
      setConfirmedTrip(hit.value.confirmedTrip)
      setError(null)
      if (hit.fresh && hit.value.view.lodging.status !== 'pending') return
    } else setView(null)
    api.loadPlanning(id).then(
      (r) => {
        if (!live) return
        // Something changed the journey while this was read: a shown view is newer than this answer.
        if (hit && (!r.current || hit.value.revision === r.revision)) return
        setView(r.view)
        setConfirmedTrip(r.confirmedTrip)
        setError(null)
      },
      () => {
        if (live && !hit) setError(OFFLINE)
      },
    )
    return () => {
      live = false
    }
  }, [id, tick])

  useEffect(() => {
    if (!id || view?.lodging.status !== 'pending') return
    const unsubscribe = api.watchLodging(id, (e) => {
      if (e.event === 'progress') setLodgingProgress(e.data as ProgressEvent)
      // The server sends a bare View on `view`; the fallback also accepts a wrapped { view } shape.
      if (e.event === 'view') {
        const next = (e.data as { view: View }).view ?? (e.data as View)
        setView(next)
        api.rememberPlanning(id, next, confirmedTrip, e.revision)
      }
    })
    return unsubscribe
  }, [id, view?.lodging.status, confirmedTrip])

  const act = useCallback(
    async (a: Action) => {
      if (!id) return
      setBusy(true)
      try {
        const r = await api.act(id, a)
        setView(r.view)
        setDiff(r.diff)
        setError(null)
      } catch (e) {
        setError(e instanceof api.PlanningError ? `Không thực hiện được: ${e.detail || e.status}` : OFFLINE)
      } finally {
        setBusy(false)
      }
    },
    [id],
  )

  const confirm = useCallback(async () => {
    if (!id) return null
    setBusy(true)
    try {
      const out = await api.confirm(id)
      setConfirmedTrip(true)
      setError(null)
      return out
    } catch (e) {
      setError(e instanceof api.PlanningError ? `Chưa chốt được: ${e.detail || e.status}` : OFFLINE)
      return null
    } finally {
      setBusy(false)
    }
  }, [id])

  // Ask the Planning Agent for one better layout; the server keeps it only if it passes the checks.
  const optimize = useCallback(async () => {
    if (!id) return
    setBusy(true)
    try {
      const r = await api.runRecommend(id, view)
      if (r) setView(r.view)
      else setError(OFFLINE)
    } finally {
      setBusy(false)
    }
  }, [id, view])

  return (
    <Ctx.Provider value={{ view, diff, lodgingProgress, error, busy, confirmedTrip, act, confirm, optimize, reload: () => { if (id) api.forgetPlanning(id); setTick((t) => t + 1) } }}>
      {children}
    </Ctx.Provider>
  )
}

export function usePlanning() {
  const c = useContext(Ctx)
  if (!c) throw new Error('usePlanning outside PlanningProvider')
  return c
}
