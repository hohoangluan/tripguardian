import { useState } from 'react'
import { continueAsGuest, signIn, signUp, type AuthError } from '../account'
import { navigate } from '../../router'
import { Icon, Logo } from '../ui/icons'
import { useTitle } from '../ui/Shell'

// Sign-in sits before the trip questions but never blocks them: the guest path comes first.
// Accounts are kept in this browser only until an auth backend exists (src/user/account.ts); social sign-in is not open yet.
export function Auth({ onDone }: { onDone: () => void }) {
  useTitle('Vào ứng dụng')
  const [mode, setMode] = useState<'pick' | 'login' | 'signup'>('pick')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<AuthError | null>(null)
  const err = (f: AuthError['field']) => (error?.field === f ? <small className="tg-auth__err" role="alert">{error.text}</small> : null)
  const submit = () => {
    const e = mode === 'login' ? signIn(email, password) : signUp(name, email, password)
    setError(e)
    if (!e) onDone()
  }
  return (
    <div className="tg-auth">
      <aside className="tg-auth__art" aria-hidden="true"><div className="tg-auth__img" /><a className="tg-auth__logo" href="/" onClick={(e) => { e.preventDefault(); navigate('/') }}><Logo size={34} dark /><span>TripGuardian</span></a><p>Đà Lạt có cả nghìn chỗ đẹp.<br /><em>Chuyến này của bạn cần mấy chỗ?</em></p></aside>
      <main className="tg-auth__main">
        <div className="tg-auth__card tg-stage" key={mode}>
          {mode === 'pick' ? (
            <>
              <h1>Bắt đầu chuyến Đà Lạt</h1><p className="tg-muted">Nói một câu, mình dựng cả chuyến. Mỗi gợi ý có lý do và có cái giá.</p>
              <button type="button" className="tg-btn tg-btn--primary tg-auth__try" onClick={() => { continueAsGuest(); onDone() }}>Dùng thử, không cần tài khoản <Icon name="arrow" size={18} /></button>
              <p className="tg-auth__or"><span>hoặc</span></p>
              <div className="tg-auth__alt">{['Google', 'Zalo', 'Facebook', 'Apple'].map((n) => <button key={n} type="button" className="tg-btn tg-btn--ghost tg-btn--sm" disabled title="Sắp có">{n} · sắp có</button>)}</div>
              <p className="tg-auth__foot"><button type="button" className="tg-link" onClick={() => setMode('login')}>Đăng nhập bằng email</button><button type="button" className="tg-link" onClick={() => setMode('signup')}>Tạo tài khoản</button></p>
              <p className="tg-faint tg-auth__fine"><Icon name="shield" size={14} /> Tài khoản hiện chỉ lưu trên trình duyệt này. Chuyến đi vẫn lưu trên máy chủ theo mã chuyến, không cần tài khoản.</p>
            </>
          ) : (
            <>
              <h1>{mode === 'login' ? 'Đăng nhập' : 'Tạo tài khoản'}</h1><p className="tg-muted">Tài khoản lưu trên trình duyệt này; mật khẩu không được gửi đi đâu.</p>
              <form onSubmit={(e) => { e.preventDefault(); submit() }} noValidate>
                {mode === 'signup' && <label className="tg-auth__f"><span>Tên bạn</span><input className="tg-input" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />{err('name')}</label>}
                <label className="tg-auth__f"><span>Email</span><input className="tg-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />{err('email')}</label>
                <label className="tg-auth__f"><span>Mật khẩu</span><input className="tg-input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} />{err('password')}</label>
                <button type="submit" className="tg-btn tg-btn--primary">{mode === 'login' ? 'Vào' : 'Tạo tài khoản'}</button>
              </form>
              <p className="tg-auth__foot">{mode === 'login' ? <button type="button" className="tg-link" onClick={() => { setMode('signup'); setError(null) }}>Tạo tài khoản</button> : <button type="button" className="tg-link" onClick={() => { setMode('login'); setError(null) }}>Đã có tài khoản? Đăng nhập</button>}<button type="button" className="tg-link tg-link--quiet" onClick={() => { setMode('pick'); setError(null) }}>Quay lại</button></p>
            </>
          )}
        </div>
      </main>
    </div>
  )
}
