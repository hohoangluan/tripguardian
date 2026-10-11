import { featureLabel, TIME_VI, valueLabel } from '../../data/labels'
import { VEHICLE_LABEL } from '../../data/store'
import { WHO_LABEL, type Who } from '../trip'
import type { HardRow, SoftRow } from './types'

export const FIELD_LABEL: Record<string, string> = {
  dates: 'Ngày đi', start_date: 'Ngày đi', month: 'Tháng', days: 'Số ngày', companions: 'Đi với ai', people: 'Số người',
  base: 'Chỗ ở', mobility: 'Đi lại', arrive_at: 'Ngày đầu tới', leave_at: 'Ngày cuối rời', day_end: 'Mỗi ngày xong trước',
  purpose: 'Mục đích', pace: 'Nhịp độ', max_leg_min: 'Mỗi chặng tối đa', crowd_tolerance: 'Chỗ đông', novelty: 'Mới hay quen',
  budget_vnd: 'Ngân sách', origin: 'Xuất phát', arrival_mode: 'Tới Đà Lạt bằng', inbound: 'Chuyến đi', outbound: 'Chuyến về',
  lodging_booked: 'Chỗ ở', lodging: 'Chỗ ở',
}
export const ARRIVAL_LABEL: Record<string, string> = { self: 'Tự đi (xe máy, ô tô)', bus: 'Xe khách', plane: 'Máy bay' }
const LODGING_BOOKED_LABEL: Record<string, string> = { yes: 'Đã đặt', no: 'Chưa có, nhờ gợi ý' }
const hhmm = (t: string) => t.slice(11, 16)
export const PURPOSE_LABEL: Record<string, string> = {
  relax: 'Nghỉ ngơi', bond: 'Gắn kết', photo: 'Chụp ảnh', food_culture: 'Ẩm thực, văn hóa', nature: 'Thiên nhiên',
  explore: 'Khám phá', adventure: 'Mạo hiểm',
}
export const PACE_LABEL: Record<string, string> = { slow: 'Thong thả', normal: 'Vừa phải', packed: 'Đi nhiều' }
export const CROWD_LABEL: Record<string, string> = { avoid: 'Tránh', ok_if_worth: 'Nếu đáng', fine: 'Không ngại' }
export const NOVELTY_LABEL: Record<string, string> = { familiar: 'Quen', new: 'Mới', mix: 'Trộn' }
const HARD_TEXT: Record<string, string> = {
  steep_or_stairs: 'Tránh dốc, bậc thang', long_walk: 'Không đi bộ xa', vegetarian_options: 'Có món chay',
}

export function valueText(target: string, v: any): string {
  if (target === 'companions') return (v as Who[]).map((w) => WHO_LABEL[w] ?? w).join(', ')
  if (target === 'mobility') return VEHICLE_LABEL[v as keyof typeof VEHICLE_LABEL] ?? v
  if (target === 'start_date') return new Date(v + 'T00:00').toLocaleDateString('vi-VN')
  if (target === 'month') return `tháng ${v}`
  if (target === 'days') return `${v} ngày`
  if (target === 'people') return `${v} người`
  if (target === 'base' || target === 'origin' || target === 'lodging') return v.name ?? v.text
  if (target === 'arrival_mode') return ARRIVAL_LABEL[v] ?? v
  if (target === 'lodging_booked') return LODGING_BOOKED_LABEL[v] ?? v
  // a chosen coach / flight: "Vietjet Air 06:10 → 07:05"
  if (target === 'inbound' || target === 'outbound') return `${v.carrier} ${hhmm(v.depart_at)} → ${hhmm(v.arrive_at)}`
  if (target === 'max_leg_min') return `${v} phút`
  if (target === 'budget_vnd') return `${Math.round(v / 1000)} nghìn / người / ngày`
  if (target === 'purpose') return PURPOSE_LABEL[v] ?? v
  if (target === 'pace') return PACE_LABEL[v] ?? v
  if (target === 'crowd_tolerance') return CROWD_LABEL[v] ?? v
  if (target === 'novelty') return NOVELTY_LABEL[v] ?? v
  return String(v)
}

function softBase(s: SoftRow) {
  const base = s.value === 'present' ? featureLabel(s.feature) : `${featureLabel(s.feature)}: ${valueLabel(s.value)}`
  const when = Object.values(s.context).map((c) => TIME_VI[c] ?? c)
  return base + (when.length ? ` · ${when.join(', ')}` : '')
}

export function softText(s: SoftRow) {
  return (s.weight === 'avoid' ? 'Tránh: ' : '') + softBase(s) + (s.like ? ` (giống ${s.like})` : '')
}

// Tastes read from one compared place show as one chip: "Tránh: ồn, đông (giống X)"; every other taste is its own chip.
export function softGroups(rows: SoftRow[]): { key: string; rows: SoftRow[]; text: string }[] {
  const out: { key: string; rows: SoftRow[]; text: string }[] = []
  const by = new Map<string, SoftRow[]>()
  for (const s of rows) {
    if (!s.like) { out.push({ key: s.target, rows: [s], text: softText(s) }); continue }
    const k = `${s.like}|${s.weight}`
    if (!by.has(k)) { const g: SoftRow[] = []; by.set(k, g); out.push({ key: `like:${k}`, rows: g, text: '' }) }
    by.get(k)!.push(s)
  }
  for (const g of out)
    if (!g.text) g.text = (g.rows[0].weight === 'avoid' ? 'Tránh: ' : '') + g.rows.map(softBase).join(', ') + ` (giống ${g.rows[0].like})`
  return out
}

export const hardText = (h: HardRow) =>
  HARD_TEXT[h.feature] ?? `${featureLabel(h.feature)} ${h.op === 'ne' ? 'khác' : 'là'} ${valueLabel(h.value)}`

// "−1.384 nơi" / "+120 nơi": a change in the matching count, with a real minus sign.
export const placesDelta = (n: number) => `${n < 0 ? '−' : '+'}${Math.abs(n).toLocaleString('vi-VN')} nơi`
