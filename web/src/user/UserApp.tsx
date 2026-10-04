import { useEffect } from 'react'
import { useSnapshot } from '../data/store'
import { Auth } from '../pages/Auth'
import { Start } from '../pages/Start'
import { match, navigate } from '../router'
import { Icon } from '../ui/bits'
import { DecisionProvider, useDecision } from './pd/decision'
import { PlanningProvider } from './planning/planning'
import { Compare } from './screens/Compare'
import { CurateBar } from './screens/Curate'
import { Explore } from './screens/Explore'
import { Feasibility } from './screens/Feasibility'
import { Feedback } from './screens/Feedback'
import { Home } from './screens/Home'
import { Itinerary } from './screens/Itinerary'
import { PlaceDetail } from './screens/PlaceDetail'
import { Profile } from './screens/Profile'
import { Shortlist } from './screens/Shortlist'
import { Understand } from './screens/Understand'
import { initialOf, useAccount } from './account'
import { hasTrip, STEPS, stepOf, TripProvider, useTrip } from './trip'
import './css/base.css'
import './css/shell.css'
import './css/understand.css'
import './css/shortlist.css'
import './css/place.css'
import './css/check.css'
import './css/plan.css'
import './css/pages.css'

const NAV = [
  { path: '/app', label: 'Trang chủ' },
  { path: '/app/trip', label: 'Chuyến đi' },
  { path: '/app/explore', label: 'Khám phá' },
  { path: '/app/profile', label: 'Hồ sơ' },
]

export function UserApp({ path, onHome }: { path: string; onHome: () => void }) {
  return (
    <TripProvider>
      <DecisionProvider>
        <Shell path={path} onHome={onHome} />
      </DecisionProvider>
    </TripProvider>
  )
}

function Shell({ path, onHome }: { path: string; onHome: () => void }) {
  const { snap, error } = useSnapshot()
  const account = useAccount()
  const { trip } = useTrip()
  const { view } = useDecision()
  const clean = path.split('?')[0]
  const base = '/' + clean.split('/').filter(Boolean).slice(0, 2).join('/')
  const returning = hasTrip(trip)

  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [base])

  // "Chuyến đi" in the outer nav resumes the trip at the step it stopped on.
  useEffect(() => {
    if (base === '/app/trip') navigate(returning ? stepOf(trip).path : '/app/start', { replace: true })
  }, [base, returning, trip])

  const step = STEPS.findIndex((s) => base === s.path || (s.path === '/app/shortlist' && ['/app/place', '/app/compare'].includes(base)))
  const showCurate = ['/app/shortlist', '/app/place', '/app/compare'].includes(base) && (view?.selected.length ?? 0) > 0

  let screen
  let mode: 'bare' | 'flow' | 'nav' = 'flow'
  let m: Record<string, string> | null
  if (!account && (clean === '/app' || base === '/app/start' || base === '/app/login')) {
    // First visit: sign in, sign up or go on as a guest. Nothing behind it is locked.
    screen = <Auth onHome={onHome} onDone={() => navigate(base === '/app/login' ? '/app/profile' : '/app', { replace: true })} />
    mode = 'bare'
  } else if (base === '/app/login') {
    screen = <Auth onHome={onHome} onDone={() => navigate('/app/profile', { replace: true })} />
    mode = 'bare'
  } else if (clean === '/app' && returning) {
    screen = <Home />
    mode = 'nav'
  } else if (clean === '/app' || base === '/app/start') screen = <Start onHome={onHome} onDone={() => navigate('/app/understand')} />
  else if (base === '/app/profile') {
    screen = <Profile />
    mode = 'nav'
  } else if (base === '/app/explore') {
    screen = <Explore />
    mode = 'nav'
  } else if (!snap)
    screen = (
      <div className={`loading${error ? ' loading--error' : ''}`} role="status">
        {error ? `Không tải được dữ liệu địa điểm (${error}). Chạy scripts/export_snapshot.py rồi tải lại.` : 'Đang tải dữ liệu Đà Lạt'}
      </div>
    )
  else if (base === '/app/understand') screen = <Understand />
  else if (base === '/app/shortlist') screen = <Shortlist />
  else if ((m = match(path, '/app/place/:id'))) screen = <PlaceDetail id={m.id} key={m.id} />
  else if ((m = match(path, '/app/compare/:ids'))) screen = <Compare ids={m.ids.split(',')} key={m.ids} />
  else if (base === '/app/feasibility') screen = <Feasibility />
  else if (base === '/app/plan')
    screen = (
      <PlanningProvider>
        <Itinerary />
      </PlanningProvider>
    )
  else if (base === '/app/feedback') screen = <Feedback />
  else screen = <div className="loading loading--error">Không có trang này.</div>

  const finished = base === '/app/feedback'

  return (
    <div className={`uapp uapp--${mode}`}>
      <header className="ubar">
        <a
          className="ubar__mark"
          href="/"
          onClick={(e) => {
            e.preventDefault()
            if (mode === 'bare') onHome()
            else navigate('/app')
          }}
        >
          TripGuardian
        </a>
        {mode === 'flow' && (
          <nav className="usteps" aria-label="Bốn bước lập chuyến">
            <ol>
              {STEPS.map((s, i) => {
                const state = finished || i < step ? 'done' : i === step ? 'now' : 'next'
                return (
                  <li key={s.path} className={`is-${state}`}>
                    <button type="button" onClick={() => navigate(s.path)} aria-current={state === 'now' ? 'step' : undefined}>
                      {state === 'done' && (
                        <span className="usteps__tick" aria-hidden="true">
                          <Icon name="check" size={11} />
                        </span>
                      )}
                      {s.label}
                      {state === 'done' && <span className="visually-hidden"> (đã xong)</span>}
                    </button>
                  </li>
                )
              })}
            </ol>
          </nav>
        )}
        {mode === 'nav' && (
          <nav className="unav" aria-label="Điều hướng">
            {NAV.map((n) => {
              const on = n.path === '/app' ? clean === '/app' : base === n.path
              return (
                <a
                  key={n.path}
                  href={n.path}
                  className={on ? 'is-on' : ''}
                  aria-current={on ? 'page' : undefined}
                  onClick={(e) => {
                    e.preventDefault()
                    navigate(n.path)
                  }}
                >
                  {n.label}
                </a>
              )
            })}
          </nav>
        )}
        {mode !== 'bare' && (
          <button type="button" className="ubar__me" aria-label="Hồ sơ của bạn" onClick={() => navigate('/app/profile')}>
            {initialOf(account) ? <span className="iconbtn__initial">{initialOf(account)}</span> : <Icon name="user" />}
          </button>
        )}
      </header>
      <main className={`umain${showCurate ? ' has-curate' : ''}`}>{screen}</main>
      {showCurate && <CurateBar />}
    </div>
  )
}
