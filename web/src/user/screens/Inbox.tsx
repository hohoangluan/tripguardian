import { useEffect, useState } from 'react'
import { navigate } from '../../router'
import { loadInbox, openNote, type Note } from '../notify'
import { ArtCup, Busy, Empty, go } from '../ui/common'
import { Page, useTitle } from '../ui/Shell'

// Hộp thông báo: every note sent also lands here, push or no push (docs/COMPANION.md §Thông báo).
export function Inbox() {
  useTitle('Thông báo')
  const [list, setList] = useState<Note[] | null>(null)
  useEffect(() => { loadInbox().then(setList, () => setList([])) }, [])
  if (!list) return <Page><Busy text="Đang mở hộp thông báo…" /></Page>
  return (
    <Page>
      <header className="tg-head"><div><p className="tg-kicker">Thông báo</p><h1>Hộp thông báo</h1><p>Ít thôi, đúng lúc thôi. Tắt từng loại trong Hồ sơ.</p></div></header>
      {list.length === 0 ? <Empty art={<ArtCup />} title="Chưa có thông báo nào" body="Khi chuyến đã chốt lịch, TripGuardian sẽ nhắn vài điều có ích: bản tin sáng, giờ hoàng hôn, chỗ nên đặt trước." action={<button type="button" className="tg-btn tg-btn--primary" onClick={() => go('/today')}>Mở Hôm nay</button>} /> : (
        <ul className="tg-inbox">{list.map((n) => (
          <li key={n.id} className={n.opened ? '' : 'is-new'}>
            <button type="button" onClick={() => { void openNote(n.id, 'inbox'); navigate(n.url) }}>
              <b>{n.title}</b><span>{n.body}</span><small className="tg-faint">{new Date(n.sent_at).toLocaleString('vi-VN', { dateStyle: 'short', timeStyle: 'short' })}</small>
            </button>
          </li>
        ))}</ul>
      )}
    </Page>
  )
}
