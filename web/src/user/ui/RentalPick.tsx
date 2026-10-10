import { useEffect, useState } from 'react'
import { Icon } from './icons'

// Motorbike rental points near where a coach / flight drops the trip (docs/P4_PLANNING.md §Thuê xe máy). Only shops the
// corpus holds are listed; none -> say so and point at Google Maps, never an invented shop.

export interface RentalParams { mode: 'bus' | 'plane'; lat?: number; lng?: number; text?: string }
interface Point { id: string; name: string; address: string | null; lat: number; lng: number; km: number; near_hub: boolean; hours_known: boolean; maps_url: string }
interface Rentals { status: 'ready' | 'none'; hub: { text: string; lat: number; lng: number }; points: Point[] }

const query = (p: RentalParams) =>
  new URLSearchParams({ mode: p.mode, ...(p.lat != null && p.lng != null ? { lat: String(p.lat), lng: String(p.lng), ...(p.text ? { text: p.text } : {}) } : {}) }).toString()
const km = (n: number) => (n < 1 ? `${Math.round(n * 1000)} m` : `${n.toLocaleString('vi-VN')} km`)

export function RentalPick({ params }: { params: RentalParams }) {
  const [res, setRes] = useState<Rentals | 'failed' | null>(null)
  const key = query(params)
  useEffect(() => {
    let live = true
    setRes(null)
    fetch(`/api/harness/rentals?${key}`)
      .then((r) => (r.ok ? (r.json() as Promise<Rentals>) : Promise.reject(new Error(String(r.status)))))
      .then((r) => live && setRes(r), () => live && setRes('failed'))
    return () => { live = false }
  }, [key])

  const where = params.mode === 'plane' ? 'sân bay' : 'bến xe'
  if (!res) return <p className="tg-faint tg-trn__wait" role="status"><span className="tg-dots" aria-hidden="true"><i /><i /><i /></span> Đang tìm điểm thuê xe máy gần {where}…</p>
  if (res === 'failed' || res.status === 'none') {
    const q = encodeURIComponent(`thuê xe máy gần ${params.text ?? (params.mode === 'plane' ? 'Sân bay Liên Khương' : 'Bến xe Liên tỉnh Đà Lạt')}`)
    return (
      <div className="tg-trn__none">
        <p><b>Mình chưa có điểm thuê xe máy nào trong dữ liệu cho khu này.</b> Bạn tìm trực tiếp trên Google Maps rồi hỏi giá và giờ nhận xe.</p>
        <a className="tg-btn tg-btn--soft tg-btn--sm" href={`https://www.google.com/maps/search/${q}`} target="_blank" rel="noopener noreferrer">Tìm trên Google Maps <Icon name="external" size={15} /></a>
      </div>
    )
  }
  const near = res.points.some((p) => p.near_hub)
  return (
    <div className="tg-trn">
      <p className="tg-faint tg-trn__wait">
        {near ? `Điểm thuê xe máy gần ${res.hub.text}` : `Mình không thấy điểm thuê nào gần ${res.hub.text}; đây là các điểm thuê gần nhất trong thành phố`}. Giá và giờ nhận xe bạn hỏi trực tiếp.
      </p>
      <ul className="tg-trn__list">
        {res.points.map((p) => (
          <li key={p.id} className="tg-trn__row">
            <div className="tg-trn__main">
              <span className="tg-trn__who"><Icon name="bike" size={16} /> <b>{p.name}</b>{p.near_hub && <em className="tg-trn__tag">Gần {where}</em>}</span>
              <span className="tg-trn__where">{p.address ?? 'Chưa có địa chỉ'}{p.hours_known ? '' : ' · chưa rõ giờ mở cửa'}</span>
            </div>
            <div className="tg-trn__buy">
              <b className="tg-mono">{km(p.km)}</b>
              <small className="tg-faint">từ {res.hub.text}, đường chim bay</small>
              <a className="tg-btn tg-btn--soft tg-btn--sm" href={p.maps_url} target="_blank" rel="noopener noreferrer">Mở bản đồ <Icon name="external" size={14} /></a>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
