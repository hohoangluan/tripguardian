import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { openCreate, openTheme, setFamiliar, useFamiliar } from '../home/dialogs'
import { MiniCalendar } from '../home/MiniCalendar'
import { Who } from '../home/Who'
import { useSnapshot } from '../../data/store'
import { matches, THEMES, type Theme } from '../home/themes'
import { toast, toggleTheme, useUi } from '../store'
import { hasTrip, useTrip } from '../trip'
import { HeartFill, Icon } from '../ui/icons'
import { useTitle } from '../ui/Shell'

export { useBegin } from '../home/dialogs'

// The pastel square behind each trend's number.
const TONES = ['#fbf6b8', '#d9f4ae', '#d2e5fb', '#fbdce5', '#e5def9']

// "Dành cho bạn": the home page of the app (ui_mock_for_design/designs/homepage). Every theme is a way into a trip.
export function Discover() {
  useTitle('Dành cho bạn')
  const { trip } = useTrip()
  const familiar = useFamiliar()
  const [q, setQ] = useState('')
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      const el = document.activeElement
      if (e.key === '/' && !(el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) && !document.querySelector('[role="dialog"]')) { e.preventDefault(); input.current?.focus() }
    }
    addEventListener('keydown', key)
    return () => removeEventListener('keydown', key)
  }, [])
  const shown = THEMES.filter((t) => matches(t, q))
  const { snap } = useSnapshot()
  const ctx = hasTrip(trip) ? trip.searchInput?.context : null
  return (
    <div className="tg-hm">
      <div className="tg-hm__center">
        <header className="tg-hm__bar">
          <form className="tg-hm__search" role="search" onSubmit={(e) => { e.preventDefault(); openCreate(q.trim()) }}>
            <Icon name="search" size={15} />
            <label className="tg-sr" htmlFor="tg-hm-q">Bạn muốn đi đâu, làm gì?</label>
            <input id="tg-hm-q" ref={input} value={q} maxLength={200} placeholder="Bạn muốn đi đâu, làm gì?" autoComplete="off" onChange={(e) => setQ(e.target.value)} />
            <kbd aria-hidden="true">/</kbd>
          </form>
        </header>

        <section className="tg-hm__hero" aria-label="Gợi ý khám phá Đà Lạt">
          <div className="tg-hm__cover">
            <img src="/img/home/cloud.jpg" alt="Bình minh giữa rừng thông và mây tại Đồi Đa Phú, Đà Lạt" />
            {snap && <span className="tg-hm__chip"><Icon name="pin" size={14} />{snap.places.length.toLocaleString('vi-VN')} địa điểm</span>}
          </div>
          <div className="tg-hm__hbody">
            <div>
              <h2>Một chuyến đi thật đúng gu</h2>
              <p>Đà Lạt · Đi đâu cũng được, miễn là đúng gu</p>
            </div>
          </div>
        </section>

        <section className="tg-hm__coll" aria-labelledby="tg-hm-coll">
          <div className="tg-hm__head">
            <div>
              <h2 id="tg-hm-coll">Gợi ý để bắt đầu</h2>
              <p>{shown.length} chủ đề cho chuyến Đà Lạt</p>
            </div>
            <span className="tg-hm__headact">
              {hasTrip(trip) && <button type="button" className="tg-hb-link" onClick={() => { setFamiliar(!familiar); toast(familiar ? 'Chuyến mới sẽ thử một hướng khác' : 'Chuyến mới sẽ theo gu quen thuộc') }}>{familiar ? 'Theo gu quen thuộc' : 'Lần này khác'}<Icon name="chevronRight" size={12} /></button>}
              <button type="button" className="tg-hm__more" onClick={() => openCreate(q.trim())}>Kể chuyến đi</button>
            </span>
          </div>
          <div className="tg-hm__cards">
            {shown.map((t, i) => (
              <article key={t.id} className={`tg-hm__card ${i === 0 ? 'is-lead' : ''}`}>
                <div className="tg-hm__ph"><button type="button" onClick={(e) => openTheme(t.id, e.currentTarget.querySelector('img'))} aria-label={`Khám phá ${t.short}`}><img src={t.photo} alt={t.alt} loading="lazy" /></button><Save t={t} /></div>
                <p>{t.category}</p>
                <button type="button" className="tg-hm__ct" onClick={(e) => openTheme(t.id, e.currentTarget.closest('.tg-hm__card')?.querySelector('img'))}>{t.short}</button>
              </article>
            ))}
            {shown.length === 0 && <p className="tg-hm__empty">Chưa có chủ đề phù hợp. Nhấn Enter để kể chuyến đi “{q}”, hoặc thử “cà phê”, “săn mây”.</p>}
          </div>
        </section>
        <footer className="tg-hm__foot"><span><Icon name="shield" size={13} />Bạn chọn nơi. Mình giúp xếp chuyến.</span><span>Đà Lạt</span></footer>
      </div>

      <aside className="tg-hm__rail" aria-label="Hồ sơ, lịch và xu hướng">
        <Who />
        <MiniCalendar start={ctx?.start_date ?? null} days={ctx?.days ?? null} />
        <div className="tg-hm__trend">
          <div className="tg-hm__thead"><h2>Top xu hướng</h2><p>Top 3 ý tưởng để bắt đầu chuyến đi</p></div>
          <ol className="tg-hm__ideas">
            {THEMES.slice(0, 3).map((t, i) => (
              <li key={t.id} className="tg-hm__idea" style={{ '--tone': TONES[i % TONES.length], '--i': i } as CSSProperties}>
                <button type="button" className="tg-hm__open" onClick={() => openTheme(t.id)}>
                  <span className="tg-hm__n" aria-hidden="true">{String(i + 1).padStart(2, '0')}</span>
                  <span className="tg-hm__tx"><b>{t.short}</b><small><Icon name={t.icon} size={14} />{t.subtitle}</small></span>
                </button>
                <Save t={t} />
              </li>
            ))}
          </ol>
        </div>
      </aside>
    </div>
  )
}

function Save({ t }: { t: Theme }) {
  const on = useUi((u) => u.savedThemes.includes(t.id))
  return <button type="button" className="tg-hb-icon tg-hb-save" aria-pressed={on} aria-label={`${on ? 'Bỏ lưu' : 'Lưu'} ${t.short}`} onClick={() => toggleTheme(t.id, t.short)}>{on ? <HeartFill size={16} /> : <Icon name="heart" size={16} />}</button>
}
