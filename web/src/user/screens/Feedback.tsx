import { useState } from 'react'
import { navigate } from '../../router'
import { Chip, Page } from '../../ui/bits'
import { useTrip } from '../trip'

// §2.12: short, optional.
const QUESTIONS = [
  { key: 'fit', q: 'Các gợi ý có đúng gu bạn không?' },
  { key: 'why', q: 'Lý do vì sao chọn có dễ hiểu không?' },
  { key: 'real', q: 'Lịch trình có thực tế không?' },
  { key: 'search', q: 'Bạn còn phải tìm thêm chỗ khác không?', options: ['Không cần', 'Một ít', 'Nhiều'] },
  { key: 'confident', q: 'Bạn có tự tin hơn với chuyến đi không?' },
]

export function Feedback() {
  const { trip, dispatch } = useTrip()
  const [sent, setSent] = useState(false)
  const set = (k: string, v: string) => dispatch({ type: 'set', patch: { feedback: { ...trip.feedback, [k]: v } } })

  return (
    <Page className="page--narrow">
      <header className="phead">
        <h1>{sent ? 'Cảm ơn bạn.' : 'Kế hoạch đã chốt.'}</h1>
        <p>{sent ? 'Phản hồi giúp mình gợi ý sát hơn cho chuyến sau.' : 'Nếu có 20 giây, cho mình biết chuyến này thế nào. Không bắt buộc.'}</p>
      </header>
      {!sent && (
        <section className="block">
          {QUESTIONS.map((x) => (
            <div className="fbq" key={x.key}>
              <p>{x.q}</p>
              <div className="chips">
                {(x.options ?? ['Có', 'Tạm', 'Không']).map((o) => (
                  <Chip key={o} on={trip.feedback[x.key] === o} onClick={() => set(x.key, o)}>
                    {o}
                  </Chip>
                ))}
              </div>
            </div>
          ))}
          <div className="pfoot">
            <button className="link" onClick={() => navigate('/app/plan')}>
              Xem lại lịch trình
            </button>
            <button className="btn" onClick={() => setSent(true)}>
              Gửi phản hồi
            </button>
          </div>
        </section>
      )}
      {sent && (
        <button className="btn" onClick={() => navigate('/app/plan')}>
          Về lịch trình
        </button>
      )}
    </Page>
  )
}
