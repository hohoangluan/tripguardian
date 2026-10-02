import gsap from 'gsap'
import { useEffect, useRef, useState } from 'react'
import { fmtDuration } from '../../data/store'
import { navigate } from '../../router'
import { story } from '../../scene/story'
import { Icon, Sheet } from '../../ui/bits'
import { useDecision } from '../pd/decision'
import type { Diff, Feasibility } from '../pd/types'

const VERDICT: Record<Feasibility['status'], string> = {
  feasible: 'Đi kịp',
  partial: 'Có chỗ cần sửa',
  infeasible: 'Quá sức',
  unknown: 'Chưa biết số ngày',
}

// Live curation summary (§2.8): never blocks, always one line of difference with an undo.
export function CurateBar() {
  const { view, diff, act, busy } = useDecision()
  const [shown, setShown] = useState<Diff | null>(null)
  const [open, setOpen] = useState(false)
  const bar = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!diff) return
    setShown(diff)
    if (!story.reducedMotion && bar.current) gsap.fromTo(bar.current, { y: 6 }, { y: 0, duration: 0.5, ease: 'elastic.out(1, 0.5)' })
    const t = setTimeout(() => setShown(null), 5200)
    return () => clearTimeout(t)
  }, [diff])

  if (!view) return null
  const f = view.feasibility
  const t = f.totals
  const names = new Map(view.groups.flatMap((g) => g.cards).map((c) => [c.id, c.name]))
  const warnings = f.conflicts.length + f.warnings.length

  return (
    <>
      <div className="curate" ref={bar}>
        {shown && (
          <p className={`curate__delta${shown.status[1] !== 'feasible' ? ' is-warn' : ''}`} role="status">
            {shown.text}.{' '}
            <button className="link" disabled={busy} onClick={() => act({ type: 'undo' })}>
              Hoàn tác
            </button>
          </p>
        )}
        <button className="curate__main" onClick={() => setOpen(true)} aria-label="Mở danh sách đã chọn">
          <span className="curate__count">{t.places}</span>
          <span className="curate__nums">
            <b>{t.places} nơi đã chọn</b>
            <small>
              {fmtDuration(t.visit)} tham quan, ≈{fmtDuration(t.travel)} đi lại
            </small>
          </span>
          <span className={`verdict verdict--${f.status === 'unknown' ? 'partial' : f.status}`}>
            {VERDICT[f.status]}
            {warnings > 0 && <em>{warnings} lưu ý</em>}
          </span>
        </button>
        <button className="btn btn--small" onClick={() => navigate('/app/feasibility')}>
          Kiểm tra
        </button>
      </div>

      <Sheet open={open} onClose={() => setOpen(false)} label="Danh sách đã chọn">
        <h2>Danh sách đã chọn</h2>
        <dl className="totals">
          <div>
            <dt>Tham quan</dt>
            <dd>{fmtDuration(t.visit)}</dd>
          </div>
          <div>
            <dt>Di chuyển, ước tính</dt>
            <dd>{fmtDuration(t.travel)}</dd>
          </div>
          <div>
            <dt>Thời gian có</dt>
            <dd>{f.known_days ? fmtDuration(t.available) : 'Chưa biết số ngày'}</dd>
          </div>
        </dl>
        <ul className="picked">
          {view.selected.map((id) => {
            const locked = view.locked.includes(id)
            const name = names.get(id) ?? id
            return (
              <li key={id}>
                <button className="link picked__name" onClick={() => (setOpen(false), navigate(`/app/place/${encodeURIComponent(id)}`))}>
                  {name}
                </button>
                <button className={`iconbtn${locked ? ' is-on' : ''}`} aria-pressed={locked} aria-label={locked ? 'Mở khóa' : 'Khóa'} disabled={busy} onClick={() => act({ type: locked ? 'unlock' : 'lock', place_id: id })}>
                  <Icon name={locked ? 'lock' : 'unlock'} size={16} />
                </button>
                <button className="iconbtn" aria-label={`Bỏ ${name}`} disabled={busy} onClick={() => act({ type: 'drop', place_id: id })}>
                  <Icon name="x" size={16} />
                </button>
              </li>
            )
          })}
        </ul>
        <button className="btn" onClick={() => (setOpen(false), navigate('/app/feasibility'))}>
          Kiểm tra khả thi
        </button>
      </Sheet>
    </>
  )
}
