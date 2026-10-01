import gsap from 'gsap'
import { useLayoutEffect, useMemo, useRef } from 'react'
import { fmtDuration } from '../../data/store'
import { navigate } from '../../router'
import { story } from '../../scene/story'
import { Icon, Page } from '../../ui/bits'
import { plan } from '../planner'
import { useTrip } from '../trip'

const HEAD = {
  feasible: { title: 'Đi kịp. Sẵn sàng xếp lịch.', tone: 'ok' },
  partial: { title: 'Gần được rồi, còn vài chỗ cần bạn chọn cách sửa.', tone: 'warn' },
  infeasible: { title: 'Kế hoạch này quá sức so với thời gian có.', tone: 'bad' },
} as const

export function Feasibility() {
  const { trip, dispatch } = useTrip()
  const result = useMemo(() => plan(trip), [trip])
  const list = useRef<HTMLDivElement>(null)

  // Background: a red route while conflicts remain, the golden one once clear.
  useLayoutEffect(() => {
    story.appScene = result.status === 'feasible' ? 0.96 : 0.8
  }, [result.status])

  useLayoutEffect(() => {
    if (story.reducedMotion || !list.current) return
    const ctx = gsap.context(() => {
      gsap.from('.conflict', { opacity: 0, x: -24, rotateY: -12, duration: 0.6, stagger: 0.08, ease: 'power3.out' })
    }, list)
    return () => ctx.revert()
  }, [result.conflicts.length])

  if (!trip.selected.length)
    return (
      <Page className="page--narrow">
        <div className="empty">
          <img src="/img/empty.webp" alt="" />
          <p>Chưa có nơi nào được chọn để kiểm tra.</p>
          <button className="btn" onClick={() => navigate('/app/shortlist')}>
            Chọn địa điểm
          </button>
        </div>
      </Page>
    )

  const t = result.totals
  // Open questions stay visible even when the plan fits (UX brief §3.2).
  const checks = result.days.flatMap((d) =>
    d.stops.flatMap((s) => s.flags.filter((f) => /chưa có thông tin|chưa xác nhận/.test(f)).map((f) => ({ id: `${s.place.id}${f}`, name: s.place.name, f }))),
  )
  const head =
    result.status === 'feasible' && checks.length
      ? { title: `Đi kịp, nếu ${checks.length} điều chưa chắc dưới đây đúng như dự kiến.`, tone: 'ok' as const }
      : HEAD[result.status]

  return (
    <Page className="page--narrow">
      <header className={`verdict-head verdict-head--${head.tone}`}>
        <h1>{head.title}</h1>
        <div className="meter" aria-label={`Cần ${fmtDuration(t.needed)} trên ${fmtDuration(t.available)}`}>
          <div className="meter__fill" style={{ width: `${Math.min(100, (t.needed / t.available) * 100)}%` }} />
          {t.needed > t.available && <div className="meter__over" style={{ width: `${Math.min(40, ((t.needed - t.available) / t.available) * 100)}%` }} />}
        </div>
        <p className="meter__legend">
          Cần khoảng {fmtDuration(t.needed)} cho {t.places} nơi, chuyến đi có {fmtDuration(t.available)}. Thời gian di chuyển là ước tính.
        </p>
      </header>

      {result.reasons.length > 0 && (
        <section className="block block--bad">
          <h2 className="block__title">Vì sao không khả thi</h2>
          <ul>
            {result.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
          <button className="btn btn--ghost" onClick={() => navigate('/app/shortlist')}>
            Quay lại bỏ bớt địa điểm
          </button>
        </section>
      )}

      {result.status === 'feasible' && checks.length > 0 && (
        <section className="block">
          <h2 className="block__title">
            <Icon name="info" size={16} /> Kiểm tra trước khi đi
          </h2>
          <ul className="checks">
            {checks.map((c) => (
              <li key={c.id}>
                <b>{c.name}</b>: {c.f.replace(', kiểm tra trước khi đi', '').toLowerCase()}
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="conflicts" ref={list}>
        {result.conflicts.map((c) => (
          <article key={c.id} className={`conflict${c.physical ? ' conflict--hard' : ' conflict--rule'}`}>
            <p className="conflict__what">
              <Icon name={c.physical ? 'alert' : 'lock'} size={16} /> {c.title}
            </p>
            <p>{c.rule}</p>
            <p className="conflict__kind">{c.physical ? 'Giới hạn thật: không đi kịp. Chỉ có cách dời.' : 'Quy tắc của bạn: bạn có thể nới nếu muốn.'}</p>
            <div className="fixes">
              {c.fixes.map((f) => (
                <button key={f.label} className="fix" onClick={() => dispatch(f.action)}>
                  <b>{f.label}</b>
                  <small>{f.effect}</small>
                </button>
              ))}
            </div>
          </article>
        ))}
      </div>

      <div className="pfoot">
        <button className="link" onClick={() => navigate('/app/shortlist')}>
          Sửa danh sách
        </button>
        {/* No button turns a plan that cannot be done into a "feasible" one (UX brief §3.6). */}
        <button className="btn" disabled={result.status !== 'feasible'} onClick={() => navigate('/app/plan')}>
          {result.status === 'feasible' ? 'Xếp lịch' : 'Chọn cách sửa ở trên trước'}
        </button>
      </div>
    </Page>
  )
}
