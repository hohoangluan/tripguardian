import gsap from 'gsap'
import { useLayoutEffect, useRef, useState } from 'react'
import { fmtDuration } from '../../data/store'
import { navigate } from '../../router'
import { story } from '../../scene/story'
import { Icon, Page } from '../../ui/bits'
import { LineArt } from '../../ui/LineArt'
import { confirm } from '../pd/api'
import { useDecision } from '../pd/decision'
import { createPlanning } from '../planning/api'
import type { Feasibility as F } from '../pd/types'
import { useTrip } from '../trip'

const HEAD: Record<F['status'], { title: string; tone: 'ok' | 'warn' | 'bad' }> = {
  feasible: { title: 'Đi kịp, sẵn sàng xếp lịch', tone: 'ok' },
  partial: { title: 'Đi được, nhưng còn chỗ cần sửa', tone: 'warn' },
  infeasible: { title: 'Quá sức so với thời gian có', tone: 'bad' },
  unknown: { title: 'Chưa biết đi mấy ngày nên chưa kiểm được giờ', tone: 'warn' },
}

export function Feasibility() {
  const { trip, dispatch } = useTrip()
  const { view, act, busy, error } = useDecision()
  const list = useRef<HTMLDivElement>(null)
  const [sending, setSending] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const status = view?.feasibility.status
  const nConflicts = view?.feasibility.conflicts.length ?? 0

  // Background: a red route while conflicts remain, the golden one once clear.
  useLayoutEffect(() => {
    story.appScene = status === 'feasible' ? 0.96 : 0.8
  }, [status])

  useLayoutEffect(() => {
    if (story.reducedMotion || !list.current) return
    const ctx = gsap.context(() => {
      gsap.from('.conflict', { opacity: 0, y: 16, duration: 0.5, stagger: 0.08, ease: 'power3.out' })
    }, list)
    return () => ctx.revert()
  }, [nConflicts])

  if (!view) return <div className={`loading${error ? ' loading--error' : ''}`}>{error ?? 'Đang kiểm tra'}</div>
  if (!view.selected.length)
    return (
      <Page className="page--narrow">
        <div className="empty">
          <LineArt variant="spot" />
          <p>Chưa có nơi nào được chọn để kiểm tra.</p>
          <button className="btn" onClick={() => navigate('/app/shortlist')}>
            Chọn địa điểm
          </button>
        </div>
      </Page>
    )

  const f = view.feasibility
  const t = f.totals
  const head = f.status === 'feasible' && f.warnings.length ? { title: `Đi kịp, nếu ${f.warnings.length} điều dưới đây đúng`, tone: 'ok' as const } : HEAD[f.status]
  const confirmable = f.status === 'feasible' || f.status === 'unknown'

  const go = async () => {
    if (!trip.decisionId) return
    setSending(true)
    setMsg(null)
    try {
      const out = await confirm(trip.decisionId)
      // Hand Planning the Decision Output just returned: no second round-trip to the Decision server.
      const created = await createPlanning(out)
      dispatch({
        type: 'set',
        patch: {
          selected: out.confirmed.map((c) => c.id),
          locked: out.confirmed.filter((c) => c.role !== 'selected').map((c) => c.id),
          planningId: created.id,
        },
      })
      navigate('/app/plan')
    } catch {
      setMsg('Chưa xác nhận được, thử lại.')
    } finally {
      setSending(false)
    }
  }

  const pct = (t.needed / Math.max(1, t.available)) * 100
  const step = `Kiểm tra khả thi · ${t.places} nơi`
  return (
    <Page className="page--mid">
      <header className={`fz-head is-${head.tone}`}>
        <span className="uhead__kicker">{step}</span>
        <h1>{head.title}</h1>
        {f.known_days && (
          <>
            <div className="meter" role="img" aria-label={`Cần ${fmtDuration(t.needed)} trên ${fmtDuration(t.available)}`}>
              <div className="meter__fill" style={{ width: `${Math.min(100, pct)}%` }} />
              {t.needed > t.available && <div className="meter__over" style={{ left: `${(100 * t.available) / t.needed}%`, width: `${100 - (100 * t.available) / t.needed}%` }} />}
            </div>
            <p className="meter__legend">
              Cần khoảng {fmtDuration(t.needed)} cho {t.places} nơi, chuyến đi có {fmtDuration(t.available)}. Thời gian di chuyển là ước tính.
            </p>
          </>
        )}
      </header>

      {f.conflicts.length > 0 && (
        <section className="fz-sec">
          <h2 className="utitle">Xung đột</h2>
          <div className="fz-conflicts" ref={list}>
            {f.conflicts.map((c) => (
              <article key={c.id} className={`conflict${c.physical ? ' conflict--hard' : ' conflict--rule'}`}>
                <h3>{c.title}</h3>
                <p className="conflict__rule">{c.rule}</p>
                <p className="conflict__kind">{c.physical ? 'Không đi kịp thật sự: chỉ có cách đổi lựa chọn.' : 'Quy tắc của bạn: bạn có thể nới nếu muốn.'}</p>
                <ul className="fixes">
                  {c.fixes.map((x) => (
                    <li key={x.label}>
                      <button className="fix" disabled={busy} onClick={() => (x.action ? act(x.action) : navigate('/app/understand'))}>
                        <span className="fix__radio" aria-hidden="true" />
                        <span>
                          <b>{x.label}</b> {x.effect && <small>— {x.effect}</small>}
                        </span>
                        {x.action?.type === 'relax' && <Icon name="lock" size={16} />}
                      </button>
                    </li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        </section>
      )}

      {f.warnings.length > 0 && (
        <section className="fz-sec">
          <h2 className="utitle">Kiểm tra trước khi đi</h2>
          <ul className="checks ucard">
            {f.warnings.map((w) => (
              <li key={w}>
                <Icon name="alert" size={16} /> {w}
              </li>
            ))}
          </ul>
        </section>
      )}

      {view.wishlist.length > 0 && (
        <section className="fz-sec">
          <h2 className="utitle">Để dành cho dịp khác</h2>
          <div className="saved">
            {view.wishlist.map((w) => (
              <button key={w.id} className="chip" title={w.reason} onClick={() => navigate(`/app/place/${encodeURIComponent(w.id)}`)}>
                {w.name}
              </button>
            ))}
          </div>
        </section>
      )}

      {(msg || error) && (
        <p className="notice notice--bad" role="alert">
          <Icon name="alert" size={16} /> {msg ?? error}
        </p>
      )}
      <div className="pfoot">
        <button className="link" onClick={() => navigate('/app/shortlist')}>
          Quay lại chọn lại
        </button>
        {/* No button turns a plan that cannot be done into a "feasible" one (UX brief §3.6). */}
        <button className="btn" disabled={!confirmable || sending} onClick={go}>
          {confirmable ? 'Xác nhận và xếp lịch' : 'Chọn cách sửa ở trên trước'}
        </button>
      </div>
    </Page>
  )
}
