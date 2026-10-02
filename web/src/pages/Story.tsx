import { useEffect, useRef, useState } from 'react'
import { story } from '../scene/story'

// The 37 s brand film: plays muted while on screen, with a pause control
// (auto-moving content longer than 5 s must be pausable).
export function Story() {
  const video = useRef<HTMLVideoElement>(null)
  const [paused, setPaused] = useState(true)
  const held = useRef(false) // the viewer paused it; scrolling must not restart it

  useEffect(() => {
    const v = video.current
    if (!v || story.reducedMotion) return
    const io = new IntersectionObserver(
      ([e]) => {
        if (!e.isIntersecting) v.pause()
        else if (!held.current) v.play().catch(() => {})
      },
      { threshold: 0.4 },
    )
    io.observe(v)
    return () => io.disconnect()
  }, [])

  const toggle = () => {
    const v = video.current
    if (!v) return
    held.current = !v.paused
    if (v.paused) v.play().catch(() => {})
    else v.pause()
  }

  return (
    <section className="story" aria-label="Câu chuyện TripGuardian">
      <p className="eyebrow reveal">Câu chuyện 37 giây</p>
      <h2 className="reveal">Một chuyến đi hay bắt đầu từ việc chọn đúng.</h2>
      <figure className="story__film reveal">
        <video
          ref={video}
          src="/media/story.mp4"
          poster="/media/story.jpg"
          muted
          loop
          playsInline
          preload="metadata"
          controls={story.reducedMotion}
          onPlay={() => setPaused(false)}
          onPause={() => setPaused(true)}
          aria-label="Video câu chuyện TripGuardian, không có tiếng"
        />
        {!story.reducedMotion && (
          <button className="story__toggle" onClick={toggle} aria-label={paused ? 'Phát video' : 'Tạm dừng video'}>
            {paused ? '▶' : '❚❚'}
          </button>
        )}
      </figure>
    </section>
  )
}
