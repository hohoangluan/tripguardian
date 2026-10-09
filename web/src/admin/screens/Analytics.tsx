import { useState } from 'react'
import { pct, useAnalytics, type DecisionNums, type Filters, type Funnel } from '../analytics'
import { AgentTab, NotifyTab, PlanningTab, QualityTab, RealityTab, TripTab } from './AnalyticsTabs'

// docs/ANALYTICS.md: numbers from the events table (read-only role). Thresholds only after a real baseline (§3.7).
const TABS = [['funnel', 'Phễu'], ['trip', 'Trip'], ['decision', 'Quyết định'], ['planning', 'Lịch trình'], ['reality', 'Thực tế'], ['notify', 'Thông báo'], ['agent', 'Agent'], ['quality', 'Chất lượng']] as const
const START: [string, string][] = [['', 'Mọi cách bắt đầu'], ['nothing', 'Chưa có ý tưởng'], ['saved', 'Nơi đã lưu'], ['must', 'Nơi bắt buộc'], ['itinerary', 'Lịch có sẵn']]
const ACTION: Record<string, string> = { select: 'Chọn', drop: 'Bỏ', lock: 'Khóa', unlock: 'Mở khóa', swap: 'Thay', relax: 'Nới điều kiện', wishlist: 'Để dành', answer: 'Trả lời gợi ý' }
const REASON: Record<string, string> = { far: 'Xa', crowded: 'Đông', pricey: 'Đắt', visited: 'Đã đến', 'không nói': 'Không nói lý do' }
const PREVIEW: Record<string, string> = { ready: 'Sẵn sàng', failed: 'Không xếp được', blocked: 'Bị chặn', empty: 'Chưa chọn nơi' }

export function Analytics() {
  const [tab, setTab] = useState<(typeof TABS)[number][0]>('funnel')
  const [f, setF] = useState<Filters>({})
  const versions = useAnalytics<string[]>('versions')
  const set = (k: keyof Filters, v: string) => setF((x) => ({ ...x, [k]: v || undefined }))
  return (
    <div className="a-page">
      <header className="a-head">
        <div>
          <h1>Phân tích</h1>
          <p>Số thật từ sự kiện trên máy chủ. Hành trình nhập từ file cũ chỉ có các mốc suy ra từ trạng thái đã lưu.</p>
        </div>
      </header>
      <div className="a-toolbar">
        <div className="seg" role="radiogroup" aria-label="Bảng">{TABS.map(([k, l]) => <button key={k} role="radio" aria-checked={tab === k} onClick={() => setTab(k)}>{l}</button>)}</div>
        <div className="a-filters">
          <label className="a-small">Từ <input type="date" className="a-search" value={f.from ?? ''} onChange={(e) => set('from', e.target.value)} /></label>
          <label className="a-small">Đến <input type="date" className="a-search" value={f.to ?? ''} onChange={(e) => set('to', e.target.value)} /></label>
          <select className="a-search" aria-label="Cách bắt đầu" value={f.start_with ?? ''} onChange={(e) => set('start_with', e.target.value)}>{START.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
          <select className="a-search" aria-label="Phiên bản" value={f.app_version ?? ''} onChange={(e) => set('app_version', e.target.value)}><option value="">Mọi phiên bản</option>{(versions.data ?? []).map((v) => <option key={v} value={v}>{v}</option>)}</select>
        </div>
      </div>
      {tab === 'funnel' ? <FunnelTab f={f} versions={versions.data ?? []} /> : tab === 'decision' ? <DecisionTab f={f} /> : tab === 'trip' ? <TripTab f={f} /> : tab === 'planning' ? <PlanningTab f={f} /> : tab === 'reality' ? <RealityTab f={f} /> : tab === 'notify' ? <NotifyTab f={f} /> : tab === 'agent' ? <AgentTab f={f} /> : <QualityTab f={f} />}
    </div>
  )
}

function Problem({ error }: { error?: string }) {
  return <section className="a-card"><p className="a-muted">{error ? `Chưa đọc được số liệu (${error}). Chạy python -m analytics serve (./run.sh start).` : 'Đang tải…'}</p></section>
}

function FunnelTab({ f, versions }: { f: Filters; versions: string[] }) {
  const { data, error } = useAnalytics<Funnel>('funnel', f)
  const [vb, setVb] = useState('')
  const b = useAnalytics<Funnel>('funnel', { ...f, app_version: vb || undefined })
  if (!data) return <Problem error={error} />
  const other = vb && b.data ? new Map(b.data.steps.map((s) => [s.key, s])) : null
  const top = data.steps[0]?.journeys || 1
  return (
    <>
      <div className="tiles">
        <div className="tile"><span>Lượt vào landing</span><b>{data.top.landing}</b></div>
        <div className="tile"><span>Bấm CTA</span><b>{data.top.cta}</b></div>
        <div className="tile"><span>Người đăng nhập</span><b>{data.top.logins}</b></div>
        <div className="tile"><span>Hành trình tạo mới</span><b>{data.steps[0]?.journeys ?? 0}</b></div>
      </div>
      <section className="a-card">
        <h2>Phễu hành trình</h2>
        <p className="a-muted">Mỗi bước đếm số hành trình đã tới bước đó. “Giữ lại” so với bước trước có số liệu; “Dừng ở đây” là hành trình không tới bước nào sau.</p>
        <label className="a-small">So với phiên bản <select className="a-search" value={vb} onChange={(e) => setVb(e.target.value)}><option value="">không so sánh</option>{versions.map((v) => <option key={v} value={v}>{v}</option>)}</select></label>
        <table className="a-table">
          <thead><tr><th>Bước</th><th className="num">Hành trình</th><th>Tỉ lệ so với tạo mới</th><th className="num">Giữ lại</th>{other && <th className="num">Giữ lại ({vb})</th>}<th className="num">Phút từ lúc tạo (trung vị)</th><th className="num">Dừng ở đây</th><th>Thao tác cuối trước khi dừng</th></tr></thead>
          <tbody>
            {data.steps.map((s) => (
              <tr key={s.key}>
                <td>{s.label}</td>
                <td className="num">{s.journeys}</td>
                <td><div className="dist__bar" role="img" aria-label={pct(s.journeys / top)}><i style={{ width: `${(s.journeys / top) * 100}%` }} /></div></td>
                <td className="num">{pct(s.kept)}</td>{other && <td className="num">{pct(other.get(s.key)?.kept ?? null)} <span className="a-muted">({other.get(s.key)?.journeys ?? 0})</span></td>}
                <td className="num">{s.median_min ?? '—'}</td>
                <td className="num">{s.stopped || '—'}</td>
                <td className="a-small">{s.last_before_stop.map(([n, k]) => `${n} (${k})`).join(', ') || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  )
}

function Bars({ rows, label }: { rows: { name: string; n: number }[]; label: string }) {
  const max = Math.max(1, ...rows.map((r) => r.n))
  if (!rows.length) return <p className="a-muted">Chưa có.</p>
  return <div className="dist" aria-label={label}>{rows.map((r) => <div className="dist__row" key={r.name}><span>{r.name}</span><div className="dist__bar"><i style={{ width: `${(r.n / max) * 100}%` }} /></div><b className="num">{r.n}</b></div>)}</div>
}

function DecisionTab({ f }: { f: Filters }) {
  const { data, error } = useAnalytics<DecisionNums>('decision', f)
  if (!data) return <Problem error={error} />
  return (
    <>
      <div className="tiles">
        <div className="tile"><span>Trang “Xem thêm”</span><b>{data.counts.page_more}</b></div>
        <div className="tile"><span>Hỏi “Sao không có…”</span><b>{data.counts.why_not}</b></div>
        <div className="tile"><span>Mở so sánh</span><b>{data.counts.compare_open}</b></div>
        <div className="tile"><span>Bấm ra ngoài (Maps, TikTok)</span><b>{data.counts.outbound_click}</b><small>Proxy cho việc phải tìm thêm ở chỗ khác</small></div>
        <div className="tile"><span>Thao tác mỗi hành trình (trung vị)</span><b>{data.acts_per_journey_median ?? '—'}</b></div>
      </div>
      <div className="a-grid2">
        <section className="a-card"><h2>Thao tác ở Chọn nơi</h2><Bars label="Thao tác" rows={data.acts.map((r) => ({ name: ACTION[r.action] ?? r.action, n: r.n }))} /></section>
        <section className="a-card"><h2>Lý do bỏ</h2><Bars label="Lý do bỏ" rows={data.drop_reasons.map((r) => ({ name: REASON[r.reason] ?? r.reason, n: r.n }))} /></section>
        <section className="a-card"><h2>Lịch xem trước</h2><Bars label="Trạng thái lịch xem trước" rows={data.previews.map((r) => ({ name: PREVIEW[r.status] ?? r.status, n: r.n }))} /></section>
        <section className="a-card"><h2>Từ khóa tìm không thấy</h2><p className="a-muted">Gợi ý cho danh sách crawl.</p>
          {data.search_misses.length ? <table className="a-table a-table--compact"><tbody>{data.search_misses.map((m) => <tr key={m.q}><td>{m.q}</td><td className="num">{m.n}</td></tr>)}</tbody></table> : <p className="a-muted">Chưa có.</p>}
        </section>
        <section className="a-card"><h2>Tỉ lệ chọn theo vị trí xếp hạng</h2><p className="a-muted">Mẫu số là lượt thẻ hiện ra; thẻ hiện mà không bấm không có nghĩa là không thích.</p>
          {data.ranks.length ? <table className="a-table a-table--compact"><thead><tr><th>Vị trí</th><th className="num">Hiện</th><th className="num">Được chọn</th><th className="num">Tỉ lệ</th></tr></thead><tbody>{data.ranks.map((r) => <tr key={r.rank}><td>{r.rank}</td><td className="num">{r.shown}</td><td className="num">{r.chosen}</td><td className="num">{pct(r.chosen / Math.max(1, r.shown))}</td></tr>)}</tbody></table> : <p className="a-muted">Chưa có lượt hiện thẻ nào.</p>}
        </section>
      </div>
    </>
  )
}
