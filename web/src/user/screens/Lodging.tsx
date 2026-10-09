import { fmtMin, fmtVnd, info } from '../lib'
import { usePlanning } from '../planning/planning'
import type { LodgingCandidate } from '../planning/types'
import { lodgingSuggest } from '../tu/api'
import type { LodgingHit } from '../tu/types'
import { PlacePhoto } from '../ui/common'
import { Icon } from '../ui/icons'
import { PlaceInput } from '../ui/PlaceInput'
import { openPlace } from '../ui/PlaceSheet'
import { FlowBar, Page, useTitle } from '../ui/Shell'

// "Bạn ở đâu?" (docs/Role_Web_Functional_Design.md §6): asked once before the schedule when the user said they have
// no lodging yet. Cards come ranked by taste first, location after (docs/PLANNING.md ⓐ); the side card on Lịch trình
// still changes it later.

const ASKED = (id: string) => `tg.lodging.asked.${id}`
export const lodgingAsked = (id: string) => {
  try { return localStorage.getItem(ASKED(id)) === '1' } catch { return false }
}
const markAsked = (id: string) => {
  try { localStorage.setItem(ASKED(id), '1') } catch { /* asked again after a reload */ }
}

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
    finish(offered ? { type: 'pick_lodging', id: h.id! } : { type: 'set_lodging', text: h.kind === 'address' || !h.address ? h.text : `${h.text}, ${h.address}` })
  }
  const tasteful = cands[0]?.fit?.length
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
            row={(h) => ({ key: h.id ?? `${h.lat},${h.lng}`, icon: h.kind === 'address' ? 'pin' : 'bed', name: h.text, sub: h.address, rating: h.rating })} onPick={elsewhere} />
        </section>

        <div className="tg-lod__acts">
          <button type="button" className="tg-btn tg-btn--ghost" disabled={busy} onClick={() => finish()}><Icon name="sparkle" size={17} /> Cứ xếp giúp</button>
          <button type="button" className="tg-link" disabled={busy} onClick={() => finish({ type: 'clear_lodging' })}>Bỏ qua</button>
          <p className="tg-faint">“Cứ xếp giúp”: mình tự chọn chỗ ở hợp lịch nhất. “Bỏ qua”: lịch tính từ điểm bạn tới Đà Lạt. Đổi được sau ở cột bên của lịch trình.</p>
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

function Card({ c, top, busy, onPick }: { c: LodgingCandidate; top: boolean; busy: boolean; onPick: () => void }) {
  const known = !!info(c.id) // in the snapshot: it has photos and a detail sheet
  const quote = c.fit?.find((f) => f.quote)?.quote
  return (
    <li className={`tg-lod__card ${top ? 'is-top' : ''}`}>
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
        <button type="button" className="tg-btn tg-btn--primary tg-btn--sm" disabled={busy} onClick={onPick}>Ở đây</button>
      </div>
    </li>
  )
}
