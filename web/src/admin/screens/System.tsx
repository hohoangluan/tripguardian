import type { Snapshot } from '../../data/types'
import { Icon } from '../../ui/bits'
import { fmtAgo } from '../model'

type Health = 'Healthy' | 'Warning' | 'Unavailable'

export function System({ snap }: { snap: Snapshot }) {
  const obs = snap.system.observe
  const errs = snap.system.errors
  const recent = (source: string, stage?: string) => errs.filter((e) => e.source === source && (!stage || e.stage === stage) && e.at && Date.now() - new Date(e.at).getTime() < 6 * 3600e3).length
  const llmErr = errs.filter((e) => /APIConnectionError|BadAnswer|RateLimit/i.test(e.error) && e.at && Date.now() - new Date(e.at).getTime() < 6 * 3600e3).length

  const parts: { name: string; health: Health; detail: string }[] = [
    {
      name: 'Corpus build',
      health: snap.build.stale_files > 0 ? 'Warning' : 'Healthy',
      detail: `${snap.build.places} địa điểm, ${fmtAgo(snap.build.at)}. ${snap.build.stale_files} file observation theo ontology cũ chưa được đọc lại.`,
    },
    { name: 'Discovery (Google)', health: recent('gmaps') > 10 ? 'Warning' : 'Healthy', detail: `${snap.system.gmapsPlaces} địa điểm đã thu. ${recent('gmaps')} lỗi trong 6 giờ.` },
    {
      name: 'Evidence pipeline',
      health: obs && (obs.status.failed ?? 0) > (obs.status.done ?? 0) ? 'Warning' : 'Healthy',
      detail: obs ? `Đọc review: ${obs.status.done ?? 0} xong, ${obs.status.failed ?? 0} lỗi trên ${obs.places} địa điểm.` : 'Chưa chạy.',
    },
    { name: 'TikTok', health: recent('tiktok') > 10 ? 'Warning' : 'Healthy', detail: `${snap.system.videos} clip. ${recent('tiktok')} lỗi trong 6 giờ.` },
    { name: 'Resolution', health: 'Unavailable', detail: 'Chưa có số liệu trong snapshot.' },
    { name: 'Recommendation, Feasibility, Routing', health: 'Healthy', detail: 'Bản thử chạy trên trình duyệt người dùng, thời gian di chuyển là ước tính đường chim bay.' },
    { name: 'LLM', health: llmErr ? 'Warning' : 'Healthy', detail: `${llmErr} lỗi gọi model trong 6 giờ.` },
  ]

  return (
    <div className="a-page">
      <header className="a-head">
        <div>
          <h1>System Monitor</h1>
          <p>Trạng thái từ snapshot lúc {new Date(snap.build.at).toLocaleString('vi-VN')}.</p>
        </div>
      </header>
      <div className="health">
        {parts.map((p) => (
          <section key={p.name} className={`health__item health--${p.health}`}>
            <span className="health__state">
              <Icon name={p.health === 'Healthy' ? 'check' : p.health === 'Warning' ? 'alert' : 'x'} size={14} /> {p.health}
            </span>
            <h2>{p.name}</h2>
            <p>{p.detail}</p>
          </section>
        ))}
      </div>
      <section className="a-card">
        <h2>Lỗi gần đây</h2>
        <table className="a-table a-table--compact">
          <thead>
            <tr>
              <th>Thời gian</th>
              <th>Nguồn</th>
              <th>Bước</th>
              <th>Liên quan</th>
              <th>Lỗi</th>
            </tr>
          </thead>
          <tbody>
            {errs.map((e, i) => (
              <tr key={i}>
                <td>{e.at ? new Date(e.at).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' }) : '—'}</td>
                <td>{e.source}</td>
                <td>{e.stage ?? '—'}</td>
                <td className="a-small">{e.ref ?? '—'}</td>
                <td className="a-small">{e.error}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}
