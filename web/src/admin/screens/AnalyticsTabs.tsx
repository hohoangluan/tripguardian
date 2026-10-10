import { pct, useAnalytics, type Filters } from '../analytics'

// Tabs Trip, Lịch trình, Thực tế, Thông báo, Agent, Chất lượng (docs/ANALYTICS.md §Chỉ số). Each block says what it
// counts over; thresholds come only after a real baseline.
type Rec = Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any

function Load({ path, f, children }: { path: string; f: Filters; children: (d: Rec) => React.ReactNode }) {
  const { data, error } = useAnalytics<Rec>(path, f)
  if (!data) return <section className="a-card"><p className="a-muted">{error ? `Chưa đọc được (${error}).` : 'Đang tải…'}</p></section>
  return <>{children(data)}</>
}

const Tile = ({ label, n, sub, warn }: { label: string; n: React.ReactNode; sub?: string; warn?: boolean }) => (
  <div className={`tile${warn ? ' tile--warn' : ''}`}><span>{label}</span><b>{n ?? '—'}</b>{sub && <small>{sub}</small>}</div>
)

function Bars({ rows, label }: { rows: [string, number][]; label: string }) {
  const max = Math.max(1, ...rows.map((r) => r[1]))
  if (!rows.length) return <p className="a-muted">Chưa có.</p>
  return <div className="dist" aria-label={label}>{rows.map(([k, n]) => <div className="dist__row" key={k}><span>{k}</span><div className="dist__bar"><i style={{ width: `${(n / max) * 100}%` }} /></div><b className="num">{n}</b></div>)}</div>
}

const entries = (o: Record<string, number> | undefined) => Object.entries(o ?? {}).sort((a, b) => b[1] - a[1])

export const TripTab = ({ f }: { f: Filters }) => <Load path="trip" f={f}>{(d) => <>
  <div className="tiles">
    <Tile label="Lượt hỏi tới khi hiểu xong (trung vị)" n={d.turns_to_compile_median} sub={`${d.compiled} / ${d.journeys} hành trình hiểu xong`} />
    <Tile label="Gõ lại ở Chọn nơi (refine)" n={d.refined} />
    <Tile label="Quay lại" n={(d.backs['decision.back'] ?? 0) + (d.backs['planning.back'] ?? 0)} sub={`Chọn nơi ${d.backs['decision.back'] ?? 0} · Lịch trình ${d.backs['planning.back'] ?? 0}`} />
  </div>
  <div className="a-grid2">
    <section className="a-card"><h2>Chip so với gõ tự do</h2><Bars label="Kiểu lượt" rows={entries(d.kinds)} /></section>
    <section className="a-card"><h2>Đường trả lời</h2><p className="a-muted">agent, fallback hay heuristic.</p><Bars label="Đường" rows={entries(d.paths)} /></section>
    <section className="a-card"><h2>Bỏ qua / Chưa chắc theo câu hỏi</h2>{d.exits.length ? <table className="a-table a-table--compact"><tbody>{d.exits.map((e: Rec) => <tr key={e.qid + e.exit}><td>{e.qid}</td><td>{e.exit === 'skip' ? 'Bỏ qua' : 'Chưa chắc'}</td><td className="num">{e.n}</td></tr>)}</tbody></table> : <p className="a-muted">Chưa có.</p>}</section>
    <section className="a-card"><h2>Mong muốn chưa hiểu (unmapped)</h2>{d.unmapped.length ? <table className="a-table a-table--compact"><tbody>{d.unmapped.map((u: Rec) => <tr key={u.phrase}><td>{u.phrase}</td><td className="num">{u.journeys}</td></tr>)}</tbody></table> : <p className="a-muted">Chưa có.</p>}</section>
  </div>
</>}</Load>

export const PlanningTab = ({ f }: { f: Filters }) => <Load path="planning" f={f}>{(d) => <>
  <div className="tiles">
    <Tile label="Vào Lịch trình" n={d.entered} />
    <Tile label="Dùng gợi ý tự động" n={d.recommend_used} sub={d.entered ? pct(d.recommend_used / d.entered) : undefined} />
    <Tile label="Quay về Chọn nơi" n={d.back_to_decision} sub={d.entered ? pct(d.back_to_decision / d.entered) : undefined} />
    <Tile label="Phút từ vào tới chốt (trung vị)" n={d.advance_to_confirm_min == null ? null : Math.round(d.advance_to_confirm_min)} />
    <Tile label="Lỗi ở Lịch trình" n={d.errors} warn={d.errors > 0} />
  </div>
  <div className="a-grid2">
    <section className="a-card"><h2>Thao tác</h2><Bars label="Thao tác" rows={d.acts.map((r: Rec) => [r.action, r.n])} /></section>
    <section className="a-card"><h2>Phương án được chọn</h2><Bars label="Phương án" rows={d.variants.map((r: Rec) => [r.variant ?? '?', r.n])} /></section>
    <section className="a-card"><h2>Độ vững của lịch đã chốt</h2><Bars label="Độ vững" rows={d.robustness.map((r: Rec) => [r.level, r.n])} /></section>
  </div>
</>}</Load>

export const RealityTab = ({ f }: { f: Filters }) => <Load path="reality" f={f}>{(d) => <>
  <p className="a-muted">Trên {d.stops} điểm dừng của các chuyến đã bắt đầu. Độ phủ check-in {pct(d.coverage)}: điểm không check-in là chưa biết, không phải bị lỡ.</p>
  <div className="tiles">
    <Tile label="Check-in lại ở điểm sau" n={pct(d.next_checkin_rate)} sub={`trên ${d.next_checkin_n} điểm đã check-in`} />
    <Tile label="Tới muộn (trung vị / p90)" n={d.late_min.median == null ? null : `${d.late_min.median} / ${d.late_min.p90} ph`} sub={`${d.late_min.n} lượt`} />
    <Tile label="Khoảng giữa hai điểm so với lịch" n={d.gap_vs_plan_min.median == null ? null : `${d.gap_vs_plan_min.median} ph`} sub={`${d.gap_vs_plan_min.n} cặp`} />
    <Tile label="Check-in ngoài lịch" n={d.off_plan_checkins} />
    <Tile label="Thêm từ gợi ý" n={d.added_from_suggestions} sub={`${d.suggestions_opened} lượt mở gợi ý`} />
  </div>
  <div className="a-grid2">
    <section className="a-card"><h2>Trạng thái điểm dừng</h2><Bars label="Trạng thái" rows={[['Đã đến', d.status.arrived], ['Bỏ qua', d.status.skipped], ['Chưa biết', d.status.planned]]} /></section>
    <section className="a-card"><h2>Lý do bỏ qua</h2><Bars label="Lý do" rows={entries(d.skip_reasons)} /></section>
    <section className="a-card"><h2>Đánh giá tại chỗ</h2><Bars label="Đánh giá" rows={[['Hợp', d.ratings.up], ['Không hợp', d.ratings.down]]} /></section>
  </div>
</>}</Load>

export const NotifyTab = ({ f }: { f: Filters }) => <Load path="notifications" f={f}>{(d) => <>
  <div className="tiles">
    <Tile label="Đã gửi" n={d.sent} />
    <Tile label="Tắt hoặc tạm dừng / 1.000 gửi" n={d.off_or_pause_per_1000} sub="Chỉ số chặn: tăng là dừng thử nghiệm" warn={(d.off_or_pause_per_1000 ?? 0) > 0} />
    <Tile label="Cho phép thông báo" n={(d.permission.find((p: Rec) => p.result === 'granted')?.n) ?? 0} sub={d.permission.map((p: Rec) => `${p.result} ${p.n}`).join(' · ') || undefined} />
  </div>
  <section className="a-card"><h2>Theo loại và biến thể</h2><p className="a-muted">Có ích = mở rồi có thao tác trong 2 giờ.</p>
    {d.by_variant.length ? <table className="a-table a-table--compact"><thead><tr><th>Loại</th><th>Biến thể</th><th className="num">Gửi</th><th className="num">Mở</th><th className="num">Có ích</th></tr></thead><tbody>{d.by_variant.map((r: Rec) => <tr key={r.kind + r.variant}><td>{r.kind}</td><td>{r.variant}</td><td className="num">{r.sent}</td><td className="num">{pct(r.opened / r.sent)}</td><td className="num">{pct(r.useful / r.sent)}</td></tr>)}</tbody></table> : <p className="a-muted">Chưa gửi thông báo nào.</p>}
  </section>
  <section className="a-card"><h2>Bị bỏ không gửi</h2><Bars label="Lý do" rows={d.skipped.map((r: Rec) => [`${r.kind} · ${r.skip_reason}`, r.n])} /></section>
</>}</Load>

export const AgentTab = ({ f }: { f: Filters }) => <Load path="agent" f={f}>{(d) => (<>
  <section className="a-card"><h2>Yêu cầu dùng model</h2><p className="a-muted">Số liệu theo từng lời gọi của từng vai trò chưa được ghi; đây là các yêu cầu hành trình có dùng model.</p>
    <table className="a-table"><thead><tr><th>Yêu cầu</th><th className="num">Số lượt</th><th className="num">p50</th><th className="num">p95</th><th className="num">Tới event đầu (p50)</th><th className="num">Fallback</th><th>Lỗi</th></tr></thead>
      <tbody>{d.requests.map((r: Rec) => <tr key={r.name}><td>{r.name}</td><td className="num">{r.n}</td><td className="num">{r.p50_ms ?? '—'} ms</td><td className="num">{r.p95_ms ?? '—'} ms</td><td className="num">{r.first_event_p50_ms ?? '—'} ms</td><td className="num">{pct(r.fallback_rate)}</td><td className="a-small">{Object.entries(r.errors).map(([k, n]) => `${k} ${n}`).join(', ') || '—'}</td></tr>)}</tbody></table>
  </section>
  {d.decision_fallback && <section className="a-card"><h2>Chat ở bước Lựa chọn: agent_fallback</h2><p className="a-muted">Đọc từ log phiên Decision: {d.decision_fallback.asked_agent} lượt gõ có hỏi agent, {d.decision_fallback.fallback} lượt rơi về bộ khớp từ khóa ({pct(d.decision_fallback.rate)}).</p><Bars label="Lý do" rows={entries(d.decision_fallback.reasons)} /></section>}
</>)}</Load>

export const QualityTab = ({ f }: { f: Filters }) => <Load path="quality" f={f}>{(d) => (
  <div className="tiles">
    <Tile label="Vi phạm hard constraint" n={d.hard_fail} sub={d.alarm ? 'Phải bằng 0: kiểm tra ngay' : 'Bằng 0'} warn={d.alarm} />
    <Tile label="Kiểm tra chưa rõ (unknown)" n={pct(d.hard_unknown_rate)} sub="trên các nơi trong lịch đã chốt" />
    <Tile label="Lịch xem trước xếp được" n={pct(d.feasible_rate)} />
    <Tile label="Phút tới lịch được chấp nhận (trung vị)" n={d.time_to_plan_min == null ? null : Math.round(d.time_to_plan_min)} sub={`${d.confirmed} lịch đã chốt`} />
    <Tile label="Phải tìm ở ngoài (proxy)" n={d.away.outbound + d.away.hidden} sub={`bấm ra ngoài ${d.away.outbound} · rời tab ở Chọn nơi ${d.away.hidden}`} />
  </div>
)}</Load>
