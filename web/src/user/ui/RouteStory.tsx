import { useMemo } from 'react'
import { fmtClock, toMin } from '../lib'
import type { ItineraryDay } from '../planning/types'
import { Link, placeHref, PlacePhoto } from './common'
import { Icon } from './icons'

interface Node { id: string | null; day: number; start: number; end: number; travel: number; label: string }

// Infographic view of a day (or the whole trip): photo cards pinned along a dashed route, alternating above / below.
export function RouteStory({ days, day, home, hot, setHot }: { days: ItineraryDay[]; day: number | 'all'; home: string; hot: string | null; setHot: (v: string | null) => void }) {
  const nodes = useMemo<Node[]>(() => {
    const shown = day === 'all' ? days : [days[day]].filter(Boolean)
    const out: Node[] = [{ id: null, day: shown[0]?.day ?? 1, start: shown[0] ? toMin(shown[0].window[0]) : 0, end: 0, travel: 0, label: home }]
    shown.forEach((d) => {
      let leg = 0
      d.items.forEach((it) => {
        if (it.kind === 'travel') leg += toMin(it.end) - toMin(it.start)
        if (it.kind === 'visit' && it.place_id) {
          out.push({ id: it.place_id, day: d.day, start: toMin(it.start), end: toMin(it.end), travel: leg, label: it.name ?? '' })
          leg = 0
        }
      })
    })
    return out
  }, [days, day, home])
  const n = nodes.length
  const W = 1000, H = 400
  const pts = nodes.map((_, i) => ({ x: n === 1 ? W / 2 : 70 + (i * (W - 140)) / (n - 1), y: H / 2 + (i % 2 === 0 ? 22 : -22) + Math.sin(i * 1.3) * 18 }))
  const d = pts.map((p, i) => {
    if (i === 0) return `M${p.x} ${p.y}`
    const a = pts[i - 1]
    const mx = (a.x + p.x) / 2
    return `C${mx} ${a.y} ${mx} ${p.y} ${p.x} ${p.y}`
  }).join(' ')
  const cur = day === 'all' ? null : days[day]
  const title = cur ? `Ngày ${cur.day}${cur.weekday ? ` · ${cur.weekday}` : ''}` : 'Cả chuyến'
  return (
    <div className="tg-rs" style={{ minWidth: Math.max(860, n * 190) }}>
      <h3 className="tg-rs__title">{title}</h3>
      <div className="tg-rs__stage" role="img" aria-label={`Hành trình ${title}: ${nodes.map((x) => x.label).join(' → ')}. Xem chế độ theo giờ để đọc chi tiết.`}>
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
          <g className="tg-rs__blobs">
            <path d="M40 90c40-50 120-60 150-20s0 90-50 100-130-30-100-80Z" /><path d="M560 300c50-40 120-40 160 0s10 80-50 80-150-10-110-80Z" /><path d="M820 60c40-30 100-20 120 20s-20 80-80 80-80-70-40-100Z" />
          </g>
          <path key={d} className="tg-rs__route" d={d} pathLength={1} vectorEffect="non-scaling-stroke" />
        </svg>
        {nodes.map((nd, i) => {
          const mid = i > 0 ? { x: (pts[i - 1].x + pts[i].x) / 2, y: (pts[i - 1].y + pts[i].y) / 2 } : null
          const on = hot === nd.id && nd.id
          return (
            <div key={`${nd.id}-${i}`}>
              {mid && nd.travel > 0 && <span className="tg-rs__leg" style={{ left: `${(mid.x / W) * 100}%`, top: `${(mid.y / H) * 100}%` }}><Icon name="bike" size={13} />≈{nd.travel}′</span>}
              <span className={`tg-rs__dot ${nd.id === null ? 'is-home' : ''} ${on ? 'is-hot' : ''}`} style={{ left: `${(pts[i].x / W) * 100}%`, top: `${(pts[i].y / H) * 100}%` }}>{nd.id === null ? <Icon name="bed" size={14} /> : i}</span>
              <div className={`tg-rs__card ${i % 2 === 1 ? 'is-above' : 'is-below'} ${nd.id === null ? 'is-home' : ''} ${on ? 'is-hot' : ''}`} style={{ left: `${(pts[i].x / W) * 100}%`, top: `${(pts[i].y / H) * 100}%`, ['--i' as string]: i }} onMouseEnter={() => nd.id && setHot(nd.id)} onMouseLeave={() => setHot(null)}>
                {nd.id ? (
                  <Link to={placeHref(nd.id)} className="tg-rs__frame">
                    <PlacePhoto id={nd.id} name={nd.label} className="tg-rs__ph" />
                    <b>{nd.label}</b>
                    <span className="tg-mono">{fmtClock(nd.start)} · {nd.end - nd.start} phút</span>
                    {day === 'all' && <em className="tg-tag">Ngày {nd.day}</em>}
                  </Link>
                ) : (
                  <div className="tg-rs__frame is-home"><Icon name="bed" size={22} /><b>{nd.label}</b><span>Xuất phát {fmtClock(nd.start)}</span></div>
                )}
              </div>
            </div>
          )
        })}
      </div>
      <p className="tg-faint tg-rs__note">Sơ đồ minh họa thứ tự đi, không đúng tỉ lệ bản đồ. Giờ giấc và đường đi là ước tính.</p>
    </div>
  )
}
