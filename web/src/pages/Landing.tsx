import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import Lenis from 'lenis'
import { useEffect, useRef, useState } from 'react'
import { story } from '../scene/story'

gsap.registerPlugin(ScrollTrigger)

const STEPS = ['Hiểu chuyến đi', 'Xác minh', 'So sánh và chọn', 'Kiểm tra khả thi', 'Xếp lịch']

const HEADLINE = ['Đà Lạt có cả nghìn chỗ đẹp.', 'Chuyến này của bạn cần mấy chỗ?']

export function Landing({ onStart }: { onStart: () => void }) {
  const root = useRef<HTMLDivElement>(null)
  const lenis = useRef<Lenis | null>(null)
  const [active, setActive] = useState(0)
  const [past, setPast] = useState(false)

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
      ScrollTrigger.create({
        trigger: root.current,
        start: 'top top',
        end: 'bottom bottom',
        onUpdate: (self) => {
          story.progress = self.progress
          setActive(Math.round(self.progress * STEPS.length))
        },
      })
      // Past the five beats the page turns to paper: the step rail steps aside.
      ScrollTrigger.create({ trigger: '.outro', start: 'top 70%', onToggle: (self) => setPast(self.isActive) })
      if (!story.reducedMotion) {
        gsap.set('.reveal', { opacity: 0, y: 28 })
        ScrollTrigger.batch('.reveal', {
          start: 'top 88%',
          once: true,
          onEnter: (els) => gsap.to(els, { opacity: 1, y: 0, duration: 0.9, ease: 'power3.out', stagger: 0.1 }),
        })
        gsap.to('.hero__phone', { y: -14, duration: 3.2, ease: 'sine.inOut', yoyo: true, repeat: -1, delay: 1.6 })
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
        gsap.from('.hero__after', { opacity: 0, duration: 1, delay: 1.3, stagger: 0.12 })
      }
    }, root)

    return () => {
      ctx.revert()
      gsap.ticker.remove(tick)
      l?.destroy()
      lenis.current = null
    }
  }, [])

  const jump = (i: number) => {
    const r = root.current!
    const y = r.offsetTop + (i / STEPS.length) * (r.scrollHeight - innerHeight)
    if (lenis.current) lenis.current.scrollTo(y, { duration: 2.2 })
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
              jump(0)
            }}
          >
            TripGuardian
          </a>
          <button className="btn btn--small" onClick={onStart}>
            <span className="only-wide">Bắt đầu lên kế hoạch</span>
            <span className="only-narrow">Bắt đầu</span>
          </button>
        </header>

        <nav className={`rail${past ? ' is-away' : ''}`} aria-label="Các bước">
          <ol>
            {STEPS.map((s, i) => (
              <li key={s} className={active === i + 1 ? 'is-active' : active > i + 1 ? 'is-done' : ''}>
                <button onClick={() => jump(i + 1)} aria-current={active === i + 1 ? 'step' : undefined}>
                  <span className="rail__n">{i + 1}</span>
                  <span className="rail__label">{s}</span>
                </button>
              </li>
            ))}
          </ol>
        </nav>

        <section className="beat hero">
          <div className="hero__copy">
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
            <p className="hero__lead hero__after">
              TripGuardian giúp bạn chọn đúng nơi cho chuyến 2–4 ngày, hiểu vì sao chọn, và chắc rằng các nơi đó đi chung được.
            </p>
            <div className="hero__after hero__actions">
              <button className="btn" onClick={onStart}>
                Bắt đầu lên kế hoạch
              </button>
              <span className="hint">Cuộn xuống để sương tan</span>
            </div>
          </div>
          <figure className="hero__phone hero__after" aria-hidden="true">
            <img src="/img/landing-app.webp" alt="" />
            <figcaption className="hero__tag hero__tag--a">
              <i /> 6 nơi, đi kịp
            </figcaption>
            <figcaption className="hero__tag hero__tag--b">Chưa xác nhận giờ mở cửa</figcaption>
          </figure>
        </section>

        <section className="beat">
          <article className="panel">
            <p className="panel__step">Bước 1, hiểu chuyến đi</p>
            <h2>Gợi ý thì đủ rồi. Khó là chọn.</h2>
            <p>
              Bạn lưu cả chục clip TikTok, mỗi clip một quán, một đồi, một góc chụp. TripGuardian bắt đầu từ chính chuyến đi: mấy ngày, đi với ai,
              đi bằng gì, nơi nào nhất định phải đến.
            </p>
            <div className="trip">
              <div className="trip__group">
                <span className="trip__kind">Quy tắc, không vượt qua</span>
                <span className="chip chip--rule">Rời Đà Lạt trước 15:00 ngày 3</span>
                <span className="chip chip--rule">Phải đến Đồi chè Cầu Đất</span>
              </div>
              <div className="trip__group">
                <span className="trip__kind">Thiên hướng, có thể nới</span>
                <span className="chip chip--lean">Thích chỗ yên</span>
                <span className="chip chip--lean">Cà phê nhìn ra đồi</span>
                <span className="chip chip--lean chip--profile">Đi chậm, từ hồ sơ của bạn</span>
              </div>
            </div>
          </article>
        </section>

        <section className="beat">
          <article className="panel">
            <p className="panel__step">Bước 2, xác minh</p>
            <h2>Chỗ nào chưa chắc, bạn thấy ngay.</h2>
            <p>
              Mỗi nơi được đối chiếu nhiều nguồn. Thông tin thực tế và trải nghiệm của người đi trước nằm tách riêng, và bằng chứng luôn cách một
              chạm.
            </p>
            <div className="evidence">
              <div className="evidence__head">
                <strong>Hồ Tuyền Lâm</strong>
                <span className="demo-note">Ví dụ minh họa</span>
              </div>
              <div className="evidence__cols">
                <dl className="facts">
                  <dt>Thời gian tham quan</dt>
                  <dd>60–90 phút</dd>
                  <dt>Phí vào cổng</dt>
                  <dd>
                    <span className="unsure">Chưa xác nhận</span>
                    <small>2 nguồn ghi khác nhau</small>
                  </dd>
                </dl>
                <div className="voices">
                  <p className="voices__quote">Sáng cuối tuần khá đông, chiều trong tuần rất yên.</p>
                  <small>Tổng hợp từ 123 bình luận của 30 người đăng clip</small>
                </div>
              </div>
            </div>
          </article>
        </section>

        <section className="beat">
          <article className="panel">
            <p className="panel__step">Bước 3, so sánh và chọn</p>
            <h2>Năm nơi đáng đi, thay vì năm mươi.</h2>
            <p>
              Các nơi giống nhau được gom lại, kèm lời khuyên nên giữ nơi nào. Mỗi gợi ý nói vì sao hợp và bạn phải đánh đổi gì. Người chốt luôn là
              bạn.
            </p>
            <div className="pick">
              <div className="pick__title">
                <strong>Đồi chè Cầu Đất</strong>
                <span className="pick__kept">Bạn đã giữ</span>
              </div>
              <p>
                <b>Vì sao hợp.</b> Nơi bạn đã muốn đến, sáng sớm có mây trôi ngang đồi.
              </p>
              <p>
                <b>Đánh đổi.</b> Xa trung tâm, phải đi từ trước 6 giờ.
              </p>
              <p className="pick__group">Có 3 đồi chè giống nhau. Giữ Cầu Đất vì bạn đã chọn nơi này.</p>
            </div>
          </article>
        </section>

        <section className="beat">
          <article className="panel">
            <p className="panel__step">Bước 4, kiểm tra khả thi</p>
            <h2>Không đi kịp thì biết ngay, kèm cách sửa.</h2>
            <div className="conflict">
              <p className="conflict__what">Đồi chè Cầu Đất: tới nơi lúc 11:40</p>
              <p>Bạn muốn ngắm mây, cần có mặt trước 8:00. Thứ tự này còn băng qua thung lũng hai lần.</p>
              <p className="conflict__fix">Cách sửa: dời Cầu Đất sang sáng ngày 2, đi thẳng từ chỗ ở.</p>
            </div>
            <p className="aside">Không có nút nào biến một kế hoạch đi không kịp thành đi được. Chỉ có những cách dời có thật.</p>
          </article>
        </section>

        <section className="beat beat--last">
          <article className="panel">
            <p className="panel__step">Bước 5, xếp lịch</p>
            <h2>Một lịch trình bạn hiểu từng dòng.</h2>
            <p>Dòng thời gian đi cùng bản đồ. Cảnh báo nằm ngay tại điểm dừng có vấn đề, không dồn xuống cuối trang.</p>
            <button className="btn" onClick={onStart}>
              Bắt đầu lên kế hoạch
            </button>
          </article>
        </section>
      </div>
      <Outro onStart={onStart} />
    </>
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
