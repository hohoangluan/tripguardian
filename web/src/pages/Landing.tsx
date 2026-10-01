import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import Lenis from 'lenis'
import { useEffect, useRef, useState } from 'react'
import { story } from '../scene/story'

gsap.registerPlugin(ScrollTrigger)

const STEPS = ['Hiểu chuyến đi', 'Xác minh', 'So sánh và chọn', 'Kiểm tra khả thi', 'Xếp lịch']

const HEADLINE = 'Đà Lạt có cả nghìn chỗ đẹp. Chuyến này của bạn cần mấy chỗ?'

export function Landing({ onStart }: { onStart: () => void }) {
  const root = useRef<HTMLDivElement>(null)
  const lenis = useRef<Lenis | null>(null)
  const [active, setActive] = useState(0)

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
      if (!story.reducedMotion) {
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
    const y = (i / STEPS.length) * (document.documentElement.scrollHeight - innerHeight)
    if (lenis.current) lenis.current.scrollTo(y, { duration: 2.2 })
    else window.scrollTo(0, y)
  }

  return (
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

      <nav className="rail" aria-label="Các bước">
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
            {HEADLINE.split(' ').map((w, i) => (
              <span className="hero__word" key={i}>
                {w}{' '}
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
  )
}
