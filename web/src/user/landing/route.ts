// The landing's example day: real places from the snapshot (web/scripts/pick_landing_places.py).
import type { Cover } from '../../data/store'
import type { PriceRange } from '../../data/types'
import { thumbOf } from '../ui/common'
import raw from './places.json'
import type { ScenePlace } from './scene'

// `signals`: what people said about the place, with how many said it (the app's place card reads the same numbers)
export interface Signal { id: string; value: string; n: number }
export interface LPlace extends ScenePlace { id: string; category?: string; area?: string; photos: Cover[]; rating?: number; reviews?: number; price?: PriceRange; crowd?: { weekend?: Record<string, number> }; videos?: { url: string; handle: string }[]; signals?: Signal[] }
export const PLACES = raw as unknown as LPlace[]
export const byName = (n: string) => PLACES.find((p) => p.name.startsWith(n))!

// The example day, in visiting order. Times and stays are illustrative; places are real; the minutes between stops use
// the planner's rough estimate (config/planning.yaml: road_factor, rough_speed_kmh).
export const DAY: { name: string; at: string; stay: string; meal?: string }[] = [
  { name: 'Thiên Đường Săn Mây', at: '05:30', stay: '1 giờ 30' },
  { name: 'Tiệm cà phê Thênh Thang', at: '08:45', stay: '1 giờ' },
  { name: 'Hồ Xuân Hương', at: '11:00', stay: '1 giờ' },
  { name: 'An - Tuyền Lâm', at: '12:30', stay: '1 giờ', meal: 'Ăn trưa' },
  { name: 'Hồ Tuyền Lâm', at: '15:00', stay: '1 giờ 30' },
  { name: 'Hoàng hôn 3000', at: '17:15', stay: '1 giờ 30', meal: 'Ăn tối' },
]
export const ROUTE = DAY.map((d) => byName(d.name))
export const FOCUS = 1 // the place the reason card shows
export const ROAD_FACTOR = 1.4
export const SPEED_KMH = 25
export const AREAS: ScenePlace[] = [
  { name: 'Trung tâm', lat: 11.951, lng: 108.452 },
  { name: 'Langbiang', lat: 12.017, lng: 108.44 },
  { name: 'Cầu Đất', lat: 11.872, lng: 108.556 },
  { name: 'Trại Mát', lat: 11.948, lng: 108.505 },
  { name: 'Tuyền Lâm', lat: 11.884, lng: 108.412 },
]
// the example day as postcards on the map, each with its own real photo (the light thumbnail when there is one);
// the first photo of Hồ Xuân Hương is a night shot, so its postcard uses the daylight one
export const POSTCARD_PHOTO: Record<string, number> = { 'Hồ Xuân Hương': 1 }
export const SCENE_PLACES: ScenePlace[] = ROUTE.map((p) => {
  const ph = p.photos[POSTCARD_PHOTO[p.name] ?? 0]
  return { name: p.name, lat: p.lat, lng: p.lng, photo: ph && (thumbOf(ph.src) ?? ph.src) }
})
