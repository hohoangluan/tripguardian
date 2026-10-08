import { Fragment, useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { navigate } from '../../router'
import { Icon, Page, Segmented, Sheet } from '../../ui/bits'
import { WHO_LABEL, useTrip, type Who } from '../trip'
import { fromSearchInput } from '../tu/adapter'
import { consumeStageEntry, enterStage, mutateJourney, resumeJourney } from '../journey'
import type { SearchInput } from '../tu/types'
import { ApiError, createSession, getSession, searchPlaces, sendTurn } from '../tu/api'
import { CROWD_LABEL, FIELD_LABEL, NOVELTY_LABEL, PACE_LABEL, PURPOSE_LABEL, hardText, softText, valueText } from '../tu/labels'
import type { Card, Chip, HardRow, Row, TurnInput, Understanding } from '../tu/types'

// docs/UI_SPEC_USER_WEB.md §4 Trang 3. The agent decides the intents, how many questions each takes and their order;
// this page only shows the turn being asked and what has already happened. Never a fraction, never what comes next.

const KEY = 'tg.tu.v1'
const HIST = (sid: string) => `tg.tu.hist.${sid}`

// One answered question: which intent it served and what it changed on the ticket.
interface Turn {
  n: number
  intent: string
  text: string
  answer: string
  targets: string[]
}

const store = {
  get(k: string) {
    try {
      return localStorage.getItem(k)
    } catch {
      return null
    }
  },
  set(k: string, v: string | null) {
    try {
      if (v === null) localStorage.removeItem(k)
      else localStorage.setItem(k, v)
    } catch {
      /* storage blocked: the session lasts until reload */
    }
  },
}

const QID_INTENT: Record<string, string> = {
  frame: 'Chuyến đi', days: 'Số ngày', dates: 'Ngày đi', mobility: 'Đi lại', base: 'Chỗ ở', times: 'Giờ đến, giờ đi',
  entry_exit: 'Giờ đến, giờ đi', purpose: 'Mục đích', ready: 'Sẵn sàng', show_first: 'Sẵn sàng',
}
const GROUP_INTENT: Record<string, string> = {
  A: 'Chuyến đi', B: 'Đi với ai', C: 'Điều cần lưu ý', D: 'Ngân sách', E: 'Nơi muốn đến', F: 'Nhịp độ', G: 'Gu chuyến đi',
  H: 'Mới hay quen', I: 'Làm rõ',
}
const intentOf = (c: Card) => QID_INTENT[c.qid] ?? GROUP_INTENT[c.group] ?? 'Câu hỏi'

// Flatten the understanding so two snapshots can be compared target by target.
function flat(u: Understanding | null): Record<string, string> {
  if (!u) return {}
  const out: Record<string, string> = {}
  const put = (r: { target: string } | null) => r && (out[r.target] = JSON.stringify(r))
  ;[u.purpose, u.pace, u.max_leg_min, u.crowd_tolerance, u.novelty, u.budget_vnd, ...u.trip, ...u.anchors, ...u.hard, ...u.soft].forEach(put)
  return out
}

function changed(a: Understanding | null, b: Understanding) {
  const x = flat(a)
  const y = flat(b)
  return Object.keys(y).filter((k) => x[k] !== y[k])
}

export function Understand() {
  const { trip, dispatch } = useTrip()
  const [sid, setSid] = useState<string | null>(null)
  const [card, setCard] = useState<Card | null>(null)
  const [u, setU] = useState<Understanding | null>(null)
  const [hist, setHist] = useState<Turn[]>([])
  const [said, setSaid] = useState<Record<string, string>>({}) // target -> where it came from, besides answers
  const [remark, setRemark] = useState('')
  const [busy, setBusy] = useState(false)
  const [preview, setPreview] = useState<Set<string>>(new Set())
  const [offline, setOffline] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [full, setFull] = useState(false)
  const [focus, setFocus] = useState<string | null>(null) // row to open for editing in the full ticket
  const [sheet, setSheet] = useState(false)
  const uRef = useRef<Understanding | null>(null)
  const mounted = useRef(true)
  uRef.current = u

  const open = useCallback(
    async (fresh: boolean) => {
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
          const j = await mutateJourney(recovery.view.id, 'trip', 'advance')
          if (!mounted.current || origin !== location.pathname + location.search) return null
          dispatch({ type: 'set', patch: { ...fromSearchInput(recovery.view.outputs.trip as SearchInput), journeyId: j.id, decisionId: j.id, planningId: null } })
          store.set(KEY, null)
          navigate('/app/shortlist')
          return null
        }
        if (recovery && recovery.view.stage !== 'trip') {
          const j = recovery.view
          dispatch({ type: 'set', patch: { journeyId: j.id, decisionId: j.id, planningId: j.stage === 'planning' ? j.id : null } })
          navigate(j.stage === 'planning' ? '/app/plan' : '/app/shortlist')
          return null
        }
        const resumed = recovery ? await getSession(recovery.view.id) : null
        if (!mounted.current || origin !== location.pathname + location.search) return null
        const v = resumed ?? (await createSession(trip.experience, trip.startWith))
        store.set(KEY, v.id)
        setSid(v.id)
        dispatch({ type: 'set', patch: { journeyId: v.id, decisionId: null, planningId: null } })
        setCard(v.card)
        setU(v.understanding)
        try {
          setHist(resumed ? JSON.parse(store.get(HIST(v.id)) ?? '[]') : [])
        } catch {
          setHist([])
        }
        return v.id
      } catch {
        setOffline(true)
        return null
      }
    },
    [trip.experience, trip.startWith],
  )

  const send = useCallback(
    async (input: TurnInput, turn?: Omit<Turn, 'targets'>, id = sid) => {
      if (!id) return
      setBusy(true)
      setNotice(null)
      setRemark('')
      const origin = location.pathname + location.search
      const before = uRef.current
      let touched: string[] = []
      let compiled: SearchInput | null = null
      try {
        await sendTurn(id, input, {
          preview: (p) => setPreview(new Set(p.fields.map((f) => f.target))),
          say: (d) => setRemark((r) => (d.replace !== undefined ? d.replace : r + (d.delta ?? ''))),
          state: (s) => {
            touched = changed(before, s.understanding)
            setU(s.understanding)
            setPreview(new Set())
          },
          card: (c) => setCard(c),
          done: (d) => { compiled = d.search_input },
          error: (e) => setNotice(e.message),
        })
        if (compiled && mounted.current && origin === location.pathname + location.search) {
          const r = await mutateJourney(id, 'trip', 'advance')
          if (!mounted.current || origin !== location.pathname + location.search) return
          dispatch({ type: 'set', patch: { ...fromSearchInput(compiled), journeyId: r.id, decisionId: r.id, planningId: null } })
          store.set(KEY, null)
          navigate('/app/shortlist')
        }
        if (turn) {
          setHist((h) => {
            const next = [...h, { ...turn, targets: touched }]
            store.set(HIST(id), JSON.stringify(next))
            return next
          })
        } else if (touched.length) {
          const from = input.kind === 'edit' ? 'bạn sửa trực tiếp' : 'từ lời bạn kể'
          setSaid((s) => ({ ...s, ...Object.fromEntries(touched.map((t) => [t, from])) }))
        }
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) {
          store.set(KEY, null)
          setNotice('Phiên này đã hết. Bấm “Đặt lại toàn bộ” để bắt đầu lại.')
        } else setOffline(true)
      } finally {
        setBusy(false)
        setPreview(new Set())
      }
    },
    [sid, dispatch],
  )

  // Opens once per mount. What the user typed on the start page becomes the first turn.
  useEffect(() => {
    mounted.current = true
    let alive = true
    ;(async () => {
      const id = await open(false)
      if (alive && id && trip.startText) {
        const text = trip.startText
        dispatch({ type: 'set', patch: { startText: null } })
        await send({ kind: 'text', text }, undefined, id)
      }
    })()
    return () => {
      alive = false
      mounted.current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Esc closes the full ticket.
  useEffect(() => {
    if (!full) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setFull(false)
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [full])

  const answer = (chips: string[], value?: string | null, label?: string) => {
    if (!card || busy) return
    const names = card.chips.filter((c) => chips.includes(c.id)).map((c) => c.label)
    const text = label ?? (chips.includes('skip') ? 'Bỏ qua' : chips.includes('unsure') ? 'Chưa chắc' : [...names, value ?? ''].filter(Boolean).join(', '))
    send({ kind: 'answer', qid: card.qid, chips, value: value ?? null }, { n: hist.length + 1, intent: intentOf(card), text: card.text, answer: text })
  }
  const edit = (target: string, value: string | null) => send({ kind: 'edit', target, value })
  const show = () => send({ kind: 'show' })
  const reset = async () => {
    if (!confirm('Đặt lại toàn bộ những gì mình đã hiểu về chuyến này?')) return
    if (sid) store.set(HIST(sid), null)
    setFull(false)
    setSaid({})
    await open(true)
  }
  const openRow = (target: string | null) => {
    setFocus(target)
    setFull(true)
  }

  if (offline)
    return (
      <Page className="page--narrow">
        <p className="notice notice--bad" role="alert">
          <Icon name="alert" /> Chưa kết nối được trợ lý. Chạy <code>python -m trip serve</code> rồi tải lại trang.
        </p>
      </Page>
    )
  if (!u || !sid) return <div className="loading">Đang mở cuộc hỏi</div>

  const intent = card ? intentOf(card) : null
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

  const ask = (
    <Ask
      card={card}
      intent={intent}
      n={hist.length + 1}
      chain={chain}
      u={u}
      busy={busy}
      remark={remark}
      notice={notice}
      onAnswer={answer}
      onText={(text) => send({ kind: 'text', text })}
      onEdit={(t) => openRow(t)}
    />
  )

  return (
    <Page className={`tu${full ? ' tu--full' : ''}`}>
      <section className="tu__ask" aria-label="Câu hỏi">
        {ask}
      </section>
      <aside className="tu__ticket" aria-label="Vé chuyến này">
        {full ? (
          <FullTicket u={u} intent={intent} chain={chain} busy={busy} preview={preview} focus={focus} source={source} onFocus={setFocus} onEdit={edit} onShow={show} onReset={reset} onClose={() => setFull(false)} />
        ) : (
          <Ticket u={u} intent={intent} busy={busy} preview={preview} source={source} onEdit={edit} onShow={show} onOpen={openRow} />
        )}
      </aside>
      <button type="button" className="tu__bar" onClick={() => setSheet(true)}>
        <span>Vé chuyến này · đã ghi {countRows(u)} mục</span>
        <Icon name="chevron-up" size={16} />
      </button>
      <Sheet open={sheet} onClose={() => setSheet(false)} label="Vé chuyến này">
        <FullTicket u={u} intent={intent} chain={chain} busy={busy} preview={preview} focus={focus} source={source} onFocus={setFocus} onEdit={edit} onShow={show} onReset={reset} onClose={() => setSheet(false)} />
      </Sheet>
    </Page>
  )
}

interface Source {
  text: string
  turns: Turn[]
}

// ---------- left column: the turn being asked ----------

function Ask({
  card,
  intent,
  n,
  chain,
  u,
  busy,
  remark,
  notice,
  onAnswer,
  onText,
  onEdit,
}: {
  card: Card | null
  intent: string | null
  n: number
  chain: Turn[]
  u: Understanding
  busy: boolean
  remark: string
  notice: string | null
  onAnswer: (chips: string[], value?: string | null, label?: string) => void
  onText: (text: string) => void
  onEdit: (target: string | null) => void
}) {
  const multi = chain.length > 0
  const share = u.total ? u.matching / u.total : 0
  return (
    <>
      <div className="ask__top">
        {intent && <span className="ask__intent">{intent}</span>}
        {card && <span className="ask__n">câu {n}</span>}
        <p className="ask__count">
          Có <b>{u.matching.toLocaleString('vi-VN')}</b> nơi đang hợp với nhu cầu của bạn
          <span className="ask__bar" aria-hidden="true">
            <i style={{ width: `${Math.max(2, share * 100)}%` }} />
          </span>
        </p>
        {multi && card?.exits && (
          <button className="link ask__skipall" disabled={busy} onClick={() => onAnswer(['skip'])}>
            Bỏ qua phần này
          </button>
        )}
      </div>

      {(remark || busy) && (
        <p className={`ask__remark${busy ? ' is-live' : ''}`} aria-live="polite">
          {remark || 'Mình đang ghi lại…'}
        </p>
      )}
      {notice && (
        <p className="notice notice--bad" role="status">
          <Icon name="alert" size={16} /> {notice}
        </p>
      )}

      {!card ? (
        <p className="ask__idle">Mình đã ghi lại hết. Soát vé bên cạnh rồi bấm Bắt đầu tìm.</p>
      ) : multi ? (
        <div className="ask__chain">
          {chain.map((t) => (
            <div className="ask__done" key={t.n}>
              <span className="ask__q">{t.text}</span>
              <span className="ask__a">{t.answer}</span>
              <button className="link" onClick={() => onEdit(t.targets[0] ?? null)}>
                Sửa
              </button>
            </div>
          ))}
          <div className="ask__live">
            <Question key={card.qid} card={card} busy={busy} small onAnswer={onAnswer} onText={onText} multi />
          </div>
        </div>
      ) : (
        <Question key={card.qid} card={card} busy={busy} onAnswer={onAnswer} onText={onText} />
      )}
    </>
  )
}

function Question({
  card,
  busy,
  small,
  multi,
  onAnswer,
  onText,
}: {
  card: Card
  busy: boolean
  small?: boolean
  multi?: boolean
  onAnswer: (chips: string[], value?: string | null, label?: string) => void
  onText: (text: string) => void
}) {
  const [picked, setPicked] = useState<string[]>([])
  const [date, setDate] = useState('')
  const instant = !card.multi && card.input !== 'date'
  const rows: { row: string | null; chips: Chip[] }[] = []
  for (const c of card.chips) {
    const r = rows.find((x) => x.row === c.row)
    if (r) r.chips.push(c)
    else rows.push({ row: c.row, chips: [c] })
  }
  // "Ready" turns are a decision to move on, not a preference: plain buttons.
  const go = card.qid === 'ready' || card.qid === 'show_first'
  const asCards = rows.length === 1 && !rows[0].row && card.chips.length <= 6
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
  const canDone = picked.length > 0 || !!date
  // A long question keeps its first sentence as the headline; the rest reads as a normal line.
  const cut = card.text.length > 70 ? card.text.search(/[.:?!]\s/) : -1
  const head = cut > 0 ? card.text.slice(0, cut + 1).replace(/:$/, '?') : card.text
  const rest = cut > 0 ? card.text.slice(cut + 2) : ''
  let k = 0
  return (
    <div className={`q${small ? ' q--small' : ''}`}>
      <h1 className="q__text">{head}</h1>
      {rest && <p className="q__more">{rest}</p>}
      {card.reason && <p className="q__why">Vì sao hỏi: {card.reason}</p>}

      {go ? (
        <div className="q__go">
          {card.chips.map((c, i) => (
            <button key={c.id} type="button" className={`btn${i ? ' btn--ghost' : ' btn--stub'}`} disabled={busy} onClick={() => onAnswer([c.id])}>
              {c.label}
            </button>
          ))}
        </div>
      ) : asCards ? (
        <div className="q__cards">
          {card.chips.map((c) => {
            k += 1
            const on = picked.includes(c.id)
            return (
              <button key={c.id} type="button" className={`qcard${on ? ' is-on' : ''}`} aria-pressed={card.multi ? on : undefined} disabled={busy} onClick={() => toggle(c)}>
                <b>{c.label}</b>
                {k <= 9 && <kbd aria-hidden="true">{k}</kbd>}
              </button>
            )
          })}
          {card.exits && (
            <button type="button" className="qcard qcard--unsure" disabled={busy} onClick={() => onAnswer(['unsure'])}>
              <b>Chưa chắc</b>
              <span>để mình hỏi tiếp</span>
            </button>
          )}
        </div>
      ) : (
        <div className="q__rows">
          {rows.map((r) => (
            <div className={`q__row${r.row ? '' : ' q__row--plain'}`} key={r.row ?? '_'}>
              {r.row && <span className="q__rowlabel">{r.row}</span>}
              <div className="chips">
                {r.chips.map((c) => {
                  k += 1
                  const on = picked.includes(c.id)
                  return (
                    <button key={c.id} type="button" className={`chip${on ? ' is-on' : ''}`} aria-pressed={on} disabled={busy} onClick={() => toggle(c)}>
                      {c.label}
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
          {card.exits && (
            <button type="button" className="chip chip--unsure" disabled={busy} onClick={() => onAnswer(['unsure'])}>
              Chưa chắc
            </button>
          )}
        </div>
      )}

      {card.input === 'date' && (
        <label className="field q__date">
          <span>Ngày đến</span>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
      )}
      {card.input === 'place' && <PlaceSearch placeholder="Tìm một nơi gần chỗ ở" onPick={(p) => onAnswer([], p.id, p.name)} />}
      {(card.multi || card.input === 'date') && (
        <button className="btn q__done" disabled={busy || !canDone} onClick={() => onAnswer(picked, date || null, date ? new Date(date + 'T00:00').toLocaleDateString('vi-VN') : undefined)}>
          Xong câu này
        </button>
      )}

      <LineInput busy={busy} big={card.input === 'text'} onSend={onText} />

      <div className="q__foot">
        {card.exits ? (
          <button className="link" disabled={busy} onClick={() => onAnswer(['skip'])}>
            Bỏ qua câu này
          </button>
        ) : (
          <span />
        )}
        <p>{multi ? 'Mình hỏi thêm nếu còn chưa rõ, xong sẽ gộp thành một dòng trên vé.' : 'Mình hỏi tiếp tuỳ câu trả lời của bạn.'}</p>
      </div>
    </div>
  )
}

function LineInput({ busy, big, onSend }: { busy: boolean; big?: boolean; onSend: (text: string) => void }) {
  const [text, setText] = useState('')
  const submit = () => {
    if (!text.trim() || busy) return
    onSend(text.trim())
    setText('')
  }
  return (
    <form
      className="lineinput q__input"
      onSubmit={(e) => {
        e.preventDefault()
        submit()
      }}
    >
      <textarea
        rows={1}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            submit()
          }
        }}
        placeholder={big ? 'Gõ tự nhiên, ví dụ: 3 ngày cuối tuần, đi với người yêu, xe máy, mê cà phê view đồi' : 'hoặc viết theo cách của bạn'}
        aria-label="Trả lời bằng lời của bạn"
      />
      <kbd>Enter để gửi</kbd>
    </form>
  )
}

function PlaceSearch({ onPick, placeholder }: { onPick: (p: { id: string; name: string }) => void; placeholder: string }) {
  const [q, setQ] = useState('')
  const [hits, setHits] = useState<{ id: string; name: string; category: string | null }[]>([])
  useEffect(() => {
    if (q.trim().length < 2) return setHits([])
    const t = setTimeout(() => searchPlaces(q).then(setHits).catch(() => setHits([])), 180)
    return () => clearTimeout(t)
  }, [q])
  return (
    <div className="picker">
      <label className="lineinput">
        <Icon name="search" size={16} />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={placeholder} aria-label={placeholder} />
      </label>
      {hits.length > 0 && (
        <ul className="picker__list">
          {hits.map((p) => (
            <li key={p.id}>
              <button type="button" onClick={() => onPick(p)}>
                <b>{p.name}</b>
                <small>{p.category}</small>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// ---------- the ticket: only what is already there ----------

type TripRows = Record<string, Row>
const tripOf = (u: Understanding) => Object.fromEntries(u.trip.map((r) => [r.target, r])) as TripRows

function dateLine(t: TripRows) {
  const days = t.days?.value as number | undefined
  const bits: string[] = []
  if (t.start_date) {
    const a = new Date(t.start_date.value + 'T00:00')
    if (days) {
      const b = new Date(a)
      b.setDate(a.getDate() + days - 1)
      bits.push(a.getMonth() === b.getMonth() ? `${a.getDate()}–${b.getDate()}/${a.getMonth() + 1}` : `${a.getDate()}/${a.getMonth() + 1}–${b.getDate()}/${b.getMonth() + 1}`)
    } else bits.push(a.toLocaleDateString('vi-VN'))
  } else if (t.month) bits.push(`tháng ${t.month.value}`)
  if (days) bits.push(`${days} ngày`)
  return bits.join(' · ')
}

function whoText(t: TripRows) {
  const who = t.companions ? valueText('companions', t.companions.value).toLowerCase() : ''
  const people = t.people ? `${t.people.value} người` : ''
  return [people, who].filter(Boolean).join(' · ')
}

function timesText(t: TripRows) {
  return [t.arrive_at && `tới ${t.arrive_at.value}`, t.leave_at && `rời ${t.leave_at.value}`, t.day_end && `xong trước ${t.day_end.value}`].filter(Boolean).join(' · ')
}

function paceText(u: Understanding) {
  return [u.pace && valueText('pace', u.pace.value).toLowerCase(), u.max_leg_min && `≤ ${u.max_leg_min.value}′ mỗi chặng`, u.crowd_tolerance && `chỗ đông: ${valueText('crowd_tolerance', u.crowd_tolerance.value).toLowerCase()}`]
    .filter(Boolean)
    .join(' · ')
}

// Excluded right now by one hard limit: failed, plus unknown unless the user chose to see those flagged.
const excluding = (h: HardRow) => h.coverage.failed + (h.unknown_policy === 'flag' ? 0 : h.coverage.unknown)

interface Line {
  key: string
  label: string
  value: ReactNode
  target: string
  mark?: boolean
}

function lines(u: Understanding): { trip: Line[]; way: Line[] } {
  const t = tripOf(u)
  const trip: Line[] = []
  if (t.companions || t.people) trip.push({ key: 'who', label: 'Đi với', value: whoText(t), target: 'companions', mark: t.companions?.mark })
  if (t.mobility) trip.push({ key: 'mobility', label: 'Phương tiện', value: valueText('mobility', t.mobility.value).toLowerCase(), target: 'mobility', mark: t.mobility.mark })
  if (t.base) trip.push({ key: 'base', label: 'Chỗ ở', value: valueText('base', t.base.value), target: 'base', mark: t.base.mark })
  if (t.arrive_at || t.leave_at || t.day_end) trip.push({ key: 'times', label: 'Giờ giấc', value: timesText(t), target: 'arrive_at' })
  const way: Line[] = []
  if (u.purpose) way.push({ key: 'purpose', label: 'Mục đích', value: valueText('purpose', u.purpose.value).toLowerCase(), target: 'purpose', mark: u.purpose.mark })
  if (u.pace || u.max_leg_min || u.crowd_tolerance) way.push({ key: 'pace', label: 'Nhịp độ', value: paceText(u), target: 'pace', mark: u.pace?.mark })
  if (u.novelty) way.push({ key: 'novelty', label: 'Mới hay quen', value: valueText('novelty', u.novelty.value).toLowerCase(), target: 'novelty', mark: u.novelty.mark })
  if (u.budget_vnd) way.push({ key: 'budget', label: 'Ngân sách', value: valueText('budget_vnd', u.budget_vnd.value), target: 'budget_vnd', mark: u.budget_vnd.mark })
  return { trip, way }
}

function countRows(u: Understanding) {
  const l = lines(u)
  return l.trip.length + l.way.length + u.anchors.length + u.hard.length + u.soft.length + (u.trip.some((r) => ['start_date', 'month', 'days'].includes(r.target)) ? 1 : 0)
}

function unknownLabel(k: string) {
  return (FIELD_LABEL[k] ?? k).toLowerCase()
}

function Ticket({
  u,
  intent,
  busy,
  preview,
  source,
  onEdit,
  onShow,
  onOpen,
}: {
  u: Understanding
  intent: string | null
  busy: boolean
  preview: Set<string>
  source: (t: string, mark?: boolean) => Source
  onEdit: (t: string, v: string | null) => void
  onShow: () => void
  onOpen: (target: string | null) => void
}) {
  const t = tripOf(u)
  const { trip, way } = lines(u)
  const live = (target: string) => (preview.has(target) ? ' is-preview' : '')
  return (
    <div className={`ticket${busy ? ' is-busy' : ''}`}>
      <header className="ticket__head">
        <h2>Đà Lạt</h2>
        {dateLine(t) && <p className="mono">{dateLine(t)}</p>}
      </header>

      {trip.length > 0 && (
        <TSection title="Chuyến đi">
          {trip.map((l) => (
            <div key={l.key} className={`trow${live(l.target)}`}>
              <span>{l.label}</span>
              <b>{l.value}</b>
            </div>
          ))}
        </TSection>
      )}

      {u.anchors.length > 0 && (
        <TSection title="Nhất định đến">
          {u.anchors.map((a) => (
            <div key={a.target} className={`tanchor${a.state !== 'matched' ? ' is-open' : ''}`}>
              <Icon name={a.state === 'matched' ? (a.priority === 'must' ? 'lock' : 'pin') : 'alert'} size={15} />
              <span>
                {a.name ?? a.text}
                {a.state === 'choose' && <small> · cần bạn chọn</small>}
                {a.state === 'missing' && <small> · chưa tìm thấy</small>}
              </span>
            </div>
          ))}
        </TSection>
      )}

      {u.hard.length > 0 && (
        <TSection title="Giới hạn cứng">
          <div className="tstamps">
            {u.hard.map((h) => (
              <span key={h.target} className={`stamp${h.unknown_policy === 'flag' ? ' is-relaxed' : ''}${live(h.target)}`}>
                {hardText(h)}
              </span>
            ))}
          </div>
        </TSection>
      )}

      {u.soft.length > 0 && (
        <TSection title="Sở thích">
          <div className="twishes">
            {u.soft.map((s) => (
              <span key={s.target} className={`wish${s.weight === 'avoid' ? ' wish--avoid' : ''}${live('soft')}`}>
                <span className="wish__chip">
                  {softText(s)}
                  <button type="button" className="wish__x" aria-label={`Bỏ ${softText(s)}`} onClick={() => onEdit(s.target, null)}>
                    <Icon name="x" size={12} />
                  </button>
                </span>
                <small>{source(s.target, s.mark).text}</small>
              </span>
            ))}
          </div>
        </TSection>
      )}

      {way.length > 0 && (
        <TSection title="Cách đi">
          {way.map((l) => (
            <div key={l.key} className={`trow${live(l.target)}`}>
              <span>{l.label}</span>
              <b>{l.value}</b>
            </div>
          ))}
        </TSection>
      )}

      {intent && intent !== 'Sẵn sàng' && (
        <div className="trow trow--asking">
          <span>{intent}</span>
          <b className="mono">đang hỏi</b>
        </div>
      )}

      {countRows(u) > 0 && (u.unknowns.length > 0 || u.safety_pending) && (
        <TSection title="Còn chưa rõ">
          {u.safety_pending && (
            <div className="topen">
              <Icon name="alert" size={15} />
              <span>một câu về an toàn</span>
            </div>
          )}
          {u.unknowns.slice(0, 4).map((k) => (
            <div className="topen" key={k}>
              <Icon name="alert" size={15} />
              <span>{unknownLabel(k)}</span>
              <button className="link" onClick={() => onOpen(k)}>
                Trả lời
              </button>
            </div>
          ))}
          {u.unknowns.length > 4 && (
            <button className="link topen__more" onClick={() => onOpen(null)}>
              và {u.unknowns.length - 4} điều nữa
            </button>
          )}
        </TSection>
      )}

      <footer className="ticket__foot">
        <span className="mono">đã ghi {countRows(u)} mục</span>
        <button className="btn btn--stub" disabled={busy} onClick={onShow}>
          Bắt đầu tìm
        </button>
        <button className="link" onClick={() => onOpen(null)}>
          Xem đầy đủ
        </button>
      </footer>
    </div>
  )
}

function TSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="tsec">
      <h3>{title}</h3>
      {children}
    </section>
  )
}

// ---------- Xem đầy đủ: review and edit every line, see the questions behind each conclusion ----------

function FullTicket({
  u,
  intent,
  chain,
  busy,
  preview,
  focus,
  source,
  onFocus,
  onEdit,
  onShow,
  onReset,
  onClose,
}: {
  u: Understanding
  intent: string | null
  chain: Turn[]
  busy: boolean
  preview: Set<string>
  focus: string | null
  source: (t: string, mark?: boolean) => Source
  onFocus: (t: string | null) => void
  onEdit: (t: string, v: string | null) => void
  onShow: () => void
  onReset: () => void
  onClose: () => void
}) {
  const t = tripOf(u)
  const [opened, setOpened] = useState<string | null>(null)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (focus) ref.current?.querySelector(`[data-row="${focus}"]`)?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [focus])

  const row = (key: string, label: string, value: ReactNode, target: string, mark?: boolean, editor?: ReactNode) => {
    const src = source(target, mark)
    const editing = focus === key || focus === target
    const chainOpen = opened === key
    return (
      <div className={`frow${preview.has(target) ? ' is-preview' : ''}${editing ? ' is-editing' : ''}`} data-row={key} key={key}>
        <span className="frow__k">{label}</span>
        <div className="frow__v">
          <b>{value ?? <span className="muted">—</span>}</b>
          {value ? <small className="source">{src.text}</small> : null}
          {chainOpen && src.turns.length > 1 && (
            <ol className="frow__chain">
              {src.turns.map((x, i) => (
                <li key={x.n}>
                  <span className="mono">{String(i + 1).padStart(2, '0')}</span>
                  <span>{x.text}</span>
                  <b>{x.answer}</b>
                </li>
              ))}
              <li className="frow__rule">Chỉ dòng kết luận được dùng để gợi ý.</li>
            </ol>
          )}
          {editing && editor && <div className="frow__edit">{editor}</div>}
        </div>
        <span className="frow__act">
          {src.turns.length > 1 && (
            <button className="iconbtn iconbtn--sm" aria-expanded={chainOpen} aria-label="Xem các câu đã hỏi" onClick={() => setOpened(chainOpen ? null : key)}>
              <Icon name={chainOpen ? 'chevron-up' : 'next'} size={13} />
            </button>
          )}
          {editor && (
            <button className="link" onClick={() => onFocus(editing ? null : key)}>
              {editing ? 'Xong' : value ? 'Sửa' : 'Trả lời'}
            </button>
          )}
        </span>
      </div>
    )
  }

  const companions: Who[] = t.companions?.value ?? []
  const toggleWho = (w: Who) => onEdit('companions', (companions.includes(w) ? companions.filter((x) => x !== w) : [...companions, w]).join(','))
  const seg = <T extends string | number>(target: string, label: string, value: T | null, options: { value: T; label: string }[]) => (
    <Segmented label={label} value={value} onChange={(v) => onEdit(target, String(v))} options={options} />
  )

  return (
    <div className={`fticket${busy ? ' is-busy' : ''}`} ref={ref}>
      <header className="fticket__head">
        <div>
          <h2>Vé chuyến này</h2>
          <p className="mono">Đà Lạt{dateLine(t) ? ` · ${dateLine(t)}` : ''}</p>
          <small className="source">Xem lại và sửa bất cứ dòng nào.</small>
        </div>
        <button className="link fticket__close" onClick={onClose}>
          Thu gọn <kbd>Esc</kbd>
        </button>
      </header>

      <div className="fticket__body">
        {row('dates', 'Ngày đi', dateLine(t) || null, t.start_date ? 'start_date' : 'days', t.start_date?.mark, (
          <div className="frow__pair">
            <input type="date" value={t.start_date?.value ?? ''} onChange={(e) => onEdit('start_date', e.target.value || null)} aria-label="Ngày đi" />
            {seg('days', 'Số ngày', t.days?.value ?? null, [1, 2, 3, 4, 5].map((d) => ({ value: d, label: `${d} ngày` })))}
          </div>
        ))}
        {row('who', 'Đi với', whoText(t) || null, 'companions', t.companions?.mark, (
          <div className="chips">
            {(Object.keys(WHO_LABEL) as Who[]).map((w) => (
              <button key={w} type="button" className={`chip${companions.includes(w) ? ' is-on' : ''}`} aria-pressed={companions.includes(w)} onClick={() => toggleWho(w)}>
                {WHO_LABEL[w]}
              </button>
            ))}
          </div>
        ))}
        {row('mobility', 'Phương tiện', t.mobility ? valueText('mobility', t.mobility.value).toLowerCase() : null, 'mobility', t.mobility?.mark,
          seg('mobility', 'Đi lại', t.mobility?.value ?? null, [
            { value: 'motorbike', label: 'Xe máy' },
            { value: 'car', label: 'Ô tô' },
            { value: 'ride', label: 'Xe công nghệ' },
          ]),
        )}
        {row('base', 'Chỗ ở', t.base ? valueText('base', t.base.value) : null, 'base', t.base?.mark, <PlaceSearch placeholder="Chọn nơi gần chỗ ở" onPick={(p) => onEdit('base', p.id)} />)}
        {row('times', 'Giờ giấc', timesText(t) || null, 'arrive_at', false, (
          <div className="frow__times">
            {(['arrive_at', 'leave_at', 'day_end'] as const).map((k) => (
              <label key={k} className="field">
                <span>{FIELD_LABEL[k]}</span>
                <input type="time" value={t[k]?.value ?? ''} onChange={(e) => onEdit(k, e.target.value || null)} />
              </label>
            ))}
          </div>
        ))}

        {intent && intent !== 'Sẵn sàng' && (
          <div className="frow frow--asking">
            <span className="frow__k">{intent}</span>
            <div className="frow__v">
              <b>đang hỏi</b>
              <ol className="frow__chain">
                {chain.map((x, i) => (
                  <li key={x.n}>
                    <span className="mono">{String(i + 1).padStart(2, '0')}</span>
                    <span>{x.text}</span>
                    <b>{x.answer}</b>
                  </li>
                ))}
                <li>
                  <span className="mono">{String(chain.length + 1).padStart(2, '0')}</span>
                  <span>…</span>
                </li>
              </ol>
            </div>
            <span className="frow__act">
              <button className="link" onClick={onClose}>
                Trả lời tiếp
              </button>
            </span>
          </div>
        )}

        {u.anchors.length > 0 && (
          <div className="fgroup">
            <span className="frow__k">Nhất định đến</span>
            <ul>
              {u.anchors.map((a) => (
                <li key={a.target}>
                  <Icon name={a.state === 'matched' ? 'lock' : 'alert'} size={15} />
                  <span>
                    {a.name ?? a.text}
                    {a.state === 'missing' && <small className="unsure"> · chưa tìm thấy, không dùng để xếp lịch</small>}
                    {a.priority === 'want' && <small className="muted"> · bỏ được nếu thiếu giờ</small>}
                  </span>
                  <button className="link" onClick={() => onEdit(a.target, null)}>
                    Bỏ
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {u.hard.length > 0 && (
          <div className="fgroup">
            <span className="frow__k">Giới hạn cứng</span>
            <ul>
              {u.hard.map((h) => (
                <li key={h.target} className={preview.has(h.target) ? 'is-preview' : ''}>
                  <span className={`stamp${h.unknown_policy === 'flag' ? ' is-relaxed' : ''}`}>{hardText(h)}</span>
                  <span className="mono fgroup__cost">
                    {h.unknown_policy === 'flag' ? `đã nới · xem cả ${h.coverage.unknown} nơi chưa rõ` : `đang loại ${excluding(h)} nơi`}
                  </span>
                  <button className="link" onClick={() => onEdit(h.target, h.unknown_policy === 'flag' ? 'exclude' : 'flag')}>
                    {h.unknown_policy === 'flag' ? 'Siết lại' : 'Nới'}
                  </button>
                  <button className="link" onClick={() => onEdit(h.target, null)}>
                    Bỏ
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="fgroup">
          <span className="frow__k">Sở thích</span>
          {u.soft.length ? (
            <div className="twishes">
              {u.soft.map((s) => (
                <span key={s.target} className={`wish${s.weight === 'avoid' ? ' wish--avoid' : ''}`}>
                  <span className="wish__chip">
                    <button type="button" title="Đổi thích / tránh" onClick={() => onEdit(s.target, s.weight === 'love' ? 'avoid' : 'love')}>
                      {softText(s)}
                    </button>
                    <button type="button" className="wish__x" aria-label={`Bỏ ${softText(s)}`} onClick={() => onEdit(s.target, null)}>
                      <Icon name="x" size={12} />
                    </button>
                  </span>
                  <small>{source(s.target, s.mark).text}</small>
                </span>
              ))}
            </div>
          ) : (
            <p className="muted">—</p>
          )}
        </div>

        {row('purpose', 'Mục đích', u.purpose ? valueText('purpose', u.purpose.value).toLowerCase() : null, 'purpose', u.purpose?.mark,
          seg('purpose', 'Mục đích', u.purpose?.value ?? null, Object.entries(PURPOSE_LABEL).map(([value, label]) => ({ value, label }))),
        )}
        {row('pace', 'Nhịp độ', paceText(u) || null, 'pace', u.pace?.mark, (
          <div className="frow__stack">
            {seg('pace', 'Nhịp độ', u.pace?.value ?? null, Object.entries(PACE_LABEL).map(([value, label]) => ({ value, label })))}
            {seg('max_leg_min', 'Mỗi chặng tối đa', u.max_leg_min?.value ?? null, [15, 30, 45, 60].map((m) => ({ value: m, label: `≤ ${m}′ mỗi chặng` })))}
            {seg('crowd_tolerance', 'Chỗ đông', u.crowd_tolerance?.value ?? null, Object.entries(CROWD_LABEL).map(([value, label]) => ({ value, label: `Chỗ đông: ${label.toLowerCase()}` })))}
          </div>
        ))}
        {row('novelty', 'Mới hay quen', u.novelty ? valueText('novelty', u.novelty.value).toLowerCase() : null, 'novelty', u.novelty?.mark,
          seg('novelty', 'Mới hay quen', u.novelty?.value ?? null, Object.entries(NOVELTY_LABEL).map(([value, label]) => ({ value, label }))),
        )}
        {u.budget_vnd && row('budget', 'Ngân sách', `${valueText('budget_vnd', u.budget_vnd.value)} · chưa kiểm được bằng dữ liệu`, 'budget_vnd', u.budget_vnd.mark)}

        {(u.unknowns.length > 0 || u.unmapped.length > 0) && (
          <div className="fgroup">
            <span className="frow__k">Còn chưa rõ</span>
            <ul>
              {u.unknowns.map((k) => (
                <li key={k} className="topen">
                  <Icon name="alert" size={15} />
                  <span>{unknownLabel(k)}</span>
                </li>
              ))}
              {u.unmapped.map((x) => (
                <Fragment key={x.target}>
                  <li>
                    <Icon name="info" size={15} />
                    <span>
                      “{x.phrase}” <small className="muted">· chưa kiểm được bằng dữ liệu, chỉ nêu trong lời giải thích</small>
                    </span>
                    <button className="link" onClick={() => onEdit(x.target, null)}>
                      Bỏ
                    </button>
                  </li>
                </Fragment>
              ))}
            </ul>
          </div>
        )}
      </div>

      <footer className="fticket__foot">
        <span className="mono">đã ghi {countRows(u)} mục</span>
        <button className="btn btn--stub" disabled={busy} onClick={onShow}>
          Bắt đầu tìm
        </button>
        <button className="link link--quiet" onClick={onReset}>
          Đặt lại toàn bộ
        </button>
      </footer>
    </div>
  )
}
