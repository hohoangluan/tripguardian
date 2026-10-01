import gsap from 'gsap'
import { useEffect, useMemo, useRef, useState } from 'react'
import { valueLabel } from '../../data/labels'
import type { ReviewItem, Snapshot } from '../../data/types'
import { Icon, TikTokEmbed } from '../../ui/bits'
import { decide, REPORT_LABEL, undo, useDecisions, VERDICT_LABEL, type ReportKind, type Verdict } from '../decisions'
import { itemTitle, KIND_LABEL, riskOf, signalOf, whyOf, type Risk } from '../model'

const REPORTS = Object.keys(REPORT_LABEL) as ReportKind[]
const RISK_RANK: Record<Risk, number> = { Cao: 0, Vừa: 1, Thấp: 2 }

export function Review({ snap }: { snap: Snapshot }) {
  const decisions = useDecisions()
  const [show, setShow] = useState<'open' | 'done'>('open')
  const [kind, setKind] = useState<ReviewItem['kind'] | 'all'>('all')
  const [cursor, setCursor] = useState(0)
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [reporting, setReporting] = useState(false)
  const [started] = useState(() => Date.now())
  const [doneHere, setDoneHere] = useState(0)
  const card = useRef<HTMLDivElement>(null)

  const items = useMemo(
    () =>
      snap.review
        .filter((r) => (show === 'open' ? !decisions[r.id] : !!decisions[r.id]))
        .filter((r) => kind === 'all' || r.kind === kind)
        .sort((a, b) => RISK_RANK[riskOf(a)] - RISK_RANK[riskOf(b)] || a.placeId.localeCompare(b.placeId)),
    [snap, decisions, show, kind],
  )
  const cur = items[Math.min(cursor, items.length - 1)]
  const total = snap.review.length
  const handled = snap.review.filter((r) => decisions[r.id]).length
  const minutes = Math.max(1, (Date.now() - started) / 60000)

  const act = (verdict: Verdict, report?: ReportKind, ids = cur ? [cur.id] : []) => {
    if (!ids.length) return
    const commit = () => {
      decide(ids, verdict, report)
      setDoneHere((n) => n + ids.length)
      setPicked(new Set())
      setReporting(false)
      if (card.current) gsap.set(card.current, { clearProps: 'all' })
    }
    if (!card.current || ids.length > 1 || matchMedia('(prefers-reduced-motion: reduce)').matches) return commit()
    // Accepted cards tip away to the right, disabled ones drop, reports lift off.
    const to = verdict === 'accept' ? { x: 120, rotateY: 25 } : verdict === 'disable' ? { y: 60, rotateX: -18 } : { y: -50, rotateX: 14 }
    gsap.to(card.current, { ...to, opacity: 0, duration: 0.22, ease: 'power2.in', onComplete: commit })
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).closest('input, textarea, select') || e.metaKey || e.ctrlKey) return
      if (reporting && /^[1-5]$/.test(e.key)) return act('report', REPORTS[Number(e.key) - 1])
      if (e.key === 'j') setCursor((c) => Math.min(items.length - 1, c + 1))
      else if (e.key === 'k') setCursor((c) => Math.max(0, c - 1))
      else if (e.key === 'A' && e.shiftKey && picked.size) act('accept', undefined, [...picked])
      else if (e.key === 'a' && show === 'open') act('accept')
      else if (e.key === 'd' && show === 'open') act('disable')
      else if (e.key === 'r' && show === 'open') setReporting((r) => !r)
      else if (e.key === 'u' && cur && decisions[cur.id]) undo(cur.id)
      else if (e.key === 'x' && cur)
        setPicked((s) => {
          const n = new Set(s)
          if (n.has(cur.id)) n.delete(cur.id)
          else n.add(cur.id)
          return n
        })
      else return
      e.preventDefault()
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  })

  useEffect(() => {
    document.querySelector('.rq__row.is-cur')?.scrollIntoView({ block: 'nearest' })
  }, [cursor, items.length])

  // Bulk accept is offered only for low-risk items of one kind.
  const bulkKind = cur && riskOf(cur) === 'Thấp' ? cur.kind : null
  const sameLow = bulkKind ? items.filter((r) => r.kind === bulkKind && riskOf(r) === 'Thấp').map((r) => r.id) : []

  return (
    <div className="a-page rq">
      <header className="a-head">
        <div>
          <h1>Review Queue</h1>
          <p>
            {handled} / {total} mục đã xử lý. Phiên này: {doneHere} mục, {(doneHere / minutes).toFixed(1)} mục/phút (mục tiêu 5).
          </p>
        </div>
        <div className="a-filters">
          <div className="seg seg--admin" role="radiogroup" aria-label="Trạng thái">
            {(['open', 'done'] as const).map((s) => (
              <button key={s} role="radio" aria-checked={show === s} className={show === s ? 'is-on' : ''} onClick={() => (setShow(s), setCursor(0))}>
                {s === 'open' ? 'Chưa xử lý' : 'Đã xử lý'}
              </button>
            ))}
          </div>
          <select value={kind} onChange={(e) => (setKind(e.target.value as typeof kind), setCursor(0))} aria-label="Loại mục">
            <option value="all">Mọi loại</option>
            {(Object.keys(KIND_LABEL) as ReviewItem['kind'][]).map((k) => (
              <option key={k} value={k}>
                {KIND_LABEL[k]}
              </option>
            ))}
          </select>
        </div>
      </header>
      <p className="rq__hint">
        <kbd>j</kbd> <kbd>k</kbd> chuyển mục <kbd>a</kbd> Accept <kbd>d</kbd> Disable <kbd>r</kbd> Report error <kbd>x</kbd> chọn nhiều <kbd>u</kbd> hoàn tác <kbd>?</kbd> tất cả phím
        <span className="a-note">
          <Icon name="info" size={14} /> Bản thử: quyết định lưu trong trình duyệt này, chưa ghi vào pipeline.
        </span>
      </p>

      <div className="rq__split">
        <div className="rq__list" role="listbox" aria-label="Mục cần duyệt">
          {items.length === 0 && <p className="a-empty">{show === 'open' ? 'Hết mục cần duyệt. Tốt lắm.' : 'Chưa có quyết định nào.'}</p>}
          {items.map((r, i) => {
            const { place } = signalOf(r)
            const d = decisions[r.id]
            return (
              <button
                key={r.id}
                role="option"
                aria-selected={i === cursor}
                className={`rq__row${i === cursor ? ' is-cur' : ''}${picked.has(r.id) ? ' is-picked' : ''}`}
                onClick={() => setCursor(i)}
              >
                <span className={`risk risk--${riskOf(r)}`}>{riskOf(r)}</span>
                <span className="rq__main">
                  <b>{itemTitle(r)}</b>
                  <small>{place?.name ?? r.placeId}</small>
                </span>
                <span className="rq__kind">{d ? VERDICT_LABEL[d.verdict] : KIND_LABEL[r.kind]}</span>
              </button>
            )
          })}
        </div>

        <div className="rq__detail">
          {cur ? (
            <div className="rq__card" ref={card} key={cur.id}>
              <Detail r={cur} />
              <footer className="rq__actions">
                {show === 'open' ? (
                  <>
                    <button className="a-btn a-btn--ok" onClick={() => act('accept')}>
                      Accept <kbd>a</kbd>
                    </button>
                    <button className="a-btn a-btn--bad" onClick={() => act('disable')}>
                      Disable <kbd>d</kbd>
                    </button>
                    <button className={`a-btn${reporting ? ' is-on' : ''}`} onClick={() => setReporting((x) => !x)}>
                      Report error <kbd>r</kbd>
                    </button>
                    {sameLow.length > 1 && (
                      <button className="a-btn a-btn--ghost" onClick={() => act('accept', undefined, sameLow)}>
                        Accept cả {sameLow.length} mục rủi ro thấp cùng loại
                      </button>
                    )}
                    {picked.size > 0 && (
                      <button className="a-btn a-btn--ghost" onClick={() => act('accept', undefined, [...picked])}>
                        Accept {picked.size} mục đã chọn <kbd>Shift A</kbd>
                      </button>
                    )}
                  </>
                ) : (
                  <button className="a-btn" onClick={() => undo(cur.id)}>
                    Hoàn tác <kbd>u</kbd>
                  </button>
                )}
              </footer>
              {reporting && (
                <div className="rq__report">
                  {REPORTS.map((k, i) => (
                    <button key={k} className="a-btn a-btn--ghost" onClick={() => act('report', k)}>
                      <kbd>{i + 1}</kbd> {REPORT_LABEL[k]}
                    </button>
                  ))}
                  <p>Report error kích hoạt build lại từ bằng chứng. Không sửa giá trị bằng tay.</p>
                </div>
              )}
            </div>
          ) : (
            <p className="a-empty">Chọn một mục ở danh sách bên trái.</p>
          )}
        </div>
      </div>
    </div>
  )
}

function Detail({ r }: { r: ReviewItem }) {
  const { place, signal } = signalOf(r)
  const total = signal ? Object.values(signal.distribution).reduce((a, b) => a + b, 0) : 0
  return (
    <>
      <header className="rq__dhead">
        <span className="rq__kindtag">{KIND_LABEL[r.kind]}</span>
        <h2>{itemTitle(r)}</h2>
        <p>
          {place?.name} <small>{place?.category}</small>
        </p>
        <p className="rq__why">{whyOf(r)}</p>
      </header>

      {signal ? (
        <>
          <section className="rq__sec">
            <h3>Giá trị</h3>
            <p className="rq__value">{valueLabel(signal.value)}</p>
            <div className="dist" role="img" aria-label="Phân bố ý kiến">
              {Object.entries(signal.distribution)
                .sort((a, b) => b[1] - a[1])
                .map(([v, n]) => (
                  <div key={v} className="dist__row">
                    <span>{valueLabel(v)}</span>
                    <span className="dist__bar">
                      <i style={{ width: `${(n / total) * 100}%` }} />
                    </span>
                    <b>{Math.round(n * 10) / 10}</b>
                  </div>
                ))}
            </div>
          </section>
          <section className="rq__sec">
            <h3>Thành phần độ tin cậy</h3>
            <dl className="parts">
              <div>
                <dt>Nguồn độc lập</dt>
                <dd>{signal.n}</dd>
              </div>
              <div>
                <dt>Đồng thuận</dt>
                <dd>{Math.round(signal.agreement * 100)}%</dd>
              </div>
              <div>
                <dt>Độ mới</dt>
                <dd>{signal.freshnessDays === null ? '—' : `${signal.freshnessDays} ngày`}</dd>
              </div>
              <div>
                <dt>Loại nguồn</dt>
                <dd>{signal.sourceTypes.join(', ')}</dd>
              </div>
            </dl>
          </section>
          <section className="rq__sec">
            <h3>Bằng chứng</h3>
            {signal.quotes.length ? (
              <ul className="quotes">
                {signal.quotes.map((q, i) => (
                  <li key={i}>
                    <Icon name="quote" size={14} />
                    <span>{q.text}</span>
                    <small>
                      {q.source}
                      {q.date ? `, ${q.date}` : ''}
                    </small>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="a-muted">Không có trích dẫn trong snapshot.</p>
            )}
          </section>
        </>
      ) : (
        <section className="rq__sec">
          <h3>Đề xuất</h3>
          <p>
            Nhãn <b>{r.feature}</b>, {r.value}. Accept để đưa vào danh sách xem xét ontology.
          </p>
        </section>
      )}
      {place && place.videos[0] && (
        <section className="rq__sec">
          <h3>Clip liên quan</h3>
          <TikTokEmbed id={place.videos[0].id} />
        </section>
      )}
      <section className="rq__sec">
        <h3>Finding của Judge</h3>
        <p className="a-muted">Snapshot chưa kèm finding của Judge.</p>
      </section>
    </>
  )
}
