import { crowdOf, fmtRange, fmtVnd, info, priceText, TRUST } from '../lib'
import { useDecision } from '../pd/decision'
import type { Card } from '../pd/types'
import { toggleSaved, useUi } from '../store'
import { PlacePhoto, Trust, warmPlaces } from './common'
import { HeartFill, Icon } from './icons'
import { openPlace } from './PlaceSheet'

// One suggestion: why it fits, what it costs, how sure we are. Every main action works by click and keyboard;
// hover only reveals the secondary row earlier.
export function PlaceCard({ c, onDrop, cmp, onCmp, warn }: { c: Card; onDrop: (c: Card) => void; cmp: boolean; onCmp: (id: string) => void; warn?: string }) {
  const { act, busy, view } = useDecision()
  const p = info(c.id)
  const saved = useUi((u) => u.saved.includes(c.id))
  const flash = useUi((u) => u.flashId === c.id)
  const crowd = crowdOf(p)
  const price = c.price ?? priceText(p?.price)
  const budget = view?.budget_vnd ? `Ngân sách bạn đặt: khoảng ${fmtVnd(view.budget_vnd)}/người/ngày` : undefined
  // At most two warnings, all about this place: what is true of the whole trip (rain, no budget yet) is said once
  // above the list.
  const notes = [...c.failed.map((t) => `Không hợp điều kiện của bạn: ${t}`), ...c.unverified, ...c.warnings]
  const trade = c.tradeoffs[0]?.text ?? notes.shift()
  const alert = warn ?? [...c.tradeoffs.slice(1).map((t) => t.text), ...notes][0]
  const credit = p?.photos[0]?.credit
  return (
    // pointing at a card: the gallery its sheet opens with is fetched now, so the sheet opens with photos
    <article onPointerEnter={() => warmPlaces([c.id], 3)} onFocus={() => warmPlaces([c.id], 3)} className={`tg-pc ${c.chosen ? 'is-sel' : ''} ${c.locked ? 'is-lock' : ''} ${warn ? 'is-warn' : ''} ${c.status === 'unverified' ? 'is-dim' : ''} ${flash ? 'tg-flash' : ''}`}>
      <div className="tg-pc__media">
        <button type="button" className="tg-pc__open" onClick={(e) => openPlace(c.id, e.currentTarget.querySelector('figure'))} aria-label={`Xem chi tiết ${c.name}`}>
          <PlacePhoto id={c.id} name={c.name} />
          <span className="tg-pc__shade" />
        </button>
        {c.category && <span className="tg-tag tg-tag--dark tg-pc__cat">{c.category}</span>}
        {c.top && <span className="tg-tag tg-pc__top" title="Một trong những nơi hợp chuyến của bạn nhất, đã chọn sao cho khác nhau">Hợp nhất</span>}
        <button type="button" className={`tg-pc__save ${saved ? 'is-on' : ''}`} onClick={() => toggleSaved(c.id, c.name)} aria-pressed={saved} aria-label={saved ? `Bỏ lưu ${c.name}` : `Lưu ${c.name}`}>{saved ? <HeartFill size={18} /> : <Icon name="heart" size={18} />}</button>
        {(c.anchor || c.locked) && <span className="tg-pc__lock" title={c.anchor ? 'Bạn nói nhất định đến' : 'Đã khóa'}><Icon name="lock" size={14} /> {c.anchor ? 'Bắt buộc' : 'Đã khóa'}</span>}
        {credit && <span className="tg-pc__credit">Ảnh: {credit}</span>}
      </div>
      <div className="tg-pc__body">
        <div className="tg-pc__title">
          <h3>{c.name}</h3>
          <p className="tg-faint">{p?.area ?? c.area}{p?.rating ? <> · ★ {p.rating.toFixed(1).replace('.', ',')}</> : null}{c.suggested ? ' · gợi ý thêm' : ''}</p>
        </div>
        {c.why.length ? (
          <ul className="tg-pc__why" aria-label="Vì sao phù hợp">
            {c.why.slice(0, 3).map((r) => <li key={r.text}><Icon name="check" size={15} />{r.text}</li>)}
          </ul>
        ) : <p className="tg-faint">Chưa có lý do rõ.</p>}
        {trade ? <p className="tg-pc__trade"><Icon name="warn" size={15} /><span><b>Đánh đổi:</b> {trade}</span></p> : <p className="tg-faint">Chưa thấy điều gì đáng ngại.</p>}
        {alert && <p className="tg-pc__alert" role={warn ? 'status' : undefined}><Icon name="warn" size={14} />{alert}</p>}
        <div className="tg-pc__facts">
          {c.visit && <span title={c.visit.stay ? `Ước tính cho một lần ghé trong ngày; cắm trại qua đêm thì khoảng ${fmtRange(c.visit.stay.short, c.visit.stay.long)}` : 'Thời gian nên dành, ước tính'}><Icon name="clock" size={14} /> {fmtRange(c.visit.short, c.visit.long)}</span>}
          {price && <span title={budget}>{price}</span>}
          {c.location.minutes !== null && <span title="Ước tính bằng xe máy">{c.location.minutes} phút từ {c.location.center}</span>}
          {c.outdoor && <span className="tg-pc__out" title="Nơi ngoài trời: trời mưa thì nên có phương án dự phòng">Ngoài trời</span>}
          {crowd !== null && crowd >= 60 && <span className="tg-pc__crowd">Cuối tuần đông</span>}
          <Trust level={TRUST[c.confidence.level]} why={c.confidence.reason + (c.declined ? ' Có dấu hiệu xuống cấp gần đây.' : '')} />
        </div>
        <div className="tg-pc__act">
          {c.chosen ? (
            <button type="button" className="tg-btn tg-btn--sm tg-btn--soft" disabled={busy || c.anchor} onClick={() => onDrop(c)} title={c.anchor ? 'Nơi bạn nói nhất định đến' : 'Bấm để bỏ khỏi danh sách'} aria-pressed="true"><Icon name="check" size={16} /> Đã chọn</button>
          ) : (
            <button type="button" className="tg-btn tg-btn--sm tg-btn--primary" disabled={busy} onClick={() => act({ type: 'select', place_id: c.id })} aria-pressed="false"><Icon name="plus" size={16} /> Thêm</button>
          )}
          <div className="tg-pc__more" role="group" aria-label={`Thao tác với ${c.name}`}>
            <button type="button" className={`tg-pc__ic ${c.locked ? 'is-on' : ''}`} disabled={busy} onClick={() => act({ type: c.locked ? 'unlock' : 'lock', place_id: c.id })} aria-pressed={c.locked} title={c.locked ? 'Bỏ khóa nơi này' : 'Khóa: luôn giữ nơi này khi danh sách đổi'}><Icon name={c.locked ? 'lock' : 'unlock'} size={16} /><span>{c.locked ? 'Đã khóa' : 'Khóa'}</span></button>
            <button type="button" className={`tg-pc__ic ${cmp ? 'is-on' : ''}`} onClick={() => onCmp(c.id)} aria-pressed={cmp} title="Chọn để so sánh với nơi khác"><Icon name="swap" size={16} /><span>So sánh</span></button>
            {!c.chosen && <button type="button" className="tg-pc__ic" onClick={() => onDrop(c)} title="Bỏ nơi này khỏi gợi ý"><Icon name="x" size={16} /><span>Bỏ</span></button>}
          </div>
        </div>
      </div>
    </article>
  )
}
