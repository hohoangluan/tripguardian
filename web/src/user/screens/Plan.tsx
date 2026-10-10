import * as Dialog from '@radix-ui/react-dialog'
import { useEffect, useMemo, useState } from 'react'
import { enterStage } from '../journey'
import { blockerLines, fmtMin, info, toMin } from '../lib'
import { useDecision } from '../pd/decision'
import type { Card } from '../pd/types'
import { loadFits, type Fit } from '../planning/api'
import { usePlanning } from '../planning/planning'
import type { Diff, ItineraryDay, Variant, Warning } from '../planning/types'
import { alertsOf, RENTAL_NOTE, rentalStep, walkOnly, type Alert } from '../planning/view'
import { automaticVisitAction, moveVisitAction, reorderVisitAction, visitAction } from '../planning/visitEdit'
import { setOptimized, useUi } from '../store'
import { useTrip } from '../trip'
import { ArtRoute, Busy, Empty, go, Hint } from '../ui/common'
import { CountUp } from '../ui/CountUp'
import { Icon } from '../ui/icons'
import { PlanAlerts } from '../ui/PlanAlerts'
import { dragged, RouteStory } from '../ui/RouteStory'
import { FlowBar, Page, useTitle } from '../ui/Shell'
import { Tour, useTour, type TourStep } from '../ui/Tour'
import { costText, VariantCards } from '../ui/VariantCards'
import { lodgingAsked, LodgingPick, LodgingStrip } from './Lodging'
import { BackupCard, PlanDetail, SLOT } from './PlanDetail'

// docs/WEB.md Trang 8. Times and routes are estimates and say so; warnings sit on the stop they concern.
// Lịch trình takes actions only (no chat): docs/P4_PLANNING.md.

const SCOPE_TEXT: Record<Diff['scope'], string> = {
  none: '',
  relayout: 'Đã xếp lại một vài ngày bị ảnh hưởng',
  variant: 'Đã xếp lại cả chuyến theo thay đổi này',
  lodging_home: 'Đã đổi chỗ nghỉ, giờ di chuyển được tính lại',
  lodging_fetch: 'Đã tìm lại danh sách chỗ ở',
}
const ROBUST_CLS: Record<string, string> = { solid: 'hi', feasible: 'mid', fragile: 'lo' }
// Why the optimizer kept the plan, from the server's diagnostics (src/planning/engine.py recommend): never a guess.
const KEPT: [RegExp, string][] = [
  [/^objective_worse$/, 'Cách xếp mà trợ lý đề xuất không gọn hơn lịch hiện tại.'],
  [/^validation_failed$/, 'Cách xếp đề xuất vướng giờ mở cửa hoặc vượt khung giờ trong ngày.'],
  [/^protected_slot_changed$/, 'Cách xếp đề xuất làm lệch giờ của nơi cần giữ nguyên (nơi bạn khóa hoặc nơi phải đến).'],
  [/^membership_changed$/, 'Đề xuất thêm hoặc bớt nơi, việc đó để bạn tự quyết.'],
  [/^stale_fingerprint$/, 'Lịch vừa thay đổi trong lúc mình tính. Bạn bấm Tối ưu lịch lại nhé.'],
  [/^no_valid_baseline$/, 'Chưa có lịch hợp lệ để tối ưu.'],
  [/^proposal_unavailable$/, 'Trợ lý tối ưu chưa sẵn sàng lúc này.'],
]
const keptWhy = (diagnostics: string[]) => KEPT.find(([re]) => diagnostics.some((d) => re.test(d)))?.[1] ?? 'Trợ lý tối ưu chưa trả lời kịp hoặc trả lời chưa đúng cách.'
const visits = (d: ItineraryDay) => d.items.filter((it) => it.kind === 'visit' && it.place_id)

// How the reader had the screen (view, day) per journey, kept for the page's lifetime so another tab and back lands on the
// same view. Only a display choice: the plan itself comes from the cache in journey.ts.
const looks = new Map<string, { rday: number | 'all'; page: 'journey' | 'detail' }>()

// First visit: what the page lets the traveller do with the route, one thing at a time.
const TOUR: TourStep[] = [
  { anchor: '[data-tour="plan-route"]', side: 'top', title: 'Hành trình của bạn', body: 'Mỗi thẻ là một nơi, có giờ đến và giờ đi ước tính. Kéo một thẻ vào trước hoặc sau thẻ khác để đổi thứ tự (hoặc Alt + ← →); bấm hình đồng hồ để chỉnh giờ ở lại.' },
  { anchor: '[data-tour="plan-days"]', side: 'bottom', title: 'Chuyển sang ngày khác', body: 'Kéo một thẻ lên tên ngày để chuyển nơi đó sang ngày ấy. Nếu xếp không được (nơi đóng cửa, hết giờ trong ngày) thì thẻ ở nguyên chỗ cũ và mình nói lý do. Đổi nhầm thì bấm Hoàn tác ở thanh dưới.' },
  { anchor: '[data-tour="plan-alerts"]', side: 'bottom', title: 'Lưu ý nằm ở đây', body: 'Thời tiết, thông báo, nơi đóng cửa hay chưa rõ giờ mở cửa. Màu hổ phách là việc nên kiểm tra trước khi đi.' },
]

export function Plan() {
  useTitle('Lịch trình')
  const { trip, dispatch } = useTrip()
  const { view, diff, error, busy, confirmedTrip, act, confirm, optimize } = usePlanning()
  const { view: pick } = useDecision()
  const optimized = useUi((u) => (trip.planningId ? u.optimized[trip.planningId] : undefined))
  const ctx = trip.searchInput?.context
  const seen = trip.planningId ? looks.get(trip.planningId) : undefined
  const [hot, setHot] = useState<string | null>(null)
  const [editPlace, setEditPlace] = useState<string | null>(null)
  const [opt, setOpt] = useState(false)
  const [table, setTable] = useState(false)
  const [rday, setRday] = useState<number | 'all'>(seen?.rday ?? 'all')
  const [lodDone, setLodDone] = useState(false)
  const [dropDay, setDropDay] = useState<number | null>(null)
  const ready = !!view?.state.chosen_variant
  const [page, setPage] = useState<'journey' | 'detail'>(seen?.page ?? 'journey')
  const tour = useTour('plan-tour', { auto: true })
  useEffect(() => { if (trip.planningId) looks.set(trip.planningId, { rday, page }) }, [trip.planningId, rday, page])
  const variant = useMemo(() => view?.variants.find((v) => v.id === view.state.chosen_variant) ?? null, [view])
  // "Hợp với bạn" of a place the plan only suggests (a meal, an evening): the Decision card's own fit, never recomputed here.
  const fits = useMemo(() => {
    const m = new Map<string, Card['fit']>()
    for (const c of [...(pick?.groups.flatMap((g) => g.cards) ?? []), ...(pick?.unverified.cards ?? [])]) m.set(c.id, c.fit)
    return m
  }, [pick])
  // Suggestions are mostly outside the window Chọn nơi showed, so their fit is read by id from Place Decision.
  const [fitsMore, setFitsMore] = useState<Record<string, Fit>>({})
  const suggested = useMemo(() => {
    const itin = view?.itinerary ?? variant?.itinerary ?? []
    return [...new Set(itin.flatMap((d) => [...d.items.flatMap((i) => i.options ?? []), ...(d.night?.options ?? [])]).map((o) => o.place_id))]
  }, [view, variant])
  const ids = suggested.join(',')
  useEffect(() => {
    if (!trip.planningId || !ids) return
    let live = true
    loadFits(trip.planningId, ids.split(',')).then((r) => { if (live) setFitsMore(r) }, () => { /* no fit: suggestions keep the route order */ })
    return () => { live = false }
  }, [trip.planningId, ids])
  const fitOf = (id: string) => fitsMore[id] ?? fits.get(id)
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

  const blocked = blockerLines(view.back_to_decision?.reasons, (id) => info(id)?.name ?? id)
  if (!view.variants.length)
    return (
      <>
        <FlowBar step="plan" />
        <Page narrow>
          <Empty art={<ArtRoute />} title="Chưa xếp được lịch" body={view.back_to_decision?.places.length ? 'Bỏ hoặc đổi nơi vướng rồi xem lại.' : 'Các nơi đã chọn chưa đủ để xếp thành lịch trình.'} detail={blocked.length > 0 && <ul className="tg-notes">{blocked.map((l) => <li key={l}><Icon name="warn" size={14} /><span>{l}</span></li>)}</ul>} action={<button type="button" className="tg-btn tg-btn--primary" onClick={() => back('/explore')}>Chọn lại địa điểm</button>} />
          {view.warnings.length > 0 && <ul className="tg-notes">{view.warnings.map((w, i) => <li key={i}><Icon name="warn" size={14} /><span>{w.text}</span></li>)}</ul>}
        </Page>
      </>
    )

  // No lodging yet ("Chưa có, gợi ý giúp mình"): "Bạn ở đâu?" comes once, before the schedule.
  if (trip.searchInput?.context.lodging_booked === 'no' && !view.state.lodging_touched && !lodDone && !lodgingAsked(trip.planningId))
    return <LodgingPick planningId={trip.planningId} onDone={() => setLodDone(true)} />
  if (!view.state.chosen_variant) return <Choose variants={view.variants} busy={busy} onPick={(id) => act({ type: 'pick_variant', id })} />

  const days = view.itinerary ?? variant?.itinerary ?? []
  const places = days.reduce((n, x) => n + visits(x).length, 0)
  const travel = view.travel_load ? view.travel_load.reduce((n, x) => n + x.travel_min, 0) : variant?.metrics.travel_min ?? 0
  const lodgingName = view.lodging.candidates.find((c) => c.id === view.state.lodging_id)?.name ?? ((view.state.lodging_point?.text as string | undefined) || null)
  const better = optimized?.status === 'accepted' && optimized.after < optimized.before
  const allWarnings: Warning[] = [...view.warnings, ...(variant?.warnings ?? [])]
  const rentals: Alert[] = days.flatMap((x, i) => { const r = rentalStep(ctx, i, days.length); return r ? [{ key: `rental-${i}`, level: 'info' as const, icon: 'info' as const, day: x.day, lead: null, text: RENTAL_NOTE[r] }] : [] })
  const alerts = [...alertsOf({ warnings: allWarnings, days, conditions: view.day_conditions ?? [], tips: view.crowd_tips ?? [] }), ...rentals]
  const pinned: Record<string, 'locked' | 'chosen'> = {}
  for (const [id, v] of Object.entries(view.state.visit_overrides ?? {})) if (v.start !== null || v.duration_min !== null) pinned[id] = 'chosen'
  for (const id of view.state.locked) pinned[id] = 'locked'
  const walk = walkOnly(allWarnings)
  const onConfirm = async () => { if (await confirm()) go('/done') }
  // The trip keeps running on the confirmed plan while this one is being edited; it switches only at the next confirm.
  const editing = view.confirmed ? view.confirmed.edited : confirmedTrip
  return (
    <>
      <FlowBar step="plan" />
      <Page className="tg-plan">
        <header className="tg-plan__head">
          <div><p className="tg-kicker">Bước 3 · Lịch trình</p><h1>Đà Lạt {days.length} ngày</h1><p className="tg-muted">Giờ giấc và đường đi là ước tính.</p></div>
        </header>

        {view.variants.length > 1 && (
          <section className="tg-plan__variants" aria-label="Các hành trình">
            <p className="tg-plan__vhint"><Icon name="route" size={16} /> Mình xếp {view.variants.length} cách đi cho cùng những nơi này. Bấm một thẻ để đổi.</p>
            <VariantCards variants={view.variants} active={view.state.chosen_variant} busy={busy} size="sm" onPick={(id) => { void act({ type: 'pick_variant', id }) }} />
          </section>
        )}

        {editing && (
          <div className="tg-opt-banner" role="status"><Icon name="info" size={20} /><div><b>Bạn đang sửa lịch</b><span>Chuyến đi vẫn dùng lịch đã chốt trước đó. Bấm Chốt lại để dùng lịch mới trong chuyến.</span></div></div>
        )}
        {walk && (
          <div className="tg-opt-banner is-warn" role="status"><Icon name="walk" size={20} /><div><b>Lịch này chỉ đi bộ quanh chỗ ở</b><span>{walk.text}</span></div></div>
        )}
        {better && !optimized.seen && (
          <div className="tg-opt-banner" role="status"><Icon name="sparkle" size={20} /><div><b>Mình đã tìm được cách xếp tốt hơn</b><span>Giảm khoảng {fmtMin(optimized.before - optimized.after)} di chuyển mà không đổi chỗ ở, nhịp độ hay nơi đã khóa.</span></div><button type="button" className="tg-btn tg-btn--primary tg-btn--sm" onClick={() => setOpt(true)}>Xem đề xuất</button></div>
        )}
        <div className={`tg-sumstrip ${diff && diff.scope !== 'none' ? 'tg-flash' : ''}`}>
          <div><span>Di chuyển</span><b className="tg-mono">{travel > 0 ? `≈ ${fmtMin(travel)}` : 'Chưa tính'}</b></div>
          <div><span>Số nơi</span><b className="tg-mono">{places}</b></div>
          <div><span>Chi phí</span><b className="tg-mono">{variant ? costText(variant) : '—'}</b>{variant && variant.metrics.cost_unknown > 0 && <small>một phần chưa có giá</small>}</div>
          {variant && <div><span>Thời gian</span><Hint label={variant.robustness.reasons.join(' ') || variant.robustness.label}><b className={`tg-robust is-${ROBUST_CLS[variant.robustness.level]}`}>{variant.robustness.label} <Icon name="info" size={14} /></b></Hint></div>}
          <button type="button" className="tg-btn tg-btn--ghost tg-btn--sm" disabled={busy} onClick={async () => { await optimize(); setOpt(true) }}><Icon name="sparkle" size={16} /> {busy ? 'Đang thử…' : 'Tối ưu lịch'}</button>
        </div>
        {view.variants.length > 1 && <button type="button" className="tg-link tg-plan__tbl" aria-expanded={table} onClick={() => setTable((v) => !v)}>{table ? 'Ẩn' : 'So sánh'} {view.variants.length} hành trình</button>}
        {table && <Tradeoff variants={view.variants} active={view.state.chosen_variant} onPick={(id) => act({ type: 'pick_variant', id })} />}

        {page === 'detail' ? (
          <>
            <div className="tg-plan__viewbar"><button type="button" className="tg-link" onClick={() => setPage('journey')}><Icon name="route" size={15} /> Về hành trình</button><h2 className="tg-plan__dh">Chi tiết theo giờ</h2></div>
            <PlanDetail days={days} view={view} variant={variant} warnings={allWarnings} hot={hot} setHot={setHot} onEdit={setEditPlace} busy={busy} act={act} fitOf={fitOf} ctx={ctx} vehicle={trip.vehicle ?? null} onAdd={() => back('/explore')} />
          </>
        ) : (
          <>
        <LodgingStrip chosenName={lodgingName} />
        <PlanAlerts alerts={alerts} />

        <div className="tg-plan__viewbar">
          <div className="tg-seg" role="group" aria-label="Phạm vi" data-tour="plan-days">
            {[...days.map((_, i) => i as number | 'all'), 'all' as const].map((k) => {
              const target = k === 'all' ? null : days[k].day
              return (
                <button key={String(k)} type="button" aria-pressed={rday === k} className={target != null && dropDay === target ? 'is-drop' : undefined} onClick={() => setRday(k)}
                  onDragOver={(e) => { if (target != null && e.dataTransfer.types.includes('application/x-tg-stop')) { e.preventDefault(); setDropDay(target) } }}
                  onDragLeave={() => setDropDay(null)}
                  onDrop={(e) => { setDropDay(null); const from = dragged(e); if (target != null && from && from.day !== target) { e.preventDefault(); void act({ type: 'move_place', place: from.id, day: target }) } }}>
                  {k === 'all' ? 'Cả chuyến' : `Ngày ${days[k].day}`}
                </button>
              )
            })}
          </div>
          <button type="button" className="tg-link" onClick={tour.start}><Icon name="info" size={15} /> Cách chỉnh lộ trình</button>
          <button type="button" className="tg-btn tg-btn--soft tg-btn--sm tg-plan__detail" onClick={() => setPage('detail')}><Icon name="clock" size={15} /> Xem chi tiết theo giờ</button>
        </div>
        <p className="tg-plan__jhint"><Icon name="route" size={15} /> Kéo một thẻ vào trước hoặc sau thẻ khác để đổi thứ tự đi, hoặc kéo lên tên ngày để chuyển sang ngày đó. Mình tính lại giờ và đường đi sau mỗi lần đổi.</p>
        <div className="tg-rswrap" data-tour="plan-route"><RouteStory days={days} day={rday} home={lodgingName ?? 'Điểm xuất phát'} homeSet={!!lodgingName} hot={hot} setHot={setHot} fitOf={fitOf} busy={busy} pinned={pinned} onEdit={setEditPlace}
          onReorder={(day, order) => { void act({ type: 'reorder', day, order }) }} onMove={(place, day) => { void act({ type: 'move_place', place, day }) }} /></div>
        <BackupCard b={variant?.backups} day={rday === 'all' ? 'all' : days[rday]?.day ?? 'all'} busy={busy} onSwap={(place, w) => act({ type: 'swap', place, with: w })} />
        <div className="tg-plan__links"><button type="button" className="tg-link" disabled={busy} onClick={() => back('/explore')}><Icon name="plus" size={14} /> Thêm nơi</button><button type="button" className="tg-link tg-link--quiet" disabled={busy} onClick={() => back('/explore')}>Quay lại chọn nơi</button></div>
          </>
        )}
      </Page>
      <div className="tg-confirm">
        <div className="tg-confirm__in">
          {error ? <p className="tg-diff is-bad" role="alert"><Icon name="warn" size={15} />{error}</p> : diff && SCOPE_TEXT[diff.scope] ? <p className="tg-diff" role="status"><Icon name="bolt" size={15} />{SCOPE_TEXT[diff.scope]}<button type="button" className="tg-diff__undo" disabled={busy} onClick={() => act({ type: 'undo' })}>Hoàn tác</button></p> : <span className="tg-faint">{editing ? 'Bạn đang sửa lịch, bấm Chốt lại để dùng trong chuyến.' : 'Chưa chốt thì mình chưa lưu gì thành "đã chốt".'}</span>}
          <button type="button" className="tg-btn tg-btn--primary" disabled={busy} onClick={onConfirm}>{editing ? 'Chốt lại' : 'Chốt kế hoạch này'} <Icon name="arrow" size={18} /></button>
        </div>
      </div>
      <Tour steps={TOUR} open={tour.open && ready && page === 'journey'} onClose={tour.close} />
      <VisitEdit place={editPlace} onClose={() => setEditPlace(null)} days={days} />
      <Optimize open={opt} onClose={() => { setOpt(false); if (trip.planningId && optimized) setOptimized(trip.planningId, { ...optimized, seen: true }) }} onUndo={async () => { await act({ type: 'undo' }); if (trip.planningId) setOptimized(trip.planningId, null); setOpt(false) }} busy={busy} />
    </>
  )
}

function VisitEdit({ place, days, onClose }: { place: string | null; days: ItineraryDay[]; onClose: () => void }) {
  const { view, busy, error, act } = usePlanning()
  const day = days.find((d) => visits(d).some((it) => it.place_id === place))
  const stop = day && visits(day).find((it) => it.place_id === place)
  const [start, setStart] = useState('')
  const [duration, setDuration] = useState('')
  const fixed = place ? view?.state.visit_overrides?.[place] : undefined
  const lock = place ? view?.state.locked_visits?.[place] : undefined
  const locked = !!place && !!view?.state.locked.includes(place)
  useEffect(() => {
    if (!stop) return
    const chosenStart = fixed?.start ?? lock?.start
    setStart(chosenStart != null ? `${String(Math.floor(chosenStart / 60)).padStart(2, '0')}:${String(chosenStart % 60).padStart(2, '0')}` : stop.start)
    setDuration(String(fixed?.duration_min ?? lock?.duration_min ?? (toMin(stop.end) - toMin(stop.start))))
  }, [place, stop?.start, stop?.end, fixed?.start, fixed?.duration_min, lock?.start, lock?.duration_min])
  const action = place ? visitAction(place, start, duration) : null
  const order = day ? visits(day).map((it) => it.place_id!) : []
  const index = place ? order.indexOf(place) : -1
  const reorder = (offset: number) => {
    if (!day || index < 0) return
    const next = [...order]
    ;[next[index], next[index + offset]] = [next[index + offset], next[index]]
    void act(reorderVisitAction(day.day, next))
  }
  return <Dialog.Root open={!!stop} onOpenChange={(open) => !open && onClose()}><Dialog.Portal>
    <Dialog.Overlay className="tg tg-overlay" />
    <Dialog.Content className="tg tg-drawer" aria-describedby="tg-visit-help">
      <header><span className="tg-tag">Điểm ghé · Ngày {day?.day}</span><Dialog.Close className="tg-icon-btn" aria-label="Đóng"><Icon name="x" size={20} /></Dialog.Close></header>
      <Dialog.Title>{stop?.name ?? (place ? info(place)?.name : '')}</Dialog.Title>
      <p id="tg-visit-help" className="tg-faint">Chọn giờ đến và thời gian ở lại. Lịch sẽ được kiểm tra giờ mở cửa và thời gian di chuyển.</p>
      {(fixed || locked) && <p className="tg-visit-status">{locked ? 'Đã khóa giờ và thời lượng của điểm ghé này.' : 'Lịch đang giữ giờ hoặc thời lượng bạn chọn.'}</p>}
      <form className="tg-visit-form" onSubmit={(e) => { e.preventDefault(); if (action && !busy && !locked) void act(action) }}>
        <label>Giờ đến<input type="time" value={start} disabled={busy || locked} onChange={(e) => setStart(e.target.value)} /></label>
        <label>Thời gian ở lại (phút)<input type="number" min={1} max={1440} step={1} value={duration} disabled={busy || locked} onChange={(e) => setDuration(e.target.value)} /></label>
        <div className="tg-visit-actions"><button type="button" className="tg-link" disabled={busy || locked || fixed?.start == null} onClick={() => place && act(automaticVisitAction(place, 'start'))}>Giờ đến tự động</button><button type="button" className="tg-link" disabled={busy || locked || fixed?.duration_min == null} onClick={() => place && act(automaticVisitAction(place, 'duration_min'))}>Thời lượng tự động</button></div>
        <p className="tg-faint">Để trống một ô để tự động xếp phần đó.</p>
        {!action && <p className="tg-visit-error" role="alert">Nhập giờ từ 00:00 đến 23:59 và thời lượng nguyên từ 1 đến 1440 phút.</p>}
        <div className="tg-visit-actions"><button type="submit" className="tg-btn tg-btn--primary tg-btn--sm" disabled={busy || locked || !action}>{busy ? 'Đang xếp…' : 'Lưu giờ ghé'}</button><button type="button" className="tg-btn tg-btn--ghost tg-btn--sm" disabled={busy || locked || !fixed} onClick={() => place && act({ type: 'clear_visit', place })}>Xếp giờ tự động</button></div>
      </form>
      <div className="tg-visit-form">
        <label>Chuyển sang ngày<select value={day?.day ?? ''} disabled={busy || locked} onChange={(e) => place && act(moveVisitAction(place, Number(e.target.value)))}>{days.map((d) => <option key={d.day} value={d.day}>Ngày {d.day}</option>)}</select></label>
        <div className="tg-visit-actions"><button type="button" className="tg-btn tg-btn--soft tg-btn--sm" disabled={busy || locked || index <= 0} onClick={() => reorder(-1)}>Đi trước một điểm</button><button type="button" className="tg-btn tg-btn--soft tg-btn--sm" disabled={busy || locked || index < 0 || index >= order.length - 1} onClick={() => reorder(1)}>Đi sau một điểm</button></div>
        {place && view?.slots?.[place] && (
          <div className="tg-seg tg-seg--slot" role="group" aria-label="Giữ vào buổi">
            {view.slots[place].options.map((o) => <button key={o} type="button" aria-pressed={view.slots![place].current === o} disabled={busy} onClick={() => view.slots![place].current !== o && act({ type: 'set_slot', place_id: place, slot: o })}>{SLOT[o]}</button>)}
          </div>
        )}
        <button type="button" className="tg-btn tg-btn--ghost tg-btn--sm" disabled={busy} onClick={() => place && act({ type: locked ? 'unlock' : 'lock_slot', place })}>{locked ? 'Mở khóa để chỉnh' : 'Khóa giờ và thời lượng'}</button>
      </div>
      {error && <p className="tg-visit-error" role="alert">{error} Bạn có thể đổi giờ, giảm thời lượng hoặc chuyển ngày rồi thử lại.</p>}
      <footer><button type="button" className="tg-btn tg-btn--ghost" onClick={onClose}>Đóng</button></footer>
    </Dialog.Content>
  </Dialog.Portal></Dialog.Root>
}

function Choose({ variants, busy, onPick }: { variants: Variant[]; busy: boolean; onPick: (id: string) => void }) {
  const places = variants[0]?.itinerary.reduce((n, d) => n + visits(d).length, 0) ?? 0
  return (
    <>
      <FlowBar step="plan" />
      <Page className="tg-plan">
        <header className="tg-xhead"><div><p className="tg-kicker">Bước 3 · Lịch trình</p><h1>Chọn một hành trình</h1><p>Cùng {places} nơi bạn đã chọn, {variants.length} cách đi, mỗi cách tối ưu một mục tiêu khác. Chọn xong vẫn đổi được.</p></div></header>
        <VariantCards variants={variants} active={null} busy={busy} size="lg" onPick={onPick} />
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
    ['Di chuyển', (v) => (v.metrics.travel_min > 0 ? `≈ ${fmtMin(v.metrics.travel_min)}` : 'Chưa tính'), (v) => v.metrics.travel_min === minT],
    ['Số nơi mỗi ngày', (v) => v.itinerary.map((d) => visits(d).length).join(' · '), () => false],
    ['Chi phí', (v) => `${costText(v)}${v.metrics.cost_unknown ? ' *' : ''}`, (v) => v.metrics.cost_vnd === minC],
    ['Dính mưa', (v) => (v.metrics.rain_exposed ? `${v.metrics.rain_exposed} nơi ngoài trời` : 'Không'), (v) => v.metrics.rain_exposed === 0],
    ['Thời gian', (v) => v.robustness.label, (v) => v.robustness.level === 'solid'],
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
          {o && !better && <p className="tg-muted">{o.status === 'accepted' ? `Không có cách xếp nào giảm di chuyển đáng kể mà vẫn đúng giờ mở cửa. Giữ lịch hiện tại (${fmtMin(o.after)} di chuyển).` : `${keptWhy(o.diagnostics)} Mình giữ lịch hiện tại, lịch này đã qua kiểm tra giờ mở cửa và giờ trong ngày.`}</p>}
          <footer>{better && <button type="button" className="tg-btn tg-btn--ghost" disabled={busy} onClick={onUndo}>Giữ lịch cũ</button>}<button type="button" className="tg-btn tg-btn--primary" onClick={onClose}>{better ? 'Giữ cách xếp mới' : 'Đóng'} <Icon name="check" size={18} /></button></footer>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
