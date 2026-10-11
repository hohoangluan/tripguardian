import { useState } from 'react'
import { json } from '../journey'
import { useTrip } from '../trip'
import { go, Link } from '../ui/common'
import { Icon } from '../ui/icons'
import { FlowBar, Page, useTitle } from '../ui/Shell'

const QS: [string, string][] = [['fit', 'Gợi ý có đúng gu của bạn?'], ['clear', 'Lý do dễ hiểu?'], ['realistic', 'Lịch có thực tế?'], ['confident', 'Bạn tự tin hơn về chuyến đi?']]

export function Done() {
  useTitle('Phản hồi')
  const { trip } = useTrip()
  const [score, setScore] = useState<Record<string, number>>({})
  const [more, setMore] = useState<boolean | null>(null)
  const [note, setNote] = useState('')
  const [state, setState] = useState<'form' | 'sending' | 'sent' | 'error'>('form')
  const send = async () => {
    if (!trip.journeyId) return setState('sent')
    setState('sending')
    try {
      await fetch(`/api/harness/sessions/${trip.journeyId}/feedback`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scores: score, more_search: more, note }) }).then(json)
      setState('sent')
    } catch {
      setState('error')
    }
  }
  return (
    <>
      <FlowBar step="done" />
      <Page narrow className="tg-done">
        {state !== 'sent' ? (
          <>
            <div className="tg-done__hero"><span className="tg-done__seal"><Icon name="check" size={30} /></span><p className="tg-kicker">Chuyến Đà Lạt của bạn</p><h1>Kế hoạch đã chốt.</h1><p className="tg-muted">Vài câu ngắn thôi, bỏ qua được hết. Câu trả lời giúp mình gợi ý đúng hơn lần sau.</p></div>
            <form className="tg-card tg-done__form" onSubmit={(e) => { e.preventDefault(); send() }}>
              {QS.map(([k, q]) => (
                <fieldset key={k}><legend>{q}</legend>
                  <div className="tg-scale" role="radiogroup" aria-label={q}>{[1, 2, 3, 4, 5].map((n) => <button key={n} type="button" role="radio" aria-checked={score[k] === n} className={`tg-scale__b ${score[k] === n ? 'is-on' : ''}`} onClick={() => setScore((a) => ({ ...a, [k]: n }))}>{n}</button>)}<span className="tg-faint tg-scale__ends"><span>Chưa đúng</span><span>Rất đúng</span></span></div>
                </fieldset>
              ))}
              <fieldset><legend>Bạn còn phải tìm chỗ khác nữa không?</legend><div className="tg-basics__chips"><button type="button" className="tg-chip" aria-pressed={more === true} onClick={() => setMore(true)}>Có</button><button type="button" className="tg-chip" aria-pressed={more === false} onClick={() => setMore(false)}>Không</button></div></fieldset>
              <label className="tg-done__note"><span>Góp ý thêm (không bắt buộc)</span><textarea className="tg-input" rows={3} maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Điều gì mình làm chưa tốt?" /></label>
              {state === 'error' && <p className="tg-alert" role="alert"><Icon name="warn" size={15} /> Chưa gửi được, bạn thử lại nhé.</p>}
              <div className="tg-done__act"><button type="submit" className="tg-btn tg-btn--primary" disabled={state === 'sending'}>{state === 'sending' ? 'Đang gửi…' : 'Gửi'}</button><button type="button" className="tg-link tg-link--quiet" onClick={() => go('/trips')}>Bỏ qua</button></div>
            </form>
          </>
        ) : (
          <div className="tg-done__hero is-sent"><span className="tg-done__seal"><Icon name="heart" size={28} /></span><h1>Cảm ơn bạn.</h1><p className="tg-muted">Mình đã lưu phản hồi của chuyến này để gợi ý đúng hơn.</p><div className="tg-done__act"><Link to="/plan" className="tg-btn tg-btn--ghost">Xem lại lịch trình</Link><Link to="/trips" className="tg-btn tg-btn--primary">Đến Chuyến của tôi <Icon name="arrow" size={18} /></Link></div></div>
        )}
      </Page>
    </>
  )
}
