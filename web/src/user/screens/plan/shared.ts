import { navigate } from '../../../router'
import { fmtVnd, info } from '../../lib'
import type { ItineraryDay, Variant } from '../../planning/types'

export const visits = (d: ItineraryDay) => d.items.filter((it) => it.kind === 'visit' && it.place_id)
export const costText = (v: Variant) => (v.metrics.cost_vnd ? `~${fmtVnd(v.metrics.cost_vnd)}` : 'Chưa có giá')

// "2026-10-13" -> "13 thg 10"; the day number when the trip has no date yet.
export function shortDate(iso: string | null | undefined, day?: number) {
  const d = iso ? new Date(iso + 'T00:00') : null
  if (!d || Number.isNaN(d.getTime())) return day ? `Ngày ${day}` : ''
  return `${d.getDate()} thg ${d.getMonth() + 1}`
}

// "Xem chi tiết" opens the place sheet over the current screen (?place=<id>), so the plan keeps its place.
export function openPlace(id: string) {
  const q = new URLSearchParams(location.search)
  q.set('place', id)
  navigate(`${location.pathname}?${q}`)
}

export const placeName = (id: string, fallback?: string) => fallback ?? info(id)?.name ?? id

// The few areas a day passes through, in order: a title for a day that has no theme of its own.
export function dayAreas(d: ItineraryDay) {
  const out: string[] = []
  for (const it of visits(d)) {
    const a = info(it.place_id!)?.area
    if (a && !out.includes(a)) out.push(a)
  }
  return out
}

export const norm = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/đ/g, 'd').toLowerCase()

export const BLOCK: Record<string, string> = { meal_free: 'Ăn (tự chọn)', rest: 'Nghỉ', wait: 'Chờ', free: 'Tự do quanh đây', buffer: 'Đệm' }
export const BLOCK_NOTE: Record<string, string> = { meal_free: 'Ăn ngoài hoặc hỏi chỗ ở có phục vụ bữa này; dịch vụ và giá chưa xác nhận.', rest: 'Nghỉ chân, về chỗ ở hoặc ngồi lại.', wait: 'Chờ tới khung giờ ghé hoặc giờ mở cửa.', free: 'Thời gian tự do trước khi di chuyển tới điểm kế tiếp.', buffer: 'Thời gian dự phòng, trễ một chút vẫn ổn.' }
export const MEAL_LABEL: Record<string, string> = { breakfast: 'Ăn sáng (tự chọn)', lunch: 'Ăn trưa (tự chọn)', dinner: 'Ăn tối (tự chọn)' }
