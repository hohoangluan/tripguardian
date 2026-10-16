import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import * as api from './api'
import type { Action, ActPreview, Diff, PlanOutput, ProgressEvent, View } from './types'
import { useTrip } from '../trip'
import { mergeSuggestions, PlanningGate } from './current'

interface PlanningCtx {
  view: View | null
  diff: Diff | null
  lodgingProgress: ProgressEvent | null
  error: string | null
  busy: boolean
  act: (a: Action) => Promise<boolean>
  previewAct: (a: Action) => Promise<ActPreview | null>
  editPreview: ActPreview | null
  dismissPreview: () => void
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
  const currentView = useRef(view)
  currentView.current = view
  const [diff, setDiff] = useState<Diff | null>(null)
  const [lodgingProgress, setLodgingProgress] = useState<ProgressEvent | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [tick, setTick] = useState(0)
  const [preview, setPreview] = useState<{ result: ActPreview; ticket: ReturnType<PlanningGate['previewTicket']>; revision: number; view: View } | null>(null)
  const gate = useRef(new PlanningGate())
  const gateId = useRef<string | null | undefined>(undefined)
  const pending = useRef(0)
  if (gateId.current !== id) {
    gate.current.reset(id)
    gateId.current = id
    pending.current = 0
  }
  const accept = useCallback((ticket: ReturnType<PlanningGate['ticket']>, revision: number, incoming: View, mutation = false) => {
    if (!id || !api.acceptsRevision(id, revision) || !gate.current.accept(ticket, revision, mutation)) return false
    setView(incoming)
    return true
  }, [id])

  useEffect(() => { setView(null); setDiff(null); setError(null); setBusy(false); setLodgingProgress(null) }, [id])

  useEffect(() => {
    if (!id) return
    let live = true
    const ticket = gate.current.ticket()
    api.loadPlanning(id).then(
      (r) => {
        if (!live) return
        if (accept(ticket, r.revision, r.view)) setError(null)
      },
      () => {
        if (live && ticket.generation === gate.current.ticket().generation && ticket.epoch === gate.current.ticket().epoch) setError(OFFLINE)
      },
    )
    return () => {
      live = false
    }
  }, [id, tick, accept])

  useEffect(() => {
    if (!id || busy || view?.lodging.status !== 'pending') return
    const ticket = gate.current.ticket()
    const unsubscribe = api.watchLodging(id, (e) => {
      if (pending.current || !gate.current.accept(ticket, e.revision)) return
      if (e.event === 'progress') setLodgingProgress(e.data as ProgressEvent)
      // The server sends a bare View on `view`; the fallback also accepts a wrapped { view } shape.
      if (e.event === 'view') accept(ticket, e.revision, (e.data as { view: View }).view ?? (e.data as View))
    })
    return unsubscribe
  }, [id, busy, view?.lodging.status, view?.suggestions?.token, accept])

  useEffect(() => {
    if (!id || busy || view?.suggestions?.status !== 'pending') return
    const token = view.suggestions.token
    let live = true
    let timer: ReturnType<typeof setTimeout>
    const poll = async () => {
      const ticket = gate.current.ticket()
      try {
        const result = await api.readSuggestions(id)
        if (!live || !api.acceptsRevision(id, result.revision) || !gate.current.accept(ticket, result.revision)) return
        setView(current => current?.suggestions?.token === token ? mergeSuggestions(current, result) : current)
        if (result.status === 'pending') timer = setTimeout(poll, 300)
      } catch {
        if (!live || ticket.generation !== gate.current.ticket().generation || ticket.epoch !== gate.current.ticket().epoch) return
        setView(current => current?.suggestions?.token === token ? {
          ...current, suggestions: { ...current.suggestions, status: 'unavailable', items: [] }, recommendations: [],
        } : current)
      }
    }
    timer = setTimeout(poll, 100)
    return () => { live = false; clearTimeout(timer) }
  }, [id, busy, view?.suggestions?.token, view?.suggestions?.status])

  const act = useCallback(
    async (a: Action) => {
      if (!id) return false
      gate.current.invalidate()
      const ticket = gate.current.ticket()
      pending.current++
      setBusy(true)
      try {
        const r = await api.act(id, a)
        if (accept(ticket, r.revision, r.view, true)) { setDiff(r.diff); setError(null); return true }
        return false
      } catch (e) {
        if (ticket.generation === gate.current.ticket().generation) setError(e instanceof api.PlanningError ? `Không thực hiện được: ${e.detail || e.status}` : OFFLINE)
        return false
      } finally {
        if (ticket.generation === gate.current.ticket().generation) { pending.current--; setBusy(pending.current > 0) }
      }
    },
    [id, accept],
  )

  const confirm = useCallback(async () => {
    if (!id) return null
    gate.current.invalidate()
    const ticket = gate.current.ticket()
    pending.current++
    setBusy(true)
    try {
      const out = await api.confirm(id)
      if (ticket.generation !== gate.current.ticket().generation) return null
      setError(null)
      return out
    } catch (e) {
      if (ticket.generation === gate.current.ticket().generation) setError(e instanceof api.PlanningError ? `Chưa chốt được: ${e.detail || e.status}` : OFFLINE)
      return null
    } finally {
      if (ticket.generation === gate.current.ticket().generation) { pending.current--; setBusy(pending.current > 0) }
    }
  }, [id])

  const previewAct = useCallback(async (a: Action): Promise<ActPreview | null> => {
    if (!id || !view || pending.current) return null
    const ticket = gate.current.previewTicket(view)
    setPreview(null)
    try {
      const result = await api.previewAct(id, a)
      if (result.view.suggestions?.session_id !== view.suggestions?.session_id
        || !api.acceptsRevision(id, result.revision) || !gate.current.acceptPreview(ticket, result.revision, currentView.current)) return null
      setPreview({ result, ticket, revision: result.revision, view })
      setError(null)
      return result
    } catch (e) {
      if (!gate.current.currentPreview(ticket, currentView.current)) return null
      setError(e instanceof api.PlanningError ? `Chưa xem trước được: ${e.detail || e.status}` : OFFLINE)
      return null
    }
  }, [id, view])

  // Ask the Planning Agent for one better layout; the server keeps it only if it passes the checks.
  const optimize = useCallback(async () => {
    if (!id) return
    gate.current.invalidate()
    const ticket = gate.current.ticket()
    pending.current++
    setBusy(true)
    try {
      const r = await api.runRecommend(id, view)
      if (r) accept(ticket, r.revision, r.view, true)
      else if (ticket.generation === gate.current.ticket().generation) setError(OFFLINE)
    } finally {
      if (ticket.generation === gate.current.ticket().generation) { pending.current--; setBusy(pending.current > 0) }
    }
  }, [id, view, accept])

  return (
    <Ctx.Provider value={{ view, diff, lodgingProgress, error, busy, act, previewAct,
      editPreview: preview && !busy && preview.view === view && gate.current.currentPreview(preview.ticket, view)
        && id && api.acceptsRevision(id, preview.revision) ? preview.result : null,
      dismissPreview: () => { gate.current.previewTicket(); setPreview(null) },
      confirm, optimize, reload: () => setTick((t) => t + 1) }}>
      {children}
    </Ctx.Provider>
  )
}

export function usePlanning() {
  const c = useContext(Ctx)
  if (!c) throw new Error('usePlanning outside PlanningProvider')
  return c
}
