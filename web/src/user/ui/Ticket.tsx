import * as Dialog from '@radix-ui/react-dialog'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { WHO_LABEL, type Who } from '../trip'
import { geoSearch, lodgingSuggest, searchPlaces } from '../tu/api'
import { ARRIVAL_LABEL, BUDGET_SCOPE_LABEL, CROWD_LABEL, FIELD_LABEL, NOVELTY_LABEL, PACE_LABEL, PURPOSE_LABEL, hardText, softText, valueText } from '../tu/labels'
import type { GeoHit, HardRow, LodgingHit, Row, Understanding } from '../tu/types'
import { Icon } from './icons'
import { PlaceInput } from './PlaceInput'

// One answered question: which intent it served and what it changed on the ticket.
export interface Turn {
  n: number
  intent: string
  text: string
  answer: string
  targets: string[]
}
export interface Source {
  text: string
  turns: Turn[]
}

type TripRows = Record<string, Row>
const tripOf = (u: Understanding) => Object.fromEntries(u.trip.map((r) => [r.target, r])) as TripRows

export function dateLine(u: Understanding) {
  const t = tripOf(u)
  const days = t.days?.value as number | undefined
  const bits: string[] = []
  if (t.start_date) {
    const a = new Date(t.start_date.value + 'T00:00')
    if (days) {
      const b = new Date(a)
      b.setDate(a.getDate() + days - 1)
      bits.push(a.getMonth() === b.getMonth() ? `${a.getDate()}–${b.getDate()}/${a.getMonth() + 1}` : `${a.getDate()}/${a.getMonth() + 1}–${b.getDate()}/${b.getMonth() + 1}`)
    } else bits.push(a.toLocaleDateString('vi-VN'))
  } else if (t.month) bits.push(`tháng ${t.month.value}`)
  if (days) bits.push(`${days} ngày`)
  return bits.join(' · ')
}
const whoText = (t: TripRows) => [t.people ? `${t.people.value} người` : '', t.companions ? valueText('companions', t.companions.value).toLowerCase() : ''].filter(Boolean).join(' · ')
export const timesText = (t: TripRows) => [
  t.arrive && `tới ${valueText('arrive', t.arrive.value)}`,
  t.checkin_at && `ngày đầu từ ${t.checkin_at.value}`,
  t.leave && `rời ${valueText('leave', t.leave.value)}`,
  t.checkout_at && `ngày cuối xong ${t.checkout_at.value}`,
  t.day_end && `xong trước ${t.day_end.value}`,
].filter(Boolean).join(' · ')
const paceText = (u: Understanding) =>
  [u.pace && valueText('pace', u.pace.value).toLowerCase(), u.max_leg_min && `≤ ${u.max_leg_min.value}′ mỗi chặng`, u.crowd_tolerance && `chỗ đông: ${valueText('crowd_tolerance', u.crowd_tolerance.value).toLowerCase()}`].filter(Boolean).join(' · ')
// Excluded right now by one hard limit: failed, plus unknown unless the user chose to see those flagged.
const excluding = (h: HardRow) => h.coverage.failed + (h.unknown_policy === 'flag' ? 0 : h.coverage.unknown)

export interface Line { key: string; label: string; value: string; target: string; mark?: boolean }

export function linesOf(u: Understanding): Line[] {
  const t = tripOf(u)
  const out: Line[] = []
  const date = dateLine(u)
  if (date) out.push({ key: 'dates', label: 'Ngày đi', value: date, target: t.start_date ? 'start_date' : 'days', mark: t.start_date?.mark })
  if (t.companions || t.people) out.push({ key: 'who', label: 'Đi với', value: whoText(t), target: 'companions', mark: t.companions?.mark })
  if (t.origin) out.push({ key: 'origin', label: 'Xuất phát', value: valueText('origin', t.origin.value), target: 'origin', mark: t.origin.mark })
  if (t.arrival_mode) out.push({ key: 'arrival_mode', label: 'Tới bằng', value: valueText('arrival_mode', t.arrival_mode.value), target: 'arrival_mode', mark: t.arrival_mode.mark })
  for (const w of ['inbound', 'outbound'] as const)
    if (t[w]) out.push({ key: w, label: FIELD_LABEL[w], value: valueText(w, t[w].value), target: w })
  if (t.mobility) out.push({ key: 'mobility', label: 'Phương tiện', value: [valueText('mobility', t.mobility.value), t.driver && valueText('driver', t.driver.value)].filter(Boolean).join(' · '), target: 'mobility', mark: t.mobility.mark })
  // A booked lodging is the trip's base too: one line, from the lodging.
  if (t.lodging) out.push({ key: 'lodging', label: 'Nơi lưu trú', value: valueText('lodging', t.lodging.value), target: 'lodging' })
  else if (t.base) out.push({ key: 'base', label: 'Nơi lưu trú', value: valueText('base', t.base.value), target: 'base', mark: t.base.mark })
  else if (t.lodging_booked) out.push({ key: 'lodging_booked', label: 'Nơi lưu trú', value: valueText('lodging_booked', t.lodging_booked.value), target: 'lodging_booked' })
  if (t.arrive || t.leave || t.checkin_at || t.checkout_at || t.day_end) out.push({ key: 'times', label: 'Giờ giấc', value: timesText(t), target: 'checkin_at', mark: ['arrive', 'leave', 'checkin_at', 'checkout_at', 'day_end'].some(key => t[key]?.mark) })
  if (u.purpose) out.push({ key: 'purpose', label: 'Mục đích', value: valueText('purpose', u.purpose.value), target: 'purpose', mark: u.purpose.mark })
  if (u.pace || u.max_leg_min || u.crowd_tolerance) out.push({ key: 'pace', label: 'Nhịp độ', value: paceText(u), target: 'pace', mark: u.pace?.mark })
  if (u.novelty) out.push({ key: 'novelty', label: 'Mới hay quen', value: valueText('novelty', u.novelty.value), target: 'novelty', mark: u.novelty.mark })
  if (t.care) out.push({ key: 'care', label: 'Cần lưu ý', value: valueText('care', t.care.value), target: 'care', mark: t.care.mark })
  if (t.budget_unlimited?.value === true) out.push({ key: 'budget', label: 'Ngân sách', value: 'Không giới hạn', target: 'budget_unlimited', mark: t.budget_unlimited.mark })
  else if (u.budget_vnd) out.push({ key: 'budget', label: 'Ngân sách', value: valueText('budget_vnd', u.budget_vnd.value), target: 'budget_vnd', mark: u.budget_vnd.mark })
  return out
}
// Required groups and their completion come from the backend; facts only fill their display text.
export function requiredLines(u: Understanding): Line[] {
  const facts = linesOf(u)
  const keys: Record<string, string[]> = { trip: ['dates', 'times'], companions: ['who'], mobility: ['mobility'], lodging: ['lodging', 'base', 'lodging_booked'], pace: ['pace'], budget: ['budget'], care: ['care'] }
  return (u.required ?? []).map(group => {
    const rows = facts.filter(line => keys[group.key]?.includes(line.key))
    const readback = u.readback?.lines.filter(line => line.tab === group.key && line.kind === 'said').map(line => line.text).join(' · ')
    const value = readback || rows.map(line => line.value).join(' · ') || (group.key === 'care' ? u.hard.map(hardText).join(' · ') : '')
    return { key: group.key, label: group.label, value, target: group.key, mark: rows.some(row => row.mark) }
  })
}
export function allLines(u: Understanding): Line[] {
  const have = linesOf(u)
  return [...requiredLines(u), ...have.filter(line => ['origin', 'arrival_mode', 'inbound', 'outbound', 'purpose', 'novelty'].includes(line.key))]
}
export const countRows = (u: Understanding) => linesOf(u).length + u.anchors.length + u.hard.length + u.soft.length
const unknownLabel = (k: string) => (FIELD_LABEL[k] ?? k).toLowerCase()

export interface TicketProps {
  u: Understanding
  intent: string | null
  busy: boolean
  preview: Set<string>
  source: (t: string, mark?: boolean) => Source
  onEdit: (t: string, v: string | null) => void
  onShow: () => void
}

function Seg<T extends string | number>({ label, value, options, onChange }: { label: string; value: T | null; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div className="tg-seg tg-seg--wrap" role="group" aria-label={label}>
      {options.map((o) => <button key={String(o.value)} type="button" aria-pressed={value === o.value} onClick={() => onChange(o.value)}>{o.label}</button>)}
    </div>
  )
}

export function PlaceSearch({ onPick, placeholder }: { onPick: (p: { id: string; name: string }) => void; placeholder: string }) {
  const [q, setQ] = useState('')
  const [hits, setHits] = useState<{ id: string; name: string; category: string | null }[]>([])
  useEffect(() => {
    if (q.trim().length < 2) return setHits([])
    const t = setTimeout(() => searchPlaces(q).then(setHits).catch(() => setHits([])), 180)
    return () => clearTimeout(t)
  }, [q])
  return (
    <div className="tg-picker">
      <label className="tg-picker__in"><Icon name="search" size={16} /><input className="tg-line-input" value={q} onChange={(e) => setQ(e.target.value)} placeholder={placeholder} aria-label={placeholder} /></label>
      {hits.length > 0 && (
        <ul className="tg-picker__list">
          {hits.map((p) => <li key={p.id}><button type="button" onClick={() => { onPick(p); setQ(''); setHits([]) }}><b>{p.name}</b><small className="tg-faint">{p.category}</small></button></li>)}
        </ul>
      )}
    </div>
  )
}

// Xem đầy đủ: every line with where it came from, editable in place; limits show what they cost.
export function TicketFull({ open, onClose, u, busy, preview, focus, source, onFocus, onEdit, onShow, onReset }: TicketProps & { open: boolean; onClose: () => void; focus: string | null; onFocus: (t: string | null) => void; onReset: () => void }) {
  const t = tripOf(u)
  const [chainOpen, setChainOpen] = useState<string | null>(null)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (open && focus) setTimeout(() => ref.current?.querySelector(`[data-row="${focus}"]`)?.scrollIntoView({ block: 'center', behavior: 'smooth' }), 50)
  }, [open, focus])
  const companions: Who[] = t.companions?.value ?? []
  const editors: Record<string, ReactNode> = {
    dates: (
      <div className="tg-full__edit">
        <input className="tg-input" type="date" value={t.start_date?.value ?? ''} onChange={(e) => onEdit('start_date', e.target.value || null)} aria-label="Ngày đi" />
        <Seg label="Số ngày" value={(t.days?.value as number) ?? null} options={[1, 2, 3, 4, 5].map((d) => ({ value: d, label: `${d} ngày` }))} onChange={(v) => onEdit('days', String(v))} />
      </div>
    ),
    who: (
      <div className="tg-basics__chips">
        {(Object.keys(WHO_LABEL) as Who[]).map((w) => <button key={w} type="button" className="tg-chip" aria-pressed={companions.includes(w)} onClick={() => onEdit('companions', (companions.includes(w) ? companions.filter((x) => x !== w) : [...companions, w]).join(','))}>{WHO_LABEL[w]}</button>)}
      </div>
    ),
    mobility: <Seg label="Đi lại" value={t.mobility?.value ?? null} options={[{ value: 'motorbike', label: 'Xe máy' }, { value: 'car', label: 'Ô tô' }, { value: 'walk', label: 'Đi bộ' }]} onChange={(v) => onEdit('mobility', v)} />,
    base: <PlaceSearch placeholder="Chọn nơi gần chỗ ở" onPick={(p) => onEdit('base', p.id)} />,
    origin: <PlaceInput<GeoHit> label="Nơi bạn khởi hành" placeholder="Thành phố, quận hoặc địa chỉ" icon="home" fetcher={geoSearch} row={(g) => ({ key: `${g.lat},${g.lng}`, icon: 'pin', name: g.text, sub: g.address })} onPick={(g) => onEdit('origin', JSON.stringify({ text: g.text, lat: g.lat, lng: g.lng, province: g.province }))} />,
    arrival_mode: <Seg label="Tới Đà Lạt bằng" value={t.arrival_mode?.value ?? null} options={Object.entries(ARRIVAL_LABEL).map(([value, label]) => ({ value, label }))} onChange={(v) => onEdit('arrival_mode', v)} />,
    ...Object.fromEntries((['inbound', 'outbound'] as const).map((w) => [w, (
      <div className="tg-full__edit">
        <span className="tg-faint">{t[w] ? `${t[w].value.from_point} → ${t[w].value.to_point}` : ''}</span>
        <button type="button" className="tg-btn tg-btn--sm tg-btn--ghost" onClick={() => onEdit(w, null)}>Bỏ chuyến này</button>
      </div>
    )])),
    ...Object.fromEntries((['lodging', 'lodging_booked'] as const).map((k) => [k, (
      <div className="tg-full__edit is-stack">
        <PlaceInput<LodgingHit> label="Nơi bạn lưu trú" placeholder="Tên khách sạn, homestay hoặc địa chỉ" icon="bed" fetcher={lodgingSuggest} row={(h) => ({ key: h.id ?? `${h.lat},${h.lng}`, icon: h.kind === 'address' ? 'pin' : 'bed', name: h.text, sub: h.address, rating: h.rating })} onPick={(h) => onEdit('lodging', JSON.stringify({ kind: h.kind, ...(h.id ? { id: h.id } : {}), text: h.text, lat: h.lat, lng: h.lng }))} />
        <button type="button" className="tg-chip" aria-pressed={t.lodging_booked?.value === 'no'} onClick={() => onEdit('lodging_booked', 'no')}>Chưa có, gợi ý giúp mình</button>
      </div>
    )])),
    times: (
      <div className="tg-full__edit">
        {(['checkin_at', 'checkout_at', 'day_end'] as const).map((k) => <label key={k} className="tg-full__time"><span className="tg-faint">{FIELD_LABEL[k]}</span><input className="tg-input" type="time" value={t[k]?.value ?? ''} onChange={(e) => onEdit(k, e.target.value || null)} /></label>)}
      </div>
    ),
    purpose: <Seg label="Mục đích" value={u.purpose?.value ?? null} options={Object.entries(PURPOSE_LABEL).map(([value, label]) => ({ value, label }))} onChange={(v) => onEdit('purpose', v)} />,
    pace: (
      <div className="tg-full__edit is-stack">
        <Seg label="Nhịp độ" value={u.pace?.value ?? null} options={Object.entries(PACE_LABEL).map(([value, label]) => ({ value, label }))} onChange={(v) => onEdit('pace', v)} />
        <Seg label="Mỗi chặng tối đa" value={u.max_leg_min?.value ?? null} options={[15, 30, 45, 60].map((m) => ({ value: m, label: `≤ ${m}′ mỗi chặng` }))} onChange={(v) => onEdit('max_leg_min', String(v))} />
        <Seg label="Chỗ đông" value={u.crowd_tolerance?.value ?? null} options={Object.entries(CROWD_LABEL).map(([value, label]) => ({ value, label: `Chỗ đông: ${label.toLowerCase()}` }))} onChange={(v) => onEdit('crowd_tolerance', v)} />
      </div>
    ),
    novelty: <Seg label="Mới hay quen" value={u.novelty?.value ?? null} options={Object.entries(NOVELTY_LABEL).map(([value, label]) => ({ value, label }))} onChange={(v) => onEdit('novelty', v)} />,
  }
  editors.mobility = <>{editors.mobility}{t.mobility?.value === 'car' && <Seg label="Người lái" value={t.driver?.value ?? null} options={[{ value: 'self', label: 'Tự lái' }, { value: 'hired', label: 'Thuê tài xế' }]} onChange={v => onEdit('driver', v)} />}</>
  editors.trip = <>{editors.dates}{editors.times}</>
  editors.companions = <>{editors.who}<label className="tg-full__time">Tổng số người<input className="tg-input" type="number" min="1" value={t.people?.value ?? ''} onChange={e => onEdit('people', e.target.value || null)} /></label></>
  editors.budget = <div className="tg-full__edit is-stack"><label>Ngân sách (đồng)<input className="tg-input" type="number" min="1" defaultValue={u.budget_vnd?.value?.amount ?? ''} onBlur={e => { if (e.target.value) onEdit('budget_vnd', e.target.value) }} /></label><Seg label="Phạm vi ngân sách" value={u.budget_vnd?.value?.scope ?? null} options={Object.entries(BUDGET_SCOPE_LABEL).map(([value, label]) => ({ value, label }))} onChange={v => onEdit('budget_scope', v)} /><button type="button" className="tg-chip" aria-pressed={t.budget_unlimited?.value === true} onClick={() => onEdit('budget_unlimited', t.budget_unlimited?.value === true ? 'false' : 'true')}>Không giới hạn</button></div>
  editors.care = <p className="tg-muted">Các giới hạn của cả nhóm ở phần Giới hạn cứng bên dưới. Bạn có thể kể thêm trong ô tin nhắn.</p>
  const all = allLines(u)
  return (
    <Dialog.Root open={open} onOpenChange={(o) => !o && onClose()} modal={false}>
      <Dialog.Portal>
        <Dialog.Content className="tg tg-full" aria-describedby={undefined} onInteractOutside={(e) => e.preventDefault()} onOpenAutoFocus={(e) => e.preventDefault()}>
          <header className="tg-full__head"><Dialog.Title>Vé chuyến này · Đà Lạt</Dialog.Title><Dialog.Close className="tg-link">Thu gọn</Dialog.Close></header>
          <div className={`tg-full__body${busy ? ' is-busy' : ''}`} ref={ref}>
            {all.map((r) => {
              const src = source(r.target, r.mark)
              const editing = focus === r.key || focus === r.target
              return (
                <div key={r.key} className={`tg-full__row${preview.has(r.target) ? ' tg-flash' : ''}`} data-row={r.key}>
                  <div className="tg-full__main">
                    <div><span className="tg-faint">{r.label}</span><b>{r.value || <span className="tg-faint">Chưa có</span>}</b>{r.value && <em>{src.text}</em>}</div>
                    <div className="tg-full__ops">
                      {src.turns.length > 1 && <button type="button" className="tg-link" aria-expanded={chainOpen === r.key} onClick={() => setChainOpen(chainOpen === r.key ? null : r.key)}>{chainOpen === r.key ? 'Gập' : 'Chuỗi câu hỏi'}</button>}
                      {editors[r.key] && <button type="button" className="tg-link" onClick={() => onFocus(editing ? null : r.key)}>{editing ? 'Xong' : r.value ? 'Sửa' : 'Trả lời'}</button>}
                    </div>
                  </div>
                  {chainOpen === r.key && (
                    <ul className="tg-full__sub">
                      {src.turns.map((x) => <li key={x.n}><span>{x.text}</span><b>{x.answer}</b><span /></li>)}
                      <li className="tg-faint tg-full__note">Chỉ dòng kết luận được dùng để gợi ý.</li>
                    </ul>
                  )}
                  {editing && editors[r.key] && <fieldset className="tg-full__editor" disabled={busy}>{editors[r.key]}</fieldset>}
                </div>
              )
            })}
            {u.budget_vnd && <p className="tg-faint tg-full__hint">Ngân sách {valueText('budget_vnd', u.budget_vnd.value)} · chưa kiểm được bằng dữ liệu giá.</p>}

            {u.anchors.length > 0 && (
              <>
                <h3 className="tg-full__sec">Nhất định đến</h3>
                {u.anchors.map((a) => (
                  <div key={a.target} className="tg-full__row">
                    <div className="tg-full__main">
                      <div><b>{a.name ?? a.text}</b><em>{a.state === 'missing' ? 'chưa tìm thấy, không dùng để xếp lịch' : a.priority === 'want' ? 'bỏ được nếu thiếu giờ' : 'giữ trong mọi phương án'}</em></div>
                      <div className="tg-full__ops"><button type="button" className="tg-link" onClick={() => onEdit(a.target, null)}>Bỏ</button></div>
                    </div>
                  </div>
                ))}
              </>
            )}

            <h3 className="tg-full__sec">Giới hạn cứng</h3>
            {u.hard.length === 0 && <p className="tg-faint">Chưa có giới hạn nào.</p>}
            {u.hard.map((h) => (
              <div key={h.target} className={`tg-full__row tg-full__limit${preview.has(h.target) ? ' tg-flash' : ''}`}>
                <div className="tg-full__main">
                  <div><span className="tg-stamp"><Icon name="lock" size={14} />{hardText(h)}</span><em>{source(h.target).text}</em><b className="tg-warn-t">{h.unknown_policy === 'flag' ? `đã nới · xem cả ${h.coverage.unknown} nơi chưa rõ` : `đang loại ${excluding(h)} nơi`}</b></div>
                  <div className="tg-full__ops">
                    <button type="button" className="tg-btn tg-btn--sm tg-btn--ghost" onClick={() => onEdit(h.target, h.unknown_policy === 'flag' ? 'exclude' : 'flag')}>{h.unknown_policy === 'flag' ? 'Siết lại' : 'Nới'}</button>
                    <button type="button" className="tg-btn tg-btn--sm tg-btn--ghost" onClick={() => onEdit(h.target, null)}>Bỏ</button>
                  </div>
                </div>
              </div>
            ))}

            <h3 className="tg-full__sec">Sở thích mềm</h3>
            {u.soft.length === 0 && <p className="tg-faint">Chưa có sở thích nào.</p>}
            <ul className="tg-full__soft">
              {u.soft.map((s) => (
                <li key={s.target}>
                  <button type="button" className="tg-chip tg-chip--dash" title="Đổi thích / tránh" onClick={() => onEdit(s.target, s.weight === 'love' ? 'avoid' : 'love')}>{softText(s)}</button>
                  <em>{source(s.target, s.mark).text}</em>
                  <button type="button" className="tg-link" onClick={() => onEdit(s.target, null)}>Bỏ</button>
                </li>
              ))}
            </ul>

            {(u.unknowns.length > 0 || u.unmapped.length > 0) && (
              <>
                <h3 className="tg-full__sec">Còn chưa rõ</h3>
                <ul className="tg-full__soft">
                  {u.unknowns.map((k) => <li key={k}><Icon name="warn" size={14} /><em>{unknownLabel(k)}</em></li>)}
                  {u.unmapped.map((x) => <li key={x.target}><Icon name="info" size={14} /><em>“{x.phrase}” · chưa kiểm được bằng dữ liệu, chỉ nêu trong lời giải thích</em><button type="button" className="tg-link" onClick={() => onEdit(x.target, null)}>Bỏ</button></li>)}
                </ul>
              </>
            )}
            <p className="tg-faint tg-full__hint">Số nơi đang hợp: <b className="tg-mono">{u.matching.toLocaleString('vi-VN')}</b> trên {u.total.toLocaleString('vi-VN')}</p>
          </div>
          <footer className="tg-full__foot"><button type="button" className="tg-stub" disabled={busy} onClick={onShow}>Bắt đầu tìm <Icon name="arrow" size={18} /></button><button type="button" className="tg-link tg-link--quiet" onClick={onReset}>Đặt lại toàn bộ</button></footer>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
