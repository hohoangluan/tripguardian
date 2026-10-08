import { useCallback, useEffect, useRef, useState } from 'react'
import { consumeStageEntry, enterStage, mutateJourney, resumeJourney } from '../journey'
import { rememberTrip } from '../store'
import { STEPS, useTrip, type StepId } from '../trip'
import { fromSearchInput } from '../tu/adapter'
import { ApiError, createSession, geoSearch, getSession, lodgingSuggest, sendTurn } from '../tu/api'
import { placesDelta } from '../tu/labels'
import type { Card, Chip, GeoHit, LodgingHit, SearchInput, TurnInput, Understanding } from '../tu/types'
import { ArtHills, Busy, Empty, go, PlacePhoto } from '../ui/common'
import { Icon, type IconName } from '../ui/icons'
import { PlaceInput, type InputRow } from '../ui/PlaceInput'
import { FlowBar, Page, useTitle } from '../ui/Shell'
import { countRows, PlaceSearch, TicketFull, TicketMenu, type Source, type Turn } from '../ui/Ticket'
import { TransitPick, transitLabel } from '../ui/TransitPick'
import { GREET, TripChat, type ChatMsg, type Read } from './TripChat'

// docs/UI_SPEC_USER_WEB.md Trang 3. The agent decides the intents, how many questions each takes and their order;
// this page only shows the turn being asked and what has already happened. Never a fraction, never what comes next.
// The opening question is a conversation (TripChat); the deck of short questions starts once the user agrees.

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
  frame: 'Chuyến đi', days: 'Số ngày', dates: 'Ngày đi', mobility: 'Đi lại', base: 'Chỗ ở', times: 'Giờ đến, giờ đi',
  entry_exit: 'Giờ đến, giờ đi', purpose: 'Mục đích', ready: 'Sẵn sàng', show_first: 'Sẵn sàng',
  origin: 'Xuất phát', arrival_mode: 'Phương tiện', inbound: 'Chuyến đi', outbound: 'Chuyến về', lodging_booked: 'Chỗ ở',
}
const GROUP_INTENT: Record<string, string> = {
  A: 'Chuyến đi', B: 'Đi với ai', C: 'Điều cần lưu ý', D: 'Ngân sách', E: 'Nơi muốn đến', F: 'Nhịp độ', G: 'Gu chuyến đi', H: 'Mới hay quen', I: 'Làm rõ',
}
const GROUP_ICON: Record<string, IconName> = { A: 'calendar', B: 'users', C: 'shield', D: 'bolt', E: 'pin', F: 'walk', G: 'heart', H: 'compass', I: 'info' }
const intentOf = (c: Card) => QID_INTENT[c.qid] ?? GROUP_INTENT[c.group] ?? 'Câu hỏi'
const QID_ICON: Record<string, IconName> = {
  dates: 'calendar', days: 'calendar', mobility: 'bike', base: 'bed', lodging_booked: 'bed', ready: 'sparkle', show_first: 'sparkle', origin: 'home', arrival_mode: 'route',
}
const iconOf = (c: Card): IconName => (c.input === 'transit' ? (c.params?.mode === 'bus' ? 'bus' : 'plane') : QID_ICON[c.qid] ?? GROUP_ICON[c.group] ?? 'sparkle')
// Rows of the two type-ahead inputs (docs/plans contract: /geo, /lodging/suggest).
const geoRow = (g: GeoHit): InputRow => ({
  key: `${g.lat},${g.lng}`, icon: 'pin', name: g.text,
  sub: g.province && !g.address.includes(g.province) && g.province !== g.text ? [g.address, g.province].filter(Boolean).join(' · ') : g.address,
})
const lodgingRow = (h: LodgingHit): InputRow => ({
  key: h.id ?? `${h.lat},${h.lng}`, icon: h.kind === 'address' ? 'pin' : /homestay|villa|nhà/i.test(h.text) ? 'home' : 'bed', name: h.text, sub: h.address, rating: h.rating,
})

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
  const [notice, setNotice] = useState<string | null>(null)
  const [full, setFull] = useState(false)
  const [focus, setFocus] = useState<string | null>(null)
  // Key of the card being dropped while its answer is sent ('chat' for the conversation card).
  const [leaving, setLeaving] = useState<string | null>(null)
  const [seq, setSeq] = useState(0)
  // The opening conversation. What the user wrote on the landing page is already their first message.
  const [chat, setChat] = useState(() => !trip.journeyId && !!trip.startText)
  const [msgs, setMsgs] = useState<ChatMsg[]>(() => (!trip.journeyId && trip.startText ? [{ who: 'ai', text: GREET }, { who: 'me', text: trip.startText }] : []))
  const [reads, setReads] = useState<Read[]>([])
  // What the user did last and how it moved the "Đang hợp với bạn" count: the newest few, newest first.
  const lastAct = useRef('')
  const lastMatch = useRef<number | null>(null)
  const [moves, setMoves] = useState<{ key: number; label: string; delta: number }[]>([])
  useEffect(() => {
    if (u?.matching === undefined) return
    const before = lastMatch.current
    lastMatch.current = u.matching
    if (before === null || before === u.matching) return
    setMoves((m) => [{ key: Date.now(), label: lastAct.current || 'Cập nhật', delta: u.matching - before }, ...m].slice(0, 4))
  }, [u?.matching])
  const shownMatch = useTween(u?.matching ?? 0)
  const [quotes, setQuotes] = useState<Record<string, string>>({})
  const uRef = useRef<Understanding | null>(null)
  const cardRef = useRef<Card | null>(null)
  const sayRef = useRef('')
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
        const talk = v.card?.qid === 'frame' && !saved.length
        setChat(talk)
        if (talk) setMsgs((m) => (m.length ? m : [{ who: 'ai', text: GREET }]))
        return v.id
      } catch {
        setOffline(true)
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
            setReads((r) => [...r.filter((x) => !got.some((f) => f.target === x.target)), ...got.map((f) => ({ target: f.target, quote: f.quote }))])
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
          card: (c) => deliver(() => {
            const was = cardRef.current
            if (c?.qid !== was?.qid || c?.text !== was?.text) setSeq((n) => n + 1)
            setCard(c)
            setLeaving(null)
          }),
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
        await tell(text, id, true)
      }
    })()
    return () => {
      alive = false
      mounted.current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // The opening question (qid frame) is the conversation itself; it is never dealt again as a card.
  const talk = chat || (card?.qid === 'frame' && !msgs.some((m) => m.who === 'me'))
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
  const answer = (chips: string[], value?: string | null, label?: string) => {
    if (!card || busy || leaving) return
    const names = card.chips.filter((c) => chips.includes(c.id)).map((c) => c.label)
    const text = label ?? (chips.includes('skip') ? 'Bỏ qua' : chips.includes('unsure') ? 'Chưa chắc' : [...names, value ?? ''].filter(Boolean).join(', '))
    lastAct.current = text
    drop(cardKey)
    send({ kind: 'answer', qid: card.qid, chips, value: value ?? null }, { n: hist.length + 1, intent: intentOf(card), text: card.text, answer: text })
  }
  const typed = (text: string) => {
    if (busy || leaving) return
    lastAct.current = quoteOf(text)
    drop(cardKey)
    send({ kind: 'text', text })
  }
  // One message of the opening conversation; the agent's reply joins the thread when the turn ends.
  const tell = async (text: string, id = sid, echoed = false) => {
    if (!echoed) setMsgs((m) => [...m, { who: 'me', text }])
    lastAct.current = quoteOf(text)
    const reply = await send({ kind: 'text', text }, undefined, id)
    if (mounted.current) setMsgs((m) => [...m, { who: 'ai', text: reply || 'Mình ghi lại được như dưới đây.' }])
  }
  // The user agrees with what was understood: the conversation card drops and the first short question is dealt.
  const proceed = () => {
    if (busy || leaving) return
    setRemark('')
    if (!card) return show()
    if (still()) return setChat(false)
    setLeaving('chat')
    window.setTimeout(() => { setChat(false); setLeaving(null) }, DROP_MS)
  }
  const edit = (target: string, value: string | null) => {
    lastAct.current = value === null ? 'Bỏ một dòng trên vé' : 'Sửa vé chuyến'
    return send({ kind: 'edit', target, value })
  }
  const show = () => send({ kind: 'show' })
  // A later step chosen on the step bar before the questions are done: search with what is known so far.
  const jump = (target: StepId) => {
    if (!sid || busy) return
    ahead.current = target === 'explore' ? '/explore' : STEPS.find((x) => x.id === target)?.path ?? '/explore'
    show()
  }
  const reset = async () => {
    if (!confirm('Đặt lại toàn bộ những gì mình đã hiểu về chuyến này?')) return
    if (sid) store.set(HIST(sid), null)
    setFull(false)
    setSaid({})
    setMsgs([])
    setQuotes({})
    await open(true)
  }
  const openRow = (target: string | null) => {
    setFocus(target)
    setFull(true)
  }

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
  // The chain: questions just answered for the intent still being asked.
  const chain: Turn[] = []
  for (let i = hist.length - 1; i >= 0 && intent && hist[i].intent === intent; i--) chain.unshift(hist[i])
  const source = (target: string, mark?: boolean): Source => {
    const turns = hist.filter((t) => t.targets.includes(target))
    if (turns.length > 1) return { text: `kết luận từ ${turns.length} câu hỏi`, turns }
    if (turns.length === 1) return { text: `bạn trả lời ở câu ${turns[0].n}`, turns }
    if (said[target]) return { text: said[target], turns: [] }
    return { text: mark ? 'mình suy ra, sửa được' : 'bạn nói', turns: [] }
  }
  const ticket = u && { u, intent, busy, preview, source, onEdit: edit, onShow: show }
  const done = hist.filter((t, i) => hist.findIndex((x) => x.intent === t.intent) === i && t.intent !== intent)
  const told = msgs.find((m) => m.who === 'me')
  const waiting = !talk && !!leaving && leaving === cardKey

  return (
    <>
      <FlowBar step="understand" onAhead={jump} aside={ticket ? <TicketMenu {...ticket} onOpen={openRow} /> : undefined} />
      <Page className="tg-und">
        <div className="tg-und__grid has-sides">
          <nav className="tg-qrail" aria-label="Những điều mình đã hiểu">
            <h2 className="tg-side__h">Mình đang hiểu</h2>
            <ol>
              {!talk && told && (
                <li className="is-done">
                  <button type="button" onClick={() => openRow(null)} aria-label="Xem lại điều bạn kể"><i aria-hidden="true"><Icon name="check" size={13} /></i><span><small>Bạn kể</small><b className="tg-qrail__told">{told.text}</b></span></button>
                </li>
              )}
              {done.map((t) => (
                <li key={t.intent} className="is-done">
                  <button type="button" onClick={() => openRow(t.targets[0] ?? null)} aria-label={`Sửa ${t.intent}`}><i aria-hidden="true"><Icon name="check" size={13} /></i><span><small>{t.intent}</small><b>{hist.filter((x) => x.intent === t.intent).map((x) => x.answer).join(' · ')}</b></span></button>
                </li>
              ))}
              {talk && <li className="is-now" aria-current="step"><div><i aria-hidden="true" /><span><small>Trò chuyện</small><b>bạn kể, mình ghi</b></span></div></li>}
              {intent && <li className="is-now" aria-current="step"><div><i aria-hidden="true" /><span><small>{intent}</small><b>đang hỏi</b></span></div></li>}
              {!talk && !told && !done.length && !intent && <li className="is-next"><div><i aria-hidden="true" /><span><small>Chưa có câu nào</small></span></div></li>}
            </ol>
          </nav>

          <section className="tg-ask" aria-live="polite">
            {hist.length > 0 && (
              <ul className="tg-hist">
                {done.map((t) => (
                  <li key={t.intent}><Icon name="check" size={15} /><span className="tg-faint">{t.intent}</span><b className="tg-chip tg-chip--soft">{hist.filter((x) => x.intent === t.intent).map((x) => x.answer).join(' · ')}</b><button type="button" className="tg-link" onClick={() => openRow(t.targets[0] ?? null)}>Sửa</button></li>
                ))}
              </ul>
            )}
            {notice && <p className="tg-alert" role="alert"><Icon name="warn" size={16} /> {notice}</p>}
            {!talk && !card && u ? (
              <div className="tg-ask__done tg-stage">
                <span className="tg-chip tg-chip--soft"><Icon name="check" size={14} /> ĐỦ ĐỂ TÌM</span>
                <h1>Mình đủ hiểu để gợi ý rồi.</h1>
                <p className="tg-muted">Mình đã ghi {countRows(u)} điều về chuyến này. Bạn vẫn sửa được ở vé bất cứ lúc nào.</p>
                {(remark || busy) && <p className="tg-ask__say">{remark || 'Mình đang ghi lại…'}</p>}
                <div className="tg-ask__ctas"><button type="button" className="tg-btn tg-btn--primary" disabled={busy} onClick={show}>Bắt đầu tìm <Icon name="arrow" size={18} /></button><button type="button" className="tg-btn tg-btn--ghost" onClick={() => openRow(null)}>Xem lại vé</button></div>
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
                  <TripChat key="chat" msgs={msgs.length ? msgs : [{ who: 'ai', text: GREET }]} ready={!!sid} busy={busy} live={remark} reads={reads} quotes={quotes} u={u} card={card} preview={preview} leaving={leaving === 'chat'} onTell={(t) => tell(t)} onOpen={openRow} onEdit={edit} onGo={proceed} />
                ) : card && u && (
                  <div className={`tg-stage tg-ask__card ${chain.length ? 'tg-ask__chain' : ''} ${leaving === cardKey ? 'is-leaving' : ''}`} key={cardKey} aria-busy={busy || !!leaving}>
                    <div className="tg-ask__top">
                      <span className="tg-ask__ico" aria-hidden="true"><Icon name={iconOf(card)} size={18} /></span>
                      <span className="tg-ask__intent"><b>{intent?.toUpperCase()}</b><span className="tg-mono">câu {hist.length + (leaving === cardKey ? 0 : 1)}</span></span>
                      {card.exits && <button type="button" className="tg-ask__skip" disabled={busy} aria-label="Bỏ qua câu này" title="Bỏ qua câu này" onClick={() => answer(['skip'])}><Icon name="arrow" size={16} /></button>}
                    </div>
                    {chain.length > 0 && (
                      <ul className="tg-ask__prev">
                        {chain.map((t) => <li key={t.n}><Icon name="check" size={14} /><span>{t.text}</span><b>{t.answer}</b><button type="button" className="tg-link" onClick={() => openRow(t.targets[0] ?? null)}>Sửa</button></li>)}
                      </ul>
                    )}
                    <Question card={card} busy={busy} onAnswer={answer} onText={typed} u={u} />
                    <div className="tg-ask__note">
                      {busy && !leaving && <p className="tg-ask__say">{remark || 'Mình đang ghi lại…'}</p>}
                      {!busy && remark && <p className="tg-ask__say">{remark}</p>}
                      {card.reason && <p className="tg-ask__why"><Icon name="info" size={13} /> {card.reason}</p>}
                      <p className="tg-faint">{chain.length ? 'Mình hỏi thêm nếu còn chưa rõ, xong sẽ gộp thành một dòng trên vé.' : 'Mình hỏi tiếp tuỳ câu trả lời của bạn.'}</p>
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
                <h2 className="tg-side__h">Đang hợp với bạn</h2>
                <p className="tg-match__n"><b className="tg-mono">{shownMatch.toLocaleString('vi-VN')}</b> nơi{moves[0] && <span key={moves[0].key} className={`tg-match__delta tg-mono ${moves[0].delta < 0 ? 'is-down' : 'is-up'}`}>{placesDelta(moves[0].delta)}</span>}</p>
                <span className="tg-ask__meter tg-match__meter" aria-hidden="true"><i style={{ width: `${Math.max(2, (u.matching / Math.max(1, u.total)) * 100)}%` }} /></span>
                <p className="tg-faint tg-match__of">trên {u.total.toLocaleString('vi-VN')} nơi ở Đà Lạt qua được giới hạn của bạn và có dấu hiệu hợp gu. Danh sách cụ thể hiện ở bước Lựa chọn.</p>
                {moves.length > 0 && (
                  <ol className="tg-match__moves" aria-label="Lựa chọn gần đây làm đổi số nơi">
                    {moves.map((m, i) => <li key={m.key} className={i === 0 ? 'is-new' : undefined}><span>{m.label}</span><b className={`tg-mono ${m.delta < 0 ? 'is-down' : 'is-up'}`}>{placesDelta(m.delta)}</b></li>)}
                  </ol>
                )}
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
  const instant = !card.multi && card.input !== 'date'
  const rows: { row: string | null; chips: Chip[] }[] = []
  for (const c of card.chips) {
    const r = rows.find((x) => x.row === c.row)
    if (r) r.chips.push(c)
    else rows.push({ row: c.row, chips: [c] })
  }
  const asCards = rows.length === 1 && !rows[0].row && card.chips.length <= 6 && card.input !== 'lodging'
  // The search box / trip list is the answer; a typed sentence would not pick a point or a trip.
  const logistics = card.input === 'geo' || card.input === 'transit' || card.input === 'lodging'
  const toggle = (c: Chip) => {
    if (busy) return
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
        {asCards ? (
          <div className="tg-opts" role="group" aria-label="Lựa chọn">
            {card.chips.map((c) => {
              k += 1
              const on = picked.includes(c.id)
              return <button key={c.id} type="button" className={`tg-opt ${on ? 'is-on' : ''}`} aria-pressed={card.multi ? on : undefined} disabled={busy} onClick={() => toggle(c)}><b>{c.label}</b>{c.effect ? <Effect n={c.effect} /> : null}{k <= 9 && <kbd aria-hidden="true">{k}</kbd>}</button>
            })}
            {card.exits && !logistics && <button type="button" className="tg-opt is-soft" disabled={busy} onClick={() => onAnswer(['unsure'])}><b>Chưa chắc</b></button>}
          </div>
        ) : card.chips.length > 0 && card.input !== 'lodging' && (
          <div className="tg-basics">
            {rows.map((r) => (
              <div className="tg-basics__row" key={r.row ?? '_'}>
                {r.row && <h3>{r.row}</h3>}
                <div className="tg-basics__chips" role="group" aria-label={r.row ?? 'Lựa chọn'}>
                  {r.chips.map((c) => <button key={c.id} type="button" className="tg-chip" aria-pressed={picked.includes(c.id)} disabled={busy} onClick={() => toggle(c)}>{c.label}{c.effect ? <Effect n={c.effect} /> : null}</button>)}
                </div>
              </div>
            ))}
            {card.exits && <button type="button" className="tg-chip tg-chip--dash" disabled={busy} onClick={() => onAnswer(['unsure'])}>Chưa chắc</button>}
          </div>
        )}
        {card.input === 'date' && <label className="tg-ask__date"><span>Ngày đến</span><input className="tg-input" type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>}
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
          <TransitPick params={card.params} way={card.qid === 'outbound' ? 'outbound' : 'inbound'} busy={busy}
            onPick={(t) => onAnswer([], JSON.stringify(t), transitLabel(t))}
            onTime={(hhmm) => onAnswer([], JSON.stringify({ time: hhmm }), hhmm)}
            onSkip={() => onAnswer(['skip'], null, 'Tôi tự lo')} />
        )}
        {(card.multi || card.input === 'date') && (
          <button type="button" className="tg-btn tg-btn--primary tg-ask__ok" disabled={busy || !(picked.length || date)} onClick={() => onAnswer(picked, date || null, date ? new Date(date + 'T00:00').toLocaleDateString('vi-VN') : undefined)}>Xong câu này</button>
        )}
        {!logistics && <label className="tg-ask__free">
          <span className="tg-sr">Hoặc gõ câu trả lời của bạn</span>
          <textarea className="tg-line-input" rows={card.input === 'text' ? 2 : 1} value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() } }} placeholder={card.input === 'text' ? 'Ví dụ: 3 ngày cuối tuần với người yêu, đi xe máy, muốn săn mây và ngồi cà phê view đồi' : 'Đáp án khác? Gõ vào đây, ví dụ: không thích đông'} />
          <kbd>Enter</kbd>
        </label>}
        <span className="tg-ask__pill"><b className="tg-mono">{u.matching.toLocaleString('vi-VN')}</b> nơi đang hợp<span className="tg-ask__meter" aria-hidden="true"><i style={{ width: `${Math.max(2, (u.matching / Math.max(1, u.total)) * 100)}%` }} /></span></span>
      </div>
    </>
  )
}

// How a chip would move the "Đang hợp với bạn" count if it alone were chosen now.
function Effect({ n }: { n: number }) {
  return <small className={`tg-opt__fx tg-mono ${n < 0 ? 'is-down' : 'is-up'}`} title="Số nơi hợp với bạn đổi chừng này nếu chỉ chọn ý này">{placesDelta(n)}</small>
}

const quoteOf = (t: string) => `“${t.length > 42 ? `${t.slice(0, 40).trimEnd()}…` : t}”`

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
