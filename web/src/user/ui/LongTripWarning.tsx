import { Icon } from './icons'

export const RECOMMENDED_TRIP_DAYS = 14

export function LongTripWarning({ days }: { days: number }) {
  if (days <= RECOMMENDED_TRIP_DAYS) return null
  return <p className="tg-narrow" role="status"><Icon name="warn" size={18} /><span>Khuyến nghị tối đa {RECOMMENDED_TRIP_DAYS} ngày. Chuyến {days} ngày vẫn được phép, nhưng khả năng xử lý chưa được kiểm chứng; việc xếp và sửa lịch có thể lâu hơn.</span></p>
}
