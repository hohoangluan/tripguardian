import { useEffect, useRef, useState } from 'react'
import { useAccount } from '../account'
import { dateRange } from '../lib'
import { useDecision } from '../pd/decision'
import { useUi } from '../store'
import { hasTrip, STEPS, stepOf, useTrip, type TripState } from '../trip'
import { go, Link, PlacePhoto } from '../ui/common'
import { Icon } from '../ui/icons'
import { useTitle } from '../ui/Shell'
import { useParallax } from './useParallax'

const CHIPS = ['3 ngày', 'Đi với người yêu', 'Xe máy', 'Chill', 'Cà phê', 'Săn mây', 'Ít đông']
// Each theme is a way in: its sentence becomes the first turn of Hiểu chuyến đi. Photos are real places of that theme.
const THEMES = [
  { id: 'area', area: 'Theo khu', title: 'Săn mây và cà phê Trại Mát', photo: '0x3171132a3f334c1f:0x2d831c6a07e1a1f9', prompt: 'Săn mây buổi sáng rồi ngồi cà phê khu Trại Mát' },
  { id: 'rain', area: 'Theo thời tiết', title: 'Chỗ trong nhà khi mưa', photo: '0x317113353ac6af0f:0xdaa1ac573fa04a4f', prompt: 'Những chỗ đi trong nhà được khi trời mưa' },
  { id: 'hour', area: 'Theo giờ trong ngày', title: 'Chiều muộn bên hồ', photo: '0x31711321284ed77f:0x7752634a02e162e9', prompt: 'Chiều muộn ngồi bên hồ, yên tĩnh' },
]

// A new trip: forget the current journey on this screen (it stays in Chuyến của tôi) and open Hiểu chuyến đi.
export function useBegin() {
  const { trip, dispatch } = useTrip()
  return (patch: Partial<Pick<TripState, 'startText' | 'startWith' | 'experience'>>) => {
    dispatch({ type: 'reset' })
    dispatch({ type: 'set', patch: { experience: hasTrip(trip) ? 'returning' : null, ...patch } })
    try { localStorage.removeItem('tg.tu.v1') } catch { /* nothing stored */ }
    go('/understand')
  }
}

export function Discover() {
  useTitle('Khám phá')
  const { trip } = useTrip()
  const begin = useBegin()
  const [text, setText] = useState('')
  const [ph, setPh] = useState(0)
  const heroRef = useRef<HTMLElement>(null)
  useParallax(heroRef)
  const examples = ['3 ngày ở Đà Lạt, thích chill, cà phê và săn mây…', 'Cuối tuần đi cùng bố mẹ, ít dốc, ăn nhẹ…', 'Kể tên vài quán bạn đã lưu, mình khớp từng nơi…']
  useEffect(() => { const t = setInterval(() => setPh((i) => (i + 1) % examples.length), 3600); return () => clearInterval(t) }, [examples.length])
  const submit = (t = text) => (t.trim() ? begin({ startText: t.trim(), startWith: null }) : begin({ startWith: 'nothing', startText: null }))
  const toggleChip = (c: string) => setText((t) => (t.includes(c) ? t.replace(c, '').replace(/,\s*,/g, ',').replace(/^,\s*|,\s*$/g, '').trim() : t ? `${t}, ${c}` : c))
  const returning = hasTrip(trip)
  return (
    <>
      <section className="tg-hero" ref={heroRef} aria-labelledby="tg-hero-h">
        <div className="tg-hero__img" data-depth="14" aria-hidden="true" />
        <div className="tg-hero__veil" aria-hidden="true" />
        <div className="tg-hero__in">
          <p className="tg-kicker">TripGuardian · Đà Lạt</p>
          <h1 id="tg-hero-h">Khám phá Đà Lạt,<br /><em>đúng gu của bạn.</em></h1>
          <p className="tg-hero__sub">Nói một câu, mình dựng cả chuyến. Mỗi gợi ý có lý do và có cái giá; bạn chốt, mình không chọn thay.</p>
          <form className="tg-ask-box" onSubmit={(e) => { e.preventDefault(); submit() }}>
            <Icon name="sparkle" size={22} className="tg-ask-box__ic" />
            <label className="tg-sr" htmlFor="tg-start-input">Chuyến Đà Lạt của bạn đang thế nào?</label>
            <textarea id="tg-start-input" rows={2} value={text} maxLength={1000} placeholder={examples[ph]} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() } }} />
            <button type="submit" className="tg-btn tg-btn--primary tg-ask-box__go" aria-label="Bắt đầu"><span>Bắt đầu</span><Icon name="arrow" size={20} /></button>
          </form>
          <div className="tg-hero__chips" role="group" aria-label="Gợi ý nhanh">
            {CHIPS.map((c) => <button key={c} type="button" className="tg-chip tg-chip--glass" aria-pressed={text.includes(c)} onClick={() => toggleChip(c)}>{c}</button>)}
          </div>
        </div>
      </section>

      <div className="tg-page tg-discover">
        {returning && <ActiveTrip />}
        {returning && (
          <div className="tg-seg tg-seg--solo" role="group" aria-label="Gu của bạn"><button type="button" aria-pressed="true" onClick={() => begin({ experience: 'returning', startWith: 'nothing', startText: null })}>Theo gu quen thuộc</button><button type="button" aria-pressed="false" onClick={() => begin({ experience: 'first', startWith: 'nothing', startText: null })}>Lần này khác</button></div>
        )}
        <section aria-labelledby="tg-themes-h" className="tg-sec">
          <div className="tg-sec__head"><h2 id="tg-themes-h">Khám phá Đà Lạt</h2><p className="tg-muted">Mỗi thẻ là một lối vào chuyến đi, không phải bài đọc.</p></div>
          <div className="tg-themes">
            {THEMES.map((t) => (
              <button key={t.id} type="button" className="tg-theme" onClick={() => begin({ startText: t.prompt, startWith: null })}>
                <PlacePhoto id={t.photo} className="tg-theme__ph" />
                <span className="tg-theme__shade" />
                <span className="tg-theme__txt"><em>{t.area}</em><b>{t.title}</b><span>Bắt đầu với chủ đề này</span></span>
                <span className="tg-theme__go"><Icon name="arrow" size={18} /></span>
              </button>
            ))}
          </div>
        </section>
        {returning && <p className="tg-newtrip"><Icon name="plus" size={16} /> Bắt đầu một chuyến mới<button type="button" className="tg-link" onClick={() => begin({ startWith: 'nothing', startText: null })}>Chuyến mới</button></p>}
      </div>
    </>
  )
}

function ActiveTrip() {
  const { trip } = useTrip()
  const { view, preview } = useDecision()
  const account = useAccount()
  const others = useUi((u) => u.trips.filter((id) => id !== trip.journeyId).length)
  const step = stepOf(trip)
  const ctx = trip.searchInput?.context
  const selected = view?.selected ?? trip.selected
  const conflicts = view?.feasibility.conflicts.length ?? 0
  const where = step.path
  const name = account?.kind === 'user' ? account.name.split(' ')[0] : null
  const range = dateRange(ctx?.start_date, ctx?.days)
  return (
    <section className="tg-active" aria-labelledby="tg-act-h">
      <p className="tg-active__hello"><b>{name ? `Chào ${name}.` : 'Chào bạn.'}</b> Chuyến Đà Lạt của bạn đang ở bước <b>{step.label}</b>.</p>
      <div className="tg-active__card">
        {selected[0] ? <PlacePhoto id={selected[0]} className="tg-active__ph" /> : <div className="tg-active__ph tg-hero__img" aria-hidden="true" />}
        <div className="tg-active__body">
          <span className="tg-kicker">Chuyến đang lập</span>
          <h2 id="tg-act-h">Đà Lạt{ctx?.days ? ` ${ctx.days} ngày` : ''}</h2>
          <p className="tg-mono tg-muted">{[range, ctx?.people ? `${ctx.people} người` : null, `${selected.length} nơi đã chọn`].filter(Boolean).join(' · ')}</p>
          <div className="tg-prog" role="img" aria-label={`Đang ở bước ${step.index + 1} trên 3`}>
            {STEPS.map((s, i) => <span key={s.id} className={i < step.index ? 'is-done' : i === step.index ? 'is-now' : ''}><i />{s.label}</span>)}
          </div>
          {(conflicts > 0 || ('status' in preview && preview.status === 'blocked')) && <p className="tg-active__warn"><Icon name="warn" size={15} /> Còn {Math.max(conflicts, 1)} chỗ cần chú ý trước khi xếp lịch</p>}
          <div className="tg-active__act"><button type="button" className="tg-btn tg-btn--primary" onClick={() => go(where)}>Đi tiếp <Icon name="arrow" size={18} /></button><Link to="/saved" className="tg-link">Nơi đã lưu</Link></div>
        </div>
        <div className="tg-active__side">
          <h3>Chuyến khác <span className="tg-faint">{others}</span></h3>
          <p className="tg-muted">{others ? 'Các chuyến bạn đã bắt đầu trên trình duyệt này.' : 'Chưa có chuyến nào khác.'}</p>
          <Link to="/trips" className="tg-link">Xem Chuyến của tôi</Link>
          <p className="tg-faint tg-active__obj">Ba kiểu hành trình sẽ hiện ở bước Lịch trình.</p>
        </div>
      </div>
    </section>
  )
}
