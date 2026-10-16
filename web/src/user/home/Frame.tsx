import { useEffect, useState, type CSSProperties, type ReactNode } from 'react'
import { signOut, useAccount } from '../account'
import { tripSummaries } from '../pd/api'
import { useDecision } from '../pd/decision'
import { loadLibrary, useUi } from '../store'
import { hasTrip, STEPS, stepOf, useTrip } from '../trip'
import { go, Link, PlacePhoto } from '../ui/common'
import { Icon, type IconName } from '../ui/icons'
import { Who } from './Who'
import { HomeDialogs, openCreate } from './dialogs'

// The app frame of every page that is not a step of the trip flow (ui_mock_for_design/designs/homepage):
// a sidebar card | the page (friends and your activity drop down from the icon in its top corner), and the trip in progress along the bottom while it is not yet confirmed.
export function Frame({ path, children }: { path: string; children: ReactNode }) {
  const account = useAccount()
  useEffect(() => { if (account && !account.needs_consent) void loadLibrary() }, [account?.id]) // eslint-disable-line react-hooks/exhaustive-deps
  const bar = useUnfinishedTrip()
  return (
    <div className="tg-home tg-hf">
      <div className={`tg-hf__app ${bar ? 'has-bar' : ''}`}>
        <div className="tg-hf__ws">
          <Sidebar path={path} />
          <div className="tg-hf__mid">
            {children}
            {path !== '' && <Who compact className="tg-hf__corner" />}
          </div>
        </div>
        {bar && <JourneyBar />}
        <button type="button" className="tg-hf__new" onClick={() => openCreate()}><Icon name="plus" size={20} />Tạo chuyến đi</button>
      </div>
      <HomeDialogs />
    </div>
  )
}

// The bar is the trip being made: it shows only while the server lists this trip and its itinerary is not confirmed.
// A trip the server does not know (cleared, or the server not answering) is not a trip the user has: no bar.
function useUnfinishedTrip() {
  const { trip } = useTrip()
  const [show, setShow] = useState(false)
  useEffect(() => {
    const id = trip.journeyId
    if (!hasTrip(trip) || !id) { setShow(false); return }
    let alive = true
    tripSummaries().then((l) => { if (alive) setShow(l.some((t) => t.id === id && !t.confirmed)) }, () => { if (alive) setShow(false) })
    return () => { alive = false }
  }, [trip.journeyId, trip.decisionId, trip.planningId]) // eslint-disable-line react-hooks/exhaustive-deps
  return show
}

const NAV: { to: string; label: string; icon: IconName }[] = [
  { to: '/', label: 'Dành cho bạn', icon: 'home' },
  { to: '/trips', label: 'Chuyến của tôi', icon: 'map' },
  { to: '/saved', label: 'Đã lưu', icon: 'heart' },
  { to: '/recent', label: 'Đã xem gần đây', icon: 'clock' },
]
const ACCOUNT_NAV: { to: string; label: string; icon: IconName }[] = [
  { to: '/profile', label: 'Cài đặt', icon: 'settings' },
  { to: '/support', label: 'Hỗ trợ', icon: 'info' },
]

// The sidebar is a slim rail of icons (after Pinterest's): the name of each button shows as a tooltip on hover or focus.
// Three blocks (new trip · places and trips · settings and support), the logo above them and sign-out alone at the bottom.
export function Sidebar({ path }: { path: string }) {
  const saved = useUi((u) => u.saved.length + u.savedThemes.length)
  const account = useAccount()
  const guest = !!account?.guest
  const item = (n: { to: string; label: string; icon: IconName }) => {
    const on = n.to === '/' ? path === '' : path.startsWith(n.to)
    return (
      <li key={n.to}>
        <Link to={n.to} className={`tg-hf__item ${on ? 'is-on' : ''}`} data-tip={n.label} aria-label={n.label} aria-current={on ? 'page' : undefined}>
          <Icon name={n.icon} size={26} />
          {n.to === '/saved' && saved > 0 && <b className="tg-hf__count" aria-label={`${saved} mục`}>{saved > 99 ? '99+' : saved}</b>}
        </Link>
      </li>
    )
  }
  return (
    <nav className="tg-hf__side" aria-label="Điều hướng chính">
      <div className="tg-hf__blk tg-hf__blk--top"><span className="tg-hf__logo" aria-hidden="true" /></div>
      <div className="tg-hf__mids">
        <ul className="tg-hf__blk tg-hf__nav">{NAV.map(item)}</ul>
        <ul className="tg-hf__blk tg-hf__nav">{ACCOUNT_NAV.map(item)}</ul>
      </div>
      <div className="tg-hf__foot">
        {guest
          ? <Link to="/login" className="tg-hf__item" data-tip="Đăng nhập" aria-label="Đăng nhập"><Icon name="user" size={26} /></Link>
          : <button type="button" className="tg-hf__item" data-tip="Đăng xuất" aria-label="Đăng xuất" onClick={() => { void signOut() }}><Icon name="logout" size={26} /></button>}
      </div>
    </nav>
  )
}

function JourneyBar() {
  const { trip } = useTrip()
  const { view } = useDecision()
  const step = stepOf(trip)
  const ctx = trip.searchInput?.context
  const selected = view?.selected ?? trip.selected
  const steps = STEPS
  return (
    <footer className="tg-hf__bar" aria-label="Chuyến đang lập" style={{ '--tg-prog': `${((step.index + 0.5) / steps.length) * 100}%` } as CSSProperties}>
      <button type="button" className="tg-hf__trip" onClick={() => go(step.path)}>
        {selected[0] ? <PlacePhoto id={selected[0]} /> : <img src="/img/home/lake.jpg" alt="" />}
        <span><strong>Đà Lạt{ctx?.days ? ` ${ctx.days} ngày` : ''}</strong><small>{[ctx?.people ? `${ctx.people} người` : null, `${selected.length} nơi đã chọn`, `Đang ở ${step.label}`].filter(Boolean).join(' · ')}</small></span>
      </button>
      <ol className="tg-hf__steps" aria-label={`Bước ${step.index + 1} trên ${steps.length}: ${step.label}`}>
        {steps.map((s, i) => <li key={s.id} className={i < step.index ? 'is-done' : i === step.index ? 'is-now' : ''}><i>{i < step.index ? <Icon name="check" size={12} /> : i + 1}</i>{s.label}</li>)}
      </ol>
      <span className="tg-hf__bact">
        <Link to="/saved" className="tg-hb-icon" aria-label="Xem mục đã lưu"><Icon name="heart" size={16} /></Link>
        <button type="button" className="tg-hb-go" onClick={() => go(step.path)}>Đi tiếp<Icon name="arrow" size={15} /></button>
      </span>
    </footer>
  )
}
