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

// The "Đã chọn" bar (UI spec §4): always visible on 4–6, one line of difference after each change, never blocking.
export function CurateBar() {
  const { view, diff, act, busy } = useDecision()
  const [shown, setShown] = useState<Diff | null>(null)
  const [open, setOpen] = useState(false)
  const bar = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!diff) return
    setShown(diff)
    if (!story.reducedMotion && bar.current) gsap.fromTo(bar.current, { y: 6 }, { y: 0, duration: 0.5, ease: 'elastic.out(1, 0.5)' })
    const t = setTimeout(() => setShown(null), 7000)
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
        <button className="curate__main" onClick={() => setOpen(true)} aria-label="Mở danh sách đã chọn">
          <span className="curate__count">{t.places}</span>
          <b>Đã chọn {t.places} nơi</b>
        </button>
        <div className="curate__nums">
          <p className="mono">
            {fmtDuration(t.visit)} tham quan · di chuyển ≈{fmtDuration(t.travel)}
            <span className={`curate__verdict is-${f.status}`}>
              {VERDICT[f.status]}
              {warnings > 0 ? ` · ${warnings} lưu ý` : ''}
            </span>
          </p>
          {shown ? (
            <p className={`curate__delta${shown.status[1] !== 'feasible' ? ' is-warn' : ''}`} role="status">
              {shown.text}.{' '}
              <button className="link" disabled={busy} onClick={() => act({ type: 'undo' })}>
                Hoàn tác
              </button>
            </p>
          ) : (
            <p className="curate__delta curate__delta--quiet">Thời gian là ước tính. Bấm số bên trái để xem danh sách.</p>
          )}
        </div>
        <button className="btn" onClick={() => navigate('/app/feasibility')}>
          Kiểm tra khả thi
        </button>
      </div>

      <Sheet open={open} onClose={() => setOpen(false)} label="Danh sách đã chọn">
        <h2>Đã chọn {t.places} nơi</h2>
        <dl className="totals">
          <div>
            <dt>Tham quan</dt>
            <dd className="mono">{fmtDuration(t.visit)}</dd>
          </div>
          <div>
            <dt>Di chuyển, ước tính</dt>
            <dd className="mono">≈{fmtDuration(t.travel)}</dd>
          </div>
          <div>
            <dt>Thời gian có</dt>
            <dd className="mono">{f.known_days ? fmtDuration(t.available) : 'Chưa biết số ngày'}</dd>
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
                <button className={`iconbtn iconbtn--sm${locked ? ' is-on' : ''}`} aria-pressed={locked} aria-label={locked ? 'Mở khóa' : 'Khóa'} disabled={busy} onClick={() => act({ type: locked ? 'unlock' : 'lock', place_id: id })}>
                  <Icon name={locked ? 'lock' : 'unlock'} size={13} />
                </button>
                <button className="iconbtn iconbtn--sm" aria-label={`Bỏ ${name}`} disabled={busy} onClick={() => act({ type: 'drop', place_id: id })}>
                  <Icon name="x" size={13} />
                </button>
              </li>
            )
          })}
        </ul>
        <button className="btn btn--wide" onClick={() => (setOpen(false), navigate('/app/feasibility'))}>
          Kiểm tra khả thi
        </button>
      </Sheet>
    </>
  )
}
