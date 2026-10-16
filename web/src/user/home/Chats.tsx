import * as Popover from '@radix-ui/react-popover'
import { useEffect, useState } from 'react'
import { navigate } from '../../router'
import { useAccount } from '../account'
import { loadInbox, openNote, type Note } from '../notify'
import { info } from '../lib'
import { useFriends } from '../social'
import { useUi } from '../store'
import { Link, PlacePhoto } from '../ui/common'
import { Icon } from '../ui/icons'
import { openPlace } from '../ui/PlaceSheet'
import { Avatar, openChat, openFriends, openTheme } from './dialogs'
import { themeOf } from './themes'

// The round buttons beside the avatar at the top of the sidebar: the notifications, and (only while the friends panel is closed) the
// one icon that opens it.
export function TopTools({ className = '', side = 'bottom' }: { className?: string; side?: 'bottom' | 'right' }) {
  const account = useAccount()
  const member = !!account && !account.guest
  return (
    <span className={`tg-tt ${className}`}>
      {member && <Bell side={side} />}
      <FriendsMenu side={side} />
    </span>
  )
}

// The friends icon opens a dropdown right under itself (the icon stays where it is): the friends, then your activity.
export function FriendsMenu({ side = 'bottom' }: { side?: 'bottom' | 'right' }) {
  const account = useAccount()
  const member = !!account && !account.guest
  const f = useFriends(member)
  const [open, setOpen] = useState(false)
  const unread = f?.friends.reduce((n, p) => n + (p.unread ?? 0), 0) ?? 0
  const online = f?.friends.filter((p) => p.online).length ?? 0
  const label = ['Bạn bè', online ? `${online} bạn đang online` : null, unread ? `${unread} tin chưa đọc` : null, f?.incoming.length ? `${f.incoming.length} lời mời kết bạn` : null].filter(Boolean).join(', ')
  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger className={`tg-tt__btn ${online ? 'is-online' : ''} ${open ? 'is-open' : ''}`} aria-label={label} title="Bạn bè">
        <Icon name="users" size={18} />
        {unread > 0 ? <b className="tg-hf__unread">{unread}</b> : (f?.incoming.length ?? 0) > 0 && <i className="tg-hf__dot" />}
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content className="tg tg-home tg-fp" side={side} align={side === 'right' ? 'start' : 'end'} sideOffset={10} collisionPadding={16} aria-label="Bạn bè và hoạt động của bạn">
          <FriendsPanel member={member} close={() => setOpen(false)} />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}

function FriendsPanel({ member, close }: { member: boolean; close: () => void }) {
  const f = useFriends(member)
  const recent = useUi((u) => u.recent)
  const saved = useUi((u) => u.saved)
  const savedThemes = useUi((u) => u.savedThemes)
  const rows = recent.length ? recent.map((r) => ({ ...r, sub: 'Đã xem gần đây' }))
    : [...savedThemes.map((id) => ({ kind: 'theme' as const, id, sub: 'Đã lưu chủ đề' })), ...saved.map((id) => ({ kind: 'place' as const, id, sub: 'Đã lưu' }))]
  const shown = rows.filter((r) => (r.kind === 'theme' ? themeOf(r.id) : info(r.id))).slice(0, 5)
  const unread = f?.friends.reduce((n, p) => n + (p.unread ?? 0), 0) ?? 0
  return (
    <>
      <section>
        <div className="tg-hf__ahead">
          <h2>Bạn bè{unread > 0 && <b className="tg-hf__unread" aria-label={`${unread} tin chưa đọc`}>{unread}</b>}</h2>
          {member && <button type="button" className="tg-hb-icon" aria-label="Tìm bạn và lời mời kết bạn" title="Tìm bạn" onClick={() => { close(); openFriends() }}><Icon name="users" size={15} />{(f?.incoming.length ?? 0) > 0 && <i className="tg-hf__dot" />}</button>}
        </div>
        {!member ? (
          <p className="tg-hf__note">Đăng nhập Google để kết bạn, nhắn tin và gửi lịch trình cho nhau. <Link to="/login" className="tg-hb-link" onClick={close}>Đăng nhập</Link></p>
        ) : !f ? <p className="tg-hf__note">Đang tải…</p> : (
          <>
            {f.incoming.length > 0 && <button type="button" className="tg-hf__invite" onClick={() => { close(); openFriends() }}><Icon name="users" size={14} />{f.incoming.length} lời mời kết bạn</button>}
            {f.friends.length ? (
              <ul className="tg-hf__friends">
                {f.friends.map((p) => (
                  <li key={p.id}>
                    <button type="button" className="tg-hf__friend" onClick={() => { close(); openChat(p) }}>
                      <Avatar p={p} size={28} dot />
                      <span className="tg-hf__fc"><strong>{p.name}</strong><small>{p.online ? 'Đang online' : 'Offline'}</small></span>
                      {(p.unread ?? 0) > 0 && <b className="tg-hf__unread" aria-label={`${p.unread} tin chưa đọc`}>{p.unread}</b>}
                    </button>
                  </li>
                ))}
              </ul>
            ) : <p className="tg-hf__note">Chưa có bạn bè. <button type="button" className="tg-hb-link" onClick={() => { close(); openFriends() }}>Tìm theo nickname</button></p>}
          </>
        )}
      </section>
      <section className="tg-hf__mine">
        <div className="tg-hf__ahead"><h2>Hoạt động của bạn</h2><Icon name="clock" size={14} /></div>
        {shown.length ? (
          <ul className="tg-hf__hist">
            {shown.map((r) => {
              const t = r.kind === 'theme' ? themeOf(r.id) : null
              return (
                <li key={`${r.kind}:${r.id}`}>
                  <button type="button" className="tg-hf__row" onClick={(e) => { const img = e.currentTarget.querySelector('img'); close(); if (t) openTheme(r.id); else openPlace(r.id, img) }}>
                    {t ? <img src={t.photo} alt="" /> : <PlacePhoto id={r.id} className="tg-hf__thumb" />}
                    <span className="tg-hf__fc"><strong>{t ? t.short : info(r.id)?.name}</strong><small>{r.sub}</small></span>
                  </button>
                </li>
              )
            })}
          </ul>
        ) : <p className="tg-hf__note">Nơi và chủ đề bạn mở hoặc lưu sẽ hiện ở đây.</p>}
      </section>
    </>
  )
}

const ago = (iso: string) => {
  const m = Math.max(0, Math.round((Date.now() - +new Date(iso)) / 60000))
  if (m < 1) return 'Vừa xong'
  if (m < 60) return `${m} phút trước`
  if (m < 1440) return `${Math.round(m / 60)} giờ trước`
  return new Date(iso).toLocaleDateString('vi-VN', { day: 'numeric', month: 'numeric' })
}

// A small floating box over a blurred page, not a page of its own; "Xem tất cả" opens the full inbox.
function Bell({ side }: { side: 'bottom' | 'right' }) {
  const [open, setOpen] = useState(false)
  const [list, setList] = useState<Note[] | null>(null)
  useEffect(() => { loadInbox().then(setList, () => setList([])) }, [open])
  const unread = list?.filter((n) => !n.opened).length ?? 0
  const label = unread ? `Thông báo, ${unread} chưa mở` : 'Thông báo'
  const shown = (list ?? []).slice(0, 5)
  return (
    <Popover.Root open={open} onOpenChange={setOpen} modal>
      <Popover.Trigger className={`tg-tt__btn ${open ? 'is-open' : ''}`} aria-label={label} title="Thông báo">
        <Icon name="bell" size={18} />
        {unread > 0 && <i className="tg-hf__dot" />}
      </Popover.Trigger>
      <Popover.Portal>
        <div>
          <div className="tg-hd__veil" />
          <Popover.Content className="tg tg-home tg-nb" side={side} align={side === 'right' ? 'start' : 'end'} sideOffset={10} collisionPadding={16} aria-label="Thông báo">
          <h2>Thông báo</h2>
          {!list ? <p className="tg-nb__none">Đang mở…</p> : shown.length === 0 ? <p className="tg-nb__none">Chưa có thông báo nào. Khi chuyến đã chốt lịch, TripGuardian sẽ nhắn vài điều có ích.</p> : (
            <ul>
              {shown.map((n) => (
                <li key={n.id}>
                  <button type="button" className={n.opened ? '' : 'is-new'} onClick={() => { setOpen(false); void openNote(n.id, 'inbox'); navigate(n.url) }}>
                    <span><b>{n.title}</b><small>{n.body}</small><time dateTime={n.sent_at}>{ago(n.sent_at)}</time></span>
                    {!n.opened && <i className="tg-nb__dot" aria-label="Chưa mở" />}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <Link to="/inbox" className="tg-nb__all" onClick={() => setOpen(false)}>Xem tất cả</Link>
          </Popover.Content>
        </div>
      </Popover.Portal>
    </Popover.Root>
  )
}
