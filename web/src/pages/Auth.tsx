import gsap from 'gsap'
import { useEffect, useLayoutEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { story } from '../scene/story'
import { continueAsGuest, PROVIDER_LABEL, signIn, signInWith, signUp, type AuthError, type Provider } from '../user/account'

type Social = Exclude<Provider, 'email'>
type Mode = 'login' | 'signup'

// Sign-in sits before the trip questions but never blocks them: the guest path
// is as prominent as any provider (the landing promises "no account needed").
export function Auth({ onDone, onHome }: { onDone: () => void; onHome: () => void }) {
  const card = useRef<HTMLDivElement>(null)
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const [busy, setBusy] = useState<Social | null>(null)
  const [withEmail, setWithEmail] = useState(false)
  const [mode, setMode] = useState<Mode>('login')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [error, setError] = useState<AuthError | null>(null)
  const [forgot, setForgot] = useState(false)

  useEffect(() => () => clearTimeout(timer.current), [])

  useLayoutEffect(() => {
    if (story.reducedMotion || !card.current) return
    const ctx = gsap.context(() => {
      gsap.from(card.current, { y: 30, opacity: 0, scale: 0.97, duration: 0.7, ease: 'power3.out' })
      gsap.from('.auth__in', { y: 12, opacity: 0, duration: 0.45, stagger: 0.05, delay: 0.2, ease: 'power2.out' })
    }, card)
    return () => ctx.revert()
  }, [])

  // Simulated provider round-trip: long enough to read as "connecting", short enough not to annoy.
  const social = (p: Social) => {
    if (busy) return
    setBusy(p)
    timer.current = setTimeout(() => {
      signInWith(p)
      onDone()
    }, 900)
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const err = mode === 'login' ? signIn(email, password) : signUp(name, email, password)
    setError(err)
    if (!err) onDone()
  }

  const switchMode = (m: Mode) => {
    setMode(m)
    setError(null)
    setForgot(false)
  }

  const fieldError = (f: AuthError['field']) =>
    error?.field === f ? (
      <small className="auth__err" role="alert">
        {error.text}
        {error.text.endsWith('Đăng ký?') && (
          <button type="button" className="link" onClick={() => switchMode('signup')}>
            Đăng ký ngay
          </button>
        )}
      </small>
    ) : null

  return (
    <div className="auth">
      <div className="auth__card" ref={card}>
        <header className="auth__in">
          <h1>Bắt đầu chuyến Đà Lạt</h1>
          <p>Đăng nhập để lưu chuyến đi và mở lại trên máy khác.</p>
        </header>

        <div className="auth__social auth__in">
          <SocialButton p="google" busy={busy} onClick={social} wide />
          <div className="auth__row">
            {(['zalo', 'facebook', 'apple', 'tiktok'] as const).map((p) => (
              <SocialButton key={p} p={p} busy={busy} onClick={social} />
            ))}
          </div>
        </div>

        {!withEmail ? (
          <button className="auth__email-toggle auth__in" onClick={() => setWithEmail(true)}>
            Dùng email và mật khẩu
          </button>
        ) : (
          <form className="auth__form" onSubmit={submit} noValidate>
            <div className="seg auth__tabs" role="tablist" aria-label="Đăng nhập hoặc đăng ký">
              {(['login', 'signup'] as const).map((m) => (
                <button key={m} type="button" role="tab" aria-selected={mode === m} aria-checked={mode === m} onClick={() => switchMode(m)}>
                  {m === 'login' ? 'Đăng nhập' : 'Đăng ký'}
                </button>
              ))}
            </div>
            {mode === 'signup' && (
              <label className="field">
                <span>Tên của bạn</span>
                <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" aria-invalid={error?.field === 'name'} />
                {fieldError('name')}
              </label>
            )}
            <label className="field">
              <span>Email</span>
              <input type="email" inputMode="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" aria-invalid={error?.field === 'email'} />
              {fieldError('email')}
            </label>
            <label className="field">
              <span>Mật khẩu</span>
              <span className="auth__pass">
                <input
                  type={show ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                  aria-invalid={error?.field === 'password'}
                />
                <button type="button" className="link" onClick={() => setShow((s) => !s)}>
                  {show ? 'Ẩn' : 'Hiện'}
                </button>
              </span>
              {mode === 'signup' && !fieldError('password') && <small className="auth__hint">Ít nhất 8 ký tự.</small>}
              {fieldError('password')}
            </label>
            {mode === 'login' && (
              <p className="auth__forgot">
                {forgot ? (
                  <span role="status">Bản thử chưa gửi được email đặt lại mật khẩu.</span>
                ) : (
                  <button type="button" className="link" onClick={() => setForgot(true)}>
                    Quên mật khẩu?
                  </button>
                )}
              </p>
            )}
            <button className="btn" type="submit">
              {mode === 'login' ? 'Đăng nhập' : 'Tạo tài khoản'}
            </button>
          </form>
        )}

        <div className="auth__or auth__in">
          <span>hoặc</span>
        </div>

        <button
          className="auth__guest auth__in"
          onClick={() => {
            continueAsGuest()
            onDone()
          }}
        >
          <b>Dùng thử, không cần tài khoản</b>
          <small>Chuyến đi lưu trên trình duyệt này. Tạo tài khoản sau cũng được.</small>
        </button>

        <footer className="auth__foot auth__in">
          <p>Bản thử: đăng nhập được mô phỏng ngay trên trình duyệt, chưa gửi dữ liệu nào đi đâu.</p>
          <button className="link" onClick={onHome}>
            Về trang giới thiệu
          </button>
        </footer>
      </div>
    </div>
  )
}

function SocialButton({ p, busy, onClick, wide }: { p: Social; busy: Social | null; onClick: (p: Social) => void; wide?: boolean }) {
  const label = PROVIDER_LABEL[p]
  return (
    <button
      type="button"
      className={`social social--${p}${wide ? ' social--wide' : ''}${busy === p ? ' is-busy' : ''}`}
      onClick={() => onClick(p)}
      disabled={!!busy}
      aria-label={`Tiếp tục với ${label}`}
    >
      {busy === p ? <span className="social__spin" aria-hidden="true" /> : MARK[p]}
      <span>{busy === p && wide ? 'Đang kết nối…' : wide ? `Tiếp tục với ${label}` : label}</span>
    </button>
  )
}

// Simplified provider marks for the sign-in buttons.
const MARK: Record<Social, ReactNode> = {
  google: (
    <svg viewBox="0 0 48 48" width="20" height="20" aria-hidden="true">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
    </svg>
  ),
  zalo: (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
      <rect width="24" height="24" rx="6" fill="#0068FF" />
      <text x="12" y="15.2" textAnchor="middle" fontSize="7.6" fontWeight="800" fill="#fff" fontFamily="Arial, sans-serif">
        Zalo
      </text>
    </svg>
  ),
  facebook: (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
      <circle cx="12" cy="12" r="12" fill="#1877F2" />
      <path fill="#fff" d="M13.4 24v-8.6h2.9l.44-3.37H13.4V9.88c0-.97.27-1.64 1.66-1.64h1.77V5.23a23.7 23.7 0 0 0-2.58-.13c-2.56 0-4.31 1.56-4.31 4.43v2.5H7.04v3.37h2.9V24z" />
    </svg>
  ),
  apple: (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
      <path
        fill="currentColor"
        d="M16.37 12.6c-.02-2.3 1.88-3.4 1.96-3.46-1.07-1.56-2.73-1.78-3.32-1.8-1.41-.14-2.76.83-3.47.83-.72 0-1.82-.81-2.99-.79-1.54.02-2.96.9-3.75 2.27-1.6 2.78-.41 6.89 1.15 9.14.76 1.1 1.67 2.34 2.86 2.3 1.15-.05 1.58-.74 2.97-.74 1.38 0 1.77.74 2.98.72 1.23-.02 2.01-1.12 2.77-2.23.87-1.28 1.23-2.52 1.25-2.58-.03-.01-2.4-.92-2.41-3.66zM14.1 5.86c.63-.77 1.06-1.83.94-2.9-.91.04-2.02.61-2.67 1.37-.59.68-1.1 1.77-.96 2.81 1.02.08 2.05-.52 2.69-1.28z"
      />
    </svg>
  ),
  tiktok: (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
      <path fill="#25F4EE" d="M15.9 5.3A4.3 4.3 0 0 1 14.8 2.5h-3.1v12.4a2.6 2.6 0 1 1-1.8-2.48V9.16a5.7 5.7 0 1 0 4.9 5.64V8.5a7.4 7.4 0 0 0 4.3 1.38V6.8s-1.9.1-3.2-1.5z" transform="translate(-.6 .4)" />
      <path fill="#FE2C55" d="M15.9 5.3A4.3 4.3 0 0 1 14.8 2.5h-3.1v12.4a2.6 2.6 0 1 1-1.8-2.48V9.16a5.7 5.7 0 1 0 4.9 5.64V8.5a7.4 7.4 0 0 0 4.3 1.38V6.8s-1.9.1-3.2-1.5z" transform="translate(.6 -.4)" />
      <path fill="#111" d="M15.9 5.3A4.3 4.3 0 0 1 14.8 2.5h-3.1v12.4a2.6 2.6 0 1 1-1.8-2.48V9.16a5.7 5.7 0 1 0 4.9 5.64V8.5a7.4 7.4 0 0 0 4.3 1.38V6.8s-1.9.1-3.2-1.5z" />
    </svg>
  ),
}
