import { Icon, type IconName } from './icons'

// A postage stamp's rippled edge: a rounded square whose outline waves, as a path in a 100 x 100 box.
const STAMP = (() => {
  const n = 160, waves = 14, amp = 2.1
  const pts: string[] = []
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2
    const c = Math.cos(a), s = Math.sin(a)
    // superellipse radius so the corners are rounded, then a ripple along the normal
    const k = 4.2
    const rad = 41 / Math.pow(Math.pow(Math.abs(c), k) + Math.pow(Math.abs(s), k), 1 / k)
    const w = amp * Math.sin(a * waves)
    pts.push(`${(50 + (rad + w) * c).toFixed(2)},${(50 + (rad + w) * s).toFixed(2)}`)
  }
  return `M${pts.join('L')}Z`
})()

// The caller's class places and colours it (fill on the first svg, stroke on the icon); see blog.css and gate.css.
export function Stamp({ icon, className }: { icon: IconName; className: string }) {
  return (
    <span className={className} aria-hidden="true">
      <svg viewBox="0 0 100 100"><path d={STAMP} /></svg>
      <Icon name={icon} size={46} />
    </span>
  )
}
