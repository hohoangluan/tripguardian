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
  say: (text: string, onSay: (soFar: string) => void) => Promise<void>
  confirm: () => Promise<PlanOutput | null>
  reload: () => void
}

const Ctx = createContext<PlanningCtx | null>(null)
const OFFLINE = 'Không kết nối được máy chủ xếp lịch (python -m planning serve).'

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

  const say = useCallback(
    async (text: string, onSay: (soFar: string) => void) => {
      if (!id) return
      setBusy(true)
      let acc = ''
      try {
        await api.sendText(id, text, {
          say: (d) => {
            acc = d.replace !== undefined ? d.replace : acc + (d.delta ?? '')
            onSay(acc)
          },
          view: (r) => {
            setView(r.view)
            setDiff(r.diff)
          },
          error: (d) => setError(d.message),
        })
      } catch {
        setError(OFFLINE)
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

  return (
    <Ctx.Provider value={{ view, diff, lodgingProgress, error, busy, act, say, confirm, reload: () => setTick((t) => t + 1) }}>
      {children}
    </Ctx.Provider>
  )
}

export function usePlanning() {
  const c = useContext(Ctx)
  if (!c) throw new Error('usePlanning outside PlanningProvider')
  return c
}
