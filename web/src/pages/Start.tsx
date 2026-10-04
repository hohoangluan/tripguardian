import { useState } from 'react'
import { Icon } from '../ui/bits'
import { hasTrip, useTrip } from '../user/trip'

// UI spec §4 Trang 2. One free box is the strongest thing on the page: type or paste anything (a TikTok / Maps
// link, saved places, a plan, one sentence). Four big cards for someone who does not know what to type.
// No "have you been to Đà Lạt" question: the starting state is read from what the user gives.
const STARTS = [
  { value: 'nothing', label: 'Chưa có ý tưởng gì', note: 'Gợi ý từ đầu theo sở thích và thời gian của bạn.', icon: 'spark' },
  { value: 'saved', label: 'Vài địa điểm đã lưu', note: 'Bạn có sẵn vài nơi, mình giúp sắp cho hợp lý.', icon: 'flag' },
  { value: 'must', label: 'Một nơi nhất định phải đến', note: 'Xây chuyến đi quanh nơi không thể bỏ qua.', icon: 'pin' },
  { value: 'itinerary', label: 'Một lịch trình có sẵn', note: 'Mình kiểm tra, chỉ ra chỗ vướng và cách sửa.', icon: 'route' },
] as const

export function Start({ onHome, onDone }: { onHome: () => void; onDone: () => void }) {
  const { trip, dispatch } = useTrip()
  const [text, setText] = useState('')
  const go = (patch: { startWith?: string | null; startText?: string | null; experience?: 'first' | 'returning' | null }) => {
    dispatch({ type: 'set', patch })
    onDone()
  }
  const returning = trip.experience === 'returning' || hasTrip(trip)

  return (
    <div className="start2">
      <header className="uhead uhead--center">
        <h1>Chuyến Đà Lạt của bạn đang thế nào?</h1>
        <p>Gõ tự nhiên, hoặc dán link TikTok, Google Maps, danh sách đã lưu. Mình bắt đầu từ chỗ bạn đang đứng.</p>
      </header>

      <form
        className="start2__box"
        onSubmit={(e) => {
          e.preventDefault()
          if (text.trim()) go({ startText: text.trim(), startWith: null })
        }}
      >
        <textarea
          rows={3}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              if (text.trim()) go({ startText: text.trim(), startWith: null })
            }
          }}
          placeholder="Ví dụ: 3 ngày cuối tháng 11, đi với người yêu, xe máy. Muốn đồi chè Cầu Đất và vài quán cà phê view đồi."
          aria-label="Kể về chuyến đi"
        />
        <div className="start2__row">
          <span className="hint">Enter để bắt đầu · Shift+Enter xuống dòng</span>
          <button className="btn" disabled={!text.trim()}>
            Bắt đầu <Icon name="arrow-right" size={16} />
          </button>
        </div>
      </form>

      <p className="start2__or">
        <span>chưa biết gõ gì? chọn một</span>
      </p>
      <div className="start2__cards">
        {STARTS.map((s) => (
          <button key={s.value} className="start2__card" onClick={() => go({ startWith: s.value, startText: null })}>
            <Icon name={s.icon} size={30} />
            <b>{s.label}</b>
            <span>{s.note}</span>
          </button>
        ))}
      </div>

      {returning && (
        <div className="start2__back">
          <span>Bạn đã đi Đà Lạt với mình trước đây</span>
          <button className="chip" onClick={() => go({ experience: 'returning', startWith: 'nothing', startText: null })}>
            Theo gu quen thuộc
          </button>
          <button className="chip" onClick={() => go({ experience: 'first', startWith: 'nothing', startText: null })}>
            Lần này khác
          </button>
        </div>
      )}

      <button className="link start2__home" onClick={onHome}>
        Về trang giới thiệu
      </button>
    </div>
  )
}
