import { useState } from 'react'
import { Icon } from '../ui/icons'

const WEEK = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN']
const ymd = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

// A month, Monday first. Today is ringed; the dates of the trip being made (start + days) are marked only when the trip really has them.
export function MiniCalendar({ start, days }: { start: string | null; days: number | null }) {
  const now = new Date()
  const first = start ? new Date(`${start}T00:00:00`) : null
  const [at, setAt] = useState(() => new Date((first && !Number.isNaN(+first) ? first : now).getFullYear(), (first && !Number.isNaN(+first) ? first : now).getMonth(), 1))
  const lead = (at.getDay() + 6) % 7 // blanks before the 1st
  const count = new Date(at.getFullYear(), at.getMonth() + 1, 0).getDate()
  const from = first && !Number.isNaN(+first) ? ymd(first) : null
  const to = from && days && days > 0 ? ymd(new Date(first!.getFullYear(), first!.getMonth(), first!.getDate() + days - 1)) : from
  const today = ymd(now)
  const move = (d: number) => setAt(new Date(at.getFullYear(), at.getMonth() + d, 1))
  const cells = [...Array(lead).fill(null), ...Array.from({ length: count }, (_, i) => i + 1)]
  return (
    <section className="tg-cal" aria-label="Lịch">
      <header>
        <h3 aria-live="polite">Tháng {at.getMonth() + 1}, {at.getFullYear()}</h3>
        <span>
          <button type="button" aria-label="Tháng trước" onClick={() => move(-1)}><Icon name="chevronLeft" size={14} /></button>
          <button type="button" className="is-next" aria-label="Tháng sau" onClick={() => move(1)}><Icon name="chevronRight" size={14} /></button>
        </span>
      </header>
      <div className="tg-cal__grid" role="grid">
        {WEEK.map((w) => <b key={w} role="columnheader">{w}</b>)}
        {cells.map((n, i) => {
          if (n === null) return <i key={`b${i}`} />
          const key = ymd(new Date(at.getFullYear(), at.getMonth(), n))
          const edge = key === from || key === to
          const mid = from && to && key > from && key < to
          return <span key={key} role="gridcell" className={`${key === today ? 'is-today' : ''} ${edge ? 'is-edge' : ''} ${mid ? 'is-mid' : ''}`} aria-current={key === today ? 'date' : undefined}>{n}</span>
        })}
      </div>
    </section>
  )
}
