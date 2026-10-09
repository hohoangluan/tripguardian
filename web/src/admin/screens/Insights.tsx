import { navigate } from '../../router'
import { useAnalytics } from '../analytics'

// Insights (docs/ANALYTICS.md §Insights): each item points at the work it suggests. Nothing here writes the corpus.
type Insight = { kind: string; title: string; action: string; items: { label: string; n: number; of?: number }[] }
type Cluster = { week: string; source: string; label: string; size: number; examples: string[] }
const GO: Record<string, string> = { dropped_often: '/admin/review', errors: '/admin/sessions' }

export function Insights() {
  const { data, error } = useAnalytics<Insight[]>('insights', { from: '2026-01-01' })
  const clusters = useAnalytics<Cluster[]>('clusters')
  return (
    <div className="a-page">
      <header className="a-head"><div><h1>Insights</h1><p>Gợi ý việc cần làm từ số liệu. Chỉ đề xuất; người quyết định.</p></div></header>
      {!data ? <section className="a-card"><p className="a-muted">{error ?? 'Đang tải…'}</p></section> : data.length === 0 ? <section className="a-card"><p className="a-muted">Chưa có gì nổi bật.</p></section> : (
        <div className="a-grid2">{data.map((i) => (
          <section className="a-card" key={i.kind}>
            <h2>{i.title}</h2>
            <table className="a-table a-table--compact"><tbody>{i.items.map((x) => <tr key={x.label}><td>{i.kind === 'errors' ? <button className="a-link" onClick={() => navigate(`/admin/sessions/${x.label}`)}>{x.label}</button> : x.label}</td><td className="num">{x.n}{x.of ? ` / ${x.of}` : ''}</td></tr>)}</tbody></table>
            {GO[i.kind] ? <button className="a-btn a-btn--ghost" onClick={() => navigate(GO[i.kind])}>{i.action}</button>
              : <button className="a-btn a-btn--ghost" onClick={() => void navigator.clipboard?.writeText(i.items.map((x) => x.label).join('\n'))}>{i.action} (sao chép danh sách)</button>}
          </section>
        ))}</div>
      )}
      <section className="a-card"><h2>Nhóm ý người dùng viết (tuần này)</h2><p className="a-muted">Từ phản hồi sau chuyến và lời gõ tự do; nhóm bởi vai trò Extractor mỗi tuần (python -m analytics cluster).</p>
        {!clusters.data?.length ? <p className="a-muted">Chưa có nhóm nào.</p> : <table className="a-table a-table--compact"><tbody>{clusters.data.map((c) => <tr key={c.source + c.label}><td>{c.source === 'feedback' ? 'Phản hồi' : 'Gõ tự do'}</td><td><b>{c.label}</b><br /><span className="a-small a-muted">{c.examples.slice(0, 2).join(' · ')}</span></td><td className="num">{c.size}</td></tr>)}</tbody></table>}
      </section>
    </div>
  )
}
