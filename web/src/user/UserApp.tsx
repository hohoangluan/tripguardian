import { useEffect } from 'react'
import { useSnapshot } from '../data/store'
import { Auth } from '../pages/Auth'
import { Start } from '../pages/Start'
import { match, navigate } from '../router'
import { Icon } from '../ui/bits'
import { Compare } from './screens/Compare'
import { CurateBar } from './screens/Curate'
import { Feasibility } from './screens/Feasibility'
import { Feedback } from './screens/Feedback'
import { Itinerary } from './screens/Itinerary'
import { PlaceDetail } from './screens/PlaceDetail'
import { Profile } from './screens/Profile'
import { Shortlist } from './screens/Shortlist'
import { Understand } from './screens/Understand'
import { initialOf, useAccount } from './account'
import { TripProvider, useTrip } from './trip'
import './user.css'

const STEPS = [
  { path: '/app/understand', label: 'Hiểu chuyến đi' },
  { path: '/app/shortlist', label: 'Chọn nơi' },
  { path: '/app/feasibility', label: 'Khả thi' },
  { path: '/app/plan', label: 'Lịch trình' },
]

// Poster illustration behind each screen's title (public/img/poster-*.webp).
const POSTER: Record<string, string> = {
  '/app': 'start',
  '/app/login': 'start',
  '/app/understand': 'discover',
  '/app/shortlist': 'shortlist',
  '/app/place': 'shortlist',
  '/app/compare': 'shortlist',
  '/app/feasibility': 'feasibility',
  '/app/plan': 'plan',
  '/app/profile': 'profile',
  '/app/feedback': 'plan',
}

export function UserApp({ path, onHome }: { path: string; onHome: () => void }) {
  return (
    <TripProvider>
      <Shell path={path} onHome={onHome} />
    </TripProvider>
  )
}

function Shell({ path, onHome }: { path: string; onHome: () => void }) {
  const { snap, error } = useSnapshot()
  const { trip } = useTrip()
  const account = useAccount()
  const base = '/' + path.split('?')[0].split('/').filter(Boolean).slice(0, 2).join('/')

  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [base])

  const stepIndex = STEPS.findIndex((s) => base === s.path || (s.path === '/app/shortlist' && ['/app/place', '/app/compare'].includes(base)))
  const showCurate = ['/app/shortlist', '/app/place', '/app/compare'].includes(base) && trip.selected.length > 0

  let screen
  let m: Record<string, string> | null
  // First visit: sign in, sign up or go on as a guest; then the two start questions.
  if (path.split('?')[0] === '/app') screen = account ? <Start onHome={onHome} onDone={() => navigate('/app/understand')} /> : <Auth onHome={onHome} onDone={() => {}} />
  else if (base === '/app/login') screen = <Auth onHome={onHome} onDone={() => navigate('/app/profile', { replace: true })} />
  else if (!snap)
    screen = (
      <div className="loading" role="status">
        {error ? `Không tải được dữ liệu địa điểm (${error}). Chạy scripts/export_snapshot.py rồi tải lại.` : 'Đang tải dữ liệu Đà Lạt'}
      </div>
    )
  else if (base === '/app/understand') screen = <Understand />
  else if (base === '/app/shortlist') screen = <Shortlist />
  else if ((m = match(path, '/app/place/:id'))) screen = <PlaceDetail id={m.id} key={m.id} />
  else if ((m = match(path, '/app/compare/:ids'))) screen = <Compare ids={m.ids.split(',')} key={m.ids} />
  else if (base === '/app/feasibility') screen = <Feasibility />
  else if (base === '/app/plan') screen = <Itinerary />
  else if (base === '/app/profile') screen = <Profile />
  else if (base === '/app/feedback') screen = <Feedback />
  else screen = <div className="loading">Không có trang này.</div>

  const poster = POSTER[base] ?? 'shortlist'

  return (
    <div className={`uapp${base === '/app' || base === '/app/login' ? ' uapp--start' : ''}`}>
      <div className="uposter" aria-hidden="true">
        <img src={`/img/poster-${poster}.webp`} alt="" key={poster} decoding="async" />
      </div>
      <header className="ubar">
        <a
          className="wordmark"
          href="/"
          onClick={(e) => {
            e.preventDefault()
            onHome()
          }}
        >
          TripGuardian
        </a>
        {stepIndex >= 0 && (
          <nav className="usteps" aria-label="Tiến trình" style={{ ['--done' as string]: (stepIndex + 1) / STEPS.length }}>
            <p className="usteps__now" aria-hidden="true">
              <span>
                Bước {stepIndex + 1}/{STEPS.length}
              </span>{' '}
              {STEPS[stepIndex].label}
            </p>
            <ol>
              {STEPS.map((s, i) => (
                <li key={s.path} className={i === stepIndex ? 'is-active' : i < stepIndex ? 'is-done' : ''}>
                  <button type="button" onClick={() => navigate(s.path)} aria-current={i === stepIndex ? 'step' : undefined}>
                    <span className="usteps__n">{i < stepIndex ? <Icon name="check" size={12} /> : i + 1}</span>
                    <span className="usteps__label">{s.label}</span>
                  </button>
                </li>
              ))}
            </ol>
          </nav>
        )}
        <button type="button" className="iconbtn" aria-label="Hồ sơ của bạn" onClick={() => navigate('/app/profile')}>
          {initialOf(account) ? <span className="iconbtn__initial">{initialOf(account)}</span> : <Icon name="user" />}
        </button>
      </header>
      <main className={`umain${showCurate ? ' has-curate' : ''}`}>{screen}</main>
      {showCurate && snap && <CurateBar />}
    </div>
  )
}
