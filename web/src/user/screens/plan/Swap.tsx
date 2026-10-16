import { useMemo, useState } from 'react'
import { info, priceText } from '../../lib'
import type { ItineraryDay } from '../../planning/types'
import { PlacePhoto } from '../../ui/common'
import { Icon } from '../../ui/icons'
import { FlowBar } from '../../ui/Shell'
import type { Candidate } from './candidates'
import { norm, shortDate } from './shared'

// Mẫu ui_mock_for_design/designs/itinerary (màn tìm nơi): search on top, filters on the left, places on the right.
// "Chọn" only asks for a preview of the change; the day is not touched until the preview is applied.

export function Swap({ day, replacing, candidates, people, busy, onOverview, onDay, onPick, onOpen, onMore }: {
  day: ItineraryDay; replacing: string | null; candidates: Candidate[]; people: number | null; busy: boolean
  onOverview: () => void; onDay: () => void; onPick: (c: Candidate) => void; onOpen: (id: string) => void; onMore: () => void
}) {
  const [q, setQ] = useState('')
  const [draft, setDraft] = useState('')
  const [cat, setCat] = useState('all')
  const cats = useMemo(() => {
    const n = new Map<string, number>()
    for (const c of candidates) { const k = info(c.id)?.category; if (k) n.set(k, (n.get(k) ?? 0) + 1) }
    return [...n.entries()].sort((a, b) => b[1] - a[1])
  }, [candidates])
  const hits = candidates.filter((c) => (cat === 'all' || info(c.id)?.category === cat) && (!q || norm(`${c.name} ${info(c.id)?.category ?? ''} ${info(c.id)?.area ?? ''}`).includes(norm(q))))
  const target = replacing ? info(replacing)?.name ?? replacing : null
  return (
    <>
      <FlowBar step="plan" />
      <div className="tg-it-crumb">
        <button type="button" className="tg-it-crumb__back" aria-label="Về ngày đang sửa" onClick={onDay}><Icon name="arrowLeft" size={18} /></button>
        <button type="button" onClick={onOverview}>Tổng quan</button><Icon name="chevronRight" size={14} />
        <button type="button" onClick={onDay}>Ngày {day.day}</button><Icon name="chevronRight" size={14} />
        <strong>{replacing ? 'Đổi trải nghiệm' : 'Thêm trải nghiệm'}</strong>
      </div>
      <main className="tg-it-find">
        <form className="tg-it-search" role="search" onSubmit={(e) => { e.preventDefault(); setQ(draft.trim()) }}>
          <Icon name="search" size={19} />
          <input aria-label="Tìm địa điểm tại Đà Lạt" placeholder="Tìm trải nghiệm ở Đà Lạt" value={draft} onChange={(e) => { setDraft(e.target.value); setQ(e.target.value.trim()) }} />
          <button type="submit" className="tg-it-search__go" aria-label="Tìm kiếm"><Icon name="search" size={18} /></button>
        </form>
        <div className="tg-it-find__ctx">
          <span>{target ? <>Thay <strong>{target}</strong> trong ngày {day.day}</> : <>Thêm vào <strong>ngày {day.day} · {shortDate(day.date, day.day)}</strong></>}</span>
          <span>{candidates.length} nơi chưa có trong lịch</span>
        </div>
        <div className="tg-it-find__cols">
          <aside className="tg-it-filters">
            <div className="tg-it-fcard">
              <div className="tg-it-frow"><Icon name="pin" size={18} /><div><small>Điểm đến</small><b>Đà Lạt, Việt Nam</b></div></div>
              <div className="tg-it-frow"><Icon name="calendar" size={18} /><div><small>Ngày ghé</small><b>{shortDate(day.date, day.day)}</b></div></div>
              <div className="tg-it-frow"><Icon name="user" size={18} /><div><small>Đi cùng</small><b>{people ? `${people} người` : 'Chưa rõ số người'}</b></div></div>
            </div>
            {cats.length > 1 && <div className="tg-it-fcard">
              <h3>Loại trải nghiệm</h3>
              {[['all', 'Tất cả', candidates.length] as const, ...cats.map(([k, n]) => [k, k, n] as const)].map(([k, label, n]) => (
                <label key={k}><input type="radio" name="tg-it-cat" checked={cat === k} onChange={() => setCat(k)} />{label}<small>{n}</small></label>
              ))}
            </div>}
            <p className="tg-it-small">Chỉ dùng nơi bạn đã chọn hoặc nơi dự phòng đã được kiểm tra. Muốn thêm nơi khác, <button type="button" className="tg-link" onClick={onMore}>quay lại chọn nơi</button>.</p>
          </aside>
          <div className="tg-it-results" aria-live="polite">
            {hits.map((c, i) => {
              const p = info(c.id)
              const price = priceText(p?.price)
              return (
                <article key={c.id} className="tg-it-result" style={{ ['--i' as string]: i }}>
                  <button type="button" className="tg-it-result__ph" aria-label={`Xem chi tiết ${c.name}`} onClick={() => onOpen(c.id)}><PlacePhoto id={c.id} name={c.name} sizes="160px" /></button>
                  <div className="tg-it-result__copy">
                    <h2>{c.name}</h2>
                    <p>{[p?.category, p?.area].filter(Boolean).join(' · ')}</p>
                    <div className="tg-it-rate">{p?.rating != null && <><Icon name="star" size={15} /><b>{p.rating.toFixed(1)}</b>{p.reviews != null && <span>({p.reviews.toLocaleString('vi-VN')} đánh giá)</span>}</>}</div>
                    <button type="button" className="tg-it-textbtn" onClick={() => onOpen(c.id)}><Icon name="pin" size={14} />Xem chi tiết</button>
                    <div className="tg-it-result__meta">{c.forThis && <b className="tg-tag">Hợp để thay {target}</b>} {c.why ?? (c.from === 'selection' ? 'Nơi bạn đã chọn, đang chưa có trong lịch' : 'Dự phòng đã kiểm tra')}</div>
                    <div className="tg-it-result__act">
                      <span className="tg-faint">{price ? `Giá tham khảo ${price}` : 'Chưa có giá xác nhận'}</span>
                      <button type="button" className="tg-btn tg-btn--primary tg-btn--sm" disabled={busy} onClick={() => onPick(c)}><Icon name={replacing ? 'swap' : 'plus'} size={15} />{replacing ? 'Chọn thay thế' : 'Thêm vào lịch'}</button>
                    </div>
                  </div>
                </article>
              )
            })}
            {!hits.length && <div className="tg-it-empty">{candidates.length ? 'Không có nơi phù hợp với bộ lọc này. Thử đổi loại trải nghiệm hoặc từ khóa.' : 'Chưa còn nơi nào để đổi hay thêm. Quay lại bước chọn nơi để thêm nơi mới.'}</div>}
          </div>
        </div>
      </main>
    </>
  )
}
