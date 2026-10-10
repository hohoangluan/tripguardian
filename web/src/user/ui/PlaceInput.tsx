import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import type { GeoHit, LodgingHit } from '../tu/types'
import { Icon, type IconName } from './icons'

// Type-ahead like Google Maps (docs/WEB.md §6): suggestions from the 2nd character, 250 ms
// debounce, at most 6 rows with the typed part in bold, ↑ ↓ Enter Esc. Used for the trip's origin (/geo), a booked
// lodging (/lodging/suggest) and "Tôi ở chỗ khác" on the lodging screen.

export interface InputRow {
  key: string
  icon: IconName
  name: string
  sub: string
  rating?: number | null
  approx?: boolean
}

const KIND_ICON: Record<NonNullable<GeoHit['kind']>, IconName> = { area: 'map', transport: 'bus', stay: 'bed', street: 'route', place: 'pin' }

// Rows of the two searches (/geo, /lodging/suggest); every box that lists them shares these.
export const geoRow = (g: GeoHit): InputRow => ({
  key: `${g.lat},${g.lng}${g.approx ? ':approx' : ''}`, icon: g.approx ? 'pin' : KIND_ICON[g.kind ?? 'place'], name: g.text, approx: g.approx,
  sub: g.approx ? `gần ${g.address}` : g.province && !g.address.includes(g.province) && g.province !== g.text ? [g.address, g.province].filter(Boolean).join(' · ') : g.address,
})
export const lodgingRow = (h: LodgingHit): InputRow => ({
  key: h.id ?? `${h.lat},${h.lng}${h.approx ? ':approx' : ''}`, name: h.text, rating: h.rating, approx: h.approx,
  icon: h.kind === 'address' ? (h.approx ? 'pin' : KIND_ICON[h.geo_kind ?? 'place']) : /homestay|villa|nhà/i.test(h.text) ? 'home' : 'bed',
  sub: h.approx ? `gần ${h.address}` : h.address,
})

const MIN = 2
const WAIT = 250
const MAX = 6
const EMPTY = 'Không thấy nơi này. Thử gõ địa chỉ hoặc tên đường.'

// One lower-case base letter per character, so indices line up with the original text ("Đà Lạt" ~ "da lat").
const fold = (s: string) => Array.from(s, (c) => (c === 'đ' || c === 'Đ' ? 'd' : c.normalize('NFD')[0].toLowerCase())).join('')

// Each typed word in bold where it starts a word of the name, the way the server matches ("ana man" -> Ana Mandara).
function Marked({ text, q }: { text: string; q: string }) {
  const f = fold(text)
  const marks: [number, number][] = []
  for (const w of fold(q).split(/[\s,-]+/).filter(Boolean)) {
    for (let i = f.indexOf(w); i >= 0; i = f.indexOf(w, i + 1))
      if ((i === 0 || /[\s,(/-]/.test(f[i - 1])) && !marks.some(([a, b]) => i < b && i + w.length > a)) { marks.push([i, i + w.length]); break }
  }
  if (!marks.length) return <>{text}</>
  marks.sort((a, b) => a[0] - b[0])
  const out: ReactNode[] = []
  let at = 0
  for (const [a, b] of marks) { out.push(text.slice(at, a), <b key={a}>{text.slice(a, b)}</b>); at = b }
  out.push(text.slice(at))
  return <>{out}</>
}

export function PlaceInput<T>({ fetcher, row, onPick, placeholder, label, autoFocus = false, disabled = false, icon = 'search' }: {
  fetcher: (q: string, signal: AbortSignal) => Promise<T[]>
  row: (item: T) => InputRow
  onPick: (item: T, r: InputRow) => void
  placeholder: string
  label: string
  autoFocus?: boolean
  disabled?: boolean
  icon?: IconName
}) {
  const id = useId()
  const [q, setQ] = useState('')
  const [hits, setHits] = useState<T[] | null>(null) // null: nothing asked yet
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)
  const [at, setAt] = useState(-1)
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const picked = useRef<string | null>(null) // the text a pick wrote into the box: no search for it
  const answered = useRef('') // the query `hits` belong to: Enter never picks a row of an older query

  useEffect(() => {
    const text = q.trim()
    if (text.length < MIN) { setHits(null); setBusy(false); return }
    if (text === picked.current) { setBusy(false); return }
    picked.current = null
    const ctl = new AbortController()
    setBusy(true)
    const t = window.setTimeout(() => {
      fetcher(text, ctl.signal).then(
        (r) => { answered.current = text; setHits(r.slice(0, MAX)); setFailed(false); setAt(-1); setBusy(false) },
        (e) => { if (e?.name !== 'AbortError') { setHits([]); setFailed(true); setBusy(false) } },
      )
    }, WAIT)
    return () => { window.clearTimeout(t); ctl.abort() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q])

  // A click outside closes the list; the typed text stays.
  useEffect(() => {
    if (!open) return
    const off = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false) }
    addEventListener('pointerdown', off)
    return () => removeEventListener('pointerdown', off)
  }, [open])

  const rows = (hits ?? []).map(row)
  const shown = open && q.trim().length >= MIN && (hits !== null || busy)
  const pick = (i: number) => {
    const item = hits?.[i]
    if (!item) return
    onPick(item, rows[i])
    picked.current = rows[i].name.trim()
    setQ(rows[i].name)
    setOpen(false)
  }
  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown' && rows.length) { e.preventDefault(); setOpen(true); setAt((i) => (i + 1) % rows.length) }
    else if (e.key === 'ArrowUp' && rows.length) { e.preventDefault(); setOpen(true); setAt((i) => (i <= 0 ? rows.length - 1 : i - 1)) }
    else if (e.key === 'Enter') { e.preventDefault(); if (shown && !busy && rows.length && answered.current === q.trim()) pick(at < 0 ? 0 : at) }
    else if (e.key === 'Escape') { if (shown) { e.preventDefault(); e.stopPropagation(); setOpen(false) } else setQ('') }
  }
  let body: ReactNode = null
  if (shown) {
    if (rows.length)
      body = rows.map((r, i) => (
        <li key={r.key} id={`${id}-${i}`} role="option" aria-selected={i === at} className={i === at ? 'is-at' : undefined} onPointerDown={(e) => e.preventDefault()} onClick={() => pick(i)} onPointerMove={() => setAt(i)}>
          <i aria-hidden="true"><Icon name={r.icon} size={16} /></i>
          <span><b className="tg-pin__name"><Marked text={r.name} q={q} /></b>{r.sub && <small>{r.sub}</small>}</span>
          {r.approx ? <span className="tg-tag">Gần đúng</span> : r.rating ? <em className="tg-mono" aria-label={`${r.rating} sao`}>★ {r.rating.toFixed(1)}</em> : null}
        </li>
      ))
    else if (busy) body = <li className="tg-pin__note" role="status"><span className="tg-dots" aria-hidden="true"><i /><i /><i /></span> Đang tìm…</li>
    else body = <li className="tg-pin__note" role="status">{failed ? 'Chưa tìm được lúc này. Thử lại sau ít giây.' : EMPTY}</li>
  }
  return (
    <div className="tg-pin" ref={box}>
      <label className="tg-pin__in">
        <Icon name={icon} size={18} aria-hidden="true" />
        <span className="tg-sr">{label}</span>
        <input
          className="tg-input" type="text" role="combobox" autoComplete="off" spellCheck={false} autoFocus={autoFocus} disabled={disabled}
          aria-expanded={shown} aria-controls={`${id}-list`} aria-autocomplete="list" aria-activedescendant={shown && at >= 0 ? `${id}-${at}` : undefined}
          value={q} placeholder={placeholder}
          onChange={(e) => { setQ(e.target.value); setOpen(true) }} onFocus={() => setOpen(true)} onKeyDown={onKey}
        />
        {busy && <span className="tg-pin__spin" aria-hidden="true" />}
      </label>
      {shown && <ul className="tg-pin__list" id={`${id}-list`} role="listbox" aria-label={label}>{body}</ul>}
    </div>
  )
}
