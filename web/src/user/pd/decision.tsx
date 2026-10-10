import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { usePath } from '../../router'
import { cacheEpoch, cacheGet, cachePut, mutateJourney, requestStageEntry } from '../journey'
import { runRecommend } from '../planning/api'
import type { View as PlanView } from '../planning/types'
import { useTrip } from '../trip'
import { go } from '../ui/common'
import * as api from './api'
import { PreviewQueue, previewKey } from './previewQueue'
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

// What Chọn nơi shows, in the shared journey cache (journey.ts) under `${journey}:decision`: the journey's stage when it
// was read, and the view. Every change goes through journey.ts, which empties the entry; the provider refills it with
// the view the change answered with.
interface Loaded { view: View; stage: string }
const peek = (id: string | null | undefined) => (id ? cacheGet<Loaded>(id, 'decision') : undefined)

// One Place Decision stage per journey: the backend holds the state, the page only shows its view.
export function DecisionProvider({ children }: { children: ReactNode }) {
  const { trip, dispatch } = useTrip()
  const id = trip.decisionId
  const [view, setView] = useState<View | null>(() => peek(id)?.value.view ?? null)
  const [diff, setDiff] = useState<Diff | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [tick, setTick] = useState(0)
  const [preview, setPreview] = useState<PreviewState>({ status: 'idle' })
  const [stage, setStage] = useState<string | null>(() => peek(id)?.value.stage ?? null)
  const queue = useRef(new PreviewQueue<PlanPreview>(DEBOUNCE_MS))
  const path = usePath().split('?')[0]
  const selecting = path === '/app/explore' || path.startsWith('/app/explore/')
  const [loadingMore, setLoadingMore] = useState<string | null>(null)
  const loading = useRef<string | null>(null)

  // Presentation revisions and paging do not change the schedule's dependencies.
  const cards = [...(view?.groups.flatMap((group) => group.cards) ?? []), ...(view?.unverified.cards ?? [])]
  const key = id && view ? previewKey(id, view.selected, view.locked, {
    trip: trip.searchInput,
    profile: view.profile,
    days: view.days,
    budget: view.budget_vnd,
    selected: cards.filter((card) => view.selected.includes(card.id)).map((card) => ({ id: card.id, visit: card.visit, warnings: card.warnings, failed: card.failed, alternatives: card.alternatives })).sort((a, b) => a.id.localeCompare(b.id)),
    backups: cards.filter((card) => card.top && !view.selected.includes(card.id)).map((card) => card.id).sort(),
  }) : null
  useEffect(() => {
    if (!id || !key || !selecting || stage !== 'decision') {
      queue.current.cancel()
      setPreview({ status: 'idle' })
      return
    }
    setPreview({ status: 'building' })
    queue.current.request(key, () => api.previewPlan(id), setPreview, () => setPreview({ status: 'idle' }))
  }, [id, key, selecting, stage, tick])
  useEffect(() => () => queue.current.cancel(), [])

  useEffect(() => {
    if (!id) {
      setView(null)
      setStage(null)
      return
    }
    let live = true
    const origin = location.pathname + location.search
    const hit = tick === 0 ? peek(id) : undefined // reload() skips the cache
    if (hit) {
      setView(hit.value.view)
      setStage(hit.value.stage)
      setError(null)
      if (hit.fresh) return
    } else setView(null)
    const epoch = cacheEpoch(id)
    api.loadDecision(id).then(
      (r) => {
        if (!live) return
        if (r.recoveredHandoff && origin === location.pathname + location.search) {
          dispatch({ type: 'set', patch: { journeyId: r.id, decisionId: r.id, planningId: r.id } })
          go('/plan')
          return
        }
        if (!r.recoveredHandoff) cachePut(id, 'decision', { view: r.view, stage: r.stage } satisfies Loaded, epoch)
        if (hit && epoch !== cacheEpoch(id)) return // a change landed while this was read: what is shown is newer
        setView(r.view)
        setStage(r.stage)
        setError(null)
      },
      (e) => {
        if (!live) return
        if (e instanceof api.DecisionError && (e.status === 404 || e.status === 409)) {
          dispatch({ type: 'set', patch: { decisionId: null } })
          setError(e.status === 404 ? 'Phiên chọn nơi đã hết. Quay lại bước Tìm hiểu để bắt đầu lại.' : null)
        } else if (!hit) setError(OFFLINE)
      },
    )
    return () => {
      live = false
    }
  }, [id, tick, dispatch])

  const act = useCallback(
    async (a: Action) => {
      if (!id) return false
      setBusy(true)
      try {
        const r = await api.act(id, a)
        dispatch({ type: 'set', patch: { planningId: null } })
        setView(r.view)
        setStage(r.goto === 'understand' ? 'trip' : 'decision')
        setDiff(r.diff)
        setError(null)
        if (r.goto !== 'understand') cachePut(id, 'decision', { view: r.view, stage: 'decision' } satisfies Loaded)
        if (r.goto === 'understand') {
          requestStageEntry(id, 'trip')
          go('/understand')
        }
        return true
      } catch (e) {
        setError(e instanceof api.DecisionError ? `Không thực hiện được: ${e.detail || e.status}` : OFFLINE)
        return false
      } finally {
        setBusy(false)
      }
    },
    [id, dispatch],
  )

  const say = useCallback(
    async (text: string, onSay: (soFar: string) => void) => {
      if (!id) return null
      setBusy(true)
      let acc = ''
      let last: Diff | null = null
      let lastView: View | null = null
      try {
        await api.sendText(id, text, {
          say: (d) => {
            acc = d.replace !== undefined ? d.replace : acc + (d.delta ?? '')
            onSay(acc)
          },
          view: (r) => {
            dispatch({ type: 'set', patch: { planningId: null } })
            setView(r.view)
            setStage('decision')
            setDiff(r.diff)
            last = r.diff
            lastView = r.view
          },
          error: (d) => setError(d.message),
        })
        if (lastView) cachePut(id, 'decision', { view: lastView, stage: 'decision' } satisfies Loaded)
        return last
      } catch {
        setError(OFFLINE)
        return null
      } finally {
        setBusy(false)
      }
    },
    [id, dispatch],
  )

  // Confirm the selection and hand it to Planning (journey decision -> planning), then ask for one proposal.
  const toPlan = useCallback(async () => {
    if (!id) return false
    queue.current.cancel()
    setPreview({ status: 'idle' })
    setBusy(true)
    const origin = location.pathname + location.search
    try {
      const created = await mutateJourney(id, 'decision', 'advance')
      setStage('planning')
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
      const epoch = cacheEpoch(id)
      const r = await api.morePlaces(id, group)
      setView(r.view)
      cachePut(id, 'decision', { view: r.view, stage: 'decision' } satisfies Loaded, epoch)
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
