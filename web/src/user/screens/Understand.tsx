import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { navigate } from '../../router'
import { Icon, Page, Segmented, Sheet } from '../../ui/bits'
import { WHO_LABEL, useTrip, type Who } from '../trip'
import { fromSearchInput } from '../tu/adapter'
import { createDecision } from '../pd/api'
import { ApiError, createSession, getSession, searchPlaces, sendTurn } from '../tu/api'
import { CROWD_LABEL, FIELD_LABEL, NOVELTY_LABEL, PACE_LABEL, PURPOSE_LABEL, hardText, softText, valueText } from '../tu/labels'
import type { Card, Chip, Row, TurnInput, Understanding } from '../tu/types'

const KEY = 'tg.tu.v1'
type Msg = { role: 'user' | 'agent'; text: string; live?: boolean }

const read = () => {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null
  }
}
const write = (id: string | null) => {
  try {
    if (id) localStorage.setItem(KEY, id)
    else localStorage.removeItem(KEY)
  } catch {
    /* storage blocked: the session lasts until reload */
  }
}

export function Understand() {
  const { trip, dispatch } = useTrip()
  const [sid, setSid] = useState<string | null>(null)
  const [log, setLog] = useState<Msg[]>([])
  const [card, setCard] = useState<Card | null>(null)
  const [u, setU] = useState<Understanding | null>(null)
  const [busy, setBusy] = useState(false)
  const [preview, setPreview] = useState<Set<string>>(new Set())
  const [offline, setOffline] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [sheet, setSheet] = useState(false)
  const end = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const old = read()
        const resumed = old
          ? await getSession(old).catch((e) => {
              if (e instanceof ApiError && e.status === 404) return null
              throw e
            })
          : null
        const v = resumed ?? (await createSession(trip.experience, trip.startWith))
        if (!alive) return
        write(v.id)
        setSid(v.id)
        setLog(v.transcript.map((t) => ({ role: t.role, text: t.text })))
        setCard(v.card)
        setU(v.understanding)
      } catch {
        if (alive) setOffline(true)
      }
    })()
    return () => {
      alive = false
    }
    // the session opens once per mount; experience / startWith only matter for a new one
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    end.current?.scrollIntoView({ block: 'end', behavior: 'smooth' })
  }, [log, card])

  const send = useCallback(
    async (input: TurnInput, echo?: string) => {
      if (!sid || busy) return
      setBusy(true)
      setNotice(null)
      if (echo !== undefined) setLog((l) => [...l, ...(card ? [{ role: 'agent' as const, text: card.text }] : []), { role: 'user', text: echo }])
      if (echo !== undefined) setCard(null)
      try {
        await sendTurn(sid, input, {
          preview: (p) => setPreview(new Set(p.fields.map((f) => f.target))),
          say: (d) =>
            setLog((l) => {
              const last = l[l.length - 1]
              if (d.replace !== undefined) {
                const base = last?.live ? l.slice(0, -1) : l
                return d.replace ? [...base, { role: 'agent', text: d.replace, live: true }] : base
              }
              if (last?.live) return [...l.slice(0, -1), { ...last, text: last.text + (d.delta ?? '') }]
              return [...l, { role: 'agent', text: d.delta ?? '', live: true }]
            }),
          state: (s) => {
            setU(s.understanding)
            setPreview(new Set())
          },
          card: (c) => setCard(c),
          done: (d) => {
            dispatch({ type: 'set', patch: fromSearchInput(d.search_input) })
            write(null)
            createDecision(d.search_input, null).then(
              (r) => {
                dispatch({ type: 'set', patch: { decisionId: r.id } })
                navigate('/app/shortlist')
              },
              () => setNotice('Chưa tạo được gợi ý. Kiểm tra máy chủ chọn nơi (python -m decision serve) rồi thử lại.'),
            )
          },
          error: (e) => setNotice(e.message),
        })
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) {
          write(null)
          setNotice('Phiên này đã hết. Tải lại trang để bắt đầu lại.')
        } else setOffline(true)
      } finally {
        setBusy(false)
        setPreview(new Set())
        setLog((l) => l.map((m) => (m.live ? { ...m, live: false } : m)))
      }
    },
    [sid, busy, card, dispatch],
  )

  const answer = (chips: string[], value?: string | null, label?: string) => {
    if (!card) return
    const names = card.chips.filter((c) => chips.includes(c.id)).map((c) => c.label)
    const echo = label ?? (chips.includes('skip') ? 'Bỏ qua' : chips.includes('unsure') ? 'Không chắc' : [...names, value ?? ''].filter(Boolean).join(', '))
    send({ kind: 'answer', qid: card.qid, chips, value: value ?? null }, echo)
  }
  const edit = (target: string, value: string | null) => send({ kind: 'edit', target, value })
  const show = () => send({ kind: 'show' })

  if (offline)
    return (
      <Page className="page--wide">
        <div className="tu__offline" role="alert">
          <Icon name="alert" />
          <p>
            Chưa kết nối được trợ lý. Chạy <code>python -m trip serve</code> rồi tải lại trang.
          </p>
        </div>
      </Page>
    )

  return (
    <Page className="page--wide">
      <header className="phead">
        <h1>Hiểu chuyến đi của bạn</h1>
        <p>Nói tự nhiên hoặc chọn nhanh. Mình chỉ hỏi điều làm thay đổi gợi ý, và bạn sửa được mọi thứ bên cạnh.</p>
      </header>
      <div className="tu">
        <section className="tu__chat" aria-label="Hội thoại">
          <ol className="tu__log" aria-live="polite">
            {log.map((m, i) => (
              <li key={i} className={`msg msg--${m.role}${m.live ? ' is-live' : ''}`}>
                {m.text}
              </li>
            ))}
            {busy && !log[log.length - 1]?.live && <li className="msg msg--agent msg--typing" aria-label="Đang hiểu">…</li>}
          </ol>
          {card && <QuestionCard key={card.qid} card={card} busy={busy} onAnswer={answer} />}
          {notice && (
            <p className="tu__notice" role="status">
              {notice}
            </p>
          )}
          <Composer busy={busy || !sid} onSend={(text) => send({ kind: 'text', text }, text)} />
          <div ref={end} />
        </section>
        <aside className="tu__panel" aria-label="Bản hiểu nhu cầu">
          {u && <Panel u={u} preview={preview} busy={busy} onEdit={edit} onShow={show} />}
        </aside>
      </div>
      {u && (
        <button type="button" className="tu__bar" onClick={() => setSheet(true)}>
          <span>{summary(u)}</span>
          <Icon name="chevron-up" size={16} />
        </button>
      )}
      <Sheet open={sheet} onClose={() => setSheet(false)} label="Bản hiểu nhu cầu">
        {u && <Panel u={u} preview={preview} busy={busy} onEdit={edit} onShow={show} />}
      </Sheet>
    </Page>
  )
}

function summary(u: Understanding) {
  const bits = u.trip.filter((r) => ['days', 'companions', 'mobility'].includes(r.target)).map((r) => valueText(r.target, r.value))
  if (u.hard.length) bits.push(hardText(u.hard[0]))
  if (u.soft.length) bits.push(`${u.soft.length} sở thích`)
  return bits.join(' · ') || 'Mình đang hiểu chuyến đi của bạn'
}

function QuestionCard({ card, busy, onAnswer }: { card: Card; busy: boolean; onAnswer: (chips: string[], value?: string | null, label?: string) => void }) {
  const [picked, setPicked] = useState<string[]>([])
  const [date, setDate] = useState('')
  const instant = !card.multi && card.input !== 'date'
  const rows: { row: string | null; chips: Chip[] }[] = []
  for (const c of card.chips) {
    const r = rows.find((x) => x.row === c.row)
    if (r) r.chips.push(c)
    else rows.push({ row: c.row, chips: [c] })
  }
  const toggle = (c: Chip) => {
    if (instant) return onAnswer([c.id])
    setPicked((p) => {
      if (p.includes(c.id)) return p.filter((x) => x !== c.id)
      const single = !card.multi || card.single_rows.includes(c.row ?? '')
      const rest = single ? p.filter((id) => card.chips.find((x) => x.id === id)?.row !== c.row) : p
      return [...rest, c.id]
    })
  }
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (busy || t.closest('input, textarea') || e.metaKey || e.ctrlKey || e.altKey) return
      const n = Number(e.key)
      if (n >= 1 && n <= card.chips.length) toggle(card.chips[n - 1])
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })
  let n = 0
  return (
    <section className={`qcard${card.tier === 1 ? ' qcard--must' : ''}`} aria-label="Câu hỏi">
      <p className="qcard__text">{card.text}</p>
      {card.reason && (
        <p className="qcard__why">
          <Icon name="info" size={14} /> {card.reason}
        </p>
      )}
      {rows.map((r) => (
        <div className="qcard__row" key={r.row ?? '_'}>
          {r.row && <span className="qcard__rowlabel">{r.row}</span>}
          <div className="chips">
            {r.chips.map((c) => {
              n += 1
              const on = picked.includes(c.id)
              return (
                <button key={c.id} type="button" className={`chip chip--lean${on ? ' is-on' : ''}`} aria-pressed={on} disabled={busy} onClick={() => toggle(c)}>
                  {n <= 9 && <kbd aria-hidden="true">{n}</kbd>}
                  {c.label}
                </button>
              )
            })}
          </div>
        </div>
      ))}
      {card.input === 'date' && (
        <label className="field">
          <span>Ngày đến</span>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
      )}
      {card.input === 'place' && <PlaceSearch placeholder="Tìm một nơi gần chỗ ở" onPick={(p) => onAnswer([], p.id, p.name)} />}
      <div className="qcard__foot">
        {(card.multi || card.input === 'date') && (
          <button className="btn" disabled={busy || (!picked.length && !date)} onClick={() => onAnswer(picked, date || null, date ? new Date(date + 'T00:00').toLocaleDateString('vi-VN') : undefined)}>
            Xong
          </button>
        )}
        {card.exits && (
          <span className="qcard__exits">
            <button className="link" disabled={busy} onClick={() => onAnswer(['unsure'])}>
              Không chắc
            </button>
            <button className="link" disabled={busy} onClick={() => onAnswer(['skip'])}>
              Bỏ qua
            </button>
          </span>
        )}
      </div>
    </section>
  )
}

function Composer({ busy, onSend }: { busy: boolean; onSend: (text: string) => void }) {
  const [text, setText] = useState('')
  const submit = () => {
    if (!text.trim() || busy) return
    onSend(text.trim())
    setText('')
  }
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }
  return (
    <form
      className="tu__composer"
      onSubmit={(e) => {
        e.preventDefault()
        submit()
      }}
    >
      <textarea
        rows={1}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKey}
        placeholder="Gõ thêm, hoặc dán tên / link…"
        aria-label="Tin nhắn cho trợ lý"
      />
      <button className="btn" type="submit" disabled={busy || !text.trim()} aria-label="Gửi">
        <Icon name="send" size={18} />
      </button>
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
      <label className="search">
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

function Panel({ u, preview, busy, onEdit, onShow }: { u: Understanding; preview: Set<string>; busy: boolean; onEdit: (t: string, v: string | null) => void; onShow: () => void }) {
  const cls = (target: string, mark = false) => `urow${preview.has(target) ? ' is-preview' : ''}${mark ? ' urow--mark' : ''}`
  const trip = Object.fromEntries(u.trip.map((r) => [r.target, r])) as Record<string, Row>
  const [basePick, setBasePick] = useState(false)
  const companions: Who[] = trip.companions?.value ?? []
  const toggleWho = (w: Who) => onEdit('companions', (companions.includes(w) ? companions.filter((x) => x !== w) : [...companions, w]).join(','))
  return (
    <div className={`upanel${busy ? ' is-busy' : ''}`}>
      <h2 className="upanel__title">Mình đang hiểu</h2>

      <section className="usec">
        <h3>Mục đích</h3>
        <div className={cls('purpose', u.purpose?.mark)}>
          <Segmented label="Mục đích" value={u.purpose?.value ?? null} onChange={(v) => onEdit('purpose', v)} options={Object.entries(PURPOSE_LABEL).map(([value, label]) => ({ value, label }))} />
          {u.purpose?.mark && <Mark />}
        </div>
      </section>

      <section className="usec">
        <h3>Chuyến đi</h3>
        <div className={cls('days', trip.days?.mark)}>
          <span className="urow__k">{FIELD_LABEL.days}</span>
          <Segmented label="Số ngày" value={trip.days?.value ?? null} onChange={(v) => onEdit('days', String(v))} options={[1, 2, 3, 4, 5].map((d) => ({ value: d, label: `${d}` }))} />
        </div>
        <div className={cls('start_date', trip.start_date?.mark)}>
          <span className="urow__k">{FIELD_LABEL.start_date}</span>
          <input type="date" value={trip.start_date?.value ?? ''} onChange={(e) => onEdit('start_date', e.target.value || null)} aria-label="Ngày đi" />
          {!trip.start_date && trip.month && <small>{valueText('month', trip.month.value)}</small>}
        </div>
        <div className={cls('companions', trip.companions?.mark)}>
          <span className="urow__k">{FIELD_LABEL.companions}</span>
          <div className="chips">
            {(Object.keys(WHO_LABEL) as Who[]).map((w) => (
              <button key={w} type="button" className={`chip chip--lean${companions.includes(w) ? ' is-on' : ''}`} aria-pressed={companions.includes(w)} onClick={() => toggleWho(w)}>
                {WHO_LABEL[w]}
              </button>
            ))}
          </div>
        </div>
        <div className={cls('mobility', trip.mobility?.mark)}>
          <span className="urow__k">{FIELD_LABEL.mobility}</span>
          <Segmented label="Đi lại" value={trip.mobility?.value ?? null} onChange={(v) => onEdit('mobility', v)} options={[{ value: 'motorbike', label: 'Xe máy' }, { value: 'car', label: 'Ô tô' }, { value: 'ride', label: 'Grab' }]} />
        </div>
        <div className={cls('base', trip.base?.mark)}>
          <span className="urow__k">{FIELD_LABEL.base}</span>
          {trip.base && !basePick ? (
            <span className="urow__v">
              {valueText('base', trip.base.value)}{' '}
              <button className="link" onClick={() => setBasePick(true)}>
                Đổi
              </button>
            </span>
          ) : (
            <PlaceSearch
              placeholder="Chọn nơi gần chỗ ở"
              onPick={(p) => {
                setBasePick(false)
                onEdit('base', p.id)
              }}
            />
          )}
        </div>
        <div className="urow urow--times">
          {(['arrive_at', 'leave_at', 'day_end'] as const).map((t) => (
            <label key={t} className={cls(t, trip[t]?.mark)}>
              <span className="urow__k">{FIELD_LABEL[t]}</span>
              <input type="time" value={trip[t]?.value ?? ''} onChange={(e) => onEdit(t, e.target.value || null)} />
            </label>
          ))}
        </div>
      </section>

      {u.anchors.length > 0 && (
        <section className="usec">
          <h3>Nơi muốn đến</h3>
          <ul className="ulist">
            {u.anchors.map((a) => (
              <li key={a.target} className={cls(a.target)}>
                <Icon name={a.state === 'matched' ? 'flag' : 'alert'} size={14} />
                <span className="urow__v">
                  {a.name ?? a.text}
                  {a.state === 'missing' && <small> · chưa tìm thấy, không dùng để xếp lịch</small>}
                  {a.priority === 'want' && <small> · bỏ được nếu thiếu giờ</small>}
                </span>
                <Remove onClick={() => onEdit(a.target, null)} />
              </li>
            ))}
          </ul>
        </section>
      )}

      {u.hard.length > 0 && (
        <section className="usec usec--rule">
          <h3>
            <Icon name="lock" size={14} /> Bắt buộc
          </h3>
          <ul className="ulist">
            {u.hard.map((h) => (
              <li key={h.target} className={cls(h.target)}>
                <span className="urow__v">
                  {hardText(h)}
                  <small>
                    {' '}
                    · {h.coverage.passed} nơi xác minh, {h.coverage.unknown} chưa rõ
                  </small>
                </span>
                <button type="button" className={`chip chip--rule${h.unknown_policy === 'flag' ? ' is-on' : ''}`} aria-pressed={h.unknown_policy === 'flag'} onClick={() => onEdit(h.target, h.unknown_policy === 'flag' ? 'exclude' : 'flag')}>
                  Xem cả nơi chưa rõ
                </button>
                <Remove onClick={() => onEdit(h.target, null)} />
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="usec">
        <h3>Sở thích</h3>
        {u.soft.length ? (
          <div className="chips">
            {u.soft.map((s) => (
              <span key={s.target} className={`chip chip--${s.mark ? 'profile' : 'lean'} is-on${preview.has('soft') ? ' is-preview' : ''}`}>
                <button type="button" className="chip__body" title="Chạm để đổi thích / tránh" onClick={() => onEdit(s.target, s.weight === 'love' ? 'avoid' : 'love')}>
                  {softText(s)}
                  {s.mark && <Mark />}
                </button>
                <Remove onClick={() => onEdit(s.target, null)} />
              </span>
            ))}
          </div>
        ) : (
          <p className="usec__empty">Chưa có. Kể thêm điều bạn muốn trải nghiệm.</p>
        )}
      </section>

      <section className="usec">
        <h3>Nhịp độ</h3>
        <div className={cls('pace', u.pace?.mark)}>
          <Segmented label="Nhịp độ" value={u.pace?.value ?? null} onChange={(v) => onEdit('pace', v)} options={Object.entries(PACE_LABEL).map(([value, label]) => ({ value, label }))} />
          {u.pace?.mark && <Mark />}
        </div>
        <div className={cls('max_leg_min', u.max_leg_min?.mark)}>
          <span className="urow__k">{FIELD_LABEL.max_leg_min}</span>
          <Segmented label="Mỗi chặng tối đa" value={u.max_leg_min?.value ?? null} onChange={(v) => onEdit('max_leg_min', String(v))} options={[15, 30, 60].map((m) => ({ value: m, label: `${m}′` }))} />
        </div>
        <div className={cls('crowd_tolerance', u.crowd_tolerance?.mark)}>
          <span className="urow__k">{FIELD_LABEL.crowd_tolerance}</span>
          <Segmented label="Chỗ đông" value={u.crowd_tolerance?.value ?? null} onChange={(v) => onEdit('crowd_tolerance', v)} options={Object.entries(CROWD_LABEL).map(([value, label]) => ({ value, label }))} />
        </div>
        <div className={cls('novelty', u.novelty?.mark)}>
          <span className="urow__k">{FIELD_LABEL.novelty}</span>
          <Segmented label="Mới hay quen" value={u.novelty?.value ?? null} onChange={(v) => onEdit('novelty', v)} options={Object.entries(NOVELTY_LABEL).map(([value, label]) => ({ value, label }))} />
        </div>
        {u.budget_vnd && (
          <div className={cls('budget_vnd', u.budget_vnd.mark)}>
            <span className="urow__k">{FIELD_LABEL.budget_vnd}</span>
            <span className="urow__v">{valueText('budget_vnd', u.budget_vnd.value)} · chưa kiểm được bằng dữ liệu</span>
            <Remove onClick={() => onEdit('budget_vnd', null)} />
          </div>
        )}
      </section>

      {(u.unknowns.length > 0 || u.unmapped.length > 0) && (
        <section className="usec usec--open">
          {u.unknowns.length > 0 && (
            <p>
              <b>Chưa rõ</b> {u.unknowns.map((k) => FIELD_LABEL[k] ?? k).join(', ')}
            </p>
          )}
          {u.unmapped.length > 0 && (
            <div>
              <b>Chưa kiểm được</b>
              <ul className="ulist">
                {u.unmapped.map((x) => (
                  <li key={x.target} className="urow">
                    <span className="urow__v">{x.phrase}</span>
                    <small>sẽ nêu trong lời giải thích, không dùng để chọn</small>
                    <Remove onClick={() => onEdit(x.target, null)} />
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      <button className="btn upanel__go" disabled={busy} onClick={onShow}>
        {u.safety_pending ? 'Còn 1 câu an toàn cần trả lời' : 'Xem gợi ý'} <Icon name="arrow-right" size={16} />
      </button>
    </div>
  )
}

const Mark = () => (
  <span className="umark" title="Mình suy ra, bạn sửa được">
    ✎
  </span>
)

const Remove = ({ onClick }: { onClick: () => void }) => (
  <button type="button" className="iconbtn iconbtn--sm" aria-label="Bỏ" onClick={onClick}>
    <Icon name="x" size={12} />
  </button>
)
