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
  const [view, setView] = useState<View | null>(null)
  const [diff, setDiff] = useState<Diff | null>(null)
  const [lodgingProgress, setLodgingProgress] = useState<ProgressEvent | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    setView(null)
    if (!id) return
    let live = true
    api.loadPlanning(id).then(
      (r) => {
        if (!live) return
        setView(r.view)
        setError(null)
      },
      () => {
        if (live) setError(OFFLINE)
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
      if (e.event === 'view') setView((e.data as { view: View }).view ?? (e.data as View))
    })
    return unsubscribe
  }, [id, view?.lodging.status])

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
    <Ctx.Provider value={{ view, diff, lodgingProgress, error, busy, act, confirm, optimize, reload: () => setTick((t) => t + 1) }}>
      {children}
    </Ctx.Provider>
  )
}

export function usePlanning() {
  const c = useContext(Ctx)
  if (!c) throw new Error('usePlanning outside PlanningProvider')
  return c
}
