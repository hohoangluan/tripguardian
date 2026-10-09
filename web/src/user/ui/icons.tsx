import { useState } from 'react'
import type { SVGProps } from 'react'

// Thin outline set (24px grid, 1.6 stroke). Decorative by default: pass `title` for a meaningful icon.
const P: Record<string, string> = {
  search: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14ZM20 20l-3.6-3.6',
  heart: 'M12 20s-7-4.4-9-9.2C1.8 7.6 3.6 4.5 6.8 4.5c2 0 3.5 1 5.2 3 1.7-2 3.2-3 5.2-3 3.2 0 5 3.1 3.8 6.3-2 4.8-9 9.2-9 9.2Z',
  pin: 'M12 21s-6.5-6-6.5-11a6.5 6.5 0 1 1 13 0c0 5-6.5 11-6.5 11ZM12 7.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5Z',
  route: 'M6 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM18 9a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM8 17h6.5a3.5 3.5 0 0 0 0-7H9.5a3.5 3.5 0 0 1 0-7H16',
  calendar: 'M4 7a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7ZM4 10h16M8 3v4M16 3v4',
  compass: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18ZM15.5 8.5l-2 5-5 2 2-5 5-2Z',
  suitcase: 'M5 8h14a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1ZM9 8V6a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M4 13h16',
  user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM4.5 20a7.5 7.5 0 0 1 15 0',
  users: 'M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7ZM2.5 19a6.5 6.5 0 0 1 13 0M16 4.2a3.5 3.5 0 0 1 0 6.6M18 14.2a6.5 6.5 0 0 1 3.5 4.8',
  sparkle: 'M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3ZM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8L19 16Z',
  arrow: 'M5 12h14M13 6l6 6-6 6',
  arrowLeft: 'M19 12H5M11 6l-6 6 6 6',
  check: 'M5 12.5l4.5 4.5L19 7.5',
  x: 'M6 6l12 12M18 6L6 18',
  lock: 'M7 11V8a5 5 0 0 1 10 0v3M6 11h12a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-7a1 1 0 0 1 1-1Z',
  unlock: 'M7 11V8a5 5 0 0 1 9.5-2.2M6 11h12a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-7a1 1 0 0 1 1-1Z',
  clock: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18ZM12 7.5V12l3 2',
  bell: 'M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15L6 16ZM10 20.5a2.2 2.2 0 0 0 4 0',
  sun: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM12 2.5v2M12 19.5v2M4.5 12h-2M21.5 12h-2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4L7 17M17 7l1.4-1.4',
  cloud: 'M7 18a4 4 0 0 1-.6-7.95A5.5 5.5 0 0 1 17 8.5a4.75 4.75 0 0 1 0 9.5H7Z',
  rain: 'M7 14a4 4 0 0 1-.6-7.95A5.5 5.5 0 0 1 17 4.5a4.75 4.75 0 0 1 0 9.5H7ZM8 17.5l-1 2.5M12 17.5l-1 2.5M16 17.5l-1 2.5',
  coffee: 'M5 9h11v5a5 5 0 0 1-5 5H10a5 5 0 0 1-5-5V9ZM16 10h1.5a2.5 2.5 0 0 1 0 5H16M8 3.5v2.5M12 3.5v2.5',
  tree: 'M12 3l5 7h-3l4 6h-5v5h-2v-5H6l4-6H7l5-7Z',
  utensils: 'M7 3v8a2 2 0 0 0 2 2h0V21M5 3v6M9 3v6M17 21V3c-2.5 1.5-3.5 4-3.5 7 0 2 1 3 3.5 3',
  walk: 'M13 5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3ZM10 21l1.5-6.5L9 12l1-4 3-1 2 3 3 1M9 12l-2 3',
  bike: 'M6 18a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7ZM18 18a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7ZM6 14.5L9 8h4l3 6.5M9 8L8 6H6M13 8l1-2h2',
  map: 'M9 4l-6 2v14l6-2 6 2 6-2V4l-6 2-6-2ZM9 4v14M15 6v14',
  plus: 'M12 5v14M5 12h14',
  minus: 'M5 12h14',
  chevronDown: 'M6 9l6 6 6-6',
  chevronLeft: 'M15 6l-6 6 6 6',
  chevronRight: 'M9 6l6 6-6 6',
  turn: 'M3 12c0 2.8 4 5 9 5s9-2.2 9-5-4-5-9-5M3 12l2.4-2.6M3 12l3.2.6M12 7l-2.2-2M12 7l-2.2 2',
  chevronUp: 'M6 15l6-6 6 6',
  swap: 'M7 4L3 8l4 4M3 8h14M17 20l4-4-4-4M21 16H7',
  info: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18ZM12 11v5M12 7.8v.2',
  warn: 'M12 4L2.5 20h19L12 4ZM12 10v4.5M12 17.2v.2',
  flag: 'M5 21V4M5 4h11l-2 4 2 4H5',
  bolt: 'M13 3L5 13.5h6L10 21l8-10.5h-6L13 3Z',
  home: 'M4 11l8-7 8 7v8a1 1 0 0 1-1 1h-4v-6h-6v6H5a1 1 0 0 1-1-1v-8Z',
  ticket: 'M4 7a1 1 0 0 1 1-1h14a1 1 0 0 1 1 1v2.5a2.5 2.5 0 0 0 0 5V17a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-2.5a2.5 2.5 0 0 0 0-5V7ZM14.5 6v12',
  bookmark: 'M7 4h10a1 1 0 0 1 1 1v15l-6-4-6 4V5a1 1 0 0 1 1-1Z',
  send: 'M4 12L20 4l-6 16-3-7-7-1Z',
  sliders: 'M4 7h9M17 7h3M4 17h3M11 17h9M15 4v6M9 14v6',
  play: 'M8 5v14l11-7L8 5Z',
  external: 'M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5',
  trash: 'M5 7h14M10 7V4h4v3M7 7l1 13h8l1-13M10 11v6M14 11v6',
  edit: 'M4 20h4L19 9l-4-4L4 16v4ZM13.5 6.5l4 4',
  refresh: 'M20 12a8 8 0 1 1-2.5-5.8M20 4v5h-5',
  moon: 'M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5Z',
  bed: 'M3 18V6M3 14h18v4M21 14v-2a3 3 0 0 0-3-3h-7v5M7.5 11.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z',
  zap: 'M13 3L5 13.5h6L10 21l8-10.5h-6L13 3Z',
  shield: 'M12 3l7 3v5c0 5-3 8.5-7 10-4-1.5-7-5-7-10V6l7-3ZM9 12l2 2 4-4',
  logout: 'M10 4H6a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h4M15 8l4 4-4 4M19 12H9',
  grid: 'M4 4h6v6H4V4ZM14 4h6v6h-6V4ZM4 14h6v6H4v-6ZM14 14h6v6h-6v-6Z',
  car: 'M5 16l1.5-5.5A2 2 0 0 1 8.4 9h7.2a2 2 0 0 1 1.9 1.5L19 16M4 16h16v3H4v-3ZM7.5 19v1.5M16.5 19v1.5',
  phone: 'M8 3h8a1.5 1.5 0 0 1 1.5 1.5v15A1.5 1.5 0 0 1 16 21H8a1.5 1.5 0 0 1-1.5-1.5v-15A1.5 1.5 0 0 1 8 3ZM11 18h2',
  laptop: 'M5 6a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v9H5V6ZM3 15h18l-1.5 3.5h-15L3 15Z',
  download: 'M12 4v11M7.5 10.5 12 15l4.5-4.5M5 19h14',
  plane: 'M10.5 13.5 4 16v-1.8l6.5-4.2V5a1.5 1.5 0 0 1 3 0v5l6.5 4.2V16l-6.5-2.5V18l2 1.5V21L12 20l-3.5 1v-1.5l2-1.5v-4.5Z',
  bus: 'M6 4h12a1.5 1.5 0 0 1 1.5 1.5V17H4.5V5.5A1.5 1.5 0 0 1 6 4ZM4.5 11h15M4.5 7.5h15M7.5 17v2.5M16.5 17v2.5M8 14h.01M16 14h.01',
  clip: 'M20 11.5l-7.8 7.8a5 5 0 0 1-7.1-7.1l8.5-8.5a3.3 3.3 0 0 1 4.7 4.7l-8.5 8.5a1.7 1.7 0 0 1-2.4-2.4l7.8-7.8',
  link: 'M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1',
}

export type IconName = keyof typeof P
export function Icon({ name, size = 20, title, ...rest }: { name: IconName; size?: number; title?: string } & Omit<SVGProps<SVGSVGElement>, 'name'>) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" role={title ? 'img' : undefined} aria-hidden={title ? undefined : true} aria-label={title} {...rest}>
      <path d={P[name]} />
    </svg>
  )
}
export const HeartFill = ({ size = 20 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true"><path d={P.heart} fill="currentColor" stroke="currentColor" strokeWidth={1.6} strokeLinejoin="round" /></svg>
)
// The assistant's face in the chat: the logo's pine, round, with two eyes, and the sun as its spark. Tokens only.
// The generated mascot (web/scripts/gen_ui_images.py bot-avatar, 160 px) replaces the drawing once that file exists.
let botImage = true
export function BotAvatar({ size = 32, live = false }: { size?: number; live?: boolean }) {
  const [img, setImg] = useState(botImage)
  return (
    <span className={`tg-bot ${live ? 'is-live' : ''}`} style={{ width: size, height: size }} aria-hidden="true">
      {img ? <img src="/img/gen/bot-avatar.webp" alt="" width={size} height={size} onError={() => { botImage = false; setImg(false) }} /> : <svg viewBox="0 0 32 32" width={size} height={size}>
        <circle cx="16" cy="16" r="16" style={{ fill: 'var(--tg-pine, #0f5f5a)' }} />
        <path d="M16 6.5l6.2 8.3h-3.4l4.7 6.7H8.5l4.7-6.7H9.8L16 6.5Z" style={{ fill: '#fff' }} />
        <rect x="14.6" y="21.5" width="2.8" height="3.6" rx="1" style={{ fill: '#fff' }} />
        <circle cx="13.9" cy="17.6" r="1.15" style={{ fill: 'var(--tg-pine, #0f5f5a)' }} />
        <circle cx="18.1" cy="17.6" r="1.15" style={{ fill: 'var(--tg-pine, #0f5f5a)' }} />
        <circle cx="24.3" cy="8.2" r="2.3" style={{ fill: 'var(--tg-sun, #e8590c)' }} />
      </svg>}
    </span>
  )
}

// The generated shield mark (web/scripts/make_brand_assets.py cuts it out of gen/app-logo.webp); the drawing stays as the fallback.
let logoImage = true
export function Logo({ size = 28, dark = false }: { size?: number; dark?: boolean }) {
  const [img, setImg] = useState(logoImage)
  if (img) return <img className="tg-logo" src="/img/logo.webp" alt="" width={size} height={size} onError={() => { logoImage = false; setImg(false) }} />
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="9" style={{ fill: dark ? '#fff' : 'var(--tg-pine, #0f5f5a)' }} />
      <path d="M16 6l8 11h-5l5 7H8l5-7H8l8-11Z" style={{ fill: dark ? 'var(--tg-pine, #0f5f5a)' : '#fff' }} />
      <circle cx="24" cy="8" r="2.4" style={{ fill: 'var(--tg-sun, #e8590c)' }} />
    </svg>
  )
}
