import { useMemo, useState } from 'react'
import { APP_LINKS, platform } from '../landing/device'
import stats from '../landing/stats.json'
import { Icon, Logo } from '../ui/icons'
import { qrMatrix } from '../ui/qr'
import { useTitle } from '../ui/Shell'

// What a phone sees on every user page (docs/UI_DESIGN.md §7): the web is built for a computer and there is no
// phone version of it. The page helps move this exact link to a computer (share sheet, copy, QR drawn locally); store
// buttons appear once the app has a store link.
const STORES = [
  { id: 'ios', name: 'App Store', url: APP_LINKS.ios },
  { id: 'android', name: 'Google Play', url: APP_LINKS.android },
] as const

export function GetApp() {
  useTitle('Mở trên máy tính')
  const [sent, setSent] = useState<'' | 'copied' | 'failed'>('')
  const mine = platform()
  const stores = [...STORES].sort((a, b) => Number(b.id === mine) - Number(a.id === mine)).filter((s) => s.url)
  const url = location.href // the page they opened (a shared place, a trip) opens the same on the computer
  const qr = useMemo(() => qrMatrix(url) ?? qrMatrix(location.origin), [url])

  const copy = async () => {
    try { await navigator.clipboard.writeText(url); setSent('copied') } catch { setSent('failed') }
  }
  const share = async () => {
    try { await navigator.share({ title: 'TripGuardian Đà Lạt', text: 'Mở trên máy tính để lên lịch Đà Lạt', url }) } catch (e) { if ((e as Error).name !== 'AbortError') void copy() }
  }

  return (
    <main className="tg-ga">
      <header className="tg-ga__top"><Logo size={30} /><span>TripGuardian</span></header>

      <section className="tg-ga__body" aria-labelledby="tg-ga-h">
        <p className="tg-kicker">Trên điện thoại</p>
        <h1 id="tg-ga-h">Mở trên máy tính</h1>
        <p className="tg-muted">TripGuardian hiện được làm cho màn hình máy tính: bản đồ, so sánh và lịch trình cần chỗ rộng. Gửi link này sang máy tính rồi mở ở đó nhé.</p>

        <div className="tg-ga__send">
          {'share' in navigator && <button type="button" className="tg-btn tg-btn--primary tg-ga__share" onClick={share}><Icon name="laptop" size={20} />Gửi link cho chính bạn</button>}
          <button type="button" className="tg-btn tg-btn--ghost tg-ga__share" onClick={copy}><Icon name="link" size={20} />Chép link</button>
          <p className="tg-ga__status" role="status">{sent === 'copied' ? 'Đã chép link. Dán vào email hoặc tin nhắn gửi cho chính bạn.' : sent === 'failed' ? `Chưa chép được. Trên máy tính, mở ${location.host}` : ''}</p>
        </div>

        {qr && <figure className="tg-ga__qr"><svg viewBox={`-4 -4 ${qr.length + 8} ${qr.length + 8}`} role="img" aria-label="Mã QR của trang này" shapeRendering="crispEdges"><rect x="-4" y="-4" width={qr.length + 8} height={qr.length + 8} fill="#fff" /><path d={qr.flatMap((row, y) => row.map((on, x) => (on ? `M${x} ${y}h1v1h-1z` : ''))).join('')} fill="#000" /></svg><figcaption className="tg-faint">Mã QR của trang này: quét bằng máy khác để mở đúng trang này.</figcaption></figure>}

        {stores.length ? (
          <div className="tg-ga__stores">{stores.map((s) => <a key={s.id} className="tg-ga__store" href={s.url} target="_blank" rel="noreferrer"><Icon name="download" size={22} /><span><small>Tải trên</small><b>{s.name}</b></span></a>)}</div>
        ) : <p className="tg-faint tg-ga__later"><Icon name="phone" size={16} /> Ứng dụng điện thoại sẽ có trong thời gian tới.</p>}
      </section>

      <footer className="tg-ga__foot">Hơn {(Math.floor(stats.places / 100) * 100).toLocaleString('vi-VN')} địa điểm có thật ở Đà Lạt · cập nhật {stats.asOf?.split('-').reverse().join('/')}</footer>
    </main>
  )
}
