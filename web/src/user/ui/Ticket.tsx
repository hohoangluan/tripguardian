import * as Dialog from '@radix-ui/react-dialog'
import * as Popover from '@radix-ui/react-popover'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { WHO_LABEL, type Who } from '../trip'
import { geoSearch, lodgingSuggest, searchPlaces } from '../tu/api'
import { ARRIVAL_LABEL, CROWD_LABEL, FIELD_LABEL, NOVELTY_LABEL, PACE_LABEL, PURPOSE_LABEL, hardText, monthText, softGroups, softText, valueText } from '../tu/labels'
import type { GeoHit, HardRow, LodgingHit, Row, Understanding } from '../tu/types'
import { Icon } from './icons'
import { PlaceInput, geoRow, lodgingRow } from './PlaceInput'

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
  } else if (t.month) bits.push(monthText(t.month.value, t.month_part?.value))
  if (days) bits.push(t.nights ? `${days} ngày ${t.nights.value} đêm` : `${days} ngày`)
  return bits.join(' · ')
}
const whoText = (t: TripRows) => [t.people ? `${t.people.value} người` : '', t.companions ? valueText('companions', t.companions.value).toLowerCase() : ''].filter(Boolean).join(' · ')
// Without a lodging there is no room to check into: the hours are when the first day starts and the last day ends.
const timesText = (t: TripRows) => [t.checkin_at && `${t.lodging_booked?.value === 'no' ? 'bắt đầu' : 'nhận phòng'} ${t.checkin_at.value}`, t.checkout_at && `${t.lodging_booked?.value === 'no' ? 'kết thúc' : 'trả phòng'} ${t.checkout_at.value}`, t.day_end && `xong trước ${t.day_end.value}`].filter(Boolean).join(' · ')
const paceText = (u: Understanding) =>
  [u.pace && valueText('pace', u.pace.value).toLowerCase(), u.max_leg_min && `≤ ${u.max_leg_min.value}′ mỗi chặng`].filter(Boolean).join(' · ')
// Excluded right now by one hard limit: failed, plus unknown unless the user chose to see those flagged.
const excluding = (h: HardRow) => h.coverage.failed + (h.unknown_policy === 'flag' ? 0 : h.coverage.unknown)

interface Line { key: string; label: string; value: string; target: string; mark?: boolean }

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
  if (t.mobility) out.push({ key: 'mobility', label: 'Phương tiện', value: valueText('mobility', t.mobility.value), target: 'mobility', mark: t.mobility.mark })
  // A booked lodging is the trip's base too: one line, from the lodging.
  if (t.lodging) out.push({ key: 'lodging', label: 'Chỗ ở', value: valueText('lodging', t.lodging.value), target: 'lodging' })
  else if (t.base) out.push({ key: 'base', label: 'Chỗ ở', value: valueText('base', t.base.value), target: 'base', mark: t.base.mark })
  else if (t.lodging_booked) out.push({ key: 'lodging_booked', label: 'Chỗ ở', value: valueText('lodging_booked', t.lodging_booked.value), target: 'lodging_booked' })
  if (t.checkin_at || t.checkout_at || t.day_end) out.push({ key: 'times', label: 'Giờ giấc', value: timesText(t), target: 'checkin_at' })
  if (u.purpose) out.push({ key: 'purpose', label: 'Mục đích', value: valueText('purpose', u.purpose.value), target: 'purpose', mark: u.purpose.mark })
  if (u.liked_groups) out.push({ key: 'liked_groups', label: 'Muốn đi', value: valueText('liked_groups', u.liked_groups.value), target: 'liked_groups', mark: u.liked_groups.mark })
  if (u.pace || u.max_leg_min) out.push({ key: 'pace', label: 'Nhịp độ', value: paceText(u), target: 'pace', mark: u.pace?.mark })
  // Crowds are their own line: "tránh chỗ đông" is not a pace, and pace may still be unknown.
  if (u.crowd_tolerance) out.push({ key: 'crowd', label: 'Chỗ đông', value: valueText('crowd_tolerance', u.crowd_tolerance.value), target: 'crowd_tolerance', mark: u.crowd_tolerance.mark })
  if (u.novelty) out.push({ key: 'novelty', label: 'Mới hay quen', value: valueText('novelty', u.novelty.value), target: 'novelty', mark: u.novelty.mark })
  if (u.budget_vnd) out.push({ key: 'budget', label: 'Ngân sách', value: valueText('budget_vnd', u.budget_vnd.value), target: 'budget_vnd', mark: u.budget_vnd.mark })
  return out
}
export const countRows = (u: Understanding) => linesOf(u).length + u.anchors.length + u.hard.length + u.soft.length
const unknownLabel = (k: string) => (FIELD_LABEL[k] ?? k).toLowerCase()

interface TicketProps {
  u: Understanding
  intent: string | null
  busy: boolean
  preview: Set<string>
  source: (t: string, mark?: boolean) => Source
  onEdit: (t: string, v: string | null) => void
  onShow: () => void
}

export function Ticket({ u, intent, busy, preview, source, onEdit, onShow, onOpen, compact = false }: TicketProps & { onOpen: (target: string | null) => void; compact?: boolean }) {
  const rows = linesOf(u)
  const live = (target: string) => (preview.has(target) ? ' tg-flash' : '')
  return (
    <aside className={`tg-ticket ${compact ? 'is-compact' : ''}`} aria-label="Vé chuyến này" aria-busy={busy}>
      <div className="tg-ticket__perf" aria-hidden="true" />
      <div className="tg-ticket__scroll">
        <h2 className="tg-ticket__h">Vé chuyến này · Đà Lạt</h2>
        <dl className="tg-ticket__rows">
          {rows.map((r) => <div key={r.key} className={`tg-ticket__row${live(r.target)}`}><dt>{r.label}</dt><dd>{r.value}</dd></div>)}
          {intent && intent !== 'Sẵn sàng' && <div className="tg-ticket__row is-asking"><dt>{intent}</dt><dd>đang hỏi</dd></div>}
          {!rows.length && !intent && <p className="tg-faint">Chưa ghi gì. Kể vài dòng về chuyến đi là vé tự điền.</p>}
        </dl>
        {u.anchors.length > 0 && (
          <div className="tg-ticket__sec">
            <h3>Nhất định đến</h3>
            {u.anchors.map((a) => <div key={a.target} className="tg-ticket__unclear"><span><Icon name={a.state === 'matched' ? 'lock' : 'warn'} size={14} /> {a.name ?? a.text}{a.state === 'choose' && ' · cần bạn chọn'}{a.state === 'missing' && ' · chưa tìm thấy'}</span></div>)}
          </div>
        )}
        {u.hard.length > 0 && (
          <div className="tg-ticket__sec">
            <h3>Giới hạn cứng</h3>
            {u.hard.map((h) => <div key={h.target} className={`tg-stamp${live(h.target)}`}><Icon name="lock" size={14} /><span>{hardText(h)}</span></div>)}
          </div>
        )}
        {u.soft.length > 0 && (
          <div className="tg-ticket__sec">
            <h3>Sở thích mềm</h3>
            <div className="tg-ticket__chips">
              {softGroups(u.soft).map((g) => (
                <span key={g.key} className={`tg-chip tg-chip--dash${live('soft')}`} title={g.rows[0].like ? `Mình suy từ nét của ${g.rows[0].like}` : source(g.rows[0].target, g.rows[0].mark).text}>
                  {g.text}
                  <button type="button" className="tg-chip__x" aria-label={`Bỏ ${g.text}`} onClick={() => g.rows.forEach((s) => onEdit(s.target, null))}><Icon name="x" size={12} /></button>
                </span>
              ))}
            </div>
          </div>
        )}
        {rows.length > 0 && (u.unknowns.length > 0 || u.safety_pending) && (
          <div className="tg-ticket__sec">
            <h3>Còn chưa rõ</h3>
            {u.safety_pending && <div className="tg-ticket__unclear"><span>một câu về an toàn</span></div>}
            {u.unknowns.slice(0, 4).map((k) => <div key={k} className="tg-ticket__unclear"><span>{unknownLabel(k)}</span><button type="button" onClick={() => onOpen(k)} className="tg-link">Trả lời</button></div>)}
            {u.unknowns.length > 4 && <button type="button" className="tg-link" onClick={() => onOpen(null)}>và {u.unknowns.length - 4} điều nữa</button>}
          </div>
        )}
      </div>
      <footer className="tg-ticket__foot">
        <p className="tg-faint">đã ghi <b className="tg-mono">{countRows(u)}</b> mục</p>
        <button type="button" className="tg-stub" disabled={busy} onClick={onShow}>Bắt đầu tìm <Icon name="arrow" size={18} /></button>
        <button type="button" className="tg-link tg-ticket__full" onClick={() => onOpen(null)}>Xem đầy đủ</button>
      </footer>
    </aside>
  )
}

// The trip ticket as a small icon next to the profile; the ticket itself opens on click.
export function TicketMenu(props: TicketProps & { onOpen: (target: string | null) => void }) {
  const [open, setOpen] = useState(false)
  const count = countRows(props.u)
  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button type="button" className="tg-tbtn" aria-label={`Vé chuyến này, đã ghi ${count} mục. Bấm để xem và sửa`} title="Xem và sửa vé chuyến"><Icon name="ticket" size={19} /><span className="tg-tbtn__l">Vé chuyến</span><b key={count} className="tg-tbtn__n tg-mono">{count}</b></button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content className="tg tg-tpop" align="end" sideOffset={10} collisionPadding={16}>
          <Ticket {...props} compact onShow={() => { setOpen(false); props.onShow() }} onOpen={(t) => { setOpen(false); props.onOpen(t) }} />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
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
      <div className="tg-full__edit is-stack">
        <input className="tg-input" type="date" value={t.start_date?.value ?? ''} onChange={(e) => onEdit('start_date', e.target.value || null)} aria-label="Ngày đi" />
        <Seg label="Số ngày" value={(t.days?.value as number) ?? null} options={[1, 2, 3, 4, 5].map((d) => ({ value: d, label: `${d} ngày` }))} onChange={(v) => onEdit('days', String(v))} />
        {t.days && <Seg label="Số đêm" value={(t.nights?.value as number) ?? null} options={Array.from({ length: Math.min(7, t.days.value) + 1 }, (_, n) => ({ value: n, label: `${n} đêm` }))} onChange={(v) => onEdit('nights', String(v))} />}
      </div>
    ),
    who: (
      <div className="tg-basics__chips">
        {(Object.keys(WHO_LABEL) as Who[]).map((w) => <button key={w} type="button" className="tg-chip" aria-pressed={companions.includes(w)} onClick={() => onEdit('companions', (companions.includes(w) ? companions.filter((x) => x !== w) : [...companions, w]).join(','))}>{WHO_LABEL[w]}</button>)}
      </div>
    ),
    mobility: <Seg label="Đi lại" value={t.mobility?.value ?? null} options={[{ value: 'motorbike', label: 'Xe máy' }, { value: 'car', label: 'Ô tô' }, ...(t.arrival_mode && t.arrival_mode.value !== 'self' ? [{ value: 'walk', label: 'Đi bộ' }] : [])]} onChange={(v) => onEdit('mobility', v)} />,
    base: <PlaceSearch placeholder="Chọn nơi gần chỗ ở" onPick={(p) => onEdit('base', p.id)} />,
    origin: <PlaceInput<GeoHit> label="Nơi bạn khởi hành" placeholder="Thành phố, quận hoặc địa chỉ" icon="home" fetcher={geoSearch} row={geoRow} onPick={(g) => onEdit('origin', JSON.stringify({ text: g.text, lat: g.lat, lng: g.lng, province: g.province }))} />,
    arrival_mode: <Seg label="Tới Đà Lạt bằng" value={t.arrival_mode?.value ?? null} options={Object.entries(ARRIVAL_LABEL).map(([value, label]) => ({ value, label }))} onChange={(v) => onEdit('arrival_mode', v)} />,
    ...Object.fromEntries((['inbound', 'outbound'] as const).map((w) => [w, (
      <div className="tg-full__edit">
        <span className="tg-faint">{t[w] ? `${t[w].value.from_point} → ${t[w].value.to_point}` : ''}</span>
        <button type="button" className="tg-btn tg-btn--sm tg-btn--ghost" onClick={() => onEdit(w, null)}>Bỏ chuyến này</button>
      </div>
    )])),
    ...Object.fromEntries((['lodging', 'lodging_booked'] as const).map((k) => [k, (
      <div className="tg-full__edit is-stack">
        <PlaceInput<LodgingHit> label="Nơi bạn lưu trú" placeholder="Tên khách sạn, homestay hoặc địa chỉ" icon="bed" fetcher={lodgingSuggest} row={lodgingRow} onPick={(h) => onEdit('lodging', JSON.stringify({ kind: h.kind, ...(h.id ? { id: h.id } : {}), text: h.text, lat: h.lat, lng: h.lng }))} />
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
  const all: Line[] = [
    ...linesOf(u),
    ...(['dates', 'who', 'mobility', 'base', 'times', 'purpose', 'pace', 'novelty'] as const)
      .filter((k) => !linesOf(u).some((l) => l.key === k))
      .map((k) => ({ key: k, label: { dates: 'Ngày đi', who: 'Đi với', mobility: 'Phương tiện', base: 'Chỗ ở', times: 'Giờ giấc', purpose: 'Mục đích', pace: 'Nhịp độ', novelty: 'Mới hay quen' }[k], value: '', target: k === 'dates' ? 'start_date' : k === 'who' ? 'companions' : k === 'times' ? 'checkin_at' : k })),
  ]
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
                  {editing && editors[r.key] && <div className="tg-full__editor">{editors[r.key]}</div>}
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
