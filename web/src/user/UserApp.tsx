import { Component, useEffect, useState, type ReactNode } from 'react'
import { useSnapshot } from '../data/store'
import { match, query } from '../router'
import { isGuest, signInHref, useAccount } from './account'
import { setEventJourney, track } from './events'
import { bindCacheAccount, loadJourney } from './journey'
import { openNote } from './notify'
import { bindOwner, clearSaved, loadSaved } from './store'
import { isPhone } from './landing/device'
import { DecisionProvider } from './pd/decision'
import { PlanningProvider } from './planning/planning'
import { Account, Saved, Trips } from './screens/Account'
import { Auth } from './screens/Auth'
import { Compare } from './screens/Compare'
import { Discover } from './screens/Discover'
import { Done } from './screens/Done'
import { Explore } from './screens/Explore'
import { GetApp } from './screens/GetApp'
import { Landing } from './screens/Landing'
import { PlaceDetail } from './screens/PlaceDetail'
import { Plan } from './screens/Plan'
import { Inbox } from './screens/Inbox'
import { Today } from './screens/Today'
import { Understand } from './screens/Understand'
import { TripProvider, useTrip } from './trip'
import { Busy, Empty, ArtHills, go, Toast } from './ui/common'
import { PlaceSheet } from './ui/PlaceSheet'
import { Rail } from './ui/Shell'
import './css/tokens.css'
import './css/base.css'
import './css/shell.css'
import './css/explore.css'
import './css/bar.css'
import './css/assistant.css'
import './css/disc.css'
import './css/sheet.css'
import './css/understand.css'
import './css/screens.css'
import './css/plan.css'
import './css/landing.css'
import './css/app.css'
import './css/today.css'

// docs/WEB.md §6: one surface for the landing (/) and the app (/app/...).
// Phones get the app download page on every user page (/, /app/..., shared links): the web is built for a computer.
export default function UserApp({ path }: { path: string }) {
  useEffect(() => {
    document.body.classList.add('tg-body')
    return () => document.body.classList.remove('tg-body')
  }, [])
  const clean = path.split('?')[0].replace(/\/$/, '')
  useEffect(() => { if (!isPhone()) track('page_view', { route: clean || '/' }) }, [clean])
  if (isPhone()) return <div className="tg tg-root tg-landing"><GetApp /></div>
  if (!clean.startsWith('/app')) {
    return (
      <TripProvider>
        <div className="tg tg-root tg-landing"><Landing /></div>
      </TripProvider>
    )
  }
  return (
    <TripProvider>
      <DecisionProvider>
        <Shell p={clean.slice('/app'.length)} sheet={query(path).get('place')} />
      </DecisionProvider>
    </TripProvider>
  )
}

function Shell({ p, sheet }: { p: string; sheet: string | null }) {
  const account = useAccount()
  const { trip, dispatch } = useTrip()
  useEffect(() => { setEventJourney(trip.journeyId ?? null) }, [trip.journeyId])
  // A link to one journey's step (/app/plan?journey=…, /app/explore?journey=… from a note or another device) opens
  // that journey, as Chuyến của tôi does; the server answers 404 for a journey of another account.
  const wanted = (p === '/plan' || p === '/explore') ? query(location.search).get('journey') : null
  const [adopt, setAdopt] = useState<'idle' | 'busy' | 'failed'>('idle')
  const switching = !!wanted && wanted !== trip.journeyId
  const ready = !!account && !account.needs_consent
  useEffect(() => {
    if (!switching || !ready) return
    setAdopt('busy')
    loadJourney(wanted).then((v) => {
      dispatch({ type: 'reset' })
      dispatch({ type: 'set', patch: { journeyId: v.id, decisionId: v.stage === 'trip' ? null : v.id, planningId: v.stage === 'planning' ? v.id : null } })
      if (v.stage === 'trip') go('/understand', { replace: true })
      else if (v.stage === 'decision' && p === '/plan') go(`/explore?journey=${v.id}`, { replace: true })
      setAdopt('idle')
    }, () => setAdopt('failed'))
  }, [switching, wanted, ready]) // eslint-disable-line react-hooks/exhaustive-deps
  const note = query(location.search).get('n')
  useEffect(() => { if (note && account) void openNote(note, 'link') }, [note, !!account]) // eslint-disable-line react-hooks/exhaustive-deps
  const { snap, error } = useSnapshot()
  useEffect(() => { if (error) console.error(`[TripGuardian] place snapshot did not load (${error}); run web/scripts/export_snapshot.py and reload`) }, [error])
  useEffect(() => { window.scrollTo({ top: 0 }) }, [p, !account])
  const signedIn = !!account && !account.needs_consent
  useEffect(() => { if (signedIn && !isGuest(account)) void loadSaved(); else clearSaved() }, [signedIn, account?.id]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (account !== undefined) bindCacheAccount(signedIn ? account!.id : null) }, [signedIn, account?.id]) // eslint-disable-line react-hooks/exhaustive-deps: journey cache is per account; sign-out empties it
  useEffect(() => {
    if (account === undefined) return
    if (bindOwner(signedIn ? account!.id : null, isGuest(account))) dispatch({ type: 'reset' }) // another account: its trip is not shown here
  }, [signedIn, account?.id]) // eslint-disable-line react-hooks/exhaustive-deps
  // The guest strip sits above the top bar; every layer that starts below the bar (portalled ones too) reads its height from :root.
  const guest = isGuest(account)
  useEffect(() => {
    document.documentElement.style.setProperty('--tg-guest', guest ? '36px' : '0px')
    return () => { document.documentElement.style.removeProperty('--tg-guest') }
  }, [guest])
  useEffect(() => { if (signedIn && p === '/login') go('/', { replace: true }) }, [signedIn, p])
  let m: Record<string, string> | null
  let rail = true
  let screen: ReactNode
  if (account === undefined) { screen = <div className="tg-page"><Busy text="Đang mở TripGuardian…" /></div>; rail = false }
  else if (!account || account.needs_consent) {
    // /app needs an account: Google brings the browser back to the page it asked for.
    screen = <Auth next={p === '/login' ? '/app' : '/app' + p + location.search} />
    rail = false
  } else if (p === '/login') { screen = <div className="tg-page"><Busy text="Đang vào…" /></div>; rail = false }
  else if (p === '/understand') { screen = <Understand />; rail = false } // talks to the harness only: never waits for the snapshot
  else if (switching && adopt === 'failed') {
    screen = <Empty art={<ArtHills />} title="Chưa mở được chuyến này" body="Chuyến này không thuộc tài khoản đang đăng nhập, hoặc không còn nữa. Các chuyến của bạn nằm ở Chuyến của tôi." action={<button type="button" className="tg-btn tg-btn--primary" onClick={() => go('/trips')}>Chuyến của tôi</button>} />
  } else if (switching) { screen = <div className="tg-page"><Busy text="Đang mở chuyến của bạn…" /></div>; rail = false }
  else if (!snap) {
    screen = error ? (
      <Empty art={<ArtHills />} title="TripGuardian đang cập nhật" body="Bạn thử lại sau ít phút nhé. Chuyến đi của bạn vẫn được giữ nguyên." action={<button type="button" className="tg-btn tg-btn--primary" onClick={() => location.reload()}>Thử lại</button>} />
    ) : (
      <div className="tg-page"><Busy text="Đang tải dữ liệu Đà Lạt…" /></div>
    )
  } else if (p === '') screen = <Discover />
  else if (p === '/explore') { screen = <Explore />; rail = false }
  else if ((m = match(p, '/explore/place/:id'))) { screen = <PlaceDetail id={m.id} key={m.id} />; rail = false }
  else if ((m = match(p, '/explore/compare/:ids'))) { screen = <Compare ids={m.ids.split(',')} key={m.ids} />; rail = false }
  else if (p === '/plan') { screen = <PlanningProvider><Plan /></PlanningProvider>; rail = false }
  else if (p === '/done') { screen = <Done />; rail = false }
  else if (p === '/today') screen = <Today />
  else if (p === '/inbox') screen = <Inbox />
  else if (p === '/trips') screen = <Trips />
  else if (p === '/saved') screen = <Saved />
  else if (p === '/profile') screen = <Account />
  else screen = <Empty art={<ArtHills />} title="Không có trang này" body="Đường dẫn này không còn dùng nữa." action={<button type="button" className="tg-btn tg-btn--primary" onClick={() => go('/')}>Về Khám phá</button>} />
  return (
    <div className="tg tg-root">
      {isGuest(account) && <div className="tg-guest" role="status">Bạn đang dùng thử: 1 chuyến, không lưu lịch sử. <a href={signInHref('/app')}>Đăng nhập để giữ chuyến</a></div>}
      <a className="tg-skip" href="#tg-main" onClick={(e) => { e.preventDefault(); document.getElementById('tg-main')?.focus() }}>Bỏ qua điều hướng</a>
      <div className={`tg-app ${rail ? 'has-rail' : ''}`}>
        {rail && <Rail path={p} />}
        <main id="tg-main" tabIndex={-1} key={p} className="tg-stage"><Guard>{screen}</Guard></main>
      </div>
      {sheet && snap && <PlaceSheet id={sheet} key={sheet} modal />}
      <Toast />
    </div>
  )
}

// A screen that fails to render shows a way out instead of a blank page; the trip itself is safe on the server.
class Guard extends Component<{ children: ReactNode }, { error: string | null }> {
  state = { error: null as string | null }
  static getDerivedStateFromError(e: unknown) {
    return { error: e instanceof Error ? e.message : String(e) }
  }
  render() {
    if (!this.state.error) return this.props.children
    return <Empty art={<ArtHills />} title="Màn này gặp lỗi hiển thị" body="Chuyến đi của bạn vẫn còn nguyên trên máy chủ. Tải lại trang hoặc về Khám phá." action={<button type="button" className="tg-btn tg-btn--primary" onClick={() => location.reload()}>Tải lại</button>} />
  }
}
