import { STATUS_LABEL } from '../../data/labels'
import type { Snapshot, Status } from '../../data/types'
import { navigate } from '../../router'
import { Icon } from '../../ui/bits'
import { useAnalytics, type Today } from '../analytics'
import { useDecisions } from '../decisions'
import { fmtAgo, riskOf, STATUS_COLOR, type Risk } from '../model'

const SHOWN: Status[] = ['VERIFIED', 'UNCERTAIN', 'OUTDATED', 'NEEDS_REVIEW']
const ASPECTS: [string, string][] = [
  ['experience', 'Trải nghiệm'],
  ['environment', 'Không gian'],
  ['service', 'Dịch vụ'],
  ['effort', 'Vận động'],
  ['suitability', 'Hợp với ai'],
  ['operation', 'Vận hành'],
]
const COVER = [
  ['COMPLETE', 'Đủ', 'var(--cov-full)'],
  ['PARTIAL', 'Một phần', 'var(--cov-part)'],
  ['NONE', 'Chưa có', 'var(--cov-none)'],
] as const
const RISKS: Risk[] = ['Cao', 'Vừa', 'Thấp']
const PACE = 5 // items per minute, the review-queue target

export function Dashboard({ snap }: { snap: Snapshot }) {
  const decisions = useDecisions()
  const exp = snap.places.filter((p) => p.kind === 'experience')
  const feats = exp.flatMap((p) => p.features)
  const byStatus = Object.fromEntries(SHOWN.map((s) => [s, feats.filter((f) => f.status === s).length])) as Record<Status, number>
  const open = snap.review.filter((r) => !decisions[r.id])
  const byRisk = Object.fromEntries(RISKS.map((k) => [k, open.filter((r) => riskOf(r) === k).length])) as Record<Risk, number>
  const obs = snap.system.observe
  const observeRate = obs ? Math.round(((obs.status.done ?? 0) / Math.max(1, obs.places)) * 100) : null
  const verifiedPct = Math.round((byStatus.VERIFIED / Math.max(1, feats.length)) * 100)
  const errors = snap.system.errors

  return (
    <div className="a-page">
      <header className="a-head">
        <div>
          <h1>Tổng quan</h1>
          <p>Việc cần làm trước, sức khỏe dữ liệu sau. Build gần nhất {fmtAgo(snap.build.at)}.</p>
        </div>
      </header>

      <div className="dash-top">
        <section className="todo">
          <p className="todo__eyebrow">Việc cần làm</p>
          <div className="todo__main">
            <b className="todo__n">{open.length.toLocaleString('vi-VN')}</b>
            <div>
              <p className="todo__what">mục chờ duyệt</p>
              <p className="todo__eta">{open.length ? `≈ ${Math.ceil(open.length / PACE)} phút ở nhịp ${PACE} mục/phút` : 'Hàng đợi trống'}</p>
            </div>
          </div>
          <div className="todo__risk" role="img" aria-label={`Rủi ro cao ${byRisk.Cao}, vừa ${byRisk.Vừa}, thấp ${byRisk.Thấp}`}>
            {RISKS.map((k) => (
              <i key={k} className={`risk-seg risk-seg--${k}`} style={{ flexGrow: byRisk[k] }} />
            ))}
          </div>
          <ul className="todo__legend">
            {RISKS.map((k) => (
              <li key={k}>
                <i className={`risk-seg risk-seg--${k}`} /> Rủi ro {k.toLowerCase()} <b>{byRisk[k]}</b>
              </li>
            ))}
          </ul>
          <button className="a-btn a-btn--primary" onClick={() => navigate('/admin/review')} disabled={!open.length}>
            Bắt đầu duyệt <kbd>g r</kbd>
          </button>
        </section>

        <section className="a-card pulse">
          <h2>Nhịp pipeline</h2>
          <dl>
            <div>
              <dt>Đã đọc review</dt>
              <dd>
                {observeRate === null ? '—' : `${observeRate}%`}
                <small>{obs ? `${obs.status.done ?? 0} / ${obs.places} địa điểm, ${obs.status.failed ?? 0} lỗi` : 'chưa chạy'}</small>
              </dd>
            </div>
            <div>
              <dt>Lỗi gần đây</dt>
              <dd className={errors.length ? 'is-warn' : ''}>
                {errors.length}
                <small>{errors[0] ? `mới nhất ${fmtAgo(errors[0].at)}` : 'không có'}</small>
              </dd>
            </div>
            <div>
              <dt>Snapshot</dt>
              <dd>
                {fmtAgo(snap.build.at)}
                <small>{snap.build.stale_files} file theo ontology cũ</small>
              </dd>
            </div>
          </dl>
          <button className="a-link" onClick={() => navigate('/admin/system')}>
            Xem hệ thống <Icon name="next" size={13} />
          </button>
        </section>
      </div>

      <TodayRow />

      <div className="tiles">
        <Tile n={exp.length} label="Địa điểm có bằng chứng" sub={`+ ${(snap.places.length - exp.length).toLocaleString('vi-VN')} chỉ có thông tin Google`} />
        <Tile n={byStatus.VERIFIED} label="Giá trị đã xác minh" sub={`${verifiedPct}% trên ${feats.length.toLocaleString('vi-VN')} giá trị`} />
        <Tile n={byStatus.OUTDATED} label="Giá trị quá hạn" sub="cần làm mới nguồn" tone={byStatus.OUTDATED ? 'warn' : undefined} />
        <Tile n={snap.system.videos} label="Clip TikTok đã thu" sub={`${snap.places.filter((p) => p.videos.length).length} địa điểm có clip`} />
      </div>

      <div className="a-grid2">
        <section className="a-card">
          <h2>Trạng thái các giá trị</h2>
          <div className="stack" role="img" aria-label="Phân bố trạng thái">
            {SHOWN.map((s) => (
              <i key={s} title={`${STATUS_LABEL[s]}: ${byStatus[s]}`} style={{ flexGrow: byStatus[s], background: STATUS_COLOR[s] }} />
            ))}
          </div>
          <ul className="legend">
            {SHOWN.map((s) => (
              <li key={s} title={s}>
                <i style={{ background: STATUS_COLOR[s] }} />
                {STATUS_LABEL[s]} <b>{byStatus[s]}</b>
              </li>
            ))}
          </ul>

          <h2 className="a-card__sub">Độ phủ theo khía cạnh</h2>
          <table className="a-table a-table--compact">
            <thead>
              <tr>
                <th>Khía cạnh</th>
                <th>Trên {exp.length} địa điểm</th>
                {COVER.map(([k, label]) => (
                  <th key={k} className="num">
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ASPECTS.map(([a, label]) => {
                const c = (k: string) => snap.build.coverage[`${a}=${k}`] ?? 0
                return (
                  <tr key={a}>
                    <td title={a}>{label}</td>
                    <td>
                      <div className="stack stack--thin">
                        {COVER.map(([k, l, color]) => (
                          <i key={k} title={`${l}: ${c(k)}`} style={{ flexGrow: c(k), background: color }} />
                        ))}
                      </div>
                    </td>
                    {COVER.map(([k]) => (
                      <td key={k} className="num">
                        {c(k)}
                      </td>
                    ))}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </section>

        <section className="a-card">
          <h2>Lỗi gần đây</h2>
          {errors.length ? (
            <ul className="errs">
              {errors.slice(0, 7).map((e, i) => (
                <li key={i}>
                  <time>{fmtAgo(e.at)}</time>
                  <span>
                    {e.source}/{e.stage}
                  </span>
                  <code title={e.error}>{e.error.split(':')[0]}</code>
                </li>
              ))}
            </ul>
          ) : (
            <p className="a-muted">Không có lỗi nào trong snapshot.</p>
          )}
          <h2 className="a-card__sub">Hôm nay</h2>
          <p className="a-muted">Phiên chuyến đi, kế hoạch hoàn thành và tỷ lệ khả thi sẽ hiện khi User Web ghi sự kiện. Bản thử chưa ghi sự kiện nào nên chưa có số.</p>
        </section>
      </div>
    </div>
  )
}

function Tile({ n, label, sub, tone }: { n: number; label: string; sub: string; tone?: 'warn' }) {
  return (
    <div className={`tile${tone ? ` tile--${tone}` : ''}`}>
      <span>{label}</span>
      <b>{n.toLocaleString('vi-VN')}</b>
      <small>{sub}</small>
    </div>
  )
}

// Users today (Asia/Ho_Chi_Minh day), from the private analytics server (docs/ANALYTICS.md).
function TodayRow() {
  const { data, error } = useAnalytics<Today>('today')
  if (!data) return <p className="a-muted">{error ? `Hôm nay: chưa đọc được số liệu người dùng (${error}).` : 'Hôm nay: đang tải…'}</p>
  return (
    <section aria-label="Hôm nay">
      <h2 className="a-small">Hôm nay · {data.day}</h2>
      <div className="tiles">
        <Tile n={data.new_users} label="Người dùng mới" sub={`${data.active_users} người có hoạt động`} />
        <Tile n={data.journeys} label="Hành trình tạo mới" sub={`${data.confirmed} lịch đã chốt`} />
        <Tile n={data.feedback} label="Phản hồi sau chuyến" sub="xem ở Phiên chuyến đi" />
        <Tile n={data.errors + data.fallbacks} label="Lỗi và fallback" sub={`${data.errors} lỗi · ${data.fallbacks} fallback`} tone={data.errors ? 'warn' : undefined} />
      </div>
    </section>
  )
}
