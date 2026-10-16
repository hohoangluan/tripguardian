import { initialOf, useAccount } from '../account'
import { Link } from '../ui/common'
import { TopTools } from './Chats'

// The signed-in person: avatar (opens the profile to edit), name, @nickname, and the notification and friends buttons beside them.
// `compact` (pages other than the home page): the avatar and the buttons only.
export function Who({ compact = false, className = '' }: { compact?: boolean; className?: string }) {
  const account = useAccount()
  const guest = !!account?.guest
  const who = guest ? 'Khách' : account?.name || account?.nickname || 'Bạn'
  const handle = guest ? null : account?.nickname ? `@${account.nickname}` : account?.email ?? null
  return (
    <div className={`tg-hf__who ${compact ? 'is-compact' : ''} ${className}`}>
      <Link to="/profile" className="tg-hf__me" aria-label={`${who}, mở hồ sơ để chỉnh`} title="Chỉnh hồ sơ">
        <span className="tg-hf__face" aria-hidden="true">{account?.avatar ? <img src={account.avatar} alt="" referrerPolicy="no-referrer" /> : initialOf(account)}</span>
        {!compact && <span className="tg-hf__name"><strong>{who}</strong>{handle && <small>{handle}</small>}</span>}
      </Link>
      <TopTools />
    </div>
  )
}
