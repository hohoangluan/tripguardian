import { type FormEvent, useLayoutEffect, useMemo, useRef, useState } from 'react'
import gsap from 'gsap'
import { fmtDuration, fmtTime } from '../../data/store'
import { navigate } from '../../router'
import { story } from '../../scene/story'
import { Icon, Page } from '../../ui/bits'
import { usePlanning } from '../planning/planning'
import type { Diff, ItineraryDay, Variant } from '../planning/types'
import { useTrip } from '../trip'

function toMin(hhmm: string) {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + (m || 0)
}

// What a sửa changed on the laid-out days, from the backend's diff.scope (src/planning/scope.py).
const SCOPE_TEXT: Record<Diff['scope'], string> = {
  none: '',
  relayout: 'Đã xếp lại một vài ngày bị ảnh hưởng.',
  variant: 'Đã xếp lại cả chuyến theo thay đổi này.',
  lodging_home: 'Đã đổi điểm nghỉ đêm, giờ di chuyển được tính lại.',
  lodging_fetch: 'Đã tìm lại danh sách chỗ ở.',
}

function VariantTabs({ variants, chosen, onPick }: { variants: Variant[]; chosen: string | null; onPick: (id: string) => void }) {
  return (
    <div className="daytabs" role="tablist">
      {variants.map((v) => (
        <button key={v.id} role="tab" aria-selected={chosen === v.id} className={chosen === v.id ? 'is-on' : ''} onClick={() => onPick(v.id)}>
          <b>{v.label}</b>
          <small>≈{fmtDuration(v.metrics.travel_min)} di chuyển cả chuyến</small>
          <span className={`robust robust--${v.robustness.level === 'solid' ? 'ok' : v.robustness.level === 'feasible' ? 'mid' : 'thin'}`}>
            {v.robustness.label}
          </span>
        </button>
      ))}
    </div>
  )
}

function Trade({ variants }: { variants: Variant[] }) {
  if (variants.length < 2) return null
  return (
    <table className="totals totals--table">
      <thead>
        <tr>
          <th>Phương án</th>
          <th>Di chuyển</th>
          <th>Chi phí</th>
          <th>Độ vững</th>
        </tr>
      </thead>
      <tbody>
        {variants.map((v) => (
          <tr key={v.id}>
            <td>{v.label}</td>
            <td>≈{fmtDuration(v.metrics.travel_min)}</td>
            <td>{v.metrics.cost_unknown ? 'Một phần chưa có giá' : `${v.metrics.cost_vnd.toLocaleString('vi-VN')} đ`}</td>
            <td>{v.robustness.label}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function LodgingPanel() {
  const { view, lodgingProgress, act, busy } = usePlanning()
  if (!view) return null
  const status = view.lodging.status
  const candidates = status === 'pending' && lodgingProgress ? lodgingProgress.candidates : view.lodging.candidates
  const chosen = view.state.lodging_id
  return (
    <section className="plan__lodging">
      <h2>Chỗ ở</h2>
      {status === 'pending' && <p className="muted">Đang tìm chỗ ở gần lịch trình...</p>}
      {status === 'unavailable' && <p className="muted">Chưa tra được chỗ ở, lịch dùng điểm xuất phát làm neo.</p>}
      <ul className="lodging-list">
        {candidates.map((c) => (
          <li key={c.id}>
            <button className={chosen === c.id ? 'btn btn--small is-on' : 'btn btn--small btn--ghost'} disabled={busy} onClick={() => act({ type: 'pick_lodging', id: c.id })}>
              {c.name} {c.price_vnd ? `· ${c.price_vnd.toLocaleString('vi-VN')} đ/đêm` : '· chưa có giá'}
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

function Backups({ items }: { items: Record<string, unknown>[] }) {
  if (!items.length) return null
  return (
    <section className="plan__backups">
      <h2>Dự phòng</h2>
      <ul>
        {items.map((b, i) => (
          <li key={i}>
            Ngày {String(b.day)}: thay cho {String(b.name ?? b.place_id)}
          </li>
        ))}
      </ul>
    </section>
  )
}

function TurnBox() {
  const { say, busy } = usePlanning()
  const [text, setText] = useState('')
  const [reply, setReply] = useState<string | null>(null)
  const send = async (e: FormEvent) => {
    e.preventDefault()
    const t = text.trim()
    if (!t || busy) return
    setText('')
    setReply('')
    await say(t, setReply)
  }
  return (
    <section className="pdchat">
      <form onSubmit={send}>
        <label className="pdchat__label" htmlFor="planchat">
          Nói với mình, ví dụ "Cà phê trước đi" hay "ngày 2 nhiều quá"
        </label>
        <div className="pdchat__row">
          <input id="planchat" value={text} maxLength={1000} onChange={(e) => setText(e.target.value)} placeholder="Gõ ở đây" />
          <button className="btn btn--small" disabled={busy || !text.trim()}>
            Gửi
          </button>
        </div>
      </form>
      {reply !== null && (
        <p className="bubble bubble--a" aria-live="polite">
          {reply || '…'}
        </p>
      )}
    </section>
  )
}

// Backend item kinds (src/planning/model.py): visit | travel | wait | buffer | rest | meal_free.
function itemLabel(kind: string) {
  if (kind === 'meal_free') return 'Ăn (tự chọn)'
  if (kind === 'rest') return 'Nghỉ'
  if (kind === 'wait') return 'Chờ'
  if (kind === 'buffer') return 'Đệm'
  return kind
}

function DayView({ day }: { day: ItineraryDay }) {
  const timeline = useRef<HTMLOListElement>(null)
  useLayoutEffect(() => {
    if (story.reducedMotion || !timeline.current) return
    const ctx = gsap.context(() => {
      gsap.fromTo('.tl__rail', { scaleY: 0 }, { scaleY: 1, duration: 1.1, ease: 'power2.inOut', transformOrigin: 'top' })
      gsap.from('.tl__item', { opacity: 0, x: 16, duration: 0.5, stagger: 0.09, delay: 0.15, ease: 'power2.out' })
    }, timeline)
    return () => ctx.revert()
  }, [day])

  return (
    <ol className="tl" ref={timeline}>
      <span className="tl__rail" aria-hidden="true" />
      {day.items.map((it, i) => {
        if (it.kind === 'travel')
          return (
            <li className="tl__leg-row" key={i}>
              <Icon name="route" size={13} /> ≈{toMin(it.end) - toMin(it.start)} phút đi
            </li>
          )
        return (
          <li className="tl__item" key={i}>
            <span className="tl__time">{fmtTime(toMin(it.start))}</span>
            <span className="tl__dot tl__dot--stop" />
            <div className="tl__body">
              {it.place_id ? (
                <button className="link tl__name" onClick={() => navigate(`/app/place/${encodeURIComponent(it.place_id!)}`)}>
                  {it.name}
                </button>
              ) : (
                <span className="tl__name">{it.name ?? itemLabel(it.kind)}</span>
              )}
              <small>đến {fmtTime(toMin(it.end))}</small>
              {it.note && (
                <p className="tl__flag">
                  <Icon name="alert" size={13} /> {it.note}
                </p>
              )}
            </div>
          </li>
        )
      })}
    </ol>
  )
}

export function Itinerary() {
  const { trip } = useTrip()
  const { view, diff, error, busy, act, confirm: confirmPlan } = usePlanning()
  const [dayIdx, setDayIdx] = useState(0)

  const variant = useMemo(() => view?.variants.find((v) => v.id === view.state.chosen_variant) ?? null, [view])
  const days = view?.itinerary ?? variant?.itinerary ?? []

  if (!trip.planningId)
    return (
      <Page className="page--narrow">
        <div className="empty">
          <img src="/img/empty.webp" alt="" />
          <p>Chưa có lịch trình. Xác nhận khả thi trước đã.</p>
          <button className="btn" onClick={() => navigate('/app/feasibility')}>
            Kiểm tra khả thi
          </button>
        </div>
      </Page>
    )

  if (!view) return <div className="loading">{error ?? 'Đang tải'}</div>

  // No schedule could be laid out from the confirmed places (view.ok false, back_to_decision set): say so, do not show empty tabs.
  if (!view.variants.length)
    return (
      <Page className="page--narrow">
        <header className="phead">
          <h1>Chưa xếp được lịch</h1>
          <p>Các nơi đã chọn chưa đủ để xếp thành lịch trình. Quay lại chọn lại địa điểm nhé.</p>
        </header>
        {view.warnings.length > 0 && (
          <ul className="warn-list">
            {view.warnings.map((w, i) => (
              <li key={i}>
                <Icon name="alert" size={13} /> {w.text}
              </li>
            ))}
          </ul>
        )}
        <div className="pfoot">
          <button className="btn" onClick={() => navigate('/app/shortlist')}>
            Chọn lại địa điểm
          </button>
        </div>
      </Page>
    )

  if (!view.state.chosen_variant)
    return (
      <Page className="page--narrow">
        <header className="phead">
          <h1>Chọn một phương án</h1>
          <p>Mỗi phương án tối ưu một mục tiêu khác nhau.</p>
        </header>
        <VariantTabs variants={view.variants} chosen={null} onPick={(id) => act({ type: 'pick_variant', id })} />
        <Trade variants={view.variants} />
      </Page>
    )

  const d = days[dayIdx]

  const onConfirm = async () => {
    const out = await confirmPlan()
    if (out) navigate('/app/feedback')
  }

  return (
    <Page className="page--wide">
      <header className="phead phead--split">
        <div>
          <h1>Lịch trình</h1>
          <p>Giờ giấc và đường đi là ước tính.</p>
        </div>
      </header>

      <VariantTabs variants={view.variants} chosen={view.state.chosen_variant} onPick={(id) => act({ type: 'pick_variant', id })} />
      <Trade variants={view.variants} />

      <div className="daytabs" role="tablist">
        {days.map((x, i) => (
          <button key={x.day} role="tab" aria-selected={dayIdx === i} className={dayIdx === i ? 'is-on' : ''} onClick={() => setDayIdx(i)}>
            <b>Ngày {x.day}</b>
            {x.date && <small>{new Date(x.date).toLocaleDateString('vi-VN', { weekday: 'short', day: 'numeric', month: 'numeric' })}</small>}
          </button>
        ))}
      </div>

      {d && (
        <div className="plan">
          <div className="plan__left">
            <DayView day={d} />
            <dl className="totals totals--inline">
              <div>
                <dt>Di chuyển</dt>
                <dd>≈{fmtDuration(view.travel_load?.[dayIdx]?.travel_min ?? 0)}</dd>
              </div>
            </dl>
          </div>
          <LodgingPanel />
        </div>
      )}

      {diff && SCOPE_TEXT[diff.scope] && <p className="muted">{SCOPE_TEXT[diff.scope]}</p>}

      <Backups items={(variant?.backups ?? []) as Record<string, unknown>[]} />

      {view.warnings.length > 0 && (
        <ul className="warn-list">
          {view.warnings.map((w, i) => (
            <li key={i}>
              <Icon name="alert" size={13} /> {w.text}
            </li>
          ))}
        </ul>
      )}

      <TurnBox />

      {error && <p className="error">{error}</p>}

      <div className="pfoot">
        <button className="link" onClick={() => navigate('/app/feasibility')}>
          Quay lại kiểm tra
        </button>
        <button className="btn" disabled={busy} onClick={onConfirm}>
          Chốt kế hoạch này
        </button>
      </div>
    </Page>
  )
}
