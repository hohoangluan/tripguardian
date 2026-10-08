import * as Dialog from '@radix-ui/react-dialog'
import { useMemo, useState } from 'react'
import { mapsRouteEmbed, mapsRouteLink, VEHICLE_LABEL } from '../../data/store'
import { enterStage } from '../journey'
import { dayLabel, fmtMin, fmtVnd, info, toMin } from '../lib'
import { usePlanning } from '../planning/planning'
import type { Backups, CrowdTip, DayConditions, Diff, ItineraryDay, ItineraryItem, Variant } from '../planning/types'
import { setOptimized, useUi } from '../store'
import { useTrip } from '../trip'
import { ArtRoute, Busy, Empty, go, Hint, Link, placeHref, PlacePhoto } from '../ui/common'
import { CountUp } from '../ui/CountUp'
import { Icon } from '../ui/icons'
import { RouteStory } from '../ui/RouteStory'
import { FlowBar, Page, useTitle } from '../ui/Shell'
import { lodgingAsked, LodgingPick } from './Lodging'

// docs/UI_SPEC_USER_WEB.md Trang 8. Times and routes are estimates and say so; warnings sit on the stop they concern.
// Lịch trình takes actions only (no chat): docs/PLANNING.md.

const SCOPE_TEXT: Record<Diff['scope'], string> = {
  none: '',
  relayout: 'Đã xếp lại một vài ngày bị ảnh hưởng',
  variant: 'Đã xếp lại cả chuyến theo thay đổi này',
  lodging_home: 'Đã đổi chỗ nghỉ, giờ di chuyển được tính lại',
  lodging_fetch: 'Đã tìm lại danh sách chỗ ở',
}
const ROBUST_CLS: Record<string, string> = { solid: 'hi', feasible: 'mid', fragile: 'lo' }
const COVER: Record<string, string> = { least_travel: 'journey-travel', low_cost: 'journey-budget', diverse: 'journey-experience', preference_fit: 'journey-experience', weather_robust: 'dusk' }
const BLOCK: Record<string, string> = { meal_free: 'Ăn (tự chọn)', rest: 'Nghỉ', wait: 'Chờ', buffer: 'Đệm' }
const BLOCK_NOTE: Record<string, string> = { meal_free: 'Ăn ở khu gần đó, mình không chọn quán thay bạn.', rest: 'Nghỉ chân, về chỗ ở hoặc ngồi lại.', wait: 'Chờ nơi tiếp theo mở cửa.', buffer: 'Thời gian dự phòng, trễ một chút vẫn ổn.' }
const ADVISORY: Record<string, string> = { storm: 'bão / dông', flood: 'ngập lụt', landslide: 'sạt lở', fire: 'cháy', road_closed: 'đường bị chặn', other: 'khác' }

const costText = (v: Variant) => (v.metrics.cost_vnd ? `~${fmtVnd(v.metrics.cost_vnd)}` : 'Chưa có giá')
const visits = (d: ItineraryDay) => d.items.filter((it) => it.kind === 'visit' && it.place_id)

export function Plan() {
  useTitle('Lịch trình')
  const { trip, dispatch } = useTrip()
  const { view, diff, error, busy, act, confirm, optimize } = usePlanning()
  const optimized = useUi((u) => (trip.planningId ? u.optimized[trip.planningId] : undefined))
  const [picked, setDayIdx] = useState<number | null>(null) // null: the first day that has a stop
  const [hot, setHot] = useState<string | null>(null)
  const [opt, setOpt] = useState(false)
  const [table, setTable] = useState(false)
  const [mode, setMode] = useState<'list' | 'route'>('list')
  const [rday, setRday] = useState<number | 'all'>('all')
  const [lodDone, setLodDone] = useState(false)
  const variant = useMemo(() => view?.variants.find((v) => v.id === view.state.chosen_variant) ?? null, [view])
  const back = async (to: string) => {
    if (trip.planningId) {
      try {
        await enterStage(trip.planningId, 'decision')
        dispatch({ type: 'set', patch: { planningId: null } })
      } catch { /* Chọn nơi shows the connection error itself */ }
    }
    go(to)
  }

  if (!trip.planningId)
    return (
      <>
        <FlowBar step="plan" />
        <Page narrow><Empty art={<ArtRoute />} title="Chưa có lịch trình" body="Chọn vài nơi rồi bấm Xem lịch trình, mình xếp lịch ngay." action={<button type="button" className="tg-btn tg-btn--primary" onClick={() => go('/explore')}>Lựa chọn</button>} /></Page>
      </>
    )
  if (!view)
    return (
      <>
        <FlowBar step="plan" />
        <Page>
          {error ? <Empty art={<ArtRoute />} title="Chưa tải được lịch trình" body={error} action={<button type="button" className="tg-btn tg-btn--primary" onClick={() => location.reload()}><Icon name="refresh" size={18} /> Thử lại</button>} /> : (
            <>
              <Busy text="Đang xếp lịch… chỗ nghỉ có thể đến sau ~10 giây" />
              <div className="tg-plan__cols" aria-busy="true">
                <div className="tg-skel-col">{Array.from({ length: 4 }, (_, i) => <span key={i} className="tg-skel" style={{ height: 88 }} />)}</div>
                <span className="tg-skel" style={{ height: 460, borderRadius: 18 }} />
                <div className="tg-skel-col">{Array.from({ length: 3 }, (_, i) => <span key={i} className="tg-skel" style={{ height: 120 }} />)}</div>
              </div>
            </>
          )}
        </Page>
      </>
    )

  if (!view.variants.length)
    return (
      <>
        <FlowBar step="plan" />
        <Page narrow>
          <Empty art={<ArtRoute />} title="Chưa xếp được lịch" body={view.back_to_decision?.places.length ? `Vướng ở: ${view.back_to_decision.places.map((id) => info(id)?.name ?? id).join(', ')}. Bỏ hoặc đổi nơi này rồi xem lại.` : 'Các nơi đã chọn chưa đủ để xếp thành lịch trình.'} action={<button type="button" className="tg-btn tg-btn--primary" onClick={() => back('/explore')}>Chọn lại địa điểm</button>} />
          {view.warnings.length > 0 && <ul className="tg-notes">{view.warnings.map((w, i) => <li key={i}><Icon name="warn" size={14} /><span>{w.text}</span></li>)}</ul>}
        </Page>
      </>
    )

  // No lodging yet ("Chưa có, gợi ý giúp mình"): "Bạn ở đâu?" comes once, before the schedule.
  if (trip.searchInput?.context.lodging_booked === 'no' && !view.state.lodging_touched && !lodDone && !lodgingAsked(trip.planningId))
    return <LodgingPick planningId={trip.planningId} onDone={() => setLodDone(true)} />
  if (!view.state.chosen_variant) return <Choose variants={view.variants} busy={busy} onPick={(id) => act({ type: 'pick_variant', id })} />

  const days = view.itinerary ?? variant?.itinerary ?? []
  const dayIdx = picked ?? Math.max(0, days.findIndex((x) => visits(x).length > 0))
  const d = days[Math.min(dayIdx, days.length - 1)]
  const places = days.reduce((n, x) => n + visits(x).length, 0)
  const travel = view.travel_load ? view.travel_load.reduce((n, x) => n + x.travel_min, 0) : variant?.metrics.travel_min ?? 0
  const vehicle = trip.vehicle ? VEHICLE_LABEL[trip.vehicle].toLowerCase() : ''
  const lodgingName = view.lodging.candidates.find((c) => c.id === view.state.lodging_id)?.name ?? ((view.state.lodging_point?.text as string | undefined) || null)
  const better = optimized?.status === 'accepted' && optimized.after < optimized.before
  const onConfirm = async () => { if (await confirm()) go('/done') }
  return (
    <>
      <FlowBar step="plan" />
      <Page className="tg-plan">
        <header className="tg-plan__head">
          <div><p className="tg-kicker">Bước 3 · Lịch trình</p><h1>Đà Lạt {days.length} ngày</h1><p className="tg-muted">Giờ giấc và đường đi là ước tính.</p></div>
          <div className="tg-plan__tabs" role="tablist" aria-label="Hành trình">
            {view.variants.map((v) => <button key={v.id} type="button" role="tab" aria-selected={view.state.chosen_variant === v.id} className="tg-tab" disabled={busy} onClick={() => { act({ type: 'pick_variant', id: v.id }); setDayIdx(null) }}>{v.label}</button>)}
          </div>
        </header>

        {better && !optimized.seen && (
          <div className="tg-opt-banner" role="status"><Icon name="sparkle" size={20} /><div><b>Mình đã tìm được cách xếp tốt hơn</b><span>Giảm khoảng {fmtMin(optimized.before - optimized.after)} di chuyển mà không đổi chỗ ở, nhịp độ hay nơi đã khóa.</span></div><button type="button" className="tg-btn tg-btn--primary tg-btn--sm" onClick={() => setOpt(true)}>Xem đề xuất</button></div>
        )}
        <div className={`tg-sumstrip ${diff && diff.scope !== 'none' ? 'tg-flash' : ''}`}>
          <div><span>Di chuyển</span><b className="tg-mono">≈ {fmtMin(travel)}</b></div>
          <div><span>Số nơi</span><b className="tg-mono">{places}</b></div>
          <div><span>Chi phí</span><b className="tg-mono">{variant ? costText(variant) : '—'}</b>{variant && variant.metrics.cost_unknown > 0 && <small>một phần chưa có giá</small>}</div>
          {variant && <div><span>Độ vững</span><Hint label={variant.robustness.reasons.join(' ') || variant.robustness.label}><b className={`tg-robust is-${ROBUST_CLS[variant.robustness.level]}`}>{variant.robustness.label} <Icon name="info" size={14} /></b></Hint></div>}
          <button type="button" className="tg-btn tg-btn--ghost tg-btn--sm" disabled={busy} onClick={async () => { await optimize(); setOpt(true) }}><Icon name="sparkle" size={16} /> {busy ? 'Đang thử…' : 'Tối ưu lịch'}</button>
        </div>
        {view.variants.length > 1 && <button type="button" className="tg-link tg-plan__tbl" aria-expanded={table} onClick={() => setTable((v) => !v)}>{table ? 'Ẩn' : 'So sánh'} {view.variants.length} hành trình</button>}
        {table && <Tradeoff variants={view.variants} active={view.state.chosen_variant} onPick={(id) => act({ type: 'pick_variant', id })} />}

        <div className="tg-plan__viewbar">
          <div className="tg-seg" role="group" aria-label="Cách xem lịch trình"><button type="button" aria-pressed={mode === 'list'} onClick={() => setMode('list')}><Icon name="clock" size={15} /> Theo giờ</button><button type="button" aria-pressed={mode === 'route'} onClick={() => setMode('route')}><Icon name="route" size={15} /> Hành trình</button></div>
          {mode === 'route' && <div className="tg-seg" role="group" aria-label="Phạm vi">{[...days.map((_, i) => i as number | 'all'), 'all' as const].map((k) => <button key={String(k)} type="button" aria-pressed={rday === k} onClick={() => setRday(k)}>{k === 'all' ? 'Cả chuyến' : `Ngày ${k + 1}`}</button>)}</div>}
        </div>
        {mode === 'route' && <div className="tg-rswrap"><RouteStory days={days} day={rday} home={lodgingName ?? 'Điểm xuất phát'} hot={hot} setHot={setHot} /></div>}
        <div className="tg-plan__cols" hidden={mode === 'route'}>
          <section aria-label="Ngày" className="tg-days">
            <div className="tg-daytabs" role="tablist" aria-label="Ngày" onKeyDown={(e) => { if (e.key === 'ArrowRight') setDayIdx((dayIdx + 1) % days.length); if (e.key === 'ArrowLeft') setDayIdx((dayIdx + days.length - 1) % days.length) }}>
              {days.map((x, i) => {
                const l = dayLabel(x.date)
                const load = view.travel_load?.[i]
                return <button key={x.day} type="button" role="tab" aria-selected={d?.day === x.day} tabIndex={d?.day === x.day ? 0 : -1} className="tg-daytab" onClick={() => setDayIdx(i)}><b>Ngày {x.day}</b><span>{l ? `${l.wd} · ${l.dm}` : x.weekday || 'Chưa có ngày'}</span>{load && <em className="tg-mono">≈{fmtMin(load.travel_min)} đi</em>}</button>
              })}
            </div>
            {d && <DayBlock d={d} cond={view.day_conditions?.find((c) => c.day === d.day)} tips={view.crowd_tips ?? []} vehicle={vehicle} hot={hot} setHot={setHot} />}
            <div className="tg-plan__links"><button type="button" className="tg-link" disabled={busy} onClick={() => back('/explore')}><Icon name="plus" size={14} /> Thêm nơi</button><button type="button" className="tg-link tg-link--quiet" onClick={() => back('/explore')}>Quay lại chọn nơi</button></div>
          </section>
          <section aria-label="Bản đồ" className="tg-plan__map"><DayMap d={d} /></section>
          <aside aria-label="Chỗ nghỉ và dự phòng" className="tg-side">
            <Lodging />
            <BackupCard b={variant?.backups} day={d?.day ?? 1} busy={busy} onSwap={(place, w) => act({ type: 'swap', place, with: w })} />
            <section className="tg-sidecard" aria-labelledby="tg-nt-h">
              <h2 id="tg-nt-h"><Icon name="info" size={18} /> Lưu ý cả chuyến</h2>
              {view.warnings.length === 0 && !(variant?.warnings.length) ? <p className="tg-faint">Chưa có lưu ý nào.</p> : <ul className="tg-notes">{[...view.warnings, ...(variant?.warnings ?? [])].slice(0, 6).map((w, i) => <li key={i}><Icon name="warn" size={14} /><span>{w.text}</span></li>)}</ul>}
            </section>
          </aside>
        </div>
      </Page>
      <div className="tg-confirm">
        <div className="tg-confirm__in">
          {error ? <p className="tg-diff is-bad" role="alert"><Icon name="warn" size={15} />{error}</p> : diff && SCOPE_TEXT[diff.scope] ? <p className="tg-diff" role="status"><Icon name="bolt" size={15} />{SCOPE_TEXT[diff.scope]}<button type="button" className="tg-diff__undo" disabled={busy} onClick={() => act({ type: 'undo' })}>Hoàn tác</button></p> : <span className="tg-faint">Chưa chốt thì mình chưa lưu gì thành "đã chốt".</span>}
          <button type="button" className="tg-btn tg-btn--primary" disabled={busy} onClick={onConfirm}>Chốt kế hoạch này <Icon name="arrow" size={18} /></button>
        </div>
      </div>
      <Optimize open={opt} onClose={() => { setOpt(false); if (trip.planningId && optimized) setOptimized(trip.planningId, { ...optimized, seen: true }) }} onUndo={async () => { await act({ type: 'undo' }); if (trip.planningId) setOptimized(trip.planningId, null); setOpt(false) }} busy={busy} />
    </>
  )
}

function Choose({ variants, busy, onPick }: { variants: Variant[]; busy: boolean; onPick: (id: string) => void }) {
  const [hover, setHover] = useState<string | null>(null)
  const places = variants[0]?.itinerary.reduce((n, d) => n + visits(d).length, 0) ?? 0
  return (
    <>
      <FlowBar step="plan" />
      <Page className="tg-plan">
        <header className="tg-xhead"><div><p className="tg-kicker">Bước 3 · Lịch trình</p><h1>Chọn một hành trình</h1><p>Cùng {places} nơi bạn đã chọn, {variants.length} cách đi, mỗi cách tối ưu một mục tiêu khác. Chọn xong vẫn đổi được.</p></div></header>
        <div className="tg-journeys">
          {variants.map((v) => (
            <button key={v.id} type="button" disabled={busy} className={`tg-journey ${hover === v.id ? 'is-hover' : ''}`} style={{ backgroundImage: `linear-gradient(180deg, rgba(10,24,26,.05), rgba(10,24,26,.78)), url(/img/gen/${COVER[v.objective] ?? 'journey-travel'}.webp)` }} onClick={() => onPick(v.id)} onMouseEnter={() => setHover(v.id)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(v.id)} onBlur={() => setHover(null)}>
              <span className="tg-journey__top"><span className="tg-tag tg-tag--dark">{v.robustness.label}</span></span>
              <span className="tg-journey__txt">
                <b>{v.label}</b><em>{v.robustness.reasons[0] ?? ''}</em>
                <span className="tg-journey__stats"><span><Icon name="calendar" size={15} /> {v.itinerary.length} ngày</span><span><Icon name="pin" size={15} /> {v.itinerary.reduce((n, d) => n + visits(d).length, 0)} nơi</span><span><Icon name="route" size={15} /> ≈{fmtMin(v.metrics.travel_min)} đi</span></span>
                <span className="tg-journey__prev" aria-hidden={hover !== v.id}>{v.itinerary.map((d) => <span key={d.day}><i>Ngày {d.day}</i>{visits(d).map((x) => x.name).join(' → ') || '—'}</span>)}</span>
                <span className="tg-journey__go">{costText(v)} <Icon name="arrow" size={16} /></span>
              </span>
            </button>
          ))}
        </div>
        <Tradeoff variants={variants} active={null} onPick={onPick} />
      </Page>
    </>
  )
}

function Tradeoff({ variants, active, onPick }: { variants: Variant[]; active: string | null; onPick: (id: string) => void }) {
  if (variants.length < 2) return null
  const minT = Math.min(...variants.map((v) => v.metrics.travel_min))
  const priced = variants.filter((v) => v.metrics.cost_vnd > 0)
  const minC = priced.length ? Math.min(...priced.map((v) => v.metrics.cost_vnd)) : -1
  const rows: [string, (v: Variant) => string, (v: Variant) => boolean][] = [
    ['Di chuyển', (v) => `≈ ${fmtMin(v.metrics.travel_min)}`, (v) => v.metrics.travel_min === minT],
    ['Số nơi mỗi ngày', (v) => v.itinerary.map((d) => visits(d).length).join(' · '), () => false],
    ['Chi phí', (v) => `${costText(v)}${v.metrics.cost_unknown ? ' *' : ''}`, (v) => v.metrics.cost_vnd === minC],
    ['Dính mưa', (v) => (v.metrics.rain_exposed ? `${v.metrics.rain_exposed} nơi ngoài trời` : 'Không'), (v) => v.metrics.rain_exposed === 0],
    ['Độ vững', (v) => v.robustness.label, (v) => v.robustness.level === 'solid'],
  ]
  return (
    <div className="tg-trade" role="table" aria-label="Đánh đổi giữa các hành trình">
      <div role="row" className="tg-trade__r tg-trade__h"><span role="columnheader" /> {variants.map((v) => <button key={v.id} role="columnheader" type="button" className={active === v.id ? 'is-on' : ''} onClick={() => onPick(v.id)}>{v.label}</button>)}</div>
      {rows.map(([label, f, best]) => (
        <div role="row" className="tg-trade__r" key={label}><span role="rowheader">{label}</span>{variants.map((v) => <span role="cell" key={v.id} className={best(v) ? 'is-best' : ''}>{f(v)}</span>)}</div>
      ))}
      <p className="tg-faint tg-trade__note">* Một phần chưa có giá. Giờ giấc và đường đi là ước tính.</p>
    </div>
  )
}

// Facts about the date, from live sources and hand-entered notices; no notice is not the same as "all clear".
function Conditions({ c, tips }: { c: DayConditions | undefined; tips: CrowdTip[] }) {
  const items: { icon: 'rain' | 'cloud' | 'users' | 'calendar' | 'warn' | 'info' | 'clock'; text: string; warn: boolean }[] = []
  if (c) {
    if (c.weather !== 'none') {
      const what = [c.storm ? 'dông' : '', c.rain_mm ? `mưa ~${Math.round(c.rain_mm)} mm` : '', c.gust_kmh ? `gió giật ~${Math.round(c.gust_kmh)} km/h` : ''].filter(Boolean).join(', ')
      items.push({ icon: 'rain', text: `${c.weather === 'severe' ? 'Thời tiết rất xấu' : 'Mưa lớn hoặc dông'}${what ? ` (${what})` : ''}`, warn: true })
    } else items.push({ icon: 'cloud', text: c.rain_mm === null ? 'Chưa có số liệu thời tiết cho ngày này' : 'Dự báo không có mưa lớn', warn: false })
    for (const a of c.advisories) items.push({ icon: 'warn', text: `Thông báo ${ADVISORY[a.kind] ?? a.kind}: ${a.note || 'xem nguồn'} (${a.source})`, warn: true })
    if (c.crowd !== 'normal') items.push({ icon: 'users', text: `${c.crowd === 'peak' ? 'Rất đông' : 'Đông hơn thường'}: ${c.crowd_reasons.join(', ')}`, warn: true })
    if (c.day_type !== 'weekday') items.push({ icon: 'calendar', text: c.day_type === 'holiday' ? 'Ngày lễ' : 'Cuối tuần', warn: c.day_type === 'holiday' })
    if (c.closure_risk) items.push({ icon: 'warn', text: `Dịp ${c.closure_risk}: nhiều quán đóng cửa hoặc đổi giờ, gọi xác nhận trước`, warn: true })
    if (c.crowd !== 'normal') tips.slice(0, 2).forEach((t) => items.push({ icon: 'clock', text: t.text, warn: false }))
  }
  if (!c || (!c.advisories.length && c.crowd === 'normal' && !c.closure_risk)) items.push({ icon: 'info', text: 'Chưa có thông báo hay sự kiện ghi nhận cho ngày này (không có nghĩa là chắc chắn bình thường).', warn: false })
  return <ul className="tg-cond" aria-label="Điều kiện ngày">{items.map((x) => <li key={x.text} className={x.warn ? 'is-warn' : ''}><Icon name={x.icon} size={16} />{x.text}</li>)}</ul>
}

function DayBlock({ d, cond, tips, vehicle, hot, setHot }: { d: ItineraryDay; cond: DayConditions | undefined; tips: CrowdTip[]; vehicle: string; hot: string | null; setHot: (v: string | null) => void }) {
  let n = 0
  let leg = 0
  const rows: { it: ItineraryItem; leg: number; n: number }[] = []
  for (const it of d.items) {
    if (it.kind === 'travel') { leg += toMin(it.end) - toMin(it.start); continue }
    rows.push({ it, leg, n: it.kind === 'visit' ? ++n : 0 })
    leg = 0
  }
  return (
    <div className="tg-day" key={d.day}>
      <div className="tg-day__top"><span className="tg-muted">{d.window[0]}–{d.window[1]}{d.method ? '' : ''}</span></div>
      <Conditions c={cond} tips={tips} />
      <ol className="tg-tl">
        {rows.map(({ it, leg: l, n: k }, i) => {
          const dur = toMin(it.end) - toMin(it.start)
          if (it.kind !== 'visit' || !it.place_id)
            return <li key={i} className="tg-tl__blk" style={{ ['--i' as string]: i }}><time className="tg-mono">{it.start}</time><div><Icon name={it.kind === 'meal_free' ? 'utensils' : it.kind === 'wait' ? 'clock' : 'moon'} size={16} />{it.name ?? BLOCK[it.kind] ?? it.kind}<span className="tg-faint">{dur} phút · {BLOCK_NOTE[it.kind] ?? ''}</span></div></li>
          const p = info(it.place_id)
          return (
            <li key={i} className="tg-tl__stop" style={{ ['--i' as string]: i }} onMouseEnter={() => setHot(it.place_id!)} onMouseLeave={() => setHot(null)}>
              {l > 0 && <p className="tg-tl__leg"><Icon name="bike" size={15} />≈ {l} phút{vehicle ? ` ${vehicle}` : ''}</p>}
              <time className="tg-mono">{it.start}</time>
              <div className={`tg-stop ${hot === it.place_id ? 'is-hot' : ''}`}>
                <i className="tg-stop__n" aria-hidden="true">{k}</i>
                <PlacePhoto id={it.place_id} name={it.name} className="tg-stop__ph" />
                <div className="tg-stop__txt"><Link to={placeHref(it.place_id)} className="tg-stop__name">{it.name ?? p?.name}</Link><span className="tg-faint">{p?.area ? `${p.area} · ` : ''}ở lại ≈ <span className="tg-mono">{fmtMin(dur)}</span></span></div>
              </div>
              {it.note && it.note.includes(' ') && <p className="tg-tl__warn"><Icon name="warn" size={14} />{it.note}</p>}
            </li>
          )
        })}
        {n === 0 && <li className="tg-faint">Ngày này chưa có nơi nào. Thêm nơi ở bước Lựa chọn.</li>}
      </ol>
    </div>
  )
}

function DayMap({ d }: { d: ItineraryDay | undefined }) {
  const stops = (d ? visits(d) : []).map((it) => info(it.place_id!)).filter((p): p is NonNullable<typeof p> => !!p)
  return (
    <div className="tg-map">
      {stops.length ? <iframe className="tg-map__frame" title={`Lộ trình ngày ${d?.day}`} src={mapsRouteEmbed(stops)} loading="lazy" referrerPolicy="no-referrer-when-downgrade" /> : <div className="tg-map__none tg-faint">Chưa có điểm nào để vẽ đường.</div>}
      <div className="tg-map__foot"><span><Icon name="route" size={16} /> {stops.length} điểm dừng</span>{stops.length > 1 && <a href={mapsRouteLink(stops)} target="_blank" rel="noreferrer" className="tg-link">Mở trên Google Maps <Icon name="external" size={14} /></a>}</div>
      <p className="tg-map__note tg-faint">Bản đồ Google Maps. Đường đi và giờ giấc trong lịch là ước tính.</p>
    </div>
  )
}

function Lodging() {
  const { view, lodgingProgress, act, busy } = usePlanning()
  const [text, setText] = useState('')
  if (!view) return null
  const status = view.lodging.status
  const candidates = status === 'pending' && lodgingProgress ? lodgingProgress.candidates : view.lodging.candidates
  const chosen = view.state.lodging_id
  return (
    <section className="tg-sidecard" aria-labelledby="tg-lod-h">
      <h2 id="tg-lod-h"><Icon name="bed" size={18} /> Chỗ nghỉ đêm</h2>
      {status === 'pending' && <p className="tg-faint">Đang tra giá chỗ ở quanh lịch trình… có thể mất ~10 giây.</p>}
      {status === 'unavailable' && <p className="tg-faint">Chưa tra được chỗ ở, lịch dùng điểm xuất phát làm neo.</p>}
      {status === 'booked' && view.state.lodging_point && <p><b>{String(view.state.lodging_point.text ?? '')}</b><br /><small className="tg-faint">Chỗ bạn đã đặt, mọi ngày bắt đầu và kết thúc ở đây.</small></p>}
      {candidates.length > 0 && (
        <ul>
          {candidates.slice(0, 5).map((c) => (
            <li key={c.id}><label className={`tg-radio ${chosen === c.id ? 'is-on' : ''}`}>
              <input type="radio" name="lodging" checked={chosen === c.id} disabled={busy} onChange={() => act({ type: 'pick_lodging', id: c.id })} />
              <span><b>{c.name}</b><small className="tg-faint">{c.price_vnd ? `${fmtVnd(c.price_vnd)}/đêm` : 'Chưa có giá'}</small></span>
            </label></li>
          ))}
        </ul>
      )}
      <form className="tg-sidecard__lookup" onSubmit={(e) => { e.preventDefault(); if (text.trim()) { act({ type: 'set_lodging', text: text.trim() }); setText('') } }}>
        <label className="tg-sr" htmlFor="tg-lodging-in">Chỗ bạn ở</label>
        <input id="tg-lodging-in" className="tg-line-input" value={text} onChange={(e) => setText(e.target.value)} placeholder="Nhập chỗ bạn ở (tên hoặc địa chỉ)" />
        <button type="submit" className="tg-link" disabled={busy || !text.trim()}><Icon name="search" size={14} /> Dùng chỗ này</button>
      </form>
      <p className="tg-faint tg-sidecard__mini">Đổi chỗ nghỉ thì giờ di chuyển được tính lại. Giá là của Google Maps, chưa xác minh.</p>
    </section>
  )
}

// Backups of the day on screen: a stand-in for a place that may fail (rain, hours) and what to drop first when late.
function BackupCard({ b, day, busy, onSwap }: { b: Backups | undefined; day: number; busy: boolean; onSwap: (place: string, w: string) => void }) {
  const items = b?.places.filter((x) => x.day === day) ?? []
  const late = b?.on_delay.find((x) => x.day === day)
  return (
    <section className="tg-sidecard" aria-labelledby="tg-bk-h">
      <h2 id="tg-bk-h"><Icon name="shield" size={18} /> Phương án dự phòng · Ngày {day}</h2>
      {items.length === 0 && !late && <p className="tg-faint">Ngày này chưa có nơi nào cần dự phòng.</p>}
      {items.slice(0, 3).map((x) => (
        <div key={x.place_id} className="tg-backup">
          <b>{x.text ? `Nếu ${x.text.toLowerCase()}` : x.name}</b>
          <span>{x.name}{x.alternatives.length ? ' → ' : ''}{x.alternatives.length ? '' : ` · ${x.none_text ?? 'Không có phương án thay.'}`}</span>
          {x.alternatives.slice(0, 2).map((a) => <button key={a.id} type="button" className="tg-btn tg-btn--soft tg-btn--sm" disabled={busy} onClick={() => onSwap(x.place_id, a.id)}>Thay bằng {a.name}{a.minutes_rough ? ` (≈${a.minutes_rough}′)` : ''}</button>)}
        </div>
      ))}
      {late && <div className="tg-backup"><b>Bị trễ</b><span>Bỏ {late.name} trước, giữ phần còn lại</span></div>}
      <p className="tg-faint tg-sidecard__mini">Chỉ thay khi bạn bấm chọn.</p>
    </section>
  )
}

// The Planning Agent's proposal: kept by the server only when it passes the deterministic checks and is not worse.
function Optimize({ open, onClose, onUndo, busy }: { open: boolean; onClose: () => void; onUndo: () => void; busy: boolean }) {
  const { trip } = useTrip()
  const o = useUi((u) => (trip.planningId ? u.optimized[trip.planningId] : undefined))
  const better = o?.status === 'accepted' && o.after < o.before
  return (
    <Dialog.Root open={open} onOpenChange={(v) => !v && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="tg tg-overlay" />
        <Dialog.Content className="tg tg-drawer" aria-describedby={undefined}>
          <header><span className="tg-tag"><Icon name="sparkle" size={13} /> Đề xuất tối ưu</span><Dialog.Close className="tg-icon-btn" aria-label="Đóng"><Icon name="x" size={20} /></Dialog.Close></header>
          <Dialog.Title>{!o ? 'Đang thử xếp lại…' : better ? 'Mình xếp lại được tốt hơn' : o.status === 'accepted' ? 'Lịch hiện tại đã khá gọn' : 'Chưa áp dụng được đề xuất'}</Dialog.Title>
          {o && better && (
            <>
              <div className="tg-ba">
                <div><span>Trước</span><b className="tg-mono">{fmtMin(o.before)}</b><small>di chuyển</small></div>
                <Icon name="arrow" size={22} />
                <div className="is-after"><span>Sau</span><b><CountUp from={o.before} to={o.after} render={fmtMin} /></b><small>tiết kiệm {fmtMin(o.before - o.after)}</small></div>
              </div>
              <div className="tg-ba__why"><h3>Vì sao</h3><ul><li>Thứ tự trong ngày được xếp lại để bớt quay đầu giữa các khu.</li><li>Lịch mới đã qua kiểm tra giờ mở cửa, nơi đã khóa và giới hạn của bạn.</li><li>Điểm theo mục tiêu của hành trình này không kém lịch cũ.</li></ul><p className="tg-ba__keep"><Icon name="shield" size={15} /> Mình không đổi chỗ ở, nhịp độ, nơi đã khóa hay tập địa điểm.</p></div>
            </>
          )}
          {o && !better && <p className="tg-muted">{o.status === 'accepted' ? `Không có cách xếp nào giảm di chuyển đáng kể mà vẫn đúng giờ mở cửa. Giữ lịch hiện tại (${fmtMin(o.after)} di chuyển).` : 'Đề xuất chưa qua được kiểm tra (vướng nơi đã khóa, giờ mở cửa hoặc không tốt hơn), nên mình giữ lịch hiện tại.'}</p>}
          <footer>{better && <button type="button" className="tg-btn tg-btn--ghost" disabled={busy} onClick={onUndo}>Giữ lịch cũ</button>}<button type="button" className="tg-btn tg-btn--primary" onClick={onClose}>{better ? 'Giữ cách xếp mới' : 'Đóng'} <Icon name="check" size={18} /></button></footer>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
