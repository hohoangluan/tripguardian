import gsap from 'gsap'
import { useEffect, useMemo, useRef, useState } from 'react'
import { fmtDuration, placeById } from '../../data/store'
import { navigate } from '../../router'
import { story } from '../../scene/story'
import { Icon, Sheet } from '../../ui/bits'
import { deltaLine, plan, type Plan } from '../planner'
import { useTrip } from '../trip'

const VERDICT: Record<Plan['status'], string> = {
  feasible: 'Đi kịp',
  partial: 'Có chỗ cần sửa',
  infeasible: 'Quá sức',
}

// Live curation summary (§2.8): never blocks, always one line of difference.
export function CurateBar() {
  const { trip, dispatch } = useTrip()
  const current = useMemo(() => plan(trip), [trip])
  const prev = useRef<Plan | null>(null)
  const prevSel = useRef<string[]>(trip.selected)
  const [removed, setRemoved] = useState<string | null>(null)
  const [delta, setDelta] = useState<ReturnType<typeof deltaLine> | null>(null)
  const [open, setOpen] = useState(false)
  const bar = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const before = prev.current
    const beforeSel = prevSel.current
    prev.current = current
    prevSel.current = trip.selected
    if (!before || before.totals.places === current.totals.places) return
    setDelta(deltaLine(before, current))
    setRemoved(beforeSel.find((id) => !trip.selected.includes(id)) ?? null)
    if (!story.reducedMotion && bar.current) gsap.fromTo(bar.current, { y: 6 }, { y: 0, duration: 0.5, ease: 'elastic.out(1, 0.5)' })
    const t = setTimeout(() => setDelta(null), 5200)
    return () => clearTimeout(t)
  }, [current])

  const warnings = current.conflicts.length + current.days.reduce((a, d) => a + d.stops.filter((s) => s.flags.length).length, 0)

  return (
    <>
      <div className="curate" ref={bar}>
        {delta && (
          <p className={`curate__delta${delta.warn ? ' is-warn' : ''}`} role="status">
            {delta.text}. {delta.note}
            {removed && (
              <button
                className="link"
                onClick={() => {
                  dispatch({ type: 'select', id: removed })
                  setRemoved(null)
                }}
              >
                Hoàn tác
              </button>
            )}
          </p>
        )}
        <button className="curate__main" onClick={() => setOpen(true)} aria-label="Mở danh sách đã chọn">
          <span className="curate__count">{current.totals.places}</span>
          <span className="curate__nums">
            <b>{current.totals.places} nơi đã chọn</b>
            <small>
              {fmtDuration(current.totals.visit)} tham quan, ≈{fmtDuration(current.totals.travel)} đi lại
            </small>
          </span>
          <span className={`verdict verdict--${current.status}`}>
            {VERDICT[current.status]}
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
            <dd>{fmtDuration(current.totals.visit)}</dd>
          </div>
          <div>
            <dt>Di chuyển, ước tính</dt>
            <dd>{fmtDuration(current.totals.travel)}</dd>
          </div>
          <div>
            <dt>Thời gian có</dt>
            <dd>{fmtDuration(current.totals.available)}</dd>
          </div>
          <div>
            <dt>Chi phí</dt>
            <dd className="muted">Chưa có thông tin</dd>
          </div>
        </dl>
        <ul className="picked">
          {trip.selected.map((id) => {
            const p = placeById(id)
            if (!p) return null
            const locked = trip.locked.includes(id)
            return (
              <li key={id}>
                <button className="link picked__name" onClick={() => (setOpen(false), navigate(`/app/place/${encodeURIComponent(id)}`))}>
                  {p.name}
                </button>
                <button className={`iconbtn${locked ? ' is-on' : ''}`} aria-pressed={locked} aria-label={locked ? 'Mở khóa' : 'Khóa'} onClick={() => dispatch({ type: 'lock', id })}>
                  <Icon name={locked ? 'lock' : 'unlock'} size={16} />
                </button>
                <button className="iconbtn" aria-label={`Bỏ ${p.name}`} onClick={() => dispatch({ type: 'unselect', id })}>
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
