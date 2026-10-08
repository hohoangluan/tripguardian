import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { navigate } from '../../router'
import { requestStageEntry } from '../journey'
import { useTrip } from '../trip'
import * as api from './api'
import type { Action, Diff, View } from './types'

interface DecisionCtx {
  view: View | null
  diff: Diff | null
  error: string | null
  busy: boolean
  act: (a: Action) => Promise<void>
  say: (text: string, onSay: (soFar: string) => void) => Promise<void>
  reload: () => void
}

const Ctx = createContext<DecisionCtx | null>(null)
const OFFLINE = 'Không kết nối được máy chủ chọn nơi. Bạn thử lại nhé.'

// One Place Decision session per trip: the backend holds the state, the page only shows its view.
export function DecisionProvider({ children }: { children: ReactNode }) {
  const { trip, dispatch } = useTrip()
  const id = trip.decisionId
  const [view, setView] = useState<View | null>(null)
  const [diff, setDiff] = useState<Diff | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    setView(null)
    if (!id) return
    let live = true
    const origin = location.pathname + location.search
    api.loadDecision(id).then(
      (r) => {
        if (!live) return
        if (r.recoveredHandoff && origin === location.pathname + location.search) {
          dispatch({ type: 'set', patch: { journeyId: r.id, decisionId: r.id, planningId: r.id } })
          navigate('/app/plan')
          return
        }
        setView(r.view)
        setError(null)
      },
      (e) => {
        if (!live) return
        if (e instanceof api.DecisionError && e.status === 404) {
          dispatch({ type: 'set', patch: { decisionId: null } })
          setError('Phiên chọn nơi đã hết. Quay lại bước Hiểu chuyến đi để bắt đầu lại.')
        } else setError(OFFLINE)
      },
    )
    return () => {
      live = false
    }
  }, [id, tick, dispatch])

  const act = useCallback(
    async (a: Action) => {
      if (!id) return
      setBusy(true)
      try {
        const r = await api.act(id, a)
        dispatch({ type: 'set', patch: { planningId: null } })
        setView(r.view)
        setDiff(r.diff)
        setError(null)
        if (r.goto === 'understand') { requestStageEntry(id, 'trip'); navigate('/app/understand') }
      } catch (e) {
        setError(e instanceof api.DecisionError ? `Không thực hiện được: ${e.detail || e.status}` : OFFLINE)
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
            dispatch({ type: 'set', patch: { planningId: null } })
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

  return (
    <Ctx.Provider value={{ view, diff, error, busy, act, say, reload: () => setTick((t) => t + 1) }}>{children}</Ctx.Provider>
  )
}

export function useDecision() {
  const c = useContext(Ctx)
  if (!c) throw new Error('useDecision outside DecisionProvider')
  return c
}
