import { useEffect, useState } from 'react'
import { info } from '../lib'
import { compare } from '../pd/api'
import { useDecision } from '../pd/decision'
import type { CompareResult } from '../pd/types'
import { useTrip } from '../trip'
import { ArtHills, Busy, Empty, go, placeHref, PlacePhoto } from '../ui/common'
import { Icon } from '../ui/icons'
import { SelectedBar } from '../ui/SelectedBar'
import { FlowBar, Page, useTitle } from '../ui/Shell'
import { useEditTicket } from './Explore'

// Only what differs (src/decision/compare.py); a third place is compared with the first one.
export function Compare({ ids }: { ids: string[] }) {
  useTitle('So sánh')
  const { trip } = useTrip()
  const { view, act, busy } = useDecision()
  const editTicket = useEditTicket()
  const [res, setRes] = useState<CompareResult[] | null>(null)
  const [err, setErr] = useState(false)
  const list = ids.slice(0, 3)
  useEffect(() => {
    if (!trip.decisionId || list.length < 2) return
    Promise.all(list.slice(1).map((b) => compare(trip.decisionId!, list[0], b))).then(setRes, () => setErr(true))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trip.decisionId, ids.join()])
  const cards = new Map(view?.groups.flatMap((g) => g.cards).map((c) => [c.id, c]) ?? [])
  const back = () => go('/explore')
  if (list.length < 2 || err)
    return (
      <>
        <FlowBar step="explore" />
        <Page narrow><Empty art={<ArtHills />} title={err ? 'Chưa so sánh được' : 'Chọn ít nhất hai nơi'} body={err ? 'Một trong các nơi này không còn trong danh sách gợi ý.' : 'Bấm So sánh trên hai hoặc ba thẻ để đặt cạnh nhau.'} action={<button type="button" className="tg-btn tg-btn--primary" onClick={back}>Về danh sách gợi ý</button>} /></Page>
      </>
    )
  // aspect -> label + one value per place
  const rows = new Map<string, { label: string; vals: string[]; best: number }>()
  res?.forEach((r, k) => r.rows.forEach((row) => {
    const cur = rows.get(row.aspect) ?? { label: row.label, vals: list.map(() => '—'), best: -1 }
    cur.vals[0] = row.a
    cur.vals[k + 1] = row.b
    if (list.length === 2) cur.best = row.better === 'a' ? 0 : row.better === 'b' ? 1 : -1
    rows.set(row.aspect, cur)
  }))
  const names = list.map((id, i) => cards.get(id)?.name ?? (i === 0 ? res?.[0]?.a.name : res?.[i - 1]?.b.name) ?? info(id)?.name ?? id)
  return (
    <>
      <FlowBar step="explore" />
      <Page className="tg-compare">
        <button type="button" className="tg-back" onClick={back}><Icon name="arrowLeft" size={18} /> Về danh sách gợi ý</button>
        <header className="tg-xhead"><div><p className="tg-kicker">So sánh nhanh</p><h1>Chỉ những điểm khác nhau</h1><p>Điểm giống nhau đã được ẩn. Bạn là người bấm giữ, mình không chọn thay.</p></div></header>
        {!res ? <Busy text="Đang đặt các nơi cạnh nhau…" /> : (
          <div className="tg-cmp" style={{ gridTemplateColumns: `180px repeat(${list.length}, minmax(0, 1fr))` }}>
            <div className="tg-cmp__corner" />
            {list.map((id, i) => (
              <div key={id} className="tg-cmp__col">
                <PlacePhoto id={id} name={names[i]} className="tg-cmp__ph" />
                <button type="button" className="tg-cmp__name" onClick={() => go(placeHref(id))}>{names[i]}<Icon name="chevronRight" size={16} /></button>
                <span className="tg-faint">{[cards.get(id)?.category, info(id)?.area].filter(Boolean).join(' · ')}</span>
              </div>
            ))}
            {[...rows.values()].map((r) => (
              <div className="tg-cmp__row" key={r.label} style={{ display: 'contents' }}>
                <div className="tg-cmp__label">{r.label}</div>
                {r.vals.map((v, i) => <div key={i} className={`tg-cmp__cell ${r.best === i ? 'is-best' : ''}`}>{v === 'unknown' || v === '—' ? <span className="tg-faint">Chưa có thông tin</span> : v}{r.best === i && <Icon name="check" size={15} />}</div>)}
              </div>
            ))}
            {rows.size === 0 && <p className="tg-faint tg-cmp__same">Các nơi này không khác nhau ở điểm nào mình đo được.</p>}
            <div className="tg-cmp__label" />
            {list.map((id) => {
              const c = cards.get(id)
              return (
                <div key={id} className="tg-cmp__act">
                  {c ? (
                    <>
                      <button type="button" className={`tg-btn ${c.chosen ? 'tg-btn--soft' : 'tg-btn--primary'}`} disabled={busy || c.chosen} onClick={() => act({ type: 'select', place_id: id })}>{c.chosen ? <><Icon name="check" size={16} /> Đã giữ</> : 'Giữ nơi này'}</button>
                      {!c.anchor && <button type="button" className="tg-link tg-link--quiet" disabled={busy} onClick={async () => { if ((await act({ type: 'drop', place_id: id })) && list.length <= 2) back() }}>Bỏ nơi này</button>}
                    </>
                  ) : <span className="tg-faint">Không còn trong gợi ý</span>}
                </div>
              )
            })}
          </div>
        )}
        {res && list.length === 2 && res[0].sacrifice.length > 0 && (
          <section className="tg-narrow tg-cmp__sac"><b>Chọn một nơi thì bỏ lại:</b>{res[0].sacrifice.map((s) => <span key={s.aspect} className="tg-chip tg-chip--soft">{s.label}: {s.better === 'a' ? names[0] : names[1]} hơn</span>)}</section>
        )}
      </Page>
      <SelectedBar onRelax={editTicket} />
    </>
  )
}
