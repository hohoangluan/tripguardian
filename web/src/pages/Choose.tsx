import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { story } from '../scene/story'

gsap.registerPlugin(ScrollTrigger)

const MiniatureCanvas = lazy(() => import('../scene/miniature/Miniature'))

const STEPS = [
  { t: 'Bạn lưu cả chục nơi.', d: 'Chỗ nào trong clip cũng đẹp. Nhưng chưa biết chỗ nào hợp chuyến này.' },
  { t: 'Giữ lại nơi hợp gu.', d: 'Mỗi nơi có lý do hợp và cái giá phải đánh đổi. Nơi không hợp thì để sang một bên.' },
  { t: 'Rồi mới nối thành lộ trình.', d: 'Chọn xong, TripGuardian mới kiểm tra đi kịp và xếp lịch.' },
]

// Where the mist ends and the paper begins: a tabletop Đà Lạt that sorts
// itself as you scroll. Pinned by CSS sticky; the scroll only drives progress.
export function Choose() {
  const root = useRef<HTMLElement>(null)
  const progress = useRef(story.reducedMotion ? 1 : 0)
  const [step, setStep] = useState(story.reducedMotion ? STEPS.length - 1 : 0)

  useEffect(() => {
    if (story.reducedMotion) return
    const st = ScrollTrigger.create({
      trigger: root.current,
      start: 'top top',
      end: 'bottom bottom',
      onUpdate: (self) => {
        // Hold the last beat for the final stretch so the finished route can be read.
        progress.current = Math.min(1, self.progress / 0.85)
        setStep(Math.min(STEPS.length - 1, Math.floor(progress.current * STEPS.length)))
      },
    })
    return () => st.kill()
  }, [])

  return (
    <section className="choose" ref={root} aria-label="Chọn trước, xếp lịch sau">
      <div className="choose__stage">
        <div className="choose__copy">
          <p className="eyebrow">Chọn trước, xếp lịch sau</p>
          <ol className="choose__steps">
            {STEPS.map((s, i) => (
              <li key={s.t} className={i === step ? 'is-on' : i < step ? 'is-done' : ''} aria-current={i === step ? 'step' : undefined}>
                <h2>{s.t}</h2>
                <p>{s.d}</p>
              </li>
            ))}
          </ol>
          <small className="choose__note">Sa bàn minh họa, không phải bản đồ thật.</small>
        </div>
        <Suspense fallback={<div className="choose__canvas" />}>
          <MiniatureCanvas progress={progress} />
        </Suspense>
      </div>
    </section>
  )
}
