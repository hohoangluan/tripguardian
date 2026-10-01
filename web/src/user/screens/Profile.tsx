import { featureLabel } from '../../data/labels'
import { Icon, Page } from '../../ui/bits'
import { useTrip } from '../trip'

// §2.11: sources are optional; with none, everything still works.
const SOURCES = [
  { id: 'tiktok', label: 'Clip đã lưu trên TikTok', note: 'Đọc danh sách clip bạn lưu để biết gu.' },
  { id: 'gmaps', label: 'Địa điểm đã lưu trên Google Maps', note: 'Đọc các danh sách bạn đã lưu.' },
  { id: 'history', label: 'Các chuyến trước trên TripGuardian', note: 'Nơi đã đến và phản hồi bạn gửi.' },
]

export function Profile() {
  const { trip, dispatch } = useTrip()
  const inferred = Object.entries(trip.prefs).filter(([, p]) => p.from === 'profile')

  return (
    <Page className="page--narrow">
      <button className="back" onClick={() => history.back()}>
        <Icon name="back" size={16} /> Quay lại
      </button>
      <header className="phead">
        <h1>Hồ sơ và dữ liệu</h1>
        <p>Mọi nguồn đều tùy chọn. Không kết nối gì thì TripGuardian vẫn chạy đầy đủ.</p>
      </header>

      <section className="block">
        <h2 className="block__title">Nguồn đã kết nối</h2>
        <ul className="sources">
          {SOURCES.map((s) => (
            <li key={s.id}>
              <div>
                <b>{s.label}</b>
                <small>{s.note}</small>
              </div>
              <button className="btn btn--small btn--ghost" disabled title="Chưa có trong bản thử">
                Kết nối
              </button>
            </li>
          ))}
        </ul>
        <p className="block__note">Kết nối nguồn chưa có trong bản thử này.</p>
      </section>

      <section className="block">
        <h2 className="block__title">Điều hệ thống suy ra về bạn</h2>
        {inferred.length === 0 ? (
          <p className="muted">Chưa có gì. Khi có nguồn hoặc chuyến đi trước, các suy đoán sẽ hiện ở đây, kèm lý do, và bạn sửa được từng dòng.</p>
        ) : (
          <ul className="inferred">
            {inferred.map(([id]) => (
              <li key={id}>
                <span>Thích {featureLabel(id).toLowerCase()}</span>
                <button className="link" onClick={() => dispatch({ type: 'pref', id, pref: null })}>
                  Xóa
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="block">
        <h2 className="block__title">Chuyến đi đang lập</h2>
        <p className="block__hint">Lưu trong trình duyệt này. Đặt lại sẽ xóa sở thích, danh sách chọn và lịch trình.</p>
        <button className="btn btn--ghost" onClick={() => confirm('Đặt lại toàn bộ chuyến đi đang lập?') && dispatch({ type: 'reset' })}>
          Đặt lại chuyến đi
        </button>
      </section>
    </Page>
  )
}
