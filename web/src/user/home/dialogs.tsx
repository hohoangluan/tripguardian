import * as Dialog from '@radix-ui/react-dialog'
import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from 'react'
import { updateProfile, useAccount } from '../account'
import { track } from '../events'
import { dateRange } from '../lib'
import { tripSummaries } from '../pd/api'
import type { TripSummary } from '../pd/types'
import { acceptFriend, friendTyping, importTrip, initials, loadThread, refreshFriends, removeFriend, requestFriend, searchPeople, sendMessage, sendTyping, useFriends, type Message, type Person } from '../social'
import { toast } from '../store'
import { hasTrip, STEPS, useTrip, type TripState } from '../trip'
import { go } from '../ui/common'
import { Icon } from '../ui/icons'
import { themeOf } from './themes'
import { ThemeBlog } from './ThemeBlog'

// The home frame's dialogs: one at a time, opened from anywhere in the frame (sidebar, home, friends column, trips).
type Open =
  | { kind: 'theme'; id: string }
  | { kind: 'create'; prompt: string }
  | { kind: 'friends' }
  | { kind: 'chat'; friend: Person }
  | { kind: 'share'; trip: TripSummary }
  | null

const EVENT = 'tg:home-dialog'
let open: Open = null
let familiar = true // "Theo gu quen thuộc" (returning) or "Lần này khác" (first) for the next trip
const set = (o: Open) => { open = o; dispatchEvent(new Event(EVENT)) }
const subscribe = (cb: () => void) => { addEventListener(EVENT, cb); return () => removeEventListener(EVENT, cb) }
export const useHomeState = () => useSyncExternalStore(subscribe, () => open)
export const useFamiliar = () => useSyncExternalStore(subscribe, () => familiar)
export const setFamiliar = (v: boolean) => { familiar = v; dispatchEvent(new Event(EVENT)) }

// `from`: the photo of the card the theme was opened from, so the blog's photo can fly out of it (only the first opening, not a tab switch).
let blogFrom: HTMLElement | null = null
export const openTheme = (id: string, from?: HTMLElement | null) => { track('theme_open', { theme: id }); blogFrom = from ?? null; set({ kind: 'theme', id }) }
export const openCreate = (prompt = '') => set({ kind: 'create', prompt })
export const openFriends = () => set({ kind: 'friends' })
export const openChat = (friend: Person) => set({ kind: 'chat', friend })
export const openShare = (trip: TripSummary) => set({ kind: 'share', trip })
const close = () => set(null)

// A new trip: forget the current journey on this screen (it stays in Chuyến của tôi) and open Tìm hiểu.
export function useBegin() {
  const { trip, dispatch } = useTrip()
  return (patch: Partial<Pick<TripState, 'startText' | 'startWith' | 'experience'>>) => {
    dispatch({ type: 'reset' })
    dispatch({ type: 'set', patch: { experience: hasTrip(trip) ? (familiar ? 'returning' : 'first') : null, ...patch } })
    try { localStorage.removeItem('tg.tu.v1') } catch { /* nothing stored */ }
    go('/understand')
  }
}

// Open a journey of this account at the step it stopped on (or `to`).
export function useOpenJourney() {
  const { dispatch } = useTrip()
  return (j: { id: string; stage: TripSummary['stage'] }, to?: string) => {
    dispatch({ type: 'reset' })
    dispatch({ type: 'set', patch: { journeyId: j.id, decisionId: j.stage === 'trip' ? null : j.id, planningId: j.stage === 'planning' ? j.id : null } })
    go(to ?? STEPS[{ trip: 0, decision: 1, planning: 2 }[j.stage]].path)
  }
}

export const tripTitle = (t: { days: number | null }) => `Đà Lạt${t.days ? ` ${t.days} ngày` : ''}`
export const tripLine = (t: TripSummary) => [dateRange(t.start_date, t.days), t.people ? `${t.people} người` : null, `${t.places.length} nơi`].filter(Boolean).join(' · ')

const AV = ['rose', 'peach', 'green', 'blue', 'charcoal']
export function Avatar({ p, size = 28, dot = false }: { p: Person; size?: number; dot?: boolean }) {
  const tone = AV[[...p.id].reduce((n, c) => n + c.charCodeAt(0), 0) % AV.length]
  return (
    <span className={`tg-av tg-av--${tone} ${dot && p.online ? 'is-online' : ''}`} style={{ width: size, height: size }} aria-hidden="true">
      {p.avatar ? <img src={p.avatar} alt="" referrerPolicy="no-referrer" /> : initials(p)}
    </span>
  )
}

const ERR: Record<string, string> = {
  'nickname is taken': 'Nickname này đã có người dùng.',
  'choose a nickname first': 'Bạn đặt nickname trước đã nhé.',
  'not a friend': 'Hai bạn chưa là bạn bè.',
}
const say = (e: unknown) => {
  const m = e instanceof Error ? (e as { detail?: string }).detail || e.message : ''
  return ERR[m] ?? (m.startsWith('nickname:') ? 'Nickname 3–24 ký tự: chữ thường không dấu, số, dấu chấm, gạch dưới.' : 'Chưa làm được, bạn thử lại nhé.')
}

export function HomeDialogs() {
  const o = useHomeState()
  const theme = o?.kind === 'theme' ? themeOf(o.id) : null
  return (
    <>
      <ThemeBlog id={theme?.id ?? null} from={blogFrom} onPick={(id) => openTheme(id)} onStart={(t) => openCreate(t.prompt)} onClose={close} />
      {o && o.kind !== 'theme' && <HomeDialog o={o} />}
    </>
  )
}

function HomeDialog({ o }: { o: Exclude<Open, { kind: 'theme' } | null> }) {
  const title = o.kind === 'create' ? 'Kể mình nghe chuyến đi của bạn' : o.kind === 'friends' ? 'Bạn bè' : o.kind === 'chat' ? o.friend.name : 'Gửi lịch trình cho bạn'
  return (
    <Dialog.Root open onOpenChange={(v) => { if (!v) close() }}>
      <Dialog.Portal>
        <Dialog.Overlay className="tg-hd__veil" />
        <Dialog.Content className={`tg tg-home tg-hd ${o.kind === 'chat' ? 'tg-hd--chat' : ''}`} aria-describedby={undefined} onOpenAutoFocus={o.kind === 'chat' ? (e) => e.preventDefault() : undefined}>
          {o.kind === 'chat' ? <ChatWindow friend={o.friend} key={o.friend.id} /> : (
            <div className="tg-hd__top">
              <Dialog.Title>{title}</Dialog.Title>
              <Dialog.Close className="tg-hd__x" aria-label="Đóng"><Icon name="x" size={16} /></Dialog.Close>
            </div>
          )}
          {o.kind === 'create' && <CreateBody prompt={o.prompt} />}
          {o.kind === 'friends' && <FriendsBody />}
          {o.kind === 'share' && <ShareBody trip={o.trip} />}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

const CHIPS = ['3 ngày', '2 người', 'Đi với người yêu', 'Xe máy', 'Cà phê', 'Săn mây', 'Ít đông']
function CreateBody({ prompt }: { prompt: string }) {
  const begin = useBegin()
  const [text, setText] = useState(prompt)
  const ref = useRef<HTMLTextAreaElement>(null)
  useEffect(() => { ref.current?.focus() }, [])
  const chip = (c: string) => setText((t) => (t.includes(c) ? t.replace(c, '').replace(/,\s*,/g, ',').replace(/^,\s*|,\s*$/g, '').trim() : [t, c].filter(Boolean).join(', ')))
  return (
    <form className="tg-hd__body" onSubmit={(e) => { e.preventDefault(); close(); if (text.trim()) begin({ startText: text.trim(), startWith: null }); else begin({ startWith: 'nothing', startText: null }) }}>
      <h3>Chuyến tới, bạn muốn gì?</h3>
      <p>Nói một câu là được. Mình sẽ hỏi thêm để hiểu đúng chuyến đi của bạn.</p>
      <label htmlFor="tg-hd-prompt">Ý tưởng chuyến đi</label>
      <textarea id="tg-hd-prompt" ref={ref} rows={4} maxLength={1000} value={text} placeholder="3 ngày ở Đà Lạt, đi cùng người yêu, thích cà phê và săn mây…" onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); e.currentTarget.form?.requestSubmit() } }} />
      <div className="tg-hd__chips" role="group" aria-label="Gợi ý nhanh">{CHIPS.map((c) => <button key={c} type="button" aria-pressed={text.includes(c)} onClick={() => chip(c)}>{c}</button>)}</div>
      <button type="submit" className="tg-hb-go tg-hd__act">{text.trim() ? 'Bắt đầu tìm hiểu chuyến đi' : 'Bắt đầu, chưa có gì trong đầu'}<Icon name="arrow" size={16} /></button>
    </form>
  )
}

function NicknameForm() {
  const account = useAccount()
  const [v, setV] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  if (!account || account.nickname) return null
  return (
    <form className="tg-hd__nick" onSubmit={(e) => {
      e.preventDefault()
      setBusy(true)
      updateProfile({ nickname: v }).then(() => { setErr(''); toast('Đã lưu nickname') }, (x) => setErr(say(x))).finally(() => setBusy(false))
    }}>
      <p><b>Đặt nickname</b> để bạn bè tìm thấy bạn và để gửi lời mời kết bạn.</p>
      <div className="tg-hd__line"><span className="tg-hd__at">@</span><input value={v} maxLength={24} placeholder="ví dụ: an.nguyen" onChange={(e) => setV(e.target.value.toLowerCase())} aria-label="Nickname" /><button type="submit" className="tg-hb-go" disabled={busy || v.length < 3}>Lưu</button></div>
      {err && <p className="tg-hd__err" role="alert">{err}</p>}
    </form>
  )
}

function PersonRow({ p, children, onOpen }: { p: Person; children?: ReactNode; onOpen?: () => void }) {
  const body = <><Avatar p={p} size={34} dot={p.relation === undefined || p.relation === 'friend'} /><span className="tg-hd__pc"><strong>{p.name}</strong><small>{p.nickname ? `@${p.nickname}` : ''}{p.bio ? ` · ${p.bio}` : ''}</small></span></>
  return <li className="tg-hd__person">{onOpen ? <button type="button" className="tg-hd__pmain" onClick={onOpen}>{body}</button> : <span className="tg-hd__pmain">{body}</span>}<span className="tg-hd__pact">{children}</span></li>
}

function FriendsBody() {
  const account = useAccount()
  const f = useFriends(true)
  const [q, setQ] = useState('')
  const [found, setFound] = useState<Person[] | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (q.trim().replace(/^@/, '').length < 2) { setFound(null); return }
    const t = setTimeout(() => { searchPeople(q).then(setFound, () => setFound([])) }, 250)
    return () => clearTimeout(t)
  }, [q])
  const run = (p: Promise<unknown>, done?: string) => {
    setBusy(true)
    p.then(() => { if (done) toast(done); if (q) searchPeople(q).then(setFound, () => {}) }, (e) => toast(say(e))).finally(() => setBusy(false))
  }
  const action = (p: Person) => p.relation === 'friend' ? <span className="tg-hd__tag">Bạn bè</span>
    : p.relation === 'sent' ? <button type="button" className="tg-hb-soft" disabled={busy} onClick={() => run(removeFriend(p.id), 'Đã hủy lời mời')}>Hủy lời mời</button>
    : p.relation === 'received' ? <button type="button" className="tg-hb-go" disabled={busy} onClick={() => run(acceptFriend(p.id), `Bạn và ${p.name} đã là bạn bè`)}>Chấp nhận</button>
    : <button type="button" className="tg-hb-go" disabled={busy || !account?.nickname} onClick={() => run(requestFriend(p.id), `Đã gửi lời mời tới ${p.name}`)}>Kết bạn</button>
  return (
    <div className="tg-hd__body">
      <NicknameForm />
      <label className="tg-hd__search"><Icon name="search" size={15} /><span className="tg-sr">Tìm theo nickname</span><input value={q} placeholder="Tìm bạn theo nickname" onChange={(e) => setQ(e.target.value)} autoComplete="off" /></label>
      {found && (found.length ? <ul className="tg-hd__people">{found.map((p) => <PersonRow key={p.id} p={p}>{action(p)}</PersonRow>)}</ul> : <p className="tg-hd__empty">Không có ai với nickname này.</p>)}
      {!found && f && (
        <>
          {f.incoming.length > 0 && <><h4>Lời mời kết bạn <b>{f.incoming.length}</b></h4><ul className="tg-hd__people">{f.incoming.map((p) => <PersonRow key={p.id} p={{ ...p, relation: 'received' }}><button type="button" className="tg-hb-go" disabled={busy} onClick={() => run(acceptFriend(p.id), `Bạn và ${p.name} đã là bạn bè`)}>Chấp nhận</button><button type="button" className="tg-hb-soft" disabled={busy} onClick={() => run(removeFriend(p.id))}>Từ chối</button></PersonRow>)}</ul></>}
          <h4>Bạn bè <b>{f.friends.length}</b></h4>
          {f.friends.length ? <ul className="tg-hd__people">{f.friends.map((p) => <PersonRow key={p.id} p={p} onOpen={() => openChat(p)}><button type="button" className="tg-hb-soft" onClick={() => openChat(p)}>Nhắn tin</button><button type="button" className="tg-hb-icon" disabled={busy} aria-label={`Hủy kết bạn với ${p.name}`} title="Hủy kết bạn" onClick={() => { if (confirm(`Hủy kết bạn với ${p.name}?`)) run(removeFriend(p.id)) }}><Icon name="x" size={14} /></button></PersonRow>)}</ul> : <p className="tg-hd__empty">Chưa có bạn bè. Tìm theo nickname ở trên để gửi lời mời.</p>}
          {f.outgoing.length > 0 && <><h4>Đã gửi lời mời</h4><ul className="tg-hd__people">{f.outgoing.map((p) => <PersonRow key={p.id} p={{ ...p, relation: 'sent' }}><button type="button" className="tg-hb-soft" disabled={busy} onClick={() => run(removeFriend(p.id), 'Đã hủy lời mời')}>Hủy lời mời</button></PersonRow>)}</ul></>}
        </>
      )}
    </div>
  )
}

// Emoji like a messenger: a small set that fits one panel, grouped, and a thumbs-up that sends itself when the box is empty.
const EMOJI: [string, string[]][] = [
  ['Hay dùng', ['😀', '😂', '🥰', '😍', '😘', '😊', '😎', '🤗', '😅', '🥹', '😭', '😴', '🤔', '😮', '🙏', '👍', '👏', '🙌', '❤️', '🔥', '✨', '🎉']],
  ['Chuyến đi', ['🌄', '☁️', '🌲', '⛰️', '🌸', '🌧️', '☕', '🍜', '🍲', '🥐', '🍓', '🛵', '🚗', '🏨', '⛺', '📸', '🗺️', '🧳', '🎒', '⏰', '📍', '💰']],
  ['Cảm xúc', ['😆', '🤩', '😋', '😌', '😢', '😤', '😱', '🥶', '🤒', '😬', '🙈', '🤝', '💪', '👌', '✌️', '🤞', '💯', '💜', '💗', '🎶', '🌙', '☀️']],
]
const LIKE = '👍'
// A message of one to three emoji and nothing else is drawn large, as messengers do.
const onlyEmoji = (s: string) => /^(?:\p{Extended_Pictographic}(?:\uFE0F|\u200D\p{Extended_Pictographic}|\p{Emoji_Modifier})*\s*){1,3}$/u.test(s.trim())

function EmojiPicker({ onPick }: { onPick: (e: string) => void }) {
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState(0)
  return (
    <>
      <button type="button" className="tg-hb-icon" aria-label="Chèn emoji" aria-expanded={open} title="Emoji" onClick={() => setOpen((o) => !o)}><Icon name="smile" size={18} /></button>
      {open && (
        <div className="tg-emoji" role="dialog" aria-label="Chọn emoji">
          <div className="tg-emoji__tabs" role="tablist">{EMOJI.map(([l], i) => <button key={l} type="button" role="tab" aria-selected={tab === i} onClick={() => setTab(i)}>{l}</button>)}</div>
          <div className="tg-emoji__grid">{EMOJI[tab][1].map((e) => <button key={e} type="button" aria-label={e} onClick={() => onPick(e)}>{e}</button>)}</div>
        </div>
      )}
    </>
  )
}

const timeOf = (iso: string) => new Date(iso).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })
// The line between two stretches of talk, as a messenger draws it: the time today, the date and time before.
const stamp = (iso: string) => {
  const d = new Date(iso)
  return d.toDateString() === new Date().toDateString() ? timeOf(iso) : `${timeOf(iso)} ${d.getDate()} Tháng ${d.getMonth() + 1}, ${d.getFullYear()}`
}
const GAP = 30 * 60_000

// The friend as the poll last saw them (online, unread), not as they were when the chat opened.
const useLive = (friend: Person) => useFriends(true)?.friends.find((p) => p.id === friend.id) ?? friend

// The chat, as a window over a blurred page (the Dialog around it); it stays until closed.
function ChatWindow({ friend }: { friend: Person }) {
  const live = useLive(friend)
  const [msgs, setMsgs] = useState<Message[] | null>(null)
  const [text, setText] = useState('')
  const [picking, setPicking] = useState<TripSummary[] | null>(null)
  const [busy, setBusy] = useState(false)
  const openJourney = useOpenJourney()
  const end = useRef<HTMLDivElement>(null)
  const last = useRef(0)
  const box = useRef<HTMLInputElement>(null)
  useEffect(() => {
    let alive = true
    const pull = () => loadThread(friend.id, last.current).then((more) => {
      if (!alive || !more.length) return
      last.current = more[more.length - 1].id
      setMsgs((m) => [...(m ?? []), ...more.filter((x) => !(m ?? []).some((y) => y.id === x.id))])
      refreshFriends().catch(() => {})
    }, () => {})
    pull().then(() => setMsgs((m) => m ?? []))
    const t = setInterval(() => { if (document.visibilityState === 'visible') pull() }, 4000)
    return () => { alive = false; clearInterval(t) }
  }, [friend.id])
  useEffect(() => { end.current?.scrollIntoView({ block: 'end' }) }, [msgs?.length, picking])
  useEffect(() => { box.current?.focus() }, [])
  const push = (m: Message) => { last.current = Math.max(last.current, m.id); setMsgs((x) => [...(x ?? []), m]) }
  const send = (body: string, journey?: string) => {
    setBusy(true)
    return sendMessage(friend.id, body, journey).then((m) => { push(m); setText(''); told.current = 0; void sendTyping(friend.id, false) }, (e) => toast(say(e))).finally(() => setBusy(false))
  }
  const take = (m: Message) => {
    setBusy(true)
    importTrip(m.id).then((j) => {
      setMsgs((x) => (x ?? []).map((y) => (y.id === m.id ? { ...y, imported: j.id } : y)))
      toast('Đã lấy về thành chuyến của bạn')
      close()
      openJourney(j)
    }, (e) => toast(say(e))).finally(() => setBusy(false))
  }
  // "..." while the friend types: asked every 2 s, and said once every 2.5 s while this box is being typed in.
  const [theyType, setTheyType] = useState(false)
  const told = useRef(0)
  useEffect(() => {
    let alive = true
    const ask = () => { if (document.visibilityState === 'visible') friendTyping(friend.id).then((v) => { if (alive) setTheyType(v) }) }
    ask()
    const t = setInterval(ask, 2000)
    return () => { alive = false; clearInterval(t); void sendTyping(friend.id, false) }
  }, [friend.id])
  useEffect(() => { if (theyType) end.current?.scrollIntoView({ block: 'end' }) }, [theyType])
  const typed = (v: string) => {
    setText(v)
    if (!v.trim()) { if (told.current) { told.current = 0; void sendTyping(friend.id, false) } return }
    if (Date.now() - told.current > 2500) { told.current = Date.now(); void sendTyping(friend.id, true) }
  }
  const lastMine = msgs ? [...msgs].reverse().find((m) => m.mine)?.id : undefined
  return (
    <section className="tg-cw" aria-label={`Trò chuyện với ${live.name}`}>
      <header className="tg-cw__top">
        <span className="tg-cw__who"><Avatar p={live} size={36} dot /><span><Dialog.Title asChild><strong>{live.name}</strong></Dialog.Title><small>{live.online ? 'Đang hoạt động' : live.nickname ? `@${live.nickname}` : 'Không hoạt động'}</small></span></span>
        <Dialog.Close className="tg-cw__btn" aria-label="Đóng cuộc trò chuyện" title="Đóng"><Icon name="x" size={17} /></Dialog.Close>
      </header>
      <div className="tg-cw__msgs" aria-live="polite">
        {msgs === null ? <p className="tg-hd__empty">Đang tải tin nhắn…</p> : msgs.length === 0 ? (
          <div className="tg-cw__hello"><Avatar p={live} size={64} /><strong>{live.name}</strong><p>Chưa có tin nhắn. Gửi lời chào hoặc một lịch trình nhé.</p></div>
        ) : msgs.map((m, i) => {
          const prev = msgs[i - 1]
          const next = msgs[i + 1]
          const gap = !prev || +new Date(m.at) - +new Date(prev.at) > GAP
          const tail = !next || next.mine !== m.mine || +new Date(next.at) - +new Date(m.at) > GAP
          return (
            <div key={m.id} className="tg-cw__row">
              {gap && <time className="tg-cw__stamp" dateTime={m.at}>{stamp(m.at)}</time>}
              <div className={`tg-cw__msg ${m.mine ? 'is-mine' : ''}`}>
                {!m.mine && (tail ? <Avatar p={live} size={26} /> : <span className="tg-cw__gap" />)}
                {m.journey ? (
                  <div className="tg-hd__trip">
                    <span className="tg-hd__tripic"><Icon name="route" size={18} /></span>
                    <span className="tg-hd__pc"><strong>Lịch trình chuyến đi</strong><small>{m.body || 'Một chuyến Đà Lạt'}</small></span>
                    {!m.mine && (m.imported ? <span className="tg-hd__tag"><Icon name="check" size={13} /> Đã lấy về</span> : <button type="button" className="tg-hb-go" disabled={busy} onClick={() => take(m)}><Icon name="download" size={14} /> Lấy về</button>)}
                  </div>
                ) : <p className={onlyEmoji(m.body) ? 'tg-cw__big' : ''}>{m.body}</p>}
              </div>
              {m.mine && m.id === lastMine && m.read && <small className="tg-cw__seen">Đã xem</small>}
            </div>
          )
        })}
        {theyType && <div className="tg-cw__msg tg-cw__typing" role="status" aria-label={`${live.name} đang nhập`}><Avatar p={live} size={26} /><p aria-hidden="true"><i /><i /><i /></p></div>}
        <div ref={end} />
      </div>
      {picking && (
        <div className="tg-hd__pick">
          <div className="tg-hd__row"><h4>Chọn một chuyến để gửi</h4><button type="button" className="tg-hb-icon" aria-label="Đóng" onClick={() => setPicking(null)}><Icon name="x" size={14} /></button></div>
          {picking.length ? <ul>{picking.map((t) => <li key={t.id}><button type="button" disabled={busy} onClick={() => { setPicking(null); void send(`${tripTitle(t)} · ${tripLine(t)}`, t.id) }}><strong>{tripTitle(t)}</strong><small>{tripLine(t)}</small><Icon name="send" size={14} /></button></li>)}</ul> : <p className="tg-hd__empty">Bạn chưa có chuyến nào để gửi.</p>}
        </div>
      )}
      <form className="tg-cw__compose" onSubmit={(e) => { e.preventDefault(); if (text.trim()) void send(text.trim()) }}>
        <button type="button" className="tg-hb-icon" aria-label="Gửi một lịch trình" title="Gửi lịch trình" disabled={busy} onClick={() => tripSummaries().then((l) => setPicking(l.filter((t) => t.stage !== 'trip')), () => toast('Chưa tải được danh sách chuyến'))}><Icon name="route" size={18} /></button>
        <span className="tg-cw__input">
          <input ref={box} value={text} maxLength={2000} placeholder="Aa" onChange={(e) => typed(e.target.value)} aria-label={`Nhắn cho ${live.name}`} />
          <EmojiPicker onPick={(e) => { setText((t) => t + e); box.current?.focus() }} />
        </span>
        {text.trim()
          ? <button type="submit" className="tg-hb-icon tg-cw__send" disabled={busy} aria-label="Gửi" title="Gửi"><Icon name="send" size={18} /></button>
          : <button type="button" className="tg-hb-icon tg-hd__like" disabled={busy} aria-label="Gửi biểu tượng thích" title="Thích" onClick={() => void send(LIKE)}>{LIKE}</button>}
      </form>
    </section>
  )
}

function ShareBody({ trip }: { trip: TripSummary }) {
  const f = useFriends(true)
  const [busy, setBusy] = useState(false)
  const give = (p: Person) => {
    setBusy(true)
    sendMessage(p.id, `${tripTitle(trip)} · ${tripLine(trip)}`, trip.id).then(() => { toast(`Đã gửi lịch trình cho ${p.name}`); close() }, (e) => toast(say(e))).finally(() => setBusy(false))
  }
  return (
    <div className="tg-hd__body">
      <div className="tg-hd__ticket"><b>{tripTitle(trip)}</b> · {tripLine(trip)}<br />Bạn bè nhận được bản sao để tự sửa; chuyến của bạn giữ nguyên.</div>
      {!f ? <p className="tg-hd__empty">Đang tải bạn bè…</p> : f.friends.length ? (
        <ul className="tg-hd__people">{f.friends.map((p) => <PersonRow key={p.id} p={p}><button type="button" className="tg-hb-go" disabled={busy} onClick={() => give(p)}><Icon name="send" size={14} /> Gửi</button></PersonRow>)}</ul>
      ) : <p className="tg-hd__empty">Chưa có bạn bè để gửi. <button type="button" className="tg-hb-link" onClick={openFriends}>Tìm bạn</button></p>}
    </div>
  )
}
