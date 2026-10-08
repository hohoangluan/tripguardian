import { useEffect, useState } from 'react'
import { findTransit, watchTransit } from '../tu/api'
import type { Transit, TransitParams, TransitResult } from '../tu/types'
import { Icon } from './icons'

// The coach / flight question (docs/TRIP_UNDERSTANDING.md §Hậu cần): trips come from a crawl, read from the cache or
// fetched live while a skeleton shows. Nothing found → the booking site with the route filled in, and a typed time.

type Filter = 'all' | 'morning' | 'afternoon' | 'night' | 'cheap'
const FILTERS: { id: Filter; label: string }[] = [
  { id: 'all', label: 'Tất cả' }, { id: 'morning', label: 'Sáng' }, { id: 'afternoon', label: 'Chiều' }, { id: 'night', label: 'Đêm' }, { id: 'cheap', label: 'Rẻ nhất' },
]
const FIRST = 6

const clock = (t: string) => t.slice(11, 16)
const hour = (t: string) => Number(t.slice(11, 13))
// An overnight coach read with the same date on both ends still lasts until the next morning.
const minutes = (a: string, b: string) => { const m = Math.round((new Date(b).getTime() - new Date(a).getTime()) / 60000); return m < 0 ? m + 1440 : m }
const span = (m: number) => (m >= 60 ? `${Math.floor(m / 60)}h${m % 60 ? String(m % 60).padStart(2, '0') : ''}` : `${m} phút`)
const vnd = (n: number) => `${n.toLocaleString('vi-VN')} ₫`
// "giá tham khảo lúc 21:05 08/10": when the price was read, in Vietnam time.
function readAt(iso: string) {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  const v = (o: Intl.DateTimeFormatOptions) => d.toLocaleString('en-GB', { timeZone: 'Asia/Ho_Chi_Minh', hour12: false, ...o })
  return `${v({ hour: '2-digit' })}:${v({ minute: '2-digit' }).padStart(2, '0')} ${v({ day: '2-digit' })}/${v({ month: '2-digit' })}`
}
const keep = (f: Filter, t: Transit) => {
  const h = hour(t.depart_at)
  if (f === 'morning') return h >= 5 && h < 12
  if (f === 'afternoon') return h >= 12 && h < 18
  if (f === 'night') return h >= 18 || h < 5
  return true
}
export const transitLabel = (t: Transit) => `${t.carrier} ${clock(t.depart_at)} → ${clock(t.arrive_at)}`

export function TransitPick({ params, way, busy, onPick, onTime, onSkip }: {
  params: TransitParams
  way: 'inbound' | 'outbound'
  busy: boolean
  onPick: (t: Transit) => void
  onTime: (hhmm: string) => void
  onSkip: () => void
}) {
  const [res, setRes] = useState<TransitResult | null>(null)
  const [filter, setFilter] = useState<Filter>('all')
  const [more, setMore] = useState(false)
  const [time, setTime] = useState('')
  const key = `${params.mode}|${params.from}|${params.to}|${params.date}|${params.lat}|${params.lng}`
  useEffect(() => {
    let live = true
    let stop = () => {}
    setRes(null)
    findTransit(params).then(
      (r) => {
        if (!live) return
        setRes(r)
        if (r.status === 'pending') stop = watchTransit(params, (x) => live && setRes(x))
      },
      () => live && setRes({ status: 'unavailable', trips: [], book_url: null }),
    )
    return () => { live = false; stop() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  const plane = params.mode === 'plane'
  const site = plane ? 'Google Flights' : 'Vexere'
  if (!res || res.status === 'pending')
    return (
      <div className="tg-trn" aria-busy="true">
        <p className="tg-faint tg-trn__wait" role="status"><span className="tg-dots" aria-hidden="true"><i /><i /><i /></span> Đang tra {plane ? 'chuyến bay' : 'chuyến xe'} trên {site}… thường mất dưới một phút.</p>
        <ul className="tg-trn__list">{Array.from({ length: 3 }, (_, i) => <li key={i} className="tg-trn__skel"><span className="tg-skel" /><span className="tg-skel" /></li>)}</ul>
        <button type="button" className="tg-chip tg-chip--dash" disabled={busy} onClick={onSkip}>Tôi tự lo phần này</button>
      </div>
    )

  if (res.status === 'unavailable' || !res.trips.length)
    return (
      <div className="tg-trn">
        <div className="tg-trn__none">
          <p><b>Mình chưa tra được {plane ? 'chuyến bay' : 'chuyến xe'} cho ngày này.</b> Bạn xem trực tiếp trên {site}, rồi cho mình biết giờ {way === 'inbound' ? 'tới Đà Lạt' : 'rời Đà Lạt'}.</p>
          {res.book_url && <a className="tg-btn tg-btn--soft tg-btn--sm" href={res.book_url} target="_blank" rel="noopener noreferrer">Mở {site} <Icon name="external" size={15} /></a>}
        </div>
        <form className="tg-trn__time" onSubmit={(e) => { e.preventDefault(); if (time) onTime(time) }}>
          <label><span>{way === 'inbound' ? 'Giờ tới Đà Lạt' : 'Giờ rời Đà Lạt'}</span><input className="tg-input" type="time" value={time} onChange={(e) => setTime(e.target.value)} /></label>
          <button type="submit" className="tg-btn tg-btn--primary tg-btn--sm" disabled={busy || !time}>Xong câu này</button>
        </form>
        <button type="button" className="tg-chip tg-chip--dash" disabled={busy} onClick={onSkip}>Tôi tự lo phần này</button>
      </div>
    )

  let trips = res.trips.filter((t) => keep(filter, t))
  trips = filter === 'cheap'
    ? [...res.trips].filter((t) => t.price_vnd !== null).sort((a, b) => a.price_vnd! - b.price_vnd!)
    : [...trips].sort((a, b) => a.depart_at.localeCompare(b.depart_at))
  const shown = more ? trips : trips.slice(0, FIRST)
  const cheapest = Math.min(...res.trips.map((t) => t.price_vnd ?? Infinity))
  return (
    <div className="tg-trn">
      <div className="tg-trn__filters" role="group" aria-label="Lọc nhanh">
        {FILTERS.map((f) => <button key={f.id} type="button" className="tg-chip" aria-pressed={filter === f.id} onClick={() => { setFilter(f.id); setMore(false) }}>{f.label}</button>)}
        <span className="tg-faint tg-trn__count">{trips.length} / {res.trips.length} chuyến</span>
      </div>
      {shown.length ? (
        <ul className="tg-trn__list">
          {shown.map((t, i) => (
            <li key={`${t.carrier}-${t.depart_at}-${i}`} className="tg-trn__row">
              <div className="tg-trn__main">
                <span className="tg-trn__who"><Icon name={plane ? 'plane' : 'bus'} size={16} /> <b>{t.carrier}</b>{t.price_vnd !== null && t.price_vnd === cheapest && <em className="tg-trn__tag">Rẻ nhất</em>}</span>
                <span className="tg-trn__when tg-mono"><b>{clock(t.depart_at)}</b><i aria-hidden="true" /><small>{span(minutes(t.depart_at, t.arrive_at))}</small><i aria-hidden="true" /><b>{clock(t.arrive_at)}</b>{(t.arrive_at.slice(0, 10) > t.depart_at.slice(0, 10) || t.arrive_at < t.depart_at) && <sup title="Tới vào hôm sau">+1</sup>}</span>
                <span className="tg-trn__where">{t.from_point} → {t.to_point}</span>
              </div>
              <div className="tg-trn__buy">
                <b className="tg-mono">{t.price_vnd !== null ? vnd(t.price_vnd) : 'Chưa có giá'}</b>
                <small className="tg-faint">giá tham khảo lúc {readAt(t.fetched_at)}, kiểm lại khi đặt</small>
                <button type="button" className="tg-btn tg-btn--primary tg-btn--sm" disabled={busy} onClick={() => onPick(t)}>Chọn chuyến này</button>
              </div>
            </li>
          ))}
        </ul>
      ) : <p className="tg-faint">Không có chuyến nào trong khung giờ này.</p>}
      {trips.length > FIRST && !more && <button type="button" className="tg-link" onClick={() => setMore(true)}>Xem thêm {trips.length - FIRST} chuyến</button>}
      <div className="tg-trn__end">
        <button type="button" className="tg-chip tg-chip--dash" disabled={busy} onClick={onSkip}>Tôi tự lo phần này</button>
        {res.book_url && <a className="tg-link" href={res.book_url} target="_blank" rel="noopener noreferrer">Xem trên {site} <Icon name="external" size={14} /></a>}
      </div>
    </div>
  )
}
