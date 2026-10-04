import { useEffect, useState } from 'react'
import { placeById } from '../../data/store'
import { navigate } from '../../router'
import { Icon, Page, PlaceCover } from '../../ui/bits'
import { LineArt } from '../../ui/LineArt'
import { compare, DecisionError } from '../pd/api'
import { useDecision } from '../pd/decision'
import type { CompareResult, CompareRow } from '../pd/types'
import { area } from '../search'
import { useTrip } from '../trip'

// UI spec §4 Trang 6: 2 (at most 3) places side by side, only where they differ. The user decides.
// The API compares pairs, so a third place is compared against the first and the rows are merged.

interface Row {
  aspect: string
  label: string
  cells: string[]
  best: number[] // columns the evidence favours on this aspect
  sacrifice: boolean
}

function merge(results: CompareResult[]): Row[] {
  const rows = new Map<string, Row>()
  results.forEach((r, k) => {
    const add = (x: CompareRow, sacrifice: boolean) => {
      const row = rows.get(x.aspect) ?? { aspect: x.aspect, label: x.label, cells: [], best: [], sacrifice }
      row.cells[0] ??= x.a
      row.cells[k + 1] = x.b
      if (x.better === 'a' && !row.best.includes(0)) row.best.push(0)
      if (x.better === 'b') row.best.push(k + 1)
      row.sacrifice ||= sacrifice
      rows.set(x.aspect, row)
    }
    r.sacrifice.forEach((x) => add(x, true))
    r.rows.forEach((x) => add(x, false))
  })
  return [...rows.values()]
}

export function Compare({ ids }: { ids: string[] }) {
  const { trip } = useTrip()
  const { view, act, busy } = useDecision()
  const [res, setRes] = useState<CompareResult[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [lean, setLean] = useState<number | null>(null)
  const [a, ...rest] = ids.slice(0, 3)

  useEffect(() => {
    if (!trip.decisionId || !a || !rest.length) return
    let live = true
    Promise.all(rest.map((b) => compare(trip.decisionId!, a, b))).then(
      (r) => live && setRes(r),
      (e) =>
        live &&
        setErr(
          e instanceof DecisionError && e.status === 400
            ? 'Các nơi này khác loại (một chỗ ăn, một nơi tham quan) nên không đặt cạnh nhau.'
            : 'Chưa so sánh được, thử lại sau.',
        ),
    )
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trip.decisionId, ids.join()])

  if (ids.length < 2) return <div className="loading loading--error">Cần ít nhất 2 nơi để so sánh.</div>
  if (err) return <div className="loading loading--error">{err}</div>
  if (!res) return <div className="loading">Đang đặt cạnh nhau</div>

  const cols = [res[0].a, ...res.map((r) => r.b)]
  const rows = merge(res)
  // The closing question: two aspects where different places win.
  const pivots = rows.filter((r) => r.best.length === 1)
  const q = pivots.length >= 2 && pivots[0].best[0] !== pivots[1].best[0] ? [pivots[0], pivots[1]] : null

  return (
    <Page>
      <button className="link pd-back" onClick={() => history.back()}>
        <Icon name="back" size={15} /> Quay lại
      </button>
      <header className="uhead">
        <h1>So sánh nhanh</h1>
        <p>Chỉ hiện những điểm các nơi khác nhau, có bằng chứng. “Chưa biết” không có nghĩa là kém hơn.</p>
      </header>

      <div className="cmp-wrap">
        <table className="cmp" style={{ ['--cols' as string]: cols.length }}>
          <thead>
            <tr>
              <th className="cmp__corner" />
              {cols.map((c, i) => {
                const p = placeById(c.id)
                return (
                  <th key={c.id} className={lean === i ? 'is-lean' : ''}>
                    <div className="cmp__cover"><PlaceCover id={c.id} fallback={<LineArt variant="spot" seed={c.name.length} />} /></div>
                    <button className="cmp__name" onClick={() => navigate(`/app/place/${encodeURIComponent(c.id)}`)}>
                      {c.name}
                    </button>
                    {p && <small>{[p.category, area(p)].filter(Boolean).join(' · ')}</small>}
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={cols.length + 1} className="hint">
                  Các nơi này không khác nhau ở điểm nào có bằng chứng.
                </td>
              </tr>
            )}
            {rows.map((r) => (
              <tr key={r.aspect}>
                <th scope="row">{r.label}</th>
                {cols.map((c, i) => (
                  <td key={c.id} className={`${r.best.includes(i) ? 'is-best' : ''}${lean === i ? ' is-lean' : ''}`}>
                    {r.best.includes(i) && <i className="cmp__dot" aria-label="Có lợi hơn ở điểm này" />}
                    <span className={r.cells[i] ? '' : 'unknown'}>{r.cells[i] ?? 'Chưa biết'}</span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th />
              {cols.map((c, i) => {
                const on = view?.selected.includes(c.id) ?? false
                return (
                  <td key={c.id} className={lean === i ? 'is-lean' : ''}>
                    <button className={`btn btn--wide${on ? ' btn--chosen' : ''}`} disabled={busy} onClick={() => !on && act({ type: 'select', place_id: c.id })}>
                      {on ? (
                        <>
                          <Icon name="check" size={16} /> Đã giữ
                        </>
                      ) : (
                        'Giữ nơi này'
                      )}
                    </button>
                    <button className="link cmp__drop" disabled={busy} onClick={() => act({ type: 'drop', place_id: c.id })}>
                      Bỏ nơi này
                    </button>
                  </td>
                )
              })}
            </tr>
          </tfoot>
        </table>
      </div>

      {q && (
        <section className="cmp-ask">
          <h2>
            Bạn ưu tiên {q[0].label.toLowerCase()} hay {q[1].label.toLowerCase()} hơn?
          </h2>
          <div className="chips">
            {q.map((r) => (
              <button key={r.aspect} type="button" className={`chip${lean === r.best[0] ? ' is-on' : ''}`} onClick={() => setLean(r.best[0])}>
                {r.label}
              </button>
            ))}
          </div>
          {lean !== null && <p className="hint">Nơi hợp ưu tiên này được tô nhạt bên trên. Bạn vẫn là người bấm giữ.</p>}
        </section>
      )}

      <p className="cmp-note hint">Bạn chốt, mình không chọn thay.</p>
    </Page>
  )
}
