import { useEffect, useState } from 'react'
import type { DayKey, Place, PriceRange, Signal, Snapshot } from './types'

let cache: Promise<Snapshot> | null = null
let ready: Snapshot | null = null

export function loadSnapshot() {
  cache ??= fetch('/data/covers.json')
    .then((r) => (r.ok ? r.json() : {}))
    .then((c) => (covers = c), () => {})
    .then(() => fetch('/data/snapshot.json'))
    .then((r) => {
      if (!r.ok) throw new Error(`snapshot ${r.status}`)
      return r.json() as Promise<Snapshot>
    })
    .then((s) => {
      ready = s
      byId = new Map(s.places.map((p) => [p.id, p]))
      return s
    })
  return cache
}

let byId = new Map<string, Place>()
export const placeById = (id: string) => byId.get(id)

// Cover images picked offline by web/scripts/pick_covers.py: Maps photos or clip frames without people in them.
export interface Cover {
  src: string
  credit: string
  kind: 'gmaps' | 'tiktok'
  w: number
  h: number
  url?: string
}
let covers: Record<string, Cover[]> = {}
export const coversOf = (id: string): Cover[] => covers[id] ?? []

export function useSnapshot() {
  const [snap, setSnap] = useState<Snapshot | null>(ready)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (ready) return
    loadSnapshot().then(setSnap, (e) => setError(String(e)))
  }, [])
  return { snap, error }
}

// ---------- place helpers ----------

export type Section = 'sight' | 'nature' | 'food' | 'shop'

export const SECTION_LABEL: Record<Section, string> = {
  sight: 'Điểm tham quan',
  nature: 'Thiên nhiên và view',
  food: 'Ăn uống và cà phê',
  shop: 'Mua sắm, đặc sản',
}

const NATURE_CATS = ['Đỉnh núi', 'Vườn', 'Thác', 'Hồ', 'Đồi', 'Rừng', 'Thung lũng', 'Trang trại', 'Cánh đồng', 'Khu bảo tồn', 'Công viên']

export function sectionOf(p: Place): Section | null {
  if (p.group === 'food') return 'food'
  if (p.group === 'shop') return 'shop'
  if (p.group !== 'sight') return null
  const c = p.category ?? ''
  if (NATURE_CATS.some((n) => c.startsWith(n))) return 'nature'
  const nat = p.features.find((f) => f.id === 'nature' || f.id === 'scenic_view')
  return nat && nat.n >= 3 ? 'nature' : 'sight'
}

// User-visible signals: NEEDS_REVIEW and DISABLED are never shown (UX brief §4).
export const visible = (p: Place) => p.features.filter((f) => f.status !== 'NEEDS_REVIEW' && f.status !== 'DISABLED')

export const signal = (p: Place, id: string): Signal | undefined => visible(p).find((f) => f.id === id)

export function has(p: Place, id: string, value = 'present') {
  const s = signal(p, id)
  return !!s && s.value === value
}

// Visit length is always a range (UX brief §4, Estimate).
export function visitRange(p: Place): [number, number] {
  const c = p.category ?? ''
  if (c.startsWith('Đỉnh núi') || has(p, 'hiking')) return [120, 180]
  if (sectionOf(p) === 'nature') return [60, 120]
  if (c.startsWith('Vườn dâu') || has(p, 'pick_your_own')) return [45, 75]
  if (p.group === 'sight') return [60, 120]
  if (c.startsWith('Quán cà phê') || c.includes('cà phê')) return has(p, 'long_stay_chill') ? [60, 120] : [45, 90]
  if (p.group === 'food') return [45, 90]
  if (p.group === 'shop') return [30, 60]
  return [45, 90]
}

export type Confidence = 'Cao' | 'Trung bình' | 'Thấp'

export function confidenceOf(p: Place): { level: Confidence; reason: string } {
  if (p.kind === 'inventory') return { level: 'Thấp', reason: 'Chỉ có thông tin cơ bản từ Google, chưa có bằng chứng trải nghiệm.' }
  const vis = visible(p)
  const strong = vis.filter((f) => f.status === 'VERIFIED' && f.n >= 3).length
  const voices = p.voices ?? 0
  const sources = new Set(vis.flatMap((f) => f.sourceTypes)).size + (p.videos.length ? 1 : 0)
  const month = p.asOf ? new Date(p.asOf).toLocaleDateString('vi-VN', { month: 'numeric', year: 'numeric' }) : ''
  const reason = `${voices} người đã viết về nơi này, ${sources} loại nguồn, kiểm tra tháng ${month}.`
  if (strong >= 6 && voices >= 40) return { level: 'Cao', reason }
  if (strong >= 3) return { level: 'Trung bình', reason }
  return { level: 'Thấp', reason }
}

// Google's reported price band, e.g. "100.000–200.000 đ/người".
export function priceText(r: PriceRange) {
  const k = (n: number) => n.toLocaleString('vi-VN')
  const band = r.min_vnd <= 1 ? `Dưới ${k(r.max_vnd)} đ` : `${k(r.min_vnd)}–${k(r.max_vnd)} đ`
  return `${band}${r.per === 'person' ? '/người' : ''}`
}

// ---------- hours ----------

export const DAYS: DayKey[] = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']
const VI_DAYS: Record<string, DayKey> = {
  'Chủ Nhật': 'sun',
  'Thứ Hai': 'mon',
  'Thứ Ba': 'tue',
  'Thứ Tư': 'wed',
  'Thứ Năm': 'thu',
  'Thứ Sáu': 'fri',
  'Thứ Bảy': 'sat',
}

const toMin = (hhmm: string) => {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + (m || 0)
}

// Opening windows in minutes for a weekday, or null when unknown (never assume "open").
export function openWindows(p: Place, day: DayKey): [number, number][] | null {
  if (p.hours && p.hours[day]) return p.hours[day]!.map(([a, b]) => [toMin(a), b === '00:00' ? 24 * 60 : toMin(b)])
  for (const line of p.hoursText) {
    const name = Object.keys(VI_DAYS).find((d) => line.startsWith(d))
    if (!name || VI_DAYS[name] !== day) continue
    const rest = line.slice(name.length).trim()
    if (/Mở cửa 24 giờ/i.test(rest)) return [[0, 24 * 60]]
    if (/Đóng cửa/i.test(rest)) return []
    const spans = [...rest.matchAll(/(\d{1,2}:\d{2})\s*[–-]\s*(\d{1,2}:\d{2})/g)].map(
      (m) => [toMin(m[1]), toMin(m[2]) <= toMin(m[1]) ? 24 * 60 : toMin(m[2])] as [number, number],
    )
    return spans.length ? spans : null
  }
  return null
}

export const fmtTime = (min: number) => {
  const m = ((Math.round(min) % 1440) + 1440) % 1440
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`
}

export const fmtDuration = (min: number) => {
  const m = Math.round(min)
  if (m < 60) return `${m} phút`
  const h = Math.floor(m / 60)
  const r = m % 60
  return r ? `${h} giờ ${r} phút` : `${h} giờ`
}

// ---------- geography ----------

export const CENTER = { lat: 11.9404, lng: 108.4583 } // Chợ Đà Lạt area

export function km(a: { lat: number; lng: number }, b: { lat: number; lng: number }) {
  const R = 6371
  const dLat = ((b.lat - a.lat) * Math.PI) / 180
  const dLng = ((b.lng - a.lng) * Math.PI) / 180
  const s = Math.sin(dLat / 2) ** 2 + Math.cos((a.lat * Math.PI) / 180) * Math.cos((b.lat * Math.PI) / 180) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(s))
}

export type Vehicle = 'motorbike' | 'car' | 'ride'
export const VEHICLE_LABEL: Record<Vehicle, string> = { motorbike: 'Xe máy', car: 'Ô tô', ride: 'Xe công nghệ' }
const SPEED: Record<Vehicle, number> = { motorbike: 26, car: 24, ride: 24 } // km/h on Da Lat roads
const BUFFER: Record<Vehicle, number> = { motorbike: 5, car: 10, ride: 8 } // parking / pickup

// Estimated travel minutes: straight line x 1.5 for winding highland roads. Always shown as an estimate.
export function travelMin(a: { lat: number; lng: number }, b: { lat: number; lng: number }, v: Vehicle) {
  const d = km(a, b) * 1.5
  if (d < 0.25) return 3
  return Math.round((d / SPEED[v]) * 60 + BUFFER[v])
}

export function mapsEmbed(q: { lat: number; lng: number } | string, zoom = 15) {
  const query = typeof q === 'string' ? encodeURIComponent(q) : `${q.lat},${q.lng}`
  return `https://maps.google.com/maps?q=${query}&z=${zoom}&hl=vi&output=embed`
}

export function mapsRouteEmbed(stops: { lat: number; lng: number }[]) {
  if (stops.length < 2) return stops[0] ? mapsEmbed(stops[0], 13) : ''
  const [first, ...rest] = stops
  const daddr = rest.map((s) => `${s.lat},${s.lng}`).join('+to:')
  return `https://maps.google.com/maps?saddr=${first.lat},${first.lng}&daddr=${daddr}&hl=vi&output=embed`
}

export function mapsRouteLink(stops: { lat: number; lng: number }[]) {
  return `https://www.google.com/maps/dir/${stops.map((s) => `${s.lat},${s.lng}`).join('/')}`
}
