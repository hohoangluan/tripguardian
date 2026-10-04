import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import Lenis from 'lenis'
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { featureLabel, valueLabel } from '../data/labels'
import { confidenceOf, coversOf, loadSnapshot, visible, type Cover } from '../data/store'
import type { Place, Signal, Snapshot } from '../data/types'
import { CHOSEN } from '../scene/places'
import { story } from '../scene/story'
import { Icon } from '../ui/bits'
import { area } from '../user/search'
import './landing.css'

gsap.registerPlugin(ScrollTrigger)

// docs/UI_SPEC_LANDING.md. The landing does not explain the product, it performs it: each screen is one label,
// one title of six words at most, one line at most; the 3D world and small slices of the real UI carry the rest.
// Every number comes from the real build (snapshot.json); no number, no box.

// The sample day on the itinerary screen: three stops of the 3D scene, one day.
const DAY = [
  [CHOSEN[0], '07:30'],
  [CHOSEN[1], '09:30'],
  [CHOSEN[4], '14:15'],
] as const

const BEATS = ['Chọn nơi', 'Hiểu chuyến đi', 'Bằng chứng', 'Khả thi', 'Lịch trình', 'Bắt đầu'] as const

// Claims about the place itself (what you see, how busy, how quiet): their quotes read in the claim's direction.
const SCENE_SIGNALS = ['scenic_view', 'photo_spot', 'cloud_hunting', 'flower_garden', 'crowd', 'noise', 'long_stay_chill', 'spacious', 'nature']

interface Evidence {
  place: Place
  signal: Signal
  clips: Cover[]
}

// The real place that best shows "one claim, many voices": many people, a clear signal, clip frames without people.
function pickEvidence(snap: Snapshot): Evidence | null {
  let best: (Evidence & { score: number }) | null = null
  for (const p of snap.places) {
    const clips = coversOf(p.id).filter((c) => c.kind === 'tiktok')
    if (clips.length < 3 || !p.voices) continue
    const s = visible(p)
      .filter((x) => SCENE_SIGNALS.includes(x.id) && x.status === 'VERIFIED' && x.quotes.length >= 2 && x.agreement < 0.97)
      .sort((a, b) => b.n - a.n)[0]
    if (!s) continue
    const score = s.n + p.voices / 10
    if (!best || score > best.score) best = { place: p, signal: s, clips, score }
  }
  return best
}

// Six real places for the mosaic: the most talked-about ones that have a cover without people in it.
function pickMosaic(snap: Snapshot) {
  return snap.places
    .filter((p) => p.group === 'sight' && p.kind === 'experience' && coversOf(p.id).some((c) => c.w >= c.h))
    .sort((a, b) => (b.voices ?? 0) - (a.voices ?? 0))
    .slice(0, 6)
    .map((p) => ({ place: p, cover: coversOf(p.id).find((c) => c.w >= c.h)! }))
}

export function Landing({ onStart }: { onStart: () => void }) {
  const root = useRef<HTMLDivElement>(null)
  const lenis = useRef<Lenis | null>(null)
  const [beat, setBeat] = useState(-1)
  const [snap, setSnap] = useState<Snapshot | null>(null)

  useEffect(() => {
    loadSnapshot().then(setSnap, () => {})
  }, [])
  const evidence = useMemo(() => (snap ? pickEvidence(snap) : null), [snap])

  useEffect(() => {
    story.progress = 0
    let l: Lenis | null = null
    const tick = (time: number) => l?.raf(time * 1000)
    if (!story.reducedMotion) {
      l = new Lenis({ lerp: 0.085 })
      lenis.current = l
      l.on('scroll', ScrollTrigger.update)
      gsap.ticker.add(tick)
      gsap.ticker.lagSmoothing(0)
    }
    const ctx = gsap.context(() => {
      // Hero + six screens: progress i/6 is where the camera rests for screen i.
      ScrollTrigger.create({
        trigger: root.current,
        start: 'top top',
        end: 'bottom bottom',
        onUpdate: (self) => (story.progress = self.progress),
      })
      ScrollTrigger.create({
        trigger: '.st-story',
        start: 'top top',
        end: 'bottom bottom',
        onUpdate: (self) => setBeat(self.progress <= 0 ? -1 : Math.min(BEATS.length - 1, Math.floor(self.progress * BEATS.length))),
        onLeaveBack: () => setBeat(-1),
      })
      if (!story.reducedMotion) {
        gsap.set('.reveal', { opacity: 0, y: 24 })
        ScrollTrigger.batch('.reveal', {
          start: 'top 88%',
          once: true,
          onEnter: (els) => gsap.to(els, { opacity: 1, y: 0, duration: 0.8, ease: 'power3.out', stagger: 0.08 }),
        })
        gsap.from('.hero__line', { opacity: 0, y: 22, filter: 'blur(10px)', duration: 1.3, ease: 'power3.out', stagger: 0.15, delay: 0.2 })
        gsap.from('.hero__after', { opacity: 0, y: 14, duration: 0.9, delay: 0.9 })
      }
    }, root)
    return () => {
      ctx.revert()
      gsap.ticker.remove(tick)
      l?.destroy()
      lenis.current = null
    }
  }, [])

  const to = (sel: string | number) => {
    const s = document.querySelector<HTMLElement>('.st-story')
    let y = 0
    if (typeof sel === 'number') y = sel < 0 || !s ? 0 : s.offsetTop + ((sel + 0.5) / BEATS.length) * (s.offsetHeight - innerHeight)
    else y = (document.querySelector<HTMLElement>(sel)?.offsetTop ?? 0) - 70
    if (lenis.current) lenis.current.scrollTo(y, { duration: 1.6 })
    else window.scrollTo(0, y)
  }

  return (
    <>
      <div className="landing" ref={root}>
        <header className="topbar">
          <a
            className="wordmark"
            href="/"
            onClick={(e) => {
              e.preventDefault()
              to(-1)
            }}
          >
            TripGuardian
          </a>
          <nav className="topbar__nav">
            <button className="only-wide" onClick={() => to(0)}>
              Cách hoạt động
            </button>
            <button className="only-wide" onClick={() => to('#hoi-nhanh')}>
              Hỏi nhanh
            </button>
            <button className="btn btn--small" onClick={onStart}>
              Mở ứng dụng
            </button>
          </nav>
        </header>

        <section className="hero">
          <div className="scrim">
            <h1 className="hero__title">
              <span className="hero__line">Đà Lạt có cả nghìn chỗ đẹp.</span>
              <span className="hero__line hero__line--ask">Chuyến này cần mấy chỗ?</span>
            </h1>
            <button className="btn btn--big hero__after" onClick={onStart}>
              Bắt đầu
            </button>
          </div>
          <button className="hero__down hero__after" aria-label="Xem cách hoạt động" onClick={() => to(0)}>
            <Icon name="chevron-up" size={28} />
          </button>
        </section>

        <section className="st-story" aria-label="Cách TripGuardian hoạt động">
          <div className="st-stage">
            {beat >= 0 && <Stage index={beat} total={snap?.places.length ?? null} evidence={evidence} onStart={onStart} />}
            <nav className="st-dots" aria-label="Các màn">
              {BEATS.map((b, i) => (
                <button key={b} className={i === beat ? 'is-on' : ''} aria-label={b} aria-current={i === beat ? 'step' : undefined} onClick={() => to(i)} />
              ))}
            </nav>
          </div>
        </section>
      </div>
      <Outro snap={snap} onStart={onStart} />
    </>
  )
}

// One screen of the story. Entering a screen plays its one meaningful motion; reduced motion shows the end state.
function Stage({ index, total, evidence, onStart }: { index: number; total: number | null; evidence: Evidence | null; onStart: () => void }) {
  const ref = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    if (story.reducedMotion || !ref.current) return
    const ctx = gsap.context(() => {
      const tl = gsap.timeline({ defaults: { ease: 'power3.out' } })
      tl.from('.st-head > *', { y: 22, opacity: 0, duration: 0.6, stagger: 0.08 })
      if (index === 0 && total) {
        const n = { v: 0 }
        tl.to(n, { v: total, duration: 1.2, ease: 'power2.out', onUpdate: () => ref.current?.querySelector('.st-count__from')?.replaceChildren(String(Math.round(n.v))) }, 0.1)
        tl.from('.st-count__to', { opacity: 0, x: -20, duration: 0.5 }, 1.2)
      }
      if (index === 1) {
        tl.from('.mt-stamp', { x: -260, opacity: 0, rotate: -6, duration: 0.7, stagger: 0.12 }, 0.3)
        tl.from('.mt-wish', { x: 260, opacity: 0, rotate: 6, duration: 0.7, stagger: 0.12 }, 0.45)
      }
      if (index === 2) {
        tl.from('.ev-card', { y: 30, opacity: 0, duration: 0.6 }, 0.2)
        tl.fromTo('.ev-bar i', { width: '0%' }, { width: () => (ref.current?.querySelector<HTMLElement>('.ev-bar i')?.dataset.w ?? '0') + '%', duration: 1.1, ease: 'power2.inOut' }, 0.5)
        tl.from('.ev-clip', { x: 80, opacity: 0, duration: 0.6, stagger: 0.12 }, 0.7)
        tl.from('.ev-lines path', { strokeDashoffset: 400, duration: 0.9, stagger: 0.1 }, 1.1)
      }
      if (index === 3) {
        tl.from('.fz-mini', { y: 30, opacity: 0, duration: 0.6 }, 0.2)
        tl.fromTo('.mm-fill', { width: '0%' }, { width: '118%', duration: 1, ease: 'power2.inOut' }, 0.5)
        tl.fromTo('.mm-over', { opacity: 0 }, { opacity: 1, duration: 0.3 }, 1.3)
        tl.fromTo('.mm-fix--on', { backgroundColor: 'rgba(252, 238, 241, 0)' }, { backgroundColor: '#fceef1', duration: 0.2 }, 1.9)
        tl.fromTo('.mm-fix--on .mm-radio', { backgroundColor: '#ffffff' }, { backgroundColor: '#c97890', duration: 0.2 }, 1.9)
        tl.to('.mm-fill', { width: '86%', duration: 0.9, ease: 'power3.inOut' }, 2.1)
        tl.to('.mm-over', { opacity: 0, duration: 0.3 }, 2.1)
      }
      if (index === 4) tl.from('.tl-mini li', { x: 40, opacity: 0, duration: 0.5, stagger: 0.12 }, 0.3)
      if (index === 5) tl.from('.st-cta .btn, .st-cta small', { y: 14, opacity: 0, duration: 0.5, stagger: 0.1 }, 0.4)
    }, ref)
    return () => ctx.revert()
  }, [index, total])

  return (
    <div className={`st-scene st-scene--${index}`} ref={ref} key={index}>
      {index === 0 && (
        <div className="st-head st-head--bottom scrim">
          <p className="st-count mono" aria-label={total ? `${total} nơi, còn 5` : undefined}>
            {total ? (
              <>
                <span className="st-count__from">{story.reducedMotion ? total : 0}</span>
                <span className="st-count__to">
                  <Icon name="arrow-right" size={44} /> 5
                </span>
              </>
            ) : (
              <span className="st-count__to">5</span>
            )}
          </p>
          <p className="st-lead">Chuyến này cần bấy nhiêu.</p>
        </div>
      )}

      {index === 1 && (
        <div className="st-row">
          <header className="st-head scrim">
            <p className="st-step">Hiểu chuyến đi</p>
            <h2>Luật cứng, gu mềm.</h2>
            <p className="st-lead">Điều bắt buộc đóng dấu thẳng. Điều bạn thích thì sửa được bằng một chạm.</p>
          </header>
          <article className="mini-ticket">
            <h3>Đà Lạt</h3>
            <p className="mono">3 ngày · xe máy · 2 người</p>
            <p className="mt-k">Giới hạn cứng</p>
            <div className="mt-zone">
              <span className="mt-stamp">Rời trước 15:00 ngày 3</span>
              <span className="mt-stamp">≤ 45′ mỗi chặng</span>
            </div>
            <p className="mt-k">Sở thích</p>
            <div className="mt-zone">
              <span className="mt-wish">
                cà phê view đồi <i>×</i>
              </span>
              <span className="mt-wish">
                chỗ yên tĩnh <i>×</i>
              </span>
              <span className="mt-wish mt-wish--profile">
                đi chậm <i>×</i>
                <small>từ hồ sơ của bạn</small>
              </span>
            </div>
          </article>
        </div>
      )}

      {index === 2 && (
        <div className="st-row st-row--ev">
          <header className="st-head st-head--top scrim">
            <p className="st-step">Bằng chứng</p>
            <h2>Một câu, nhiều người nói.</h2>
          </header>
          {evidence ? <EvidenceCard ev={evidence} /> : <p className="st-lead scrim">Đang tải dữ liệu thật…</p>}
        </div>
      )}

      {index === 3 && (
        <div className="st-row">
          <header className="st-head scrim">
            <p className="st-step">Khả thi</p>
            <h2>Đi được không, nói thẳng.</h2>
            <p className="st-lead">Không đi kịp thì nói ngay, kèm cách sửa và cái giá của nó.</p>
          </header>
          <article className="fz-mini">
            <p className="mm-title">{CHOSEN[2].name}</p>
            <p className="mm-rule">tới lúc 11:40, mây đã tan từ 8:00</p>
            <div className="mm-meter">
              <i className="mm-fill" />
              <i className="mm-over" />
              <span className="mm-mark" />
            </div>
            <p className="mm-legend mono">cần 11 giờ · có 9 giờ</p>
            <div className="mm-fix mm-fix--on">
              <span className="mm-radio" />
              Dời {CHOSEN[2].name} sang sáng ngày 2 <small>— bớt 35 phút đi lại</small>
            </div>
            <div className="mm-fix mm-fix--off">
              <span className="mm-radio" />
              Bỏ {CHOSEN[3].name} <small>— tiết kiệm 90 phút</small>
            </div>
            <p className="mm-note">Ví dụ minh hoạ cách màn khả thi trả lời.</p>
          </article>
        </div>
      )}

      {index === 4 && (
        <div className="st-row">
          <header className="st-head scrim">
            <p className="st-step">Lịch trình</p>
            <h2>Một ngày đi được trông thế này.</h2>
          </header>
          <ol className="tl-mini">
            {DAY.map(([c, time], i) => (
              <li key={c.name}>
                <span className="tl-mini__n">{i + 1}</span>
                <div>
                  <p>
                    <b className="mono">{time}</b> {c.name}
                  </p>
                  {i < 2 ? (
                    <small className="tl-mini__leg">
                      <Icon name="route" size={13} /> đi {i ? 40 : 25} phút · xe máy
                    </small>
                  ) : (
                    <small className="tl-mini__warn">
                      <Icon name="alert" size={13} /> Giờ mở cửa chưa xác nhận
                    </small>
                  )}
                </div>
              </li>
            ))}
            <li className="tl-mini__note">Ví dụ minh hoạ một ngày trên lịch trình.</li>
          </ol>
        </div>
      )}

      {index === 5 && (
        <div className="st-cta scrim">
          <h2>
            Đà Lạt đang chờ.
            <em>Chọn đúng nơi thôi.</em>
          </h2>
          <button className="btn btn--big" onClick={onStart}>
            Bắt đầu
          </button>
          <small>Không cần tài khoản.</small>
        </div>
      )}
    </div>
  )
}

function EvidenceCard({ ev }: { ev: Evidence }) {
  const { place, signal, clips } = ev
  const pct = Math.round(signal.agreement * 100)
  const conf = confidenceOf(place)
  const name = signal.value === 'present' ? featureLabel(signal.id) : `${featureLabel(signal.id)}: ${valueLabel(signal.value)}`
  return (
    <div className="ev">
      <article className="ev-card">
        <p className="ev-place">{place.name}</p>
        <h3>{name}</h3>
        <p className="mono ev-n">
          {pct}% trong {signal.n} người nhắc · {place.videos.length} clip
        </p>
        <div className="ev-bar">
          <i data-w={pct} style={{ width: `${pct}%` }} />
        </div>
        {signal.quotes.slice(0, 2).map((q, i) => (
          <q key={i}>{q.text.length > 90 ? q.text.slice(0, 88) + '…' : q.text}</q>
        ))}
        <p className="ev-conf">
          <span className="ev-bars" aria-hidden="true">
            {[1, 2, 3].map((i) => (
              <i key={i} className={i <= (conf.level === 'Cao' ? 3 : conf.level === 'Trung bình' ? 2 : 1) ? 'on' : ''} />
            ))}
          </span>
          Tin cậy: {conf.level}
        </p>
      </article>
      <svg className="ev-lines" viewBox="0 0 120 300" preserveAspectRatio="none" aria-hidden="true">
        {clips.slice(0, 3).map((_, i) => (
          <path key={i} d={`M0 150 C 60 150, 60 ${50 + i * 100}, 120 ${50 + i * 100}`} strokeDasharray="400" />
        ))}
      </svg>
      <div className="ev-clips">
        {clips.slice(0, 3).map((c) => (
          <a key={c.src} className="ev-clip" href={c.url} target="_blank" rel="noreferrer">
            <img src={c.src} alt="" loading="lazy" />
            <span>
              <Icon name="play" size={14} /> {c.credit}
            </span>
          </a>
        ))}
      </div>
    </div>
  )
}

const FAQ = [
  { q: 'Có thay mình quyết định không?', a: 'Không. Mình đưa ra lý do và cái giá, bạn chốt từng nơi.' },
  { q: 'Dữ liệu lấy từ đâu?', a: 'Thông tin thực tế từ Google Maps, trải nghiệm từ review và clip TikTok của người đi trước. Chỗ nào chưa chắc đều ghi là chưa chắc.' },
  { q: 'Có cần tài khoản không?', a: 'Không. Bản thử lưu chuyến đi ngay trong trình duyệt của bạn.' },
  { q: 'Có gợi ý chỗ ở không?', a: 'Không. Bạn đã có chỗ ở thì nhập vào; mình chỉ dùng nó làm điểm bắt đầu và kết thúc mỗi ngày.' },
]

const SOON = [
  { t: 'Khám phá Đà Lạt', d: 'theo khu, theo thời tiết, theo giờ trong ngày', icon: 'map' },
  { t: 'Nhật ký chuyến đi', d: 'chuyến đã đi thành gu cho lần sau', icon: 'layers' },
  { t: 'Thêm thành phố', d: 'Đà Lạt trước, rồi tới nơi khác', icon: 'pin' },
]

// After the 3D story: white paper. Real photos never sit on the mist.
function Outro({ snap, onStart }: { snap: Snapshot | null; onStart: () => void }) {
  const video = useRef<HTMLVideoElement>(null)
  const mosaic = useMemo(() => (snap ? pickMosaic(snap) : []), [snap])

  useEffect(() => {
    const v = video.current
    if (!v || story.reducedMotion) return
    const io = new IntersectionObserver(([e]) => (e.isIntersecting ? v.play().catch(() => {}) : v.pause()), { threshold: 0.35 })
    io.observe(v)
    return () => io.disconnect()
  }, [])

  return (
    <div className="outro">
      {mosaic.length > 0 && (
        <section className="mosaic">
          <header className="o-head reveal">
            <p className="o-step">Đà Lạt thật</p>
            <h2>Không ảnh minh hoạ.</h2>
            <p>Ảnh bìa mỗi nơi lấy từ ảnh và clip của chính nơi đó.</p>
          </header>
          <div className="mosaic__row">
            {mosaic.map(({ place, cover }) => (
              <figure key={place.id} className="mosaic__tile reveal">
                <img src={cover.src} alt="" loading="lazy" />
                <figcaption>
                  <b>{place.name}</b>
                  <small>{cover.kind === 'gmaps' ? `Ảnh: Google Maps · ${area(place)}` : cover.credit}</small>
                </figcaption>
              </figure>
            ))}
          </div>
        </section>
      )}

      <section className="demo">
        <header className="o-head reveal">
          <p className="o-step">Xem thử 45 giây</p>
          <h2>Từ clip đã lưu đến lịch.</h2>
        </header>
        <figure className="device reveal">
          <video ref={video} src="/media/demo.mp4" poster="/media/demo.jpg" muted loop playsInline preload="metadata" aria-label="Video demo TripGuardian trên điện thoại" />
        </figure>
      </section>

      <section className="faq" id="hoi-nhanh">
        <h2 className="reveal">Hỏi nhanh</h2>
        <div className="faq__list">
          {FAQ.map((f, i) => (
            <details key={f.q} className="reveal" open={i === 0}>
              <summary>{f.q}</summary>
              <p>{f.a}</p>
            </details>
          ))}
        </div>
      </section>

      <section className="soon-band">
        <h2 className="reveal">Sắp có</h2>
        <div className="soon-cards">
          {SOON.map((s) => (
            <article key={s.t} className="reveal">
              <Icon name={s.icon} size={44} />
              <div>
                <b>{s.t}</b>
                <p>{s.d}</p>
                <span>chưa mở</span>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="close">
        <h2 className="reveal">
          Đà Lạt đang chờ.
          <br />
          Chọn đúng nơi thôi.
        </h2>
        <button className="btn btn--big reveal" onClick={onStart}>
          Bắt đầu chuyến đi
        </button>
        <p className="reveal">Không cần tài khoản. Bỏ ngang lúc nào cũng được.</p>
      </section>

      <footer className="foot">
        <span className="wordmark">TripGuardian</span>
        <small>Dữ liệu địa điểm dựng từ nguồn công khai và clip của creator, luôn ghi nguồn.</small>
      </footer>
    </div>
  )
}
