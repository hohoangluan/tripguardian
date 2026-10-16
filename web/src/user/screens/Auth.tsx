import { useEffect, useState, type FormEvent, type PointerEvent } from 'react'
import { acceptTerms, AccountError, holdGuest, loginWithEmail, registerWithEmail, signInHref, signOut, startGuest, useAccount } from '../account'
import { navigate } from '../../router'
import { go } from '../ui/common'
import { Icon } from '../ui/icons'
import { useTitle } from '../ui/Shell'

// The mascot leans toward the pointer (CSS vars read by .tg-auth__mascot); reduced motion is handled in the CSS.
function look(e: PointerEvent<HTMLElement>) {
  const r = e.currentTarget.getBoundingClientRect()
  const x = ((e.clientX - r.left) / r.width - 0.5) * 2
  const y = ((e.clientY - r.top) / r.height - 0.5) * 2
  e.currentTarget.style.setProperty('--lx', `${(x * 14).toFixed(1)}px`)
  e.currentTarget.style.setProperty('--ly', `${(y * 8).toFixed(1)}px`)
}
function unlook(e: PointerEvent<HTMLElement>) {
  e.currentTarget.style.setProperty('--lx', '0px')
  e.currentTarget.style.setProperty('--ly', '0px')
}

const ERRORS: Record<string, string> = {
  denied: 'Bạn chưa cho phép Google chia sẻ tài khoản, nên mình chưa đăng nhập được.',
  state: 'Phiên đăng nhập đã hết hạn. Bấm lại nút bên dưới nhé.',
  failed: 'Google chưa xác nhận được tài khoản. Thử lại sau ít phút nhé.',
}

// /app needs a session (docs/Role_Web_Functional_Design.md §1): Google sign-in with a one-time consent to the terms and
// the data policy, or a guest session that keeps nothing. `next` is where Google sends the browser back.
// Look: the split card of web/public/prototype (mascot scene left, form right); sign in and sign up share one card.
export function Auth({ next }: { next: string }) {
  const account = useAccount()
  useTitle(account?.needs_consent ? 'Điều khoản' : 'Đăng nhập')
  const error = new URLSearchParams(location.search).get('error')
  const [mode, setMode] = useState<'in' | 'up'>('in')
  const [guestErr, setGuestErr] = useState<'many' | 'failed' | null>(null)
  const done = () => go(next.slice('/app'.length) || '/', { replace: true })
  const asGuest = () => startGuest().then(done, (e) => setGuestErr(e instanceof AccountError && e.status === 429 ? 'many' : 'failed'))
  const up = mode === 'up'
  const consent = !!account?.needs_consent
  return (
    <div className="tg-auth">
      <a className="tg-auth__back" href="/" aria-label="Về trang giới thiệu" onClick={(e) => { e.preventDefault(); navigate('/') }}><Icon name="arrowLeft" size={20} /></a>
      <div className="tg-auth__card tg-stage" key={account ? 'consent' : 'pick'}>
        <aside className="tg-auth__art" aria-hidden="true">
          <div className="tg-auth__scene" onPointerMove={look} onPointerLeave={unlook}>
            <span className="tg-auth__cloud tg-auth__cloud--a" /><span className="tg-auth__cloud tg-auth__cloud--b" />
            <span className="tg-auth__hill" />
            <span className="tg-auth__shadow" />
            <img className="tg-auth__mascot" src="/img/auth/acorn_greet.webp" alt="" />
          </div>
        </aside>
        <main className="tg-auth__main">
          <img className="tg-auth__mark" src="/img/auth/acorn_mascot.png" alt="TripGuardian" width={48} height={48} />
          {consent ? <Consent version={account!.terms_version} /> : (
            <>
              <h1>{account?.guest ? 'Đăng nhập để lưu chuyến' : up ? 'Tạo tài khoản' : 'Chào mừng trở lại'}</h1>
              <p className="tg-muted">{account?.guest ? 'Các chuyến bạn đã lập khi dùng với tư cách khách sẽ chuyển sang tài khoản.' : up ? 'Một tài khoản để giữ chuyến, hồ sơ và lịch sử trên mọi máy.' : 'Nhập email và mật khẩu để vào tài khoản của bạn.'}</p>
              {error && ERRORS[error] && <p className="tg-auth__err" role="alert">{ERRORS[error]}</p>}
              <EmailForm up={up} onDone={done} />
              <p className="tg-auth__or">hoặc</p>
              <a className="tg-btn tg-btn--ghost tg-auth__google" href={signInHref(next)} onClick={holdGuest}><GoogleMark /> {up ? 'Đăng ký với Google' : 'Đăng nhập với Google'}</a>
              <p className="tg-auth__switch">{up ? 'Đã có tài khoản?' : 'Chưa có tài khoản?'} <button type="button" className="tg-link" onClick={() => setMode(up ? 'in' : 'up')}>{up ? 'Đăng nhập' : 'Đăng ký'}</button></p>
              {account?.guest
                ? <button type="button" className="tg-link tg-link--quiet" onClick={() => go('/')}>Tiếp tục với tư cách khách</button>
                : <button type="button" className="tg-link tg-link--quiet" onClick={() => void asGuest()}>Dùng thử, không cần tài khoản</button>}
              {guestErr && <p className="tg-auth__err" role="alert">{guestErr === 'many' ? 'Địa chỉ này đã mở quá nhiều phiên khách trong một giờ. Bạn đăng nhập hoặc tạo tài khoản nhé.' : 'Chưa mở được phiên khách. Bạn thử lại, hoặc đăng nhập nhé.'}</p>}
              <p className="tg-faint tg-auth__fine"><Icon name="shield" size={14} /> Có tài khoản: chuyến đi, hồ sơ và lịch sử được lưu, xóa tài khoản lúc nào cũng được. Khách: không lưu lịch sử, chuyến bị xóa sau 24 giờ không hoạt động.</p>
            </>
          )}
        </main>
      </div>
    </div>
  )
}

function GoogleMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
    </svg>
  )
}

const EMAIL_ERRORS: Record<number, string> = {
  401: 'Email hoặc mật khẩu chưa đúng.',
  409: 'Email này đã có tài khoản. Bạn đăng nhập, hoặc dùng email khác nhé.',
  429: 'Bạn thử quá nhiều lần. Chờ vài phút rồi thử lại nhé.',
}

// Sign up (name, email, password, repeat) or sign in (email, password) without Google. The server checks again.
function EmailForm({ up, onDone }: { up: boolean; onDone: () => void }) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [again, setAgain] = useState('')
  const [show, setShow] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => setErr(null), [up])
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (busy) return
    if (up && password.length < 8) return setErr('Mật khẩu cần ít nhất 8 ký tự.')
    if (up && password !== again) return setErr('Hai mật khẩu chưa giống nhau.')
    setBusy(true)
    setErr(null)
    try {
      await (up ? registerWithEmail(email, password, name) : loginWithEmail(email, password))
      onDone()
    } catch (x) {
      const s = x instanceof AccountError ? x.status : 0
      setErr(EMAIL_ERRORS[s] ?? (s === 400 ? 'Email hoặc mật khẩu chưa hợp lệ (mật khẩu 8 đến 128 ký tự).' : 'Chưa gửi được, bạn thử lại nhé.'))
      setBusy(false)
    }
  }
  const type = show ? 'text' : 'password'
  return (
    <form onSubmit={submit} noValidate>
      {up && <label className="tg-auth__f">Tên của bạn<input className="tg-input" value={name} onChange={(e) => setName(e.target.value)} maxLength={60} autoComplete="name" placeholder="Không bắt buộc" /></label>}
      <label className="tg-auth__f">Email<input className="tg-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" placeholder="ban@email.com" required /></label>
      <div className={up ? 'tg-auth__pair' : undefined}>
        <label className="tg-auth__f">Mật khẩu
          <span className="tg-auth__pw">
            <input className="tg-input" type={type} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete={up ? 'new-password' : 'current-password'} minLength={8} maxLength={128} required placeholder={up ? 'Ít nhất 8 ký tự' : 'Nhập mật khẩu'} />
            <button type="button" className="tg-auth__eye" aria-label={show ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'} aria-pressed={show} onClick={() => setShow(!show)}><Icon name="eye" size={18} /></button>
          </span>
        </label>
        {up && <label className="tg-auth__f">Nhập lại<input className="tg-input" type={type} value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" required placeholder="Nhập lại mật khẩu" /></label>}
      </div>
      {err && <p className="tg-auth__err" role="alert">{err}</p>}
      <button type="submit" className="tg-btn tg-btn--primary tg-auth__try" disabled={busy || !email.trim() || !password}>{busy ? 'Đang gửi…' : up ? 'Tạo tài khoản' : 'Đăng nhập'}</button>
    </form>
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
        <li>Tên và email (cùng ảnh nếu bạn đăng nhập bằng Google) dùng để đăng nhập và hiện trên hồ sơ. Mật khẩu chỉ lưu dạng băm, không ai đọc được.</li>
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
