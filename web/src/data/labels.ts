// Plain-Vietnamese labels for ontology ids (config/ontology.yaml). UI copy only.

export const FEATURE: Record<string, string> = {
  scenic_view: 'View đẹp',
  cloud_hunting: 'Săn mây',
  sunset_view: 'Ngắm hoàng hôn',
  photo_spot: 'Nhiều góc chụp',
  nature: 'Thiên nhiên',
  flower_garden: 'Vườn hoa',
  heritage_architecture: 'Kiến trúc, di tích',
  cozy_decor: 'Không gian xinh',
  laptop_friendly: 'Ngồi làm việc được',
  long_stay_chill: 'Ngồi lâu, chill',
  live_music: 'Nhạc sống',
  adventure_activity: 'Trò mạo hiểm',
  hiking: 'Leo núi, trekking',
  animals: 'Có thú để chơi',
  local_specialty_food: 'Món đặc sản',
  food_quality: 'Đồ ăn',
  drink_quality: 'Đồ uống',
  hands_on_workshop: 'Workshop tự làm',
  pick_your_own: 'Tự hái tại vườn',
  cultural_show: 'Biểu diễn văn hóa',
  camping: 'Cắm trại',
  crowd: 'Độ đông',
  noise: 'Độ ồn',
  setting: 'Trong nhà hay ngoài trời',
  cleanliness: 'Sạch sẽ',
  weather_exposed: 'Phụ thuộc thời tiết',
  parking: 'Gửi xe',
  toilet: 'Nhà vệ sinh',
  outdoor_seating: 'Chỗ ngồi ngoài trời',
  spacious: 'Rộng, thoáng',
  service_attitude: 'Thái độ phục vụ',
  service_quality: 'Chất lượng dịch vụ',
  value_for_money: 'Đáng tiền',
  tourist_trap: 'Bị phản ánh chặt chém',
  wait_time: 'Thời gian chờ',
  booking_needed: 'Cần đặt trước',
  portion_size: 'Khẩu phần',
  entry_fee: 'Vé vào cửa',
  vegetarian_options: 'Món chay',
  cash_only: 'Chỉ nhận tiền mặt',
  condition_change: 'So với trước đây',
  rough_road_access: 'Đường vào xấu',
  steep_or_stairs: 'Dốc, nhiều bậc',
  long_walk: 'Phải đi bộ xa',
  kids: 'Trẻ em',
  elderly: 'Người lớn tuổi',
  couples: 'Cặp đôi',
  groups: 'Nhóm bạn',
}

export const VALUE: Record<string, string> = {
  present: 'có',
  absent: 'không',
  good: 'tốt',
  mixed: 'lẫn lộn',
  poor: 'kém',
  low: 'vắng',
  medium: 'vừa',
  high: 'đông',
  quiet: 'yên tĩnh',
  moderate: 'hơi ồn',
  loud: 'ồn',
  indoor: 'trong nhà',
  outdoor: 'ngoài trời',
  both: 'cả hai',
  clean: 'sạch',
  dirty: 'chưa sạch',
  sheltered: 'có mái che',
  easy: 'dễ',
  hard: 'khó',
  none: 'không phải chờ',
  short: 'chờ chút',
  long: 'chờ lâu',
  yes: 'có',
  no: 'không',
  generous: 'nhiều',
  small: 'ít',
  free: 'miễn phí',
  paid: 'có thu phí',
  improved: 'tốt lên',
  declined: 'xuống cấp',
  suitable: 'hợp',
  unsuitable: 'không hợp',
}

export const featureLabel = (id: string) => FEATURE[id] ?? id.replace(/_/g, ' ')

// How a liked feature reads as a wish ("Yên tĩnh", not "Độ ồn").
const PREF: Record<string, string> = {
  noise: 'Yên tĩnh',
  crowd: 'Ít đông',
  wait_time: 'Không phải chờ lâu',
  value_for_money: 'Đáng tiền',
  vegetarian_options: 'Có món chay',
  food_quality: 'Đồ ăn ngon',
  drink_quality: 'Đồ uống ngon',
}
export const prefLabel = (id: string) => PREF[id] ?? featureLabel(id)
export const valueLabel = (v: string) => VALUE[v] ?? v

// One short phrase for a signal: "Độ đông: đông", "View đẹp".
export function signalPhrase(id: string, value: string) {
  if (value === 'present') return featureLabel(id)
  return `${featureLabel(id)}: ${valueLabel(value)}`
}

// Features a person reads as a downside when they hold this value.
export const NEGATIVE: Record<string, string[]> = {
  crowd: ['high'],
  noise: ['loud'],
  cleanliness: ['dirty'],
  weather_exposed: ['present'],
  parking: ['hard'],
  service_attitude: ['poor'],
  service_quality: ['poor'],
  value_for_money: ['poor'],
  tourist_trap: ['present'],
  wait_time: ['long'],
  booking_needed: ['yes'],
  condition_change: ['declined'],
  rough_road_access: ['present'],
  steep_or_stairs: ['present'],
  long_walk: ['present'],
  food_quality: ['poor'],
  drink_quality: ['poor'],
  kids: ['unsuitable'],
  elderly: ['unsuitable'],
  cash_only: ['present'],
}

export const isNegative = (id: string, v: string) => NEGATIVE[id]?.includes(v) ?? false

export const STATUS_LABEL = {
  VERIFIED: 'Đã xác minh',
  UNCERTAIN: 'Chưa xác nhận',
  OUTDATED: 'Có thể đã thay đổi',
  NEEDS_REVIEW: 'Chờ duyệt',
  DISABLED: 'Đã vô hiệu',
} as const

export const DAY_VI: Record<string, string> = {
  mon: 'Thứ Hai',
  tue: 'Thứ Ba',
  wed: 'Thứ Tư',
  thu: 'Thứ Năm',
  fri: 'Thứ Sáu',
  sat: 'Thứ Bảy',
  sun: 'Chủ Nhật',
}

export const TIME_VI: Record<string, string> = {
  early_morning: 'sáng sớm',
  morning: 'buổi sáng',
  noon: 'buổi trưa',
  afternoon: 'buổi chiều',
  evening: 'buổi tối',
  night: 'đêm',
  weekday: 'ngày thường',
  weekend: 'cuối tuần',
  holiday: 'ngày lễ',
  sunny: 'trời nắng',
  rainy: 'trời mưa',
  foggy: 'trời sương',
  cold: 'trời lạnh',
}
