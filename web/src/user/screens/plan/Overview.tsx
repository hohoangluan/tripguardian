import type { ReactNode } from 'react'
import { dayLabel, fmtMin, info } from '../../lib'
import type { ItineraryDay, Robustness, Variant } from '../../planning/types'
import { Hint, PlacePhoto } from '../../ui/common'
import { Icon, type IconName } from '../../ui/icons'
import { FlowBar } from '../../ui/Shell'
import { TripMap } from './TripMap'
import { dayAreas, placeName, shortDate, visits } from './shared'

// Mẫu ui_mock_for_design/designs/itinerary (màn tổng quan): the whole trip on one map, then the journey top to bottom —
// arrival, where to sleep, one card per day, departure. A day opens on its own screen.

const ROBUST_CLS: Record<string, string> = { solid: 'hi', feasible: 'mid', fragile: 'lo' }

function Row({ icon, title, sub, children }: { icon: IconName; title: string; sub: string; children: ReactNode }) {
  return (
    <div className="tg-it-row">
      <div className="tg-it-row__label"><span><Icon name={icon} size={20} /></span><div><b>{title}</b><small>{sub}</small></div></div>
      <div className="tg-it-row__body">{children}</div>
    </div>
  )
}

export function Overview({ days, variant, robustness, travelMin, visitMin, droppedCount, lodgingName, hasHotel, notices, after, delta, sameAs, busy, footer, onDay, onChangeVariant, onHotel, onDropped, onStory, onReoptimize, onOpen }: {
  days: ItineraryDay[]; variant: Variant | null; robustness?: Robustness; travelMin: number; visitMin: number; droppedCount: number
  lodgingName: string | null; hasHotel: boolean; notices: ReactNode; after: ReactNode; delta: string | null; sameAs: string | null; busy: boolean; footer: ReactNode
  onDay: (i: number) => void; onChangeVariant: () => void; onHotel: () => void; onDropped: () => void; onStory: () => void; onReoptimize: () => void; onOpen: (id: string) => void
}) {
  const ids = days.flatMap((d) => visits(d).map((it) => it.place_id!))
  const first = days[0]
  const last = days[days.length - 1]
  const range = days.length > 1 ? `${shortDate(first?.date, 1)} – ${shortDate(last?.date, days.length)}` : shortDate(first?.date, 1)
  const label = variant?.label ?? 'Lịch trình'
  return (
    <>
      <FlowBar step="plan" />
      <div className="tg-it-crumb">
        <button type="button" className="tg-it-crumb__back" aria-label="Quay lại chọn phương án" onClick={onChangeVariant}><Icon name="arrowLeft" size={18} /></button>
        <span>Chuyến đi của bạn</span><Icon name="chevronRight" size={14} /><strong>Tổng quan</strong>
        <div className="tg-it-crumb__right"><span>{label}</span><button type="button" className="tg-it-textbtn" onClick={onChangeVariant}>Đổi phương án</button></div>
      </div>
      <main className="tg-it-ov">
        <TripMap groups={days.map((d) => visits(d).map((it) => it.place_id!))} title="Bản đồ cả chuyến" className="is-banner" labels={false} onOpen={onOpen}>
          <span className="tg-it-map__city"><Icon name="pin" size={14} />Đà Lạt</span>
          <button type="button" className="tg-it-map__open" onClick={() => onDay(0)}>Xem lịch &amp; bản đồ <Icon name="arrow" size={15} /></button>
          <span className="tg-it-map__note">Đường nối minh họa thứ tự · không phải chỉ đường</span>
        </TripMap>
        {notices}
        <Row icon="pin" title={`Ngày 1–${days.length}`} sub={range}>
          <div className="tg-it-intro">
            <h1>Đà Lạt</h1>
            <p>{days.length} ngày, {ids.length} nơi. Mở từng ngày để xem, đổi hoặc thêm nơi muốn ghé.</p>
            {variant?.preset && variant.tradeoff && <p className="tg-it-intro__trade tg-faint">Đánh đổi: {variant.tradeoff}{sameAs ? ` · Cùng lịch với ${sameAs}.` : ''}</p>}
            {delta && <p className="tg-it-intro__trade tg-faint">{delta}</p>}
            <ul className="tg-it-facts">
              <li><Icon name="route" size={15} />≈ {fmtMin(travelMin)} di chuyển</li>
              <li><Icon name="clock" size={15} />≈ {fmtMin(visitMin)} tham quan</li>
              {robustness && <li><Hint label={robustness.reasons.join(' ') || robustness.label}><b className={`tg-robust is-${ROBUST_CLS[robustness.level]}`}>{robustness.label} <Icon name="info" size={14} /></b></Hint></li>}
              <li><button type="button" className="tg-it-textbtn" onClick={onStory}>Xem sơ đồ hành trình</button></li>
              {variant?.preset && <li><button type="button" className="tg-it-textbtn" disabled={busy} onClick={onReoptimize}>Tối ưu lại quanh lựa chọn của tôi</button></li>}
            </ul>
            <div className="tg-it-plan"><span><Icon name="check" size={14} />{label} · {ids.length} nơi trong lịch</span>{droppedCount > 0 && <button type="button" className="tg-it-textbtn" onClick={onDropped}>{droppedCount} nơi tạm bỏ <Icon name="chevronRight" size={14} /></button>}</div>
          </div>
        </Row>
        <Row icon="plane" title="Đến Đà Lạt" sub={shortDate(first?.date, 1)}>
          <div className="tg-it-transit"><span><Icon name="plane" size={16} /><b>Di chuyển đến Đà Lạt</b></span><span>{first ? `Lịch ngày đầu bắt đầu lúc ${first.window[0]}` : 'Chưa có thông tin chuyến đến'}</span></div>
        </Row>
        <Row icon="bed" title="Chỗ nghỉ" sub={days.length > 1 ? `${days.length - 1} đêm` : 'Không nghỉ đêm'}>
          <div className="tg-it-transit"><span><Icon name="bed" size={16} /><b>{hasHotel && lodgingName ? lodgingName : 'Chưa chọn chỗ nghỉ'}</b></span><button type="button" className="tg-it-textbtn" onClick={onHotel}>{hasHotel ? 'Đổi chỗ nghỉ' : 'Chọn chỗ nghỉ'} <Icon name="chevronRight" size={14} /></button></div>
        </Row>
        <Row icon="calendar" title="Lịch trình" sub={`Ngày 1–${days.length}`}>
          <div className="tg-it-days">
            {days.map((d, i) => {
              const stops = visits(d)
              const cover = stops[0]?.place_id
              const l = dayLabel(d.date)
              return (
                <button key={d.day} type="button" className="tg-it-daycard" style={{ ['--i' as string]: i }} onClick={() => onDay(i)}>
                  {cover && info(cover) ? <PlacePhoto id={cover} name={placeName(cover)} className="tg-it-daycard__ph" /> : <span className="tg-it-daycard__ph tg-photo tg-photo__ph" />}
                  <div>
                    <div className="tg-it-daymeta"><span className="tg-it-pill">Ngày {d.day}</span><span>{l ? `${l.wd} · ${shortDate(d.date)}` : d.weekday || 'Chưa có ngày'}</span><span>·</span><span>{stops.length} điểm dừng</span></div>
                    <h3>{dayAreas(d).join(' · ') || 'Ngày tự do'}</h3>
                    <p>{stops.map((it) => it.name ?? placeName(it.place_id!)).join(' · ') || 'Nghỉ, tự khám phá hoặc thêm nơi'}</p>
                  </div>
                  <Icon name="chevronRight" size={16} />
                </button>
              )
            })}
          </div>
        </Row>
        <Row icon="plane" title="Rời Đà Lạt" sub={shortDate(last?.date, days.length)}>
          <div className="tg-it-transit"><span><Icon name="plane" size={16} /><b>Di chuyển về</b></span><span>{last ? `Lịch ngày cuối kết thúc lúc ${last.window[1]}` : 'Chưa có thông tin chuyến về'}</span></div>
        </Row>
        {after}
      </main>
      {footer}
    </>
  )
}
