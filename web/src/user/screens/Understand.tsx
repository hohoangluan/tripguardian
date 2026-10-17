import { useCallback, useEffect, useRef, useState, type DragEvent } from 'react'
import { useAccount } from '../account'
import { Sidebar } from '../home/Frame'
import { useOpenJourney } from '../home/dialogs'
import { primeDecision } from '../pd/api'
import type { TripSummary } from '../pd/types'
import { consumeStageEntry, enterStage, mutateJourney, resumeJourney } from '../journey'
import { rememberTrip } from '../store'
import { useTrip } from '../trip'
import { fromSearchInput } from '../tu/adapter'
import { ApiError, createSession, getSession, sendTurn } from '../tu/api'
import type { Card, Deck, DeckAnswers, SearchInput, TurnInput, Understanding, View } from '../tu/types'
import { ArtHills, Busy, Empty, go } from '../ui/common'
import { Icon } from '../ui/icons'
import { LongTripWarning } from '../ui/LongTripWarning'
import { useTitle } from '../ui/Shell'
import { TicketFull, type Source } from '../ui/Ticket'
import { Board } from './understand/Board'
import { Composer, shrink, type Outgoing } from './understand/Composer'
import { History } from './understand/History'
import { botMsg, Turn, type Msg } from './understand/Turn'

// docs/UI_SPEC_USER_WEB.md Trang 3. One conversation: the user tells the trip in words, a photo or a list; the agent
// says what it understood and asks with cards inside the chat (quick replies, the signs of a look, photos of real
// places). The workspace shares the homepage rail and shows progress across eight trip information groups.

const KEY = 'tg.tu.v1'
export const GREET = 'Chuyến Đà Lạt bạn đang mong là chuyến như thế nào? Kể tự nhiên thôi: đi cùng ai, mấy ngày, muốn săn mây, sống chậm hay ăn cho đã. Gửi ảnh một nơi bạn thích cũng được.'

// Starting points on the welcome canvas: a tap fills the message box, the user still sends it.
const STARTERS = [
  { img: '/img/home/cloud.jpg', a: 'Săn', b: 'mây', note: 'Dậy sớm, đồi cao, bình minh trên núi.', seed: 'Mình muốn săn mây và ngắm bình minh, đi chậm và yên tĩnh.' },
  { img: '/img/home/cafe.jpg', a: 'Sống', b: 'chậm', note: 'Ít điểm, nhiều quán cà phê và đi dạo.', seed: 'Mình muốn sống chậm, ít điểm đến, nhiều quán cà phê đẹp.' },
  { img: '/img/home/lake.jpg', a: 'Cả nhà', b: 'cùng đi', note: 'Dễ đi, có chỗ cho trẻ và người lớn tuổi.', seed: 'Mình đi cùng gia đình có trẻ nhỏ và người lớn tuổi, cần lịch trình nhẹ nhàng.' },
  { img: '/img/home/pine.jpg', a: 'Ăn cho', b: 'đã', note: 'Quán ngon, đồ nướng, chợ đêm.', seed: 'Mình muốn ăn cho đã: quán ngon, đồ nướng và chợ đêm.' },
]

const store = {
  get(k: string) {
    try { return localStorage.getItem(k) } catch { return null }
  },
  set(k: string, v: string | null) {
    try { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v) } catch { /* the session lasts until reload */ }
  },
}

let seq = 0
const key = () => `m${++seq}`
const isOpen = (c: Card | Deck | null) => !!c && (c.kind === 'deck' || (c.qid !== 'conversation' && c.qid !== 'frame'))

// The server's transcript -> the chat, for a resumed session: what was said stays, old cards read as text.
function fromTranscript(v: View): Msg[] {
  const out: Msg[] = [botMsg(key(), { say: GREET })]
  for (const t of v.transcript) {
    if (t.role === 'user') out.push({ key: key(), who: 'me', text: t.text })
    else if (t.text && t.turn > 0) out.push(botMsg(key(), { say: t.text })) // turn 0 is the server's greeting: the chat has its own
  }
  if (isOpen(v.card)) out.push(botMsg(key(), { card: v.card }))
  return out
}

export function Understand() {
  const [workspace, setWorkspace] = useState(0)
  return <UnderstandSession key={workspace} onSwitch={() => setWorkspace(n => n + 1)} />
}

function UnderstandSession({ onSwitch }: { onSwitch: () => void }) {
  useTitle('Hiểu chuyến đi')
  const { trip, dispatch } = useTrip()
  const account = useAccount()
  const openJourney = useOpenJourney()
  const [sid, setSid] = useState<string | null>(null)
  const [u, setU] = useState<Understanding | null>(null)
  const [msgs, setMsgs] = useState<Msg[]>(() => [botMsg(key(), { say: GREET })])
  const [busy, setBusy] = useState(false)
  const [handing, setHanding] = useState(false)
  const [offline, setOffline] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [full, setFull] = useState(false)
  const [focus, setFocus] = useState<string | null>(null)
  const [preview, setPreview] = useState<Set<string>>(new Set())
  const [seed, setSeed] = useState<{ text: string; n: number } | null>(null)
  const [dragging, setDragging] = useState(false)
  const [incoming, setIncoming] = useState<{ files: File[]; n: number } | null>(null)
  const mounted = useRef(true)
  const scroller = useRef<HTMLDivElement>(null)
  const photoPick = useRef<HTMLInputElement>(null)

  const patchBot = (k: string, fn: (m: Extract<Msg, { who: 'bot' }>) => Partial<Extract<Msg, { who: 'bot' }>>) =>
    setMsgs((ms) => ms.map((m) => (m.key === k && m.who === 'bot' ? { ...m, ...fn(m) } : m)))

  // Keep the newest line in view.
  useEffect(() => {
    const el = scroller.current
    if (!el) return
    const t = window.setTimeout(() => el.scrollTo({ top: el.scrollHeight, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' }), 40)
    return () => window.clearTimeout(t)
  }, [msgs])

  const handOff = useCallback((si: SearchInput, jid: string) => {
    dispatch({ type: 'set', patch: { ...fromSearchInput(si), journeyId: jid, decisionId: jid, planningId: null } })
    store.set(KEY, null)
    primeDecision(jid)
    go('/explore')
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
        if (!explicitBack && recovery?.view.stage === 'trip' && recovery.view.outputs.trip) {
          setHanding(true)
          const j = await mutateJourney(recovery.view.id, 'trip', 'advance')
          if (!mounted.current || origin !== location.pathname + location.search) return null
          handOff(recovery.view.outputs.trip as SearchInput, j.id)
          return null
        }
        if (recovery && recovery.view.stage !== 'trip') {
          const j = recovery.view
          dispatch({ type: 'set', patch: { journeyId: j.id, decisionId: j.id, planningId: null } })
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
        setU(v.understanding)
        if (resumed) setMsgs(fromTranscript(v))
        return v.id
      } catch {
        setOffline(true)
        return null
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [trip.experience, trip.startWith, trip.journeyId],
  )

  // One turn: the user's line joins the chat, a live bot turn fills from the server's events.
  const send = useCallback(
    async (input: TurnInput, mine: Msg | null, id = sid): Promise<boolean> => {
      if (!id) return false
      setBusy(true)
      setNotice(null)
      const bot = key()
      setMsgs((ms) => [...ms, ...(mine ? [mine] : []), botMsg(bot, { live: true })])
      const origin = location.pathname + location.search
      let compiled: SearchInput | null = null
      let said = ''
      try {
        await sendTurn(id, input, {
          preview: (p) => setPreview(new Set(p.fields.map((f) => f.target))),
          progress: (d) => patchBot(bot, () => ({ steps: d.steps, ...(d.sources?.length ? { sources: d.sources } : {}) })),
          say: (d) => {
            said = d.replace !== undefined ? d.replace : said + (d.delta ?? '')
            patchBot(bot, () => ({ say: said }))
          },
          state: (s) => { setU(s.understanding); setPreview(new Set()) },
          card: (c) => patchBot(bot, () => ({ card: isOpen(c) ? c : null })),
          deck_issues: (d) => patchBot(bot, () => ({ issues: d.issues })),
          readback: (readback) => setU(old => old ? { ...old, readback } : old),
          done: (d) => { compiled = d.search_input },
          error: (e) => setNotice(e.message),
        })
        if (compiled && mounted.current && origin === location.pathname + location.search) {
          setHanding(true)
          const r = await mutateJourney(id, 'trip', 'advance')
          if (!mounted.current || origin !== location.pathname + location.search) return false
          handOff(compiled, r.id)
        }
        return true
      } catch (e) {
        setHanding(false)
        if (e instanceof ApiError && e.status === 404) {
          store.set(KEY, null)
          setNotice('Phiên này đã hết. Bấm “Sửa” rồi “Đặt lại toàn bộ” để bắt đầu lại.')
        } else setOffline(true)
        return false
      } finally {
        setBusy(false)
        setPreview(new Set())
        // a turn that brought nothing to show (an edit) leaves no empty bubble behind
        setMsgs((ms) => ms.flatMap((m) => (m.key !== bot || m.who !== 'bot' ? [m] : !m.say && !m.card && !m.steps.length ? [] : [{ ...m, live: false, t1: Date.now() }])))
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sid, handOff],
  )

  // Opens once per mount. What the user typed on Khám phá becomes the first message.
  useEffect(() => {
    mounted.current = true
    let alive = true
    ;(async () => {
      const id = await open(!trip.journeyId && !!(trip.startText || trip.startWith), () => alive)
      if (alive && id && trip.startText) {
        const text = trip.startText
        dispatch({ type: 'set', patch: { startText: null } })
        await send({ kind: 'text', text }, { key: key(), who: 'me', text }, id)
      }
    })()
    return () => {
      alive = false
      mounted.current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // A file dropped anywhere on the chat frame goes to the message box; a miss must not open the file in the tab.
  useEffect(() => {
    const stop = (e: globalThis.DragEvent) => { if (e.dataTransfer?.types.includes('Files')) e.preventDefault() }
    window.addEventListener('dragover', stop)
    window.addEventListener('drop', stop)
    return () => { window.removeEventListener('dragover', stop); window.removeEventListener('drop', stop) }
  }, [])
  const dragOver = (e: DragEvent) => { if (e.dataTransfer.types.includes('Files')) { e.preventDefault(); setDragging(true) } }
  const dragLeave = (e: DragEvent) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false) }
  const dropped = (e: DragEvent) => {
    if (!e.dataTransfer.files.length) return
    e.preventDefault()
    setDragging(false)
    setIncoming({ files: Array.from(e.dataTransfer.files), n: Date.now() })
  }

  const say = (m: Outgoing) => {
    if (busy) return
    if (m.photo) return send({ kind: 'image', value: m.photo, text: m.shown }, { key: key(), who: 'me', text: m.shown, photo: m.photo })
    send({ kind: 'text', text: m.text }, { key: key(), who: 'me', text: m.shown, files: m.files })
  }
  const answer = (m: Msg, input: { chips?: string[]; value?: string | null }, shown: string) => {
    if (busy || m.who !== 'bot' || !m.card || m.card.kind === 'deck') return
    patchBot(m.key, () => ({ answered: shown })) // the card folds into "✓ answer": no second bubble repeats it
    send({ kind: 'answer', qid: m.card.qid, chips: input.chips ?? [], value: input.value ?? null }, null)
  }
  const answerDeck = async (m: Msg, answers: DeckAnswers, shown: string) => {
    if (busy || m.who !== 'bot') return
    patchBot(m.key, () => ({ answered: shown })) // the card folds into "✓ what was chosen" at once
    if (!(await send({ kind: 'deck', answers }, null))) patchBot(m.key, () => ({ answered: null }))
  }
  const typed = (text: string) => { if (!busy) send({ kind: 'text', text }, { key: key(), who: 'me', text }) }
  const photoFromCard = () => photoPick.current?.click()
  const pickedPhoto = async (f: File | undefined) => {
    if (photoPick.current) photoPick.current.value = ''
    if (!f) return
    try {
      const url = await shrink(f)
      send({ kind: 'image', value: url }, { key: key(), who: 'me', text: '', photo: url })
    } catch {
      setNotice('Ảnh này mình không mở được, bạn thử ảnh JPG hoặc PNG khác nhé.')
    }
  }
  const edit = (target: string, value: string | null) => send({ kind: 'edit', target, value }, null)
  const show = () => { if (!busy) send({ kind: 'show' }, null) }
  const newTrip = () => {
    if (busy) return
    store.set(KEY, null)
    dispatch({ type: 'reset' })
    onSwitch()
  }
  const selectTrip = (selected: TripSummary) => {
    if (busy || selected.id === sid) return
    openJourney(selected)
    if (selected.stage === 'trip') onSwitch()
  }
  const reset = async () => {
    if (!confirm('Đặt lại toàn bộ những gì mình đã hiểu về chuyến này?')) return
    setFull(false)
    setMsgs([botMsg(key(), { say: GREET })])
    await open(true)
  }
  const openRow = (target: string | null) => {
    const current = [...msgs].reverse().find(m => m.who === 'bot' && !m.answered && m.card?.kind === 'deck')
    if (target && current?.who === 'bot' && current.card?.kind === 'deck' && current.card.tabs.some(tab => tab.qid === target)) {
      setFull(false) // the open question is that topic: bring it into view
      setTimeout(() => document.querySelector<HTMLElement>('[data-deck-qid]')?.scrollIntoView({ block: 'center', behavior: 'smooth' }), 0)
      return
    }
    setFocus(target)
    setFull(true)
  }

  const source = (_t: string, mark?: boolean): Source => ({ text: mark ? 'mình suy ra, sửa được' : 'bạn nói', turns: [] })
  const ticket = u && { u, intent: null, busy, preview, source, onEdit: edit, onShow: show }
  const greeting = msgs.length === 1 && msgs[0].who === 'bot' && msgs[0].say === GREET && !msgs[0].card
  const name = account?.guest ? '' : account?.name?.trim()

  return (
    <div className="tg-home tg-workspace">
      <Sidebar path="" />
      <History active={sid} busy={busy || handing || (!sid && !offline)} onNew={newTrip} onOpen={selectTrip} />
      <div className="tg-cx-root tg-workspace__content">
        <LongTripWarning days={Number(u?.trip.find((row) => row.target === 'days')?.value ?? 0)} />
        <div className="tg-cx__body">
          <main className={`tg-cx__chat tg-cx__panel ${dragging ? 'is-dropping' : ''}`} onDragEnter={dragOver} onDragOver={dragOver} onDragLeave={dragLeave} onDrop={dropped}>
            {offline ? <div className="tg-workspace__state"><Empty art={<ArtHills />} title="Chưa kết nối được trợ lý" body="Máy chủ hành trình chưa trả lời. Thử lại sau ít phút; những gì bạn đã trả lời vẫn còn." action={<button type="button" className="tg-btn tg-btn--primary" onClick={() => location.reload()}><Icon name="refresh" size={18} /> Thử lại</button>} /></div>
              : handing ? <div className="tg-workspace__state"><Busy text="Mình đủ hiểu rồi, đang chuẩn bị gợi ý cho chuyến của bạn…" /></div>
              : <>
            <div className={`tg-cx__scroll ${greeting ? 'is-welcome' : ''}`} ref={scroller}>
              {greeting ? <section className="tg-welcome" aria-label="Bắt đầu trò chuyện">
                <h1>Chào{name ? ` ${name}` : ' bạn'},<br />bạn muốn đi đâu, làm gì?</h1>
                <p>Cứ nói tự nhiên, mình sẽ cùng bạn lên ý tưởng cho chuyến đi thật hợp.</p>
                <ul className="tg-welcome__cards" aria-label="Gợi ý để bắt đầu">
                  {STARTERS.map((c) => (
                    <li key={c.a}><button type="button" onClick={() => setSeed({ text: c.seed, n: Date.now() })}>
                      <img src={c.img} alt="" loading="lazy" />
                      <b>{c.a} <em>{c.b}</em></b>
                      <span>{c.note}</span>
                    </button></li>
                  ))}
                </ul>
              </section> : <ol className="tg-cx__log" aria-live="polite" aria-label="Trò chuyện về chuyến đi">
                {msgs.map((m) => <Turn key={m.key} m={m} busy={busy} onAnswer={answer} onDeck={answerDeck} onText={typed} onPhoto={photoFromCard} />)}
              </ol>}
              {notice && <p className="tg-alert" role="alert"><Icon name="warn" size={16} /> {notice}</p>}
            </div>
            <input ref={photoPick} type="file" accept="image/*" hidden onChange={(e) => pickedPhoto(e.target.files?.[0])} />
            <Composer ready={!!sid} busy={busy} onSend={say} seed={seed} incoming={incoming} dragging={dragging} />
            {dragging && <div className="tg-cx__drop" aria-hidden="true"><Icon name="image" size={28} /><b>Thả ảnh vào đây</b><span>Ảnh một nơi bạn thích, hoặc danh sách địa điểm</span></div>}
            </>}
          </main>
          <Board u={u} busy={busy || handing || offline} preview={preview} onShow={show} onOpen={openRow} />
        </div>
      </div>
      {ticket && <TicketFull {...ticket} open={full} onClose={() => setFull(false)} focus={focus} onFocus={setFocus} onReset={reset} />}
    </div>
  )
}
