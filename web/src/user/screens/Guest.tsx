import { useState } from 'react'
import { deleteAccount, holdGuest, signInHref, useAccount } from '../account'
import { go, ArtHills, Empty } from '../ui/common'
import { Icon } from '../ui/icons'
import { Page, useTitle } from '../ui/Shell'

// A guest plans like anyone, but nothing outlives the visit: trips are deleted after 24 idle hours
// (docs/ACCOUNTS.md §Khách). Signing in with Google keeps the trips made so far.
export function GuestNotice() {
  const account = useAccount()
  if (!account?.guest) return null
  return (
    <aside className="tg-guest" role="note">
      <Icon name="info" size={18} />
      <p><b>Bạn đang dùng với tư cách khách.</b> Chuyến đi sẽ bị xóa sau 24 giờ không hoạt động.</p>
      <a className="tg-btn tg-btn--primary tg-btn--sm" href={signInHref(location.pathname + location.search)} onClick={holdGuest}>Đăng nhập để lưu</a>
    </aside>
  )
}

// A page that needs a Google account (Hôm nay, Thông báo)
export function GuestGate({ what }: { what: string }) {
  useTitle(what)
  return (
    <Page narrow>
      <Empty art={<ArtHills />} title={`${what} cần đăng nhập Google`} body="Khách không lưu lịch sử, nên chưa dùng được Hôm nay, thông báo và Google Calendar. Đăng nhập thì các chuyến bạn đã lập được giữ lại."
        action={<div className="tg-guest__act"><a className="tg-btn tg-btn--primary" href={signInHref('/app')} onClick={holdGuest}>Đăng nhập bằng Google <Icon name="arrow" size={18} /></a><button type="button" className="tg-link tg-link--quiet" onClick={() => go('/')}>Về Khám phá</button></div>} />
    </Page>
  )
}

export function GuestProfile() {
  useTitle('Khách')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(false)
  const end = () => {
    setBusy(true)
    deleteAccount().catch(() => { setErr(true); setBusy(false) })
  }
  return (
    <Page narrow>
      <header className="tg-head"><div><p className="tg-kicker">Khách</p><h1>Bạn đang dùng không cần tài khoản</h1><p>Lập chuyến đầy đủ như người có tài khoản, nhưng không lưu lịch sử: chuyến bị xóa sau 24 giờ không hoạt động, và không có hồ sơ, Hôm nay, thông báo hay Google Calendar.</p></div></header>
      <div className="tg-guest__act is-left">
        <a className="tg-btn tg-btn--primary" href={signInHref('/app')} onClick={holdGuest}>Đăng nhập bằng Google để lưu chuyến <Icon name="arrow" size={18} /></a>
        <button type="button" className="tg-btn tg-btn--ghost" disabled={busy} onClick={end}>Kết thúc và xóa chuyến của tôi</button>
      </div>
      {err && <p className="tg-alert" role="alert"><Icon name="warn" size={15} /> Chưa xóa được, bạn thử lại nhé.</p>}
    </Page>
  )
}
