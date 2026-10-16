import * as Dialog from '@radix-ui/react-dialog'
import { useState } from 'react'
import { fmtMin, fmtVnd, info } from '../../lib'
import { usePlanning } from '../../planning/planning'
import type { Backups, CrowdTip, DayConditions, ItineraryDay, TimeRecommendation, TimeSuitabilityDay, Variant } from '../../planning/types'
import { useUi } from '../../store'
import { useTrip } from '../../trip'
import { PlacePhoto } from '../../ui/common'
import { CountUp } from '../../ui/CountUp'
import { Icon } from '../../ui/icons'
import { BLOCK, costText, visits } from './shared'

// Side cards, notices and dialogs of the itinerary screens (screens/Plan.tsx, screens/plan/*).

export const ADVISORY: Record<string, string> = { storm: 'bão / dông', flood: 'ngập lụt', landslide: 'sạt lở', fire: 'cháy', road_closed: 'đường bị chặn', other: 'khác' }

export function TimeCard({ day, itinerary, timing, suggestions, status, busy, onAdd }: {
  day: number; itinerary: ItineraryDay | undefined; timing: TimeSuitabilityDay[]; suggestions: TimeRecommendation[];
  busy: boolean; onAdd: (id: string, day: number) => void
  status?: 'pending' | 'ready' | 'unavailable'
}) {
  const details = timing.find((x) => x.day === day)?.places.filter((p) => p.reasons.length || p.shortened_min) ?? []
  const optional = suggestions.filter((x) => x.day === day).slice(0, 3)
  if (!details.length && !optional.length && (!status || status === 'ready')) return null
  return <section className="tg-sidecard" aria-labelledby="tg-time-h">
    <h2 id="tg-time-h"><Icon name="clock" size={18} /> Giờ ghé · Ngày {day}</h2>
    {status === 'pending' && <p className="tg-faint" role="status">Đang tìm hoạt động phù hợp với giờ trống…</p>}
    {status === 'unavailable' && <p className="tg-faint">Chưa tải được gợi ý thêm hoạt động.</p>}
    {details.map((p) => <div className="tg-backup" key={p.place_id}>
      <b>{itinerary?.items.find((i) => i.place_id === p.place_id && i.kind === 'visit')?.name ?? info(p.place_id)?.name ?? p.place_id}</b>
      {p.reasons.map((r, i) => <span key={i}>{r.text}{r.fit !== null && r.fit < 1 ? ' · lịch chưa khớp hết khung giờ ưu tiên' : ''}</span>)}
      {p.shortened_min > 0 && <span>Rút khoảng {p.shortened_min} phút để vừa lịch, vẫn giữ thời lượng tối thiểu.</span>}
    </div>)}
    {optional.map((s, i) => <div className="tg-backup" key={i}>
      <span>{s.text}</span>
      {s.alternatives.map((a) => <button key={a.id} type="button" className="tg-btn tg-btn--soft tg-btn--sm"
        disabled={busy} onClick={() => onAdd(a.id, day)}>Thêm {a.name}{a.cost_unknown ? ' · chưa có giá' : ''}</button>)}
    </div>)}
    <p className="tg-faint tg-sidecard__mini">Độ phù hợp giờ là ước lượng. Thêm nơi sẽ xếp lại ngày này; bạn có thể hoàn tác.</p>
  </section>
}

export function KeepAll({ variant, busy, onPick }: { variant: NonNullable<import('../../planning/types').View['keep_all']>; busy: boolean; onPick: (id: string) => void }) {
  return <details className="tg-sidecard"><summary>Giữ tất cả · Đối chiếu danh sách ban đầu</summary>
    <p>{variant.kept?.length ?? variant.metrics.places} nơi · ≈{fmtMin(variant.metrics.travel_min)} di chuyển · {costText(variant)}{variant.metrics.cost_unknown ? ` + ${variant.metrics.cost_unknown} nơi chưa có giá` : ''} · {variant.robustness.label}</p>
    <p className="tg-faint">Cùng điểm xuất phát của lịch gốc. Chi phí địa điểm đã biết; thời gian đi lại là ước lượng.</p>
    {variant.violations.map((v, i) => <p key={i}>{v.detail}</p>)}
    {variant.itinerary.map(d => <div key={d.day}><b>Ngày {d.day}</b><ol>{d.items.map((it, i) => <li key={i}>{it.start}–{it.end} · {it.name ?? it.note ?? BLOCK[it.kind] ?? 'Di chuyển'}</li>)}</ol></div>)}
    <button type="button" className="tg-btn tg-btn--soft" disabled={busy || !variant.confirmable} onClick={() => onPick(variant.id)}>Chọn Giữ tất cả</button>
    {!variant.confirmable && <p className="tg-faint">Lịch gốc còn lỗi nên chưa thể chọn để chốt.</p>}
  </details>
}

export function Tradeoff({ variants, busy, active, onPick }: { variants: Variant[]; busy: boolean; active: string | null; onPick: (id: string) => void }) {
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
      <div role="row" className="tg-trade__r tg-trade__h"><span role="columnheader" /> {variants.map((v) => <button key={v.id} role="columnheader" type="button" className={active === v.id ? 'is-on' : ''} disabled={busy || v.status === 'unavailable'} onClick={() => onPick(v.id)}>{v.label}</button>)}</div>
      {rows.map(([label, f, best]) => (
        <div role="row" className="tg-trade__r" key={label}><span role="rowheader">{label}</span>{variants.map((v) => <span role="cell" key={v.id} className={best(v) ? 'is-best' : ''}>{f(v)}</span>)}</div>
      ))}
      <p className="tg-faint tg-trade__note">* Một phần chưa có giá. Giờ giấc và đường đi là ước tính.</p>
    </div>
  )
}

// Facts about the date, from live sources and hand-entered notices; no notice is not the same as "all clear".
export function Conditions({ c, tips }: { c: DayConditions | undefined; tips: CrowdTip[] }) {
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

export function VisitDuration({ place, name, minutes, bounds, manual, disabled, onPreview }: {
  place: string; name: string; minutes: number; bounds?: [number, number]; manual: boolean;
  disabled: boolean; onPreview: (place: string, minutes: number | null) => void
}) {
  const [value, setValue] = useState(String(minutes))
  if (!bounds) return null
  const valid = Number.isInteger(Number(value)) && Number(value) >= bounds[0] && Number(value) <= bounds[1]
  return <details className="tg-duration">
    <summary className="tg-link">{manual ? 'Thời lượng đã chỉnh' : 'Chỉnh thời lượng'}</summary>
    <p className="tg-faint">Ước lượng theo lựa chọn và nhịp chuyến đi. Chỉnh tay có thể ảnh hưởng các giờ ghé và bữa ăn.</p>
    <form onSubmit={e => { e.preventDefault(); if (valid && !disabled) onPreview(place, Number(value)) }}>
      <label>Thời gian ở {name} (phút)<input type="number" min={bounds[0]} max={bounds[1]} step="1" required value={value} disabled={disabled} onChange={e => setValue(e.target.value)} /></label>
      <div className="tg-duration__actions">
        {[30, 60, 90, 150].filter(n => n >= bounds[0] && n <= bounds[1]).map(n => <button key={n} type="button" className="tg-btn tg-btn--soft tg-btn--sm" disabled={disabled} aria-pressed={Number(value) === n} onClick={() => setValue(String(n))}>{n} phút</button>)}
        <button type="submit" className="tg-btn tg-btn--primary tg-btn--sm" disabled={disabled || !valid}>Xem ảnh hưởng</button>
        {manual && <button type="button" className="tg-link" disabled={disabled} onClick={() => onPreview(place, null)}>Dùng lại ước lượng</button>}
      </div>
      {!valid && <p className="tg-faint" role="status">Nhập số phút nguyên từ {bounds[0]} đến {bounds[1]}.</p>}
    </form>
  </details>
}

// No lodging picked: the plan is still laid out (days start at the first stop), the user is told and decides.
// The trip has no lodging yet: Lịch trình (not Lựa chọn) suggests a few of the stays Planning ranked for it, each
// picked here in one tap (pick_lodging); "Xem tất cả" opens the full list on Lựa chọn's Chỗ ở tab.
export function NoHotel({ onHotel }: { onHotel: () => void }) {
  const { view, act, busy } = usePlanning()
  const lod = view?.lodging
  const picks = lod?.candidates.slice(0, 3) ?? []
  return (
    <section className="tg-it-stays" aria-labelledby="tg-it-stays-h">
      <div className="tg-it-stays__head">
        <h3 id="tg-it-stays-h"><Icon name="bed" size={17} /> Gợi ý chỗ ở cho chuyến này</h3>
        <button type="button" className="tg-link" onClick={onHotel}>Xem tất cả chỗ ở</button>
      </div>
      <p className="tg-faint">Mỗi ngày bắt đầu và kết thúc ở chỗ ở; chọn một chỗ để lịch tính đường đi sáng và tối. Chưa chọn cũng không sao.</p>
      {lod?.status === 'pending' ? <p className="tg-faint" role="status">Đang tìm chỗ ở hợp với chuyến…</p>
        : picks.length === 0 ? <p className="tg-faint">Chưa có gợi ý chỗ ở cho chuyến này. Bạn tìm chỗ ở trong "Xem tất cả chỗ ở".</p>
        : (
          <ul className="tg-it-stays__list">
            {picks.map((c) => (
              <li key={c.id} className="tg-it-stay">
                {info(c.id) ? <PlacePhoto id={c.id} name={c.name} className="tg-it-stay__ph" /> : <span className="tg-it-stay__ph" aria-hidden="true"><Icon name="bed" size={22} /></span>}
                <div className="tg-it-stay__b">
                  <b>{c.name}</b>
                  <span className="tg-faint">{[c.rating ? `★ ${c.rating.toFixed(1)}` : null, c.price_vnd ? `${fmtVnd(c.price_vnd)}/đêm` : 'Chưa có giá', c.avg_min != null ? `≈ ${fmtMin(c.avg_min)} tới các nơi đã chọn` : null].filter(Boolean).join(' · ')}</span>
                  {c.fit?.[0] && <span className="tg-it-stay__why"><Icon name="check" size={13} /> {c.fit[0].text}</span>}
                </div>
                <button type="button" className="tg-btn tg-btn--primary tg-btn--sm" disabled={busy} onClick={() => { void act({ type: 'pick_lodging', id: c.id }) }}>Chọn</button>
              </li>
            ))}
          </ul>
        )}
    </section>
  )
}

export function Lodging({ onChange }: { onChange: () => void }) {
  const { view, busy } = usePlanning()
  if (!view) return null
  const point = view.state.lodging_point
  const placeId = typeof point?.place_id === 'string' ? point.place_id : null
  const name = view.state.lodging_id ? String(point?.text ?? view.lodging.candidates.find((c) => c.id === view.state.lodging_id)?.name ?? 'Chỗ ở đã chọn') : 'Chưa chọn chỗ ở'

  return (
    <section className="tg-sidecard" aria-labelledby="tg-lod-h">
      <h2 id="tg-lod-h"><Icon name="bed" size={18} /> Chỗ nghỉ đêm</h2>
      {placeId && info(placeId) && <PlacePhoto id={placeId} name={name} className="tg-sidecard__ph" />}
      <p><b>{name}</b><br /><small className="tg-faint">Mỗi ngày bắt đầu và kết thúc ở đây. Giá là tham khảo.</small></p>
      <button type="button" className="tg-link" disabled={busy} onClick={onChange}>{view.state.lodging_id ? 'Đổi chỗ ở' : 'Chọn chỗ ở'}</button>
    </section>
  )
}

// Backups of the day on screen: a stand-in for a place that may fail (rain, hours) and what to drop first when late.
export function BackupCard({ b, day, busy, onSwap }: { b: Backups | undefined; day: number; busy: boolean; onSwap: (place: string, w: string) => void | Promise<void> }) {
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
export function Optimize({ open, onClose, onUndo, busy }: { open: boolean; onClose: () => void; onUndo: () => void; busy: boolean }) {
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
