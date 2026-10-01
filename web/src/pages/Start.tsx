import gsap from 'gsap'
import { useLayoutEffect, useRef, useState } from 'react'
import { story } from '../scene/story'

// Role_Web_Functional_Design.md §2.1: two questions, each skippable.
const QUESTIONS = [
  {
    title: 'Bạn đã đến Đà Lạt chưa?',
    note: 'Lần đầu thì mình dẫn từng bước. Đã từng đến thì mình bỏ qua phần cơ bản.',
    options: ['Đây là lần đầu', 'Đã từng đến'],
  },
  {
    title: 'Bạn đang có gì trong tay?',
    note: 'Mình bắt đầu từ chỗ bạn đang đứng, không bắt bạn làm lại.',
    options: ['Chưa có ý tưởng gì', 'Vài địa điểm đã lưu', 'Một nơi nhất định phải đến', 'Một lịch trình có sẵn'],
  },
]

export function Start({ onHome }: { onHome: () => void }) {
  const [step, setStep] = useState(0)
  const [answers, setAnswers] = useState<string[]>([])
  const card = useRef<HTMLDivElement>(null)
  const dir = useRef(1)

  useLayoutEffect(() => {
    story.appStep = step
    const el = card.current
    if (story.reducedMotion || !el) return
    // Reverted on cleanup so a re-run never starts from a half-faded state.
    const ctx = gsap.context(() => {
      gsap.fromTo(
        el,
        { rotateY: 55 * dir.current, z: -260, opacity: 0, transformOrigin: dir.current > 0 ? '0% 50%' : '100% 50%' },
        { rotateY: 0, z: 0, opacity: 1, duration: 0.9, ease: 'power3.out' },
      )
      gsap.from('.choice', { y: 14, opacity: 0, duration: 0.5, stagger: 0.06, delay: 0.25, ease: 'power2.out' })
    }, el)
    return () => ctx.revert()
  }, [step])

  const move = (next: number, answer?: string) => {
    dir.current = next > step ? 1 : -1
    const commit = () => {
      if (answer !== undefined) setAnswers((a) => Object.assign([...a], { [step]: answer }))
      setStep(next)
    }
    if (story.reducedMotion || !card.current) return commit()
    gsap.to(card.current, {
      rotateY: -55 * dir.current,
      z: -260,
      opacity: 0,
      duration: 0.45,
      ease: 'power2.in',
      transformOrigin: dir.current > 0 ? '100% 50%' : '0% 50%',
      onComplete: commit,
    })
  }

  const q = QUESTIONS[step]

  return (
    <main className="start">
      <header className="topbar">
        <a
          className="wordmark"
          href="/"
          onClick={(e) => {
            e.preventDefault()
            onHome()
          }}
        >
          TripGuardian
        </a>
        <span className="start__count">{step < QUESTIONS.length ? `Câu ${step + 1} trên ${QUESTIONS.length}` : 'Xong phần mở đầu'}</span>
      </header>

      <div className="stage">
        <div className="card" ref={card} key={step}>
          {q ? (
            <>
              <h1>{q.title}</h1>
              <p className="card__note">{q.note}</p>
              <div className="choices">
                {q.options.map((o) => (
                  <button key={o} className={`choice${answers[step] === o ? ' is-picked' : ''}`} onClick={() => move(step + 1, o)}>
                    {o}
                  </button>
                ))}
              </div>
              <div className="card__foot">
                {step > 0 ? (
                  <button className="link" onClick={() => move(step - 1)}>
                    Quay lại
                  </button>
                ) : (
                  <span />
                )}
                <button className="link" onClick={() => move(step + 1, 'Chưa chắc')}>
                  Chưa chắc, bỏ qua
                </button>
              </div>
            </>
          ) : (
            <>
              <h1>Tiếp theo là thiết lập chuyến đi.</h1>
              <ul className="recap">
                {QUESTIONS.map((x, i) => (
                  <li key={x.title}>
                    <span>{x.title}</span>
                    <b>{answers[i] ?? 'Chưa chắc'}</b>
                  </li>
                ))}
              </ul>
              <p className="card__note">Màn thiết lập chuyến đi đang được dựng. Bản thử này dừng ở đây.</p>
              <div className="card__foot">
                <button className="link" onClick={() => move(step - 1)}>
                  Sửa câu trả lời
                </button>
                <button className="link" onClick={onHome}>
                  Về trang giới thiệu
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </main>
  )
}
