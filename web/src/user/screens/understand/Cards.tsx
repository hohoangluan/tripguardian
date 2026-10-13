import { useState, type CSSProperties } from 'react'
import { geoSearch, lodgingSuggest } from '../../tu/api'
import type { Card, Chip, GeoHit, LodgingHit, VibeKind, VibeParams } from '../../tu/types'
import { Icon } from '../../ui/icons'
import { PlaceInput, type InputRow } from '../../ui/PlaceInput'
import { openPlace } from '../../ui/PlaceSheet'
import { PlaceSearch } from '../../ui/Ticket'

// The cards a bot turn may carry (docs/UI_SPEC_USER_WEB.md Trang 3). Every card stays answerable later in the chat;
// every card has a way out: "Chưa chắc", "Bỏ qua", or typing in the box below. Places and photos come from the corpus.

export type Answer = (input: { chips?: string[]; value?: string | null }, shown: string) => void

const geoRow = (g: GeoHit): InputRow => ({
  key: `${g.lat},${g.lng}`, icon: 'pin', name: g.text,
  sub: g.province && !g.address.includes(g.province) && g.province !== g.text ? [g.address, g.province].filter(Boolean).join(' · ') : g.address,
})
const lodgingRow = (h: LodgingHit): InputRow => ({
  key: h.id ?? `${h.lat},${h.lng}`, icon: h.kind === 'address' ? 'pin' : /homestay|villa|nhà/i.test(h.text) ? 'home' : 'bed', name: h.text, sub: h.address, rating: h.rating,
})

function Exits({ card, busy, onAnswer, skip = true }: { card: Card; busy: boolean; onAnswer: Answer; skip?: boolean }) {
  if (!card.exits) return null
  return (
    <>
      <button type="button" className="tg-cx__ghost" disabled={busy} onClick={() => onAnswer({ chips: ['unsure'] }, 'Chưa chắc')}>Chưa chắc</button>
      {skip && <button type="button" className="tg-cx__ghost" disabled={busy} onClick={() => onAnswer({ chips: ['skip'] }, 'Bỏ qua')}>Bỏ qua</button>}
    </>
  )
}

// A bank question: tap one option (sent at once), or several then "Xong"; date and place inputs where asked.
export function QuickReply({ card, busy, onAnswer }: { card: Card; busy: boolean; onAnswer: Answer }) {
  const [picked, setPicked] = useState<string[]>([])
  const [date, setDate] = useState('')
  const many = (c: Chip) => card.multi && !card.single_rows.includes(c.row ?? '')
  const toggle = (c: Chip) => {
    if (busy) return
    if (!card.multi && card.input !== 'date') return onAnswer({ chips: [c.id] }, c.label)
    setPicked((p) => {
      if (p.includes(c.id)) return p.filter((x) => x !== c.id)
      const rest = many(c) ? p : p.filter((id) => card.chips.find((x) => x.id === id)?.row !== c.row)
      return [...rest, c.id]
    })
  }
  const rows: { row: string | null; chips: Chip[] }[] = []
  for (const c of card.chips) {
    const r = rows.find((x) => x.row === c.row)
    if (r) r.chips.push(c)
    else rows.push({ row: c.row, chips: [c] })
  }
  const chips = card.input === 'lodging' ? [] : rows
  const label = card.chips.filter((c) => picked.includes(c.id)).map((c) => c.label).join(', ')
  return (
    <div className="tg-cx__qr-wrap">
      {chips.map((r) => (
        <div key={r.row ?? '_'} className="tg-cx__qr" role="group" aria-label={r.row ?? 'Lựa chọn'}>
          {r.row && <span className="tg-cx__qr-row">{r.row}</span>}
          {r.chips.map((c) => (
            <button key={c.id} type="button" className={picked.includes(c.id) ? 'is-on' : ''} aria-pressed={card.multi ? picked.includes(c.id) : undefined} disabled={busy} onClick={() => toggle(c)}>
              {card.multi && <i className="tg-cx__mark" aria-hidden="true">{picked.includes(c.id) && <Icon name="check" size={11} />}</i>}
              {c.label}
              {c.effect ? <small className={c.effect < 0 ? 'is-down' : 'is-up'} title="Số nơi đang hợp đổi chừng này nếu chỉ chọn ý này">{c.effect > 0 ? '+' : '−'}{Math.abs(c.effect).toLocaleString('vi-VN')}</small> : null}
            </button>
          ))}
        </div>
      ))}
      {card.input === 'date' && <label className="tg-cx__date"><span>Ngày đến</span><input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>}
      {card.input === 'place' && <PlaceSearch placeholder="Tìm một nơi gần chỗ ở" onPick={(p) => onAnswer({ value: p.id }, p.name)} />}
      {card.input === 'geo' && (
        <PlaceInput<GeoHit> label="Nơi bạn khởi hành" placeholder="Thành phố, quận hoặc địa chỉ" icon="home" disabled={busy} fetcher={geoSearch} row={geoRow}
          onPick={(g) => onAnswer({ value: JSON.stringify({ text: g.text, lat: g.lat, lng: g.lng, province: g.province }) }, g.text)} />
      )}
      {card.input === 'lodging' && (
        <>
          <PlaceInput<LodgingHit> label="Nơi bạn lưu trú" placeholder="Tên khách sạn, homestay hoặc địa chỉ" icon="bed" disabled={busy} fetcher={lodgingSuggest} row={lodgingRow}
            onPick={(h) => onAnswer({ value: JSON.stringify({ kind: h.kind, ...(h.id ? { id: h.id } : {}), text: h.text, lat: h.lat, lng: h.lng }) }, h.text)} />
          <div className="tg-cx__qr">{card.chips.map((c) => <button key={c.id} type="button" disabled={busy} onClick={() => onAnswer({ chips: [c.id] }, c.label)}>{c.label}</button>)}</div>
        </>
      )}
      <div className="tg-cx__qr">
        {(card.multi || card.input === 'date') && (
          <button type="button" className="tg-cx__done" disabled={busy || !(picked.length || date)}
            onClick={() => onAnswer({ chips: picked, value: date || null }, date ? new Date(date + 'T00:00').toLocaleDateString('vi-VN') : label)}>Xong</button>
        )}
        <Exits card={card} busy={busy} onAnswer={onAnswer} skip={card.input === 'geo' || card.input === 'lodging' || card.multi} />
      </div>
    </div>
  )
}

// guess_confirm: the signs the agent read a look as. Take one out, put it back, add one; then see the kinds.
export function GuessConfirm({ card, busy, onAnswer, onPhoto }: { card: Card; busy: boolean; onAnswer: Answer; onPhoto: () => void }) {
  const p = card.params as VibeParams
  const [cues, setCues] = useState(() => [...(p.cues ?? []).map((l) => ({ l, off: false })), ...(p.removed ?? []).map((l) => ({ l, off: true }))])
  const [adding, setAdding] = useState(false)
  const [draft, setDraft] = useState('')
  const [open, setOpen] = useState(false)
  const add = () => {
    const v = draft.trim().toLowerCase()
    if (v && !cues.some((c) => c.l === v)) setCues((x) => [...x, { l: v, off: false }])
    setDraft('')
    setAdding(false)
  }
  const kept = cues.filter((c) => !c.off)
  return (
    <div className="tg-cx__card">
      <h4 className="tg-cx__kick">Dấu hiệu mình sẽ tìm</h4>
      <div className="tg-cx__cues">
        {cues.map((c, i) => (
          <span key={c.l} className={`tg-cx__cue ${c.off ? 'is-off' : ''}`} style={{ '--d': `${i * 90}ms` } as CSSProperties}>
            {c.l}
            <button type="button" aria-label={c.off ? `Thêm lại ${c.l}` : `Bỏ ${c.l}`} disabled={busy} onClick={() => setCues((x) => x.map((y) => (y.l === c.l ? { ...y, off: !y.off } : y)))}>{c.off ? <Icon name="plus" size={12} /> : <Icon name="x" size={12} />}</button>
          </span>
        ))}
        {adding ? (
          <span className="tg-cx__cue is-add"><input autoFocus maxLength={40} value={draft} placeholder="dấu hiệu" onChange={(e) => setDraft(e.target.value)} onBlur={add}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add() } if (e.key === 'Escape') { setDraft(''); setAdding(false) } }} /></span>
        ) : <button type="button" className="tg-cx__cue is-add" disabled={busy} onClick={() => setAdding(true)}>+ thêm dấu hiệu</button>}
      </div>
      {!!p.kinds?.length && (
        <>
          <h4 className="tg-cx__kick">Có vài kiểu {p.phrase ? `“${p.phrase}”` : ''} khác nhau</h4>
          <div className="tg-cx__peek">
            {p.kinds.map((k) => (
              <button type="button" key={k.id} className="tg-cx__peek-i" onClick={() => k.photos[0] && openPlace(k.photos[0].place_id)} aria-label={`Xem ${k.photos[0]?.name ?? k.label}`}>
                {k.photos[0] ? <img src={k.photos[0].url} alt="" loading="lazy" /> : <span className="tg-cx__peek-ph" />}
                <span><b>{k.label}</b><small>{k.count.toLocaleString('vi-VN')} nơi</small></span>
              </button>
            ))}
          </div>
        </>
      )}
      <div className="tg-cx__foot">
        <button type="button" className="tg-cx__primary" disabled={busy || !kept.length}
          onClick={() => onAnswer({ value: JSON.stringify(cues.map((c) => ({ label: c.l, removed: c.off }))) }, 'Đúng rồi, xem ảnh các kiểu')}>
          {p.kinds && p.kinds.length >= 2 ? 'Đúng rồi, xem ảnh các kiểu' : 'Đúng rồi'}
        </button>
        <button type="button" className="tg-cx__link" disabled={busy} onClick={onPhoto}>Gửi ảnh mẫu thay vì chọn</button>
        <Exits card={card} busy={busy} onAnswer={onAnswer} />
      </div>
      {!!p.sources?.length && (
        <div className={`tg-cx__src ${open ? 'is-open' : ''}`}>
          <button type="button" className="tg-cx__src-h" aria-expanded={open} onClick={() => setOpen((o) => !o)}>Nguồn mình đã đọc <Icon name="chevronDown" size={14} /></button>
          {open && (
            <>
              <ul>{p.sources.map((s) => <li key={s.url}><a href={s.url} target="_blank" rel="noopener noreferrer"><b>{s.domain}</b> — {s.title}</a></li>)}</ul>
              <p>Nguồn web chỉ dùng để hiểu từ {p.phrase ? `“${p.phrase}”` : 'của bạn'}. Nơi được gợi ý luôn lấy từ dữ liệu đã kiểm chứng.</p>
            </>
          )}
        </div>
      )}
    </div>
  )
}

function KindTile({ k, on, i, onToggle }: { k: VibeKind; on: boolean; i: number; onToggle: () => void }) {
  const [big, ...small] = k.photos
  return (
    <div className={`tg-cx__opt ${on ? 'is-on' : ''}`} style={{ '--i': i } as CSSProperties}>
      <div className="tg-cx__pics">
        {big && <button type="button" className="tg-cx__pic is-big" onClick={() => openPlace(big.place_id)} aria-label={`Xem ${big.name}`}><img src={big.url} alt={big.name} loading="lazy" /></button>}
        {small.slice(0, 2).map((ph) => <button type="button" key={ph.url} className="tg-cx__pic" onClick={() => openPlace(ph.place_id)} aria-label={`Xem ${ph.name}`}><img src={ph.url} alt={ph.name} loading="lazy" /></button>)}
        <span className="tg-cx__ring" aria-hidden="true"><Icon name="check" size={16} /></span>
      </div>
      <button type="button" className="tg-cx__opt-b" aria-pressed={on} onClick={onToggle}>
        <b>{k.label}</b>
        <span>{k.places.map((p) => p.name).join(', ')}</span>
        <small>{k.count.toLocaleString('vi-VN')} nơi</small>
      </button>
    </div>
  )
}

// image_choice: the kinds of a look as real places' photos. Several may be picked; "Không kiểu nào giống" ranks none.
export function ImageChoice({ card, busy, onAnswer, onPhoto }: { card: Card; busy: boolean; onAnswer: Answer; onPhoto: () => void }) {
  const p = card.params as VibeParams
  const kinds = p.kinds ?? []
  const [on, setOn] = useState<string[]>(p.chosen ?? [])
  const toggle = (id: string) => setOn((x) => (x.includes(id) ? x.filter((y) => y !== id) : [...x, id]))
  return (
    <div className="tg-cx__card is-flat">
      <div className="tg-cx__opts">
        {kinds.map((k, i) => <KindTile key={k.id} k={k} i={i} on={on.includes(k.id)} onToggle={() => toggle(k.id)} />)}
        <button type="button" className="tg-cx__upload" disabled={busy} onClick={onPhoto}>
          <Icon name="image" size={34} />
          <b>Gửi ảnh kiểu bạn thích</b>
          <small>kéo thả hoặc chọn tệp</small>
        </button>
      </div>
      <div className="tg-cx__foot">
        <button type="button" className="tg-cx__primary" disabled={busy || !on.length}
          onClick={() => onAnswer({ chips: on }, kinds.filter((k) => on.includes(k.id)).map((k) => k.label).join(', '))}>Xong{on.length ? ` (${on.length})` : ''}</button>
        <button type="button" className="tg-cx__ghost" disabled={busy} onClick={() => onAnswer({ chips: ['none'] }, 'Không kiểu nào giống')}>Không kiểu nào giống</button>
        <Exits card={card} busy={busy} onAnswer={onAnswer} />
      </div>
    </div>
  )
}

// place_pick: the user's photo looks like one corpus place.
export function PhotoPick({ card, busy, onAnswer }: { card: Card; busy: boolean; onAnswer: Answer }) {
  const place = (card.params as VibeParams).place!
  return (
    <div className="tg-cx__card">
      <button type="button" className="tg-cx__pick" onClick={() => openPlace(place.id)}>
        {place.photo && <img src={place.photo} alt={place.name} />}
        <span><b>{place.name}</b><small>Xem chi tiết nơi này</small></span>
      </button>
      <div className="tg-cx__foot">
        {card.chips.map((c, i) => <button key={c.id} type="button" className={i === 0 ? 'tg-cx__primary' : 'tg-cx__ghost'} disabled={busy} onClick={() => onAnswer({ chips: [c.id] }, c.label)}>{c.label}</button>)}
      </div>
    </div>
  )
}

export function CardView({ card, busy, onAnswer, onPhoto }: { card: Card; busy: boolean; onAnswer: Answer; onPhoto: () => void }) {
  if (card.input === 'cues') return <GuessConfirm card={card} busy={busy} onAnswer={onAnswer} onPhoto={onPhoto} />
  if (card.input === 'kinds') return <ImageChoice card={card} busy={busy} onAnswer={onAnswer} onPhoto={onPhoto} />
  if (card.input === 'photo_pick') return <PhotoPick card={card} busy={busy} onAnswer={onAnswer} />
  return <QuickReply card={card} busy={busy} onAnswer={onAnswer} />
}
