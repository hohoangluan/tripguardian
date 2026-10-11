import { useEffect, useState } from 'react'
import { coversOf, placeById, type Cover } from '../data/store'
import type { CrowdTable, PriceRange, Quote, Video } from '../data/types'

export const fmtMin = (m: number) => {
  const r = Math.round(m)
  if (r < 60) return `${r} phút`
  const h = Math.floor(r / 60)
  const mm = r % 60
  return mm ? `${h} giờ ${mm.toString().padStart(2, '0')}` : `${h} giờ`
}
// "60–90 phút" or "1,5–2,5 giờ": a range, because every visit time is an estimate
export const fmtRange = (lo: number, hi: number) => {
  if (hi <= 120) return `${lo}–${hi} phút`
  const h = (m: number) => (m / 60).toFixed(m % 60 ? 1 : 0).replace('.', ',')
  return `${h(lo)}–${h(hi)} giờ`
}
export const fmtClock = (m: number) => {
  const x = ((Math.round(m) % 1440) + 1440) % 1440
  return `${String(Math.floor(x / 60)).padStart(2, '0')}:${String(x % 60).padStart(2, '0')}`
}
export const fmtVnd = (n: number) => (n >= 1_000_000 ? `${(n / 1_000_000).toFixed(n % 1_000_000 ? 1 : 0).replace('.', ',')} triệu` : `${Math.round(n / 1000)}k`)
export const toMin = (hhmm: string) => {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + (m || 0)
}

export const DAY_NAMES = ['Chủ nhật', 'Thứ hai', 'Thứ ba', 'Thứ tư', 'Thứ năm', 'Thứ sáu', 'Thứ bảy']
// "2026-11-12" -> { wd: 'Thứ năm', dm: '12/11', weekend }; null when the trip has no date yet.
export function dayLabel(iso: string | null | undefined) {
  if (!iso) return null
  const d = new Date(iso + 'T00:00')
  if (Number.isNaN(d.getTime())) return null
  return { wd: DAY_NAMES[d.getDay()], dm: `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}`, weekend: d.getDay() === 0 || d.getDay() === 6 }
}
export function dateRange(start: string | null | undefined, days: number | null | undefined) {
  if (!start) return null
  const a = new Date(start + 'T00:00')
  if (Number.isNaN(a.getTime())) return null
  const b = new Date(a)
  b.setDate(a.getDate() + Math.max(1, days ?? 1) - 1)
  const f = (d: Date) => `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}`
  return days && days > 1 ? `${f(a)}–${f(b)}` : f(a)
}

export function useReducedMotion() {
  const [r, setR] = useState(() => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches)
  useEffect(() => {
    const m = matchMedia('(prefers-reduced-motion: reduce)')
    const on = () => setR(m.matches)
    m.addEventListener('change', on)
    return () => m.removeEventListener('change', on)
  }, [])
  return r
}
export const reducedMotion = () => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches

// ---------- place facts from the snapshot (public/data/snapshot.json + covers.json) ----------

// Rough Đà Lạt area from coordinates: a label for orientation, not an address.
export function areaOf(lat: number, lng: number) {
  if (lat > 12.0) return 'Lạc Dương'
  if (lng > 108.62) return 'Đèo Ngoạn Mục'
  if (lng > 108.55) return 'Cầu Đất'
  if (lat < 11.91 && lng < 108.46) return 'Tuyền Lâm'
  if (lng > 108.465) return 'Trại Mát'
  return 'Trung tâm'
}

export interface PlaceInfo {
  id: string
  name: string
  category: string | null
  group: string
  area: string
  lat: number
  lng: number
  rating: number | null
  reviews: number | null
  voices: number | null
  hours: string | null // one span shared by every day, else null (the full lines stay in hoursText)
  hoursText: string[]
  price: PriceRange | null
  crowd: CrowdTable | null
  photos: Cover[]
  quotes: Quote[]
  videos: Video[]
  mapsUrl: string | null
  asOf: string | null
}

const infoCache = new Map<string, PlaceInfo>()

export function info(id: string): PlaceInfo | null {
  const hit = infoCache.get(id)
  if (hit) return hit
  const p = placeById(id)
  if (!p) return null
  const spans = new Set(p.hoursText.map((l) => l.replace(/^[^\d]*/, '')).filter(Boolean))
  const quotes: Quote[] = []
  for (const f of [...p.features].filter((f) => f.status !== 'NEEDS_REVIEW' && f.status !== 'DISABLED').sort((a, b) => b.n - a.n))
    for (const q of f.quotes) if (q.text.length >= 25 && q.text.length <= 160 && quotes.length < 3) quotes.push(q)
  const out: PlaceInfo = {
    id: p.id,
    name: p.name,
    category: p.category,
    group: p.group,
    area: areaOf(p.lat, p.lng),
    lat: p.lat,
    lng: p.lng,
    rating: p.rating,
    reviews: p.reviewCount,
    voices: p.voices ?? null,
    hours: spans.size === 1 && p.hoursText.length >= 7 ? [...spans][0] : null,
    hoursText: p.hoursText,
    price: p.priceRange ?? null,
    crowd: p.crowdByTime ?? null,
    photos: coversOf(p.id),
    quotes,
    videos: p.videos,
    mapsUrl: p.mapsUrl,
    asOf: p.asOf ?? null,
  }
  infoCache.set(id, out)
  return out
}

// "120–250k", "đến 80k"; null when Google has no usable band.
export function priceText(pr: PriceRange | null | undefined) {
  if (!pr || !Number.isFinite(pr.max_vnd) || pr.max_vnd < 1000) return null
  const lo = !Number.isFinite(pr.min_vnd) || pr.min_vnd < 1000 ? null : pr.min_vnd
  return lo ? `${Math.round(lo / 1000)}–${Math.round(pr.max_vnd / 1000)}k` : `đến ${Math.round(pr.max_vnd / 1000)}k`
}

// Busiest weekend slot as % of the place's own peak (Google popular times), or null.
export const crowdOf = (p: PlaceInfo | null) => (p?.crowd?.weekend ? Math.max(...Object.values(p.crowd.weekend)) : null)

export const TRUST = { high: 'Cao', medium: 'Trung bình', low: 'Thấp' } as const
export type TrustLevel = (typeof TRUST)[keyof typeof TRUST]
