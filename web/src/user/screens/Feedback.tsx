import { useState } from 'react'
import { navigate } from '../../router'
import { Page } from '../../ui/bits'
import { LineArt } from '../../ui/LineArt'
import { useTrip } from '../trip'

// UI spec §4 Trang 10: a few short questions, all skippable. Used only to improve suggestions.
const SCALES = [
  { key: 'fit', q: 'Gợi ý có đúng gu bạn không?' },
  { key: 'why', q: 'Lý do mình đưa ra có dễ hiểu không?' },
  { key: 'real', q: 'Lịch trình có thực tế không?' },
  { key: 'confident', q: 'Bạn có tự tin hơn khi đi không?' },
]

export function Feedback() {
  const { trip, dispatch } = useTrip()
  const [sent, setSent] = useState(false)
  const set = (k: string, v: string) => dispatch({ type: 'set', patch: { feedback: { ...trip.feedback, [k]: v } } })

  return (
    <Page className="page--narrow fb">
      <header className="uhead uhead--center">
        <h1>{sent ? 'Cảm ơn bạn.' : 'Kế hoạch đã chốt.'}</h1>
        <p>{sent ? 'Phản hồi giúp mình gợi ý sát hơn cho chuyến sau.' : 'Vài câu ngắn thôi, bỏ qua được hết.'}</p>
      </header>
      <LineArt variant="band" seed={5} className="fb-art" />
      {!sent ? (
        <section className="ucard fb-form">
          {SCALES.map((x) => (
            <fieldset key={x.key}>
              <legend>{x.q}</legend>
              <div className="fb-scale">
                {['1', '2', '3', '4', '5'].map((o) => (
                  <button key={o} type="button" className={trip.feedback[x.key] === o ? 'is-on' : ''} aria-pressed={trip.feedback[x.key] === o} onClick={() => set(x.key, o)}>
                    {o}
                  </button>
                ))}
              </div>
            </fieldset>
          ))}
          <fieldset>
            <legend>Bạn có còn phải đi tìm chỗ khác không?</legend>
            <div className="fb-scale fb-scale--two">
              {['Có', 'Không'].map((o) => (
                <button key={o} type="button" className={trip.feedback.search === o ? 'is-on' : ''} aria-pressed={trip.feedback.search === o} onClick={() => set('search', o)}>
                  {o}
                </button>
              ))}
            </div>
          </fieldset>
          <textarea rows={3} placeholder="Muốn nói thêm gì cũng được" value={trip.feedback.note ?? ''} onChange={(e) => set('note', e.target.value)} aria-label="Góp ý thêm" />
          <div className="fb-foot">
            <button className="btn" onClick={() => setSent(true)}>
              Gửi
            </button>
            <button className="link" onClick={() => navigate('/app')}>
              Bỏ qua
            </button>
          </div>
        </section>
      ) : (
        <div className="fb-done">
          <button className="btn" onClick={() => navigate('/app/plan')}>
            Xem lại lịch trình
          </button>
          <button className="link" onClick={() => navigate('/app')}>
            Về trang chủ
          </button>
        </div>
      )}
      <p className="hint fb-note">Phản hồi chỉ dùng để cải thiện gợi ý.</p>
    </Page>
  )
}
