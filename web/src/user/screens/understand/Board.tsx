import * as Dialog from '@radix-ui/react-dialog'
import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { useSnapshot } from '../../../data/store'
import { info } from '../../lib'
import { toggleSaved, useUi } from '../../store'
import type { Understanding } from '../../tu/types'
import { PlacePhoto } from '../../ui/common'
import { HeartFill, Icon } from '../../ui/icons'
import { openPlace } from '../../ui/PlaceSheet'
import { dateLine } from '../../ui/Ticket'

// The board beside the chat: Đà Lạt, how many places fit right now, and the best of them (a chosen look's places
// first). The count is the server's `matching`; the list is `board.ids`. Opening a place uses the shared PlaceSheet.

const GROUP_LABEL: Record<string, string> = { sight: 'Tham quan', food: 'Ăn uống', shop: 'Mua sắm', other: 'Khác' }
const GROUP_ICON = { sight: 'compass', food: 'utensils', shop: 'bookmark', other: 'sparkle' } as const

function useCount(value: number) {
  const [shown, setShown] = useState(value)
  const from = useRef(value)
  useEffect(() => {
    const start = from.current
    from.current = value
    if (start === value || matchMedia('(prefers-reduced-motion: reduce)').matches) { setShown(value); return }
    const t0 = performance.now()
    let raf = 0
    const step = (t: number) => {
      const k = Math.min(1, (t - t0) / 600)
      setShown(Math.round(start + (value - start) * (1 - (1 - k) ** 3)))
      if (k < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [value])
  return shown
}

function PlaceRow({ id, i, look }: { id: string; i: number; look: boolean }) {
  const p = info(id)
  const saved = useUi((u) => u.saved.includes(id))
  if (!p) return null
  return (
    <div className="tg-cx__pc" style={{ '--i': i } as CSSProperties}>
      <button type="button" className="tg-cx__pc-open" onClick={(e) => openPlace(id, e.currentTarget.querySelector('figure'))} aria-label={`Xem chi tiết ${p.name}`}>
        <PlacePhoto id={id} name={p.name} className="tg-cx__pc-im" sizes="112px" />
        <span className="tg-cx__pc-tx">
          <b>{p.name}</b>
          <span className="tg-cx__meta">
            {p.rating != null && <span><Icon name="star" size={13} className="tg-cx__star" /><b>{p.rating.toLocaleString('vi-VN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</b>{p.reviews ? ` (${p.reviews.toLocaleString('vi-VN')} đánh giá)` : ''}</span>}
            <span><Icon name="pin" size={13} />{p.area}</span>
          </span>
          <span className="tg-cx__ds">{[p.category, p.hours ? `mở ${p.hours}` : null].filter(Boolean).join(' · ')}</span>
          {look && <span className="tg-cx__chp"><i>Gần kiểu bạn tả</i></span>}
        </span>
      </button>
      <button type="button" className={`tg-cx__heart ${saved ? 'is-on' : ''}`} aria-pressed={saved} aria-label={saved ? `Bỏ lưu ${p.name}` : `Lưu ${p.name}`} onClick={() => toggleSaved(id, p.name)}>
        {saved ? <HeartFill size={18} /> : <Icon name="heart" size={18} />}
      </button>
    </div>
  )
}

export function Board({ u, busy, onShow }: { u: Understanding | null; busy: boolean; onShow: () => void }) {
  useSnapshot() // the place cards read the snapshot once it lands
  const [group, setGroup] = useState<string | null>(null)
  const [all, setAll] = useState(false)
  const n = useCount(u?.matching ?? u?.total ?? 0)
  const ids = (u?.board.ids ?? []).filter((id) => info(id))
  const look = new Set(u?.board.vibe ?? [])
  const groups = Object.entries(ids.reduce<Record<string, number>>((m, id) => { const g = info(id)!.group; m[g] = (m[g] ?? 0) + 1; return m }, {}))
  const shown = group ? ids.filter((id) => info(id)!.group === group) : ids
  const told = !!u && (u.trip.length > 0 || u.soft.length > 0 || u.hard.length > 0 || u.vibes.length > 0)
  const when = u ? dateLine(u) : ''
  return (
    <aside className="tg-cx__side tg-cx__panel" aria-label="Nơi đang hợp với bạn">
      <div className="tg-cx__cover">
        <img src="/img/landing-p1.webp" alt="Đà Lạt" />
        <span className="tg-cx__glass is-l"><Icon name="pin" size={16} />Đà Lạt</span>
        {when && <span className="tg-cx__glass is-r"><Icon name="calendar" size={16} />{when}</span>}
      </div>
      <div className="tg-cx__sheet">
        <div className="tg-cx__hd">
          <p className="tg-cx__n"><b>{n.toLocaleString('vi-VN')}</b><span>{told ? 'địa điểm hợp' : 'địa điểm'}</span></p>
          {ids.length > 0 && <button type="button" className="tg-cx__all" onClick={() => setAll(true)}>Xem tất cả <Icon name="arrow" size={14} /></button>}
        </div>
        {u?.vibes.filter((v) => v.status === 'done' && v.places).map((v) => (
          <p key={v.target} className="tg-cx__look"><Icon name="sparkle" size={14} /><span><b>{v.places}</b> nơi {v.picked ? `cùng phong cách ${v.picked}` : `theo “${v.phrase}”${v.chosen.length ? ` (${v.chosen.join(', ')})` : ''}`} được xếp lên đầu</span></p>
        ))}
        {groups.length > 1 && (
          <div className="tg-cx__cats" role="group" aria-label="Lọc theo loại">
            {groups.map(([g, c]) => (
              <button key={g} type="button" className={group === g ? 'is-on' : ''} aria-pressed={group === g} onClick={() => setGroup(group === g ? null : g)}>
                <Icon name={GROUP_ICON[g as keyof typeof GROUP_ICON] ?? 'sparkle'} size={15} />{GROUP_LABEL[g] ?? g}<small>{c}</small>
              </button>
            ))}
          </div>
        )}
        <div className="tg-cx__feed">
          {shown.map((id, i) => <PlaceRow key={id} id={id} i={i} look={look.has(id)} />)}
          {!shown.length && <p className="tg-cx__empty">{u ? 'Kể thêm về chuyến đi, các nơi hợp sẽ hiện ở đây.' : 'Đang mở…'}</p>}
        </div>
        {u && u.missing.length > 0 && <p className="tg-cx__miss">Còn chưa rõ: {u.missing.map((m) => m.label).join(', ')}</p>}
        <button type="button" className="tg-cx__go" disabled={busy || !u} onClick={onShow}>Bắt đầu tìm <Icon name="arrow" size={18} /></button>
      </div>
      <Dialog.Root open={all} onOpenChange={setAll}>
        <Dialog.Portal>
          <Dialog.Overlay className="tg-cx__dim" />
          <Dialog.Content className="tg-cx__drawer" aria-describedby={undefined}>
            <header><Dialog.Title>{(u?.matching ?? 0).toLocaleString('vi-VN')} địa điểm</Dialog.Title><Dialog.Close className="tg-cx__x" aria-label="Đóng"><Icon name="x" size={18} /></Dialog.Close></header>
            <p className="tg-cx__drawer-note">{ids.length} nơi hợp nhất lúc này. Danh sách đầy đủ, kèm lý do, ở bước Lựa chọn.</p>
            <div className="tg-cx__grid">{ids.map((id, i) => <PlaceRow key={id} id={id} i={i} look={look.has(id)} />)}</div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </aside>
  )
}
