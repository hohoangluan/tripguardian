import { useEffect, useState } from 'react'
import { json } from '../journey'
import { isGuest, useAccount } from '../account'
import { dateRange } from '../lib'
import { toast } from '../store'
import { loadToday, type TodayView } from '../today'
import { useTrip } from '../trip'
import { ArtRoute, Busy, Empty, go, Link } from '../ui/common'
import { Icon } from '../ui/icons'
import { FlowBar, Page, useTitle } from '../ui/Shell'
import { CalendarCard } from './Today'

// After "Chốt lịch" (Role_Web §2.12): the confirmed plan, the Calendar export and a way to share it. The few questions
// come only once the trip is over (the post_trip note links here), since "was the plan realistic?" needs the trip.
const QS: [string, string][] = [['fit', 'Các nơi được gợi ý hợp gu của bạn'], ['clear', 'Lý do của mỗi gợi ý dễ hiểu'], ['realistic', 'Lịch trình chạy được ngoài thực tế'], ['confident', 'Bạn đi chuyến này yên tâm hơn nhờ TripGuardian']]

const dayLabel = (date: string | null, day: number) => date ? `Ngày ${day} · ${new Date(date + 'T00:00').toLocaleDateString('vi-VN', { weekday: 'long', day: 'numeric', month: 'numeric' })}` : `Ngày ${day}`

export function Done() {
  const { trip } = useTrip()
  const id = new URLSearchParams(location.search).get('journey') ?? trip.journeyId
  const [view, setView] = useState<TodayView | 'none' | null>(null)
  useEffect(() => { if (!id) setView('none'); else loadToday(id).then(setView, () => setView('none')) }, [id])
  const over = view !== null && view !== 'none' && view.trip.status === 'done'
  useTitle(over ? 'Sau chuyến đi' : 'Kế hoạch đã chốt')
  return (
    <>
      <FlowBar step="done" />
      <Page narrow className="tg-done">
        {view === null ? <Busy text="Đang mở lịch đã chốt…" />
          : view === 'none' || !id ? <Empty art={<ArtRoute />} title="Chưa có lịch đã chốt" body="Chốt lịch ở bước Lịch trình, lịch của bạn sẽ hiện ở đây cùng nút thêm vào Google Calendar." action={<button type="button" className="tg-btn tg-btn--primary" onClick={() => go('/trips')}>Chuyến của tôi</button>} />
          : over ? <Survey id={id} />
          : <Confirmed id={id} view={view} />}
      </Page>
    </>
  )
}

function Confirmed({ id, view }: { id: string; view: TodayView }) {
  const guest = isGuest(useAccount())
  const range = dateRange(view.trip.start_date, view.days.length)
  const share = async () => {
    const lines = view.days.map((d) => `${dayLabel(d.date, d.day)}: ${d.stops.map((s) => `${s.arrive ? s.arrive + ' ' : ''}${s.name}`).join(' → ') || 'nghỉ ngơi'}`)
    const text = [`Lịch Đà Lạt${range ? ` ${range}` : ''}`, ...lines, 'Lên lịch bằng TripGuardian'].join('\n')
    try {
      if (navigator.share) { await navigator.share({ title: 'Lịch Đà Lạt', text }); return }
      await navigator.clipboard.writeText(text)
      toast('Đã chép lịch. Dán vào tin nhắn để gửi cho bạn đồng hành.')
    } catch (e) {
      if ((e as Error).name !== 'AbortError') toast('Chưa chép được lịch, bạn thử lại nhé')
    }
  }
  return (
    <>
      <div className="tg-done__hero"><span className="tg-done__seal"><Icon name="check" size={30} /></span><p className="tg-kicker">Chuyến Đà Lạt của bạn{range ? ` · ${range}` : ''}</p><h1>Kế hoạch đã chốt.</h1><p className="tg-muted">{view.trip.starts_in > 0 ? `Còn ${view.trip.starts_in} ngày nữa là đi. ` : ''}{guest ? 'Lịch chỉ giữ trong phiên dùng thử này; đăng nhập để giữ lại. ' : 'Lịch đã lưu vào tài khoản; '}trong chuyến, mở Hôm nay để xem từng điểm.</p></div>
      <section className="tg-card tg-done__plan" aria-labelledby="tg-done-plan">
        <h2 id="tg-done-plan">Lịch đã chốt</h2>
        {view.days.map((d) => (
          <div key={d.day} className="tg-done__day"><h3>{dayLabel(d.date, d.day)}</h3>
            {d.stops.length ? <ol>{d.stops.map((s) => <li key={s.id}><span className="tg-done__t">{s.arrive ?? '—'}</span>{s.name}</li>)}</ol> : <p className="tg-faint">Ngày này chưa có điểm nào, để nghỉ ngơi.</p>}
          </div>
        ))}
      </section>
      <div className="tg-done__side">
        <CalendarCard journey={id} state={view.calendar} next={`/app/done?journey=${id}`} />
        <section className="tg-card tg-done__share" aria-labelledby="tg-done-share"><h2 id="tg-done-share"><Icon name="link" size={18} /> Chia sẻ lịch</h2><p className="tg-muted">Gửi lịch dạng chữ cho người đi cùng qua tin nhắn.</p><button type="button" className="tg-btn tg-btn--soft tg-btn--sm" onClick={share}>Chia sẻ lịch</button></section>
      </div>
      <p className="tg-faint tg-done__later">Sau ngày về, TripGuardian sẽ hỏi bạn vài câu ngắn về chuyến đi.</p>
      <div className="tg-done__act"><Link to={`/today?journey=${id}`} className="tg-btn tg-btn--primary">Mở Hôm nay <Icon name="arrow" size={18} /></Link><Link to="/trips" className="tg-btn tg-btn--ghost">Chuyến của tôi</Link></div>
    </>
  )
}

function Survey({ id }: { id: string }) {
  const [score, setScore] = useState<Record<string, number>>({})
  const [more, setMore] = useState<boolean | null>(null)
  const [note, setNote] = useState('')
  const [state, setState] = useState<'form' | 'sending' | 'sent' | 'error'>('form')
  const send = async () => {
    setState('sending')
    try {
      await fetch(`/api/harness/sessions/${id}/feedback`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scores: score, more_search: more, note }) }).then(json)
      setState('sent')
    } catch {
      setState('error')
    }
  }
  if (state === 'sent') return <div className="tg-done__hero is-sent"><span className="tg-done__seal"><Icon name="heart" size={28} /></span><h1>Cảm ơn bạn.</h1><p className="tg-muted">TripGuardian đã lưu cảm nhận của chuyến này để gợi ý đúng hơn lần sau.</p><div className="tg-done__act"><Link to="/trips" className="tg-btn tg-btn--primary">Đến Chuyến của tôi <Icon name="arrow" size={18} /></Link></div></div>
  return (
    <>
      <div className="tg-done__hero"><span className="tg-done__seal"><Icon name="heart" size={28} /></span><p className="tg-kicker">Sau chuyến Đà Lạt</p><h1>Chuyến đi thế nào?</h1><p className="tg-muted">Vài câu ngắn thôi, bỏ qua được hết. Câu trả lời giúp TripGuardian gợi ý đúng hơn lần sau.</p></div>
      <form className="tg-card tg-done__form" onSubmit={(e) => { e.preventDefault(); void send() }}>
        <p className="tg-faint">Bạn đồng ý với mỗi câu dưới đây tới mức nào?</p>
        {QS.map(([k, q]) => (
          <fieldset key={k}><legend>{q}</legend>
            <div className="tg-scale" role="radiogroup" aria-label={q}>
              <div className="tg-scale__row">{[1, 2, 3, 4, 5].map((n) => <button key={n} type="button" role="radio" aria-checked={score[k] === n} aria-label={n === 1 ? '1, không đúng' : n === 5 ? '5, rất đúng' : String(n)} className={`tg-scale__b ${score[k] === n ? 'is-on' : ''}`} onClick={() => setScore((a) => ({ ...a, [k]: n }))}>{n}</button>)}</div>
              <span className="tg-faint tg-scale__ends" aria-hidden="true"><span>Không đúng</span><span>Rất đúng</span></span>
            </div>
          </fieldset>
        ))}
        <fieldset><legend>Trong chuyến, bạn có phải tự tìm thêm chỗ ngoài lịch không?</legend><div className="tg-basics__chips"><button type="button" className="tg-chip" aria-pressed={more === true} onClick={() => setMore(true)}>Có</button><button type="button" className="tg-chip" aria-pressed={more === false} onClick={() => setMore(false)}>Không</button></div></fieldset>
        <label className="tg-done__note"><span>Góp ý thêm (không bắt buộc)</span><textarea className="tg-input" rows={3} maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Điều gì TripGuardian làm chưa tốt?" /></label>
        {state === 'error' && <p className="tg-alert" role="alert"><Icon name="warn" size={15} /> Chưa gửi được, bạn thử lại nhé.</p>}
        <div className="tg-done__act"><button type="submit" className="tg-btn tg-btn--primary" disabled={state === 'sending'}>{state === 'sending' ? 'Đang gửi…' : 'Gửi'}</button><button type="button" className="tg-link tg-link--quiet" onClick={() => go('/trips')}>Bỏ qua</button></div>
      </form>
    </>
  )
}
