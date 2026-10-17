import { useEffect, useState, type ReactNode } from 'react'
import { fmtMin, fmtVnd, info } from '../../lib'
import * as pdApi from '../../pd/api'
import { lodgingTop } from '../../tu/api'
import type { LodgingHit } from '../../tu/types'
import { useTrip } from '../../trip'
import { PlacePhoto } from '../../ui/common'
import { Icon } from '../../ui/icons'

// The lodging question as a deck of stays to tap (docs/UI_SPEC_USER_WEB.md, "Nơi lưu trú"): the user reaches it because
// they have no hotel yet, so typing a name is a side door ("Mình đã có chỗ ở rồi"), not the way in. Every stay is a
// served corpus record; nothing is made up. Before any place is chosen (the chat) the list is the best-reviewed stays;
// at the gate, with places chosen, it is Planning's list ranked around them (distance shown).

type Row = { id: string; name: string; area: string | null; category: string | null; rating: number | null; price: number | null; minutes: number | null; why: string[]; lat: number | null; lng: number | null }
export type LodgingPick = { kind: 'corpus'; id: string; text: string; lat: number | null; lng: number | null }

const fromHit = (h: LodgingHit): Row => ({
  id: h.id ?? '', name: h.text, area: h.area ?? null, category: h.category ?? null, rating: h.rating ?? null, price: h.price_vnd ?? null, minutes: null,
  why: h.reviews ? [`${h.reviews.toLocaleString('vi-VN')} người đã viết về chỗ này`] : [], lat: h.lat, lng: h.lng,
})

export function useStays(ranked: boolean) {
  const { trip } = useTrip()
  const [rows, setRows] = useState<Row[] | null>(null)
  const [failed, setFailed] = useState(false)
  const id = trip.decisionId
  useEffect(() => {
    let live = true
    const top = () => lodgingTop(8).then(h => { if (live) setRows(h.filter(x => x.id).map(fromHit)) }, () => { if (live) setFailed(true) })
    if (ranked && id) {
      pdApi.lodgingOptions(id).then(o => {
        if (!live) return
        if (o.status !== 'ready' || !o.candidates.length) return void top()
        setRows(o.candidates.slice(0, 8).map(c => ({
          id: c.id, name: c.name, area: c.area ?? null, category: c.category ?? null, rating: c.rating ?? null, price: c.price_vnd, minutes: c.avg_min ?? null,
          why: (c.why ?? []).slice(0, 2).map(w => w.text), lat: info(c.id)?.lat ?? null, lng: info(c.id)?.lng ?? null,
        })))
      }, () => void top())
    } else void top()
    return () => { live = false }
  }, [ranked, id])
  return { rows, failed }
}

export function LodgingCards({ ranked = false, busy, onPick, onAuto, typed }: {
  ranked?: boolean; busy: boolean
  onPick: (pick: LodgingPick) => void
  onAuto: () => void
  typed: ReactNode // the search box, shown only when the user says they already have a stay
}) {
  const { rows, failed } = useStays(ranked)
  const [own, setOwn] = useState(false)
  const [on, setOn] = useState<string | null>(null)
  const pick = (r: Row) => { if (busy) return; setOn(r.id); onPick({ kind: 'corpus', id: r.id, text: r.name, lat: r.lat, lng: r.lng }) }
  return (
    <div className="tg-lc">
      {failed ? <p className="tg-lc__none">Chưa tải được danh sách chỗ ở. Bạn bấm “Cứ xếp giúp” hoặc gõ tên chỗ đang ở.</p>
        : !rows ? <div className="tg-lc__row" aria-busy="true" aria-label="Đang tải chỗ ở">{Array.from({ length: 3 }, (_, i) => <div key={i} className="tg-lc__card is-skel"><span className="tg-skel tg-lc__ph" /><span className="tg-skel tg-skel-line" /><span className="tg-skel tg-skel-line" style={{ width: '60%' }} /></div>)}</div>
        : <ul className="tg-lc__row" aria-label="Chỗ ở gợi ý">
                    <li className="tg-lc__card is-auto" style={{ '--i': 0 } as React.CSSProperties}>
            <button type="button" disabled={busy} onClick={onAuto}><Icon name="sparkle" size={26} /><b>Cứ xếp giúp</b><small>Mình tự chọn chỗ hợp nhất với lịch của bạn.</small></button>
          </li>
          {rows.map((r, i) => (
            <li key={r.id} className={`tg-lc__card ${on === r.id ? 'is-on' : ''}`} style={{ '--i': i + 1 } as React.CSSProperties}>
              <div className="tg-lc__ph">{info(r.id) ? <PlacePhoto id={r.id} name={r.name} /> : <span className="tg-lc__blank"><Icon name="bed" size={28} /></span>}{r.category && <span className="tg-tag tg-tag--dark tg-lc__cat">{r.category}</span>}</div>
              <div className="tg-lc__body">
                <h4>{r.name}</h4>
                <p className="tg-faint">{info(r.id)?.area ?? 'Đà Lạt'}{r.rating ? <> · <span className="tg-mono">★ {r.rating.toFixed(1)}</span></> : null}</p>
                <p className="tg-lc__facts">{r.price ? <span className="tg-mono">{fmtVnd(r.price)}/đêm</span> : <span className="tg-faint">Chưa có giá</span>}{r.minutes != null && <span className="tg-mono" title="Ước tính"> · ≈ {fmtMin(r.minutes)} tới các nơi đã chọn</span>}</p>
                {r.why.length > 0 && <p className="tg-lc__why"><Icon name="check" size={14} />{r.why[0]}</p>}
                <button type="button" className="tg-btn tg-btn--sm tg-btn--primary" disabled={busy} aria-pressed={on === r.id} onClick={() => pick(r)}>{on === r.id ? <><Icon name="check" size={16} /> Đã chọn</> : 'Chọn chỗ này'}</button>
              </div>
            </li>
          ))}
        </ul>}
      <div className="tg-lc__foot">
        {failed && <button type="button" className="tg-btn tg-btn--sm tg-btn--ghost" disabled={busy} onClick={onAuto}>Cứ xếp giúp</button>}
        <button type="button" className="tg-link" aria-expanded={own} onClick={() => setOwn(o => !o)}>Mình đã đặt chỗ rồi</button>
      </div>
      {(own || failed) && <div className="tg-lc__own">{typed}</div>}
    </div>
  )
}
