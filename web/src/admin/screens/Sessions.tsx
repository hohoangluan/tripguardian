import { useState } from 'react'
import { match, navigate, usePath } from '../../router'
import { fmtTime, useAnalytics, type SessionDetail, type SessionRow } from '../analytics'

// Journeys on the server (docs/ANALYTICS.md): find where people stop, replay one journey as a timeline. Admin reads
// everything, including what users typed; it is shown here only, never copied elsewhere.
const STAGE: Record<string, string> = { trip: 'Hiểu chuyến', decision: 'Chọn nơi', planning: 'Lịch trình' }
const FILTERS = [['', 'Tất cả'], ['abandoned', 'Bỏ dở'], ['low_feedback', 'Phản hồi thấp'], ['error', 'Có lỗi / fallback']] as const

export function Sessions() {
  const path = usePath()
  const m = match(path, '/admin/sessions/:id')
  return m ? <Detail id={m.id} /> : <List />
}

function List() {
  const [flag, setFlag] = useState<(typeof FILTERS)[number][0]>('')
  const [reached, setReached] = useState('')
  const { data, error } = useAnalytics<SessionRow[]>('sessions', { from: '2026-01-01', reached: reached || undefined, ...(flag ? { [flag]: '1' } : {}) })
  return (
    <div className="a-page">
      <header className="a-head"><div><h1>Phiên chuyến đi</h1><p>Hành trình trên máy chủ, mới nhất trước. Bấm một dòng để phát lại.</p></div></header>
      <div className="a-toolbar">
        <div className="seg" role="radiogroup" aria-label="Lọc">{FILTERS.map(([k, l]) => <button key={k} role="radio" aria-checked={flag === k} onClick={() => setFlag(k)}>{l}</button>)}</div>
        <select className="a-search" aria-label="Đã tới bước" value={reached} onChange={(e) => setReached(e.target.value)}><option value="">Mọi bước</option>{Object.entries(STAGE).map(([k, l]) => <option key={k} value={k}>Đã tới {l}</option>)}</select>
      </div>
      <section className="a-card">
        {!data ? <p className="a-muted">{error ? `Chưa đọc được (${error}). Chạy python -m analytics serve.` : 'Đang tải…'}</p> : data.length === 0 ? <p className="a-muted">Không có phiên nào khớp.</p> : (
          <table className="a-table">
            <thead><tr><th>Hành trình</th><th>Người dùng</th><th>Bước</th><th className="num">Revision</th><th>Bắt đầu bằng</th><th className="num">Lỗi</th><th className="num">Điểm thấp nhất</th><th>Cập nhật</th></tr></thead>
            <tbody>{data.map((s) => (
              <tr key={s.id} className="a-link" tabIndex={0} onClick={() => navigate(`/admin/sessions/${s.id}`)} onKeyDown={(e) => { if (e.key === 'Enter') navigate(`/admin/sessions/${s.id}`) }}>
                <td className="nowrap"><code>{s.id}</code></td>
                <td>{s.role === 'guest' ? 'Khách dùng thử' : s.email ?? <span className="a-muted">không gắn tài khoản</span>}</td>
                <td>{s.confirmed ? 'Đã chốt' : STAGE[s.stage] ?? s.stage}</td>
                <td className="num">{s.revision}</td>
                <td>{s.start_with ?? '—'}</td>
                <td className="num">{s.errors || '—'}</td>
                <td className="num">{s.min_score ?? '—'}</td>
                <td className="nowrap">{fmtTime(s.updated_at)}</td>
              </tr>
            ))}</tbody>
          </table>
        )}
      </section>
    </div>
  )
}

type Line = { at: string | null; kind: string; text: string; bad?: boolean }

function timeline(d: SessionDetail): Line[] {
  const lines: Line[] = [
    ...d.events.map((e) => ({ at: e.at, kind: e.source === 'client' ? 'web' : 'sự kiện', text: `${e.name} ${Object.entries(e.props).map(([k, v]) => `${k}=${v}`).join(' ')}`, bad: 'error' in e.props || e.props.path === 'fallback' })),
    ...d.decision_log.map((l) => ({ at: l.at ?? null, kind: 'Decision', text: JSON.stringify(l.action) })),
    ...d.planning_log.map((l) => ({ at: l.at ?? null, kind: 'Planning', text: JSON.stringify(l.action) })),
    ...d.feedback.map((f) => ({ at: f.at, kind: 'phản hồi', text: `${JSON.stringify(f.scores)} ${f.note}` })),
  ]
  return lines.sort((a, b) => (a.at ?? '9').localeCompare(b.at ?? '9'))
}

function Detail({ id }: { id: string }) {
  const { data, error } = useAnalytics<SessionDetail>(`sessions/${id}`)
  return (
    <div className="a-page">
      <header className="a-head"><div><h1>Hành trình <code>{id}</code></h1>{data && <p>{data.role === 'guest' ? 'Khách dùng thử' : data.email ?? 'không gắn tài khoản'} · {STAGE[data.stage] ?? data.stage} · revision {data.revision} · tạo {fmtTime(data.created_at)} · {data.app_version ?? 'chưa có phiên bản'}</p>}</div><button className="a-btn a-btn--ghost" onClick={() => navigate('/admin/sessions')}>Về danh sách</button></header>
      {!data ? <section className="a-card"><p className="a-muted">{error ?? 'Đang tải…'}</p></section> : (
        <div className="a-grid2">
          <section className="a-card">
            <h2>Dòng thời gian</h2>
            <p className="a-muted">Sự kiện, thao tác của module và phản hồi theo giờ. Dòng không có giờ (bản ghi cũ) nằm cuối.</p>
            <table className="a-table a-table--compact"><tbody>{timeline(data).map((l, i) => <tr key={i} className={l.bad ? 'a-note--bad' : ''}><td className="nowrap">{fmtTime(l.at)}</td><td className="nowrap">{l.kind}</td><td className="a-small">{l.text}</td></tr>)}</tbody></table>
          </section>
          <section className="a-card">
            <h2>Hội thoại Hiểu chuyến</h2>
            {data.trip_transcript.length === 0 ? <p className="a-muted">Không có.</p> : (
              <table className="a-table a-table--compact"><tbody>{data.trip_transcript.map((t, i) => <tr key={i}><td className="nowrap">lượt {t.turn}</td><td className="nowrap">{t.role === 'user' ? 'Người dùng' : t.role === 'agent' ? 'TripGuardian' : 'hệ thống'}</td><td className="a-small">{t.text}</td></tr>)}</tbody></table>
            )}
            <h2>Yêu cầu đã ghi ({data.receipts.length})</h2>
            <table className="a-table a-table--compact"><tbody>{data.receipts.map((r) => <tr key={r.request_id}><td className="nowrap">{fmtTime(r.at)}</td><td>{STAGE[r.stage] ?? r.stage}</td><td className="num">r{r.revision}</td><td className="a-small">{r.events.join(', ')}</td></tr>)}</tbody></table>
          </section>
        </div>
      )}
    </div>
  )
}
