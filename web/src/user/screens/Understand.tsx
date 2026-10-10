import { useCallback, useEffect, useRef, useState } from 'react'
import { consumeStageEntry, enterStage, JourneyError, mutateJourney, resumeJourney } from '../journey'
import { signInHref } from '../account'
import { rememberTrip } from '../store'
import { STEPS, useTrip, type StepId } from '../trip'
import { fromSearchInput } from '../tu/adapter'
import { ApiError, createSession, geoSearch, getSession, lodgingSuggest, sendTurn } from '../tu/api'
import { placesDelta } from '../tu/labels'
import { themeOf } from '../tu/themes'
import type { Card, Chip, GeoHit, LodgingHit, RentalParams, SearchInput, TransitParams, TurnInput, Understanding } from '../tu/types'
import { ArtHills, Busy, Empty, go, PlacePhoto } from '../ui/common'
import { Icon, type IconName } from '../ui/icons'
import { PlaceInput, geoRow, lodgingRow } from '../ui/PlaceInput'
import { FlowBar, Page, useTitle } from '../ui/Shell'
import { PlaceSearch, TicketFull, TicketMenu, type Source, type Turn } from '../ui/Ticket'
import { RentalPick } from '../ui/RentalPick'
import { TransitPick, transitLabel } from '../ui/TransitPick'
import { GREET, TripChat, Understood, type ChatMsg, type Read } from './TripChat'

// docs/WEB.md Trang 3. The agent decides the intents, how many questions each takes and their order;
// this page only shows the turn being asked and what has already happened. Never a fraction, never what comes next.
// The opening question is a conversation (TripChat); the deck of short questions starts once the user agrees.
// Nothing already passed stays on screen: no history list, no ticket while a question is open. When the questions are
// all answered the page shows one summary of what was understood.

const KEY = 'tg.tu.v1'
const HIST = (sid: string) => `tg.tu.hist.${sid}`

const store = {
  get(k: string) {
    try { return localStorage.getItem(k) } catch { return null }
  },
  set(k: string, v: string | null) {
    try { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v) } catch { /* the session lasts until reload */ }
  },
}

const QID_INTENT: Record<string, string> = {
  frame: 'Chuyến đi', days: 'Số ngày', nights: 'Số đêm', dates: 'Ngày đi', mobility: 'Đi lại', base: 'Chỗ ở', times: 'Giờ đến, giờ đi',
  entry_exit: 'Giờ đến, giờ đi', purpose: 'Mục đích', ready: 'Sẵn sàng', show_first: 'Sẵn sàng',
  origin: 'Xuất phát', arrival_mode: 'Phương tiện', inbound: 'Chuyến đi', outbound: 'Chuyến về', lodging_booked: 'Chỗ ở',
  companions: 'Đi với ai', vibe: 'Gu chuyến đi', crowd: 'Độ đông', pace: 'Nhịp độ', max_leg: 'Đường đi', budget: 'Ngân sách',
  novelty: 'Mới hay quen', review: 'Xem lại',
}
const GROUP_INTENT: Record<string, string> = {
  A: 'Chuyến đi', B: 'Đi với ai', C: 'Điều cần lưu ý', D: 'Ngân sách', E: 'Nơi muốn đến', F: 'Nhịp độ', G: 'Gu chuyến đi', H: 'Mới hay quen', I: 'Làm rõ',
}
const GROUP_ICON: Record<string, IconName> = { A: 'calendar', B: 'users', C: 'shield', D: 'bolt', E: 'pin', F: 'walk', G: 'heart', H: 'compass', I: 'info' }
// A card that asks something. The agent's own questions (ask:…) come only right after the user tells the trip and are
// answered in the chat; every other one is a chip card of the quiz, dealt as a flashcard.
const asks = (c: Card | null): c is Card => !!c && c.qid !== 'frame' && c.qid !== 'conversation'
const intentOf = (c: Card) => QID_INTENT[c.qid] ?? GROUP_INTENT[c.group] ?? 'Câu hỏi'
const QID_ICON: Record<string, IconName> = {
  dates: 'calendar', days: 'calendar', nights: 'bed', mobility: 'bike', base: 'bed', lodging_booked: 'bed', ready: 'sparkle', show_first: 'sparkle', origin: 'home', arrival_mode: 'route',
}
const iconOf = (c: Card): IconName => (c.input === 'transit' ? ((c.params as TransitParams | undefined)?.mode === 'bus' ? 'bus' : 'plane') : QID_ICON[c.qid] ?? GROUP_ICON[c.group] ?? 'sparkle')

// Flatten the understanding so two snapshots can be compared target by target.
function flat(u: Understanding | null): Record<string, string> {
  if (!u) return {}
  const out: Record<string, string> = {}
  const put = (r: { target: string } | null) => r && (out[r.target] = JSON.stringify(r))
  ;[u.purpose, u.pace, u.max_leg_min, u.crowd_tolerance, u.novelty, u.budget_vnd, ...u.trip, ...u.anchors, ...u.hard, ...u.soft].forEach(put)
  return out
}
const DROP_MS = 380
const still = () => matchMedia('(prefers-reduced-motion: reduce)').matches
const changed = (a: Understanding | null, b: Understanding) => {
  const x = flat(a)
  const y = flat(b)
  return Object.keys(y).filter((k) => x[k] !== y[k])
}

export function Understand() {
  useTitle('Tìm hiểu')
  const { trip, dispatch } = useTrip()
  const [sid, setSid] = useState<string | null>(null)
  const [card, setCard] = useState<Card | null>(null)
  const [u, setU] = useState<Understanding | null>(null)
  const [hist, setHist] = useState<Turn[]>([])
  const [said, setSaid] = useState<Record<string, string>>({})
  const [remark, setRemark] = useState('')
  const [busy, setBusy] = useState(false)
  const [handing, setHanding] = useState(false)
  const [preview, setPreview] = useState<Set<string>>(new Set())
  const [offline, setOffline] = useState(false)
  const [guestFull, setGuestFull] = useState(false) // a guest already has its one trip
  const [notice, setNotice] = useState<string | null>(null)
  const [full, setFull] = useState(false)
  const [focus, setFocus] = useState<string | null>(null)
  // Key of the card being dropped while its answer is sent.
  const [leaving, setLeaving] = useState<string | null>(null)
  const [seq, setSeq] = useState(0)
  // The opening conversation. What the user wrote on the landing page is already their first message.
  const [chat, setChat] = useState(() => !trip.journeyId && !!trip.startText)
  const [msgs, setMsgs] = useState<ChatMsg[]>(() => (!trip.journeyId && trip.startText ? [{ who: 'ai', text: GREET }, { who: 'me', text: trip.startText }] : []))
  const [reads, setReads] = useState<Read[]>([])
  // How the last answer moved the "Hợp gu bạn" count.
  const lastMatch = useRef<number | null>(null)
  const [moves, setMoves] = useState<{ key: number; delta: number }[]>([])
  useEffect(() => {
    if (u?.matching === undefined) return
    const before = lastMatch.current
    lastMatch.current = u.matching
    if (before === null || before === u.matching) return
    setMoves([{ key: Date.now(), delta: u.matching - before }])
  }, [u?.matching])
  const shownMatch = useTween(u?.matching ?? 0)
  const [quotes, setQuotes] = useState<Record<string, string>>({})
  const uRef = useRef<Understanding | null>(null)
  const cardRef = useRef<Card | null>(null)
  const sayRef = useRef('')
  const gotRef = useRef<Card | null | undefined>(undefined) // the card the last turn ended with (undefined: none came)
  // Once a quiz card has been dealt, the end of the questions is the summary, not the conversation again —
  // except the review, which is chatted: after the last box the conversation comes back so the user can keep
  // telling while the summary and "Bắt đầu tìm" stay in view.
  const quizzed = useRef(false)
  // Paused mid-quiz to chat (the "Thoát" button): progress stays server-side, the chat owns the screen until a quiz
  // card comes back. Mirrored in a ref because the card effect reads it.
  const [paused, setPausedState] = useState(false)
  const pausedRef = useRef(false)
  const setPaused = (v: boolean) => { pausedRef.current = v; setPausedState(v) }
  useEffect(() => {
    const qid = card?.qid
    if (!asks(card)) {
      // A conversation card after the quiz is transient: the agent's turn ends on it before the review card follows
      // in the same breath. Keep the chat instead of flashing the deck.
      if (qid === 'conversation' && quizzed.current) return
      if (pausedRef.current) return // paused chat owns the screen until a quiz card returns
      return setChat(!quizzed.current) // nothing is being asked: the summary after a quiz, else the conversation
    }
    if (card.qid === 'review') { quizzed.current = true; setPaused(false); setChat(true); return }
    if (!card.qid.startsWith('ask:')) { quizzed.current = true; setPaused(false); setChat(false); setFull(false) } // a quiz card: the flashcard deck, no ticket
  }, [card?.qid])
  const dropUntil = useRef(0)
  const mounted = useRef(true)
  uRef.current = u
  cardRef.current = card
  // A new card waits for the answered one to finish falling.
  const deliver = (fn: () => void) => {
    const wait = dropUntil.current - Date.now()
    if (wait > 0) window.setTimeout(fn, wait)
    else fn()
  }

  // Where the hand-off lands: Lựa chọn, or the step the user jumped to from the step bar.
  const ahead = useRef('/explore')
  const handOff = useCallback((si: SearchInput, jid: string) => {
    dispatch({ type: 'set', patch: { ...fromSearchInput(si), journeyId: jid, decisionId: jid, planningId: null } })
    store.set(KEY, null)
    go(ahead.current)
  }, [dispatch])

  const open = useCallback(
    async (fresh: boolean, alive: () => boolean = () => mounted.current) => {
      try {
        const origin = location.pathname + location.search
        const old = fresh ? null : trip.journeyId ?? store.get(KEY)
        const explicitBack = old ? consumeStageEntry(old) === 'trip' : false
        const recovery = old
          ? await resumeJourney(old).catch((e) => {
              if (e instanceof ApiError && e.status === 404) return null
              throw e
            })
          : null
        if (!mounted.current || origin !== location.pathname + location.search) return null
        if (explicitBack && recovery) {
          recovery.view = await enterStage(recovery.view.id, 'trip')
          if (!mounted.current || origin !== location.pathname + location.search) return null
        }
        if (recovery?.view.stage === 'trip' && recovery.view.outputs.trip) {
          setHanding(true)
          const j = await mutateJourney(recovery.view.id, 'trip', 'advance')
          if (!mounted.current || origin !== location.pathname + location.search) return null
          handOff(recovery.view.outputs.trip as SearchInput, j.id)
          return null
        }
        if (recovery && recovery.view.stage !== 'trip') {
          const j = recovery.view
          dispatch({ type: 'set', patch: { journeyId: j.id, decisionId: j.id, planningId: j.stage === 'planning' ? j.id : null } })
          go(j.stage === 'planning' ? '/plan' : '/explore')
          return null
        }
        const resumed = recovery ? await getSession(recovery.view.id) : null
        if (!mounted.current || origin !== location.pathname + location.search) return null
        const v = resumed ?? (await createSession(trip.experience, trip.startWith))
        if (!alive() || origin !== location.pathname + location.search) return null
        store.set(KEY, v.id)
        rememberTrip(v.id)
        setSid(v.id)
        dispatch({ type: 'set', patch: { journeyId: v.id, decisionId: null, planningId: null } })
        let saved: Turn[] = []
        try {
          saved = resumed ? JSON.parse(store.get(HIST(v.id)) ?? '[]') : []
        } catch { /* start the history again */ }
        setCard(v.card)
        setU(v.understanding)
        setHist(saved)
        // The chat is one continuous thread: quiz answers and skips rejoin it, so the conversation reads whole
        // after a reload too (empty card texts, like the free conversation card, stay out).
        setChat(true)
        const before: ChatMsg[] = (resumed ? v.transcript : []).filter((t) => t.turn > 0 && t.text).map((t) => ({ who: t.role === 'user' ? 'me' : 'ai', text: t.text }))
        setMsgs((m) => (m.length ? m : [{ who: 'ai', text: GREET }, ...before]))
        return v.id
      } catch (e) {
        if (e instanceof JourneyError && e.detail === 'guest_limit') setGuestFull(true)
        else setOffline(true)
        return null
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [trip.experience, trip.startWith, trip.journeyId],
  )

  const send = useCallback(
    async (input: TurnInput, turn?: Omit<Turn, 'targets'>, id = sid): Promise<string> => {
      if (!id) return ''
      setBusy(true)
      setNotice(null)
      setRemark('')
      setReads([])
      sayRef.current = ''
      gotRef.current = undefined
      // The answered turn joins the history at once, so the next card already counts it.
      if (turn) setHist((h) => [...h, { ...turn, targets: [] }])
      const origin = location.pathname + location.search
      const before = uRef.current
      let touched: string[] = []
      let compiled: SearchInput | null = null
      try {
        await sendTurn(id, input, {
          preview: (p) => {
            setPreview(new Set(p.fields.map((f) => f.target)))
            const got = p.fields.filter((f) => f.quote)
            if (!got.length) return
            // one line per word read: several tastes share the target "soft"
            setReads((r) => [...r.filter((x) => !got.some((f) => f.target === x.target)), ...got.filter((f, i) => got.findIndex((g) => g.target === f.target && g.quote === f.quote) === i).map((f) => ({ target: f.target, quote: f.quote }))])
            setQuotes((q) => ({ ...q, ...Object.fromEntries(got.map((f) => [f.target, f.quote])) }))
          },
          say: (d) => {
            sayRef.current = d.replace !== undefined ? d.replace : sayRef.current + (d.delta ?? '')
            setRemark(sayRef.current)
          },
          state: (s) => {
            touched = changed(before, s.understanding)
            setU(s.understanding)
            setPreview(new Set())
          },
          card: (c) => (gotRef.current = c, deliver(() => {
            const was = cardRef.current
            if (c?.qid !== was?.qid || c?.text !== was?.text) setSeq((n) => n + 1)
            setCard(c)
            setLeaving(null)
          })),
          done: (d) => { compiled = d.search_input },
          error: (e) => setNotice(e.message),
        })
        if (compiled && mounted.current && origin === location.pathname + location.search) {
          setHanding(true)
          const r = await mutateJourney(id, 'trip', 'advance')
          if (!mounted.current || origin !== location.pathname + location.search) return ''
          handOff(compiled, r.id)
        }
        if (turn) {
          setHist((h) => {
            const next = h.map((t) => (t.n === turn.n ? { ...t, targets: touched } : t))
            store.set(HIST(id), JSON.stringify(next))
            return next
          })
        } else if (touched.length) {
          const from = input.kind === 'edit' ? 'bạn sửa trực tiếp' : 'từ lời bạn kể'
          setSaid((s) => ({ ...s, ...Object.fromEntries(touched.map((t) => [t, from])) }))
        }
      } catch (e) {
        if (turn) setHist((h) => h.filter((t) => t.n !== turn.n))
        setHanding(false)
        if (e instanceof ApiError && e.status === 404) {
          store.set(KEY, null)
          setNotice('Phiên này đã hết. Bấm “Đặt lại toàn bộ” trong vé để bắt đầu lại.')
        } else setOffline(true)
      } finally {
        setBusy(false)
        setPreview(new Set())
        // No new card came back (an error, or the same question): the dropped card is dealt again.
        deliver(() => setLeaving(null))
      }
      return sayRef.current
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sid, handOff],
  )

  // Opens once per mount. What the user typed on Khám phá becomes the first turn.
  useEffect(() => {
    mounted.current = true
    let alive = true
    ;(async () => {
      const id = await open(!trip.journeyId && !!(trip.startText || trip.startWith), () => alive)
      if (alive && id && trip.startText) {
        const text = trip.startText
        dispatch({ type: 'set', patch: { startText: null } })
        const theme = themeOf(text) // a theme card of Khám phá: its fixed tastes, no sentence to read
        if (theme) await reply(send({ kind: 'theme', value: theme.id }, undefined, id))
        else await tell(text, id, true)
      }
    })()
    return () => {
      alive = false
      mounted.current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // The chat is the main surface. The agent's own questions (qid ask:…) are answered in it; the quiz cards are a
  // deck. When nothing is being asked, the chat comes back before any quiz and the summary after one — and the
  // review after the last box is chatted too, so the user can keep telling instead of staring at a flashcard.
  const questioning = asks(card)
  const talk = chat || paused || (!questioning && !quizzed.current)
  const summary = !talk && !questioning
  const cardKey = card ? `${card.qid}:${seq}` : 'none'
  // A long conversation leaves the page scrolled down: bring each newly dealt card's top back into view.
  const deck = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = deck.current
    if (talk || !el || el.getBoundingClientRect().top >= 80) return
    el.scrollIntoView({ block: 'start', behavior: still() ? 'auto' : 'smooth' })
  }, [cardKey, talk])
  // The answered card drops away at once while the answer is sent; the next one is dealt from behind when it arrives.
  const drop = (key: string) => {
    if (still()) return
    dropUntil.current = Date.now() + DROP_MS
    setLeaving(key)
  }
  // The agent's reply joins the conversation when the turn ends (nothing when it said nothing: the summary follows).
  const reply = async (said: Promise<string>) => {
    const r = await said
    if (mounted.current && r) setMsgs((m) => [...m, { who: 'ai', text: r }])
  }
  // An answer to the open question. One continuous thread: the question and the answer join the conversation at
  // once, whether asked in the chat or on a quiz flashcard (a quiz card is not kept anywhere else on screen once
  // answered; the ticket's provenance still counts it: hist).
  const answer = (chips: string[], value?: string | null, label?: string) => {
    if (!card || busy || leaving) return
    const names = card.chips.filter((c) => chips.includes(c.id)).map((c) => c.label)
    const text = label ?? (chips.includes('skip') ? 'Bỏ qua' : chips.includes('unsure') ? 'Chưa chắc' : [...names, value ?? ''].filter(Boolean).join(', '))
    if (!talk) drop(cardKey)
    setMsgs((m) => [...m, { who: 'ai', text: card.text }, { who: 'me', text }])
    const sent = send({ kind: 'answer', qid: card.qid, chips, value: value ?? null }, { n: hist.length + 1, intent: intentOf(card), text: card.text, answer: text })
    reply(sent)
  }
  const typed = (text: string) => {
    if (busy || leaving) return
    drop(cardKey)
    tell(text)
  }
  // One typed message. When it answers the open question (the agent closes it), that question joins the
  // conversation just before the message.
  const tell = async (text: string, id = sid, echoed = false, shown?: ChatMsg) => {
    const open = asks(cardRef.current) ? cardRef.current : null
    const me = shown ?? { who: 'me' as const, text }
    if (!echoed) setMsgs((m) => [...m, me])
    const r = await send({ kind: 'text', text }, undefined, id)
    if (!mounted.current) return
    const closed = open && gotRef.current !== undefined && gotRef.current?.qid !== open.qid
    setMsgs((m) => {
      const i = closed ? m.indexOf(me) : -1
      const out = i >= 0 ? [...m.slice(0, i), { who: 'ai' as const, text: open!.text }, ...m.slice(i)] : m
      return r ? [...out, { who: 'ai' as const, text: r }] : out
    })
  }
  const edit = (target: string, value: string | null) => send({ kind: 'edit', target, value })
  const show = () => send({ kind: 'show' })
  const more = () => { setPaused(false); send({ kind: 'more' }) } // leave the agent's own question, go on with the quiz cards (resumes a paused quiz where it left off)
  const requiz = () => send({ kind: 'requiz' }) // "Làm lại trắc nghiệm": the answered cards come back
  const pause = () => { if (busy || leaving || !card) return; setPaused(true); setChat(true); send({ kind: 'pause' }) } // "Thoát" mid-quiz: chat on, progress kept server-side
  // A later step chosen on the step bar before the questions are done: search with what is known so far. Chosen while
  // a turn is running, it goes as soon as that turn ends.
  const [jumping, setJumping] = useState(false)
  const jump = (target: StepId) => {
    if (!sid) return
    ahead.current = target === 'explore' ? '/explore' : STEPS.find((x) => x.id === target)?.path ?? '/explore'
    setJumping(true)
  }
  useEffect(() => {
    if (!jumping || busy || leaving) return
    setJumping(false)
    show()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jumping, busy, leaving])
  const reset = async () => {
    if (!confirm('Đặt lại toàn bộ những gì mình đã hiểu về chuyến này?')) return
    if (sid) store.set(HIST(sid), null)
    setFull(false)
    setSaid({})
    quizzed.current = false
    setPaused(false)
    setMsgs([])
    setQuotes({})
    await open(true)
  }
  const openRow = (target: string | null) => {
    setFocus(target)
    setFull(true)
  }

  if (guestFull)
    return (
      <>
        <FlowBar step="understand" />
        <Page narrow><Empty art={<ArtHills />} title="Bản dùng thử chỉ có 1 chuyến" body="Bạn đã dùng chuyến thử của hôm nay. Đăng nhập để tạo thêm chuyến và giữ lại lịch sử." action={<a className="tg-btn tg-btn--primary" href={signInHref('/app/understand')}>Đăng nhập với Google</a>} /></Page>
      </>
    )
  if (offline)
    return (
      <>
        <FlowBar step="understand" />
        <Page narrow><Empty art={<ArtHills />} title="Chưa kết nối được trợ lý" body="Máy chủ hành trình chưa trả lời. Thử lại sau ít phút; những gì bạn đã trả lời vẫn còn." action={<button type="button" className="tg-btn tg-btn--primary" onClick={() => location.reload()}><Icon name="refresh" size={18} /> Thử lại</button>} /></Page>
      </>
    )
  if (handing || (!talk && (!u || !sid)))
    return (
      <>
        <FlowBar step="understand" />
        <Page><Busy text={handing ? 'Mình đủ hiểu rồi, đang chuẩn bị gợi ý cho chuyến của bạn…' : 'Đang mở cuộc hỏi…'} /></Page>
      </>
    )

  const intent = card && !talk ? intentOf(card) : null
  const source = (target: string, mark?: boolean): Source => {
    const turns = hist.filter((t) => t.targets.includes(target))
    if (turns.length > 1) return { text: `kết luận từ ${turns.length} câu hỏi`, turns }
    if (turns.length === 1) return { text: `bạn trả lời ở câu ${turns[0].n}`, turns }
    if (said[target]) return { text: said[target], turns: [] }
    return { text: mark ? 'mình suy ra, sửa được' : 'bạn nói', turns: [] }
  }
  const ticket = u && { u, intent, busy, preview, source, onEdit: edit, onShow: show }
  const waiting = !talk && !!leaving && leaving === cardKey

  return (
    <>
      <FlowBar step="understand" onAhead={jump} aside={ticket && !questioning ? <TicketMenu {...ticket} onOpen={openRow} /> : undefined} />
      <Page className="tg-und">
        <div className="tg-und__grid has-sides">
          <nav className="tg-qrail" aria-label="Những điều mình đã hiểu">
            <h2 className="tg-side__h">Mình đang hiểu</h2>
            <ol>
              {talk && <li className="is-now" aria-current="step"><div><i aria-hidden="true" /><span><small>Trò chuyện</small><b>bạn kể, mình ghi</b></span></div></li>}
              {intent && <li className="is-now" aria-current="step"><div><i aria-hidden="true" /><span><small>{intent}</small><b>đang hỏi</b></span></div></li>}
              {summary && <li className="is-now" aria-current="step"><div><i aria-hidden="true" /><span><small>Tóm tắt</small><b>xem lại, sửa được</b></span></div></li>}
            </ol>
          </nav>

          <section className="tg-ask" aria-live="polite">
            {notice && <p className="tg-alert" role="alert"><Icon name="warn" size={16} /> {notice}</p>}
            {summary && u ? (
              <div className="tg-ask__done tg-stage">
                <span className="tg-chip tg-chip--soft"><Icon name="check" size={14} /> ĐÃ HỎI XONG</span>
                <h1>Mình hiểu chuyến của bạn như này.</h1>
                <div className="tg-ask__sum"><Understood bare u={u} card={card} quotes={quotes} preview={preview} onOpen={openRow} onEdit={edit} /></div>
                {(remark || busy) && <p className="tg-ask__say">{remark || 'Mình đang ghi lại…'}</p>}
                <div className="tg-ask__ctas">
                  <button type="button" className="tg-btn tg-btn--primary" disabled={busy} onClick={show}>Bắt đầu tìm <Icon name="arrow" size={18} /></button>
                  <button type="button" className="tg-btn tg-btn--ghost" onClick={() => setChat(true)}>Kể thêm hoặc sửa</button>
                  <button type="button" className="tg-btn tg-btn--ghost" onClick={() => openRow(null)}>Xem đầy đủ</button>
                </div>
              </div>
            ) : (
              <div ref={deck} className={`tg-deck ${waiting ? 'is-waiting' : ''} ${talk ? 'is-chat' : ''}`}>
                <i className="tg-deck__ghost tg-deck__ghost--1" aria-hidden="true" />
                <i className="tg-deck__ghost tg-deck__ghost--2" aria-hidden="true" />
                {waiting && (
                  <div className="tg-deck__wait" role="status">
                    <span className="tg-dots" aria-hidden="true"><i /><i /><i /></span>
                    <p>{remark || 'Mình đang ghi lại câu trả lời…'}</p>
                  </div>
                )}
                {talk ? (
                  <TripChat key="chat" msgs={msgs.length ? msgs : [{ who: 'ai', text: GREET }]} ready={!!sid} busy={busy || jumping} live={remark} reads={reads} quotes={quotes} u={u} card={card} preview={preview} onTell={(t, shown) => tell(t, sid, false, shown)} onOpen={openRow} onEdit={edit} onGo={show} onMore={more} onRequiz={requiz} onResume={more} paused={paused} onAnswer={answer} />
                ) : card && u && (
                  <div className={`tg-stage tg-ask__card ${leaving === cardKey ? 'is-leaving' : ''}`} key={cardKey} aria-busy={busy || !!leaving}>
                    <div className="tg-ask__top">
                      <span className="tg-ask__ico" aria-hidden="true"><Icon name={iconOf(card)} size={18} /></span>
                      <span className="tg-ask__intent"><b>{intent?.toUpperCase()}</b></span>
                      {card && !card.qid.startsWith('ask:') && card.qid !== 'review' && <button type="button" className="tg-btn tg-btn--ghost tg-btn--sm" disabled={busy} title="Tạm nghỉ trắc nghiệm, về trò chuyện (giữ nguyên đã trả lời)" onClick={pause}>Tạm nghỉ</button>}
                      {card.exits && <button type="button" className="tg-ask__skip" disabled={busy} onClick={() => answer(['skip'])}>Bỏ qua</button>}
                    </div>
                    <Question card={card} busy={busy} onAnswer={answer} onText={typed} u={u} />
                    <div className="tg-ask__note">
                      {busy && !leaving && <p className="tg-ask__say">{remark || 'Mình đang ghi lại…'}</p>}
                      {!busy && remark && <p className="tg-ask__say">{remark}</p>}
                      {card.reason && <p className="tg-ask__why"><Icon name="info" size={13} /> {card.reason}</p>}
                      <p className="tg-faint">Mình hỏi tiếp tuỳ câu trả lời của bạn.</p>
                    </div>
                  </div>
                )}
              </div>
            )}
            <div className="tg-ask__space" />
          </section>

          <aside className="tg-match" aria-label="Nơi đang hợp với bạn">
            {u && (
              <>
                <h2 className="tg-side__h">Hợp gu bạn</h2>
                <p className="tg-match__n"><b className="tg-mono">{shownMatch.toLocaleString('vi-VN')}</b> nơi{moves[0] && moves[0].delta > 0 && <span key={moves[0].key} className={`tg-match__delta tg-mono ${moves[0].delta < 0 ? 'is-down' : 'is-up'}`}>{placesDelta(moves[0].delta)}</span>}</p>
                <span className="tg-ask__meter tg-match__meter" aria-hidden="true"><i style={{ width: `${Math.max(2, (u.matching / Math.max(1, u.total)) * 100)}%` }} /></span>
                <p className="tg-faint tg-match__of">nơi hợp gu bạn, trong {u.total.toLocaleString('vi-VN')} nơi ở Đà Lạt mình có dữ liệu. Trả lời thêm thì danh sách sát hơn; bước Lựa chọn xếp hợp nhất lên đầu.</p>
                <div className="tg-match__go">
                  <button type="button" className={`tg-btn ${talk ? 'tg-btn--ghost' : 'tg-btn--primary'}`} disabled={busy || !!leaving || jumping} onClick={show}>Xem gợi ý <Icon name="arrow" size={18} /></button>
                  {!u.ready && <p className="tg-faint">Chưa biết {u.missing.map((m) => m.label).join(', ')}; vẫn xem được, biết thêm thì gợi ý sát hơn.</p>}
                </div>
                {u.anchors.some((a) => a.place_id) && (
                  <ul className="tg-match__list">
                    {u.anchors.filter((a) => a.place_id).map((a) => (
                      <li key={a.target}><PlacePhoto id={a.place_id!} className="tg-match__ph" /><span><b>{a.name}</b><small>{a.priority === 'must' ? 'nhất định đến' : 'muốn đến'}</small></span></li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </aside>
        </div>
      </Page>
      {ticket && <TicketFull {...ticket} open={full} onClose={() => setFull(false)} focus={focus} onFocus={setFocus} onReset={reset} />}
    </>
  )
}

function Question({ card, busy, u, onAnswer, onText }: { card: Card; busy: boolean; u: Understanding; onAnswer: (chips: string[], value?: string | null, label?: string) => void; onText: (text: string) => void }) {
  const [picked, setPicked] = useState<string[]>([])
  const [date, setDate] = useState('')
  const [text, setText] = useState('')
  const [flashBox, setFlashBox] = useState(false) // "Khác, tự gõ" was tapped: show where the answer goes
  const box = useRef<HTMLTextAreaElement>(null)
  const instant = !card.multi && card.input !== 'date'
  const rows: { row: string | null; chips: Chip[] }[] = []
  for (const c of card.chips) {
    const r = rows.find((x) => x.row === c.row)
    if (r) r.chips.push(c)
    else rows.push({ row: c.row, chips: [c] })
  }
  const asCards = rows.length === 1 && !rows[0].row && card.chips.length <= 6 && card.input !== 'lodging'
  // The search box / trip list is the answer; a typed sentence would not pick a point or a trip.
  const logistics = card.input === 'geo' || (card.input === 'transit' && !!card.params) || card.input === 'lodging' // a transit card without its route falls back to typing
  // How many may be picked, said before the user taps: one (sent at once), one per row, or several (then "Xong").
  const many = (row: string | null) => card.multi && !card.single_rows.includes(row ?? '')
  const how = !card.chips.length || logistics ? null
    : !card.multi ? 'Chọn một ý'
    : rows.every((r) => !many(r.row)) ? 'Mỗi dòng chọn một ý, xong bấm “Xong câu này”'
    : 'Chọn một hoặc nhiều ý, xong bấm “Xong câu này”'
  const toggle = (c: Chip) => {
    if (busy) return
    if (c.id === 'other') { // "Khác, tự gõ": the answer is typed below — focus the box and flash it so the tap is seen
      box.current?.focus({ preventScroll: true })
      box.current?.scrollIntoView({ block: 'nearest', behavior: still() ? 'auto' : 'smooth' })
      setFlashBox(true)
      window.setTimeout(() => setFlashBox(false), 1200)
      return
    }
    if (instant) return onAnswer([c.id])
    setPicked((p) => {
      if (p.includes(c.id)) return p.filter((x) => x !== c.id)
      const single = !card.multi || card.single_rows.includes(c.row ?? '')
      const rest = single ? p.filter((id) => card.chips.find((x) => x.id === id)?.row !== c.row) : p
      return [...rest, c.id]
    })
  }
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (busy || t.closest('input, textarea') || e.metaKey || e.ctrlKey || e.altKey) return
      const k = Number(e.key)
      if (k >= 1 && k <= card.chips.length) toggle(card.chips[k - 1])
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  })
  const submit = () => {
    const t = text.trim()
    if (!t || busy) return
    onText(t)
    setText('')
  }
  // A long question keeps its first sentence as the headline; the rest reads as a normal line.
  const cut = card.text.length > 70 ? card.text.search(/[.:?!]\s/) : -1
  const head = cut > 0 ? card.text.slice(0, cut + 1).replace(/:$/, '?') : card.text
  const rest = cut > 0 ? card.text.slice(cut + 2) : ''
  let k = 0
  return (
    <>
      <h1 className="tg-ask__q">{head}</h1>
      {rest && <p className="tg-ask__more">{rest}</p>}
      <div className="tg-ask__panel">
        {card.input === 'rental' && card.params && <RentalPick params={card.params as RentalParams} />}
        {how && <p className="tg-ask__how"><Icon name={card.multi ? 'check' : 'arrow'} size={13} /> {how}</p>}
        {asCards ? (
          <div className="tg-opts" role="group" aria-label="Lựa chọn">
            {card.chips.map((c) => {
              k += 1
              const on = picked.includes(c.id)
              return <button key={c.id} type="button" className={`tg-opt ${on ? 'is-on' : ''}`} aria-pressed={card.multi ? on : undefined} disabled={busy} onClick={() => toggle(c)}><span className="tg-opt__head"><i className={`tg-opt__mark ${card.multi ? 'is-box' : 'is-dot'}`} aria-hidden="true">{on && <Icon name="check" size={12} />}</i><b>{c.label}</b></span>{c.effect ? <Effect n={c.effect} base={u.matching} /> : null}{k <= 9 && <kbd aria-hidden="true">{k}</kbd>}</button>
            })}
            {card.exits && !logistics && <button type="button" className="tg-opt is-soft" disabled={busy} onClick={() => onAnswer(['unsure'])}><b>Chưa chắc</b></button>}
          </div>
        ) : card.chips.length > 0 && card.input !== 'lodging' && (
          <div className="tg-basics">
            {rows.map((r) => (
              <div className="tg-basics__row" key={r.row ?? '_'}>
                {r.row && <h3>{r.row}{card.multi && <small>{many(r.row) ? 'chọn nhiều' : 'chọn một'}</small>}</h3>}
                <div className="tg-basics__chips" role="group" aria-label={r.row ?? 'Lựa chọn'}>
                  {r.chips.map((c) => <button key={c.id} type="button" className={`tg-chip ${card.multi ? (many(r.row) ? 'is-box' : 'is-dot') : ''}`} aria-pressed={card.multi ? picked.includes(c.id) : undefined} disabled={busy} onClick={() => toggle(c)}>{card.multi && <i className="tg-chip__mark" aria-hidden="true">{picked.includes(c.id) && <Icon name="check" size={11} />}</i>}{c.label}{c.effect ? <Effect n={c.effect} base={u.matching} /> : null}</button>)}
                </div>
              </div>
            ))}
            {card.exits && <button type="button" className="tg-chip tg-chip--dash" disabled={busy} onClick={() => onAnswer(['unsure'])}>Chưa chắc</button>}
          </div>
        )}
        {card.input === 'date' && <label className="tg-ask__date"><span>Ngày khởi hành</span><input className="tg-input" type="date" min={new Date().toLocaleDateString('sv-SE')} value={date} onChange={(e) => setDate(e.target.value)} /></label>}
        {card.input === 'date' && card.exits && <button type="button" className="tg-chip tg-chip--dash" disabled={busy} onClick={() => onAnswer(['unsure'])}>Chưa chắc ngày</button>}
        {card.input === 'place' && <PlaceSearch placeholder="Tìm một nơi gần chỗ ở" onPick={(p) => onAnswer([], p.id, p.name)} />}
        {card.input === 'geo' && (
          <div className="tg-ask__find">
            <PlaceInput<GeoHit> label="Nơi bạn khởi hành" placeholder="Thành phố, quận hoặc địa chỉ" icon="home" autoFocus disabled={busy} fetcher={geoSearch} row={geoRow}
              onPick={(g) => onAnswer([], JSON.stringify({ text: g.text, lat: g.lat, lng: g.lng, province: g.province }), g.text)} />
            {card.exits && <button type="button" className="tg-chip tg-chip--dash" disabled={busy} onClick={() => onAnswer(['skip'])}>Bỏ qua</button>}
          </div>
        )}
        {card.input === 'lodging' && (
          <div className="tg-ask__find">
            <PlaceInput<LodgingHit> label="Nơi bạn lưu trú" placeholder="Tên khách sạn, homestay hoặc địa chỉ" icon="bed" autoFocus disabled={busy} fetcher={lodgingSuggest} row={lodgingRow}
              onPick={(h) => onAnswer([], JSON.stringify({ kind: h.kind, ...(h.id ? { id: h.id } : {}), text: h.text, lat: h.lat, lng: h.lng }), h.text)} />
            <div className="tg-basics__chips" role="group" aria-label="Chưa đặt chỗ ở">
              {card.chips.map((c) => <button key={c.id} type="button" className="tg-chip" disabled={busy} onClick={() => onAnswer([c.id])}><Icon name="sparkle" size={15} /> {c.label}</button>)}
              {card.exits && <button type="button" className="tg-chip tg-chip--dash" disabled={busy} onClick={() => onAnswer(['skip'])}>Bỏ qua</button>}
            </div>
          </div>
        )}
        {card.input === 'transit' && card.params && (
          <TransitPick params={card.params as TransitParams} way={card.qid === 'outbound' ? 'outbound' : 'inbound'} busy={busy}
            onPick={(t) => onAnswer([], JSON.stringify(t), transitLabel(t))}
            onTime={(hhmm) => onAnswer([], JSON.stringify({ time: hhmm }), hhmm)}
            onSkip={() => onAnswer(['skip'], null, 'Tôi tự lo')} />
        )}
        {(card.multi || card.input === 'date') && (
          <button type="button" className="tg-btn tg-btn--primary tg-ask__ok" disabled={busy || !(picked.length || date)} onClick={() => onAnswer(picked, date || null, date ? new Date(date + 'T00:00').toLocaleDateString('vi-VN') : undefined)}>Xong câu này</button>
        )}
        {!logistics && <label className="tg-ask__free">
          <span className="tg-sr">Hoặc gõ câu trả lời của bạn</span>
          <textarea ref={box} className={`tg-line-input${flashBox ? ' tg-flash' : ''}`} rows={card.input === 'text' ? 2 : 1} value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() } }} placeholder={card.placeholder ? `Ví dụ: ${card.placeholder}` : card.input === 'text' ? 'Ví dụ: 3 ngày cuối tuần với người yêu, đi xe máy, muốn săn mây và ngồi cà phê view đồi' : 'Đáp án khác? Gõ vào đây, ví dụ: không thích đông'} />
          <kbd>Enter</kbd>
        </label>}
        <span className="tg-ask__pill"><b className="tg-mono">{u.matching.toLocaleString('vi-VN')}</b> nơi hợp gu<span className="tg-ask__meter" aria-hidden="true"><i style={{ width: `${Math.max(2, (u.matching / Math.max(1, u.total)) * 100)}%` }} /></span></span>
      </div>
    </>
  )
}

// What the "nơi hợp gu" count would be if this chip alone were chosen. Shown as a result, not as a change: a preference
// narrows the list to what suits the trip, it does not take anything away, so no minus sign.
function Effect({ n, base }: { n: number; base: number }) {
  return <small className="tg-opt__fx tg-mono" title="Số nơi hợp gu nếu chỉ chọn ý này">≈{Math.max(0, base + n).toLocaleString('vi-VN')} nơi hợp</small>
}

// A number that runs to its new value in ~400 ms instead of jumping; reduced motion jumps.
function useTween(value: number) {
  const [shown, setShown] = useState(value)
  const from = useRef(value)
  useEffect(() => {
    const start = from.current
    from.current = value
    if (start === value || matchMedia('(prefers-reduced-motion: reduce)').matches) { setShown(value); return }
    const t0 = performance.now()
    let raf = 0
    const step = (t: number) => {
      const k = Math.min(1, (t - t0) / 400)
      setShown(Math.round(start + (value - start) * (1 - (1 - k) ** 3)))
      if (k < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [value])
  return shown
}
