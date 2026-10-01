import gsap from 'gsap'
import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { fmtDuration, fmtTime, mapsRouteEmbed, mapsRouteLink, useSnapshot } from '../../data/store'
import { navigate } from '../../router'
import { story } from '../../scene/story'
import { GoogleMap, Icon, Page } from '../../ui/bits'
import { anchorOf, plan, rainBackup } from '../planner'
import { useTrip } from '../trip'

export function Itinerary() {
  const { trip } = useTrip()
  const { snap } = useSnapshot()
  const result = useMemo(() => plan(trip), [trip])
  const [day, setDay] = useState(0)
  const timeline = useRef<HTMLOListElement>(null)
  const anchor = anchorOf(trip)
  const d = result.days[day]
  const pool = useMemo(() => snap!.places.filter((p) => p.kind === 'experience'), [snap])

  useLayoutEffect(() => {
    if (story.reducedMotion || !timeline.current) return
    const ctx = gsap.context(() => {
      gsap.fromTo('.tl__rail', { scaleY: 0 }, { scaleY: 1, duration: 1.1, ease: 'power2.inOut', transformOrigin: 'top' })
      gsap.from('.tl__item', { opacity: 0, x: 16, duration: 0.5, stagger: 0.09, delay: 0.15, ease: 'power2.out' })
    }, timeline)
    return () => ctx.revert()
  }, [day])

  if (!result.days.some((x) => x.stops.length))
    return (
      <Page className="page--narrow">
        <div className="empty">
          <img src="/img/empty.webp" alt="" />
          <p>Chưa có lịch trình. Chọn địa điểm rồi kiểm tra khả thi trước.</p>
          <button className="btn" onClick={() => navigate('/app/shortlist')}>
            Chọn địa điểm
          </button>
        </div>
      </Page>
    )

  const stops = [anchor, ...d.stops.map((s) => s.place), anchor]
  const lastFree = [...d.stops].reverse().find((s) => !trip.locked.includes(s.place.id) && !trip.mustVisit.includes(s.place.id))

  return (
    <Page className="page--wide">
      <header className="phead phead--split">
        <div>
          <h1>Lịch trình</h1>
          <p>Giờ giấc và đường đi là ước tính. Lưu ý nằm ngay tại điểm dừng.</p>
        </div>
        <a className="btn btn--ghost" href={mapsRouteLink(stops)} target="_blank" rel="noreferrer">
          <Icon name="map" size={16} /> Mở trên Google Maps
        </a>
      </header>

      <div className="daytabs" role="tablist">
        {result.days.map((x) => (
          <button key={x.index} role="tab" aria-selected={day === x.index} className={day === x.index ? 'is-on' : ''} onClick={() => setDay(x.index)}>
            <b>Ngày {x.index + 1}</b>
            <small>{x.date.toLocaleDateString('vi-VN', { weekday: 'short', day: 'numeric', month: 'numeric' })}</small>
            <span className={`robust robust--${x.robustness === 'Vững' ? 'ok' : x.robustness === 'Khả thi' ? 'mid' : 'thin'}`}>{x.robustness}</span>
          </button>
        ))}
      </div>

      <div className="plan">
        <div className="plan__left">
          <p className="robust-line">
            <b>{d.robustness}.</b> {d.robustReason}.
          </p>
          <ol className="tl" ref={timeline}>
            <span className="tl__rail" aria-hidden="true" />
            <li className="tl__item tl__item--anchor">
              <span className="tl__time">{fmtTime(d.start)}</span>
              <span className="tl__dot" />
              <span className="tl__body">Xuất phát từ {anchor.name}</span>
            </li>
            {d.stops.map((s) => {
              const rain = rainBackup(s, pool)
              return (
                <li className="tl__item" key={s.place.id}>
                  <span className="tl__leg">
                    <Icon name="route" size={13} /> ≈{s.travelIn} phút đi
                    {s.wait > 15 && `, chờ ${s.wait} phút`}
                  </span>
                  <span className="tl__time">{fmtTime(s.arrive)}</span>
                  <span className="tl__dot tl__dot--stop" />
                  <div className="tl__body">
                    <button className="link tl__name" onClick={() => navigate(`/app/place/${encodeURIComponent(s.place.id)}`)}>
                      {s.place.name}
                    </button>
                    <small>
                      Ở lại {fmtDuration(s.leave - s.arrive)}, đến {fmtTime(s.leave)}
                    </small>
                    {s.flags.map((f) => (
                      <p className="tl__flag" key={f}>
                        <Icon name="alert" size={13} /> {f}
                      </p>
                    ))}
                    {rain && (
                      <p className="tl__backup">
                        <Icon name="rain" size={13} /> Nếu mưa: đổi sang {rain.name}, có mái che.
                      </p>
                    )}
                  </div>
                </li>
              )
            })}
            <li className="tl__item tl__item--anchor">
              <span className="tl__time">{fmtTime(d.finish)}</span>
              <span className="tl__dot" />
              <span className="tl__body">Về {anchor.name}</span>
            </li>
          </ol>
          {lastFree && d.robustness !== 'Vững' && (
            <p className="tl__backup tl__backup--late">
              <Icon name="clock" size={13} /> Bị trễ: bỏ {lastFree.place.name} trước, các nơi khác giữ nguyên.
            </p>
          )}
          <dl className="totals totals--inline">
            <div>
              <dt>Di chuyển</dt>
              <dd>≈{fmtDuration(d.travel)}</dd>
            </div>
            <div>
              <dt>Chi phí</dt>
              <dd className="muted">Chưa có thông tin</dd>
            </div>
          </dl>
        </div>
        <div className="plan__map">
          <GoogleMap src={mapsRouteEmbed(stops)} title={`Lộ trình ngày ${day + 1}`} height={460} />
        </div>
      </div>

      <div className="pfoot">
        <button className="link" onClick={() => navigate('/app/feasibility')}>
          Quay lại kiểm tra
        </button>
        <button className="btn" onClick={() => navigate('/app/feedback')}>
          Chốt kế hoạch này
        </button>
      </div>
    </Page>
  )
}
