import type { CSSProperties } from 'react'
import { crowdOf, fmtRange, info, priceText, TRUST } from '../lib'
import { useDecision } from '../pd/decision'
import type { Card } from '../pd/types'
import { toggleSaved, useUi } from '../store'
import { go, placeHref, PlacePhoto, Trust } from './common'
import { HeartFill, Icon } from './icons'

// One suggestion: why it fits, what it costs, how sure we are. Every main action works by click and keyboard;
// hover only reveals the secondary row earlier.
export function PlaceCard({ c, onDrop, cmp, onCmp, warn, phase = 'stay', order = 0 }: { c: Card; onDrop: (c: Card) => void; cmp: boolean; onCmp: (id: string) => void; warn?: string; phase?: 'stay' | 'enter' | 'leave'; order?: number }) {
  const { act, busy } = useDecision()
  const p = info(c.id)
  const saved = useUi((u) => u.saved.includes(c.id))
  const flash = useUi((u) => u.flashId === c.id)
  const crowd = crowdOf(p)
  const price = c.price ?? priceText(p?.price)
  const notes = [...c.failed.map((t) => `Không hợp điều kiện của bạn: ${t}`), ...c.unverified, ...c.warnings, ...(c.depends_on_unknown ? [c.depends_on_unknown] : [])]
  const trade = c.tradeoffs[0]?.text ?? notes.shift()
  const credit = p?.photos[0]?.credit
  return (
    <article className={`tg-pc ${c.chosen ? 'is-sel' : ''} ${c.locked ? 'is-lock' : ''} ${warn ? 'is-warn' : ''} ${c.status === 'unverified' ? 'is-dim' : ''} ${flash ? 'tg-flash' : ''} is-${phase}`} style={{ '--i': order } as CSSProperties} data-place={c.id} aria-hidden={phase === 'leave' || undefined}>
      <div className="tg-pc__media">
        <button type="button" className="tg-pc__open" onClick={() => go(placeHref(c.id))} aria-label={`Xem chi tiết ${c.name}`}>
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
          <p className="tg-faint">{p?.area ?? c.area}{p?.rating ? <> · <span className="tg-mono">★ {p.rating.toFixed(1)}</span></> : null}{c.suggested ? ' · gợi ý thêm' : ''}</p>
        </div>
        {c.why.length ? (
          <ul className="tg-pc__why" aria-label="Vì sao phù hợp">
            {c.why.slice(0, 3).map((r) => <li key={r.text}><Icon name="check" size={15} />{r.text}</li>)}
          </ul>
        ) : <p className="tg-faint">Chưa có lý do rõ.</p>}
        {trade ? <p className="tg-pc__trade"><Icon name="warn" size={15} /><span><b>Đánh đổi:</b> {trade}</span></p> : <p className="tg-faint">Chưa thấy điều gì đáng ngại.</p>}
        {[...(c.tradeoffs.slice(1).map((t) => t.text)), ...notes].slice(0, 2).map((n) => <p key={n} className="tg-pc__alert"><Icon name="warn" size={14} />{n}</p>)}
        {warn && <p className="tg-pc__alert" role="status"><Icon name="warn" size={14} />{warn}</p>}
        <div className="tg-pc__facts">
          {c.visit ? <span className="tg-mono" title="Ước tính">≈ {fmtRange(c.visit.short, c.visit.long)}</span> : <span className="tg-faint">Chưa có thời lượng</span>}
          {price ? <span className="tg-mono">{price}</span> : <span className="tg-faint">Chưa có giá</span>}
          {c.location.minutes !== null && <span className="tg-mono" title="Ước tính">≈ {c.location.minutes}′ từ {c.location.center}</span>}
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
            <button type="button" className={`tg-pc__ic ${c.locked ? 'is-on' : ''}`} disabled={busy} onClick={() => act({ type: c.locked ? 'unlock' : 'lock', place_id: c.id })} aria-pressed={c.locked} title={c.locked ? 'Bỏ khóa' : 'Khóa: luôn giữ nơi này'}><Icon name={c.locked ? 'lock' : 'unlock'} size={17} /><span>Khóa</span></button>
            <button type="button" className={`tg-pc__ic ${cmp ? 'is-on' : ''}`} onClick={() => onCmp(c.id)} aria-pressed={cmp} title="So sánh"><Icon name="swap" size={17} /><span>So sánh</span></button>
            {!c.chosen && <button type="button" className="tg-pc__ic" onClick={() => onDrop(c)} title="Bỏ nơi này"><Icon name="x" size={17} /><span>Bỏ</span></button>}
          </div>
        </div>
      </div>
    </article>
  )
}
