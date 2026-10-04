import { useState } from 'react'
import { DAY_VI, featureLabel, isNegative, STATUS_LABEL, TIME_VI, valueLabel } from '../../data/labels'
import { confidenceOf, coversOf, DAYS, mapsEmbed, placeById, priceText, visible, visitRange } from '../../data/store'
import type { Place, Signal } from '../../data/types'
import { navigate } from '../../router'
import { Clip, ConfidenceTag, CoverStrip, GoogleMap, Icon, Page, StatusTag } from '../../ui/bits'
import { LineArt } from '../../ui/LineArt'
import { useDecision } from '../pd/decision'
import { area } from '../search'
import { useTrip } from '../trip'

// UI spec §4 Trang 5: every claim one tap from its evidence; facts (Google) and lived experience (people, clips)
// are two kinds of truth and look different.

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
const asOf = (p: Place) => (p.asOf ? new Date(p.asOf).toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit' }) : null)

export function PlaceDetail({ id }: { id: string }) {
  const p = placeById(id)
  const { trip, dispatch } = useTrip()
  const { view, act, busy } = useDecision()
  const [reported, setReported] = useState(false)
  if (!p) return <div className="loading loading--error">Không tìm thấy địa điểm này.</div>
  const sigs = visible(p)
  const conf = confidenceOf(p)
  // With a curation session the backend holds the list; without one the trip keeps it locally.
  const chosen = view ? view.selected.includes(p.id) : trip.selected.includes(p.id)
  const locked = view ? view.locked.includes(p.id) : trip.locked.includes(p.id)
  const select = () => (view ? act({ type: 'select', place_id: p.id }) : dispatch({ type: 'select', id: p.id }))
  const drop = () => (view ? act({ type: 'drop', place_id: p.id }) : dispatch({ type: 'unselect', id: p.id }))
  const lock = () => (view ? act({ type: locked ? 'unlock' : 'lock', place_id: p.id }) : dispatch({ type: 'lock', id: p.id }))
  const exp = sigs.filter((s) => EXPERIENCE.includes(groupOf(s.id))).sort((a, b) => b.n - a.n)
  const service = sigs.filter((s) => groupOf(s.id) === 'service').sort((a, b) => b.n - a.n)
  const effort = sigs.filter((s) => groupOf(s.id) === 'effort')
  const suit = sigs.filter((s) => groupOf(s.id) === 'suitability')
  const [lo, hi] = visitRange(p)
  const checked = asOf(p)

  return (
    <Page>
      <button className="link pd-back" onClick={() => history.back()}>
        <Icon name="back" size={15} /> Quay lại
      </button>
      <header className="pd-head">
        <div>
          <h1>{p.name}</h1>
          <p>
            {[p.category, area(p)].filter(Boolean).join(' · ')}
            <span className="pd-head__conf">
              <ConfidenceTag level={conf.level} reason={conf.reason} />
            </span>
          </p>
        </div>
        <div className="pd-head__act">
          {chosen ? (
            <button className="btn btn--chosen" disabled={busy} onClick={drop}>
              <Icon name="check" size={16} /> Đã chọn
            </button>
          ) : (
            <button className="btn" disabled={busy} onClick={select}>
              <Icon name="plus" size={16} /> Thêm vào danh sách chọn
            </button>
          )}
          <button className="btn btn--ghost btn--small" aria-pressed={locked} disabled={busy} onClick={lock}>
            <Icon name={locked ? 'lock' : 'unlock'} size={14} /> {locked ? 'Đã khóa' : 'Khóa'}
          </button>
          {chosen && (
            <button className="btn btn--ghost btn--small" disabled={busy} onClick={drop}>
              Bỏ
            </button>
          )}
        </div>
      </header>

      <div className="pd-banner"><CoverStrip id={p.id} fallback={<LineArt variant="band" seed={p.name.length} />} /></div>

      <div className="pd-grid">
        <section className="pd-facts ucard" aria-labelledby="facts-h">
          <h2 className="utitle" id="facts-h">
            Thông tin thực tế
          </h2>
          <table className="facts">
            <tbody>
              <Hours p={p} />
              <tr>
                <th>Thời gian tham quan</th>
                <td className="mono">
                  {lo}–{hi} phút
                </td>
                <td className="source">ước tính theo loại hình</td>
              </tr>
              <tr>
                <th>Giá</th>
                {p.priceRange ? (
                  <>
                    <td className="mono">{priceText(p.priceRange)}</td>
                    <td className="source">nguồn: Google · {p.priceRange.reports} người báo</td>
                  </>
                ) : (
                  <>
                    <td className="unknown">Chưa có thông tin</td>
                    <td />
                  </>
                )}
              </tr>
              {sigs
                .filter((s) => ['entry_fee', 'booking_needed'].includes(s.id))
                .map((s) => (
                  <FactRow key={s.id} s={s} />
                ))}
              <tr>
                <th>Địa chỉ</th>
                <td>{p.address ?? <span className="unknown">Chưa có thông tin</span>}</td>
                <td className="source">nguồn: Google{checked ? ` · kiểm tra ${checked}` : ''}</td>
              </tr>
            </tbody>
          </table>
          <GoogleMap src={mapsEmbed(p)} title={`Bản đồ ${p.name}`} height={300} />
          {p.mapsUrl && (
            <a className="link pd-maps" href={p.mapsUrl} target="_blank" rel="noreferrer">
              Mở trên Google Maps
            </a>
          )}
        </section>

        <div className="pd-right">
          <section className="pd-voices" aria-labelledby="voices-h">
            <h2 className="utitle" id="voices-h">
              Trải nghiệm <small>{p.voices ? `từ ${p.voices} người đã viết` : 'chưa có'}</small>
            </h2>
            <div className="pd-voices__body">
              <div className="pd-signals">
                {p.kind === 'inventory' && <p className="unknown">Nơi này mới có thông tin cơ bản, chưa có bằng chứng trải nghiệm.</p>}
                {exp.slice(0, 6).map((s) => (
                  <SignalRow key={s.id} s={s} />
                ))}
                {service.length > 0 && (
                  <details className="pd-more">
                    <summary>Dịch vụ và giá trị ({service.length})</summary>
                    {service.map((s) => (
                      <SignalRow key={s.id} s={s} />
                    ))}
                  </details>
                )}
              </div>
              {p.videos.length > 0 && (
                <div className="pd-clips" aria-label="Clip người đi trước quay">
                  {p.videos.slice(0, 4).map((v) => (
                    <Clip key={v.id} video={v} poster={coversOf(p.id).find((c) => c.src.includes(`/${v.id}/`))?.src} />
                  ))}
                  <p className="hint">Trải nghiệm của người đăng. Tên tác giả dẫn về clip gốc.</p>
                </div>
              )}
            </div>
          </section>

          <div className="pd-small">
            <section className="ucard">
              <h2 className="utitle">Mức vận động</h2>
              {effort.length ? effort.map((s) => <SignalRow key={s.id} s={s} compact />) : <p className="unknown">Chưa có thông tin</p>}
            </section>
            <section className="ucard">
              <h2 className="utitle">Hợp với ai</h2>
              {suit.length ? (
                <div className="chips pd-who">
                  {suit.map((s) => (
                    <span key={s.id} className={`chip${isNegative(s.id, s.value) ? ' is-no' : ''}`} title={`${s.n} người nhắc`}>
                      {featureLabel(s.id)}
                      {s.value !== 'present' && s.value !== 'suitable' ? `: ${valueLabel(s.value)}` : ''}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="unknown">Chưa có thông tin</p>
              )}
            </section>
          </div>
        </div>
      </div>

      <footer className="pfoot">
        {reported ? (
          <p role="status" className="hint">
            Đã gửi. Mình sẽ kiểm tra lại nguồn; thông tin chỉ đổi sau khi có bằng chứng mới.
          </p>
        ) : (
          <button className="btn btn--ghost btn--small" onClick={() => setReported(true)}>
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
  const [open, setOpen] = useState(false)
  const today = DAYS[new Date().getDay()]
  const checked = asOf(p)
  if (!p.hours && !p.hoursText.length)
    return (
      <tr>
        <th>Giờ mở cửa</th>
        <td className="unknown">Chưa có thông tin</td>
        <td />
      </tr>
    )
  const rows = p.hours
    ? DAYS.map((d) => [d, (p.hours?.[d] ?? []).map(([a, b]) => `${a}–${b}`).join(', ') || 'Đóng cửa'] as const)
    : p.hoursText.map((t) => {
        const d = Object.entries(DAY_VI).find(([, v]) => t.startsWith(v))
        return [d?.[0] ?? t, d ? t.slice(d[1].length).trim() : ''] as const
      })
  return (
    <>
      <tr>
        <th>Giờ mở cửa</th>
        <td>
          <span className="mono">Hôm nay {rows.find(([d]) => d === today)?.[1] ?? '—'}</span>{' '}
          <button className="link pd-week" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
            {open ? 'Thu gọn' : 'Cả tuần'}
          </button>
          {open && (
            <table className="pd-hours">
              <tbody>
                {rows.map(([d, h]) => (
                  <tr key={d} className={d === today ? 'is-today' : ''}>
                    <th>{DAY_VI[d] ?? d}</th>
                    <td className="mono">{h}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </td>
        <td className="source">nguồn: Google{checked ? ` · kiểm tra ${checked}` : ''}</td>
      </tr>
    </>
  )
}

function FactRow({ s }: { s: Signal }) {
  return (
    <tr>
      <th>{featureLabel(s.id)}</th>
      <td>
        {s.status === 'UNCERTAIN' ? <span className="unsure">{Object.keys(s.distribution).map(valueLabel).join(' hay ')}</span> : valueLabel(s.value)}
        <StatusTag status={s.status} why={why(s)} />
      </td>
      <td className="source">{s.authority ? 'nguồn: Google' : `${s.n} người nhắc`}</td>
    </tr>
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
      ? `Có thể đã thay đổi: bằng chứng mới nhất cách đây ${s.freshnessDays} ngày.`
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
  return parts.map((x) => `${TIME_VI[x.k] ?? x.k}: ${Math.round(x.share * 100)}% trong ${Math.round(x.total)} người`).join(' · ')
}

// A signal: trend + context + sample size, and its quotes one tap away (UI spec §6).
function SignalRow({ s, compact }: { s: Signal; compact?: boolean }) {
  const [open, setOpen] = useState(false)
  const neg = isNegative(s.id, s.value)
  const ctx = contextLine(s)
  const pct = Math.round(s.agreement * 100)
  const trend = s.trend === 'rising' ? 'đang tăng' : s.trend === 'falling' ? 'đang giảm' : null
  const name = s.value === 'present' ? featureLabel(s.id) : `${featureLabel(s.id)}: ${valueLabel(s.value)}`
  if (compact)
    return (
      <div className={`sig sig--compact${neg ? ' sig--neg' : ''}`}>
        <span>{name}</span>
        <small className="mono">{s.n} người nhắc</small>
        <StatusTag status={s.status} why={why(s)} />
      </div>
    )
  return (
    <div className={`sig${neg ? ' sig--neg' : ''}`}>
      <button className="sig__head" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span className="sig__name">{name}</span>
        <Icon name={open ? 'chevron-up' : 'next'} size={14} />
      </button>
      <p className="sig__n mono">
        {pct}% trong {s.n} người nhắc
        {s.mentionRate !== null && s.mentionRate < 0.05 ? ' · ít được nhắc' : ''}
        {trend ? ` · ${trend}` : ''}
      </p>
      <div className="sig__bar" aria-hidden="true">
        <i style={{ width: `${pct}%` }} />
      </div>
      <StatusTag status={s.status} why={why(s)} />
      {ctx && <p className="sig__ctx">{ctx}</p>}
      {open &&
        (s.quotes.length > 0 ? (
          <ul className="quotes">
            {s.quotes.map((q, i) => (
              <li key={i}>
                <q>{q.text}</q>
                <small>Review Google{q.date ? ` · ${new Date(q.date).toLocaleDateString('vi-VN')}` : ''}</small>
              </li>
            ))}
          </ul>
        ) : (
          <p className="unknown">Chưa có trích dẫn gốc cho nhận định này.</p>
        ))}
    </div>
  )
}
