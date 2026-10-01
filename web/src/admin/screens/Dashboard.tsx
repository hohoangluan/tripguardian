import { STATUS_LABEL } from '../../data/labels'
import type { Snapshot, Status } from '../../data/types'
import { navigate } from '../../router'
import { useDecisions } from '../decisions'
import { fmtAgo, STATUS_COLOR } from '../model'

const SHOWN: Status[] = ['VERIFIED', 'UNCERTAIN', 'OUTDATED', 'NEEDS_REVIEW']
const ASPECTS = ['experience', 'environment', 'service', 'effort', 'suitability', 'operation']
const COVER = { COMPLETE: '#1e3a34', PARTIAL: '#5d8a7c', NONE: '#cdd8d6' } as const

export function Dashboard({ snap }: { snap: Snapshot }) {
  const decisions = useDecisions()
  const exp = snap.places.filter((p) => p.kind === 'experience')
  const feats = exp.flatMap((p) => p.features)
  const byStatus = Object.fromEntries(SHOWN.map((s) => [s, feats.filter((f) => f.status === s).length])) as Record<Status, number>
  const pending = snap.review.filter((r) => !decisions[r.id]).length
  const obs = snap.system.observe
  const observeRate = obs ? Math.round(((obs.status.done ?? 0) / Math.max(1, obs.places)) * 100) : null

  return (
    <div className="a-page">
      <header className="a-head">
        <div>
          <h1>Dashboard</h1>
          <p>Vài con số để phát hiện vấn đề nhanh. Build gần nhất {fmtAgo(snap.build.at)}.</p>
        </div>
      </header>

      <div className="tiles">
        <Tile n={exp.length} label="Địa điểm có bằng chứng" sub={`+ ${snap.places.length - exp.length} chỉ có thông tin Google`} />
        <Tile n={byStatus.VERIFIED} label="Giá trị Verified" sub={`trên ${feats.length} giá trị`} />
        <Tile n={pending} label="Đang chờ review" sub="Mở hàng đợi" onClick={() => navigate('/admin/review')} tone={pending ? 'warn' : undefined} />
        <Tile n={byStatus.OUTDATED} label="Giá trị quá hạn" sub="cần làm mới nguồn" />
        <Tile n={observeRate === null ? '—' : `${observeRate}%`} label="Địa điểm đã đọc review" sub={obs ? `${obs.status.done ?? 0} / ${obs.places}, ${obs.status.failed ?? 0} lỗi` : 'chưa có'} tone={observeRate !== null && observeRate < 50 ? 'warn' : undefined} />
        <Tile n={snap.system.videos} label="Clip TikTok đã thu" sub={`${snap.places.filter((p) => p.videos.length).length} địa điểm có clip liên quan`} />
      </div>

      <section className="a-card">
        <h2>Trạng thái các giá trị</h2>
        <div className="stack" role="img" aria-label="Phân bố trạng thái">
          {SHOWN.map((s) => (
            <i key={s} title={`${STATUS_LABEL[s]}: ${byStatus[s]}`} style={{ flexGrow: byStatus[s], background: STATUS_COLOR[s] }} />
          ))}
        </div>
        <ul className="legend">
          {SHOWN.map((s) => (
            <li key={s}>
              <i style={{ background: STATUS_COLOR[s] }} />
              {s} <b>{byStatus[s]}</b>
            </li>
          ))}
        </ul>
      </section>

      <div className="a-grid2">
        <section className="a-card">
          <h2>Coverage theo khía cạnh</h2>
          <table className="a-table a-table--compact">
            <thead>
              <tr>
                <th>Khía cạnh</th>
                <th>Phân bố trên {exp.length} địa điểm</th>
                <th className="num">Complete</th>
                <th className="num">Partial</th>
                <th className="num">None</th>
              </tr>
            </thead>
            <tbody>
              {ASPECTS.map((a) => {
                const c = (k: string) => snap.build.coverage[`${a}=${k}`] ?? 0
                return (
                  <tr key={a}>
                    <td>{a}</td>
                    <td>
                      <div className="stack stack--thin">
                        {(['COMPLETE', 'PARTIAL', 'NONE'] as const).map((k) => (
                          <i key={k} title={`${k}: ${c(k)}`} style={{ flexGrow: c(k), background: COVER[k] }} />
                        ))}
                      </div>
                    </td>
                    <td className="num">{c('COMPLETE')}</td>
                    <td className="num">{c('PARTIAL')}</td>
                    <td className="num">{c('NONE')}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </section>

        <section className="a-card">
          <h2>Hôm nay</h2>
          <p className="a-muted">
            Phiên chuyến đi, kế hoạch hoàn thành và tỷ lệ khả thi sẽ hiện khi User Web ghi sự kiện. Bản thử chưa ghi sự kiện nào nên không có số để hiện.
          </p>
          <h2>Lỗi gần đây</h2>
          <ul className="errs">
            {snap.system.errors.slice(0, 5).map((e, i) => (
              <li key={i}>
                <time>{fmtAgo(e.at)}</time>
                <span>
                  {e.source}/{e.stage}
                </span>
                <code title={e.error}>{e.error.split(':')[0]}</code>
              </li>
            ))}
          </ul>
          <button className="a-link" onClick={() => navigate('/admin/system')}>
            Xem System Monitor
          </button>
        </section>
      </div>
    </div>
  )
}

function Tile({ n, label, sub, onClick, tone }: { n: number | string; label: string; sub: string; onClick?: () => void; tone?: 'warn' }) {
  const Tag = onClick ? 'button' : 'div'
  return (
    <Tag className={`tile${tone ? ` tile--${tone}` : ''}`} onClick={onClick}>
      <b>{typeof n === 'number' ? n.toLocaleString('vi-VN') : n}</b>
      <span>{label}</span>
      <small>{sub}</small>
    </Tag>
  )
}
