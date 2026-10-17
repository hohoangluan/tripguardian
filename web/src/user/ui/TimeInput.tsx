const pad = (n: number) => String(n).padStart(2, '0')
const HOURS = Array.from({ length: 24 }, (_, h) => pad(h))
const STEP = 5

// A 24-hour time field. The browser's own time input follows the device language and shows AM/PM; this one always reads 00–23.
// The value is "HH:MM", or "" while no hour is picked, like the native field it replaces.
export function TimeInput({ value, onChange, label, className, disabled }: { value: string; onChange: (v: string) => void; label: string; className?: string; disabled?: boolean }) {
  const [h = '', m = ''] = value.split(':')
  const minutes = Array.from({ length: 60 / STEP }, (_, k) => pad(k * STEP))
  if (m && !minutes.includes(m)) minutes.push(m) // a time from the server that is not on the step stays pickable
  minutes.sort()
  return (
    <span className="tg-time">
      <select className={className} aria-label={`${label}, giờ`} disabled={disabled} value={h} onChange={(e) => onChange(e.target.value ? `${e.target.value}:${m || '00'}` : '')}>
        <option value="">--</option>
        {HOURS.map((x) => <option key={x} value={x}>{x}</option>)}
      </select>
      <b aria-hidden="true">:</b>
      <select className={className} aria-label={`${label}, phút`} disabled={disabled || !h} value={h ? m || '00' : ''} onChange={(e) => onChange(`${h}:${e.target.value}`)}>
        {!h && <option value="">--</option>}
        {minutes.map((x) => <option key={x} value={x}>{x}</option>)}
      </select>
    </span>
  )
}
