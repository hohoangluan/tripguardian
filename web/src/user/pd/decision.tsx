import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { mutateJourney, readJourney, requestStageEntry } from '../journey'
import { useTrip } from '../trip'
import { info } from '../lib'
import { getUi } from '../store'
import { go, warmPhotos } from '../ui/common'
import { primePlanning } from '../planning/api'
import * as api from './api'
import type { Action, Card, DecisionOutput, Diff, PlanPreview, View } from './types'
import type { Readback } from '../tu/types'
import { ReadbackSheet } from '../ui/ReadbackSheet'

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
  more: (group: string, n?: number) => Promise<void> // page n (1 = first) of a tab, or its next page
  loadingMore: string | null
}

const Ctx = createContext<DecisionCtx | null>(null)
const OFFLINE = 'Không kết nối được máy chủ chọn nơi. Bạn thử lại nhé.'
const DEBOUNCE_MS = 350

// What the screen shows the instant a place is picked, dropped or locked; the server's answer confirms it a moment later.
function guess(v: View, a: Action): View | null {
  if (a.type !== 'select' && a.type !== 'drop' && a.type !== 'lock' && a.type !== 'unlock') return null
  const id = a.place_id
  const picked = v.selected.includes(id)
  const pick = a.type === 'select' || a.type === 'drop'
  const on = a.type === 'select' || a.type === 'lock'
  if (pick ? on === picked : !picked || on === v.locked.includes(id)) return null // nothing changes, or a lock on a place that is not in the trip: let the server answer
  const mark = (c: Card): Card => (c.id === id ? { ...c, ...(pick ? { chosen: on } : { locked: on }) } : c)
  const cards = (list: Card[]) => list.map(mark)
  return {
    ...v,
    ...(pick ? { selected: on ? [...v.selected, id] : v.selected.filter((x) => x !== id) } : { locked: on ? [...v.locked, id] : v.locked.filter((x) => x !== id) }),
    groups: v.groups.map((g) => ({ ...g, cards: cards(g.cards) })),
    unverified: { ...v.unverified, cards: cards(v.unverified.cards) },
  }
}

// One Place Decision stage per journey: the backend holds the state, the page only shows its view.
export function DecisionProvider({ children }: { children: ReactNode }) {
  const { trip, dispatch } = useTrip()
  const id = trip.decisionId
  const [view, setView] = useState<View | null>(null)
  const [diff, setDiff] = useState<Diff | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [gate, setGate] = useState<{ readback: Readback; missing: string[]; key: number } | null>(null)
  const [tick, setTick] = useState(0)
  const [preview, setPreview] = useState<PreviewState>({ status: 'idle' })
  const seq = useRef(0)
  const shown = useRef<View | null>(null)
  const queued = useRef(0) // picks, drops and locks sent and not yet answered
  shown.current = view
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
    setGate(null)
    setView(null)
    setPreview({ status: 'idle' })
    if (!id) return
    let live = true
    const origin = location.pathname + location.search
    const FIRST_SCREEN = 8 // cards of the open tab that are on view at once
    const WARM_MS = 500 // longest the list waits for its pictures: on a slow line it shows anyway
    api.loadDecision(id).then(
      async (r) => {
        if (!live) return
        const first = r.view.groups.find((g) => g.id === getUi().tab) ?? r.view.groups.find((g) => g.id !== 'anchors')
        await warmPhotos((first?.cards ?? []).slice(0, FIRST_SCREEN).map((c) => info(c.id)?.photos[0]?.src), WARM_MS)
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
          setError(e.status === 404 ? 'Phiên chọn nơi đã hết. Quay lại bước Tìm hiểu để bắt đầu lại.' : null)
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
      const before = shown.current
      const early = before && guess(before, a)
      // A pick, drop or lock shows at once and leaves the buttons alone: the next click can follow before the server answers.
      // The server takes them in order and only the last answer replaces the screen, so an earlier one never undoes a later click.
      if (early) {
        shown.current = early
        setView(early)
        queued.current += 1
      } else setBusy(true)
      try {
        const r = await api.act(id, a)
        dispatch({ type: 'set', patch: { planningId: null } })
        if (!early || queued.current === 1) setView(r.view)
        setDiff(r.diff)
        setError(null)
        if (r.goto === 'understand') {
          requestStageEntry(id, 'trip')
          go('/understand')
        } else refreshPreview()
        return true
      } catch (e) {
        if (early) setTimeout(() => { void api.loadDecision(id).then((r) => { if (queued.current === 0) setView(r.view) }, () => {}) }, 0) // the server said no: show what it holds
        setError(e instanceof api.DecisionError ? `Không thực hiện được: ${e.detail || e.status}` : OFFLINE)
        return false
      } finally {
        if (early) queued.current -= 1
        else setBusy(false)
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

  // Planning owns the gate; choosing places stays available until the user asks to schedule.
  const toPlan = useCallback(async () => {
    if (!id) return false
    setBusy(true)
    const origin = location.pathname + location.search
    try {
      const created = await mutateJourney(id, 'decision', 'advance')
      const out = created.outputs.decision as DecisionOutput
      if (origin !== location.pathname + location.search) return false
      setGate(null)
      setError(null)
      dispatch({
        type: 'set',
        patch: { selected: out.confirmed.map((c) => c.id), locked: out.confirmed.filter((c) => c.role !== 'selected').map((c) => c.id), planningId: created.id },
      })
      primePlanning(created.id)
      go('/plan')
      return true
    } catch (e) {
      if (origin !== location.pathname + location.search) return false
      if (e instanceof api.DecisionError && e.status === 409 && e.readback && (e.detail === 'trip_incomplete' || e.missing !== undefined)) {
        setGate({ readback: e.readback, missing: e.missing ?? e.readback.missing ?? [], key: Date.now() })
        setError(null)
      } else if (e instanceof api.DecisionError) {
        // A 409 with only a code (for example "partial"): open the gate when the trip still misses something, else say it in words.
        let opened = false
        if (e.status === 409) {
          try {
            const rb = await readJourney<Readback>(id, 'trip/readback')
            if (rb.missing?.length && origin === location.pathname + location.search) { setGate({ readback: rb, missing: rb.missing, key: Date.now() }); setError(null); opened = true }
          } catch { /* fall through to the message */ }
        }
        if (!opened) setError(e.status === 409 ? 'Các nơi đã chọn chưa đủ để xếp thành lịch trọn vẹn. Bạn thử thêm hoặc đổi vài nơi nhé.' : 'Chưa xếp lịch được lúc này. Bạn thử lại sau ít giây nhé.')
      } else setError(OFFLINE)
      return false
    } finally {
      setBusy(false)
    }
  }, [id, dispatch])

  // One page of a tab; one request per tab at a time however fast the user clicks.
  const more = useCallback(async (group: string, n?: number) => {
    if (!id || loading.current === group) return
    loading.current = group
    setLoadingMore(group)
    try {
      const r = await api.gotoPage(id, group, n)
      setView(r.view)
    } catch {
      setError(OFFLINE)
    } finally {
      loading.current = null
      setLoadingMore(null)
    }
  }, [id])

  return (
    <Ctx.Provider value={{ view, diff, error, busy, preview, act, say, toPlan, reload: () => setTick((t) => t + 1), more, loadingMore }}>{children}
      {id && gate && <ReadbackSheet key={gate.key} id={id} initial={gate.readback} missing={gate.missing} onClose={() => setGate(null)} onAdvance={toPlan} onView={next => { setView(next); dispatch({ type: 'set', patch: { planningId: null } }); refreshPreview() }} />}
    </Ctx.Provider>
  )
}

export function useDecision() {
  const c = useContext(Ctx)
  if (!c) throw new Error('useDecision outside DecisionProvider')
  return c
}
