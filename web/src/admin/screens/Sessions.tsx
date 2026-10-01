import { useMemo } from 'react'
import { plan } from '../../user/planner'
import { initialTrip, type TripState } from '../../user/trip'

const START: Record<string, string> = {
  nothing: 'chưa có ý tưởng',
  saved: 'địa điểm đã lưu',
  must: 'nơi bắt buộc đến',
  itinerary: 'lịch trình có sẵn',
}

function localTrip(): TripState | null {
  try {
    const raw = localStorage.getItem('tg.trip.v1')
    return raw ? { ...initialTrip, ...JSON.parse(raw) } : null
  } catch {
    return null
  }
}

export function Sessions() {
  const trip = useMemo(localTrip, [])
  const result = useMemo(() => (trip && trip.selected.length ? plan(trip) : null), [trip])

  return (
    <div className="a-page">
      <header className="a-head">
        <div>
          <h1>Phiên chuyến đi</h1>
          <p>Để debug, đánh giá pilot và tìm chỗ người dùng bỏ dở. Không hiện dữ liệu cá nhân không cần thiết.</p>
        </div>
      </header>

      <section className="a-card">
        <h2>Phiên trên máy chủ</h2>
        <p className="a-muted">Chưa có. User Web bản thử chưa gửi sự kiện về máy chủ, nên chưa có phiên nào để liệt kê.</p>
      </section>

      <section className="a-card">
        <h2>Phiên trong trình duyệt này</h2>
        {!trip ? (
          <p className="a-muted">Trình duyệt này chưa lập chuyến đi nào. Mở /app để tạo một phiên.</p>
        ) : (
          <>
            <p className="session-line">
              <b>Phiên cục bộ</b> {trip.experience === 'first' ? 'lần đầu' : trip.experience === 'returning' ? 'đã từng đến' : 'chưa rõ kinh nghiệm'}, {trip.days} ngày, bắt đầu từ{' '}
              {START[trip.startWith ?? ''] ?? 'chưa rõ'}
            </p>
            <ol className="funnel">
              <li>
                <b>{Object.keys(trip.prefs).length}</b> sở thích
              </li>
              <li>
                <b>{trip.mustVisit.length}</b> nơi bắt buộc
              </li>
              <li>
                <b>{trip.selected.length + trip.dropped.length}</b> nơi đã cân nhắc
              </li>
              <li>
                <b>{trip.dropped.length}</b> bị bỏ
              </li>
              <li>
                <b>{trip.selected.length}</b> được chọn
              </li>
              <li>
                <b>{result?.conflicts.length ?? 0}</b> xung đột
              </li>
              <li>
                <b>{result ? (result.status === 'feasible' ? 'khả thi' : result.status === 'partial' ? 'cần sửa' : 'không khả thi') : 'chưa kiểm tra'}</b>
              </li>
            </ol>
            {trip.dropped.some((d) => d.reason) && (
              <p className="a-muted">
                Lý do bỏ:{' '}
                {Object.entries(
                  trip.dropped.reduce<Record<string, number>>((a, d) => (d.reason ? ((a[d.reason] = (a[d.reason] ?? 0) + 1), a) : a), {}),
                )
                  .map(([r, n]) => `${r} ${n}`)
                  .join(', ')}
              </p>
            )}
          </>
        )}
      </section>
    </div>
  )
}
