import { useEffect, useState } from 'react'
import { navigate } from '../../router'
import { Icon, Page } from '../../ui/bits'
import { compare, DecisionError } from '../pd/api'
import { useDecision } from '../pd/decision'
import type { CompareResult } from '../pd/types'
import { useTrip } from '../trip'

export function Compare({ ids }: { ids: string[] }) {
  const { trip } = useTrip()
  const { view, act, busy } = useDecision()
  const [res, setRes] = useState<CompareResult | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [a, b] = ids

  useEffect(() => {
    if (!trip.decisionId || !a || !b) return
    let live = true
    compare(trip.decisionId, a, b).then(
      (r) => live && setRes(r),
      (e) =>
        live &&
        setErr(
          e instanceof DecisionError && e.status === 400
            ? 'Hai nơi này khác loại (một chỗ ăn, một nơi tham quan) nên không đặt cạnh nhau.'
            : 'Chưa so sánh được, thử lại sau.',
        ),
    )
    return () => {
      live = false
    }
  }, [trip.decisionId, a, b])

  if (ids.length < 2) return <div className="loading">Cần 2 nơi để so sánh.</div>
  if (err) return <div className="loading">{err}</div>
  if (!res) return <div className="loading">Đang so sánh</div>

  const cols = [res.a, res.b]
  const rows = [...res.sacrifice, ...res.rows]
  return (
    <Page className="page--wide">
      <button className="back" onClick={() => history.back()}>
        <Icon name="back" size={16} /> Quay lại
      </button>
      <header className="phead">
        <h1>So sánh nhanh</h1>
        <p>Chỉ hiện điểm khác nhau có bằng chứng. Số trong ngoặc là số người nhắc tới; “chưa biết” không có nghĩa là kém hơn.</p>
      </header>

      <div className="cmp" style={{ ['--cols' as string]: 2 }}>
        <div className="cmp__row cmp__row--head">
          <span />
          {cols.map((p) => (
            <div key={p.id} className="cmp__col">
              <button className="link cmp__name" onClick={() => navigate(`/app/place/${encodeURIComponent(p.id)}`)}>
                {p.name}
              </button>
            </div>
          ))}
        </div>
        {rows.length === 0 && <p className="block__hint">Hai nơi này không khác nhau ở điểm nào có bằng chứng.</p>}
        {rows.map((r) => (
          <div className="cmp__row" key={r.aspect}>
            <span className="cmp__label">{r.label}</span>
            {(['a', 'b'] as const).map((k) => (
              <span key={k} className={`cmp__cell${r.better === k ? ' is-best' : ''}`}>
                {r[k]}
              </span>
            ))}
          </div>
        ))}
        <div className="cmp__row cmp__row--act">
          <span />
          {cols.map((p) => {
            const on = view?.selected.includes(p.id) ?? false
            return (
              <div key={p.id}>
                <button className={`btn btn--small${on ? ' btn--chosen' : ''}`} disabled={busy} onClick={() => act(on ? { type: 'drop', place_id: p.id } : { type: 'select', place_id: p.id })}>
                  {on ? 'Đã chọn' : 'Chọn nơi này'}
                </button>
              </div>
            )
          })}
        </div>
      </div>
    </Page>
  )
}
