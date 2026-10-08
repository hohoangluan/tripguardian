import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { mutateJourney, requestStageEntry } from '../journey'
import { runRecommend } from '../planning/api'
import type { View as PlanView } from '../planning/types'
import { useTrip } from '../trip'
import { go } from '../ui/common'
import * as api from './api'
import type { Action, DecisionOutput, Diff, PlanPreview, View } from './types'

// "building" while the background schedule for the current selection is being made (Planning, not confirmed).
export type PreviewState = { status: 'idle' | 'building' } | PlanPreview

interface DecisionCtx {
  view: View | null
  diff: Diff | null
  error: string | null
  busy: boolean
  preview: PreviewState
  act: (a: Action) => Promise<boolean>
  say: (text: string, onSay: (soFar: string) => void) => Promise<Diff | null>
  toPlan: () => Promise<boolean>
  reload: () => void
  more: (group: string) => Promise<void>
  loadingMore: string | null
}

const Ctx = createContext<DecisionCtx | null>(null)
const OFFLINE = 'Không kết nối được máy chủ chọn nơi. Bạn thử lại nhé.'
const DEBOUNCE_MS = 350

// One Place Decision stage per journey: the backend holds the state, the page only shows its view.
export function DecisionProvider({ children }: { children: ReactNode }) {
  const { trip, dispatch } = useTrip()
  const id = trip.decisionId
  const [view, setView] = useState<View | null>(null)
  const [diff, setDiff] = useState<Diff | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [tick, setTick] = useState(0)
  const [preview, setPreview] = useState<PreviewState>({ status: 'idle' })
  const seq = useRef(0)
  const [loadingMore, setLoadingMore] = useState<string | null>(null)
  const loading = useRef<string | null>(null)

  // Background schedule: after each change settles, ask the harness what the current selection would get.
  const refreshPreview = useCallback(() => {
    if (!id) return
    const mine = ++seq.current
    setPreview({ status: 'building' })
    setTimeout(() => {
      if (mine !== seq.current) return
      api.previewPlan(id).then(
        (p) => { if (mine === seq.current) setPreview(p) },
        () => { if (mine === seq.current) setPreview({ status: 'idle' }) },
      )
    }, DEBOUNCE_MS)
  }, [id])

  useEffect(() => {
    setView(null)
    setPreview({ status: 'idle' })
    if (!id) return
    let live = true
    const origin = location.pathname + location.search
    api.loadDecision(id).then(
      (r) => {
        if (!live) return
        if (r.recoveredHandoff && origin === location.pathname + location.search) {
          dispatch({ type: 'set', patch: { journeyId: r.id, decisionId: r.id, planningId: r.id } })
          go('/plan')
          return
        }
        setView(r.view)
        setError(null)
        if (r.view.selected.length && r.stage === 'decision') refreshPreview()
      },
      (e) => {
        if (!live) return
        if (e instanceof api.DecisionError && (e.status === 404 || e.status === 409)) {
          dispatch({ type: 'set', patch: { decisionId: null } })
          setError(e.status === 404 ? 'Phiên chọn nơi đã hết. Quay lại bước Hiểu chuyến đi để bắt đầu lại.' : null)
        } else setError(OFFLINE)
      },
    )
    return () => {
      live = false
    }
  }, [id, tick, dispatch, refreshPreview])

  const act = useCallback(
    async (a: Action) => {
      if (!id) return false
      setBusy(true)
      try {
        const r = await api.act(id, a)
        dispatch({ type: 'set', patch: { planningId: null } })
        setView(r.view)
        setDiff(r.diff)
        setError(null)
        if (r.goto === 'understand') {
          requestStageEntry(id, 'trip')
          go('/understand')
        } else refreshPreview()
        return true
      } catch (e) {
        setError(e instanceof api.DecisionError ? `Không thực hiện được: ${e.detail || e.status}` : OFFLINE)
        return false
      } finally {
        setBusy(false)
      }
    },
    [id, dispatch, refreshPreview],
  )

  const say = useCallback(
    async (text: string, onSay: (soFar: string) => void) => {
      if (!id) return null
      setBusy(true)
      let acc = ''
      let last: Diff | null = null
      try {
        await api.sendText(id, text, {
          say: (d) => {
            acc = d.replace !== undefined ? d.replace : acc + (d.delta ?? '')
            onSay(acc)
          },
          view: (r) => {
            dispatch({ type: 'set', patch: { planningId: null } })
            setView(r.view)
            setDiff(r.diff)
            last = r.diff
          },
          error: (d) => setError(d.message),
        })
        refreshPreview()
        return last
      } catch {
        setError(OFFLINE)
        return null
      } finally {
        setBusy(false)
      }
    },
    [id, dispatch, refreshPreview],
  )

  // Confirm the selection and hand it to Planning (journey decision -> planning), then ask for one proposal.
  const toPlan = useCallback(async () => {
    if (!id) return false
    setBusy(true)
    const origin = location.pathname + location.search
    try {
      const created = await mutateJourney(id, 'decision', 'advance')
      const out = created.outputs.decision as DecisionOutput
      await runRecommend(created.id, (created.result as { view: PlanView }).view)
      if (origin !== location.pathname + location.search) return false
      dispatch({
        type: 'set',
        patch: { selected: out.confirmed.map((c) => c.id), locked: out.confirmed.filter((c) => c.role !== 'selected').map((c) => c.id), planningId: created.id },
      })
      go('/plan')
      return true
    } catch (e) {
      setError(e instanceof api.DecisionError ? `Chưa xếp lịch được: ${e.detail || e.status}` : OFFLINE)
      return false
    } finally {
      setBusy(false)
    }
  }, [id, dispatch])

  // The next page of one display group; one request per group at a time however fast the user scrolls.
  const more = useCallback(async (group: string) => {
    if (!id || loading.current === group) return
    loading.current = group
    setLoadingMore(group)
    try {
      const r = await api.morePlaces(id, group)
      setView(r.view)
    } catch {
      setError(OFFLINE)
    } finally {
      loading.current = null
      setLoadingMore(null)
    }
  }, [id])

  return (
    <Ctx.Provider value={{ view, diff, error, busy, preview, act, say, toPlan, reload: () => setTick((t) => t + 1), more, loadingMore }}>{children}</Ctx.Provider>
  )
}

export function useDecision() {
  const c = useContext(Ctx)
  if (!c) throw new Error('useDecision outside DecisionProvider')
  return c
}
