import { useCallback, useEffect, useRef, useState } from 'react'
import { consumeStageEntry, enterStage, mutateJourney, resumeJourney } from '../journey'
import { rememberTrip } from '../store'
import { STEPS, useTrip, type StepId } from '../trip'
import { fromSearchInput } from '../tu/adapter'
import { ApiError, createSession, getSession, sendTurn } from '../tu/api'
import type { Card, SearchInput, TurnInput, Understanding, View } from '../tu/types'
import { ArtHills, Busy, Empty, go } from '../ui/common'
import { Icon } from '../ui/icons'
import { LongTripWarning } from '../ui/LongTripWarning'
import { FlowBar, Page, useTitle } from '../ui/Shell'
import { linesOf, TicketFull, TicketMenu, type Source } from '../ui/Ticket'
import { Board } from './understand/Board'
import { Composer, shrink, type Outgoing } from './understand/Composer'
import { botMsg, Turn, type Msg } from './understand/Turn'

// docs/UI_SPEC_USER_WEB.md Trang 3. One conversation: the user tells the trip in words, a photo or a list; the agent
// says what it understood and asks with cards inside the chat (quick replies, the signs of a look, photos of real
// places). The board beside it shows the places that fit right now. Never a fraction, never what comes next.

const KEY = 'tg.tu.v1'
export const GREET = 'Chuyến Đà Lạt bạn đang mong là chuyến như thế nào? Kể tự nhiên thôi: đi cùng ai, mấy ngày, muốn săn mây, sống chậm hay ăn cho đã. Gửi ảnh một nơi bạn thích cũng được.'

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
const isOpen = (c: Card | null) => !!c && c.qid !== 'conversation' && c.qid !== 'frame'

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
  useTitle('Hiểu chuyến đi')
  const { trip, dispatch } = useTrip()
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
    async (input: TurnInput, mine: Msg | null, id = sid): Promise<void> => {
      if (!id) return
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
          done: (d) => { compiled = d.search_input },
          error: (e) => setNotice(e.message),
        })
        if (compiled && mounted.current && origin === location.pathname + location.search) {
          setHanding(true)
          const r = await mutateJourney(id, 'trip', 'advance')
          if (!mounted.current || origin !== location.pathname + location.search) return
          handOff(compiled, r.id)
        }
      } catch (e) {
        setHanding(false)
        if (e instanceof ApiError && e.status === 404) {
          store.set(KEY, null)
          setNotice('Phiên này đã hết. Bấm “Sửa” rồi “Đặt lại toàn bộ” để bắt đầu lại.')
        } else setOffline(true)
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

  const say = (m: Outgoing) => {
    if (busy) return
    if (m.photo) return send({ kind: 'image', value: m.photo, text: m.shown }, { key: key(), who: 'me', text: m.shown, photo: m.photo })
    send({ kind: 'text', text: m.text }, { key: key(), who: 'me', text: m.shown, files: m.files })
  }
  const answer = (m: Msg, input: { chips?: string[]; value?: string | null }, shown: string) => {
    if (busy || m.who !== 'bot' || !m.card) return
    patchBot(m.key, () => ({ answered: shown })) // the card folds into "✓ answer": no second bubble repeats it
    send({ kind: 'answer', qid: m.card.qid, chips: input.chips ?? [], value: input.value ?? null }, null)
  }
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
  // A later step chosen on the step bar: search with what is known so far.
  const jump = (target: StepId) => {
    if (!sid || busy) return
    ahead.current = target === 'explore' ? '/explore' : STEPS.find((x) => x.id === target)?.path ?? '/explore'
    show()
  }
  const reset = async () => {
    if (!confirm('Đặt lại toàn bộ những gì mình đã hiểu về chuyến này?')) return
    setFull(false)
    setMsgs([botMsg(key(), { say: GREET })])
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
  if (handing)
    return (
      <>
        <FlowBar step="understand" />
        <Page><Busy text="Mình đủ hiểu rồi, đang chuẩn bị gợi ý cho chuyến của bạn…" /></Page>
      </>
    )

  const source = (_t: string, mark?: boolean): Source => ({ text: mark ? 'mình suy ra, sửa được' : 'bạn nói', turns: [] })
  const ticket = u && { u, intent: null, busy, preview, source, onEdit: edit, onShow: show }
  const recap = u ? linesOf(u).filter((l) => ['dates', 'who', 'mobility'].includes(l.key)).map((l) => l.value).join(' · ') : ''

  return (
    <div className="tg-rose tg-cx-root">
      <FlowBar step="understand" onAhead={jump} aside={ticket ? <TicketMenu {...ticket} onOpen={openRow} /> : undefined} />
      <Page className="tg-cx">
        <LongTripWarning days={Number(u?.trip.find((row) => row.target === 'days')?.value ?? 0)} />
        <div className="tg-cx__body">
          <main className="tg-cx__chat tg-cx__panel">
            <div className="tg-cx__recap">
              <Icon name="chevronDown" size={16} />
              <span>{recap || 'Chuyến Đà Lạt của bạn'}</span>
              {u && <button type="button" onClick={() => openRow(null)}>Sửa</button>}
            </div>
            <div className="tg-cx__scroll" ref={scroller}>
              <ol className="tg-cx__log" aria-live="polite" aria-label="Trò chuyện về chuyến đi">
                {msgs.map((m) => <Turn key={m.key} m={m} busy={busy} onAnswer={answer} onPhoto={photoFromCard} />)}
              </ol>
              {notice && <p className="tg-alert" role="alert"><Icon name="warn" size={16} /> {notice}</p>}
            </div>
            <input ref={photoPick} type="file" accept="image/*" hidden onChange={(e) => pickedPhoto(e.target.files?.[0])} />
            <Composer ready={!!sid} busy={busy} onSend={say} />
          </main>
          <Board u={u} busy={busy} onShow={show} />
        </div>
      </Page>
      {ticket && <TicketFull {...ticket} open={full} onClose={() => setFull(false)} focus={focus} onFocus={setFocus} onReset={reset} />}
    </div>
  )
}
