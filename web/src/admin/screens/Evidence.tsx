import { useMemo, useState } from 'react'
import { featureLabel, valueLabel } from '../../data/labels'
import type { Snapshot } from '../../data/types'
import { navigate } from '../../router'
import { decide, useDecisions } from '../decisions'
import { StatusPill } from './Places'

type Filter = 'all' | 'fresh' | 'outdated' | 'conflicting' | 'single'
const FILTERS: { id: Filter; label: string }[] = [
  { id: 'all', label: 'Tất cả' },
  { id: 'fresh', label: 'Fresh' },
  { id: 'outdated', label: 'Outdated' },
  { id: 'conflicting', label: 'Conflicting' },
  { id: 'single', label: 'Single source' },
]

export function Evidence({ snap }: { snap: Snapshot }) {
  const decisions = useDecisions()
  const [filter, setFilter] = useState<Filter>('conflicting')
  const records = useMemo(
    () =>
      snap.places
        .filter((p) => p.kind === 'experience')
        .flatMap((p) => p.features.map((f) => ({ p, f, conflicting: Object.keys(f.distribution).length > 1 && f.rawStatus === 'uncertain' }))),
    [snap],
  )
  const rows = records
    .filter(({ f, conflicting }) =>
      filter === 'all'
        ? true
        : filter === 'fresh'
          ? f.status === 'VERIFIED' && (f.freshnessDays ?? 999) <= 90
          : filter === 'outdated'
            ? f.status === 'OUTDATED'
            : filter === 'conflicting'
              ? conflicting
              : f.n === 1,
    )
    .slice(0, 400)
  const counts = Object.fromEntries(
    FILTERS.map((x) => [
      x.id,
      x.id === 'all'
        ? records.length
        : records.filter(({ f, conflicting }) =>
            x.id === 'fresh' ? f.status === 'VERIFIED' && (f.freshnessDays ?? 999) <= 90 : x.id === 'outdated' ? f.status === 'OUTDATED' : x.id === 'conflicting' ? conflicting : f.n === 1,
          ).length,
    ]),
  )

  return (
    <div className="a-page">
      <header className="a-head">
        <div>
          <h1>Evidence</h1>
          <p>Mỗi dòng là một nhận định về một địa điểm. Xung đột chưa xử lý thì User Web hiển thị là chưa chắc chắn.</p>
        </div>
      </header>
      <div className="seg seg--admin" role="radiogroup" aria-label="Lọc bằng chứng">
        {FILTERS.map((x) => (
          <button key={x.id} role="radio" aria-checked={filter === x.id} className={filter === x.id ? 'is-on' : ''} onClick={() => setFilter(x.id)}>
            {x.label} <small>{counts[x.id]}</small>
          </button>
        ))}
      </div>
      <table className="a-table">
        <thead>
          <tr>
            <th>Địa điểm</th>
            <th>Nhận định</th>
            <th>Phân bố</th>
            <th>Nguồn</th>
            <th className="num">Độ mới</th>
            <th>Trạng thái</th>
            {filter === 'conflicting' && <th>Xử lý</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map(({ p, f }) => {
            const key = `evidence:${p.id}#${f.id}`
            const d = decisions[key]
            return (
              <tr key={key}>
                <td>
                  <button className="a-link" onClick={() => navigate(`/admin/places/${encodeURIComponent(p.id)}`)}>
                    {p.name}
                  </button>
                </td>
                <td>
                  {featureLabel(f.id)}: <b>{valueLabel(f.value)}</b>
                </td>
                <td className="a-small">
                  {Object.entries(f.distribution)
                    .map(([v, n]) => `${valueLabel(v)} ${Math.round(n * 10) / 10}`)
                    .join(' / ')}
                </td>
                <td className="a-small">{Object.entries(f.bySource).map(([s, n]) => `${s} ${n}`).join(', ')}</td>
                <td className="num">{f.freshnessDays ?? '—'}</td>
                <td>
                  <StatusPill s={f.status} />
                </td>
                {filter === 'conflicting' && (
                  <td className="a-actions">
                    {d ? (
                      <span className="a-muted">{d.verdict === 'accept' ? 'Giữ chưa chắc' : d.verdict === 'report' ? 'Đã báo lỗi nguồn' : 'Đã yêu cầu làm mới'}</span>
                    ) : (
                      <>
                        <button className="a-btn a-btn--tiny" onClick={() => decide([key], 'accept')}>
                          Accept
                        </button>
                        <button className="a-btn a-btn--tiny" onClick={() => decide([key], 'report', 'value')}>
                          Report nguồn sai
                        </button>
                        <button className="a-btn a-btn--tiny a-btn--ghost" onClick={() => decide([key], 'refresh')}>
                          Refresh
                        </button>
                      </>
                    )}
                  </td>
                )}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
