import { useState } from 'react'
import { fmtMin, fmtVnd, info } from '../lib'
import { usePlanning } from '../planning/planning'
import type { LodgingCandidate } from '../planning/types'
import { lodgingSuggest } from '../tu/api'
import type { LodgingHit } from '../tu/types'
import { PlacePhoto } from '../ui/common'
import { Icon } from '../ui/icons'
import { PlaceInput, lodgingRow } from '../ui/PlaceInput'
import { openPlace } from '../ui/PlaceSheet'
import { FlowBar, Page, useTitle } from '../ui/Shell'

// "Bạn ở đâu?" (docs/WEB.md §6): asked once before the schedule when the user said they have
// no lodging yet. Cards come ranked by taste first, location after (docs/P4_PLANNING.md ⓐ); the side card on Lịch trình
// still changes it later.

const ASKED = (id: string) => `tg.lodging.asked.${id}`
export const lodgingAsked = (id: string) => {
  try { return localStorage.getItem(ASKED(id)) === '1' } catch { return false }
}
const markAsked = (id: string) => {
  try { localStorage.setItem(ASKED(id), '1') } catch { /* asked again after a reload */ }
}

// A lodging picked from the suggestions goes with its point, so the server never has to geocode a hotel name.
export const lodgingAct = (h: LodgingHit) => ({ type: 'set_lodging' as const, text: h.kind === 'address' || !h.address ? h.text : `${h.text}, ${h.address}`, lat: h.lat, lng: h.lng })

export function LodgingPick({ planningId, onDone }: { planningId: string; onDone: () => void }) {
  useTitle('Bạn ở đâu?')
  const { view, lodgingProgress, act, busy, error } = usePlanning()
  if (!view) return null
  const status = view.lodging.status
  const cands = status === 'pending' && lodgingProgress ? lodgingProgress.candidates : view.lodging.candidates
  const finish = async (a?: Parameters<typeof act>[0]) => {
    if (a) await act(a)
    markAsked(planningId)
    onDone()
  }
  const elsewhere = (h: LodgingHit) => {
    const offered = h.id && cands.some((c) => c.id === h.id)
    finish(offered ? { type: 'pick_lodging', id: h.id! } : lodgingAct(h))
  }
  const tasteful = cands[0]?.fit?.length
  // "Cứ xếp giúp" keeps its word: the best-ranked stay becomes the lodging; with none to offer it only builds the schedule.
  const top = status === 'ready' ? view.lodging.candidates[0] : undefined
  return (
    <>
      <FlowBar step="plan" />
      <Page className="tg-plan tg-lod">
        <header className="tg-xhead">
          <div>
            <p className="tg-kicker">Bước 3 · Lịch trình</p>
            <h1>Bạn ở đâu?</h1>
            <p>Chọn chỗ ở để mình tính đường đi mỗi ngày từ đúng chỗ đó. Xếp theo mức hợp gu của bạn trước, vị trí sau.</p>
          </div>
        </header>
        {error && <p className="tg-alert" role="alert"><Icon name="warn" size={16} /> {error}</p>}

        {status === 'pending' && !cands.length ? (
          <>
            <p className="tg-faint" role="status">Đang tìm chỗ ở quanh các nơi bạn chọn… có thể mất ~10 giây.</p>
            <div className="tg-lod__grid" aria-busy="true">{Array.from({ length: 3 }, (_, i) => <div key={i} className="tg-skel-card"><span className="tg-skel" /><div><span className="tg-skel tg-skel-line" /><span className="tg-skel tg-skel-line" style={{ width: '60%' }} /></div></div>)}</div>
          </>
        ) : !cands.length ? (
          <p className="tg-lod__empty">{status === 'unavailable' ? 'Chưa tra được chỗ ở lúc này.' : 'Chưa có chỗ ở nào hợp quanh các nơi bạn chọn.'} Bạn gõ chỗ mình ở bên dưới, hoặc để mình xếp lịch trước.</p>
        ) : (
          <ol className="tg-lod__grid">
            {cands.map((c, i) => <Card key={c.id} c={c} top={i === 0 && !!tasteful} busy={busy} onPick={() => finish({ type: 'pick_lodging', id: c.id })} />)}
          </ol>
        )}

        <section className="tg-lod__other" aria-labelledby="tg-lod-other">
          <h2 id="tg-lod-other">Tôi ở chỗ khác</h2>
          <PlaceInput<LodgingHit> label="Chỗ bạn ở" placeholder="Tên khách sạn, homestay hoặc địa chỉ" icon="bed" disabled={busy} fetcher={lodgingSuggest}
            row={lodgingRow} onPick={elsewhere} />
        </section>

        <div className="tg-lod__acts">
          <button type="button" className="tg-btn tg-btn--ghost" disabled={busy} onClick={() => finish(top ? { type: 'pick_lodging', id: top.id } : undefined)}><Icon name="sparkle" size={17} /> {top ? 'Cứ xếp giúp' : 'Xếp lịch trước'}</button>
          <button type="button" className="tg-link" disabled={busy} onClick={() => finish({ type: 'clear_lodging' })}>Bỏ qua</button>
          <p className="tg-faint">{top ? `“Cứ xếp giúp”: mình chọn ${top.name}, đứng đầu danh sách (hợp gu, gần các nơi bạn chọn).` : '“Xếp lịch trước”: chưa có chỗ ở nên đường tính từ điểm bạn tới Đà Lạt.'} “Bỏ qua”: lịch tính từ điểm bạn tới Đà Lạt. Đổi chỗ ở sau ở cột bên của lịch trình.</p>
        </div>
      </Page>
    </>
  )
}

// "21:05 08/10" in Vietnam time.
function at(iso: string) {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  const v = (o: Intl.DateTimeFormatOptions) => d.toLocaleString('en-GB', { timeZone: 'Asia/Ho_Chi_Minh', hour12: false, ...o })
  return `${v({ hour: '2-digit' })}:${v({ minute: '2-digit' }).padStart(2, '0')} ${v({ day: '2-digit' })}/${v({ month: '2-digit' })}`
}

function Card({ c, top, busy, chosen = false, onPick }: { c: LodgingCandidate; top: boolean; busy: boolean; chosen?: boolean; onPick: () => void }) {
  const known = !!info(c.id) // in the snapshot: it has photos and a detail sheet
  const quote = c.fit?.find((f) => f.quote)?.quote
  return (
    <li className={`tg-lod__card ${top ? 'is-top' : ''} ${chosen ? 'is-chosen' : ''}`}>
      <button type="button" className="tg-lod__open" disabled={!known} onClick={(e) => openPlace(c.id, e.currentTarget.querySelector('figure'))} aria-label={known ? `Xem chi tiết ${c.name}` : undefined}>
        {known ? <PlacePhoto id={c.id} name={c.name} className="tg-lod__ph" /> : <figure className="tg-lod__ph is-blank" aria-hidden="true"><Icon name="bed" size={32} /></figure>}
        {top && <span className="tg-lod__badge"><Icon name="heart" size={14} /> Hợp gu bạn nhất</span>}
      </button>
      <div className="tg-lod__body">
        <h3>{c.name}</h3>
        <p className="tg-lod__facts">
          {c.rating ? <span className="tg-mono">★ {c.rating.toFixed(1)}{c.reviews ? <small> ({c.reviews.toLocaleString('vi-VN')})</small> : null}</span> : null}
          <span className="tg-mono">{c.price_vnd ? `${fmtVnd(c.price_vnd)}/đêm` : 'chưa có giá'}</span>
          {c.avg_min != null && <span><Icon name="route" size={14} /> ≈{fmtMin(c.avg_min)} tới các nơi đã chọn</span>}
          {c.price_vnd && c.price_at ? <small className="tg-lod__at">giá cho ngày đi, xem lúc {at(c.price_at)}; kiểm lại khi đặt</small> : null}
        </p>
        {c.fit?.length ? (
          <p className="tg-lod__fit"><b>Hợp vì:</b> {c.fit.map((f) => f.mentions ? `${f.text} (${f.mentions} đánh giá nhắc)` : f.text).join(' · ')}</p>
        ) : c.source === 'live' ? <p className="tg-faint tg-lod__fit">Chưa đủ dữ liệu để so gu, xếp theo vị trí và giá.</p> : null}
        {quote && <blockquote className="tg-lod__quote">“{quote}”</blockquote>}
        {c.unverified?.length ? <p className="tg-lod__warn"><Icon name="info" size={14} /> chưa xác minh: {c.unverified.join(', ')}</p> : null}
        <button type="button" className="tg-btn tg-btn--primary tg-btn--sm" disabled={busy || chosen} onClick={onPick}>{chosen ? <><Icon name="check" size={15} /> Đang ở đây</> : 'Ở đây'}</button>
      </div>
    </li>
  )
}

// The lodging on the journey page: three proposals to pick from (one tap), the chosen one as a bar that opens them again,
// and a box for a place of the traveller's own. Without a lodging the plan has no home to start the days from, so the
// strip is the first thing on the page and says so.
export function LodgingStrip({ chosenName }: { chosenName: string | null }) {
  const { view, lodgingProgress, act, busy } = usePlanning()
  const [open, setOpen] = useState(false)
  if (!view) return null
  const status = view.lodging.status
  const cands = (status === 'pending' && lodgingProgress ? lodgingProgress.candidates : view.lodging.candidates).slice(0, 3)
  const chosenId = view.state.lodging_id
  const show = !chosenName || open
  const pick = (a: Parameters<typeof act>[0]) => act(a).then(() => setOpen(false))
  const own = (h: LodgingHit) => pick(h.id && cands.some((c) => c.id === h.id) ? { type: 'pick_lodging', id: h.id } : lodgingAct(h))
  return (
    <section className={`tg-lstrip ${chosenName ? 'is-set' : 'is-need'}`} aria-labelledby="tg-lstrip-h" data-tour="plan-lodging">
      <header>
        <Icon name="bed" size={20} />
        <div>
          <h2 id="tg-lstrip-h">{chosenName ? <>Chỗ ở: <b>{chosenName}</b></> : 'Chọn chỗ ở của bạn'}</h2>
          <p className="tg-faint">{chosenName ? 'Mỗi ngày bắt đầu và kết thúc ở đây. Đổi chỗ ở thì giờ đi lại được tính lại.' : 'Chưa có chỗ ở nên mình chưa tính được đường đi mỗi ngày. Bấm một chỗ bên dưới, lịch sẽ vẽ lại ngay.'}</p>
        </div>
        {chosenName && <button type="button" className="tg-link" aria-expanded={open} onClick={() => setOpen((v) => !v)}>{open ? 'Thu gọn' : 'Đổi chỗ ở'}</button>}
      </header>
      {show && (
        <>
          {status === 'pending' && !cands.length && <p className="tg-faint" role="status">Đang tìm chỗ ở quanh lịch trình… có thể mất ~10 giây.</p>}
          {status !== 'pending' && !cands.length && <p className="tg-faint">{status === 'unavailable' ? 'Chưa tra được chỗ ở lúc này.' : 'Chưa có chỗ ở nào hợp quanh các nơi bạn chọn.'} Bạn gõ chỗ mình ở bên dưới.</p>}
          {cands.length > 0 && <ol className="tg-lod__grid">{cands.map((c, i) => <Card key={c.id} c={c} top={i === 0 && !!c.fit?.length} busy={busy} chosen={c.id === chosenId} onPick={() => pick({ type: 'pick_lodging', id: c.id })} />)}</ol>}
          <div className="tg-lstrip__own">
            <span>Tôi ở chỗ khác</span>
            <PlaceInput<LodgingHit> label="Chỗ bạn ở" placeholder="Tên khách sạn, homestay hoặc địa chỉ" icon="bed" disabled={busy} fetcher={lodgingSuggest} row={lodgingRow} onPick={own} />
          </div>
        </>
      )}
    </section>
  )
}
