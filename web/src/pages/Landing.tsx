import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import Lenis from 'lenis'
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { story } from '../scene/story'
import { Choose } from './Choose'
import { Story } from './Story'

gsap.registerPlugin(ScrollTrigger)

const HEADLINE = ['Đà Lạt có cả nghìn chỗ đẹp.', 'Chuyến này của bạn cần mấy chỗ?']

interface Beat {
  step: string
  title: [string, string]
  lead: string
  art: string
  card: ReactNode
  left: { t: string; d: string }
  right: { t: string; d: string }
}

// Five beats on one centred stage: headline on top, the product in the middle,
// what to notice on either side. The eye lands centre, spreads out, then reads up.
const BEATS: Beat[] = [
  {
    step: 'Hiểu chuyến đi',
    title: ['Gợi ý thì đủ rồi.', 'Khó là chọn.'],
    lead: 'TripGuardian bắt đầu từ chính chuyến đi: mấy ngày, đi với ai, đi bằng gì, nơi nào nhất định phải đến.',
    art: 'setup',
    card: (
      <>
        <div className="st-card__title" data-in>
          <b>Chuyến của bạn</b>
          <small>3 ngày · 2 người · xe máy</small>
        </div>
        <p className="st-kind" data-in>
          Quy tắc
        </p>
        <div className="st-chips" data-in>
          <span className="st-chip st-chip--rule">Rời Đà Lạt trước 15:00 ngày 3</span>
          <span className="st-chip st-chip--rule">Phải đến Đồi chè Cầu Đất</span>
        </div>
        <p className="st-kind" data-in>
          Thiên hướng
        </p>
        <div className="st-chips" data-in>
          <span className="st-chip">Thích chỗ yên</span>
          <span className="st-chip">Cà phê nhìn ra đồi</span>
          <span className="st-chip st-chip--profile">Đi chậm · từ hồ sơ của bạn</span>
        </div>
      </>
    ),
    left: { t: 'Quy tắc cứng', d: 'Kế hoạch nào phá quy tắc bị báo ngay. Chỉ bạn mới nới được.' },
    right: { t: 'Thiên hướng mềm', d: 'Chỉ để xếp ưu tiên. Điều suy ra từ hồ sơ luôn có nhãn, sửa bằng một chạm.' },
  },
  {
    step: 'Xác minh',
    title: ['Chỗ nào chưa chắc,', 'bạn thấy ngay.'],
    lead: 'Mỗi nơi được đối chiếu nhiều nguồn. Thông tin thực tế và trải nghiệm người đi trước nằm tách riêng.',
    art: 'plan',
    card: (
      <>
        <div className="st-card__title" data-in>
          <b>Hồ Tuyền Lâm</b>
          <small>Ví dụ minh họa</small>
        </div>
        <div className="st-split" data-in>
          <dl className="st-facts">
            <dt>Thời gian tham quan</dt>
            <dd className="st-mono">60–90 phút</dd>
            <dt>Phí vào cổng</dt>
            <dd>
              <span className="st-unsure">Chưa xác nhận</span>
              <small>2 nguồn ghi khác nhau</small>
            </dd>
          </dl>
          <div className="st-voice">
            <q>Sáng cuối tuần khá đông, chiều trong tuần rất yên.</q>
            <small>123 bình luận · 30 người đăng clip</small>
          </div>
        </div>
      </>
    ),
    left: { t: 'Thông tin thực tế', d: 'Giờ, giá, phí vào cổng từ Google, luôn kèm ngày kiểm tra.' },
    right: { t: 'Trải nghiệm thật', d: 'Tổng hợp review và clip của người đi trước, luôn kèm cỡ mẫu.' },
  },
  {
    step: 'So sánh và chọn',
    title: ['Năm nơi đáng đi,', 'thay vì năm mươi.'],
    lead: 'Nơi giống nhau được gom lại, kèm lời khuyên nên giữ nơi nào. Người chốt luôn là bạn.',
    art: 'shortlist',
    card: (
      <>
        <div className="st-card__title" data-in>
          <b>Đồi chè Cầu Đất</b>
          <span className="st-keep">Nên giữ</span>
        </div>
        <ul className="st-list" data-in>
          <li className="st-why">Nơi bạn muốn đến, sáng sớm có mây trôi ngang đồi</li>
          <li className="st-why">Nhiều góc chụp, ít người lúc 6 giờ</li>
          <li className="st-cost">Xa trung tâm, phải đi từ trước 6 giờ</li>
        </ul>
        <p className="st-group" data-in>
          Có 3 đồi chè giống nhau. Giữ Cầu Đất vì bạn đã chọn nơi này.
        </p>
      </>
    ),
    left: { t: 'Vì sao hợp', d: 'Mỗi lý do mở ra bình luận và clip đứng sau nó.' },
    right: { t: 'Cái giá phải trả', d: 'Xa hơn, đông hơn, dốc hơn: nói thẳng trước khi bạn chọn.' },
  },
  {
    step: 'Kiểm tra khả thi',
    title: ['Không đi kịp?', 'Biết ngay, kèm cách sửa.'],
    lead: 'Không nút nào biến kế hoạch đi không kịp thành đi được. Chỉ có những cách dời có thật.',
    art: 'feasibility',
    card: (
      <>
        <p className="st-conflict" data-in>
          Đồi chè Cầu Đất: tới nơi lúc <span className="st-mono">11:40</span>
        </p>
        <p className="st-text" data-in>
          Bạn muốn ngắm mây, cần có mặt trước 8:00. Thứ tự này còn băng qua thung lũng hai lần.
        </p>
        <div className="st-fix" data-in>
          <b>Dời Cầu Đất sang sáng ngày 2</b>
          <small>Đi thẳng từ chỗ ở, tới lúc 6:40. Bớt 35 phút đi lại.</small>
        </div>
      </>
    ),
    left: { t: 'Nói đúng chỗ sai', d: 'Tên địa điểm, quy tắc bị vi phạm, lệch bao nhiêu phút.' },
    right: { t: 'Sửa trong một chạm', d: 'Mỗi cách sửa nói trước nó đổi gì, rồi bạn mới bấm.' },
  },
  {
    step: 'Xếp lịch',
    title: ['Một lịch trình', 'bạn hiểu từng dòng.'],
    lead: 'Dòng thời gian đi cùng bản đồ. Cảnh báo nằm ngay tại điểm dừng có vấn đề.',
    art: 'discover',
    card: (
      <ol className="st-tl">
        <li data-in>
          <span className="st-mono">06:10</span>
          <b>Đồi chè Cầu Đất</b>
          <small>Ở lại 60–90 phút</small>
        </li>
        <li data-in>
          <span className="st-mono">09:30</span>
          <b>Cà phê nhìn ra đồi</b>
          <small>≈ 25 phút đi xe máy</small>
        </li>
        <li data-in>
          <span className="st-mono">11:40</span>
          <b>Hồ Tuyền Lâm</b>
          <small className="st-flag">Phí vào cổng chưa xác nhận</small>
        </li>
      </ol>
    ),
    left: { t: 'Giờ là ước tính', d: 'Di chuyển và tham quan luôn hiện dạng khoảng, không giả vờ chính xác.' },
    right: { t: 'Có sẵn phương án', d: 'Trời mưa hay bị trễ, lịch đã nói trước nên đổi chỗ nào.' },
  },
]

export function Landing({ onStart }: { onStart: () => void }) {
  const root = useRef<HTMLDivElement>(null)
  const lenis = useRef<Lenis | null>(null)
  const [beat, setBeat] = useState(0)

  // Warm the stage art so a beat never appears with an empty card.
  useEffect(() => {
    for (const b of BEATS) new Image().src = `/img/poster-${b.art}.webp`
  }, [])

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
      // Hero then the 5-beat stage: progress i/5 is where the 3D camera rests for beat i.
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
        onUpdate: (self) => setBeat(Math.min(BEATS.length - 1, Math.floor(self.progress * BEATS.length))),
      })
      if (!story.reducedMotion) {
        gsap.set('.reveal', { opacity: 0, y: 28 })
        ScrollTrigger.batch('.reveal', {
          start: 'top 88%',
          once: true,
          onEnter: (els) => gsap.to(els, { opacity: 1, y: 0, duration: 0.9, ease: 'power3.out', stagger: 0.1 }),
        })
        // The phone rises out of the mist as the hero scrolls away.
        gsap.fromTo('.hero__phone', { y: 60 }, { y: -40, ease: 'none', scrollTrigger: { trigger: '.hero', start: 'top top', end: 'bottom top', scrub: true } })
        gsap.to('.hero__tag--a', { y: -10, duration: 2.6, ease: 'sine.inOut', yoyo: true, repeat: -1 })
        gsap.to('.hero__tag--b', { y: 10, duration: 3.1, ease: 'sine.inOut', yoyo: true, repeat: -1 })
        // The one load moment: the headline condenses out of the mist.
        gsap.from('.hero__word', {
          opacity: 0,
          filter: 'blur(14px)',
          y: 18,
          duration: 1.6,
          ease: 'power3.out',
          stagger: 0.07,
          delay: 0.2,
        })
        gsap.from('.hero__after', { opacity: 0, y: 16, duration: 1, delay: 1.2, stagger: 0.12 })
      }
    }, root)

    return () => {
      ctx.revert()
      gsap.ticker.remove(tick)
      l?.destroy()
      lenis.current = null
    }
  }, [])

  // Scroll to the middle of beat i's stretch of the stage (or to the top for -1).
  const jump = (i: number) => {
    const s = document.querySelector<HTMLElement>('.st-story')
    const y = i < 0 || !s ? 0 : s.offsetTop + ((i + 0.5) / BEATS.length) * (s.offsetHeight - innerHeight)
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
              jump(-1)
            }}
          >
            TripGuardian
          </a>
          <button className="btn btn--small" onClick={onStart}>
            <span className="only-wide">Bắt đầu lên kế hoạch</span>
            <span className="only-narrow">Bắt đầu</span>
          </button>
        </header>

        <section className="hero">
          <div className="hero__copy">
            <p className="hero__eyebrow hero__after">Trợ lý chọn địa điểm cho chuyến Đà Lạt 2–4 ngày</p>
            <h1 className="hero__title">
              {HEADLINE.map((line, j) => (
                <span className={`hero__line${j ? ' hero__line--ask' : ''}`} key={j}>
                  {line.split(' ').map((w, i) => (
                    <span className="hero__word" key={i}>
                      {w}{' '}
                    </span>
                  ))}
                </span>
              ))}
            </h1>
            <p className="hero__lead hero__after">Chọn đúng nơi, hiểu vì sao chọn, và chắc rằng các nơi đó đi chung được.</p>
            <div className="hero__after hero__actions">
              <button className="btn" onClick={onStart}>
                Bắt đầu lên kế hoạch
              </button>
              <button className="hero__more" onClick={() => jump(0)}>
                Xem cách hoạt động ↓
              </button>
            </div>
          </div>
          <figure className="hero__phone hero__after" aria-hidden="true">
            <img src="/img/landing-app.webp" alt="" />
            <figcaption className="hero__tag hero__tag--a">
              <i /> 6 nơi, đi kịp
            </figcaption>
            <figcaption className="hero__tag hero__tag--b">Giờ mở cửa chưa xác nhận</figcaption>
          </figure>
        </section>

        <section className="st-story" aria-label="Cách TripGuardian hoạt động">
          <div className="st-stage">
            <Stage index={beat} />
            <nav className="st-dots" aria-label="Các bước">
              {BEATS.map((b, i) => (
                <button key={b.step} className={i === beat ? 'is-on' : i < beat ? 'is-done' : ''} aria-current={i === beat ? 'step' : undefined} onClick={() => jump(i)}>
                  <span className="st-dots__n">{i + 1}</span>
                  <span className="st-dots__label">{b.step}</span>
                </button>
              ))}
            </nav>
            {beat === BEATS.length - 1 && (
              <button className="btn st-cta" onClick={onStart}>
                Bắt đầu lên kế hoạch
              </button>
            )}
          </div>
        </section>
      </div>
      <Outro onStart={onStart} />
    </>
  )
}

function Stage({ index }: { index: number }) {
  const ref = useRef<HTMLDivElement>(null)
  const b = BEATS[index]

  // Every change of beat replays the same choreography: centre first, then the sides, then the type.
  useLayoutEffect(() => {
    if (story.reducedMotion || !ref.current) return
    const ctx = gsap.context(() => {
      gsap
        .timeline({ defaults: { ease: 'power3.out' } })
        .from('.st-card', { y: 50, scale: 0.92, opacity: 0, duration: 0.7 })
        .from('.st-card [data-in]', { y: 14, opacity: 0, duration: 0.45, stagger: 0.07 }, '-=0.35')
        .from('.st-note--l', { x: -60, opacity: 0, duration: 0.6 }, 0.25)
        .from('.st-note--r', { x: 60, opacity: 0, duration: 0.6 }, 0.25)
        .from('.st-note__line', { scaleX: 0, duration: 0.45, ease: 'power2.inOut' }, 0.55)
        .from('.st-head > *', { y: 26, opacity: 0, duration: 0.6, stagger: 0.08 }, 0.15)
    }, ref)
    return () => ctx.revert()
  }, [index])

  return (
    <div className="st-scene" ref={ref} key={index}>
      <header className="st-head">
        <p className="st-step">
          <span>{String(index + 1).padStart(2, '0')}</span> {b.step}
        </p>
        <h2>
          {b.title[0]} <em>{b.title[1]}</em>
        </h2>
        <p className="st-lead">{b.lead}</p>
      </header>
      <div className="st-row">
        <aside className="st-note st-note--l">
          <b>{b.left.t}</b>
          <p>{b.left.d}</p>
          <i className="st-note__line" />
        </aside>
        <article className="st-card">
          <img className="st-card__art" src={`/img/poster-${b.art}.webp`} alt="" />
          <div className="st-card__body">{b.card}</div>
        </article>
        <aside className="st-note st-note--r">
          <b>{b.right.t}</b>
          <p>{b.right.d}</p>
          <i className="st-note__line" />
        </aside>
      </div>
    </div>
  )
}

const HOW = [
  { t: 'Kể về chuyến đi', d: 'Mấy ngày, đi với ai, nơi nào phải đến. Câu nào chưa chắc thì bỏ qua.' },
  { t: 'Chọn từ một tập nhỏ', d: 'Mỗi nơi có lý do hợp, cái giá phải đánh đổi và clip thật của người đi trước.' },
  { t: 'Kiểm tra rồi xếp lịch', d: 'Không đi kịp thì biết ngay, kèm những cách dời có thật.' },
]

const FAQ = [
  { q: 'TripGuardian có chọn thay mình không?', a: 'Không. Mình gom lại, so sánh và cảnh báo; từng nơi trong chuyến đều do bạn chốt.' },
  { q: 'Thông tin lấy từ đâu?', a: 'Thông tin thực tế từ Google, trải nghiệm từ review và clip TikTok của người đi trước. Chỗ nào chưa chắc đều được ghi rõ là chưa chắc.' },
  { q: 'Có cần tạo tài khoản không?', a: 'Không. Bản thử lưu chuyến đi ngay trong trình duyệt của bạn.' },
  { q: 'Đang dùng được cho nơi nào?', a: 'Đà Lạt, cho chuyến 2–4 ngày, đi xe máy, ô tô hoặc xe công nghệ.' },
]

// After the 3D story: paper, a real demo of the app, and the way in.
function Outro({ onStart }: { onStart: () => void }) {
  const video = useRef<HTMLVideoElement>(null)

  // Play the demo only while it is on screen.
  useEffect(() => {
    const v = video.current
    if (!v || story.reducedMotion) return
    const io = new IntersectionObserver(([e]) => (e.isIntersecting ? v.play().catch(() => {}) : v.pause()), { threshold: 0.35 })
    io.observe(v)
    return () => io.disconnect()
  }, [])

  return (
    <div className="outro">
      <Choose />
      <Story />

      <section className="demo">
        <div className="demo__copy">
          <p className="eyebrow reveal">Xem thử 40 giây</p>
          <h2 className="reveal">Từ một đống clip đã lưu đến lịch trình đi kịp.</h2>
          <ol className="how">
            {HOW.map((h, i) => (
              <li key={h.t} className="reveal">
                <span className="how__n">{i + 1}</span>
                <div>
                  <b>{h.t}</b>
                  <p>{h.d}</p>
                </div>
              </li>
            ))}
          </ol>
          <button className="btn reveal" onClick={onStart}>
            Thử ngay
          </button>
        </div>
        <figure className="device reveal">
          <video ref={video} src="/media/demo.mp4" poster="/media/demo.jpg" muted loop playsInline preload="metadata" aria-label="Video demo TripGuardian trên điện thoại" />
        </figure>
      </section>

      <section className="faq">
        <h2 className="reveal">Hỏi nhanh</h2>
        <div className="faq__list">
          {FAQ.map((f) => (
            <details key={f.q} className="reveal">
              <summary>{f.q}</summary>
              <p>{f.a}</p>
            </details>
          ))}
        </div>
      </section>

      <section className="close">
        <img className="close__art" src="/img/poster-close.webp" alt="" loading="lazy" />
        <div className="close__copy">
          <h2 className="reveal">Đà Lạt đang chờ. Chọn đúng nơi thôi.</h2>
          <button className="btn reveal" onClick={onStart}>
            Bắt đầu lên kế hoạch
          </button>
          <p className="reveal">Không cần tài khoản.</p>
        </div>
      </section>

      <footer className="foot">
        <span className="wordmark">TripGuardian</span>
        <small>Dữ liệu từ Google Maps và TikTok · Ảnh minh họa do AI vẽ, không phải ảnh địa điểm thật</small>
      </footer>
    </div>
  )
}
