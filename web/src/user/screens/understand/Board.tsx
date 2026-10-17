import { useEffect, useRef, useState } from 'react'
import type { Understanding } from '../../tu/types'
import { Icon, type IconName } from '../../ui/icons'
import { dateLine, requiredLines } from '../../ui/Ticket'

const ICONS: Record<string, IconName> = { trip: 'calendar', companions: 'users', mobility: 'route', care: 'heart', pace: 'sliders', budget: 'wallet', lodging: 'bed' }

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

export function Board({ u, busy, preview, onShow, onOpen }: { u: Understanding | null; busy: boolean; preview: Set<string>; onShow: () => void; onOpen: (target: string | null) => void }) {
  const n = useCount(u?.matching ?? u?.total ?? 0)
  const lines = u ? requiredLines(u) : []
  const groups = (u?.required ?? []).map(group => ({ ...group, line: lines.find(line => line.key === group.key), active: preview.has(group.key) }))
  // The board keeps the trip to its dates on one line; day hours and their reasons stay in the ticket and the read-back.
  const short = (key: string, value: string) => (key === 'trip' && u ? dateLine(u) || value : value)
  // A group counts once it holds a value, even when the server still wants more of it (`done` = every sub-fact answered).
  const filled = (group: (typeof groups)[number]) => group.done || Boolean(group.line?.value)
  const done = groups.filter(filled).length
  const complete = groups.length > 0 && groups.every(group => group.done)
  const percent = groups.length ? Math.round(done / groups.length * 100) : 0
  return (
    <aside className="tg-cx__side tg-cx__panel tg-trail" aria-label="Nơi đang hợp với bạn">
      <header className="tg-trail__head">
        <h2>Những nơi đang hợp</h2>
        <p>{u ? <><b>{n.toLocaleString('vi-VN')}</b> địa điểm</> : <span>Đang mở…</span>}</p>
      </header>
      <section className="tg-ticket2" aria-label="Thông tin chuyến đi">
        <div className="tg-ticket2__bar">
          <span className="tg-ticket2__pill">Thông tin chuyến</span>
          <i aria-hidden="true" />
          <span className={`tg-ticket2__state ${busy ? 'is-busy' : ''}`} role="status"><Icon name="check" size={13} strokeWidth={2.4} />{busy ? 'Đang cập nhật' : complete ? 'Đã đủ thông tin' : 'Đang ghi nhận'}</span>
        </div>
        <ol className="tg-cx__steps2">
          {groups.map(group => (
            <li key={group.key} className={filled(group) ? 'is-done' : group.active ? 'is-working' : ''}>
              <span className="tg-cx__mark" aria-hidden="true"><Icon name={ICONS[group.key] ?? 'info'} size={22} /></span>
              <div className="tg-progress__row">
                <div className="tg-progress__top"><h4>{group.title ?? group.label}</h4><small>{group.done ? 'Đã ghi nhận' : group.active ? 'Đang ghi nhận…' : group.line?.value ? 'Cần bổ sung' : 'Chưa điền'}</small></div>
                <p className={group.line?.value ? 'tg-cx__val' : 'tg-cx__ask'} title={group.line?.value || undefined}>{group.line?.value ? short(group.key, group.line.value) : group.done ? 'Đã ghi nhận' : `Bổ sung ${(group.title ?? group.label).toLowerCase()}`}</p>
                {<button type="button" className="tg-link tg-progress__edit" disabled={busy} aria-label={`Sửa ${(group.title ?? group.label).toLowerCase()}`} onClick={() => onOpen(group.key)}>Sửa</button>}
              </div>
            </li>
          ))}
        </ol>
        <footer className="tg-ticket2__foot">
          <div className="tg-ticket2__ring" role="progressbar" aria-label="Thông tin chuyến đi đã ghi nhận" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent} aria-valuetext={`${done} trên ${groups.length} thông tin`}>
            <svg viewBox="0 0 120 120" aria-hidden="true">
              <circle className="tg-ticket2__track" cx="60" cy="60" r="50" />
              {done > 0 && <circle className="tg-ticket2__arc" cx="60" cy="60" r="50" pathLength={100} strokeDasharray={`${percent} 100`} />}
            </svg>
            <span><b>{done}/{groups.length}</b><small>thông tin</small></span>
          </div>
          <div>
            <small>Chuyến của bạn</small>
            <h3>{done ? 'Chuyến Đà Lạt của bạn' : 'Kể mình nghe chuyến đi'}</h3>
          </div>
        </footer>
      </section>
      <button type="button" className="tg-cx__go" disabled={busy || !u} onClick={onShow}><Icon name="sparkle" size={20} />Tiếp tục đến chọn nơi</button>
    </aside>
  )
}
