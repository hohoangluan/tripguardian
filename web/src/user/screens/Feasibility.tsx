import gsap from 'gsap'
import { useLayoutEffect, useRef, useState } from 'react'
import { fmtDuration } from '../../data/store'
import { navigate } from '../../router'
import { story } from '../../scene/story'
import { Icon, Page } from '../../ui/bits'
import { confirm } from '../pd/api'
import { useDecision } from '../pd/decision'
import { createPlanning } from '../planning/api'
import type { Feasibility as F } from '../pd/types'
import { useTrip } from '../trip'

const HEAD: Record<F['status'], { title: string; tone: 'ok' | 'warn' | 'bad' }> = {
  feasible: { title: 'Đi kịp. Sẵn sàng xếp lịch.', tone: 'ok' },
  partial: { title: 'Gần được rồi, còn vài chỗ cần bạn chọn cách sửa.', tone: 'warn' },
  infeasible: { title: 'Kế hoạch này quá sức so với thời gian có.', tone: 'bad' },
  unknown: { title: 'Chưa biết chuyến đi mấy ngày nên chưa kiểm được thời gian.', tone: 'warn' },
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
      gsap.from('.conflict', { opacity: 0, x: -24, rotateY: -12, duration: 0.6, stagger: 0.08, ease: 'power3.out' })
    }, list)
    return () => ctx.revert()
  }, [nConflicts])

  if (!view) return <div className="loading">{error ?? 'Đang tải'}</div>
  if (!view.selected.length)
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

  const f = view.feasibility
  const t = f.totals
  const head = f.status === 'feasible' && f.warnings.length ? { title: `Đi kịp, nếu ${f.warnings.length} điều chưa chắc dưới đây đúng như dự kiến.`, tone: 'ok' as const } : HEAD[f.status]
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

  return (
    <Page className="page--narrow">
      <header className={`verdict-head verdict-head--${head.tone}`}>
        <h1>{head.title}</h1>
        {f.known_days && (
          <>
            <div className="meter" aria-label={`Cần ${fmtDuration(t.needed)} trên ${fmtDuration(t.available)}`}>
              <div className="meter__fill" style={{ width: `${Math.min(100, (t.needed / Math.max(1, t.available)) * 100)}%` }} />
              {t.needed > t.available && <div className="meter__over" style={{ width: `${Math.min(40, ((t.needed - t.available) / Math.max(1, t.available)) * 100)}%` }} />}
            </div>
            <p className="meter__legend">
              Cần khoảng {fmtDuration(t.needed)} cho {t.places} nơi, chuyến đi có {fmtDuration(t.available)}. Thời gian di chuyển là ước tính.
            </p>
          </>
        )}
      </header>

      {f.warnings.length > 0 && (
        <section className="block">
          <h2 className="block__title">
            <Icon name="info" size={16} /> Kiểm tra trước khi đi
          </h2>
          <ul className="checks">
            {f.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </section>
      )}

      <div className="conflicts" ref={list}>
        {f.conflicts.map((c) => (
          <article key={c.id} className={`conflict${c.physical ? ' conflict--hard' : ' conflict--rule'}`}>
            <p className="conflict__what">
              <Icon name={c.physical ? 'alert' : 'lock'} size={16} /> {c.title}
            </p>
            <p>{c.rule}</p>
            <p className="conflict__kind">{c.physical ? 'Giới hạn thật: không đi kịp. Chỉ có cách đổi lựa chọn.' : 'Quy tắc của bạn: bạn có thể nới nếu muốn.'}</p>
            <div className="fixes">
              {c.fixes.map((x) => (
                <button key={x.label} className="fix" disabled={busy} onClick={() => (x.action ? act(x.action) : navigate('/app/understand'))}>
                  <b>{x.label}</b>
                  <small>{x.effect}</small>
                </button>
              ))}
            </div>
          </article>
        ))}
      </div>

      {view.wishlist.length > 0 && (
        <section className="block">
          <h2 className="block__title">Để dành cho dịp khác</h2>
          <ul className="checks">
            {view.wishlist.map((w) => (
              <li key={w.id}>
                <b>{w.name}</b>: {w.reason}
              </li>
            ))}
          </ul>
        </section>
      )}

      {(msg || error) && (
        <p className="notice" role="alert">
          {msg ?? error}
        </p>
      )}
      <div className="pfoot">
        <button className="link" onClick={() => navigate('/app/shortlist')}>
          Sửa danh sách
        </button>
        {/* No button turns a plan that cannot be done into a "feasible" one (UX brief §3.6). */}
        <button className="btn" disabled={!confirmable || sending} onClick={go}>
          {confirmable ? 'Xác nhận và xếp lịch' : 'Chọn cách sửa ở trên trước'}
        </button>
      </div>
    </Page>
  )
}
