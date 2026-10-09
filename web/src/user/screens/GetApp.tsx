import { useState } from 'react'
import { APP_LINKS, platform } from '../landing/device'
import stats from '../landing/stats.json'
import { Icon, Logo } from '../ui/icons'
import { useTitle } from '../ui/Shell'

// What a phone sees on every user page (docs/UI_SPEC_LANDING.md §5): the web is built for a computer and there is no
// phone version of it; phones are sent to the app. No store link yet: say the app comes later and send the link to a computer.
const STORES = [
  { id: 'ios', name: 'App Store', url: APP_LINKS.ios },
  { id: 'android', name: 'Google Play', url: APP_LINKS.android },
] as const

export function GetApp() {
  useTitle('Tải ứng dụng')
  const [sent, setSent] = useState<'' | 'copied' | 'failed'>('')
  const mine = platform()
  const stores = [...STORES].sort((a, b) => Number(b.id === mine) - Number(a.id === mine))
  const released = stores.some((s) => s.url)

  const share = async () => {
    const url = location.href // the page they opened (a shared place, a trip) opens the same on the computer
    try {
      if (navigator.share) { await navigator.share({ title: 'TripGuardian Đà Lạt', text: 'Mở trên máy tính để lên lịch Đà Lạt', url }); return }
      await navigator.clipboard.writeText(url)
      setSent('copied')
    } catch (e) {
      if ((e as Error).name !== 'AbortError') setSent('failed')
    }
  }

  return (
    <main className="tg-ga">
      <header className="tg-ga__top"><Logo size={30} /><span>TripGuardian</span></header>

      <div className="tg-ga__art" aria-hidden="true">
        <div className="tg-ga__phone">
          <span className="tg-ga__notch" />
          <span className="tg-ga__pin p1">1</span><span className="tg-ga__pin p2">2</span><span className="tg-ga__pin p3">3</span>
          <svg viewBox="0 0 100 160" className="tg-ga__route"><path d="M24 118 C 40 96, 70 104, 72 78 S 40 50, 58 34" /></svg>
          <span className="tg-ga__bar"><i />Lịch sẵn sàng</span>
        </div>
      </div>

      <section className="tg-ga__body" aria-labelledby="tg-ga-h">
        <p className="tg-kicker">Trên điện thoại</p>
        <h1 id="tg-ga-h">Tải ứng dụng để dùng TripGuardian trên điện thoại.</h1>
        <p className="tg-muted">
          {released
            ? 'Lên lịch Đà Lạt, xem đường đi và mang lịch trình theo suốt chuyến ngay trên điện thoại.'
            : 'Ứng dụng sẽ có trong thời gian tới. Hiện tại, bạn mở TripGuardian trên máy tính để có trải nghiệm tốt nhất.'}
        </p>

        <div className="tg-ga__stores">
          {stores.map((s) => s.url ? (
            <a key={s.id} className="tg-ga__store" href={s.url} target="_blank" rel="noreferrer"><Icon name="download" size={22} /><span><small>Tải trên</small><b>{s.name}</b></span></a>
          ) : (
            <div key={s.id} className="tg-ga__store is-soon" aria-disabled="true"><Icon name="phone" size={22} /><span><small>Sắp có trên</small><b>{s.name}</b></span><span className="tg-tag tg-tag--warn">chưa mở</span></div>
          ))}
        </div>

        <button type="button" className="tg-btn tg-btn--ghost tg-ga__share" onClick={share}><Icon name="laptop" size={20} />Gửi link sang máy tính</button>
        <p className="tg-ga__status" role="status">{sent === 'copied' ? 'Đã chép link. Dán vào trình duyệt trên máy tính.' : sent === 'failed' ? `Chưa chép được. Mở ${location.host} trên máy tính.` : ''}</p>

      </section>

      <footer className="tg-ga__foot">{stats.places.toLocaleString('vi-VN')} địa điểm có thật ở Đà Lạt · cập nhật {stats.asOf?.split('-').reverse().join('/')}</footer>
    </main>
  )
}
