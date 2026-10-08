import { enterStage } from '../journey'
import gsap from 'gsap'
import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { fmtDuration, fmtTime, mapsRouteEmbed, mapsRouteLink, placeById, VEHICLE_LABEL } from '../../data/store'
import { navigate } from '../../router'
import { story } from '../../scene/story'
import { GoogleMap, Icon, Page, PlaceCover } from '../../ui/bits'
import { LineArt } from '../../ui/LineArt'
import { usePlanning } from '../planning/planning'
import type { CrowdTip, DayConditions, Diff, ItineraryDay, ItineraryItem, Variant } from '../planning/types'
import { useTrip } from '../trip'

// UI spec §4 Trang 8. Times and routes are estimates and say so; warnings sit on the stop they concern.

function toMin(hhmm: string) {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + (m || 0)
}

// What a change did to the laid-out days, from the backend's diff.scope (src/planning/scope.py).
const SCOPE_TEXT: Record<Diff['scope'], string> = {
  none: '',
  relayout: 'Đã xếp lại một vài ngày bị ảnh hưởng',
  variant: 'Đã xếp lại cả chuyến theo thay đổi này',
  lodging_home: 'Đã đổi chỗ nghỉ, giờ di chuyển được tính lại',
  lodging_fetch: 'Đã tìm lại danh sách chỗ ở',
}

const ROBUST: Record<string, string> = { solid: 'ok', feasible: 'mid', fragile: 'thin' }

function costText(v: Variant) {
  if (v.metrics.cost_unknown) return v.metrics.cost_vnd ? `≈${v.metrics.cost_vnd.toLocaleString('vi-VN')} đ, một phần chưa có giá` : 'Một phần chưa có giá'
  return `≈${v.metrics.cost_vnd.toLocaleString('vi-VN')} đ`
}

function itemLabel(kind: string) {
  if (kind === 'meal_free') return 'Ăn (tự chọn)'
  if (kind === 'rest') return 'Nghỉ'
  if (kind === 'wait') return 'Chờ'
  if (kind === 'buffer') return 'Đệm'
  return kind
}

const ITEM_NOTE: Record<string, string> = {
  meal_free: 'Ăn ở khu gần đó, mình không chọn quán thay bạn.',
  rest: 'Nghỉ chân, về chỗ ở hoặc ngồi lại.',
  wait: 'Chờ nơi tiếp theo mở cửa.',
  buffer: 'Thời gian dự phòng, trễ một chút vẫn ổn.',
}

function VariantTabs({ variants, chosen, onPick }: { variants: Variant[]; chosen: string | null; onPick: (id: string) => void }) {
  return (
    <div className="vtabs" role="tablist" aria-label="Phương án">
      {variants.map((v) => (
        <button key={v.id} role="tab" aria-selected={chosen === v.id} className={chosen === v.id ? 'is-on' : ''} onClick={() => onPick(v.id)}>
          {v.label}
        </button>
      ))}
    </div>
  )
}

function Trade({ variants, chosen }: { variants: Variant[]; chosen: string | null }) {
  if (variants.length < 2) return null
  return (
    <table className="trade">
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
          <tr key={v.id} className={chosen === v.id ? 'is-on' : ''}>
            <th>{v.label}</th>
            <td className="mono">≈{fmtDuration(v.metrics.travel_min)}</td>
            <td className="mono">{costText(v)}</td>
            <td>
              <span className={`robust robust--${ROBUST[v.robustness.level]}`}>{v.robustness.label}</span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Lodging() {
  const { view, lodgingProgress, act, busy } = usePlanning()
  if (!view) return null
  const status = view.lodging.status
  const candidates = status === 'pending' && lodgingProgress ? lodgingProgress.candidates : view.lodging.candidates
  const chosen = view.state.lodging_id
  return (
    <section className="ucard plan-side">
      <h2 className="utitle">Chỗ nghỉ đêm</h2>
      {status === 'pending' && <p className="hint">Đang tra giá chỗ bạn đã nhập…</p>}
      {status === 'unavailable' && <p className="hint">Chưa tra được chỗ ở, lịch dùng điểm xuất phát làm neo.</p>}
      {candidates.length === 0 && status === 'ready' && <p className="hint">Bạn chưa nhập chỗ ở. Lịch tính từ điểm bạn tới Đà Lạt.</p>}
      <ul className="lodging">
        {candidates.map((c) => (
          <li key={c.id}>
            <button className={chosen === c.id ? 'is-on' : ''} aria-pressed={chosen === c.id} disabled={busy} onClick={() => act({ type: 'pick_lodging', id: c.id })}>
              <b>{c.name}</b>
              <span className="mono">{c.price_vnd ? `${c.price_vnd.toLocaleString('vi-VN')} đ/đêm` : 'chưa có giá'}</span>
              <Icon name="next" size={15} />
            </button>
          </li>
        ))}
      </ul>
      <p className="source">Đổi chỗ nghỉ thì giờ di chuyển được tính lại.</p>
    </section>
  )
}

function Backups({ items }: { items: Record<string, unknown>[] }) {
  return (
    <section className="ucard plan-side">
      <h2 className="utitle">Phương án dự phòng</h2>
      {items.length ? (
        <ul className="backups">
          {items.map((b, i) => (
            <li key={i}>
              <b>{b.reason ? String(b.reason) : `Ngày ${String(b.day)}`}:</b> {b.name ? `thay bằng ${String(b.name)}` : 'có nơi thay thế'}
              {b.for ? <small> · cho {String(b.for)}</small> : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="hint">Chưa có nơi dự phòng gắn với lịch này.</p>
      )}
      <p className="source">Chỉ thay khi bạn chọn.</p>
    </section>
  )
}

function Stop({ it, n, vehicle }: { it: ItineraryItem; n: number; vehicle: string }) {
  if (it.kind === 'travel')
    return (
      <li className="tl__leg">
        <Icon name="route" size={14} /> đi {toMin(it.end) - toMin(it.start)} phút{vehicle ? ` · ${vehicle.toLowerCase()}` : ''}
      </li>
    )
  const dur = toMin(it.end) - toMin(it.start)
  const visit = it.kind === 'visit' && it.place_id
  return (
    <li className={`tl__item${visit ? '' : ' tl__item--soft'}`}>
      <span className="tl__n">{n}</span>
      <div className="tl__card">
        <div className="tl__text">
          <p className="tl__head">
            <span className="mono">{fmtTime(toMin(it.start))}</span>
            {visit ? (
              <button className="tl__name" onClick={() => navigate(`/app/place/${encodeURIComponent(it.place_id!)}`)}>
                {it.name}
              </button>
            ) : (
              <span className="tl__name">{it.name ?? itemLabel(it.kind)}</span>
            )}
            <span className="mono">{dur} phút</span>
          </p>
          {!visit && <p className="tl__note">{ITEM_NOTE[it.kind] ?? ''}</p>}
          {/* Notes are sentences for the user; bare codes (e.g. 'meal') are the planner's own bookkeeping. */}
          {it.note && it.note.includes(' ') && (
            <p className="tl__flag">
              <Icon name="alert" size={14} /> {it.note}
            </p>
          )}
        </div>
        {visit && (
          <div className="tl__img">
            <PlaceCover id={it.place_id!} fallback={<LineArt variant="spot" seed={n} />} />
          </div>
        )}
      </div>
    </li>
  )
}

const ADVISORY_KIND: Record<string, string> = {
  storm: 'bão / dông', flood: 'ngập lụt', landslide: 'sạt lở', fire: 'cháy', road_closed: 'đường bị chặn', other: 'khác',
}

// Facts about the date, from live sources and hand-entered notices; an empty list means none known, not "all clear".
function ConditionNote({ c, tips }: { c: DayConditions; tips: CrowdTip[] }) {
  const notes: string[] = []
  if (c.weather !== 'none') {
    const what = [c.storm ? 'dông' : '', c.rain_mm ? `mưa ~${Math.round(c.rain_mm)} mm` : '', c.gust_kmh ? `gió giật ~${Math.round(c.gust_kmh)} km/h` : ''].filter(Boolean).join(', ')
    notes.push(`${c.weather === 'severe' ? 'Thời tiết rất xấu' : 'Mưa lớn hoặc dông'}${what ? ` (${what})` : ''}`)
  }
  for (const a of c.advisories) notes.push(`Thông báo ${ADVISORY_KIND[a.kind] ?? a.kind}: ${a.note || 'xem nguồn'} (${a.source})`)
  if (c.crowd !== 'normal') notes.push(`${c.crowd === 'peak' ? 'Rất đông' : 'Đông hơn thường'}: ${c.crowd_reasons.join(', ')}`)
  if (c.closure_risk) notes.push(`Dịp ${c.closure_risk}: nhiều quán đóng cửa hoặc đổi giờ, gọi xác nhận trước`)
  if (!notes.length) return null
  return (
    <ul className="plan-cond" aria-label="Điều kiện của ngày này">
      {notes.map((n) => <li key={n} data-tone={c.weather === 'severe' || c.advisories.length ? 'warn' : 'info'}>{n}</li>)}
      {c.crowd !== 'normal' && tips.map((t) => <li key={t.place_id} data-tone="info">{t.text}</li>)}
    </ul>
  )
}

function DayView({ day, vehicle }: { day: ItineraryDay; vehicle: string }) {
  const list = useRef<HTMLOListElement>(null)
  useLayoutEffect(() => {
    if (story.reducedMotion || !list.current) return
    const ctx = gsap.context(() => {
      gsap.from('.tl__item', { opacity: 0, y: 12, duration: 0.45, stagger: 0.07, ease: 'power2.out' })
    }, list)
    return () => ctx.revert()
  }, [day])
  let n = 0
  return (
    <ol className="tl" ref={list}>
      {day.items.map((it, i) => (
        <Stop key={i} it={it} n={it.kind === 'travel' ? 0 : ++n} vehicle={vehicle} />
      ))}
    </ol>
  )
}

function TurnBar({ busy, diffText, onConfirm }: { busy: boolean; diffText: string; onConfirm: () => void }) {
  return (
    <div className="plan-bar">
      {diffText ? <p className="plan-bar__diff" aria-live="polite">{diffText}</p> : <span />}
      <button className="btn" disabled={busy} onClick={onConfirm}>
        Chốt kế hoạch này
      </button>
    </div>
  )
}

export function Itinerary() {
  const { trip, dispatch } = useTrip()
  const { view, diff, error, busy, act, confirm: confirmPlan } = usePlanning()
  const back = async (path: string) => {
    if (!trip.planningId) { navigate(path); return }
    await enterStage(trip.planningId, 'decision')
    dispatch({ type: 'set', patch: { planningId: null } })
    navigate(path)
  }
  const [dayIdx, setDayIdx] = useState(0)

  const variant = useMemo(() => view?.variants.find((v) => v.id === view.state.chosen_variant) ?? null, [view])
  const days = view?.itinerary ?? variant?.itinerary ?? []
  const vehicle = trip.vehicle ? VEHICLE_LABEL[trip.vehicle] : ''

  if (!trip.planningId)
    return (
      <Page className="page--narrow">
        <div className="empty">
          <LineArt variant="spot" />
          <p>Chưa có lịch trình. Xác nhận khả thi trước đã.</p>
          <button className="btn" onClick={() => back('/app/feasibility')}>
            Kiểm tra khả thi
          </button>
        </div>
      </Page>
    )

  if (!view) return <div className={`loading${error ? ' loading--error' : ''}`}>{error ?? 'Đang xếp lịch'}</div>

  // No schedule could be laid out from the confirmed places: say so, with a way back.
  if (!view.variants.length)
    return (
      <Page className="page--narrow">
        <header className="uhead">
          <h1>Chưa xếp được lịch</h1>
          <p>Các nơi đã chọn chưa đủ để xếp thành lịch trình. Quay lại chọn lại địa điểm nhé.</p>
        </header>
        {view.back_to_decision && view.back_to_decision.places.length > 0 && (
          <p className="notice">
            <Icon name="alert" size={16} /> Vướng ở: {view.back_to_decision.places.map((id) => placeById(id)?.name ?? id).join(', ')}. Bỏ hoặc đổi nơi này rồi kiểm tra lại.
          </p>
        )}
        {view.warnings.length > 0 && (
          <ul className="checks ucard">
            {view.warnings.map((w, i) => (
              <li key={i}>
                <Icon name="alert" size={16} /> {w.text}
              </li>
            ))}
          </ul>
        )}
        <div className="pfoot">
          <span />
          <button className="btn" onClick={() => back('/app/shortlist')}>
            Chọn lại địa điểm
          </button>
        </div>
      </Page>
    )

  if (!view.state.chosen_variant)
    return (
      <Page className="page--mid">
        <header className="uhead">
          <h1>Chọn một phương án</h1>
          <p>Mỗi phương án tối ưu một mục tiêu khác nhau. Giờ giấc và đường đi là ước tính.</p>
        </header>
        <VariantTabs variants={view.variants} chosen={null} onPick={(id) => act({ type: 'pick_variant', id })} />
        <Trade variants={view.variants} chosen={null} />
      </Page>
    )

  const d = days[dayIdx]
  const load = view.travel_load?.[dayIdx]
  const stops = (d?.items ?? [])
    .filter((it) => it.kind === 'visit' && it.place_id)
    .map((it) => placeById(it.place_id!))
    .filter((p): p is NonNullable<typeof p> => !!p)
  const places = days.reduce((n, x) => n + x.items.filter((it) => it.kind === 'visit').length, 0)

  const onConfirm = async () => {
    const out = await confirmPlan()
    if (out) navigate('/app/feedback')
  }

  return (
    <Page className="plan-page">
      <header className="plan-head">
        <div className="uhead">
          <h1>Lịch trình</h1>
          <p>Giờ giấc và đường đi là ước tính.</p>
        </div>
        <VariantTabs variants={view.variants} chosen={view.state.chosen_variant} onPick={(id) => act({ type: 'pick_variant', id })} />
      </header>

      <div className="plan-sum ucard">
        <div>
          <span>Di chuyển</span>
          <b className="mono">≈{fmtDuration(variant?.metrics.travel_min ?? 0)}</b>
        </div>
        <div>
          <span>Số nơi</span>
          <b className="mono">{places}</b>
        </div>
        <div>
          <span>Chi phí</span>
          <b className={`mono${variant?.metrics.cost_unknown ? ' unsure' : ''}`}>{variant ? costText(variant) : '—'}</b>
        </div>
        {variant && (
          <div>
            <span>Độ vững</span>
            <b>
              <span className={`robust robust--${ROBUST[variant.robustness.level]}`} title={variant.robustness.reasons.join(' ')}>
                {variant.robustness.label}
              </span>
            </b>
          </div>
        )}
      </div>
      {variant && variant.robustness.reasons[0] && <p className="hint plan-why">{variant.robustness.reasons[0]}</p>}

      <details className="plan-trade">
        <summary>So các phương án</summary>
        <Trade variants={view.variants} chosen={view.state.chosen_variant} />
      </details>

      <div className="plan-grid">
        <section className="plan-day">
          <div className="dtabs" role="tablist" aria-label="Ngày">
            {days.map((x, i) => (
              <button
                key={x.day}
                role="tab"
                aria-selected={dayIdx === i}
                className={dayIdx === i ? 'is-on' : ''}
                onClick={() => setDayIdx(i)}
                onKeyDown={(e) => {
                  if (e.key === 'ArrowRight' && i < days.length - 1) setDayIdx(i + 1)
                  if (e.key === 'ArrowLeft' && i > 0) setDayIdx(i - 1)
                }}
              >
                <b>Ngày {x.day}</b>
                {x.date && <small>{new Date(x.date).toLocaleDateString('vi-VN', { weekday: 'short', day: 'numeric', month: 'numeric' })}</small>}
                {view.travel_load?.[i] && <span className="mono">≈{fmtDuration(view.travel_load[i].travel_min)} đi</span>}
              </button>
            ))}
          </div>
          {view.day_conditions?.[dayIdx] && <ConditionNote c={view.day_conditions[dayIdx]} tips={view.crowd_tips ?? []} />}
          {d && <DayView day={d} vehicle={vehicle} />}
        </section>

        <section className="plan-map">
          {stops.length ? <GoogleMap src={mapsRouteEmbed(stops)} title={`Lộ trình ngày ${d?.day}`} height={560} /> : <div className="gmap plan-map__none">Chưa có điểm nào để vẽ đường.</div>}
          <p className="mono plan-map__foot">
            Di chuyển ≈{fmtDuration(load?.travel_min ?? 0)}
            {stops.length > 1 && (
              <a className="link" href={mapsRouteLink(stops)} target="_blank" rel="noreferrer">
                Mở đường đi trên Google Maps
              </a>
            )}
          </p>
        </section>

        <aside className="plan-aside">
          <Lodging />
          <Backups items={(variant?.backups ?? []) as Record<string, unknown>[]} />
          {view.warnings.length > 0 && (
            <section className="ucard plan-side">
              <h2 className="utitle">Lưu ý cả chuyến</h2>
              <ul className="checks">
                {view.warnings.map((w, i) => (
                  <li key={i}>
                    <Icon name="alert" size={15} /> {w.text}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </aside>
      </div>

      {error && (
        <p className="notice notice--bad">
          <Icon name="alert" size={16} /> {error}
        </p>
      )}
      <button className="link" disabled={busy} onClick={() => back('/app/shortlist')}>
        + Thêm nơi
      </button>
      <button className="link plan-back" onClick={() => back('/app/feasibility')}>
        Quay lại kiểm tra
      </button>
      <TurnBar busy={busy} diffText={diff ? SCOPE_TEXT[diff.scope] : ''} onConfirm={onConfirm} />
    </Page>
  )
}
