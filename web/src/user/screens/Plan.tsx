import * as Dialog from '@radix-ui/react-dialog'
import { useEffect, useMemo, useState } from 'react'
import { VEHICLE_LABEL } from '../../data/store'
import { enterStage } from '../journey'
import { fmtMin, fmtVnd, info } from '../lib'
import { usePlanning } from '../planning/planning'
import type { Action, Diff } from '../planning/types'
import { setOptimized, setUi, useUi } from '../store'
import { useTrip } from '../trip'
import { ArtRoute, Busy, Empty, go } from '../ui/common'
import { Icon } from '../ui/icons'
import { RouteStory } from '../ui/RouteStory'
import { FlowBar, Page, useTitle } from '../ui/Shell'
import { LongTripWarning } from '../ui/LongTripWarning'
import { LODGING_TAB } from './Lodging'
import { candidatesOf, type Candidate } from './plan/candidates'
import { Choose } from './plan/Choose'
import { DayView } from './plan/DayView'
import { Overview } from './plan/Overview'
import { useRoutes } from './plan/useRoutes'
import { BackupCard, KeepAll, Lodging, NoHotel, Optimize, TimeCard } from './plan/parts'
import { costText, MEAL_LABEL, openPlace, placeName, visits } from './plan/shared'
import { Swap } from './plan/Swap'

// docs/UI_SPEC_USER_WEB.md Trang 8, layout from ui_mock_for_design/designs/itinerary: choose a way → overview → one screen per day
// (+ a screen to swap or add a place). Times and routes are estimates and say so; warnings sit on the stop they concern.
// Lịch trình takes actions only (no chat): docs/PLANNING.md.

const SCOPE_TEXT: Record<Diff['scope'], string> = {
  none: '',
  relayout: 'Đã xếp lại một vài ngày bị ảnh hưởng',
  variant: 'Đã xếp lại cả chuyến theo thay đổi này',
  lodging_home: 'Đã đổi chỗ nghỉ, giờ di chuyển được tính lại',
  lodging_fetch: 'Đã tìm lại danh sách chỗ ở',
}
const VIOLATION: Record<string, string> = { meal_missing: 'Chưa chừa đủ thời gian cho bữa ăn.', meal_window: 'Chưa xếp được bữa ăn vào khung giờ riêng.', hours: 'Giờ ghé nằm ngoài giờ mở cửa.', timed: 'Giờ ghé chưa khớp khung giờ cần thiết.', overlap: 'Có hoạt động trùng giờ.', day_window: 'Lịch vượt khung giờ của ngày.', travel: 'Chưa đủ thời gian di chuyển.', long_leg: 'Chặng đi vượt giới hạn đã chọn.', anchor: 'Chưa xếp được nơi bắt buộc.', budget: 'Chi phí đã biết vượt ngân sách.', duplicate: 'Địa điểm bị xếp trùng.', hard: 'Chưa đáp ứng yêu cầu bắt buộc.', hazard: 'Điều kiện ngày này không cho phép ghé an toàn.' }

type Screen = 'overview' | 'day' | 'swap'

export function Plan() {
  useTitle('Lịch trình')
  const { trip, dispatch } = useTrip()
  const { view, diff, error, busy, act, previewAct, editPreview, dismissPreview, confirm, optimize } = usePlanning()
  const optimized = useUi((u) => (trip.planningId ? u.optimized[trip.planningId] : undefined))
  const [screen, setScreen] = useState<Screen>('overview')
  const [changing, setChanging] = useState(false) // "Đổi phương án": the choice screen again, over a plan that already exists
  const [picked, setDayIdx] = useState<number | null>(null) // null: the first day that has a stop
  const [swapFor, setSwapFor] = useState<string | null>(null) // the place a swap replaces; null: add one
  const [dropAsk, setDropAsk] = useState<string | null>(null)
  const [pickAsk, setPickAsk] = useState<string | null>(null) // another way chosen while a hand-made order exists
  const [droppedOpen, setDroppedOpen] = useState(false)
  const [costOpen, setCostOpen] = useState(false)
  const [story, setStory] = useState(false)
  const [hot, setHot] = useState<string | null>(null)
  const [opt, setOpt] = useState(false)
  useEffect(() => { window.scrollTo(0, 0) }, [screen, changing, view?.state.chosen_variant])
  // The road of each day is read apart from the plan; it is read again whenever the stops, their order or the lodging change.
  const routeKey = `${view?.state.lodging_id ?? ''}|${(view?.itinerary ?? []).map((x) => x.items.filter((it) => it.kind === 'visit').map((it) => it.place_id).join(',')).join('|')}`
  const routes = useRoutes(trip.planningId, routeKey, screen === 'day' && !!view?.itinerary)
  const variant = useMemo(() => view?.active_variant ?? view?.variants.find((v) => v.id === view.state.chosen_variant) ?? null, [view])
  const back = async (to: string) => {
    if (trip.planningId) {
      try {
        await enterStage(trip.planningId, 'decision')
        dispatch({ type: 'set', patch: { planningId: null } })
      } catch { /* Chọn nơi shows the connection error itself */ }
    }
    go(to)
  }
  // Where the user sleeps is picked at Lựa chọn: changing it goes back to the "Chỗ ở" tab there.
  const toLodging = () => {
    setUi({ tab: LODGING_TAB })
    void back('/explore')
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
              <div className="tg-it-skel" aria-busy="true">
                {Array.from({ length: 3 }, (_, i) => <span key={i} className="tg-skel" style={{ height: 360, borderRadius: 22 }} />)}
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

  const hasHotel = Boolean(view.state.lodging_touched && view.state.lodging_id)
  const pickVariant = async (id: string) => {
    if (id === view.state.chosen_variant) { setChanging(false); setScreen('overview'); return }
    if (view.state.chosen_variant && Object.keys(view.state.order_override ?? {}).length && pickAsk !== id) { setPickAsk(id); return }
    setPickAsk(null)
    if (await act({ type: 'pick_variant', id })) { setChanging(false); setDayIdx(null); setScreen('overview') }
  }
  if (!view.state.chosen_variant || changing) return (
    <>
      <Choose variants={view.variants} keepAll={view.keep_all} overload={view.overload} locked={view.state.locked} current={view.state.chosen_variant} busy={busy} hasHotel={hasHotel}
        onBack={() => back('/explore')} onHotel={toLodging} onPick={(id) => { void pickVariant(id) }} onCancel={view.state.chosen_variant ? () => setChanging(false) : undefined} />
      <Dialog.Root open={!!pickAsk} onOpenChange={(o) => { if (!o) setPickAsk(null) }}>
        <Dialog.Portal><Dialog.Overlay className="tg tg-overlay" /><Dialog.Content className="tg tg-it-dlg" aria-describedby={undefined}>
          <header><Dialog.Title>Dùng lịch của phương án này?</Dialog.Title><Dialog.Close className="tg-icon-btn" aria-label="Đóng"><Icon name="x" size={18} /></Dialog.Close></header>
          <p>Thứ tự ghé bạn đã sắp trong từng ngày sẽ được đặt lại theo phương án mới. Nơi bạn đã bỏ, đã đổi ngày hoặc đã khóa vẫn giữ nguyên.</p>
          <footer><button type="button" className="tg-btn tg-btn--ghost" onClick={() => setPickAsk(null)}>Quay lại</button><button type="button" className="tg-btn tg-btn--primary" disabled={busy} onClick={() => pickAsk && void pickVariant(pickAsk)}>Dùng phương án này</button></footer>
        </Dialog.Content></Dialog.Portal>
      </Dialog.Root>
    </>
  )

  const days = view.itinerary ?? variant?.itinerary ?? []
  const dayIdx = Math.min(picked ?? Math.max(0, days.findIndex((x) => visits(x).length > 0)), Math.max(0, days.length - 1))
  const d = days[dayIdx]
  const places = days.reduce((n, x) => n + visits(x).length, 0)
  const travel = view.travel_load ? view.travel_load.reduce((n, x) => n + x.travel_min, 0) : variant?.metrics.travel_min ?? 0
  const metrics = view.metrics ?? variant?.metrics
  const robustness = view.robustness ?? variant?.robustness
  const vehicle = trip.vehicle ? VEHICLE_LABEL[trip.vehicle].toLowerCase() : ''
  const lodgingName = view.lodging.candidates.find((c) => c.id === view.state.lodging_id)?.name ?? ((view.state.lodging_point?.text as string | undefined) || null)
  const better = optimized?.status === 'accepted' && optimized.after < optimized.before
  const planDropped = (variant?.dropped_by_plan ?? []).filter((x) => (view.state.plan_dropped ?? []).includes(x.place_id))
  const userDropped = view.state.dropped.filter((x) => !planDropped.some((p) => p.place_id === x.place_id))
  const droppedCount = planDropped.length + userDropped.length
  const blocked = !!view.violations?.length || variant?.confirmable === false
  const onConfirm = async () => { if (await confirm()) go('/done') }
  const openDay = (i: number) => { setDayIdx(i); setScreen('day') }
  const startSwap = (place: string | null) => { setSwapFor(place); setScreen('swap') }
  const candidates = candidatesOf(view, variant, days, swapFor)
  const pickCandidate = async (c: Candidate) => {
    if (!d) return
    const day = d.day - 1
    await previewAct(swapFor ? { type: 'swap', place: swapFor, with: c.id } : c.from === 'backup' ? { type: 'add_from_backup', place: c.id, day } : { type: 'move_place', place: c.id, day })
  }
  const restore = async (id: string) => { setDroppedOpen(false); await previewAct({ type: 'move_place', place: id, day: dayIdx }) }

  const note = error
    ? <p className="tg-it-diff is-bad" role="alert"><Icon name="warn" size={15} />{error}</p>
    : diff && SCOPE_TEXT[diff.scope]
      ? <p className="tg-it-diff" role="status"><Icon name="bolt" size={15} />{SCOPE_TEXT[diff.scope]}<button type="button" disabled={busy} onClick={() => act({ type: 'undo' })}>Hoàn tác</button></p>
      : null
  const confirmButton = <button type="button" className="tg-btn tg-btn--primary" disabled={busy || blocked} title={blocked ? 'Lịch còn lỗi hoặc phương án chưa đạt yêu cầu; sửa trước khi chốt.' : undefined} onClick={onConfirm}>Chốt kế hoạch này <Icon name="arrow" size={18} /></button>

  const notices = (
    <div className="tg-it-notices">
      {!hasHotel && <NoHotel onHotel={toLodging} />}
      <LongTripWarning days={days.length} />
      {view.overload && <div className="tg-it-note is-attention" role="status"><Icon name="warn" size={18} /><div><b>{view.overload.text}</b><p>Ước lượng tải cho {view.overload.selection_places} nơi; lịch bên dưới được kiểm tra bằng validator.</p></div></div>}
      {better && !optimized.seen && (
        <div className="tg-it-note is-good" role="status"><Icon name="sparkle" size={20} /><div><b>Mình đã tìm được cách xếp tốt hơn</b><p>Giảm khoảng {fmtMin(optimized.before - optimized.after)} di chuyển mà không đổi chỗ ở, nhịp độ hay nơi đã khóa.</p></div><button type="button" className="tg-btn tg-btn--primary tg-btn--sm" onClick={() => setOpt(true)}>Xem đề xuất</button></div>
      )}
      {blocked && !view.violations?.length && <div className="tg-it-note is-attention" role="status"><Icon name="warn" size={18} /><span>Phương án này chưa đạt yêu cầu nên chưa chốt được. Chọn phương án khác hoặc sửa lịch.</span></div>}
      {!!view.violations?.length && <div className="tg-it-note is-attention" role="status"><Icon name="warn" size={18} /><ul>{view.violations.map((v, i) => <li key={i}>{v.day !== null ? `Ngày ${v.day + 1} · ` : ''}{v.place_id ? `${info(v.place_id)?.name ?? v.place_id}: ` : ''}{VIOLATION[v.kind] ?? 'Lịch còn xung đột cần xử lý trước khi chốt.'}</li>)}</ul></div>}
    </div>
  )
  const delta = variant?.delta_vs_selection ? `So với danh sách đã chọn: ${variant.delta_vs_selection.places > 0 ? '+' : ''}${variant.delta_vs_selection.places} nơi · Di chuyển ${variant.delta_vs_selection.travel_min === null ? 'chưa so được' : `${variant.delta_vs_selection.travel_min > 0 ? '+' : ''}${variant.delta_vs_selection.travel_min} phút`} · Chi phí địa điểm đã biết ${variant.delta_vs_selection.cost_vnd === null ? 'chưa so được' : `${variant.delta_vs_selection.cost_vnd > 0 ? '+' : ''}${fmtVnd(variant.delta_vs_selection.cost_vnd)}`}` : null
  const sameAs = variant?.same_as?.length ? variant.same_as.map((id) => view.variants.find((v) => v.id === id)?.label ?? id).join(', ') : null

  const overviewFooter = (
    <div className="tg-it-foot">
      <div className="tg-it-foot__in">
        <div className="tg-it-foot__cost">
          <span>Chi phí địa điểm đã biết</span><b>{metrics ? (metrics.cost_vnd ? `≈ ${fmtVnd(metrics.cost_vnd)}` : 'Chưa có giá') : '—'}</b><span>chưa gồm chỗ nghỉ, di chuyển</span>
          <button type="button" className="tg-it-textbtn" aria-label="Chi phí này gồm gì" onClick={() => setCostOpen(true)}><Icon name="info" size={16} /></button>
        </div>
        <div className="tg-it-foot__acts">{confirmButton}<button type="button" className="tg-btn tg-btn--soft" onClick={() => openDay(dayIdx)}>Xem lịch từng ngày <Icon name="arrow" size={18} /></button></div>
      </div>
    </div>
  )
  const dayFooter = (
    <div className="tg-it-status">
      <span>{places} nơi trong lịch · {droppedCount} nơi tạm bỏ</span>
      <div>
        <button type="button" className="tg-it-textbtn is-sec" onClick={() => setScreen('overview')}>Tổng quan</button>
        <button type="button" className="tg-btn tg-btn--ghost tg-btn--sm" disabled={busy} onClick={async () => { await optimize(); setOpt(true) }}><Icon name="sparkle" size={15} /> {busy ? 'Đang thử…' : 'Tối ưu lịch'}</button>
        {confirmButton}
      </div>
    </div>
  )
  const extras = (
    <>
      <Lodging onChange={toLodging} />
      <TimeCard day={d?.day ?? 1} itinerary={d} timing={view.time_suitability ?? variant?.time_suitability ?? []} suggestions={view.recommendations ?? variant?.recommendations ?? []} status={view.suggestions?.status}
        busy={busy} onAdd={(place, day) => act({ type: 'add_from_backup', place, day: day - 1 })} />
      <BackupCard b={view.backups ?? variant?.backups} day={d?.day ?? 1} busy={busy} onSwap={async (place, w) => { await previewAct({ type: 'swap', place, with: w }) }} />
      <section className="tg-sidecard" aria-labelledby="tg-nt-h">
        <h2 id="tg-nt-h"><Icon name="info" size={18} /> Lưu ý cả chuyến</h2>
        {view.warnings.length === 0 && !(variant?.warnings.length) ? <p className="tg-faint">Chưa có lưu ý nào.</p> : <ul className="tg-notes">{[...view.warnings, ...(variant?.warnings ?? [])].slice(0, 6).map((w, i) => <li key={i}><Icon name="warn" size={14} /><span>{w.text}</span></li>)}</ul>}
      </section>
      {!!variant?.checklist?.length && (
        <section className="tg-sidecard" aria-labelledby="tg-cl-h">
          <h2 id="tg-cl-h"><Icon name="check" size={18} /> Chuẩn bị trước khi đi</h2>
          <ul className="tg-checklist">{variant.checklist.map((c, i) => <li key={i}><Icon name={c.kind === 'scam' ? 'warn' : 'check'} size={14} /><span><small className="tg-faint">Ngày {c.day} · </small>{c.text}</span></li>)}</ul>
        </section>
      )}
    </>
  )

  return (
    <>
      {note && screen !== 'swap' && <div className="tg-it-toast">{note}</div>}
      {screen === 'overview' && <Overview days={days} variant={variant} robustness={robustness} travelMin={travel} visitMin={metrics?.visit_min ?? 0} droppedCount={droppedCount}
        lodgingName={lodgingName} hasHotel={hasHotel} notices={notices} footer={overviewFooter} busy={busy} delta={delta} sameAs={sameAs}
        after={view.keep_all ? <KeepAll variant={view.keep_all} busy={busy} onPick={(id) => act({ type: 'pick_variant', id })} /> : null} onReoptimize={() => { void previewAct({ type: 'reoptimize' }) }} onDay={openDay} onChangeVariant={() => setChanging(true)} onHotel={toLodging}
        onDropped={() => setDroppedOpen(true)} onStory={() => setStory(true)} onOpen={openPlace} />}
      {screen === 'day' && d && <DayView days={days} dayIdx={dayIdx} week={Math.floor(dayIdx / 7)} onDay={setDayIdx} busy={busy} locked={view.state.locked}
        durationRange={view.duration_range} durationOverrides={view.state.visit_duration_override ?? {}} cond={view.day_conditions?.find((c) => c.day === d.day)} tips={view.crowd_tips ?? []}
        vehicle={vehicle} extras={extras} footer={dayFooter} summary={variant?.label ?? 'Lịch trình'} route={routes?.find((r) => r.day === d.day) ?? null}
        onBack={() => setScreen('overview')} onOpen={openPlace} onSwap={startSwap} onDrop={setDropAsk}
        onMoveDay={(place, day) => { void act({ type: 'move_place', place, day }) }} onReorder={(day, order) => act({ type: 'reorder', day, order })}
        onDuration={(place, minutes) => { void previewAct({ type: 'set_visit_duration', place, minutes }) }} />}
      {screen === 'swap' && d && <Swap day={d} replacing={swapFor} candidates={candidates} people={trip.people} busy={busy} onOverview={() => setScreen('overview')} onDay={() => setScreen('day')}
        onPick={(c) => { void pickCandidate(c) }} onOpen={openPlace} onMore={() => back('/explore')} />}

      <Optimize open={opt} onClose={() => { setOpt(false); if (trip.planningId && optimized) setOptimized(trip.planningId, { ...optimized, seen: true }) }} onUndo={async () => { await act({ type: 'undo' }); if (trip.planningId) setOptimized(trip.planningId, null); setOpt(false) }} busy={busy} />

      <Dialog.Root open={!!editPreview} onOpenChange={(open) => { if (!open) dismissPreview() }}>
        <Dialog.Portal><Dialog.Overlay className="tg tg-overlay" /><Dialog.Content className="tg tg-listpanel tg-edit-preview" aria-describedby={undefined}>
          <header><Dialog.Title>Xem trước thay đổi</Dialog.Title><Dialog.Close className="tg-icon-btn" aria-label="Đóng"><Icon name="x" size={18} /></Dialog.Close></header>
          {editPreview?.action.type === 'set_visit_duration' && <p className="tg-it-note is-attention" role="status"><Icon name="warn" size={16} /> Thay thời lượng có thể đổi giờ ghé, bữa ăn và thời gian đệm. Kiểm tra lịch bên dưới trước khi áp dụng.</p>}
          <p>Đi lại {editPreview?.delta.travel_min == null ? 'chưa so được' : `${editPreview.delta.travel_min > 0 ? '+' : ''}${fmtMin(editPreview.delta.travel_min)}`} · Tham quan {editPreview?.delta.visit_min == null ? 'chưa so được' : `${editPreview.delta.visit_min > 0 ? '+' : ''}${fmtMin(editPreview.delta.visit_min)}`} · Số nơi {editPreview?.delta.places ?? '—'}</p>
          {!!editPreview?.violations.length && <ul className="tg-notes">{editPreview.violations.map((v, i) => <li key={i}><Icon name="warn" size={14} /><span>{VIOLATION[v.kind] ?? 'Lịch còn xung đột cần xử lý.'}</span></li>)}</ul>}
          {editPreview?.action.type === 'set_visit_duration' && editPreview.view.itinerary?.map(day => <section key={day.day} className="tg-backup"><b>Ngày {day.day}</b>{day.items.filter(item => item.kind === 'visit' || item.kind === 'meal_free').map((item, i) => <span key={i}>{item.start}–{item.end} · {item.kind === 'meal_free' ? MEAL_LABEL[item.name ?? ''] : item.name}</span>)}</section>)}
          {!!editPreview?.make_room.length && <div className="tg-backup"><b>Cách tạo chỗ trống</b><span>Chọn một đề xuất đã được kiểm tra; máy chủ không tự bỏ nơi.</span>{editPreview.make_room.map((a: Action, i: number) => <button key={i} type="button" className="tg-btn tg-btn--soft tg-btn--sm" disabled={busy} onClick={async () => await previewAct(a)}>Xem cách này</button>)}</div>}
          {!editPreview?.confirmable && <p className="tg-faint">Lịch sau thay đổi chưa thể chốt. Máy chủ sẽ kiểm tra lại khi chốt.</p>}
          <footer><button type="button" className="tg-btn tg-btn--ghost" onClick={() => dismissPreview()}>Để sau</button><button type="button" className="tg-btn tg-btn--primary" disabled={busy || !editPreview || (editPreview.action.type === 'set_visit_duration' && !editPreview.confirmable)} onClick={async () => { if (!editPreview) return; const ok = await act({ ...editPreview.action, _preview_token: editPreview.token }); dismissPreview(); if (ok) setScreen((s) => (s === 'swap' ? 'day' : s)) }}>Áp dụng thay đổi đã xem</button></footer>
        </Dialog.Content></Dialog.Portal>
      </Dialog.Root>

      <Dialog.Root open={!!dropAsk} onOpenChange={(o) => { if (!o) setDropAsk(null) }}>
        <Dialog.Portal><Dialog.Overlay className="tg tg-overlay" /><Dialog.Content className="tg tg-it-dlg" aria-describedby={undefined}>
          <header><Dialog.Title>Bỏ {dropAsk ? placeName(dropAsk) : ''} khỏi ngày {d?.day}?</Dialog.Title><Dialog.Close className="tg-icon-btn" aria-label="Đóng"><Icon name="x" size={18} /></Dialog.Close></header>
          <p>Nơi này vẫn nằm trong danh sách tạm bỏ để bạn có thể thêm lại. Lịch ngày này được xếp lại, và bạn hoàn tác được.</p>
          <footer><button type="button" className="tg-btn tg-btn--ghost" onClick={() => setDropAsk(null)}>Giữ lại</button><button type="button" className="tg-btn tg-btn--primary" disabled={busy} onClick={async () => { if (dropAsk) await act({ type: 'drop_place', place: dropAsk }); setDropAsk(null) }}>Tạm bỏ nơi này</button></footer>
        </Dialog.Content></Dialog.Portal>
      </Dialog.Root>

      <Dialog.Root open={droppedOpen} onOpenChange={setDroppedOpen}>
        <Dialog.Portal><Dialog.Overlay className="tg tg-overlay" /><Dialog.Content className="tg tg-it-dlg" aria-describedby={undefined}>
          <header><Dialog.Title>{droppedCount} nơi tạm bỏ</Dialog.Title><Dialog.Close className="tg-icon-btn" aria-label="Đóng"><Icon name="x" size={18} /></Dialog.Close></header>
          <ul className="tg-it-droplist">
            {planDropped.map((x) => <li key={x.place_id}><div><b>{x.name}</b><small>{x.text}</small></div><button type="button" className="tg-it-textbtn" disabled={busy} onClick={() => restore(x.place_id)}>Xem trước khi khôi phục</button></li>)}
            {userDropped.map((x) => <li key={x.place_id}><div><b>{placeName(x.place_id)}</b><small>Bạn đã tạm bỏ nơi này</small></div><button type="button" className="tg-it-textbtn" disabled={busy} onClick={() => restore(x.place_id)}>Xem trước khi khôi phục</button></li>)}
          </ul>
          <p className="tg-faint">Khôi phục sẽ thêm nơi vào ngày {d?.day ?? 1}; bạn xem trước thay đổi rồi mới áp dụng.</p>
        </Dialog.Content></Dialog.Portal>
      </Dialog.Root>

      <Dialog.Root open={costOpen} onOpenChange={setCostOpen}>
        <Dialog.Portal><Dialog.Overlay className="tg tg-overlay" /><Dialog.Content className="tg tg-it-dlg" aria-describedby={undefined}>
          <header><Dialog.Title>Chi phí tham khảo</Dialog.Title><Dialog.Close className="tg-icon-btn" aria-label="Đóng"><Icon name="x" size={18} /></Dialog.Close></header>
          <p><b>{metrics?.cost_vnd ? `≈ ${fmtVnd(metrics.cost_vnd)}` : 'Chưa có giá'}</b> cho các nơi đã có giá trong lịch. Giá từng nơi là khoảng giá đã biết, chưa phải báo giá.</p>
          <ul className="tg-it-costlist">
            {!!metrics && metrics.cost_unknown > 0 && <li>{metrics.cost_unknown} nơi chưa có giá nên chưa tính.</li>}
            {!!metrics?.meal_cost_unknown && <li>{metrics.meal_cost_unknown} bữa tự chọn chưa tính giá.</li>}
            {metrics?.transport_cost_vnd == null && <li>Chưa tính chi phí di chuyển.</li>}
            {!!metrics?.extras_max_vnd && <li>Có thể thêm tới {fmtVnd(metrics.extras_max_vnd)} cho trò chơi, thuê đồ.</li>}
            <li>Chưa gồm chỗ nghỉ và chuyến đến, về.</li>
          </ul>
          {variant && <p className="tg-faint">Phương án {variant.label}: {costText(variant)}.</p>}
        </Dialog.Content></Dialog.Portal>
      </Dialog.Root>

      <Dialog.Root open={story} onOpenChange={setStory}>
        <Dialog.Portal><Dialog.Overlay className="tg tg-overlay" /><Dialog.Content className="tg tg-it-dlg is-story" aria-describedby={undefined}>
          <header><Dialog.Title>Sơ đồ hành trình cả chuyến</Dialog.Title><Dialog.Close className="tg-icon-btn" aria-label="Đóng"><Icon name="x" size={18} /></Dialog.Close></header>
          <div className="tg-rswrap"><RouteStory days={days} day="all" home={lodgingName ?? 'Điểm xuất phát'} hot={hot} setHot={setHot} /></div>
        </Dialog.Content></Dialog.Portal>
      </Dialog.Root>
    </>
  )
}
