import * as Popover from '@radix-ui/react-popover'
import { useState, type ReactNode } from 'react'
import { useSnapshot, type Cover } from '../../data/store'
import { navigate } from '../../router'
import { info, type TrustLevel } from '../lib'
import { useUi } from '../store'
import { Icon } from './icons'

export const BASE = '/app'
export const href = (to: string) => (to === '/' ? BASE : BASE + to)
export const go = (to: string, opts?: { replace?: boolean }) => navigate(href(to), opts)
export const placeHref = (id: string) => `/explore/place/${encodeURIComponent(id)}`

export function Link({ to, children, className, onClick, ...rest }: { to: string; children: ReactNode; className?: string; onClick?: () => void } & Record<string, unknown>) {
  return (
    <a href={href(to)} className={className} {...rest} onClick={(e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return
      e.preventDefault()
      onClick?.()
      go(to)
    }}>{children}</a>
  )
}

// 480px WebP made by web/scripts/make_thumbs.py: /media/gmaps/<dir>/photos/x.jpg -> /media/thumb/gmaps/<dir>/photos/x.webp
export const THUMB_W = 480
export const thumbOf = (src: string) => (src.startsWith('/media/') ? src.replace('/media/', '/media/thumb/').replace(/\.jpe?g$/i, '.webp') : null)

const SIZES = '(max-width: 600px) 92vw, 320px'
// What an <img> of this photo asks for: the thumbnail for small slots, the original for large or dense screens (`sizes`).
// Narrower originals: the thumbnail is the same size, only lighter.
function photoSrc(photo: Cover, thumb: string | null, sizes: string) {
  const wide = !!thumb && photo.w > THUMB_W
  return { src: thumb ?? photo.src, srcSet: wide ? `${thumb} ${THUMB_W}w, ${photo.src} ${photo.w}w` : undefined, sizes: wide ? sizes : undefined }
}

// Fetch photos before they are on screen, as the very <img> the screen will draw (same srcset and sizes, so the browser
// takes the same file and the draw is a cache hit). One request per photo and slot size, started when the browser is idle.
const warmed = new Set<string>()
export function warmPhotos(photos: (Cover | undefined)[], sizes = SIZES) {
  const todo = photos.filter((p): p is Cover => !!p && !warmed.has(p.src + sizes))
  if (!todo.length) return
  const start = () => todo.forEach((p) => {
    warmed.add(p.src + sizes)
    const im = new Image()
    const { src, srcSet, sizes: s } = photoSrc(p, thumbOf(p.src), sizes)
    im.decoding = 'async'
    if (srcSet) { im.srcset = srcSet; im.sizes = s! }
    im.src = src
  })
  const idle = (window as { requestIdleCallback?: (f: () => void, o?: { timeout: number }) => void }).requestIdleCallback
  if (idle) idle(start, { timeout: 1500 })
  else window.setTimeout(start, 200)
}
// The first photos of these places (card slots), and optionally the gallery the place sheet opens with.
export function warmPlaces(ids: string[], gallery = 0) {
  warmPhotos(ids.map((id) => info(id)?.photos[0]))
  if (gallery) warmPhotos(ids.flatMap((id) => info(id)?.photos.slice(0, gallery) ?? []), '(max-width: 900px) 92vw, 640px')
}

// A missing thumbnail falls back to the original, a missing original to the placeholder.
export function Photo({ photo, alt, className, credit = false, eager = false, sizes = SIZES }: { photo: Cover | undefined; alt: string; className?: string; credit?: boolean; eager?: boolean; sizes?: string }) {
  const [fail, setFail] = useState(0)
  const thumb = photo && fail === 0 ? thumbOf(photo.src) : null
  const img = photo ? photoSrc(photo, thumb, sizes) : null
  return (
    <figure className={`tg-photo ${className ?? ''}`}>
      {fail > 1 || !img ? <div className="tg-photo__ph" role="img" aria-label={alt} /> : <img {...img} alt={alt} loading={eager ? 'eager' : 'lazy'} decoding="async" onError={() => setFail(thumb ? 1 : 2)} />}
      {credit && photo && <figcaption className="tg-photo__credit">Ảnh: {photo.credit}</figcaption>}
    </figure>
  )
}
export function PlacePhoto({ id, i = 0, name, ...rest }: { id: string; i?: number; name?: string; className?: string; credit?: boolean; eager?: boolean; sizes?: string }) {
  useSnapshot() // screens that render before the snapshot (Hiểu chuyến đi) get the photo once it lands
  const p = info(id)
  const photos = p?.photos ?? []
  return <Photo photo={photos.length ? photos[i % photos.length] : undefined} alt={name ?? p?.name ?? ''} {...rest} />
}

// Opens on hover / focus AND on click, so touch and keyboard get the same explanation.
export function Hint({ label, children, side = 'top' }: { label: ReactNode; children: ReactNode; side?: 'top' | 'bottom' | 'left' | 'right' }) {
  const [open, setOpen] = useState(false)
  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button type="button" className="tg-hint" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>{children}</button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content className="tg tg-pop" side={side} sideOffset={8} collisionPadding={12} onOpenAutoFocus={(e) => e.preventDefault()} onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
          {label}
          <Popover.Arrow className="tg-pop__arrow" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}

export function Trust({ level, why }: { level: TrustLevel; why: string }) {
  return (
    <Hint label={<><b>Độ tin cậy: {level}.</b> {why}</>}>
      <span className={`tg-trust is-${level === 'Cao' ? 'hi' : level === 'Thấp' ? 'lo' : 'mid'}`}><i /><i /><i />{level}<Icon name="info" size={13} /></span>
    </Hint>
  )
}

export function Unconfirmed({ children = 'chưa xác nhận', why }: { children?: string; why: string }) {
  return <Hint label={why}><span className="tg-unconf"><Icon name="warn" size={13} />{children}</span></Hint>
}

export function Empty({ art, title, body, detail, action }: { art: ReactNode; title: string; body: string; detail?: ReactNode; action?: ReactNode }) {
  return (
    <div className="tg-empty" role="status">
      <div className="tg-empty__art" aria-hidden="true">{art}</div>
      <h3>{title}</h3>
      <p className="tg-muted">{body}</p>
      {detail}
      {action}
    </div>
  )
}

export function Busy({ text }: { text: string }) {
  return <p className="tg-busy" role="status"><i /> {text}</p>
}

export function Toast() {
  const note = useUi((u) => u.toast)
  if (!note) return null
  return <div className="tg-toast" role="status"><Icon name="heart" size={16} />{note}</div>
}

// Hand-drawn line art for empty / error states (thin strokes, primary tint)
export const ArtHills = () => (
  <svg viewBox="0 0 200 120" width="200" height="120" fill="none" style={{ stroke: 'var(--tg-pine)' }} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M6 100c28-22 44-44 70-44s34 16 52 16 38-26 66-26" opacity=".55" /><path d="M6 112c34-18 58-30 84-30s46 14 70 14 28-8 34-12" />
    <circle cx="150" cy="30" r="12" style={{ stroke: 'var(--tg-sun)' }} /><path d="M60 62l10-22 10 22M64 54h12M52 78l8-16 8 16" />
  </svg>
)
export const ArtRoute = () => (
  <svg viewBox="0 0 200 120" width="200" height="120" fill="none" style={{ stroke: 'var(--tg-pine)' }} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M20 96c30-8 18-44 50-46s30 28 62 18 30-36 48-30" strokeDasharray="5 6" /><circle cx="20" cy="96" r="6" /><circle cx="180" cy="38" r="6" style={{ stroke: 'var(--tg-sun)' }} /><path d="M96 40c0-8 6-12 12-12s12 4 12 12c0 9-12 20-12 20s-12-11-12-20Z" />
  </svg>
)
export const ArtCup = () => (
  <svg viewBox="0 0 200 120" width="200" height="120" fill="none" style={{ stroke: 'var(--tg-pine)' }} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M62 52h62v28c0 14-12 24-26 24h-10c-14 0-26-10-26-24V52ZM124 58h10a12 12 0 0 1 0 24h-10M80 30c-6 8 6 10 0 18M100 30c-6 8 6 10 0 18" /><path d="M48 108h92" opacity=".55" />
  </svg>
)
