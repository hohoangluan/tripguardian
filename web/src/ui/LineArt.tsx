// Thin-line Đà Lạt scenery drawn in SVG: ridges, pines, a lake with ripples. Rose stroke on
// transparent so it sits on any white surface; replaces the old painted posters (UI spec §8).
// Deterministic: the same seed always draws the same hills.

function rand(seed: number) {
  let s = seed >>> 0
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0
    return s / 2 ** 32
  }
}

function pine(x: number, base: number, h: number) {
  const w = h * 0.34
  const tiers = 4
  let d = `M${x} ${base}V${base - h * 0.12}`
  for (let i = 0; i < tiers; i++) {
    const top = base - h * (0.12 + (i + 1) * 0.22)
    const bot = base - h * (0.08 + i * 0.22)
    const ww = w * (1 - i * 0.2)
    d += `M${x - ww} ${bot}L${x} ${top}L${x + ww} ${bot}`
  }
  return d
}

function ridge(r: () => number, y: number, amp: number, w: number, steps: number) {
  let d = `M0 ${y}`
  for (let i = 1; i <= steps; i++) {
    const x = (w / steps) * i
    const peak = y - amp * (0.35 + r() * 0.65)
    d += `Q${x - w / steps / 2} ${peak} ${x} ${y - amp * r() * 0.3}`
  }
  return d
}

export function LineArt({ variant = 'lake', className = '', seed = 7 }: { variant?: 'lake' | 'band' | 'spot'; className?: string; seed?: number }) {
  const r = rand(seed)
  const W = variant === 'spot' ? 320 : 1440
  const H = variant === 'spot' ? 180 : variant === 'band' ? 140 : 300
  const shore = H * (variant === 'band' ? 0.82 : 0.68)
  const pines: string[] = []
  const edge = variant === 'spot' ? 0.32 : 0.24
  // Pines crowd the two banks and thin out toward the open water in the middle.
  for (let i = 0; i < (variant === 'spot' ? 16 : 70); i++) {
    const side = r() < 0.5
    const t = Math.pow(r(), 1.6) * edge
    const x = (side ? t : 1 - t) * W
    const h = (variant === 'spot' ? 30 : 46) * (0.55 + (1 - t / edge) * 0.9 * r() + 0.25)
    pines.push(pine(x, shore - r() * 6, h))
  }
  const ripples: string[] = []
  for (let i = 0; i < (variant === 'spot' ? 6 : 16); i++) {
    const y = shore + 8 + i * (H - shore - 10) / (variant === 'spot' ? 6 : 16)
    const x = W * (0.15 + r() * 0.6)
    const len = W * (0.04 + r() * 0.12)
    ripples.push(`M${x} ${y}h${len}`)
  }
  return (
    <svg className={`lineart lineart--${variant} ${className}`} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMax slice" aria-hidden="true">
      <g fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round">
        <path d={ridge(r, shore - H * 0.18, H * 0.34, W, 5)} strokeWidth="1" opacity="0.45" />
        <path d={ridge(r, shore - H * 0.06, H * 0.2, W, 8)} strokeWidth="1" opacity="0.65" />
        <path d={`M0 ${shore}H${W}`} strokeWidth="1.1" />
        <path d={pines.join('')} strokeWidth="1" />
        <path d={ripples.join('')} strokeWidth="0.9" opacity="0.55" />
      </g>
    </svg>
  )
}
