import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import Lenis from 'lenis'
import { useEffect, useRef, useState } from 'react'
import { startGuest, useAccount } from '../account'
import { track } from '../events'
import { flushSync } from 'react-dom'
import { navigate } from '../../router'
import { prefetchSnapshot, type Cover } from '../../data/store'
import { fetchLandscape } from '../landing/bin'
import { hasGpu } from '../landing/device'
import raw from '../landing/places.json'
import stats from '../landing/stats.json'
import type { DalatScene, ScenePlace, SceneState } from '../landing/scene'
import { reducedMotion } from '../lib'
import { Photo, thumbOf } from '../ui/common'
import { Icon, Logo } from '../ui/icons'
import { useTitle } from '../ui/Shell'

// Desktop landing: one sticky stage with a 3D model of Đà Lạt; scrolling moves the camera through six chapters.
// Real places copied from the snapshot by web/scripts/pick_landing_places.py.
interface LPlace extends ScenePlace { id: string; photos: Cover[]; rating?: number; reviews?: number; crowd?: { weekend?: Record<string, number> }; videos?: { url: string; handle: string }[] }
const PLACES = raw as unknown as LPlace[]
const byName = (n: string) => PLACES.find((p) => p.name.startsWith(n))!

gsap.registerPlugin(ScrollTrigger)
// The example day, in visiting order. Times and stays are illustrative; places are real; the minutes between stops use
// the planner's rough estimate (config/planning.yaml: road_factor, rough_speed_kmh).
const DAY: { name: string; at: string; stay: string; meal?: string }[] = [
  { name: 'Thiên Đường Săn Mây', at: '05:30', stay: '1 giờ 30' },
  { name: 'Tiệm cà phê Thênh Thang', at: '08:45', stay: '1 giờ' },
  { name: 'Hồ Xuân Hương', at: '11:00', stay: '1 giờ' },
  { name: 'An - Tuyền Lâm', at: '12:30', stay: '1 giờ', meal: 'Ăn trưa' },
  { name: 'Hồ Tuyền Lâm', at: '15:00', stay: '1 giờ 30' },
  { name: 'Hoàng hôn 3000', at: '17:15', stay: '1 giờ 30', meal: 'Ăn tối' },
]
const ROUTE = DAY.map((d) => byName(d.name))
const FOCUS = 1 // the place the reason card shows
const ROAD_FACTOR = 1.4
const SPEED_KMH = 25
const AREAS: ScenePlace[] = [
  { name: 'Trung tâm', lat: 11.951, lng: 108.452 },
  { name: 'Langbiang', lat: 12.017, lng: 108.44 },
  { name: 'Cầu Đất', lat: 11.872, lng: 108.556 },
  { name: 'Trại Mát', lat: 11.948, lng: 108.505 },
  { name: 'Tuyền Lâm', lat: 11.884, lng: 108.412 },
]
// the example day as postcards in the 3D model, each with its own real photo (the light thumbnail when there is one);
// the first photo of Hồ Xuân Hương is a night shot, so its postcard uses the daylight one
const POSTCARD_PHOTO: Record<string, number> = { 'Hồ Xuân Hương': 1 }
const SCENE_PLACES: ScenePlace[] = ROUTE.map((p) => {
  const ph = p.photos[POSTCARD_PHOTO[p.name] ?? 0]
  return { name: p.name, lat: p.lat, lng: p.lng, photo: ph && (thumbOf(ph.src) ?? ph.src) }
})
// Beat i is fully in at timeline time i; the rail groups the evidence beat with selection.
const RAIL: [string, number][] = [['Mở đầu', 0], ['Tìm hiểu', 1], ['Lựa chọn', 2], ['Lịch trình', 4], ['Đánh giá', 5]]
const BEATS = 6
const STORY_LEN = 5.5
const stepOf = (beat: number) => (beat === 3 ? 2 : beat)
const FEEDBACK: [string, number][] = [['Gợi ý có đúng gu của bạn?', 5], ['Lý do có dễ hiểu?', 4], ['Lịch có thực tế?', 5], ['Bạn tự tin hơn về chuyến đi?', 4]]
const HINTS = ['Cuộn xuống để xem cách hoạt động', 'Cuộn tiếp: Lựa chọn', 'Cuộn tiếp: lý do từng nơi', 'Cuộn tiếp: Lịch trình', 'Cuộn tiếp: Đánh giá', 'Còn nữa bên dưới: địa điểm thật']
// The light version uses one frame from the real 3D model for each chapter.
const PLATES = ['/img/landing-poster.webp', '/img/landing-p1.webp', '/img/landing-p2.webp', '/img/landing-p3.webp', '/img/landing-p4.webp', '/img/landing-p5.webp']
// the four photos of the "Địa điểm thật" section: place, and which of its photos shows the place best (daylight, recognisable)
const SHOWCASE: [string, number][] = [['Thung lũng Tình Yêu', 3], ['Hồ Xuân Hương', 1], ['Dinh III', 3], ['Thác Datanla', 0]]
const DAYPART: Record<string, string> = { early_morning: 'sáng sớm', morning: 'buổi sáng', noon: 'buổi trưa', afternoon: 'buổi chiều', evening: 'buổi tối', night: 'ban đêm' }
const FAQ = [
  ['Có cần tài khoản không?', 'Không. Bạn lên lịch ngay, không cần đăng nhập. Khách không được lưu lịch sử: chuyến bị xóa sau 24 giờ không hoạt động. Đăng nhập Google nếu muốn lưu chuyến, dùng Google Calendar và thông báo.'],
  ['Mất bao lâu để có lịch?', 'Bạn kể chuyến đi bằng chat hoặc chọn nhanh, rồi TripGuardian xếp lịch từng giờ. Phần kể thường chỉ mất vài phút.'],
  ['Mang lịch theo được không?', 'Được. Sau khi đăng nhập, bạn thêm lịch vào Google Calendar, xem trước rồi mới xác nhận.'],
  ['Chưa đặt khách sạn thì sao?', 'Cứ để trống, hoặc nhập nơi bạn dự định ở. TripGuardian dùng nó để tính đường đi và không đặt chỗ giúp bạn. Thiếu thông tin này, lịch ngày đầu và ngày cuối được ghi là ước lượng.'],
  ['Nếu một nơi thiếu thông tin thì sao?', 'TripGuardian ghi rõ “Chưa có thông tin” thay vì đoán. Điều gì chưa chắc chắn đều được đánh dấu ngay tại chỗ.'],
]
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
  const spot = ROUTE[FOCUS]
  const peak = spot.crowd?.weekend ? Object.entries(spot.crowd.weekend).reduce((a, b) => (b[1] > a[1] ? b : a)) : null
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
          .from(chapters[1].querySelectorAll('.tg-stamp'), { x: -60, autoAlpha: 0, stagger: 0.06, duration: 0.2 }, 0.62)
          .from(chapters[1].querySelectorAll('.tg-chip'), { x: 60, autoAlpha: 0, stagger: 0.05, duration: 0.2 }, 0.68)
          .to(chapters[1], leave, 1.2)
          .to(state, { cam: 2, duration: 1 }, 1.1)
          .to(state, { dots: 0, duration: 0.6 }, 1.3)
          .to(count, { value: ROUTE.length, duration: 0.65, onUpdate: writeCount }, 1.3)
          .to(state, { five: 1, duration: 0.5 }, 1.45)
          .to(chapters[2], enter, 1.6)
          .to(state, { route: 1, duration: 0.4 }, 1.55)
          .to(chapters[2], leave, 2.2)
          .to(state, { cam: 3, duration: 1 }, 2.1)
          .to(chapters[3], enter, 2.6)
          .fromTo(chapters[3].querySelector('.tg-l3__fill'), { scaleX: 0 }, { scaleX: 1, duration: 0.3 }, 2.65)
          .from(chapters[3].querySelectorAll('.tg-l3__clip'), { y: 40, autoAlpha: 0, stagger: 0.06, duration: 0.2 }, 2.7)
          .to(chapters[3], leave, 3.2)
          .to(state, { cam: 4, duration: 1 }, 3.1)
          .to(chapters[4], enter, 3.6)
          .from(chapters[4].querySelectorAll('.tg-l3__day li'), { x: 30, autoAlpha: 0, stagger: 0.06, duration: 0.2 }, 3.62)
          .to(state, { travel: 1, duration: 0.8 }, 3.7)
          .to(chapters[4], leave, 4.2)
          .to(state, { cam: 5, duration: 1 }, 4.1)
          .to(chapters[5], enter, 4.6)
          .from(chapters[5].querySelectorAll('.tg-l3__rate li'), { x: 30, autoAlpha: 0, stagger: 0.06, duration: 0.2 }, 4.62)
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
  // The landing leans in and fades while the browser cross-fades to the app (View Transitions where it has them).
  const begin = async () => {
    if (leaving || starting.current) return
    starting.current = true
    const utm = Object.fromEntries([...new URLSearchParams(location.search)].filter(([k]) => k.startsWith('utm_')))
    track('landing_cta', utm)
    if (!account) await startGuest().catch(() => {})
    starting.current = false
    const go = () => { navigate('/app'); window.scrollTo(0, 0) }
    const vt = (document as Document & { startViewTransition?: (cb: () => void) => unknown }).startViewTransition
    if (still || !vt) return go()
    setLeaving(true)
    window.setTimeout(() => vt.call(document, () => flushSync(go)), 380)
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
        <a href="/" className="tg-ln__logo"><Logo size={30} /><span>TripGuardian</span></a>
        <div className="tg-ln__links">
          <button type="button" onClick={() => toChapter(1)}>Cách hoạt động</button>
          <button type="button" onClick={() => toId('tg-photos')}>Địa điểm</button>
          <button type="button" onClick={() => toId('tg-faq')}>Hỏi nhanh</button>
        </div>
        <a href="/app/login" className="tg-ln__login" onClick={(e) => { e.preventDefault(); navigate('/app/login') }}>Đăng nhập</a>
        <button type="button" className="tg-btn tg-btn--primary tg-btn--sm" onClick={begin}>Lên lịch chuyến của bạn</button>
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
              <p className="tg-l3__sub">Kể chuyến đi trong 2 phút. TripGuardian chọn từ <b>{num(stats.places)}</b> nơi có thật và xếp lịch từng giờ.</p>
              <div className="tg-l3__start">
                <button type="button" className="tg-btn tg-btn--primary tg-l3__cta" onClick={begin}>{cta}</button>
                <button type="button" className="tg-l3__how" onClick={() => toChapter(1)}>Xem cách hoạt động <Icon name="chevronDown" size={18} /></button>
              </div>
              <ul className="tg-l3__ticks">
                <li><Icon name="check" size={14} />Miễn phí</li>
                <li><Icon name="check" size={14} />Không cần tài khoản</li>
                <li><Icon name="check" size={14} />Chỉ gồm nơi có thật</li>
              </ul>
              </div>
            </div>

            <article className="tg-l3__ch" aria-labelledby="tg-ch1">
              <p className="tg-kicker">Tìm hiểu</p>
              <h2 id="tg-ch1">Tách rõ điều bắt buộc và điều mong muốn.</h2>
              <p className="tg-muted">Điều bắt buộc giữ chắc, điều mong muốn để nhẹ như sương.</p>
              <div className="tg-l3__ticket">
                <h3 className="tg-ticket__h">Thông tin chuyến đi</h3>
                <dl>{[['Thời gian', '3 ngày'], ['Số người', '2 người'], ['Phương tiện', 'Xe máy']].map(([label, value]) => <div key={label} className="tg-ticket__row"><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
                <div className="tg-l3__zone"><h4>Bắt buộc</h4><div><span className="tg-stamp"><Icon name="lock" size={14} />Tránh nơi quá đông</span><span className="tg-stamp"><Icon name="lock" size={14} />Mỗi chặng ≤ 45 phút</span></div></div>
                <div className="tg-l3__zone"><h4>Mong muốn</h4><div>{['chill', 'cà phê', 'săn mây'].map((chip) => <span key={chip} className="tg-chip tg-chip--dash">{chip}</span>)}</div></div>
              </div>
            </article>

            <article className="tg-l3__ch" aria-labelledby="tg-ch2">
              <p className="tg-kicker">Lựa chọn</p>
              <h2 id="tg-ch2" aria-label={`Còn lại ${ROUTE.length} nơi hợp với bạn, lọc từ ${num(stats.places)} địa điểm`}><span aria-hidden="true">Còn lại <span ref={counter} className="tg-l3__count">{still ? ROUTE.length : num(stats.places)}</span> nơi hợp với bạn.</span></h2>
              <p className="tg-muted">Giữa hàng nghìn ánh đèn, chỉ những nơi hợp chuyến đi sáng lên.</p>
              <ul className="tg-l3__legend">
                <li><i className="is-all" />Mỗi chấm là một địa điểm trong dữ liệu</li>
                <li><i className="is-five" />Nơi được chọn, nối thành tuyến đi</li>
              </ul>
            </article>

            <article className="tg-l3__ch" aria-labelledby="tg-ch3">
              <p className="tg-kicker">Lựa chọn · lý do</p>
              <h2 id="tg-ch3">Chọn nơi nào cũng có lý do.</h2>
              <p className="tg-muted">Dữ liệu thật cho biết nơi nào hợp bạn và điều gì cần biết trước.</p>
              <div className="tg-l3__ev">
                <div className="tg-l3__claim">
                  <b>{spot.name}</b>
                  <span>View đồi thông, hợp “chill” và “cà phê”</span>
                  <small className="tg-faint">{spot.rating && spot.reviews ? `${spot.rating.toLocaleString('vi-VN')}★ từ ${num(spot.reviews)} đánh giá Google` : 'Tổng hợp từ dữ liệu địa điểm'}</small>
                  <div className="tg-l3__bar" aria-hidden="true"><i className="tg-l3__fill" style={{ width: `${peak?.[1] ?? 58}%` }} /></div>
                </div>
                <div className="tg-l3__clips" style={{ gridTemplateColumns: `repeat(${Math.min(2, spot.videos?.length ?? 1)}, minmax(0, 120px))` }}>{(spot.videos ?? []).slice(0, 2).map((video) => <a key={video.url} className="tg-l3__clip" href={video.url} target="_blank" rel="noreferrer"><Photo photo={spot.photos[1] ?? spot.photos[0]} alt="" /><span><Icon name="play" size={20} /><b>@{video.handle}</b><small>TikTok</small></span></a>)}</div>
                {peak && <p className="tg-l3__quote">Cuối tuần đông nhất {DAYPART[peak[0]] ?? peak[0]}; lịch ví dụ đặt trước giờ cao điểm.</p>}
              </div>
            </article>

            <article className="tg-l3__ch" aria-labelledby="tg-ch4">
              <p className="tg-kicker">Lịch trình <span className="tg-tag tg-tag--warn">Ví dụ minh họa</span></p>
              <h2 id="tg-ch4">Một ngày đi kịp từng điểm.</h2>
              <p className="tg-muted">Từ bình minh trên đồi đến hoàng hôn bên hồ, không vội mà vẫn kịp.</p>
              <ol className="tg-l3__day">
                {DAY.map((item, i) => <li key={item.name}><time>{item.at}</time><span><b>{item.name}</b>{item.meal && <em>{item.meal}</em>}{i > 0 && <small className="tg-faint">~{legMinutes(ROUTE[i - 1], ROUTE[i])} phút từ điểm trước</small>}</span></li>)}
              </ol>
              <div className="tg-bar is-ready tg-l3__ready"><span className="tg-bar__status"><i />Đã kiểm tra</span><span className="tg-bar__stats"><span>Mỗi chặng ≤ 45 phút</span><span>Né giờ đông</span></span></div>
            </article>

            <article className="tg-l3__ch" aria-labelledby="tg-ch5">
              <p className="tg-kicker">Đánh giá</p>
              <h2 id="tg-ch5">Chuyến sau hợp gu hơn chuyến này.</h2>
              <p className="tg-muted">Về rồi, kể lại vài điều. Lần sau Đà Lạt sẽ hiểu bạn hơn.</p>
              <ul className="tg-l3__rate">{FEEDBACK.map(([question, value]) => <li key={question}><span>{question}</span><span className="tg-l3__scale" role="img" aria-label={`${value} trên 5`}>{[1, 2, 3, 4, 5].map((n) => <i key={n} className={n <= value ? 'is-on' : ''} />)}</span></li>)}</ul>
              <button type="button" className="tg-btn tg-btn--primary tg-l3__go" onClick={begin}>{cta}</button>
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
        <div className="tg-l__head tg-rv"><h2 id="tg-l4-h">Địa điểm thật, trải nghiệm thật</h2><p className="tg-muted">{num(stats.withPhotos)} nơi có ảnh chụp thực tế từ Google Maps, ghi rõ tên và nguồn. Không dùng ảnh minh họa cho một địa điểm cụ thể.</p></div>
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
        <div className="tg-cta__in"><h2 id="tg-cta-h">Bắt đầu chuyến Đà Lạt của bạn.</h2><button type="button" className="tg-btn tg-btn--sun tg-cta__btn" onClick={begin}>{cta}</button><p>Miễn phí · Không cần tài khoản · Đăng nhập Google để lưu chuyến</p></div>
      </section>

      <footer className="tg-lf"><Logo size={26} dark /><span>TripGuardian Đà Lạt</span><span className="tg-lf__sp" /><span>Giờ giấc và quãng đường là ước tính; địa hình theo dữ liệu thật, cây và mái nhà chỉ là biểu tượng. Số liệu theo bản dữ liệu {stats.asOf?.split('-').reverse().join('/')}: {num(stats.places)} nơi, {num(stats.withPhotos)} nơi có ảnh thật.</span></footer>
    </div>
  )
}
