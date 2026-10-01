import { useEffect } from 'react'
import { useSnapshot } from '../data/store'
import { Start } from '../pages/Start'
import { match, navigate } from '../router'
import { story } from '../scene/story'
import { Icon } from '../ui/bits'
import { Compare } from './screens/Compare'
import { CurateBar } from './screens/Curate'
import { Discover } from './screens/Discover'
import { Feasibility } from './screens/Feasibility'
import { Feedback } from './screens/Feedback'
import { Itinerary } from './screens/Itinerary'
import { PlaceDetail } from './screens/PlaceDetail'
import { Profile } from './screens/Profile'
import { Setup } from './screens/Setup'
import { Shortlist } from './screens/Shortlist'
import { TripProvider, useTrip } from './trip'
import './user.css'

const STEPS = [
  { path: '/app/setup', label: 'Chuyến đi' },
  { path: '/app/discover', label: 'Sở thích' },
  { path: '/app/shortlist', label: 'Chọn nơi' },
  { path: '/app/feasibility', label: 'Khả thi' },
  { path: '/app/plan', label: 'Lịch trình' },
]

// Background scene per screen: the plan visibly "comes together" behind the UI.
const SCENE: Record<string, [number, number]> = {
  '/app': [0, 0.2],
  '/app/setup': [1, 0.28],
  '/app/discover': [2, 0.36],
  '/app/shortlist': [3, 0.5],
  '/app/place': [3, 0.5],
  '/app/compare': [3, 0.55],
  '/app/feasibility': [4, 0.8],
  '/app/plan': [5, 0.96],
  '/app/profile': [6, 0.3],
  '/app/feedback': [6, 0.96],
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
  const base = '/' + path.split('?')[0].split('/').filter(Boolean).slice(0, 2).join('/')

  useEffect(() => {
    const [step, scene] = SCENE[base] ?? [0, 0.2]
    story.appStep = step
    story.appScene = scene
    window.scrollTo({ top: 0 })
  }, [base])

  const stepIndex = STEPS.findIndex((s) => base === s.path || (s.path === '/app/shortlist' && ['/app/place', '/app/compare'].includes(base)))
  const showCurate = ['/app/shortlist', '/app/place', '/app/compare'].includes(base) && trip.selected.length > 0

  let screen
  let m: Record<string, string> | null
  if (path.split('?')[0] === '/app') screen = <Start onHome={onHome} onDone={() => navigate('/app/setup')} />
  else if (!snap)
    screen = (
      <div className="loading" role="status">
        {error ? `Không tải được dữ liệu địa điểm (${error}). Chạy scripts/export_snapshot.py rồi tải lại.` : 'Đang tải dữ liệu Đà Lạt'}
      </div>
    )
  else if (base === '/app/setup') screen = <Setup />
  else if (base === '/app/discover') screen = <Discover />
  else if (base === '/app/shortlist') screen = <Shortlist />
  else if ((m = match(path, '/app/place/:id'))) screen = <PlaceDetail id={m.id} key={m.id} />
  else if ((m = match(path, '/app/compare/:ids'))) screen = <Compare ids={m.ids.split(',')} key={m.ids} />
  else if (base === '/app/feasibility') screen = <Feasibility />
  else if (base === '/app/plan') screen = <Itinerary />
  else if (base === '/app/profile') screen = <Profile />
  else if (base === '/app/feedback') screen = <Feedback />
  else screen = <div className="loading">Không có trang này.</div>

  return (
    <div className="uapp">
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
          <nav className="usteps" aria-label="Tiến trình">
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
          <Icon name="user" />
        </button>
      </header>
      <main className={`umain${showCurate ? ' has-curate' : ''}`}>{screen}</main>
      {showCurate && snap && <CurateBar />}
    </div>
  )
}
