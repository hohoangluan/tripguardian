import { useState } from 'react'
import { DAY_VI, featureLabel, isNegative, STATUS_LABEL, TIME_VI, valueLabel } from '../../data/labels'
import { confidenceOf, DAYS, mapsEmbed, placeById, priceText, sectionOf, visible, visitRange } from '../../data/store'
import type { Place, Signal } from '../../data/types'
import { navigate } from '../../router'
import { ConfidenceTag, GoogleMap, Icon, Page, SectionArt, StatusTag, TikTokEmbed } from '../../ui/bits'
import { area } from '../search'
import { useTrip } from '../trip'

const EXPERIENCE = ['experience', 'environment']
const GROUP_OF: Record<string, string> = {
  crowd: 'environment', noise: 'environment', setting: 'environment', cleanliness: 'environment', weather_exposed: 'environment',
  parking: 'environment', outdoor_seating: 'environment', spacious: 'environment',
  service_attitude: 'service', service_quality: 'service', value_for_money: 'service', tourist_trap: 'service', wait_time: 'service',
  booking_needed: 'service', portion_size: 'service', entry_fee: 'service', vegetarian_options: 'service', cash_only: 'service', condition_change: 'service',
  rough_road_access: 'effort', steep_or_stairs: 'effort', long_walk: 'effort',
  kids: 'suitability', elderly: 'suitability',
}
const groupOf = (id: string) => GROUP_OF[id] ?? 'experience'

export function PlaceDetail({ id }: { id: string }) {
  const p = placeById(id)
  const { trip, dispatch } = useTrip()
  const [reported, setReported] = useState(false)
  if (!p) return <div className="loading">Không tìm thấy địa điểm này.</div>
  const sigs = visible(p)
  const conf = confidenceOf(p)
  const chosen = trip.selected.includes(p.id)
  const section = sectionOf(p) ?? 'sight'
  const exp = sigs.filter((s) => EXPERIENCE.includes(groupOf(s.id))).sort((a, b) => b.n - a.n)
  const service = sigs.filter((s) => groupOf(s.id) === 'service').sort((a, b) => b.n - a.n)
  const effort = sigs.filter((s) => groupOf(s.id) === 'effort')
  const suit = sigs.filter((s) => groupOf(s.id) === 'suitability')
  const [lo, hi] = visitRange(p)

  return (
    <Page className="page--detail">
      <button className="back" onClick={() => history.back()}>
        <Icon name="back" size={16} /> Quay lại
      </button>
      <header className="dhead">
        <SectionArt section={section} />
        <div className="dhead__text">
          <h1>{p.name}</h1>
          <p>
            {p.category}
            {area(p) ? `, ${area(p)}` : ''}
          </p>
          <ConfidenceTag level={conf.level} reason={conf.reason} />
        </div>
        <div className="dhead__act">
          {chosen ? (
            <button className="btn btn--chosen" onClick={() => dispatch({ type: 'unselect', id: p.id })}>
              <Icon name="check" /> Đã chọn
            </button>
          ) : (
            <button className="btn" onClick={() => dispatch({ type: 'select', id: p.id })}>
              <Icon name="plus" /> Thêm vào chuyến
            </button>
          )}
        </div>
      </header>

      <div className="dgrid">
        <section className="facts-card" aria-labelledby="facts-h">
          <h2 id="facts-h">
            Thông tin thực tế <small>theo Google</small>
          </h2>
          <Hours p={p} />
          <dl className="facts">
            <dt>Thời gian tham quan</dt>
            <dd>
              {lo}–{hi} phút <small>ước tính theo loại hình</small>
            </dd>
            {p.priceRange ? (
              <>
                <dt>Mức giá</dt>
                <dd>
                  {priceText(p.priceRange)} <small>theo {p.priceRange.reports} người báo trên Google</small>
                </dd>
              </>
            ) : (
              <>
                <dt>Mức giá</dt>
                <dd className="muted">Chưa có thông tin</dd>
              </>
            )}
            {sigs
              .filter((s) => ['entry_fee', 'booking_needed'].includes(s.id))
              .map((s) => (
                <FactRow key={s.id} s={s} />
              ))}
            <dt>Địa chỉ</dt>
            <dd>{p.address ?? <span className="muted">Chưa có thông tin</span>}</dd>
          </dl>
          <GoogleMap src={mapsEmbed(p)} title={`Bản đồ ${p.name}`} />
          {p.mapsUrl && (
            <a className="link" href={p.mapsUrl} target="_blank" rel="noreferrer">
              Mở trên Google Maps
            </a>
          )}
        </section>

        <section className="voices-card" aria-labelledby="voices-h">
          <h2 id="voices-h">
            Người đi trước kể <small>{p.voices ? `từ ${p.voices} người` : 'chưa có'}</small>
          </h2>
          {p.kind === 'inventory' && <p className="muted">Nơi này mới có thông tin cơ bản, chưa có bằng chứng trải nghiệm.</p>}
          {exp.slice(0, 8).map((s) => (
            <SignalRow key={s.id} s={s} />
          ))}
          {service.length > 0 && (
            <details className="more">
              <summary>Dịch vụ và giá trị ({service.length})</summary>
              {service.map((s) => (
                <SignalRow key={s.id} s={s} />
              ))}
            </details>
          )}
        </section>

        {p.videos.length > 0 && (
          <section className="clips" aria-labelledby="clips-h">
            <h2 id="clips-h">Clip TikTok về nơi này</h2>
            <p className="block__hint">Clip phát qua TikTok. Đây là trải nghiệm của người đăng, khác với thông tin thực tế ở trên.</p>
            <div className="clips__row">
              {p.videos.slice(0, 3).map((v) => (
                <figure key={v.id}>
                  <TikTokEmbed id={v.id} />
                  <figcaption>
                    {v.handle && <b>@{v.handle}</b>} {v.desc.slice(0, 90)}
                  </figcaption>
                </figure>
              ))}
            </div>
          </section>
        )}

        <section className="effort-card">
          <h2>Mức vận động</h2>
          {effort.length ? effort.map((s) => <SignalRow key={s.id} s={s} compact />) : <p className="muted">Chưa có thông tin.</p>}
          <h2>Hợp với ai</h2>
          {suit.length ? suit.map((s) => <SignalRow key={s.id} s={s} compact />) : <p className="muted">Chưa có thông tin.</p>}
        </section>
      </div>

      <footer className="dfoot pfoot">
        {reported ? (
          <p role="status">Đã gửi. Mình sẽ kiểm tra lại nguồn; thông tin chỉ đổi sau khi có bằng chứng mới.</p>
        ) : (
          <button className="link" onClick={() => setReported(true)}>
            <Icon name="flag" size={14} /> Báo thông tin sai
          </button>
        )}
        <button className="link" onClick={() => navigate('/app/shortlist')}>
          Về danh sách gợi ý
        </button>
      </footer>
    </Page>
  )
}

function Hours({ p }: { p: Place }) {
  const today = DAYS[new Date().getDay()]
  if (!p.hours && !p.hoursText.length)
    return (
      <p className="hours hours--none">
        <Icon name="clock" size={14} /> Giờ mở cửa: chưa có thông tin
      </p>
    )
  const rows = p.hours
    ? DAYS.map((d) => [d, (p.hours?.[d] ?? []).map(([a, b]) => `${a}–${b}`).join(', ') || 'Đóng cửa'] as const)
    : p.hoursText.map((t) => {
        const d = Object.entries(DAY_VI).find(([, v]) => t.startsWith(v))
        return [d?.[0] ?? t, d ? t.slice(d[1].length).trim() : ''] as const
      })
  return (
    <details className="hours">
      <summary>
        <Icon name="clock" size={14} /> Hôm nay: {rows.find(([d]) => d === today)?.[1] ?? 'xem lịch'}
        <small> kiểm tra {p.asOf ? new Date(p.asOf).toLocaleDateString('vi-VN') : 'gần đây'}</small>
      </summary>
      <table>
        <tbody>
          {rows.map(([d, h]) => (
            <tr key={d} className={d === today ? 'is-today' : ''}>
              <th>{DAY_VI[d] ?? d}</th>
              <td>{h}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  )
}

function FactRow({ s }: { s: Signal }) {
  return (
    <>
      <dt>{featureLabel(s.id)}</dt>
      <dd>
        {s.status === 'UNCERTAIN' ? (
          <span className="unsure">
            {Object.keys(s.distribution).map(valueLabel).join(' hay ')}
          </span>
        ) : (
          valueLabel(s.value)
        )}
        <StatusTag status={s.status} why={why(s)} />
        <small>{s.authority ? 'Google ghi' : `${s.n} người nhắc`}</small>
      </dd>
    </>
  )
}

const why = (s: Signal) =>
  s.status === 'UNCERTAIN'
    ? s.n < 2
      ? 'Mới có 1 người nhắc, chưa đủ để chắc.'
      : `Ý kiến chia ra: ${Object.entries(s.distribution)
          .map(([v, n]) => `${valueLabel(v)} ${Math.round(n)}`)
          .join(', ')}.`
    : s.status === 'OUTDATED'
      ? `Bằng chứng mới nhất cách đây ${s.freshnessDays} ngày, có thể đã thay đổi.`
      : STATUS_LABEL[s.status]

function contextLine(s: Signal) {
  const parts = Object.entries(s.byContext)
    .map(([k, d]) => {
      const total = Object.values(d).reduce((a, b) => a + b, 0)
      const share = (d[s.value] ?? 0) / (total || 1)
      return { k: k.split('=')[1], total, share }
    })
    .filter((x) => x.total >= 2)
    .sort((a, b) => b.total - a.total)
    .slice(0, 2)
  return parts.map((x) => `${TIME_VI[x.k] ?? x.k}: ${Math.round(x.share * 100)}% trong ${Math.round(x.total)} người`).join('; ')
}

function SignalRow({ s, compact }: { s: Signal; compact?: boolean }) {
  const [open, setOpen] = useState(false)
  const neg = isNegative(s.id, s.value)
  const ctx = contextLine(s)
  const trend = s.trend === 'rising' ? 'đang tăng' : s.trend === 'falling' ? 'đang giảm' : null
  return (
    <div className={`sig${neg ? ' sig--neg' : ''}${s.status !== 'VERIFIED' ? ' sig--soft' : ''}`}>
      <button className="sig__head" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span className="sig__name">
          {s.value === 'present' ? featureLabel(s.id) : `${featureLabel(s.id)}: ${valueLabel(s.value)}`}
        </span>
        <span className="sig__n">
          {s.n} người{s.mentionRate !== null && s.mentionRate < 0.05 ? ', ít được nhắc' : ''}
          {trend ? `, ${trend}` : ''}
        </span>
        {!compact && <Icon name={open ? 'back' : 'next'} size={14} className="sig__chev" />}
      </button>
      <StatusTag status={s.status} why={why(s)} />
      {ctx && <p className="sig__ctx">{ctx}</p>}
      {open && s.quotes.length > 0 && (
        <ul className="quotes">
          {s.quotes.map((q, i) => (
            <li key={i}>
              <Icon name="quote" size={14} />
              <span>{q.text}</span>
              <small>Review Google{q.date ? `, ${new Date(q.date).toLocaleDateString('vi-VN')}` : ''}</small>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
