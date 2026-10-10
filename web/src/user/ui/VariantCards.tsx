import { fmtMin, fmtVnd, info } from '../lib'
import { OBJECTIVE_BLURB, variantPlaces } from '../planning/view'
import type { ItineraryDay, Variant } from '../planning/types'
import { PlacePhoto } from './common'
import { Icon } from './icons'

export const costText = (v: Variant) => (v.metrics.cost_vnd ? `~${fmtVnd(v.metrics.cost_vnd)}` : 'Chưa có giá')
const stops = (d: ItineraryDay) => d.items.filter((it) => it.kind === 'visit' && it.place_id)

// The plans the planner found for the same places, one photo card each, so it is plain that there are several to choose
// from (docs/P4_PLANNING.md ⓖ). Photos are the places' own (the first stop of each day, which differs most between plans).
// size lg: the choice before a plan is picked, with the day-by-day preview on hover / focus. size sm: the strip above the
// plan, to switch with one click (act pick_variant).
export function VariantCards({ variants, active, busy, onPick, size }: { variants: Variant[]; active: string | null; busy: boolean; onPick: (id: string) => void; size: 'lg' | 'sm' }) {
  return (
    <div className={`tg-vcs tg-vcs--${size}`} style={{ ['--n' as string]: Math.min(variants.length, 3) }} role="radiogroup" aria-label="Các hành trình">
      {variants.map((v) => {
        const on = active === v.id
        const ids = variantPlaces(v, (id) => !!info(id)?.photos?.length, 3, variants)
        const places = v.itinerary.reduce((n, d) => n + stops(d).length, 0)
        return (
          <button key={v.id} type="button" role="radio" aria-checked={on} disabled={busy} className={`tg-vc ${on ? 'is-on' : ''}`} onClick={() => !on && onPick(v.id)}>
            <span className={`tg-vc__photos is-${ids.length}`} aria-hidden="true">
              {ids.map((id) => <PlacePhoto key={id} id={id} name="" className="tg-vc__ph" />)}
              <span className="tg-vc__tag tg-tag tg-tag--dark">{v.robustness.label}</span>
            </span>
            <span className="tg-vc__body">
              <span className="tg-vc__top"><b>{v.label}</b>{on && <span className="tg-tag"><Icon name="check" size={13} /> Đang xem</span>}</span>
              {size === 'lg' && <em>{OBJECTIVE_BLURB[v.objective] ?? v.robustness.reasons[0] ?? ''}</em>}
              <span className="tg-vc__stats">
                <span><Icon name="calendar" size={14} /> {v.itinerary.length} ngày</span>
                <span><Icon name="pin" size={14} /> {places} nơi</span>
                <span><Icon name="route" size={14} /> {v.metrics.travel_min > 0 ? `≈${fmtMin(v.metrics.travel_min)} đi` : 'Chưa tính đường đi'}</span>
                <span className="tg-vc__cost">{costText(v)}</span>
              </span>
              {size === 'lg' && v.lodging.name && <span className="tg-vc__lodging"><Icon name="bed" size={14} /> {v.lodging.name}</span>}
              {size === 'lg' && (
                <span className="tg-vc__prev">
                  {v.itinerary.map((d) => <span key={d.day}><i>Ngày {d.day}</i>{stops(d).map((x) => x.name).join(' → ') || '—'}</span>)}
                </span>
              )}
              {size === 'lg' && <span className="tg-vc__go">Chọn hành trình này <Icon name="arrow" size={16} /></span>}
            </span>
          </button>
        )
      })}
    </div>
  )
}
