import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import Lenis from 'lenis'
import { useEffect, useRef, useState } from 'react'
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

// Desktop landing (docs/UI_SPEC_LANDING.md): one sticky stage with a 3D model of Đà Lạt; scrolling moves the
// camera through five chapters. Real places copied from the snapshot by web/scripts/pick_landing_places.py.
interface LPlace extends ScenePlace { id: string; photos: Cover[]; voices?: number; crowd?: { weekend?: Record<string, number> }; quotes?: { text: string }[]; videos?: { url: string; handle: string }[] }
const PLACES = raw as unknown as LPlace[]
const byName = (n: string) => PLACES.find((p) => p.name.startsWith(n))!

gsap.registerPlugin(ScrollTrigger)
// The example day, in visiting order. Times are illustrative; places, photos and distances are real.
const ROUTE = ['Thiên Đường Săn Mây', 'Tiệm cà phê Thênh Thang', 'Hồ Xuân Hương', 'An - Tuyền Lâm', 'Hồ Tuyền Lâm'].map(byName)
const TIMES = ['05:30', '08:45', '11:00', '12:30', '15:00']
const FOCUS = 1 // the place the evidence chapter flies to
const AREAS: ScenePlace[] = [
  { name: 'Trung tâm', lat: 11.951, lng: 108.452 },
  { name: 'Langbiang', lat: 12.017, lng: 108.44 },
  { name: 'Cầu Đất', lat: 11.872, lng: 108.556 },
  { name: 'Trại Mát', lat: 11.948, lng: 108.505 },
  { name: 'Tuyền Lâm', lat: 11.884, lng: 108.412 },
]
// beat i is fully in at timeline time i; the rail groups beats into the product's steps (evidence is part of choosing)
const RAIL: [string, number][] = [['Mở đầu', 0], ['Tìm hiểu', 1], ['Lựa chọn', 2], ['Lịch trình', 4], ['Đánh giá', 5]]
const BEATS = 6
const STORY_LEN = 5.5 // the last beat holds to the end
const stepOf = (beat: number) => (beat === 3 ? 2 : beat)
const FEEDBACK: [string, number][] = [['Gợi ý có đúng gu của bạn?', 5], ['Lý do có dễ hiểu?', 4], ['Lịch có thực tế?', 5], ['Bạn tự tin hơn về chuyến đi?', 4]]
// the five as postcards on the 3D scene: their own real photo, the light thumbnail when there is one
const SCENE_FIVE: ScenePlace[] = ROUTE.map((p) => ({ name: p.name, lat: p.lat, lng: p.lng, photo: p.photos[0] && (thumbOf(p.photos[0].src) ?? p.photos[0].src) }))
const FAQ = [
  ['Có cần tạo tài khoản không?', 'Không. Bạn dùng được ngay. Chuyến đi được lưu theo mã chuyến, danh sách chuyến nằm trên trình duyệt này.'],
  ['Nếu một nơi thiếu thông tin thì sao?', 'TripGuardian ghi rõ “Chưa có thông tin” thay vì đoán. Điều gì chưa chắc chắn đều được đánh dấu ngay tại chỗ.'],
  ['TripGuardian có quyết định thay tôi không?', 'Không. Mỗi gợi ý đi kèm lý do và điều phải đánh đổi; giữ hay bỏ là do bạn chọn.'],
  ['TripGuardian có đặt chỗ ở giúp tôi không?', 'Không. Bạn nhập nơi đang ở hoặc chọn từ danh sách tra trên Google Maps; TripGuardian chỉ dùng nó để tính đường đi.'],
]
// Where the free camera can fly: real places, and how close to look at each
const FLY: { name: string; lat: number; lng: number; dist: number }[] = [
  { name: 'Trung tâm', lat: 11.9445, lng: 108.4462, dist: 55 },
  { name: 'Langbiang', lat: 12.0453, lng: 108.441, dist: 110 },
  { name: 'Hồ Tuyền Lâm', lat: 11.8916, lng: 108.4227, dist: 80 },
  { name: 'Cầu Đất', lat: 11.872, lng: 108.556, dist: 90 },
  { name: 'Trại Mát', lat: 11.948, lng: 108.505, dist: 70 },
]
// the hint at the foot of the stage: always says there is more below, and what comes next
const HINTS = ['Cuộn để xem cách hoạt động', 'Cuộn tiếp: Lựa chọn', 'Cuộn tiếp: lý do từng nơi', 'Cuộn tiếp: Lịch trình', 'Cuộn tiếp: Đánh giá', 'Còn nữa bên dưới: ảnh thật']
// The light version (no GPU): one picture per chapter, taken from the 3D model itself (web/scripts/shots_plates.mjs)
const PLATES = ['/img/landing-poster.webp', '/img/landing-p1.webp', '/img/landing-p2.webp', '/img/landing-p3.webp', '/img/landing-p4.webp', '/img/landing-p5.webp']
const num = (n: number) => n.toLocaleString('vi-VN')
const km = (a: ScenePlace, b: ScenePlace) => {
  const R = 6371, r = Math.PI / 180
  const x = (b.lng - a.lng) * r * Math.cos(((a.lat + b.lat) / 2) * r), y = (b.lat - a.lat) * r
  return Math.hypot(x, y) * R
}
const shiftFor = (w: number) => (w > 1100 ? 0.2 : w > 900 ? 0.25 : 0) // keep the model right of the text column

export function Landing() {
  useTitle('TripGuardian · Đà Lạt')
  const story = useRef<HTMLElement>(null)
  const stage = useRef<HTMLDivElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const counter = useRef<HTMLSpanElement>(null)
  const fiveEls = useRef<HTMLElement[]>([])
  const areaEls = useRef<HTMLElement[]>([])
  const lenisRef = useRef<Lenis | null>(null)
  const [still] = useState(reducedMotion)
  const [flat, setFlat] = useState(() => !hasGpu()) // no GPU (or too slow): chapter pictures instead of the live model
  const [live, setLive] = useState(false) // the 3D model has drawn its first frame: the poster fades out
  const [active, setActive] = useState(0)
  const [used, setUsed] = useState(false) // the visitor has turned the model: the hint steps aside
  const sceneRef = useRef<DalatScene | null>(null)
  const [exploring, setExploring] = useState(false) // free exploration of the 3D model
  const [leaving, setLeaving] = useState(false) // on its way to the home page
  const exploringRef = useRef(false)
  const [faq, setFaq] = useState(0)
  const crowd = ROUTE[FOCUS]
  const crowdPct = crowd.crowd?.weekend ? Math.max(...Object.values(crowd.crowd.weekend)) : null
  const mosaic = ['Hồ Tuyền Lâm', 'Đỉnh đèo Ngoạn Mục', 'Euro Garden', 'Hồ Xuân Hương', 'Nhà Bên Rừng', 'Dinh III'].map(byName)

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
    let hintTimer = 0
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
    // Story: drag turns the model round the valley (vertical page scroll on touch screens still works, touch-action:
    // pan-y). Free exploration: drag turns, right-drag / Shift-drag slides, wheel and pinch zoom.
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
    // the story's chapters shrink to fit a short window instead of running off the bottom of it
    const fit = () => {
      if (still || innerWidth <= 900) return sec.querySelectorAll<HTMLElement>('.tg-l3__ch').forEach((el) => (el.style.zoom = ''))
      const room = st.clientHeight - 150
      sec.querySelectorAll<HTMLElement>('.tg-l3__ch').forEach((el) => {
        el.style.zoom = ''
        const h = el.offsetHeight
        if (h > room) el.style.zoom = String(Math.max(0.6, room / h))
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
      scene = DalatScene.create(cv, { points: points as [number, number][], five: SCENE_FIVE, focus: FOCUS, land }, still)
      performance.mark('tg-scene-built')
      if (!scene) { setFlat(true); return }
      scene.onReady = () => { performance.mark('tg-scene-first-frame'); setLive(true) }
      scene.onGiveUp = () => { setFlat(true); setLive(false); scene?.setRunning(false); sceneRef.current = null }
      sceneRef.current = scene
      scene.onTurn = () => setUsed(true)
      if (!still) hintTimer = window.setTimeout(() => scene?.hintTurn(), 2000)
      scene.bindLabels('five', fiveEls.current)
      scene.bindLabels('area', areaEls.current, AREAS)
      // reduced motion: one frame that tells the whole story, from the last view (cards right of the text)
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
        const tick = (t: number) => lenis!.raf(t * 1000)
        gsap.ticker.add(tick)
        gsap.ticker.lagSmoothing(0)
        const ch = gsap.utils.toArray<HTMLElement>('.tg-l3__ch', sec)
        const n = { v: stats.places }
        const write = () => { if (counter.current) counter.current.textContent = num(Math.round(n.v)) }
        const inn = { autoAlpha: 1, y: 0, duration: 0.3, ease: 'power2.out' }
        const out = { autoAlpha: 0, y: -36, duration: 0.25, ease: 'power1.in' }
        const tl = gsap.timeline({
          defaults: { ease: 'none' },
          onUpdate: () => { push(); setActive(Math.min(BEATS - 1, Math.round(tl.time()))) },
          scrollTrigger: { trigger: sec, start: 'top top', end: 'bottom bottom', scrub: 0.8 },
        })
        gsap.set(ch.slice(1), { autoAlpha: 0, y: 36 })
        // 0 → 1: read the trip first, as must-haves and wishes
        tl.to(state, { cam: 1, duration: 1 }, 0)
          .to(ch[0], out, 0)
          .to(state, { areas: 0, duration: 0.4 }, 0.1)
          .to(ch[1], inn, 0.6)
          .from(ch[1].querySelectorAll('.tg-stamp'), { x: -60, autoAlpha: 0, stagger: 0.06, duration: 0.2 }, 0.62)
          .from(ch[1].querySelectorAll('.tg-chip'), { x: 60, autoAlpha: 0, stagger: 0.05, duration: 0.2 }, 0.68)
          // 1 → 2: then filter every place down to the few that fit
          .to(ch[1], out, 1.2)
          .to(state, { cam: 2, duration: 1 }, 1.1)
          .to(state, { dots: 0, duration: 0.6 }, 1.3)
          .to(n, { v: 5, duration: 0.65, onUpdate: write }, 1.3)
          .to(state, { five: 1, duration: 0.5 }, 1.45)
          .to(ch[2], inn, 1.6)
          .to(state, { route: 1, duration: 0.4 }, 1.55)
          // 2 → 3: fly to one place and open its evidence
          .to(ch[2], out, 2.2)
          .to(state, { cam: 3, duration: 1 }, 2.1)
          .to(ch[3], inn, 2.6)
          .fromTo(ch[3].querySelector('.tg-l3__fill'), { scaleX: 0 }, { scaleX: 1, duration: 0.3 }, 2.65)
          .from(ch[3].querySelectorAll('.tg-l3__clip'), { y: 40, autoAlpha: 0, stagger: 0.06, duration: 0.2 }, 2.7)
          // 3 → 4: back out over the day, a marker rides the route
          .to(ch[3], out, 3.2)
          .to(state, { cam: 4, duration: 1 }, 3.1)
          .to(ch[4], inn, 3.6)
          .from(ch[4].querySelectorAll('.tg-l3__day li'), { x: 30, autoAlpha: 0, stagger: 0.06, duration: 0.2 }, 3.62)
          .to(state, { travel: 1, duration: 0.8 }, 3.7)
          // 4 → 5: rise over the valley; after the trip, a few questions make the next one fit better
          .to(ch[4], out, 4.2)
          .to(state, { cam: 5, duration: 1 }, 4.1)
          .to(ch[5], inn, 4.6)
          .from(ch[5].querySelectorAll('.tg-l3__rate li'), { x: 30, autoAlpha: 0, stagger: 0.06, duration: 0.2 }, 4.62)
          .to({}, { duration: 0.01 }, STORY_LEN - 0.01) // pad to STORY_LEN so beat i sits at time i
        gsap.from('.tg-l4__tile', { y: 60, opacity: 0, stagger: 0.08, duration: 0.7, ease: 'power2.out', scrollTrigger: { trigger: '.tg-l4', start: 'top 72%' } })
        return () => { gsap.ticker.remove(tick); lenis?.destroy(); lenisRef.current = null }
      })
    }
    return () => {
      gone = true
      window.clearTimeout(hintTimer)
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

  // Trải nghiệm đi only opens the home page; the questions start there, when the visitor says what the trip is.
  // The landing leans in and fades while the browser cross-fades to the home page (View Transitions where it has them).
  const begin = () => {
    if (leaving) return
    const utm = Object.fromEntries([...new URLSearchParams(location.search)].filter(([k]) => k.startsWith('utm_')))
    track('landing_cta', utm)
    const go = () => { navigate('/app'); window.scrollTo(0, 0) }
    const vt = (document as Document & { startViewTransition?: (cb: () => void) => unknown }).startViewTransition
    if (still || !vt) return go()
    setLeaving(true)
    window.setTimeout(() => vt.call(document, () => flushSync(go)), 380)
  }

  // Free exploration: the page stops scrolling, the story steps aside, the visitor drives the camera
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
    sc.setExplore(true)
    setUsed(true)
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
      const step = 60
      const k = e.key.toLowerCase()
      if (k === 'escape') leaveExplore()
      else if (k === 'arrowleft' || k === 'a') sc.explorePan(step, 0)
      else if (k === 'arrowright' || k === 'd') sc.explorePan(-step, 0)
      else if (k === 'arrowup' || k === 'w') sc.explorePan(0, step)
      else if (k === 'arrowdown' || k === 's') sc.explorePan(0, -step)
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
  // chapter i sits at timeline time i, out of STORY_LEN over the section's scroll length
  const toChapter = (i: number) => {
    const sec = story.current
    if (!sec) return
    const top = sec.offsetTop + (i / STORY_LEN) * (sec.offsetHeight - innerHeight) + (i ? 4 : 0)
    if (lenisRef.current) lenisRef.current.scrollTo(top, { duration: 1.2 })
    else window.scrollTo({ top, behavior: still ? 'auto' : 'smooth' })
  }
  const toId = (id: string) => {
    const el = document.getElementById(id)
    if (!el) return
    if (lenisRef.current) lenisRef.current.scrollTo(el, { duration: 1.2, offset: -24 })
    else el.scrollIntoView({ behavior: still ? 'auto' : 'smooth' })
  }

  return (
    <div className={`tg-l ${still ? 'is-still' : ''} ${leaving ? 'is-leaving' : ''}`}>
      <nav className="tg-ln" aria-label="Trang giới thiệu">
        <a href="/" className="tg-ln__logo"><Logo size={30} /><span>TripGuardian</span></a>
        <div className="tg-ln__links">
          <button type="button" onClick={() => toChapter(1)}>Cách hoạt động</button>
          <button type="button" onClick={() => toId('tg-photos')}>Ảnh thật</button>
          <button type="button" onClick={() => toId('tg-faq')}>Hỏi nhanh</button>
        </div>
        <a href="/app/login" className="tg-ln__login" onClick={(e) => { e.preventDefault(); navigate('/app/login') }}>Đăng nhập</a>
        <button type="button" className="tg-btn tg-btn--primary tg-btn--sm" onClick={begin}>Trải nghiệm đi</button>
      </nav>

      <section className="tg-l3" ref={story} aria-label="Cách TripGuardian lên một chuyến Đà Lạt">
        <div className={`tg-l3__stage ${flat ? 'is-flat' : ''} ${live ? 'is-live' : ''} ${exploring ? 'is-exploring' : ''}`} ref={stage}>
          <div className="tg-l3__poster" aria-hidden="true" />
          {flat && <div className="tg-l3__plates" aria-hidden="true">{PLATES.map((src, i) => <img key={src} src={src} alt="" decoding="async" loading={i ? 'lazy' : 'eager'} className={i === Math.min(active, PLATES.length - 1) ? 'is-on' : ''} />)}</div>}
          <canvas ref={canvas} className="tg-l3__cv" role="img" aria-label={`Mô hình 3D Đà Lạt theo địa hình thật, kéo để xoay 360 độ: ${num(stats.places)} địa điểm trong dữ liệu; năm nơi được chọn nối thành một tuyến đi`} />
          <div className="tg-l3__veil" aria-hidden="true" />
          <div className="tg-l3__labels" aria-hidden="true">
            {AREAS.map((a, i) => <span key={a.name} className="tg-l3__area" ref={(el) => { if (el) areaEls.current[i] = el }}><span>{a.name}</span></span>)}
            {ROUTE.map((p, i) => <span key={p.id} className="tg-l3__pin" ref={(el) => { if (el) fiveEls.current[i] = el }}><span><b>{i + 1}</b>{p.name}</span></span>)}
          </div>

          <div className="tg-l3__chs">
            <div className="tg-l3__ch tg-l3__hero">
              <p className="tg-kicker">TripGuardian · Đà Lạt</p>
              <h1>Hàng nghìn nơi ở Đà Lạt. <em>Chỉ giữ nơi hợp với bạn.</em></h1>
              <p className="tg-l3__poem">Sương sớm, tiếng thông reo, và một chuyến đi vừa với bạn.</p>
              <div className="tg-l3__start">
                <button type="button" className="tg-btn tg-btn--primary tg-l3__cta" onClick={begin}>Trải nghiệm đi <Icon name="arrow" size={20} /></button>
                {!flat && <button type="button" className="tg-btn tg-btn--ghost tg-l3__roam" disabled={!live} onClick={explore}><Icon name="compass" size={18} />Khám phá Đà Lạt 3D</button>}
                {flat && window.__tgGL !== 'none' && <button type="button" className="tg-btn tg-btn--ghost tg-l3__roam" onClick={() => { location.search = '?3d=on' }} title="Máy của bạn không có card đồ họa, bản 3D có thể chậm"><Icon name="compass" size={18} />Thử bản 3D</button>}
              </div>
              <p className="tg-l3__proof"><b>{num(stats.places)}</b> địa điểm có thật<i aria-hidden="true" /><b>{num(stats.withPhotos)}</b> nơi có ảnh thực tế<i aria-hidden="true" />Không cần tài khoản</p>
            </div>

            <article className="tg-l3__ch" aria-labelledby="tg-ch1">
              <p className="tg-kicker">Tìm hiểu</p>
              <h2 id="tg-ch1">Tách rõ điều bắt buộc và điều mong muốn.</h2>
              <p className="tg-muted">Điều bắt buộc giữ chắc, điều mong muốn để nhẹ như sương.</p>
              <div className="tg-l3__ticket">
                <h3 className="tg-ticket__h">Thông tin chuyến đi</h3>
                <dl>{[['Thời gian', '3 ngày'], ['Số người', '2 người'], ['Phương tiện', 'Xe máy']].map(([a, b]) => <div key={a} className="tg-ticket__row"><dt>{a}</dt><dd>{b}</dd></div>)}</dl>
                <div className="tg-l3__zone"><h4>Bắt buộc</h4><div><span className="tg-stamp"><Icon name="lock" size={14} />Tránh nơi quá đông</span><span className="tg-stamp"><Icon name="lock" size={14} />Mỗi chặng ≤ 45 phút</span></div></div>
                <div className="tg-l3__zone"><h4>Mong muốn</h4><div>{['chill', 'cà phê', 'săn mây'].map((c) => <span key={c} className="tg-chip tg-chip--dash">{c}</span>)}</div></div>
              </div>
            </article>

            <article className="tg-l3__ch" aria-labelledby="tg-ch2">
              <p className="tg-kicker">Lựa chọn</p>
              <h2 id="tg-ch2" aria-label={`Còn lại 5 nơi hợp với bạn, lọc từ ${num(stats.places)} địa điểm`}><span aria-hidden="true">Còn lại <span ref={counter} className="tg-l3__count">{still ? 5 : num(stats.places)}</span> nơi hợp với bạn.</span></h2>
              <p className="tg-muted">Giữa hàng nghìn ánh đèn, chỉ năm nơi sáng lên cho bạn.</p>
              <ul className="tg-l3__legend">
                <li><i className="is-all" />Mỗi chấm là một địa điểm trong dữ liệu</li>
                <li><i className="is-five" />Nơi được chọn, nối thành tuyến đi</li>
              </ul>
            </article>

            <article className="tg-l3__ch" aria-labelledby="tg-ch3">
              <p className="tg-kicker">Lựa chọn · lý do</p>
              <h2 id="tg-ch3">Chọn nơi nào cũng có lý do.</h2>
              <p className="tg-muted">Mỗi nơi đều có người đã đến, đã kể và đã chụp.</p>
              <div className="tg-l3__ev">
                <div className="tg-l3__claim">
                  <b>{crowd.name}</b>
                  <span>Cuối tuần thường {crowdPct && crowdPct >= 60 ? 'khá đông' : 'vừa phải'}</span>
                  <small className="tg-faint">Mức đông ~{crowdPct}% giờ cao điểm · tổng hợp từ {crowd.voices} đánh giá</small>
                  <div className="tg-l3__bar" aria-hidden="true"><i className="tg-l3__fill" style={{ width: `${crowdPct ?? 0}%` }} /></div>
                </div>
                <div className="tg-l3__clips" style={{ gridTemplateColumns: `repeat(${Math.min(2, crowd.videos?.length ?? 1)}, minmax(0, 120px))` }}>{(crowd.videos ?? []).slice(0, 2).map((v) => <a key={v.url} className="tg-l3__clip" href={v.url} target="_blank" rel="noreferrer"><Photo photo={crowd.photos[1] ?? crowd.photos[0]} alt="" /><span><Icon name="play" size={20} /><b>@{v.handle}</b><small>TikTok</small></span></a>)}</div>
                {crowd.quotes?.[0] && <q className="tg-l3__quote">{crowd.quotes[0].text}<small className="tg-faint"> — bình luận trên Google</small></q>}
              </div>
            </article>

            <article className="tg-l3__ch" aria-labelledby="tg-ch4">
              <p className="tg-kicker">Lịch trình <span className="tg-tag tg-tag--warn">Ví dụ minh họa</span></p>
              <h2 id="tg-ch4">Một ngày đi kịp từng điểm.</h2>
              <p className="tg-muted">Từ bình minh trên đồi đến hoàng hôn bên hồ, không vội mà vẫn kịp.</p>
              <ol className="tg-l3__day">
                {ROUTE.map((p, i) => (
                  <li key={p.id}>
                    <time>{TIMES[i]}</time>
                    <span><b>{p.name}</b>{i > 0 && <small className="tg-faint">cách điểm trước ~{km(ROUTE[i - 1], p).toFixed(1).replace('.', ',')} km</small>}</span>
                  </li>
                ))}
              </ol>
              <div className="tg-bar is-ready tg-l3__ready"><span className="tg-bar__status"><i />Đã kiểm tra</span><span className="tg-bar__stats"><span>Mỗi chặng ≤ 45 phút</span><span>Không có nơi quá đông</span></span></div>
            </article>

            <article className="tg-l3__ch" aria-labelledby="tg-ch5">
              <p className="tg-kicker">Đánh giá</p>
              <h2 id="tg-ch5">Chuyến sau hợp gu hơn chuyến này.</h2>
              <p className="tg-muted">Về rồi, kể lại vài điều. Lần sau Đà Lạt sẽ hiểu bạn hơn.</p>
              <ul className="tg-l3__rate">
                {FEEDBACK.map(([q, v]) => (
                  <li key={q}><span>{q}</span><span className="tg-l3__scale" role="img" aria-label={`${v} trên 5`}>{[1, 2, 3, 4, 5].map((n) => <i key={n} className={n <= v ? 'is-on' : ''} />)}</span></li>
                ))}
              </ul>
              <button type="button" className="tg-btn tg-btn--primary tg-l3__go" onClick={begin}>Lên lịch cho chuyến của bạn <Icon name="arrow" size={18} /></button>
            </article>
          </div>

          <div className={`tg-l3__turn ${used ? 'is-used' : ''}`}>
            <p className="tg-l3__turnhint"><span className="tg-l3__orbit" aria-hidden="true"><Icon name="turn" size={22} /><i /></span>Kéo để ngắm Đà Lạt từ mọi phía</p>
            <div className="tg-l3__turnbtns" role="group" aria-label="Xoay mô hình">
              <button type="button" aria-label="Khám phá tự do" title="Khám phá tự do" disabled={!live} onClick={explore}><Icon name="compass" size={18} /></button>
              <button type="button" aria-label="Xoay sang trái" title="Xoay sang trái" onClick={() => sceneRef.current?.turnBy(-Math.PI / 4)}><Icon name="chevronLeft" size={18} /></button>
              <button type="button" aria-label="Về góc nhìn ban đầu" title="Về góc nhìn ban đầu" onClick={() => sceneRef.current?.resetTurn()}><Icon name="refresh" size={18} /></button>
              <button type="button" aria-label="Xoay sang phải" title="Xoay sang phải" onClick={() => sceneRef.current?.turnBy(Math.PI / 4)}><Icon name="chevronRight" size={18} /></button>
            </div>
          </div>

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

          {!still && (
            <nav className="tg-l3__rail" aria-label="Các chương">
              {RAIL.map(([c, beat]) => <button key={c} type="button" aria-current={stepOf(active) === beat ? 'step' : undefined} onClick={() => toChapter(beat)}><span>{c}</span><i /></button>)}
            </nav>
          )}
          {!still && <button type="button" className="tg-l3__down" key={active} onClick={() => (active < BEATS - 1 ? toChapter(active + 1) : toId('tg-photos'))}><Icon name="chevronDown" size={18} />{HINTS[Math.min(active, BEATS - 1)]}</button>}
        </div>
      </section>

      <section className="tg-l4" id="tg-photos" aria-labelledby="tg-l4-h">
        <div className="tg-l__head"><p className="tg-kicker">Ảnh thật</p><h2 id="tg-l4-h">Nơi có thật, ảnh có thật.</h2><p className="tg-muted">Ảnh chụp từ Google Maps, ghi rõ tên nơi. Không dùng ảnh minh họa cho một địa điểm cụ thể.</p></div>
        <div className="tg-l4__grid">{mosaic.map((p, i) => <figure key={p.id} className={`tg-l4__tile t${i}`}><Photo photo={p.photos[0]} alt={p.name} sizes={i ? '(max-width: 900px) 50vw, 440px' : '(max-width: 900px) 100vw, 900px'} /><figcaption><b>{p.name}</b><span>Ảnh: Google Maps</span></figcaption></figure>)}</div>
        <button type="button" className="tg-l__more" onClick={() => toId('tg-faq')}><Icon name="chevronDown" size={18} />Còn nữa: hỏi nhanh và sắp có</button>
      </section>

      <section className="tg-l5" id="tg-faq" aria-label="Hỏi nhanh và sắp có">
        <div className="tg-faq"><h2>Hỏi nhanh</h2>{FAQ.map(([q, a], i) => <div key={q} className="tg-faq__i"><button type="button" aria-expanded={faq === i} onClick={() => setFaq(faq === i ? -1 : i)}>{q}<Icon name={faq === i ? 'minus' : 'plus'} size={18} /></button>{faq === i && <p className="tg-muted">{a}</p>}</div>)}</div>
        <aside className="tg-soon" aria-labelledby="tg-soon-h"><h2 id="tg-soon-h">Sắp có</h2>{[['compass', 'Khám phá Đà Lạt', 'Danh sách dựng sẵn theo khu và theo thời tiết'], ['bookmark', 'Nhật ký chuyến đi', 'Nhìn lại chuyến đã đi, dùng lại gu'], ['phone', 'Ứng dụng điện thoại', 'Mang lịch trình theo suốt chuyến'], ['map', 'Thêm thành phố', 'Khi trải nghiệm Đà Lạt đã hoàn thiện']].map(([ic, a, b]) => <div key={a} className="tg-soon__c"><Icon name={ic as 'map'} size={20} /><span><b>{a}</b><small className="tg-muted">{b}</small></span><span className="tg-tag tg-tag--warn">chưa mở</span></div>)}</aside>
        <button type="button" className="tg-l__more" onClick={() => toId('tg-cta')}><Icon name="chevronDown" size={18} />Còn nữa: bắt đầu chuyến của bạn</button>
      </section>

      <section className="tg-cta" id="tg-cta" aria-labelledby="tg-cta-h">
        <div className="tg-cta__img" aria-hidden="true" />
        <div className="tg-cta__in"><h2 id="tg-cta-h">Bắt đầu chuyến Đà Lạt của bạn.</h2><button type="button" className="tg-btn tg-btn--sun tg-cta__btn" onClick={begin}>Trải nghiệm đi <Icon name="arrow" size={20} /></button><p>Miễn phí, đăng nhập bằng Google.</p></div>
      </section>

      <footer className="tg-lf"><Logo size={26} dark /><span>TripGuardian Đà Lạt</span><span className="tg-lf__sp" /><span>Giờ giấc và quãng đường là ước tính; địa hình theo dữ liệu thật, cây và mái nhà chỉ là biểu tượng. Số liệu theo bản dữ liệu {stats.asOf?.split('-').reverse().join('/')}: {num(stats.places)} nơi, {num(stats.withPhotos)} nơi có ảnh thật.</span></footer>
    </div>
  )
}
