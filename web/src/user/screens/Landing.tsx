import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import Lenis from 'lenis'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { startGuest, useAccount } from '../account'
import { track } from '../events'
import { flushSync } from 'react-dom'
import { navigate } from '../../router'
import { canTransition, startTransition } from '../../viewTransition'
import { prefetchSnapshot } from '../../data/store'
import { fetchLandscape } from '../landing/bin'
import { ClipPlayer } from '../landing/clips'
import { hasGpu } from '../landing/device'
import { AREAS, DAY, FOCUS, ROAD_FACTOR, ROUTE, SCENE_PLACES, SPEED_KMH, byName } from '../landing/route'
import stats from '../landing/stats.json'
import type { DalatScene, ScenePlace, SceneState } from '../landing/scene'
import { reducedMotion } from '../lib'
import { STORY_LEN, stateTweens } from '../landing/story'
import { Photo, thumbOf } from '../ui/common'
import { Icon, Logo } from '../ui/icons'
import { FAQ } from '../faq'
import { useTitle } from '../ui/Shell'

// Desktop landing: one sticky stage with a living journey map of Đà Lạt and the TripGuardian cloud flying in front of
// it (landing/scene.ts); scrolling moves the camera through six chapters.
// Real places copied from the snapshot by web/scripts/pick_landing_places.py.
gsap.registerPlugin(ScrollTrigger)
// Beat i is fully in at timeline time i; the rail groups the evidence beat with selection.
const RAIL: [string, number][] = [['Mở đầu', 0], ['Tìm hiểu', 1], ['Lựa chọn', 2], ['Lịch trình', 4], ['Đánh giá', 5]]
const BEATS = 6
const stepOf = (beat: number) => (beat === 3 ? 2 : beat)
const HINTS = ['Cuộn xuống để xem cách hoạt động', 'Cuộn tiếp: Lựa chọn', 'Cuộn tiếp: lý do từng nơi', 'Cuộn tiếp: Lịch trình', 'Cuộn tiếp: Đánh giá', 'Cuộn tiếp: ảnh thật của từng chỗ']
// The light version uses one frame from the live map for each chapter.
const PLATES = ['/img/landing-poster.webp', '/img/landing-p1.webp', '/img/landing-p2.webp', '/img/landing-p3.webp', '/img/landing-p4.webp', '/img/landing-p5.webp']
// the four photos of the "Địa điểm thật" section: place, and which of its photos shows the place best (daylight, recognisable)
const SHOWCASE: [string, number][] = [['Thung lũng Tình Yêu', 3], ['Hồ Xuân Hương', 1], ['Dinh III', 3], ['Thác Datanla', 0]]
const LATE = ['noon', 'afternoon', 'evening', 'night'] // a crowd peak the example day's 08:45 visit comes before
const DAYPART: Record<string, string> = { early_morning: 'sáng sớm', morning: 'buổi sáng', noon: 'buổi trưa', afternoon: 'buổi chiều', evening: 'buổi tối', night: 'ban đêm' }
// Where the free camera can fly: real places, and how close to look at each
const FLY: { name: string; lat: number; lng: number; dist: number }[] = [
  { name: 'Trung tâm', lat: 11.9445, lng: 108.4462, dist: 55 },
  { name: 'Langbiang', lat: 12.0453, lng: 108.441, dist: 110 },
  { name: 'Hồ Tuyền Lâm', lat: 11.8916, lng: 108.4227, dist: 80 },
  { name: 'Cầu Đất', lat: 11.872, lng: 108.556, dist: 90 },
  { name: 'Trại Mát', lat: 11.948, lng: 108.505, dist: 70 },
]
const num = (n: number) => n.toLocaleString('vi-VN')
const km = (a: ScenePlace, b: ScenePlace) => {
  const R = 6371, r = Math.PI / 180
  const x = (b.lng - a.lng) * r * Math.cos(((a.lat + b.lat) / 2) * r), y = (b.lat - a.lat) * r
  return Math.hypot(x, y) * R
}
const legMinutes = (a: ScenePlace, b: ScenePlace) => Math.max(1, Math.round((km(a, b) * ROAD_FACTOR / SPEED_KMH) * 60))
const shiftFor = (w: number) => (w > 1100 ? 0.2 : w > 900 ? 0.25 : 0) // keep the model right of the text column

// Real screens of the app for the chapters (docs/UI_SPEC_LANDING.md §2): drop `app-<name>.webp` into
// web/src/user/landing/shots/ and rebuild. Found at build time, so a missing screen costs no request; until it is there
// the chapter keeps its drawn card.
const SHOTS = Object.fromEntries(Object.entries(import.meta.glob<string>('../landing/shots/app-*.webp', { eager: true, query: '?url', import: 'default' }))
  .map(([path, url]) => [path.replace(/^.*app-|\.webp$/g, ''), url]))
function Shot({ name, label, children }: { name: 'understand' | 'choose' | 'plan' | 'feedback'; label: string; children: ReactNode }) {
  const src = SHOTS[name]
  if (!src) return <>{children}</>
  return <figure className="tg-l3__shot"><img src={src} alt={`Giao diện TripGuardian: ${label}`} decoding="async" /><figcaption>Giao diện thật · {label}</figcaption></figure>
}

export function Landing() {
  useTitle('TripGuardian · Đà Lạt')
  const story = useRef<HTMLElement>(null)
  const stage = useRef<HTMLDivElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const counter = useRef<HTMLSpanElement>(null)
  const areaEls = useRef<HTMLElement[]>([])
  const pinEls = useRef<HTMLElement[]>([])
  const dayEls = useRef<HTMLElement[]>([])
  const mascotImg = useRef<HTMLImageElement>(null)
  const lenisRef = useRef<Lenis | null>(null)
  const [still] = useState(reducedMotion)
  // video: the story pre-rendered (every machine, no WebGL; paused 2026-10-16 with 3 of 16 clips rendered, so only
  // with ?clips=on); 3d: the live model; flat: one picture per chapter (reduced motion, no GPU, or a video that
  // cannot play)
  const [mode, setMode] = useState<'video' | '3d' | 'flat'>(() => reducedMotion() ? 'flat'
    : /[?&]clips=on/.test(location.search) ? 'video' : hasGpu() ? '3d' : 'flat')
  const flat = mode === 'flat'
  const setFlat = (on: boolean) => { if (on) setMode('flat') }
  const playerRef = useRef<ClipPlayer | null>(null)
  const clipHost = useRef<HTMLDivElement>(null)
  const wantExplore = useRef(false) // the visitor asked to explore before the live model was there
  const exploreRef = useRef(() => {})
  const [live, setLive] = useState(false) // the map has drawn its first frame: the poster fades out
  const [active, setActive] = useState(0)
  const sceneRef = useRef<DalatScene | null>(null)
  const [exploring, setExploring] = useState(false) // free exploration of the map
  const [leaving, setLeaving] = useState(false) // on its way to the home page
  const exploringRef = useRef(false)
  const [faq, setFaq] = useState(0)
  const account = useAccount()
  const starting = useRef(false)
  const member = !!account && !account.guest
  const spot = ROUTE[FOCUS]
  const peak = spot.crowd?.weekend ? Object.entries(spot.crowd.weekend).reduce((a, b) => (b[1] > a[1] ? b : a)) : null
  const showcase = SHOWCASE.map(([n, i]) => ({ place: byName(n), photo: byName(n).photos[i] }))

  // The next screens need the place data: fetch it while the visitor reads, but only once the model has drawn (or
  // cannot), so the 2.8 MB of covers never compete with the landscape for the connection.
  useEffect(() => {
    if (live || flat) prefetchSnapshot()
  }, [live, flat])

  // the map + scroll story
  useEffect(() => {
    const cv = canvas.current, st = stage.current, sec = story.current
    if (!cv || !st || !sec) return
    let scene: DalatScene | null = null
    let gone = false
    const state: SceneState = { cam: 0, dots: 1, five: 0, route: 0, travel: 0, areas: 1, shift: shiftFor(innerWidth), hour: 0, stamp: 0, lift: 0 }
    const push = () => scene?.set(state)
    // the itinerary lights the hour the cloud has walked to (the stops' places along the route come from the scene)
    const markDay = (travel = state.travel, stops = scene?.stops) => {
      const at = stops ?? DAY.map((_, i) => i / (DAY.length - 1))
      const now = travel > 0.002 ? at.reduce((n, u, i) => (u <= travel + 0.02 ? i : n), -1) : -1
      dayEls.current.forEach((el, i) => { el?.classList.toggle('is-now', i === now); el?.classList.toggle('is-past', i < now) })
    }

    const ro = new ResizeObserver(() => {
      state.shift = shiftFor(cv.clientWidth)
      scene?.resize(cv.clientWidth, cv.clientHeight)
      push()
    })
    const io = new IntersectionObserver(([e]) => scene?.setRunning(e.isIntersecting && !document.hidden))
    const onVis = () => scene?.setRunning(!document.hidden && st.getBoundingClientRect().bottom > 0)
    const onMove = (e: PointerEvent) => scene?.setPointer(e.clientX / innerWidth - 0.5, 0.5 - e.clientY / innerHeight)
    // Drag turns the model round the valley (vertical page scroll on touch screens still works, touch-action: pan-y).
    // Free exploration: drag turns, right-drag / Shift-drag slides, wheel and pinch zoom.
    const pts = new Map<number, { x: number; y: number }>()
    let pan = false
    let pinch = 0
    const down = (e: PointerEvent) => {
      if (e.pointerType === 'mouse' && e.button > 2) return
      if (e.pointerType === 'mouse' && e.button === 2 && !exploringRef.current) return
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY })
      pan = e.button === 2 || e.shiftKey || e.ctrlKey
      cv.setPointerCapture(e.pointerId)
      cv.classList.add('is-grabbing')
      if (pts.size === 2) {
        const [a, b] = [...pts.values()]
        pinch = Math.hypot(a.x - b.x, a.y - b.y)
      }
      if (!exploringRef.current) scene?.dragStart()
    }
    const drag = (e: PointerEvent) => {
      const prev = pts.get(e.pointerId)
      if (!prev) return
      const dx = e.clientX - prev.x, dy = e.clientY - prev.y
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY })
      if (!exploringRef.current) return void scene?.dragBy(dx, dy)
      if (pts.size >= 2) {
        // two fingers: the spread zooms, the pair's drift slides
        const [a, b] = [...pts.values()]
        const d = Math.hypot(a.x - b.x, a.y - b.y)
        if (pinch > 0 && d > 0) scene?.zoomBy(pinch / d)
        pinch = d
        scene?.explorePan(dx / 2, dy / 2)
      } else scene?.exploreDrag(dx, dy, pan)
    }
    const drop = (e: PointerEvent) => {
      if (!pts.delete(e.pointerId)) return
      pinch = 0
      if (pts.size) return
      cv.classList.remove('is-grabbing')
      if (!exploringRef.current) scene?.dragEnd()
    }
    const wheel = (e: WheelEvent) => {
      if (!exploringRef.current) return // the page scrolls as usual
      e.preventDefault()
      e.stopPropagation() // Lenis listens on the window
      scene?.zoomBy(Math.exp(Math.max(-120, Math.min(120, e.deltaY)) * 0.0013))
    }
    const menu = (e: Event) => { if (exploringRef.current) e.preventDefault() }
    cv.addEventListener('pointerdown', down)
    cv.addEventListener('pointermove', drag)
    cv.addEventListener('pointerup', drop)
    cv.addEventListener('pointercancel', drop)
    cv.addEventListener('wheel', wheel, { passive: false })
    cv.addEventListener('contextmenu', menu)
    // Chapters shrink on short desktop windows instead of running below the viewport.
    const fit = () => {
      if (still || innerWidth <= 900) return sec.querySelectorAll<HTMLElement>('.tg-l3__ch').forEach((el) => (el.style.zoom = ''))
      const room = st.clientHeight - 150
      sec.querySelectorAll<HTMLElement>('.tg-l3__ch').forEach((el) => {
        el.style.zoom = ''
        const height = el.offsetHeight
        if (height > room) el.style.zoom = String(Math.max(0.6, room / height))
      })
    }
    const fitRo = new ResizeObserver(fit)
    fitRo.observe(st)
    void document.fonts?.ready.then(fit)
    fit()
    // three.js and the 1.7k coordinates load only here, so phones (GetApp) never fetch them
    // the pre-rendered story: labels and the itinerary follow each frame of the video
    let player: ClipPlayer | null = null
    let unplay = () => {}
    if (mode === 'video' && clipHost.current) {
      player = new ClipPlayer(clipHost.current, BEATS)
      playerRef.current = player
      const box = { w: 1, h: 1 }
      const measure = () => { box.w = st.clientWidth; box.h = st.clientHeight }
      measure()
      addEventListener('resize', measure)
      unplay = () => { removeEventListener('resize', measure); player?.dispose(); playerRef.current = null }
      const place = (el: HTMLElement | undefined, l: [number, number, number] | undefined) => {
        if (!el || !l) return
        const p = player!.place(l[0], l[1], box)
        el.style.transform = `translate3d(${p.x}px, ${p.y}px, 0)`
        el.style.opacity = String(l[2])
      }
      player.onFrame = (f, track) => {
        pinEls.current.forEach((el, i) => place(el, f.l[i]))
        areaEls.current.forEach((el, i) => place(el, f.l[pinEls.current.length + i]))
        markDay(f.tr, track.stops)
      }
      player.onReady = () => { if (!gone) setLive(true) }
      player.start().catch(() => { if (!gone) setMode('flat') })
    }
    if (mode === '3d') Promise.all([import('../landing/scene'), import('../landing/points.json'), fetchLandscape()]).then(([{ DalatScene }, { default: points }, land]) => {
      if (gone) return
      performance.mark('tg-scene-start')
      scene = DalatScene.create(cv, { points: points as [number, number][], five: SCENE_PLACES, focus: FOCUS, land }, still)
      performance.mark('tg-scene-built')
      if (!scene) { setFlat(true); return }
      scene.onReady = () => {
        performance.mark('tg-scene-first-frame')
        setLive(true)
        if (wantExplore.current) { wantExplore.current = false; window.setTimeout(() => exploreRef.current(), 50) }
      }
      scene.onGiveUp = () => { setFlat(true); setLive(false); scene?.setRunning(false); sceneRef.current = null }
      sceneRef.current = scene
      scene.bindLabels('five', pinEls.current)
      scene.bindLabels('area', areaEls.current, AREAS)
      if (still) Object.assign(state, { cam: 5, dots: 0.4, five: 1, route: 1, travel: 1, areas: 0, hour: 1, stamp: 1 })
      scene.resize(cv.clientWidth, cv.clientHeight)
      push()
      ro.observe(st)
      io.observe(st)
      document.addEventListener('visibilitychange', onVis)
      st.addEventListener('pointermove', onMove)
    }).catch(() => { if (!gone) setFlat(true) }) // no WebGL, or the file did not come: the poster stays

    const mm = gsap.matchMedia()
    let lenis: Lenis | undefined
    if (!still) {
      mm.add('all', () => {
        lenis = new Lenis({ lerp: 0.1 })
        lenisRef.current = lenis
        lenis.on('scroll', ScrollTrigger.update)
        const tick = (time: number) => lenis!.raf(time * 1000)
        gsap.ticker.add(tick)
        gsap.ticker.lagSmoothing(0)
        const chapters = gsap.utils.toArray<HTMLElement>('.tg-l3__ch', sec)
        const count = { value: stats.places }
        const writeCount = () => { if (counter.current) counter.current.textContent = num(Math.round(count.value)) }
        const enter = { autoAlpha: 1, y: 0, duration: 0.3, ease: 'power2.out' }
        const leave = { autoAlpha: 0, y: -36, duration: 0.25, ease: 'power1.in' }
        const timeline = gsap.timeline({
          defaults: { ease: 'none' },
          onUpdate: () => {
            const beat = Math.min(BEATS - 1, Math.round(timeline.time()))
            if (player) player.go(beat)
            else { push(); markDay() }
            setActive(beat)
          },
          scrollTrigger: { trigger: sec, start: 'top top', end: 'bottom bottom', scrub: 0.8 },
        })
        gsap.set(chapters.slice(1), { autoAlpha: 0, y: 36 })
        stateTweens(timeline, state)
        timeline.to(chapters[0], leave, 0)
          .to(chapters[1], enter, 0.6)
          .from(chapters[1].querySelectorAll('.tg-stamp'), { x: -60, autoAlpha: 0, stagger: 0.06, duration: 0.2 }, 0.62)
          .from(chapters[1].querySelectorAll('.tg-chip'), { x: 60, autoAlpha: 0, stagger: 0.05, duration: 0.2 }, 0.68)
          .to(chapters[1], leave, 1.2)
          .to(count, { value: ROUTE.length, duration: 0.65, onUpdate: writeCount }, 1.3)
          .to(chapters[2], enter, 1.6)
          .to(chapters[2], leave, 2.2)
          .to(chapters[3], enter, 2.6)
          .from(chapters[3].querySelectorAll('.tg-l3__why'), { y: 24, autoAlpha: 0, stagger: 0.08, duration: 0.2 }, 2.66)
          .to(chapters[3], leave, 3.2)
          .to(chapters[4], enter, 3.6)
          .from(chapters[4].querySelectorAll('.tg-l3__day li'), { x: 30, autoAlpha: 0, stagger: 0.04, duration: 0.16 }, 3.6)
          .to(chapters[4], leave, 4.2)
          .to(chapters[5], enter, 4.6)
          .from(chapters[5].querySelectorAll('.tg-l3__memo'), { y: 24, autoAlpha: 0, duration: 0.25 }, 4.66)
          .to({}, { duration: 0.01 }, STORY_LEN - 0.01)
        gsap.from('.tg-l4__tile', { y: 60, opacity: 0, stagger: 0.08, duration: 0.7, ease: 'power2.out', scrollTrigger: { trigger: '.tg-l4', start: 'top 72%' } })
        return () => { gsap.ticker.remove(tick); lenis?.destroy(); lenisRef.current = null }
      })
    }

    return () => {
      gone = true
      cv.removeEventListener('pointerdown', down)
      cv.removeEventListener('pointermove', drag)
      cv.removeEventListener('pointerup', drop)
      cv.removeEventListener('pointercancel', drop)
      cv.removeEventListener('wheel', wheel)
      cv.removeEventListener('contextmenu', menu)
      fitRo.disconnect()
      document.documentElement.style.overflow = ''
      sceneRef.current = null
      mm.revert()
      ro.disconnect()
      io.disconnect()
      document.removeEventListener('visibilitychange', onVis)
      st.removeEventListener('pointermove', onMove)
      scene?.dispose()
      unplay()
    }
  }, [still, mode])

  // "Lên lịch chuyến của bạn" opens the app as a guest when there is no session yet (no sign-in wall; if the guest
  // cannot start, /app shows the sign-in page); the questions start there, when the visitor says what the trip is.
  // The camera rises into the haze and the words fade, then three pieces fly to their place in the app (View
  // Transitions, docs/UI_SPEC_LANDING.md §3): the stage (or the closing box) into the home hero, the cloud into the
  // rail's logo, the pressed button into `Tạo chuyến đi`. `from` is that button.
  // `asGuest`: someone signed in who wants a guest session instead: always a new, empty one, their account is left alone.
  const begin = async (from: HTMLElement | null, asGuest = false) => {
    if (leaving || starting.current) return
    starting.current = true
    const utm = Object.fromEntries([...new URLSearchParams(location.search)].filter(([k]) => k.startsWith('utm_')))
    track('landing_cta', utm)
    if (!account || asGuest) {
      try { await startGuest() } catch { if (asGuest) { starting.current = false; return } }
    }
    starting.current = false
    const go = () => { navigate('/app'); window.scrollTo(0, 0) }
    if (still || !canTransition()) return go()
    // the pressed button and its containers stay while everything around them fades (css: .is-keep, .is-from)
    from?.classList.add('is-from')
    for (let el = from?.parentElement; el && !el.matches('.tg-l, .tg-l3__stage, .tg-cta'); el = el.parentElement) el.classList.add('is-keep')
    setLeaving(true)
    sceneRef.current?.set({ lift: 1 })
    window.setTimeout(() => handOff(from, go), 380)
  }
  const handOff = (from: HTMLElement | null, go: () => void) => {
    const seen = (el: HTMLElement | null) => { if (!el) return 0; const r = el.getBoundingClientRect(); return Math.max(0, Math.min(innerHeight, r.bottom) - Math.max(0, r.top)) }
    const st = stage.current, box = document.getElementById('tg-cta')
    const frame = from?.closest<HTMLElement>('.tg-cta') ? box : seen(st) >= seen(box) ? st : box
    if (frame && seen(frame) > 0) frame.style.viewTransitionName = 'tg-l2h-frame'
    if (from?.isConnected && seen(from) > 0) from.style.viewTransitionName = 'tg-l2h-cta'
    // the 3D cloud hands over to a picture of the logo standing exactly where it stands
    const sc = sceneRef.current, img = mascotImg.current, cv = canvas.current
    const at = frame !== st ? null : sc ? sc.mascotRect() : st && playerRef.current ? playerRef.current.mascot({ w: st.clientWidth, h: st.clientHeight }) : null
    if (at && img && cv && at.h > 8) {
      const box = cv.getBoundingClientRect(), size = at.h / 0.86
      Object.assign(img.style, { left: `${box.left + at.x - size / 2}px`, top: `${box.top + at.y - size / 2}px`, width: `${size}px`, height: `${size}px`, viewTransitionName: 'tg-l2h-mascot' })
      img.hidden = false
      sc?.hideMascot(true)
    }
    // one frame for the canvas to draw without its cloud, then the browser takes the picture of this page
    requestAnimationFrame(() => { if (!startTransition(() => flushSync(go), 'tg-l2h')) go() })
  }

  // Free exploration: the page stops scrolling, the first screen's text steps aside, the visitor drives the camera
  const lock = (on: boolean) => {
    exploringRef.current = on
    document.documentElement.style.overflow = on ? 'hidden' : ''
    if (on) lenisRef.current?.stop()
    else lenisRef.current?.start()
    setExploring(on)
  }
  const explore = () => {
    const sc = sceneRef.current
    if (!sc) {
      // the story plays as video: the live model loads only now, for free flight, and opens once it has drawn
      if (mode === 'video') { wantExplore.current = true; setLive(false); setMode('3d') }
      return
    }
    // the page is about to stop scrolling: bring the model and its exit button fully on screen first
    if (lenisRef.current) lenisRef.current.scrollTo(0, { immediate: true })
    else window.scrollTo(0, 0)
    sc.setExplore(true)
    lock(true)
  }
  exploreRef.current = explore
  const leaveExplore = () => {
    sceneRef.current?.setExplore(false)
    lock(false)
  }
  useEffect(() => {
    if (!exploring) return
    const onKey = (e: KeyboardEvent) => {
      const sc = sceneRef.current
      if (!sc || (e.target as HTMLElement).closest('input, textarea')) return
      const stepPx = 60
      const k = e.key.toLowerCase()
      if (k === 'escape') leaveExplore()
      else if (k === 'arrowleft' || k === 'a') sc.explorePan(stepPx, 0)
      else if (k === 'arrowright' || k === 'd') sc.explorePan(-stepPx, 0)
      else if (k === 'arrowup' || k === 'w') sc.explorePan(0, stepPx)
      else if (k === 'arrowdown' || k === 's') sc.explorePan(0, -stepPx)
      else if (k === '+' || k === '=') sc.zoomBy(0.8)
      else if (k === '-' || k === '_') sc.zoomBy(1.25)
      else if (k === 'q') sc.rotateBy(-Math.PI / 8)
      else if (k === 'e') sc.rotateBy(Math.PI / 8)
      else return
      e.preventDefault()
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [exploring]) // eslint-disable-line react-hooks/exhaustive-deps
  const toChapter = (index: number) => {
    const sec = story.current
    if (!sec) return
    const top = sec.offsetTop + (index / STORY_LEN) * (sec.offsetHeight - innerHeight) + (index ? 4 : 0)
    if (lenisRef.current) lenisRef.current.scrollTo(top, { duration: 1.2 })
    else window.scrollTo({ top, behavior: still ? 'auto' : 'smooth' })
  }
  const toId = (id: string) => {
    const el = document.getElementById(id)
    if (!el) return
    if (exploringRef.current) leaveExplore() // the page is locked while exploring: leave first, then scroll
    if (lenisRef.current) lenisRef.current.scrollTo(el, { duration: 1.2, offset: -24 })
    else el.scrollIntoView({ behavior: still ? 'auto' : 'smooth' })
  }

  const cta = <>Lên lịch chuyến của bạn <Icon name="arrow" size={20} /></>

  return (
    <div className={`tg-l ${still ? 'is-still' : ''} ${leaving ? 'is-leaving' : ''}`}>
      <nav className="tg-ln" aria-label="Trang giới thiệu">
        <a href="/app" className="tg-ln__logo" aria-label="Vào TripGuardian" onClick={(e) => { e.preventDefault(); navigate('/app') }}><Logo size={30} /></a>
        <div className="tg-ln__links">
          <button type="button" onClick={() => toChapter(1)}>Cách hoạt động</button>
          <button type="button" onClick={() => toId('tg-photos')}>Địa điểm</button>
          <button type="button" onClick={() => toId('tg-faq')}>Hỏi nhanh</button>
        </div>
        <a href="/app/login" className="tg-ln__login" onClick={(e) => { e.preventDefault(); navigate('/app/login') }}>Đăng nhập</a>
        {member && <button type="button" className="tg-ln__login" onClick={(e) => void begin(e.currentTarget, true)} title="Phiên mới, không đụng tới tài khoản của bạn">Dùng thử khách</button>}
        <button type="button" className="tg-btn tg-btn--primary tg-btn--sm" onClick={(e) => void begin(e.currentTarget)}>Lên lịch chuyến của bạn</button>
      </nav>

      <section className="tg-l3" ref={story} aria-label="Cách TripGuardian lên một chuyến Đà Lạt">
        <div className={`tg-l3__stage ${flat ? 'is-flat' : ''} ${mode === 'video' ? 'is-video' : ''} ${live ? 'is-live' : ''} ${exploring ? 'is-exploring' : ''}`} ref={stage}>
          <div className="tg-l3__poster" aria-hidden="true" />
          {flat && <div className="tg-l3__plates" aria-hidden="true">{PLATES.map((src, i) => <img key={src} src={src} alt="" decoding="async" loading={i ? 'lazy' : 'eager'} className={i === Math.min(active, PLATES.length - 1) ? 'is-on' : ''} />)}</div>}
          <div ref={clipHost} className="tg-l3__clips" aria-hidden="true" />
          <canvas ref={canvas} className="tg-l3__cv" role="img" aria-label={`Bản đồ hành trình Đà Lạt theo dữ liệu thật, kéo để xoay: ${num(stats.places)} địa điểm trong dữ liệu`} />
          <div className="tg-l3__veil" aria-hidden="true" />
          <div className="tg-l3__labels" aria-hidden="true">
            {AREAS.map((a, i) => <span key={a.name} className="tg-l3__area" ref={(el) => { if (el) areaEls.current[i] = el }}><span>{a.name}</span></span>)}
            {ROUTE.map((p, i) => <span key={p.id} className="tg-l3__pin" ref={(el) => { if (el) pinEls.current[i] = el }}><span><b>{i + 1}</b>{p.name}</span></span>)}
          </div>

          <div className="tg-l3__chs">
            <div className="tg-l3__ch tg-l3__hero">
              <div className="tg-l3__in">
              <p className="tg-kicker">TripGuardian · Đà Lạt</p>
              <h1>Lịch trình Đà Lạt <em>vừa với bạn.</em></h1>
              <p className="tg-l3__sub">Kể chuyến đi trong vài phút. TripGuardian lọc trong <b>{num(stats.places)}</b> chỗ ở Đà Lạt, giữ lại chỗ hợp gu và xếp lịch từng giờ cho bạn.</p>
              <div className="tg-l3__start">
                <button type="button" className="tg-btn tg-btn--primary tg-l3__cta" onClick={(e) => void begin(e.currentTarget)}>{cta}</button>
                <button type="button" className="tg-l3__how" onClick={() => toChapter(1)}>Xem cách hoạt động <Icon name="chevronDown" size={18} /></button>
              </div>
              <ul className="tg-l3__ticks">
                <li><Icon name="check" size={14} />Miễn phí</li>
                <li><Icon name="check" size={14} />Không cần tài khoản</li>
                <li><Icon name="check" size={14} />Chỗ nào cũng có thật</li>
              </ul>
              </div>
            </div>

            {/* 1 · the visitor talks, TripGuardian writes down what it heard */}
            <article className="tg-l3__ch" aria-labelledby="tg-ch1">
              <p className="tg-kicker">Tìm hiểu</p>
              <h2 id="tg-ch1">Cứ kể như kể với bạn đi cùng.</h2>
              <p className="tg-muted">Không có form phải điền. Bạn nói, TripGuardian ghi lại điều nào phải giữ, điều nào có thì vui.</p>
              <Shot name="understand" label="màn Tìm hiểu"><div className="tg-l3__talk">
                <p className="tg-l3__say"><small>Bạn</small>Tụi mình đi 2 người, 3 ngày, chạy xe máy. Đừng dẫn <mark>chỗ đông quá</mark>, cũng <mark>đừng bắt chạy xa</mark>. Thích <mark>ngồi cà phê chill</mark>, có buổi <mark>săn mây</mark> thì càng tốt.</p>
                <div className="tg-l3__memo">
                  <p className="tg-l3__memo-h"><img src="/img/gen/bot-avatar.webp" alt="" width="28" height="28" />TripGuardian ghi lại<span>2 người · 3 ngày · xe máy</span></p>
                  <div className="tg-l3__memo-row"><h4>Phải giữ</h4><div><span className="tg-stamp"><Icon name="lock" size={14} />Tránh chỗ quá đông</span><span className="tg-stamp"><Icon name="lock" size={14} />Mỗi lần chạy xe dưới 45 phút</span></div></div>
                  <div className="tg-l3__memo-row"><h4>Có thì vui</h4><div>{['cà phê chill', 'săn mây'].map((chip) => <span key={chip} className="tg-chip tg-chip--dash">{chip}</span>)}</div></div>
                </div>
              </div></Shot>
            </article>

            <article className="tg-l3__ch" aria-labelledby="tg-ch2">
              <p className="tg-kicker">Lựa chọn</p>
              <h2 id="tg-ch2" aria-label={`Bạn chọn ra ${ROUTE.length} chỗ trong ${num(stats.places)} địa điểm`}><span aria-hidden="true">Chọn ra <span ref={counter} className="tg-l3__count">{still ? ROUTE.length : num(stats.places)}</span> chỗ, không phải lục cả nghìn.</span></h2>
              <p className="tg-muted">TripGuardian xếp chỗ hợp với điều bạn vừa kể lên đầu, kèm lý do. Bạn chỉ việc bấm Thêm những chỗ muốn đi.</p>
              <ul className="tg-l3__legend">
                <li><i className="is-all" />Mỗi chấm là một chỗ ở Đà Lạt</li>
                <li><i className="is-five" />Tấm ảnh là chỗ được giữ, đường chấm là thứ tự đi</li>
              </ul>
            </article>

            {/* 2 · one place, recommended the way a friend would: why it fits you, what to know before going */}
            <article className="tg-l3__ch" aria-labelledby="tg-ch3">
              <p className="tg-kicker">Lựa chọn · vì sao</p>
              <h2 id="tg-ch3">Chỗ nào cũng có lý do.</h2>
              <p className="tg-muted">Không phải danh sách “top 10”. Mỗi chỗ đi kèm lý do hợp với bạn và điều nên biết trước khi tới.</p>
              <Shot name="choose" label="thẻ một chỗ ở bước Lựa chọn"><div className="tg-l3__rec">
                <div className="tg-l3__rec-h">
                  {spot.photos[0] && <img src={thumbOf(spot.photos[0].src) ?? spot.photos[0].src} alt="" width="56" height="56" />}
                  <span><b>{spot.name}</b><small>{spot.rating && spot.reviews ? `${spot.rating.toLocaleString('vi-VN')}★ · ${num(spot.reviews)} đánh giá Google` : 'Quán cà phê'}</small></span>
                </div>
                <p className="tg-l3__why"><Icon name="heart" size={16} /><span><b>Hợp bạn vì</b>Bạn muốn ngồi cà phê chill, quán này có view đồi thông.</span></p>
                {peak && <p className="tg-l3__why is-know"><Icon name="clock" size={16} /><span><b>Nên biết</b>{LATE.includes(peak[0]) ? `Cuối tuần quán đông nhất vào ${DAYPART[peak[0]] ?? peak[0]}, nên lịch cho bạn tới lúc ${DAY[FOCUS].at}, trước khi đông.` : `Cuối tuần quán đông nhất vào ${DAYPART[peak[0]] ?? peak[0]}; lịch tránh khung giờ đó.`}</span></p>}
                {!!spot.videos?.length && <div className="tg-l3__clips"><span>Người ta quay ở đây</span>{spot.videos.slice(0, 2).map((video) => <a key={video.url} className="tg-l3__clip" href={video.url} target="_blank" rel="noreferrer"><Icon name="play" size={12} />@{video.handle}</a>)}</div>}
              </div></Shot>
            </article>

            <article className="tg-l3__ch" aria-labelledby="tg-ch4">
              <p className="tg-kicker">Lịch trình <span className="tg-tag tg-tag--warn">Ví dụ</span></p>
              <h2 id="tg-ch4">Cả ngày xếp sẵn, bạn chỉ việc đi.</h2>
              <p className="tg-muted">Săn mây lúc trời vừa sáng, ngắm hoàng hôn cuối ngày. Không lần nào phải chạy xe quá 45 phút.</p>
              <Shot name="plan" label="lịch một ngày"><ol className="tg-l3__day">
                {DAY.map((item, i) => <li key={item.name} ref={(el) => { if (el) dayEls.current[i] = el }}><time>{item.at}</time><span><b>{item.name}</b>{item.meal && <em>{item.meal}</em>}</span>{i > 0 && <small title="Thời gian chạy xe từ chỗ trước">{legMinutes(ROUTE[i - 1], ROUTE[i])} phút xe</small>}</li>)}
              </ol>
              <p className="tg-l3__ok"><Icon name="check" size={14} />Đã kiểm tra: đường đi vừa sức, không ghé chỗ nào lúc đông nhất.</p></Shot>
            </article>

            {/* 3 · after the trip: a few words back, and what TripGuardian keeps for next time */}
            <article className="tg-l3__ch" aria-labelledby="tg-ch5">
              <p className="tg-kicker">Đánh giá</p>
              <h2 id="tg-ch5">Đi về, kể lại vài câu.</h2>
              <p className="tg-muted">Chỗ nào thích, chỗ nào không. TripGuardian nhớ để chuyến sau hợp gu bạn hơn.</p>
              <Shot name="feedback" label="màn Đánh giá"><div className="tg-l3__talk">
                <p className="tg-l3__say"><small>Bạn</small>Săn mây đáng dậy sớm lắm. Hồ Tuyền Lâm hơi đông, lần sau bỏ cũng được.</p>
                <div className="tg-l3__memo">
                  <p className="tg-l3__memo-h"><img src="/img/gen/bot-avatar.webp" alt="" width="28" height="28" />Đã nhớ cho chuyến sau</p>
                  <ul className="tg-l3__keep">
                    <li><Icon name="heart" size={14} />Thích cảnh lúc bình minh</li>
                    <li><Icon name="minus" size={14} />Bớt chỗ đông khách</li>
                  </ul>
                </div>
              </div></Shot>
              <button type="button" className="tg-btn tg-btn--primary tg-l3__go" onClick={(e) => void begin(e.currentTarget)}>{cta}</button>
            </article>
          </div>

          {active === 0 && (!flat || window.__tgGL !== 'none') && (
            <div className="tg-l3__note">
              {!flat
                ? <button type="button" className="tg-l3__roam" disabled={!live && mode === '3d'} onClick={explore}><Icon name="compass" size={36} /><span><b>Khám phá bản đồ Đà Lạt</b><small>{hasGpu() ? 'Kéo chuột để xoay, cuộn để phóng to' : 'Máy của bạn không có card đồ họa, bản đồ động có thể chậm'}</small></span></button>
                : <button type="button" className="tg-l3__roam" onClick={() => { location.search = '?3d=on' }}><Icon name="compass" size={36} /><span><b>Khám phá bản đồ Đà Lạt</b><small>Máy của bạn không có card đồ họa, bản đồ động có thể chậm</small></span></button>}
            </div>
          )}

          {exploring && (
            <div className="tg-l3__ex" role="group" aria-label="Khám phá bản đồ Đà Lạt">
              <div className="tg-l3__ex-top">
                <div className="tg-l3__ex-title"><p className="tg-kicker">Khám phá tự do</p><p>Kéo để xoay · Cuộn để phóng to · Chuột phải để dịch chuyển</p></div>
                <button type="button" className="tg-btn tg-btn--ghost tg-l3__ex-exit" onClick={leaveExplore} autoFocus>Thoát<Icon name="x" size={18} /></button>
              </div>
              <div className="tg-l3__ex-chips" role="group" aria-label="Bay tới">
                {FLY.map((f) => <button key={f.name} type="button" className="tg-chip" onClick={() => sceneRef.current?.flyTo(f.lat, f.lng, f.dist)}><Icon name="pin" size={14} />{f.name}</button>)}
              </div>
              <div className="tg-l3__ex-ctl" role="group" aria-label="Điều khiển camera">
                <button type="button" aria-label="Phóng to" title="Phóng to (+)" onClick={() => sceneRef.current?.zoomBy(0.75)}><Icon name="plus" size={18} /></button>
                <button type="button" aria-label="Thu nhỏ" title="Thu nhỏ (−)" onClick={() => sceneRef.current?.zoomBy(1.33)}><Icon name="minus" size={18} /></button>
                <button type="button" aria-label="Xoay sang trái" title="Xoay trái (Q)" onClick={() => sceneRef.current?.rotateBy(-Math.PI / 6)}><Icon name="chevronLeft" size={18} /></button>
                <button type="button" aria-label="Xoay sang phải" title="Xoay phải (E)" onClick={() => sceneRef.current?.rotateBy(Math.PI / 6)}><Icon name="chevronRight" size={18} /></button>
                <button type="button" aria-label="Về trung tâm" title="Về trung tâm" onClick={() => sceneRef.current?.flyTo(11.9445, 108.4462, 110)}><Icon name="refresh" size={18} /></button>
              </div>
            </div>
          )}
          {!still && active > 0 && <nav className="tg-l3__rail" aria-label="Các chương">{RAIL.map(([label, beat]) => <button key={label} type="button" aria-current={stepOf(active) === beat ? 'step' : undefined} onClick={() => toChapter(beat)}><span>{label}</span><i /></button>)}</nav>}
          {!still && <button type="button" className="tg-l3__down" key={active} onClick={() => (active < BEATS - 1 ? toChapter(active + 1) : toId('tg-photos'))}><Icon name="chevronDown" size={18} />{HINTS[Math.min(active, BEATS - 1)]}</button>}
        </div>
      </section>

      <section className="tg-l4" id="tg-photos" aria-labelledby="tg-l4-h">
        <div className="tg-l__head tg-rv"><h2 id="tg-l4-h">Ảnh thật của chỗ thật</h2><p className="tg-muted">{num(stats.withPhotos)} chỗ có ảnh chụp từ Google Maps, ghi nguồn ngay dưới ảnh. Không có ảnh minh họa nào đứng tên một chỗ có thật.</p></div>
        <div className="tg-l4__grid">{showcase.map(({ place, photo }, i) => <figure key={place.id} className={`tg-l4__tile t${i} tg-rv`} data-delay={i * 0.08}><Photo photo={photo} alt={place.name} sizes={i ? '(max-width: 900px) 50vw, 440px' : '(max-width: 900px) 100vw, 900px'} /><figcaption><b>{place.name}</b><span>Ảnh: {photo.credit}</span></figcaption></figure>)}</div>
      </section>

      <section className="tg-l5" id="tg-faq" aria-labelledby="tg-faq-h">
        <div className="tg-l5__l tg-rv">
          <h2 id="tg-faq-h">Hỏi nhanh</h2>
          <p className="tg-l5__soon">Sắp có <span>Ứng dụng điện thoại</span><span>Thêm thành phố</span></p>
        </div>
        <div className="tg-faq tg-rv" data-delay="0.1">{FAQ.map(([q, a], i) => <div key={q} className="tg-faq__i"><button type="button" aria-expanded={faq === i} onClick={() => setFaq(faq === i ? -1 : i)}>{q}<Icon name={faq === i ? 'minus' : 'plus'} size={18} /></button>{faq === i && <p className="tg-muted">{a}</p>}</div>)}</div>
      </section>

      <section className="tg-cta tg-rv" id="tg-cta" aria-labelledby="tg-cta-h">
        <div className="tg-cta__img" aria-hidden="true" />
        <div className="tg-cta__in"><h2 id="tg-cta-h">Bắt đầu chuyến Đà Lạt của bạn.</h2><button type="button" className="tg-btn tg-btn--primary tg-cta__btn" onClick={(e) => void begin(e.currentTarget)}>{cta}</button><p>Miễn phí · Không cần tài khoản · Đăng nhập để lưu chuyến</p>{member && <button type="button" className="tg-link tg-cta__guest" onClick={(e) => void begin(e.currentTarget, true)}>Hoặc dùng thử với tư cách khách (phiên mới, tài khoản của bạn giữ nguyên)</button>}</div>
      </section>

      <img ref={mascotImg} className="tg-l__mascot" src="/img/brand/mark.webp" alt="" aria-hidden="true" hidden />
      <footer className="tg-lf"><Logo size={26} dark /><span className="tg-lf__sp" /><span>Giờ giấc và quãng đường là ước tính; bản đồ vẽ từ dữ liệu thật (độ cao SRTM, OpenStreetMap). Số liệu theo bản dữ liệu {stats.asOf?.split('-').reverse().join('/')}: {num(stats.places)} nơi, {num(stats.withPhotos)} nơi có ảnh thật.</span></footer>
    </div>
  )
}
