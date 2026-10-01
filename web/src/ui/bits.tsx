import gsap from 'gsap'
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { STATUS_LABEL } from '../data/labels'
import type { Confidence } from '../data/store'
import type { Status } from '../data/types'
import { story } from '../scene/story'

// ---------- icons (stroke, currentColor) ----------

const PATHS: Record<string, string> = {
  check: 'M4 12.5l5 5L20 6.5',
  plus: 'M12 5v14M5 12h14',
  x: 'M6 6l12 12M18 6L6 18',
  lock: 'M7 11V8a5 5 0 0110 0v3M5.5 11h13v9h-13z',
  unlock: 'M7 11V8a5 5 0 019.6-2M5.5 11h13v9h-13z',
  alert: 'M12 4l9 16H3zM12 10v4M12 17.2v.3',
  info: 'M12 3a9 9 0 110 18 9 9 0 010-18zM12 11v6M12 7.5v.3',
  clock: 'M12 3a9 9 0 110 18 9 9 0 010-18zM12 7v5l3.5 2',
  route: 'M6 19a2 2 0 100-4 2 2 0 000 4zM18 9a2 2 0 100-4 2 2 0 000 4zM6 15V9a3 3 0 013-3h3M18 9v6a3 3 0 01-3 3h-3',
  map: 'M9 4L3 6.5v13L9 17l6 2.5 6-2.5v-13L15 6.5 9 4zM9 4v13M15 6.5v13',
  compare: 'M8 4v16M16 4v16M4 8h8M12 16h8',
  back: 'M15 5l-7 7 7 7',
  next: 'M9 5l7 7-7 7',
  play: 'M8 5l11 7-11 7z',
  flag: 'M5 21V4M5 4h11l-2 4 2 4H5',
  rain: 'M7 15a4 4 0 01.5-8A6 6 0 0119 9a3.5 3.5 0 01-1 6.9H7zM8 19l-1 2M12 19l-1 2M16 19l-1 2',
  user: 'M12 12a4 4 0 100-8 4 4 0 000 8zM4.5 20a7.5 7.5 0 0115 0',
  search: 'M11 4a7 7 0 110 14 7 7 0 010-14zM20 20l-4-4',
  spark: 'M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M18 6l-2.5 2.5M8.5 15.5L6 18',
  quote: 'M7 7h4v4c0 3-1.5 5-4 6M14 7h4v4c0 3-1.5 5-4 6',
  layers: 'M12 4l9 5-9 5-9-5 9-5zM3 14l9 5 9-5',
  inbox: 'M3 13l3-8h12l3 8v6H3zM3 13h5l1.5 2.5h5L16 13h5',
  pin: 'M12 21s-7-6.2-7-11a7 7 0 0114 0c0 4.8-7 11-7 11zM12 12.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5z',
  pulse: 'M3 12h4l3-7 4 14 3-7h4',
  gauge: 'M4 18a8 8 0 1116 0M12 18l4-6',
  chart: 'M4 20V10M10 20V4M16 20v-7M22 20H2',
  server: 'M4 4h16v6H4zM4 14h16v6H4zM8 7h.01M8 17h.01',
  shield: 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z',
  keyboard: 'M3 6h18v12H3zM7 10h.01M11 10h.01M15 10h.01M7 14h10',
  refresh: 'M20 11a8 8 0 10-2.3 5.7M20 4v7h-7',
}

export function Icon({ name, size = 18, className }: { name: keyof typeof PATHS | string; size?: number; className?: string }) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={PATHS[name] ?? ''} />
    </svg>
  )
}

// ---------- data-quality vocabulary (UX brief §4) ----------

export function StatusTag({ status, why }: { status: Status; why?: string }) {
  const [open, setOpen] = useState(false)
  if (status === 'VERIFIED') return null
  return (
    <span className={`status status--${status.toLowerCase()}`}>
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        {STATUS_LABEL[status]}
      </button>
      {open && why && <span className="status__why">{why}</span>}
    </span>
  )
}

export function ConfidenceTag({ level, reason }: { level: Confidence; reason: string }) {
  const [open, setOpen] = useState(false)
  const bars = level === 'Cao' ? 3 : level === 'Trung bình' ? 2 : 1
  return (
    <span className="conf">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="conf__btn">
        <span className="conf__bars" aria-hidden="true">
          {[1, 2, 3].map((i) => (
            <i key={i} className={i <= bars ? 'on' : ''} />
          ))}
        </span>
        Độ tin cậy {level.toLowerCase()}
      </button>
      {open && <span className="conf__why">{reason}</span>}
    </span>
  )
}

export function Chip({
  children,
  on,
  onClick,
  tone = 'lean',
}: {
  children: ReactNode
  on?: boolean
  onClick?: () => void
  tone?: 'lean' | 'rule' | 'profile'
}) {
  return (
    <button type="button" className={`chip chip--${tone}${on ? ' is-on' : ''}`} aria-pressed={on} onClick={onClick}>
      {children}
    </button>
  )
}

export function Segmented<T extends string | number>({
  value,
  options,
  onChange,
  label,
}: {
  value: T | null
  options: { value: T; label: string }[]
  onChange: (v: T) => void
  label: string
}) {
  return (
    <div className="seg" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button key={String(o.value)} type="button" role="radio" aria-checked={value === o.value} className={value === o.value ? 'is-on' : ''} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

// ---------- motion ----------

// Pages enter from depth: a short tilt-and-rise that reads as moving forward.
export function Page({ children, className = '' }: { children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el || story.reducedMotion) return
    const ctx = gsap.context(() => {
      gsap.fromTo(el, { opacity: 0, y: 30, rotateX: 7, z: -90 }, { opacity: 1, y: 0, rotateX: 0, z: 0, duration: 0.75, ease: 'power3.out', clearProps: 'transform' })
    }, el)
    return () => ctx.revert()
  }, [])
  return (
    <div className={`page ${className}`} ref={ref}>
      {children}
    </div>
  )
}

// Bottom sheet on phones, side panel on wide screens.
export function Sheet({ open, onClose, children, label }: { open: boolean; onClose: () => void; children: ReactNode; label: string }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    addEventListener('keydown', onKey)
    ref.current?.focus()
    return () => removeEventListener('keydown', onKey)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="sheet" role="dialog" aria-modal="true" aria-label={label}>
      <button className="sheet__scrim" aria-label="Đóng" onClick={onClose} />
      <div className="sheet__body" ref={ref} tabIndex={-1}>
        <div className="sheet__grip" aria-hidden="true" />
        {children}
      </div>
    </div>
  )
}

// TikTok plays through its own embed (UX brief §6), never self-hosted.
export function TikTokEmbed({ id }: { id: string }) {
  const [on, setOn] = useState(false)
  return on ? (
    <iframe
      className="tiktok"
      src={`https://www.tiktok.com/embed/v2/${id}?lang=vi-VN`}
      title="Clip TikTok"
      allow="encrypted-media; fullscreen"
      allowFullScreen
      loading="lazy"
    />
  ) : (
    <button type="button" className="tiktok tiktok--idle" onClick={() => setOn(true)}>
      <Icon name="play" size={22} />
      <span>Mở clip TikTok</span>
    </button>
  )
}

export function GoogleMap({ src, title, height = 220 }: { src: string; title: string; height?: number }) {
  return (
    <div className="gmap" style={{ height }}>
      <iframe src={src} title={title} loading="lazy" referrerPolicy="no-referrer-when-downgrade" />
      <span className="gmap__src">Bản đồ Google</span>
    </div>
  )
}

export function SectionArt({ section }: { section: 'sight' | 'nature' | 'food' | 'shop' }) {
  return <img className="art" src={`/img/cat-${section}.webp`} alt="" loading="lazy" decoding="async" />
}
