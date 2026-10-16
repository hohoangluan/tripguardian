import * as Dialog from '@radix-ui/react-dialog'
import { useCallback, useRef } from 'react'
import { reducedMotion } from '../lib'
import { toggleTheme, useUi } from '../store'
import { HeartFill, Icon } from '../ui/icons'
import { Stamp } from '../ui/Stamp'
import { THEMES, themeOf, type Theme } from './themes'

// A theme as a postcard-style blog page (ui_mock_for_design reference: cream card, photo in a frame, a stamp on the corner,
// the other pages as tabs on the right edge). Opens over a blurred page; the photo flies in from the card it was clicked on.
// Colours of the paper live in blog.css; everything else is the app's tokens.

// "Săn mây, đón một ngày mới" -> the first part upright, the rest in italics; without a comma the title splits after about half the words.
const split = (title: string): [string, string] => {
  const c = title.indexOf(',')
  if (c > 0) return [title.slice(0, c + 1), title.slice(c + 1).trim()]
  const w = title.split(' ')
  const k = Math.ceil(w.length / 2)
  return [w.slice(0, k).join(' '), w.slice(k).join(' ')]
}

// Flight: the photo starts as the card it was clicked on (same place, same width, cropped to its shape) and settles into the frame.
function fly(node: HTMLElement, a: DOMRect) {
  const b = node.getBoundingClientRect()
  if (!b.width || !b.height) return
  const s = Math.max(a.width / b.width, a.height / b.height)
  const dx = a.left + a.width / 2 - (b.left + b.width / 2)
  const dy = a.top + a.height / 2 - (b.top + b.height / 2)
  const cx = Math.max(0, (b.width - a.width / s) / 2)
  const cy = Math.max(0, (b.height - a.height / s) / 2)
  node.animate(
    [
      { transform: `translate(${dx}px, ${dy}px) scale(${s})`, clipPath: `inset(${cy}px ${cx}px round 14px)` },
      { transform: 'none', clipPath: 'inset(0px 0px round 10px)' },
    ],
    { duration: 640, easing: 'cubic-bezier(0.16, 1, 0.3, 1)' },
  )
}

export function ThemeBlog({ id, from, onPick, onStart, onClose }: { id: string | null; from: HTMLElement | null; onPick: (id: string) => void; onStart: (t: Theme) => void; onClose: () => void }) {
  const keep = useRef(id ?? THEMES[0].id)
  if (id) keep.current = id
  const t = themeOf(keep.current) ?? THEMES[0]
  const saved = useUi((u) => u.savedThemes.includes(t.id))
  const flown = useRef<HTMLElement | null>(null)
  const photo = useCallback((node: HTMLElement | null) => {
    if (!node || !from || flown.current === from || !from.isConnected || reducedMotion()) return
    flown.current = from
    fly(node, from.getBoundingClientRect())
  }, [from])
  const [lead, tail] = split(t.title)
  const tabKey = (e: React.KeyboardEvent) => {
    const d = e.key === 'ArrowDown' || e.key === 'ArrowRight' ? 1 : e.key === 'ArrowUp' || e.key === 'ArrowLeft' ? -1 : 0
    if (!d) return
    e.preventDefault()
    const i = THEMES.findIndex((x) => x.id === t.id)
    const next = THEMES[(i + d + THEMES.length) % THEMES.length]
    onPick(next.id)
    requestAnimationFrame(() => document.getElementById(`tg-bl-tab-${next.id}`)?.focus())
  }
  const open = id !== null
  if (!open) flown.current = null
  return (
    <Dialog.Root open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      <Dialog.Portal>
        <Dialog.Overlay className="tg-bl__veil">
          {THEMES.map((x) => <img key={x.id} src={x.photo} alt="" className={x.id === t.id ? 'is-on' : ''} />)}
        </Dialog.Overlay>
        <Dialog.Content className="tg tg-home tg-bl" aria-describedby="tg-bl-desc">
          <div className="tg-bl__paper" />
          <Dialog.Close className="tg-bl__x" aria-label="Đóng"><Icon name="x" size={16} /></Dialog.Close>
          <div className="tg-bl__page" key={t.id}>
            <div className="tg-bl__photo" ref={photo} data-fly={from ? '' : undefined}>
              <img src={t.photo} alt={t.alt} />
            </div>
            <Stamp icon={t.icon} className="tg-bl__stamp" />
            <Dialog.Title className="tg-bl__title"><span>{lead}</span> <em>{tail}</em></Dialog.Title>
            <p id="tg-bl-desc" className="tg-bl__desc">{t.description}</p>
            <p className="tg-bl__cat">{t.category} · Ảnh địa điểm thật</p>
            <div className="tg-bl__act">
              <button type="button" className="tg-bl__go" onClick={() => onStart(t)}>Bắt đầu với ý tưởng này<Icon name="arrow" size={16} /></button>
              <button type="button" className="tg-bl__save" aria-pressed={saved} aria-label={saved ? `Bỏ lưu ${t.short}` : `Lưu ${t.short}`} onClick={() => toggleTheme(t.id, t.short)}>{saved ? <HeartFill size={17} /> : <Icon name="heart" size={17} />}</button>
            </div>
          </div>
          <div className="tg-bl__tabs" role="tablist" aria-orientation="vertical" aria-label="Các ý tưởng">
            {THEMES.map((x, k) => (
              <button key={x.id} id={`tg-bl-tab-${x.id}`} type="button" role="tab" aria-selected={x.id === t.id} tabIndex={x.id === t.id ? 0 : -1}
                style={{ '--i': k } as React.CSSProperties} onClick={() => onPick(x.id)} onKeyDown={tabKey}>
                <span>{x.tab}</span>
              </button>
            ))}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
