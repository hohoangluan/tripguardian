import { useState } from 'react'
import { acceptTerms, signInHref, signOut, useAccount } from '../account'
import { navigate } from '../../router'
import { Icon, Logo } from '../ui/icons'
import { useTitle } from '../ui/Shell'

const ERRORS: Record<string, string> = {
  denied: 'Bạn chưa cho phép Google chia sẻ tài khoản, nên mình chưa đăng nhập được.',
  state: 'Phiên đăng nhập đã hết hạn. Bấm lại nút bên dưới nhé.',
  failed: 'Google chưa xác nhận được tài khoản. Thử lại sau ít phút nhé.',
}

// /app needs an account (docs/Role_Web_Functional_Design.md §1): Google sign-in, then a one-time consent to the terms
// and the data policy. `next` is where Google sends the browser back.
export function Auth({ next }: { next: string }) {
  const account = useAccount()
  useTitle(account?.needs_consent ? 'Điều khoản' : 'Đăng nhập')
  const error = new URLSearchParams(location.search).get('error')
  return (
    <div className="tg-auth">
      <aside className="tg-auth__art" aria-hidden="true"><div className="tg-auth__img" /><a className="tg-auth__logo" href="/" onClick={(e) => { e.preventDefault(); navigate('/') }}><Logo size={34} dark /><span>TripGuardian</span></a><p>Đà Lạt có cả nghìn chỗ đẹp.<br /><em>Chuyến này của bạn cần mấy chỗ?</em></p></aside>
      <main className="tg-auth__main">
        <div className="tg-auth__card tg-stage" key={account ? 'consent' : 'pick'}>
          {account?.needs_consent ? <Consent version={account.terms_version} /> : (
            <>
              <h1>Bắt đầu chuyến Đà Lạt</h1><p className="tg-muted">Nói một câu, TripGuardian dựng cả chuyến. Mỗi gợi ý có lý do và có cái giá.</p>
              {error && ERRORS[error] && <p className="tg-auth__err" role="alert">{ERRORS[error]}</p>}
              <a className="tg-btn tg-btn--primary tg-auth__try" href={signInHref(next)}>Tiếp tục với Google <Icon name="arrow" size={18} /></a>
              <p className="tg-faint tg-auth__fine"><Icon name="shield" size={14} /> Chuyến đi, hồ sơ và lịch sử của bạn được lưu theo tài khoản, mở được trên mọi máy. Bạn xóa tài khoản lúc nào cũng được.</p>
            </>
          )}
        </div>
      </main>
    </div>
  )
}

function Consent({ version }: { version: string }) {
  const [ok, setOk] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(false)
  const agree = () => {
    setBusy(true)
    acceptTerms(version).catch(() => { setErr(true); setBusy(false) })
  }
  return (
    <>
      <h1>Trước khi bắt đầu</h1>
      <p className="tg-muted">Đọc nhanh cách TripGuardian dùng dữ liệu của bạn:</p>
      <ul className="tg-auth__terms">
        <li>Tên, email và ảnh từ Google dùng để đăng nhập và hiện trên hồ sơ.</li>
        <li>Chuyến đi, lời bạn nhắn và các thao tác trong app được lưu để giữ chuyến cho bạn và để đội ngũ cải thiện gợi ý. Người quản trị xem được các dữ liệu này.</li>
        <li>Hồ sơ (thành phố, phương tiện, hay đi với ai) chỉ là gợi ý ban đầu; chuyến hiện tại luôn thắng.</li>
        <li>Không thu vị trí GPS. Google Calendar chỉ được ghi khi bạn bấm xác nhận.</li>
        <li>Xóa tài khoản trong Hồ sơ: dữ liệu cá nhân bị xóa, số liệu còn lại không gắn với bạn nữa.</li>
      </ul>
      <label className="tg-auth__check"><input type="checkbox" checked={ok} onChange={(e) => setOk(e.target.checked)} /> <span>Tôi đồng ý với Điều khoản sử dụng và Chính sách dữ liệu (bản {version}).</span></label>
      {err && <p className="tg-auth__err" role="alert">Chưa lưu được, thử lại nhé.</p>}
      <button type="button" className="tg-btn tg-btn--primary" disabled={!ok || busy} onClick={agree}>Bắt đầu <Icon name="arrow" size={18} /></button>
      <p className="tg-auth__foot"><button type="button" className="tg-link tg-link--quiet" onClick={() => void signOut()}>Dùng tài khoản khác</button></p>
    </>
  )
}
