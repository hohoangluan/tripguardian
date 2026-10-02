import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { featureLabel, valueLabel } from '../../data/labels'
import { Icon } from '../../ui/bits'
import { labelStats, nextLabels, sendLabel, type Label, type LabelItem, type LabelStats } from '../api'

const CONTEXT_VI: Record<string, string> = { time_of_day: 'Buổi', day_type: 'Ngày', weather: 'Thời tiết' }
const BATCH = 4

// Splits the review text around the quote the Extractor claimed, so the reviewer sees what it was based on.
function marked(text: string, quote: string) {
  const i = text.toLowerCase().indexOf(quote.toLowerCase())
  if (i < 0) return <>{text}</>
  return (
    <>
      {text.slice(0, i)}
      <mark>{text.slice(i, i + quote.length)}</mark>
      {text.slice(i + quote.length)}
    </>
  )
}

export function Labels() {
  const [feature, setFeature] = useState('')
  const [queue, setQueue] = useState<LabelItem[]>([])
  const [stats, setStats] = useState<LabelStats | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  const [session, setSession] = useState(0)
  const [started] = useState(() => Date.now())
  const seen = useRef(new Set<string>())

  const refill = useCallback(
    async (reset: boolean) => {
      try {
        const got = await nextLabels(BATCH, feature || undefined)
        setError(null)
        setQueue((q) => {
          const base = reset ? [] : q
          const have = new Set(base.map((i) => i.id))
          return [...base, ...got.filter((i) => !have.has(i.id) && !seen.current.has(i.id))]
        })
      } catch (e) {
        setError(String(e instanceof Error ? e.message : e))
      }
    },
    [feature],
  )
  const reloadStats = useCallback(() => labelStats().then(setStats, () => undefined), [])

  useEffect(() => {
    refill(true)
  }, [refill])
  useEffect(() => {
    reloadStats()
  }, [reloadStats])
  useEffect(() => {
    if (!error && queue.length > 0 && queue.length < 2) refill(false)
  }, [queue.length, error, refill])

  const cur = queue[0]
  const answer = useCallback(
    async (label: Label) => {
      if (!cur || busy) return
      setBusy(true)
      try {
        await sendLabel(cur.id, label, note)
        seen.current.add(cur.id)
        setQueue((q) => q.slice(1))
        setNote('')
        setSession((n) => n + 1)
        reloadStats()
      } catch (e) {
        setError(String(e instanceof Error ? e.message : e))
      } finally {
        setBusy(false)
      }
    },
    [cur, busy, note, reloadStats],
  )
  const skip = useCallback(() => {
    if (!cur) return
    seen.current.add(cur.id)
    setQueue((q) => q.slice(1))
  }, [cur])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).closest('input, textarea, select') || e.metaKey || e.ctrlKey) return
      if (e.key === 'c') answer('correct')
      else if (e.key === 'w') answer('wrong')
      else if (e.key === 'u') answer('unsure')
      else if (e.key === 's') skip()
      else return
      e.preventDefault()
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [answer, skip])

  const features = useMemo(() => [...new Set(stats?.rows.map((r) => r.feature) ?? [])].sort(), [stats])
  const rows = useMemo(
    () => (stats?.rows ?? []).filter((r) => !feature || r.feature === feature).sort((a, b) => Number(a.gate) - Number(b.gate) || b.observations - a.observations),
    [stats, feature],
  )
  const passed = stats?.rows.filter((r) => r.gate).length ?? 0
  const minutes = Math.max(1, (Date.now() - started) / 60000)

  return (
    <div className="a-page lb">
      <header className="a-head">
        <div>
          <h1>Gán nhãn bằng chứng</h1>
          <p>
            Đọc review, so với điều Extractor đã trích. Nhãn đúng/sai cho ra độ chính xác theo từng giá trị; giá trị chưa đạt ngưỡng ({stats ? `${stats.gate.min_n} nhãn, cận dưới ${Math.round(stats.gate.lower * 100)}%` : '…'}) không được tự phục vụ.
          </p>
        </div>
        <div className="a-filters">
          <select value={feature} onChange={(e) => (setFeature(e.target.value), setQueue([]))} aria-label="Feature">
            <option value="">Mọi feature (ưu tiên giá trị ít nhãn)</option>
            {features.map((f) => (
              <option key={f} value={f}>
                {featureLabel(f)}
              </option>
            ))}
          </select>
        </div>
      </header>

      {error && (
        <p className="a-note a-note--bad" role="alert">
          <Icon name="info" size={14} /> Không nối được backend ({error}). Chạy <code>python -m corpus review</code> rồi tải lại trang.
        </p>
      )}

      <div className="lb__split">
        <div className="a-card lb__card">
          {cur ? (
            <>
              <p className="lb__claim">
                <span className="rq__kindtag">{featureLabel(cur.feature)}</span>
                <b>{valueLabel(cur.value)}</b>
                <small>
                  {cur.placeName ?? cur.place}
                  {cur.observedAt ? `, ${cur.observedAt}` : ''}
                </small>
              </p>
              <blockquote className="lb__text">{cur.text ? marked(cur.text, cur.quote) : <span className="a-muted">Không tìm thấy review gốc.</span>}</blockquote>
              <p className="lb__quote">
                <Icon name="quote" size={14} /> Trích dẫn: <b>{cur.quote}</b>
              </p>
              {Object.entries(cur.context).some(([, v]) => v !== 'unknown') && (
                <p className="a-muted">
                  Bối cảnh Extractor đọc ra:{' '}
                  {Object.entries(cur.context)
                    .filter(([, v]) => v !== 'unknown')
                    .map(([k, v]) => `${CONTEXT_VI[k] ?? k}: ${v}`)
                    .join(', ')}
                </p>
              )}
              <p className="lb__ask">
                Review có nói <b>{featureLabel(cur.feature)} = {valueLabel(cur.value)}</b> về chính địa điểm này không?
              </p>
              <input className="lb__note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Ghi chú (tuỳ chọn): vì sao sai" aria-label="Ghi chú" />
              <footer className="rq__actions">
                <button className="a-btn a-btn--ok a-btn--big" disabled={busy} onClick={() => answer('correct')}>
                  <Icon name="check" size={16} /> Đúng <kbd>c</kbd>
                </button>
                <button className="a-btn a-btn--bad a-btn--big" disabled={busy} onClick={() => answer('wrong')}>
                  <Icon name="x" size={16} /> Sai <kbd>w</kbd>
                </button>
                <button className="a-btn a-btn--big" disabled={busy} onClick={() => answer('unsure')}>
                  Không chắc <kbd>u</kbd>
                </button>
                <button className="a-btn a-btn--ghost" onClick={skip}>
                  Bỏ qua <kbd>s</kbd>
                </button>
              </footer>
            </>
          ) : (
            <p className="a-empty">{error ? 'Chưa có dữ liệu.' : queue.length === 0 && stats ? 'Hết mục để gán nhãn cho bộ lọc này.' : 'Đang tải'}</p>
          )}
          <p className="lb__session">
            Phiên này <b>{session}</b> nhãn · <b>{(session / minutes).toFixed(1)}</b>/phút
            {stats && (
              <>
                {' '}
                · tổng <b>{stats.labelled}</b> nhãn / {stats.total.toLocaleString('vi-VN')} bằng chứng
              </>
            )}
          </p>
        </div>

        <div className="a-card lb__stats">
          <h2>
            Độ chính xác đo được <small>{passed} giá trị đạt ngưỡng</small>
          </h2>
          <div className="lb__scroll">
            <table className="a-table">
              <thead>
                <tr>
                  <th>Feature</th>
                  <th>Giá trị</th>
                  <th>Đúng</th>
                  <th>Sai</th>
                  <th>Chính xác</th>
                  <th>Trạng thái</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={`${r.feature}/${r.value}`}>
                    <td>{featureLabel(r.feature)}</td>
                    <td>{valueLabel(r.value)}</td>
                    <td>{r.correct}</td>
                    <td>{r.wrong}</td>
                    <td>{r.precision === null ? '—' : `${Math.round(r.precision * 100)}% (≥ ${Math.round(r.lower * 100)}%)`}</td>
                    <td>
                      <span className={`lb__gate${r.gate ? ' is-ok' : ''}`}>{r.gate ? 'Đạt' : r.needed > 0 ? `Cần thêm ${r.needed} nhãn` : 'Chưa đạt'}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}
