import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import Lenis from 'lenis'
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { startGuest, useAccount } from '../account'
import { track } from '../events'
import { flushSync } from 'react-dom'
import { navigate } from '../../router'
import { canTransition, startTransition } from '../../viewTransition'
import { prefetchSnapshot } from '../../data/store'
import { featureLabel, isNegative } from '../../data/labels'
import { fetchLandscape } from '../landing/bin'
import { hasGpu } from '../landing/device'
import { AREAS, DAY, FOCUS, ROAD_FACTOR, ROUTE, SCENE_PLACES, SPEED_KMH, byName, type LPlace } from '../landing/route'
import stats from '../landing/stats.json'
import type { DalatScene, ScenePlace, SceneState } from '../landing/scene'
import { priceText, reducedMotion } from '../lib'
import { Photo, thumbOf } from '../ui/common'
import { Icon, Logo, type IconName } from '../ui/icons'
import { FAQ } from '../faq'
import { useTitle } from '../ui/Shell'

// Desktop landing: one sticky stage with a 3D model of Đà Lạt; scrolling moves the camera through six chapters.
// Each chapter carries a small copy of the real screen it talks about (docs/UI_SPEC_LANDING.md §2), filled with real
// places from the snapshot (web/scripts/pick_landing_places.py).
gsap.registerPlugin(ScrollTrigger)
// Beat i is fully in at timeline time i; the rail groups the evidence beat with selection.
const RAIL: [string, number][] = [['Mở đầu', 0], ['Tìm hiểu', 1], ['Lựa chọn', 2], ['Lịch trình', 4], ['Đánh giá', 5]]
const BEATS = 6
const STORY_LEN = 5.5
const stepOf = (beat: number) => (beat === 3 ? 2 : beat)
const HINTS = ['Cuộn xuống để xem cách hoạt động', 'Cuộn tiếp: Lựa chọn', 'Cuộn tiếp: vì sao chọn chỗ đó', 'Cuộn tiếp: Lịch trình', 'Cuộn tiếp: Chốt lịch', 'Còn nữa bên dưới: ảnh thật của từng chỗ']
// The light version uses one frame from the real 3D model for each chapter.
const PLATES = ['/img/landing-poster.webp', '/img/landing-p1.webp', '/img/landing-p2.webp', '/img/landing-p3.webp', '/img/landing-p4.webp', '/img/landing-p5.webp'].map((src) => `${src}?v=home1`) // ?v: the CDN keeps images a day
// the four photos of the "Địa điểm thật" section: place, and which of its photos shows the place best (daylight, recognisable)
const SHOWCASE: [string, number][] = [['Thung lũng Tình Yêu', 3], ['Hồ Xuân Hương', 1], ['Dinh III', 3], ['Thác Datanla', 0]]
const DAYPART: Record<string, string> = { early_morning: 'sáng sớm', morning: 'buổi sáng', noon: 'buổi trưa', afternoon: 'buổi chiều', evening: 'buổi tối', night: 'ban đêm' }

// Tìm hiểu: what the visitor says, the photo question the chat asks back (three real cafés, each labelled with a taste
// people really mention there, worded as the app's taste bank words it), and the trip's seven required answers.
const SAY = 'Tụi mình đi 2 người, từ thứ Sáu tới Chủ Nhật, chạy xe máy. Thích ngồi cà phê chill, có buổi săn mây thì càng tốt.'
// `photo`: which of the place's photos shows that taste best
const ASK: { label: string; place: string; photo: number }[] = [
  { label: 'Không gian rộng, thoáng', place: 'Tiệm cà phê Thênh Thang', photo: 0 }, // spacious: 22 người nhắc
  { label: 'Yên tĩnh', place: 'Quán Của Thời Thanh Xuân', photo: 3 }, // noise quiet: 32
  { label: 'Ngồi ngoài trời', place: 'Nhà Bên Rừng', photo: 3 }, // outdoor_seating: 4
]
const BOARD: [IconName, string, string | null][] = [
  ['calendar', 'Ngày đi', 'T6 → CN · 3 ngày'], ['users', 'Đi với', '2 người'], ['route', 'Phương tiện', 'Xe máy'],
  ['heart', 'Lưu ý', null], ['sliders', 'Nhịp độ', null], ['wallet', 'Ngân sách', null], ['bed', 'Nơi lưu trú', null],
]
const KNOWN = BOARD.filter((b) => b[2]).length
// Lựa chọn · vì sao: the lines the place card shows, each one something people said (and how many), tied to the visitor's words
const WHY: [string, string][] = [['spacious', 'Không gian rộng, thoáng'], ['scenic_view', 'View đẹp'], ['long_stay_chill', 'Ngồi lâu, chill']]
const TRADE = ['rough_road_access', 'crowd', 'parking', 'steep_or_stairs'] // the first downside people report becomes the card's Đánh đổi
// Lịch trình: the three fixed ways to drop places when the picks do not fit the days (docs/PLANNING.md)
const PLANS = ['Giữ nơi hợp gu nhất', 'Ít đi lại', 'Tiết kiệm']
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
const hm = (minutes: number) => `${Math.floor(minutes / 60)} giờ${minutes % 60 ? ` ${minutes % 60}` : ''}`
const stayMinutes = (stay: string) => { const [h, m] = stay.split(' giờ'); return Number(h) * 60 + (Number(m) || 0) }
const signal = (p: LPlace, id: string) => p.signals?.find((s) => s.id === id)
// the example day as the Lựa chọn bar sums it up: places, time at them, time on the road between them
const VISIT = DAY.reduce((sum, d) => sum + stayMinutes(d.stay), 0)
const ROAD = ROUTE.slice(1).reduce((sum, p, i) => sum + legMinutes(ROUTE[i], p), 0)

// Real screens of the app for the chapters (docs/UI_SPEC_LANDING.md §2): `app-<name>.webp` in web/src/user/landing/shots/,
// found at build time; a chapter without its screen keeps the drawn copy below it.
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
  const lenisRef = useRef<Lenis | null>(null)
  const [still] = useState(reducedMotion)
  const [flat, setFlat] = useState(() => !hasGpu()) // no GPU (or too slow): chapter pictures instead of the live model
  const [live, setLive] = useState(false) // the 3D model has drawn its first frame: the poster fades out
  const [active, setActive] = useState(0)
  const sceneRef = useRef<DalatScene | null>(null)
  const [exploring, setExploring] = useState(false) // free exploration of the 3D model
  const [leaving, setLeaving] = useState(false) // on its way to the home page
  const exploringRef = useRef(false)
  const [faq, setFaq] = useState(0)
  const account = useAccount()
  const starting = useRef(false)
  const member = !!account && !account.guest
  const spot = ROUTE[FOCUS]
  const peak = spot.crowd?.weekend ? Object.entries(spot.crowd.weekend).reduce((a, b) => (b[1] > a[1] ? b : a)) : null
  const why = WHY.flatMap(([id, label]) => { const s = signal(spot, id); return s ? [{ label, n: s.n }] : [] })
  const trade = TRADE.map((id) => signal(spot, id)).find((s) => s && isNegative(s.id, s.value))
  const price = priceText(spot.price)
  const asks = ASK.flatMap((a) => { const place = byName(a.place), photo = place?.photos[a.photo] ?? place?.photos[0]; return photo ? [{ ...a, src: thumbOf(photo.src) ?? photo.src }] : [] })
  const showcase = SHOWCASE.map(([n, i]) => ({ place: byName(n), photo: byName(n).photos[i] }))

  // The next screens need the place data: fetch it while the visitor reads, but only once the model has drawn (or
  // cannot), so the 2.8 MB of covers never compete with the landscape for the connection.
  useEffect(() => {
    if (live || flat) prefetchSnapshot()
  }, [live, flat])

  // 3D model + scroll story
  useEffect(() => {
    const cv = canvas.current, st = stage.current, sec = story.current
    if (!cv || !st || !sec) return
    let scene: DalatScene | null = null
    let gone = false
    const state: SceneState = { cam: 0, dots: 1, five: 0, route: 0, travel: 0, areas: 1, shift: shiftFor(innerWidth) }
    const push = () => scene?.set(state)

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
    if (!flat) Promise.all([import('../landing/scene'), import('../landing/points.json'), fetchLandscape()]).then(([{ DalatScene }, { default: points }, land]) => {
      if (gone) return
      performance.mark('tg-scene-start')
      scene = DalatScene.create(cv, { points: points as [number, number][], five: SCENE_PLACES, focus: FOCUS, land }, still)
      performance.mark('tg-scene-built')
      if (!scene) { setFlat(true); return }
      scene.onReady = () => { performance.mark('tg-scene-first-frame'); setLive(true) }
      scene.onGiveUp = () => { setFlat(true); setLive(false); scene?.setRunning(false); sceneRef.current = null }
      sceneRef.current = scene
      scene.bindLabels('five', pinEls.current)
      scene.bindLabels('area', areaEls.current, AREAS)
      if (still) Object.assign(state, { cam: 5, dots: 0.4, five: 1, route: 1, areas: 0 })
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
          onUpdate: () => { push(); setActive(Math.min(BEATS - 1, Math.round(timeline.time()))) },
          scrollTrigger: { trigger: sec, start: 'top top', end: 'bottom bottom', scrub: 0.8 },
        })
        gsap.set(chapters.slice(1), { autoAlpha: 0, y: 36 })
        timeline.to(state, { cam: 1, duration: 1 }, 0)
          .to(chapters[0], leave, 0)
          .to(state, { areas: 0, duration: 0.4 }, 0.1)
          .to(chapters[1], enter, 0.6)
          .from(chapters[1].querySelectorAll('.tg-lk__opts li'), { y: 24, autoAlpha: 0, stagger: 0.05, duration: 0.18 }, 0.64)
          .from(chapters[1].querySelectorAll('.tg-lk__board li.is-done'), { x: -16, autoAlpha: 0, stagger: 0.05, duration: 0.16 }, 0.74)
          .from(chapters[1].querySelectorAll('.tg-l3__shot'), { y: 30, autoAlpha: 0, duration: 0.25 }, 0.66)
          .to(chapters[1], leave, 1.2)
          .to(state, { cam: 2, duration: 1 }, 1.1)
          .to(state, { dots: 0, duration: 0.6 }, 1.3)
          .to(count, { value: ROUTE.length, duration: 0.65, onUpdate: writeCount }, 1.3)
          .to(state, { five: 1, duration: 0.5 }, 1.45)
          .to(chapters[2], enter, 1.6)
          .from(chapters[2].querySelector('.tg-lk--bar'), { y: 30, autoAlpha: 0, duration: 0.25 }, 1.75)
          .to(state, { route: 1, duration: 0.4 }, 1.55)
          .to(chapters[2], leave, 2.2)
          .to(state, { cam: 3, duration: 1 }, 2.1)
          .to(chapters[3], enter, 2.6)
          .from(chapters[3].querySelectorAll('.tg-lk__why li, .tg-lk__trade'), { x: 24, autoAlpha: 0, stagger: 0.05, duration: 0.18 }, 2.64)
          .from(chapters[3].querySelectorAll('.tg-l3__shot'), { y: 30, autoAlpha: 0, duration: 0.25 }, 2.64)
          .to(chapters[3], leave, 3.2)
          .to(state, { cam: 4, duration: 1 }, 3.1)
          .to(chapters[4], enter, 3.6)
          .from(chapters[4].querySelectorAll('.tg-lk__plans span'), { y: 12, autoAlpha: 0, stagger: 0.04, duration: 0.14 }, 3.6)
          .from(chapters[4].querySelectorAll('.tg-l3__day li'), { x: 30, autoAlpha: 0, stagger: 0.04, duration: 0.16 }, 3.62)
          .to(state, { travel: 1, duration: 0.8 }, 3.7)
          .from(chapters[4].querySelectorAll('.tg-l3__shot'), { y: 30, autoAlpha: 0, duration: 0.25 }, 3.62)
          .to(chapters[4], leave, 4.2)
          .to(state, { cam: 5, duration: 1 }, 4.1)
          .to(chapters[5], enter, 4.6)
          .from(chapters[5].querySelectorAll('.tg-lk__seal'), { scale: 0.4, autoAlpha: 0, duration: 0.22, ease: 'back.out(2)' }, 4.62)
          .from(chapters[5].querySelectorAll('.tg-lk__scale i'), { y: 10, autoAlpha: 0, stagger: 0.04, duration: 0.14 }, 4.7)
          .from(chapters[5].querySelectorAll('.tg-l3__shot'), { y: 30, autoAlpha: 0, duration: 0.25 }, 4.62)
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
    }
  }, [still])

  // "Lên lịch chuyến của bạn" opens the app as a guest when there is no session yet (no sign-in wall; if the guest
  // cannot start, /app shows the sign-in page); the questions start there, when the visitor says what the trip is.
  // `asGuest`: a signed-in visitor asked for a fresh guest session instead of their account.
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
    window.setTimeout(() => handOff(from, go), 380)
  }
  // The valley (or the closing box) grows into the home hero and the pressed button flies to Tạo chuyến đi (motion.css, html.tg-l2h)
  const handOff = (from: HTMLElement | null, go: () => void) => {
    const seen = (el: HTMLElement | null) => { if (!el) return 0; const r = el.getBoundingClientRect(); return Math.max(0, Math.min(innerHeight, r.bottom) - Math.max(0, r.top)) }
    const st = stage.current, box = document.getElementById('tg-cta')
    const frame = from?.closest<HTMLElement>('.tg-cta') ? box : seen(st) >= seen(box) ? st : box
    if (frame && seen(frame) > 0) frame.style.viewTransitionName = 'tg-l2h-frame'
    if (from?.isConnected && seen(from) > 0) from.style.viewTransitionName = 'tg-l2h-cta'
    if (!startTransition(() => flushSync(go), 'tg-l2h')) go()
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
    if (!sc) return
    // the page is about to stop scrolling: bring the model and its exit button fully on screen first
    if (lenisRef.current) lenisRef.current.scrollTo(0, { immediate: true })
    else window.scrollTo(0, 0)
    sc.setExplore(true)
    lock(true)
  }
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
        <div className={`tg-l3__stage ${flat ? 'is-flat' : ''} ${live ? 'is-live' : ''} ${exploring ? 'is-exploring' : ''}`} ref={stage}>
          <div className="tg-l3__poster" aria-hidden="true" />
          {flat && <div className="tg-l3__plates" aria-hidden="true">{PLATES.map((src, i) => <img key={src} src={src} alt="" decoding="async" loading={i ? 'lazy' : 'eager'} className={i === Math.min(active, PLATES.length - 1) ? 'is-on' : ''} />)}</div>}
          <canvas ref={canvas} className="tg-l3__cv" role="img" aria-label={`Mô hình 3D Đà Lạt theo địa hình thật, kéo để xoay 360 độ: ${num(stats.places)} địa điểm trong dữ liệu`} />
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
              <p className="tg-l3__sub">Kể chuyến đi trong vài phút. TripGuardian lọc trong <b>{num(stats.places)}</b> chỗ có thật ở Đà Lạt, giữ lại chỗ hợp gu và xếp lịch từng giờ.</p>
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

            {/* 1 · Tìm hiểu: the chat. The visitor talks, TripGuardian asks back with photos and fills the seven answers */}
            <article className="tg-l3__ch" aria-labelledby="tg-ch1">
              <p className="tg-kicker">Tìm hiểu</p>
              <h2 id="tg-ch1">Cứ kể như kể với bạn đi cùng.</h2>
              <p className="tg-muted">Không có form phải điền. Chỗ nào chưa rõ, TripGuardian hỏi lại bằng ảnh thật để bạn chỉ cần bấm.</p>
              <Shot name="understand" label="câu hỏi bằng ảnh ở bước Tìm hiểu"><div className="tg-lk tg-lk--chat">
                <p className="tg-lk__me">{SAY}</p>
                <div className="tg-lk__bot">
                  <img className="tg-lk__avatar" src="/img/gen/bot-avatar.webp" alt="" width="30" height="30" />
                  <div className="tg-lk__ask">
                    <p className="tg-lk__q">Bạn thích không gian quán nào hơn?<small>Vì bạn nói “cà phê chill”</small></p>
                    <ul className="tg-lk__opts">{asks.map((a, i) => <li key={a.label} className={i === 0 ? 'is-on' : ''}><img src={a.src} alt="" loading="lazy" decoding="async" /><span>{a.label}</span>{i === 0 && <i aria-label="Bạn chọn"><Icon name="check" size={12} strokeWidth={3} /></i>}</li>)}</ul>
                  </div>
                </div>
                <div className="tg-lk__board" aria-label={`Thông tin chuyến: đã ghi ${KNOWN} trên ${BOARD.length}`}>
                  <span className="tg-lk__ring" style={{ '--p': KNOWN / BOARD.length } as CSSProperties}><b>{KNOWN}/{BOARD.length}</b><small>thông tin</small></span>
                  <ul>{BOARD.map(([icon, label, value]) => <li key={label} className={value ? 'is-done' : ''} title={value ?? 'TripGuardian sẽ hỏi trong chat'}><Icon name={icon} size={14} /><span>{label}</span>{value && <b>{value}</b>}</li>)}</ul>
                </div>
              </div></Shot>
            </article>

            {/* 2 · Lựa chọn: the suggestions are already filtered by what was said; the bar sums up what the visitor picked */}
            <article className="tg-l3__ch" aria-labelledby="tg-ch2">
              <p className="tg-kicker">Lựa chọn</p>
              <h2 id="tg-ch2" aria-label={`Bạn chọn ra ${ROUTE.length} chỗ trong ${num(stats.places)} địa điểm`}><span aria-hidden="true">Chọn ra <span ref={counter} className="tg-l3__count">{still ? ROUTE.length : num(stats.places)}</span> chỗ, không phải lục cả nghìn.</span></h2>
              <p className="tg-muted">Gợi ý xếp theo điều bạn vừa kể. Bạn bấm Thêm chỗ muốn đi, thanh dưới cho biết cả ngày còn đi kịp không.</p>
              <ul className="tg-l3__legend">
                <li><i className="is-all" />Mỗi chấm là một chỗ ở Đà Lạt</li>
                <li><i className="is-five" />Chỗ bạn chọn, nối theo thứ tự đi</li>
              </ul>
              <div className="tg-lk tg-lk--bar" role="img" aria-label={`Đi kịp: ${ROUTE.length} nơi, ${hm(VISIT)} tham quan, khoảng ${hm(ROAD)} đi lại`}>
                <span className="tg-lk__fit"><i />Đi kịp</span>
                <span><b>{ROUTE.length}</b> nơi</span>
                <span><b>{hm(VISIT)}</b> tham quan</span>
                <span>≈ <b>{hm(ROAD)}</b> đi lại</span>
                <span className="tg-lk__go">Lập lịch <Icon name="arrow" size={15} /></span>
              </div>
            </article>

            {/* 3 · Lựa chọn · vì sao: one suggestion as the app's place card shows it, every line counted from what people said */}
            <article className="tg-l3__ch" aria-labelledby="tg-ch3">
              <p className="tg-kicker">Lựa chọn · vì sao</p>
              <h2 id="tg-ch3">Chỗ nào cũng có lý do.</h2>
              <p className="tg-muted">Mỗi gợi ý ghi rõ vì sao hợp bạn, bao nhiêu người đã nhắc tới, và điều cần đánh đổi.</p>
              <Shot name="choose" label="thẻ một nơi ở bước Lựa chọn"><div className="tg-lk tg-lk--card">
                {spot.photos[0] && <figure className="tg-lk__media"><img src={thumbOf(spot.photos[0].src) ?? spot.photos[0].src} alt="" decoding="async" />{spot.category && <span className="tg-lk__cat">{spot.category}</span>}<figcaption>Ảnh: {spot.photos[0].credit}</figcaption></figure>}
                <div className="tg-lk__body">
                  <div className="tg-lk__title"><h3>{spot.name}</h3><p>{spot.area}{spot.rating ? ` · ★ ${spot.rating.toLocaleString('vi-VN')}` : ''}{spot.reviews ? ` · ${num(spot.reviews)} đánh giá Google` : ''}</p></div>
                  {why.length > 0 && <ul className="tg-lk__why" aria-label="Vì sao phù hợp">{why.map((w) => <li key={w.label}><Icon name="check" size={15} /><span>{w.label}, <small>{w.n} người nhắc</small></span></li>)}</ul>}
                  {trade && <p className="tg-lk__trade"><Icon name="warn" size={15} /><span><b>Đánh đổi:</b> {featureLabel(trade.id)}, {trade.n} người nhắc</span></p>}
                  <p className="tg-lk__facts">
                    <span>Ở lại ≈ {DAY[FOCUS].stay}</span>
                    {price && <span>{price}{spot.price?.per === 'person' ? '/người' : ''}</span>}
                    {peak && <span>Cuối tuần đông nhất {DAYPART[peak[0]] ?? peak[0]}</span>}
                  </p>
                </div>
              </div></Shot>
            </article>

            {/* 4 · Lịch trình: read back, then the day hour by hour; too many picks get three ways to drop some */}
            <article className="tg-l3__ch" aria-labelledby="tg-ch4">
              <p className="tg-kicker">Lịch trình <span className="tg-tag tg-tag--warn">Ví dụ</span></p>
              <h2 id="tg-ch4">Đọc lại một lượt, rồi xếp từng giờ.</h2>
              <p className="tg-muted">Trước khi xếp, TripGuardian đọc lại mọi điều đã ghi, chỗ nào chưa đúng thì bấm sửa. Chọn nhiều hơn số ngày thì có ba cách bỏ bớt, bạn quyết.</p>
              <Shot name="plan" label="đọc lại trước khi lập lịch"><p className="tg-lk__plans" aria-label="Ba cách bỏ bớt khi chọn quá nhiều">{PLANS.map((plan, i) => <span key={plan} className={i === 0 ? 'is-on' : ''}>{plan}</span>)}</p>
              <ol className="tg-l3__day">
                {DAY.map((item, i) => <li key={item.name}><time>{item.at}</time><span><b>{item.name}</b>{item.meal && <em>{item.meal}</em>}{i > 0 && <small className="tg-faint">≈ {legMinutes(ROUTE[i - 1], ROUTE[i])} phút xe máy từ chỗ trước</small>}</span></li>)}
              </ol></Shot>
            </article>

            {/* 5 · Đánh giá: confirm the plan, then a few quick questions that can all be skipped */}
            <article className="tg-l3__ch" aria-labelledby="tg-ch5">
              <p className="tg-kicker">Đánh giá</p>
              <h2 id="tg-ch5">Chốt lịch, chấm vài câu là xong.</h2>
              <p className="tg-muted">Lịch nằm trong Chuyến của tôi. Vài câu hỏi ngắn giúp lần sau gợi ý đúng gu hơn, bỏ qua cũng được.</p>
              <Shot name="feedback" label="màn Phản hồi sau khi chốt"><div className="tg-lk tg-lk--done">
                <p className="tg-lk__head"><span className="tg-lk__seal"><Icon name="check" size={20} strokeWidth={2.6} /></span><span><small>Chuyến Đà Lạt của bạn</small><b>Kế hoạch đã chốt.</b></span></p>
                <div className="tg-lk__rate">
                  <span>Gợi ý có đúng gu của bạn?</span>
                  <span className="tg-lk__scale" role="img" aria-label="Ví dụ: 5 trên 5">{[1, 2, 3, 4, 5].map((n) => <i key={n} className={n === 5 ? 'is-on' : ''}>{n}</i>)}</span>
                  <small><span>Chưa đúng</span><span>Rất đúng</span></small>
                </div>
              </div></Shot>
              <button type="button" className="tg-btn tg-btn--primary tg-l3__go" onClick={(e) => void begin(e.currentTarget)}>{cta}</button>
            </article>
          </div>

          {active === 0 && (!flat || window.__tgGL !== 'none') && (
            <div className="tg-l3__note">
              {!flat
                ? <button type="button" className="tg-l3__roam" disabled={!live} onClick={explore}><Icon name="compass" size={36} /><span><b>Xoay thử Đà Lạt 3D</b><small>Kéo chuột để xoay, cuộn để phóng to</small></span></button>
                : <button type="button" className="tg-l3__roam" onClick={() => { location.search = '?3d=on' }}><Icon name="compass" size={36} /><span><b>Xoay thử Đà Lạt 3D</b><small>Máy của bạn không có card đồ họa, bản 3D có thể chậm</small></span></button>}
            </div>
          )}

          {exploring && (
            <div className="tg-l3__ex" role="group" aria-label="Khám phá Đà Lạt 3D">
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
        <div className="tg-cta__in"><h2 id="tg-cta-h">Bắt đầu chuyến Đà Lạt của bạn.</h2><button type="button" className="tg-btn tg-btn--sun tg-cta__btn" onClick={(e) => void begin(e.currentTarget)}>{cta}</button><p>Miễn phí · Không cần tài khoản · Đăng nhập Google để lưu chuyến</p>{member && <button type="button" className="tg-link tg-cta__guest" onClick={(e) => void begin(e.currentTarget, true)}>Hoặc dùng thử với tư cách khách (phiên mới, tài khoản của bạn giữ nguyên)</button>}</div>
      </section>

      <footer className="tg-lf"><Logo size={26} dark /><span className="tg-lf__sp" /><span>Giờ giấc và quãng đường là ước tính; địa hình theo dữ liệu thật, cây và mái nhà chỉ là biểu tượng. Số liệu theo bản dữ liệu {stats.asOf?.split('-').reverse().join('/')}: {num(stats.places)} nơi, {num(stats.withPhotos)} nơi có ảnh thật.</span></footer>
    </div>
  )
}
