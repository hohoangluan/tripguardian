import { useMemo, useState } from 'react'
import { featureLabel, STATUS_LABEL, valueLabel } from '../../data/labels'
import { mapsEmbed, placeById } from '../../data/store'
import type { Place, Snapshot, Status } from '../../data/types'
import { navigate } from '../../router'
import { GoogleMap, Icon } from '../../ui/bits'
import { decide, useDecisions, type Verdict } from '../decisions'
import { STATUS_COLOR, worstStatus } from '../model'

type Sort = 'name' | 'evidence' | 'updated'

export function Places({ snap, openId }: { snap: Snapshot; openId?: string }) {
  const [q, setQ] = useState('')
  const [status, setStatus] = useState<Status | 'ALL' | 'NONE'>('ALL')
  const [kind, setKind] = useState<'experience' | 'inventory' | 'all'>('experience')
  const [cat, setCat] = useState('all')
  const [sort, setSort] = useState<Sort>('evidence')
  const cats = useMemo(() => [...new Set(snap.places.map((p) => p.category).filter(Boolean))].sort() as string[], [snap])

  const rows = useMemo(() => {
    const f = q.trim().toLowerCase()
    return snap.places
      .filter((p) => kind === 'all' || p.kind === kind)
      .filter((p) => cat === 'all' || p.category === cat)
      .filter((p) => !f || p.name.toLowerCase().includes(f))
      .filter((p) => status === 'ALL' || (status === 'NONE' ? !p.features.length : worstStatus(p) === status))
      .sort((a, b) =>
        sort === 'name' ? a.name.localeCompare(b.name) : sort === 'updated' ? (b.asOf ?? '').localeCompare(a.asOf ?? '') : (b.voices ?? b.reviewCount ?? 0) - (a.voices ?? a.reviewCount ?? 0),
      )
      .slice(0, 300)
  }, [snap, q, status, kind, cat, sort])

  const open = openId ? placeById(openId) : undefined

  return (
    <div className={`a-page places${open ? ' has-detail' : ''}`}>
      <header className="a-head">
        <div>
          <h1>Places</h1>
          <p>{rows.length} địa điểm khớp bộ lọc. Trạng thái hiển thị là khía cạnh tệ nhất của nơi đó.</p>
        </div>
      </header>
      <div className="a-toolbar">
        <input className="a-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Tìm tên" aria-label="Tìm tên địa điểm" />
        <select value={kind} onChange={(e) => setKind(e.target.value as typeof kind)} aria-label="Nguồn">
          <option value="experience">Có bằng chứng trải nghiệm</option>
          <option value="inventory">Chỉ có thông tin Google</option>
          <option value="all">Tất cả</option>
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value as typeof status)} aria-label="Trạng thái">
          <option value="ALL">Mọi trạng thái</option>
          {(['NEEDS_REVIEW', 'UNCERTAIN', 'OUTDATED', 'VERIFIED'] as Status[]).map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
          <option value="NONE">Chưa có bằng chứng</option>
        </select>
        <select value={cat} onChange={(e) => setCat(e.target.value)} aria-label="Category">
          <option value="all">Mọi category</option>
          {cats.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
        <select value={sort} onChange={(e) => setSort(e.target.value as Sort)} aria-label="Sắp xếp">
          <option value="evidence">Nhiều bằng chứng trước</option>
          <option value="updated">Mới cập nhật</option>
          <option value="name">Theo tên</option>
        </select>
      </div>

      <div className="places__split">
        <table className="a-table">
          <thead>
            <tr>
              <th>Địa điểm</th>
              <th>Trạng thái</th>
              <th className="num">Bằng chứng</th>
              <th className="num">Giá trị</th>
              <th>Cập nhật</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const w = worstStatus(p)
              return (
                <tr key={p.id} className={open?.id === p.id ? 'is-on' : ''} onClick={() => navigate(`/admin/places/${encodeURIComponent(p.id)}`)} tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && navigate(`/admin/places/${encodeURIComponent(p.id)}`)}>
                  <td>
                    <b>{p.name}</b>
                    <small>{p.category}</small>
                  </td>
                  <td>{w ? <StatusPill s={w} /> : <span className="a-muted">Chưa có</span>}</td>
                  <td className="num">{p.voices ?? '—'}</td>
                  <td className="num">{p.features.length || '—'}</td>
                  <td className="nowrap">{p.asOf ?? '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {open && <PlacePanel p={open} />}
      </div>
    </div>
  )
}

export function StatusPill({ s }: { s: Status }) {
  return (
    <span className="pill" style={{ ['--c' as string]: STATUS_COLOR[s] }}>
      <i />
      {s}
    </span>
  )
}

function PlacePanel({ p }: { p: Place }) {
  const decisions = useDecisions()
  const [msg, setMsg] = useState<string | null>(null)
  const groups = useMemo(() => p.features.slice().sort((a, b) => b.n - a.n), [p])
  const act = (verdict: Verdict, label: string) => {
    decide([`place:${p.id}`], verdict, verdict === 'report' ? 'value' : undefined)
    setMsg(label)
  }
  const d = decisions[`place:${p.id}`]
  return (
    <aside className="pp">
      <button className="pp__close" aria-label="Đóng" onClick={() => navigate('/admin/places')}>
        <Icon name="x" />
      </button>
      <h2>{p.name}</h2>
      <p className="a-muted">
        {[p.category, p.address].filter(Boolean).join(', ')}
      </p>
      <dl className="parts parts--wide">
        <div>
          <dt>Identity</dt>
          <dd>
            {p.lat.toFixed(4)}, {p.lng.toFixed(4)}
          </dd>
        </div>
        <div>
          <dt>Operation</dt>
          <dd>{p.hours ? 'Có giờ mở cửa' : p.hoursText.length ? 'Giờ từ Google' : 'Chưa có giờ'}</dd>
        </div>
        {Object.entries(p.coverage ?? {}).map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd className={`cov cov--${v}`}>{v}</dd>
          </div>
        ))}
      </dl>
      <GoogleMap src={mapsEmbed(p, 15)} title={p.name} height={160} />
      <h3>Giá trị ({p.features.length})</h3>
      <table className="a-table a-table--compact">
        <thead>
          <tr>
            <th>Feature</th>
            <th>Giá trị</th>
            <th>Trạng thái</th>
            <th className="num">n</th>
            <th className="num">Đồng thuận</th>
            <th className="num">Độ mới</th>
          </tr>
        </thead>
        <tbody>
          {groups.map((f) => (
            <tr key={f.id}>
              <td>{featureLabel(f.id)}</td>
              <td>{valueLabel(f.value)}</td>
              <td>
                <StatusPill s={f.status} />
              </td>
              <td className="num">{f.n}</td>
              <td className="num">{Math.round(f.agreement * 100)}%</td>
              <td className="num">{f.freshnessDays ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <footer className="pp__actions">
        <button className="a-btn a-btn--ok" onClick={() => act('accept', 'Đã Accept toàn bộ giá trị đang hiển thị.')}>
          Accept
        </button>
        <button className="a-btn a-btn--bad" onClick={() => act('disable', 'Đã Disable địa điểm. Provenance cũ vẫn được giữ.')}>
          Disable
        </button>
        <button className="a-btn" onClick={() => act('report', 'Đã Report error. Hệ thống sẽ build lại từ bằng chứng.')}>
          Report error
        </button>
        <button className="a-btn a-btn--ghost" onClick={() => act('refresh', 'Đã gửi yêu cầu làm mới nguồn.')}>
          <Icon name="refresh" size={14} /> Request refresh
        </button>
      </footer>
      {(msg || d) && (
        <p className="a-note" role="status">
          {msg ?? `${d!.verdict} lúc ${new Date(d!.at).toLocaleString('vi-VN')}`} Lưu trong trình duyệt (bản thử).
        </p>
      )}
      <p className="a-muted">{STATUS_LABEL.VERIFIED}: giá trị được phục vụ cho người dùng; NEEDS_REVIEW và DISABLED thì không.</p>
    </aside>
  )
}
