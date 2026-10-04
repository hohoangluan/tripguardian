import { featureLabel } from '../../data/labels'
import { navigate } from '../../router'
import { Icon, Page } from '../../ui/bits'
import { initialOf, PROVIDER_LABEL, signOut, useAccount } from '../account'
import { hasTrip, stepOf, useTrip } from '../trip'

// UI spec §4 Trang 9: every source is optional; with none, everything still works.
const SOURCES = [
  { id: 'gmaps', label: 'Google Maps', note: 'các danh sách địa điểm bạn đã lưu', icon: 'pin' },
  { id: 'tiktok', label: 'TikTok', note: 'clip bạn đã lưu, để biết gu', icon: 'play' },
  { id: 'history', label: 'Chuyến trước trên TripGuardian', note: 'nơi đã đến và phản hồi bạn gửi', icon: 'flag' },
]

export function Profile() {
  const { trip, dispatch } = useTrip()
  const inferred = Object.entries(trip.prefs).filter(([, p]) => p.from === 'profile')
  const account = useAccount()
  const resume = stepOf(trip)
  const days = trip.searchInput?.context.days ?? trip.days

  return (
    <Page className="page--mid">
      <header className="uhead uhead--center">
        <h1>Hồ sơ và dữ liệu</h1>
        <p>Mọi thứ ở đây là suy đoán của mình. Bạn sửa hoặc xoá bất cứ lúc nào.</p>
      </header>

      <section className="ucard pf-account">
        <span className="pf-avatar" aria-hidden="true">
          {initialOf(account) ?? <Icon name="user" />}
        </span>
        <div>
          <b>{account?.kind === 'user' ? account.name : 'Bạn đang dùng thử'}</b>
          <small>{account?.kind === 'user' ? (account.email ?? `Đăng nhập bằng ${PROVIDER_LABEL[account.provider]}`) + ' · tài khoản bản thử' : 'Chuyến đi chỉ lưu trên trình duyệt này.'}</small>
        </div>
        {account?.kind === 'user' ? (
          <button className="btn btn--ghost btn--small" onClick={signOut}>
            Đăng xuất
          </button>
        ) : (
          <button className="btn btn--small" onClick={() => navigate('/app/login')}>
            Tạo tài khoản
          </button>
        )}
      </section>

      <section className="ucard">
        <h2 className="utitle">Nguồn đã kết nối</h2>
        <ul className="pf-rows">
          {SOURCES.map((s) => (
            <li key={s.id}>
              <Icon name={s.icon} size={22} />
              <span>
                <b>{s.label}</b>
                <small>{s.note}</small>
              </span>
              <span className="pf-state">
                <i /> Chưa kết nối
              </span>
              <button className="btn btn--ghost btn--small" disabled title="Chưa có trong bản thử">
                Kết nối
              </button>
            </li>
          ))}
        </ul>
        <p className="hint">Không kết nối gì thì mọi thứ vẫn chạy. Kết nối nguồn chưa có trong bản thử này.</p>
      </section>

      <section className="ucard">
        <h2 className="utitle">Điều hệ thống suy ra về bạn</h2>
        {inferred.length === 0 ? (
          <p className="hint">Chưa có gì. Khi có nguồn hoặc chuyến đi trước, các suy đoán sẽ hiện ở đây kèm lý do, và bạn sửa được từng dòng.</p>
        ) : (
          <ul className="pf-rows">
            {inferred.map(([id, p]) => (
              <li key={id}>
                <span>
                  <b>
                    {p.weight === 'love' ? 'Thích' : 'Tránh'} {featureLabel(id).toLowerCase()}
                  </b>
                </span>
                <span className="mono pf-from">từ hồ sơ của bạn</span>
                <span className="pf-acts">
                  <button className="link" onClick={() => dispatch({ type: 'pref', id, pref: { ...p, weight: p.weight === 'love' ? 'avoid' : 'love' } })}>
                    Sửa
                  </button>
                  <button className="link" onClick={() => dispatch({ type: 'pref', id, pref: null })}>
                    Xoá
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="ucard">
        <h2 className="utitle">Chuyến đi đang lập</h2>
        {hasTrip(trip) ? (
          <ul className="pf-rows">
            <li>
              <Icon name="map" size={22} />
              <span>
                <b>Đà Lạt {days} ngày</b>
                <small className="mono">
                  {days} ngày · {trip.selected.length} nơi đã chọn · đang ở bước {resume.label.toLowerCase()}
                </small>
              </span>
              <span />
              <button className="btn btn--ghost btn--small" onClick={() => navigate(resume.path)}>
                Mở tiếp
              </button>
            </li>
          </ul>
        ) : (
          <p className="hint">Chưa có chuyến nào. Bắt đầu từ trang đầu, chỉ vài câu thôi.</p>
        )}
      </section>

      <div className="pf-reset">
        <button className="btn btn--ghost" onClick={() => confirm('Đặt lại toàn bộ hồ sơ và chuyến đi đang lập?') && dispatch({ type: 'reset' })}>
          Đặt lại toàn bộ hồ sơ
        </button>
      </div>
    </Page>
  )
}
