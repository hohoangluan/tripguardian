import { useEffect, useState } from 'react'
import { tripTitle } from '../../home/dialogs'
import { tripSummaries } from '../../pd/api'
import type { TripSummary } from '../../pd/types'
import { Icon } from '../../ui/icons'

// A chat is named after its first message (like ChatGPT); a trip with no words yet, or one listed by an older harness, falls back to its place and days.
const chatName = (t: TripSummary) => t.title || (t.days ? tripTitle(t) : 'Cuộc trò chuyện mới')

export function History({ active, busy, onNew, onOpen }: { active: string | null; busy: boolean; onNew: () => void; onOpen: (trip: TripSummary) => void }) {
  const [list, setList] = useState<TripSummary[] | null>(null)
  const [error, setError] = useState(false)
  const [query, setQuery] = useState('')
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    if (busy) return
    let alive = true
    setError(false)
    tripSummaries().then(items => { if (alive) setList(items) }).catch(() => { if (alive) setError(true) })
    return () => { alive = false }
  }, [active, busy, retry])
  const q = query.trim().toLocaleLowerCase('vi-VN')
  const shown = list?.filter(t => chatName(t).toLocaleLowerCase('vi-VN').includes(q)) ?? []
  return (
    <aside className="tg-history" aria-label="Lịch sử chat">
      <header className="tg-history__head">
        <h2>Lịch sử chat</h2>
        <button type="button" className="tg-history__new" aria-label="Tạo chuyến đi mới" title="Tạo chuyến đi mới" disabled={busy} onClick={onNew}><Icon name="plus" size={23} /></button>
      </header>
      <label className="tg-history__search"><Icon name="search" size={17} /><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Tìm trong lịch sử…" aria-label="Tìm trong lịch sử" /></label>
      <div className="tg-history__list">
        {error ? <div className="tg-history__empty" role="status"><p>Chưa tải được lịch sử.</p><button type="button" className="tg-link" onClick={() => setRetry(n => n + 1)}>Thử lại</button></div>
          : !list ? <p className="tg-history__empty" role="status">Đang tải lịch sử…</p>
          : shown.length === 0 ? <p className="tg-history__empty">{q ? 'Không tìm thấy chuyến phù hợp.' : 'Những chuyến bạn bắt đầu sẽ nằm ở đây.'}</p>
          : <><p className="tg-history__label">Chuyến của bạn</p>{shown.map(t => (
            <button key={t.id} type="button" className={`tg-history__entry ${t.id === active ? 'is-active' : ''}`} aria-current={t.id === active ? 'true' : undefined} disabled={busy} onClick={() => { setQuery(''); onOpen(t) }}>
              <strong>{chatName(t)}</strong>
            </button>
          ))}</>}
      </div>
      <footer className="tg-history__foot"><Icon name="lock" size={14} /><span>Mỗi chuyến đi, một câu chuyện riêng.</span></footer>
    </aside>
  )
}
