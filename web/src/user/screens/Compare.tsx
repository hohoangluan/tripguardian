import { useMemo, useState } from 'react'
import { featureLabel, isNegative, valueLabel } from '../../data/labels'
import { confidenceOf, placeById, priceText, signal, visible, visitRange } from '../../data/store'
import type { Place } from '../../data/types'
import { navigate } from '../../router'
import { Chip, Icon, Page } from '../../ui/bits'
import { evaluate } from '../planner'
import { useTrip } from '../trip'

const TOD: Record<string, string> = { morning: 'sáng', noon: 'trưa', afternoon: 'chiều', evening: 'tối' }

function quietest(p: Place) {
  const c = p.crowdByTime
  if (!c) return null
  const cells = (['weekday', 'weekend'] as const).flatMap((d) => Object.entries(c[d] ?? {}).map(([t, v]) => ({ d, t, v })))
  const best = cells.filter((x) => TOD[x.t]).sort((a, b) => a.v - b.v)[0]
  return best ? `${TOD[best.t]} ${best.d === 'weekday' ? 'ngày thường' : 'cuối tuần'}` : null
}

export function Compare({ ids }: { ids: string[] }) {
  const { trip, dispatch } = useTrip()
  const places = ids.map((id) => placeById(id)).filter((p): p is Place => !!p).slice(0, 3)
  const cands = places.map((p) => evaluate(p, trip)!)
  const [priority, setPriority] = useState<string | null>(null)

  const rows = useMemo(() => {
    const out: { label: string; cells: string[]; best?: number }[] = []
    const feats = new Set(places.flatMap((p) => visible(p).filter((s) => s.n >= 2).map((s) => s.id)))
    for (const id of feats) {
      const cells = places.map((p) => {
        const s = signal(p, id)
        if (!s || s.n < 2) return '—'
        return `${s.value === 'present' ? 'có' : valueLabel(s.value)} (${s.n})`
      })
      if (new Set(cells).size > 1) out.push({ label: featureLabel(id), cells })
    }
    const strong = out.sort((a, b) => b.cells.filter((c) => c !== '—').length - a.cells.filter((c) => c !== '—').length).slice(0, 7)
    const base = [
      { label: 'Đi từ điểm xuất phát', cells: cands.map((c) => `≈${c.fromAnchor} phút`), best: argmin(cands.map((c) => c.fromAnchor)) },
      { label: 'Tham quan', cells: places.map((p) => visitRange(p).join('–') + ' phút') },
      { label: 'Vắng nhất vào', cells: places.map((p) => quietest(p) ?? 'chưa có thông tin') },
      { label: 'Chi phí', cells: places.map((p) => (p.priceRange ? priceText(p.priceRange) : 'chưa có thông tin')) },
      { label: 'Độ tin cậy', cells: places.map((p) => confidenceOf(p).level) },
    ]
    return [...base.filter((r) => new Set(r.cells).size > 1), ...strong]
  }, [places, cands])

  // The follow-up question only reorders emphasis; the user still picks.
  const lean = useMemo(() => {
    if (priority === 'near') return argmin(cands.map((c) => c.fromAnchor))
    if (priority === 'quiet') {
      const score = places.map((p) => {
        const s = signal(p, 'crowd')
        const n = signal(p, 'noise')
        return (s && isNegative('crowd', s.value) ? 1 : 0) + (n && n.value === 'loud' ? 1 : 0) - (n && n.value === 'quiet' ? 1 : 0)
      })
      return argmin(score)
    }
    return -1
  }, [priority, cands, places])

  if (places.length < 2) return <div className="loading">Cần ít nhất 2 nơi để so sánh.</div>

  return (
    <Page className="page--wide">
      <button className="back" onClick={() => history.back()}>
        <Icon name="back" size={16} /> Quay lại
      </button>
      <header className="phead">
        <h1>So sánh nhanh</h1>
        <p>Chỉ hiện những điểm khác nhau. Số trong ngoặc là số người nhắc tới.</p>
      </header>

      <div className="cmp" style={{ ['--cols' as string]: places.length }}>
        <div className="cmp__row cmp__row--head">
          <span />
          {places.map((p, i) => (
            <div key={p.id} className={`cmp__col${lean === i ? ' is-lean' : ''}`}>
              <button className="link cmp__name" onClick={() => navigate(`/app/place/${encodeURIComponent(p.id)}`)}>
                {p.name}
              </button>
              <small>{p.category}</small>
            </div>
          ))}
        </div>
        {rows.map((r) => (
          <div className="cmp__row" key={r.label}>
            <span className="cmp__label">{r.label}</span>
            {r.cells.map((c, i) => (
              <span key={i} className={`cmp__cell${r.best === i ? ' is-best' : ''}${lean === i ? ' is-lean' : ''}`}>
                {c}
              </span>
            ))}
          </div>
        ))}
        <div className="cmp__row cmp__row--act">
          <span />
          {places.map((p) => {
            const on = trip.selected.includes(p.id)
            return (
              <div key={p.id}>
                <button className={`btn btn--small${on ? ' btn--chosen' : ''}`} onClick={() => dispatch(on ? { type: 'unselect', id: p.id } : { type: 'select', id: p.id })}>
                  {on ? 'Đã chọn' : 'Chọn nơi này'}
                </button>
              </div>
            )
          })}
        </div>
      </div>

      <section className="followup">
        <p className="bubble bubble--q">Bạn ưu tiên ít di chuyển hay chỗ yên tĩnh hơn?</p>
        <div className="chips">
          <Chip on={priority === 'near'} onClick={() => setPriority('near')}>
            Ít di chuyển
          </Chip>
          <Chip
            on={priority === 'quiet'}
            onClick={() => {
              setPriority('quiet')
              dispatch({ type: 'pref', id: 'noise', pref: { weight: 'love', from: 'answer' } })
            }}
          >
            Yên tĩnh hơn
          </Chip>
          <Chip on={priority === null} onClick={() => setPriority(null)}>
            Chưa chắc
          </Chip>
        </div>
        {lean >= 0 && <p className="hint-line">Theo ưu tiên đó, {places[lean].name} hợp hơn. Bạn vẫn là người chọn.</p>}
      </section>
    </Page>
  )
}

function argmin(xs: number[]) {
  let b = 0
  xs.forEach((x, i) => x < xs[b] && (b = i))
  return b
}
