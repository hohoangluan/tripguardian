import gsap from 'gsap'
import { useLayoutEffect, useRef, useState } from 'react'
import { story } from '../scene/story'
import { useTrip } from '../user/trip'

// Role_Web_Functional_Design.md §2.1: two questions, each skippable.
const QUESTIONS = [
  {
    key: 'experience',
    title: 'Bạn đã đến Đà Lạt chưa?',
    note: 'Lần đầu thì mình dẫn từng bước. Đã từng đến thì mình bỏ qua phần cơ bản.',
    options: [
      { value: 'first', label: 'Đây là lần đầu' },
      { value: 'returning', label: 'Đã từng đến' },
    ],
  },
  {
    key: 'startWith',
    title: 'Bạn đang có gì trong tay?',
    note: 'Mình bắt đầu từ chỗ bạn đang đứng, không bắt bạn làm lại.',
    options: [
      { value: 'nothing', label: 'Chưa có ý tưởng gì' },
      { value: 'saved', label: 'Vài địa điểm đã lưu' },
      { value: 'must', label: 'Một nơi nhất định phải đến' },
      { value: 'itinerary', label: 'Một lịch trình có sẵn' },
    ],
  },
] as const

export function Start({ onHome, onDone }: { onHome: () => void; onDone: () => void }) {
  const { trip, dispatch } = useTrip()
  const [step, setStep] = useState(0)
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

  const move = (next: number, answer?: string | null) => {
    dir.current = next > step ? 1 : -1
    const commit = () => {
      if (answer !== undefined) dispatch({ type: 'set', patch: { [QUESTIONS[step].key]: answer } })
      if (next >= QUESTIONS.length) onDone()
      else setStep(next)
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
  const current = trip[q.key]

  return (
    <div className="start">
      <div className="start__top">
        <span className="start__count">
          Câu {step + 1} trên {QUESTIONS.length}
        </span>
      </div>
      <div className="stage">
        <div className="card" ref={card} key={step}>
          <h1>{q.title}</h1>
          <p className="card__note">{q.note}</p>
          <div className="choices">
            {q.options.map((o) => (
              <button key={o.value} className={`choice${current === o.value ? ' is-picked' : ''}`} onClick={() => move(step + 1, o.value)}>
                {o.label}
              </button>
            ))}
          </div>
          <div className="card__foot">
            {step > 0 ? (
              <button className="link" onClick={() => move(step - 1)}>
                Quay lại
              </button>
            ) : (
              <button className="link" onClick={onHome}>
                Về trang giới thiệu
              </button>
            )}
            <button className="link" onClick={() => move(step + 1, null)}>
              Chưa chắc, bỏ qua
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
