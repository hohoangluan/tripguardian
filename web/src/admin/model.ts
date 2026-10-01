import { featureLabel } from '../data/labels'
import { placeById } from '../data/store'
import type { Place, ReviewItem, Signal, Status } from '../data/types'

export const STATUS_ORDER: Status[] = ['NEEDS_REVIEW', 'UNCERTAIN', 'OUTDATED', 'VERIFIED']

// Validated status palette (dataviz validator, light surface); always paired with a text label.
export const STATUS_COLOR: Record<Status, string> = {
  VERIFIED: '#0f8a5f',
  UNCERTAIN: '#6f4fa0',
  OUTDATED: '#c98a12',
  NEEDS_REVIEW: '#b8382b',
  DISABLED: '#5b6763',
}

export function worstStatus(p: Place): Status | null {
  if (!p.features.length) return null
  return STATUS_ORDER.find((s) => p.features.some((f) => f.status === s)) ?? 'VERIFIED'
}

export type Risk = 'Cao' | 'Vừa' | 'Thấp'
const SAFETY = new Set(['kids', 'elderly', 'steep_or_stairs', 'rough_road_access', 'tourist_trap', 'weather_exposed', 'long_walk'])

export function riskOf(r: ReviewItem): Risk {
  if (r.kind === 'permissive_check' || r.kind === 'conflict') return 'Cao'
  if (r.kind === 'proposed_feature') return 'Thấp'
  return SAFETY.has(r.feature) ? 'Cao' : 'Vừa'
}

// The hidden sample must read exactly like a real item: no field depends on `sample`.
export const KIND_LABEL: Record<ReviewItem['kind'], string> = {
  judge_flag: 'Judge đánh dấu',
  permissive_check: 'Kiểm tra đối tượng',
  conflict: 'Xung đột nguồn',
  proposed_feature: 'Feature đề xuất',
}

export function whyOf(r: ReviewItem) {
  switch (r.kind) {
    case 'judge_flag':
      return 'Giá trị cần người xác nhận trước khi phục vụ người dùng.'
    case 'permissive_check':
      return 'Giá trị về đối tượng phù hợp luôn cần người kiểm tra.'
    case 'conflict':
      return 'Nguồn khai báo và người dùng nói khác nhau.'
    case 'proposed_feature':
      return `Chưa có trong ontology, ${r.value}.`
  }
}

export function signalOf(r: ReviewItem): { place: Place | undefined; signal: Signal | undefined } {
  const place = placeById(r.placeId)
  return { place, signal: place?.features.find((f) => f.id === r.feature) }
}

export const itemTitle = (r: ReviewItem) => (r.kind === 'proposed_feature' ? r.feature : featureLabel(r.feature))

export const fmtAgo = (iso: string | null | undefined) => {
  if (!iso) return '—'
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (mins < 60) return `${mins} phút trước`
  if (mins < 60 * 24) return `${Math.round(mins / 60)} giờ trước`
  return `${Math.round(mins / 1440)} ngày trước`
}
