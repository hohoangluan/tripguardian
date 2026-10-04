import gsap from 'gsap'
import { useState, type FormEvent } from 'react'
import { placeById, signal } from '../../data/store'
import type { Place } from '../../data/types'
import { navigate } from '../../router'
import { story } from '../../scene/story'
import { ConfidenceTag, Icon, Page, PlaceCover, Sheet } from '../../ui/bits'
import { LineArt } from '../../ui/LineArt'
import { whyNot } from '../pd/api'
import { useDecision } from '../pd/decision'
import type { Card, Claim, DropReason, WhyNot } from '../pd/types'
import { searchPlaces } from '../tu/api'
import { area } from '../search'
import { DROP_LABEL, useTrip } from '../trip'

export const CONF = { high: 'Cao', medium: 'Trung bình', low: 'Thấp' } as const

const placeLink = (id: string) => `/app/place/${encodeURIComponent(id)}`

export function Shortlist() {
  const { trip } = useTrip()
  const { view, error, act, busy } = useDecision()
  const [tab, setTab] = useState<string | null>(null)
  const [compare, setCompare] = useState<string[]>([])
  const [dropping, setDropping] = useState<Card | null>(null)

  if (!trip.decisionId)
    return (
      <Page className="page--narrow">
        <div className="empty">
          <LineArt variant="spot" />
          <p>{error ?? 'Chưa có gợi ý. Bắt đầu từ bước hiểu chuyến đi, chỉ vài câu thôi.'}</p>
          <button className="btn" onClick={() => navigate('/app/understand')}>
            Hiểu chuyến đi
          </button>
        </div>
      </Page>
    )
  if (!view) return <div className={`loading${error ? ' loading--error' : ''}`}>{error ?? 'Đang chuẩn bị gợi ý'}</div>

  const anchors = view.groups.find((g) => g.id === 'anchors')
  const groups = view.groups.filter((g) => g.id !== 'anchors')
  const current = groups.find((g) => g.id === tab) ?? groups[0]
  const toggleCompare = (id: string) => setCompare((c) => (c.includes(id) ? c.filter((x) => x !== id) : c.length >= 3 ? [c[1], c[2], id] : [...c, id]))
  const cardProps = { comparing: compare, onCompare: toggleCompare, onDrop: setDropping }
  const pairs = similarPairs(current?.cards ?? [])
  const total = view.groups.reduce((n, g) => n + g.cards.length, 0)

  return (
    <Page>
      <header className="uhead">
        <h1>Gợi ý cho chuyến của bạn</h1>
        <p>Một tập nhỏ đáng cân nhắc, kèm lý do và cái giá phải đánh đổi. Bạn chốt, mình không chọn thay.</p>
      </header>

      {error && (
        <p className="notice notice--bad" role="alert">
          <Icon name="alert" size={16} /> {error}
        </p>
      )}

      {anchors && anchors.cards.length > 0 && (
        <section className="usection sl-anchors">
          <h2 className="utitle">
            Nhất định đến <small>{anchors.cards.length} nơi bạn đã chốt</small>
          </h2>
          <div className="pcards">
            {anchors.cards.map((c) => (
              <PlaceCard key={c.id} c={c} {...cardProps} />
            ))}
          </div>
        </section>
      )}

      <div className="sl-tabs" role="tablist" aria-label="Nhóm địa điểm">
        {groups.map((g) => (
          <button
            key={g.id}
            role="tab"
            aria-selected={current?.id === g.id}
            className={current?.id === g.id ? 'is-on' : ''}
            onClick={() => setTab(g.id)}
            onKeyDown={(e) => {
              const i = groups.indexOf(g)
              const n = e.key === 'ArrowRight' ? groups[i + 1] : e.key === 'ArrowLeft' ? groups[i - 1] : null
              if (n) setTab(n.id)
            }}
          >
            {g.label} <span className="mono">{g.cards.length}</span>
          </button>
        ))}
      </div>

      <Question />

      {current && current.cards.length > 0 ? (
        <div className="pcards" role="tabpanel">
          {current.cards.map((c) => (
            <PlaceCard key={c.id} c={c} {...cardProps} />
          ))}
        </div>
      ) : (
        <div className="empty">
          <LineArt variant="spot" />
          <p>{total ? 'Nhóm này chưa có nơi nào qua được điều kiện của bạn.' : 'Mọi nơi đều bị một giới hạn của bạn loại. Nới một giới hạn để xem thêm?'}</p>
          <button className="btn btn--ghost" onClick={() => navigate('/app/understand')}>
            Xem lại giới hạn
          </button>
        </div>
      )}

      {pairs.map(([a, b]) => (
        <p className="sl-pair" key={a.id + b.id}>
          <span>
            <b>{a.name}</b> và <b>{b.name}</b> khá giống nhau, có lẽ bạn chỉ cần một.
          </span>
          <button className="btn btn--small btn--ghost" onClick={() => navigate(`/app/compare/${a.id},${b.id}`)}>
            So sánh
          </button>
        </p>
      ))}

      {view.excluded.by_rule.map((r) => (
        <div className="notice notice--rule" key={r.rule}>
          <Icon name="lock" size={16} />
          <span>
            {r.label} đã loại {r.count} nơi.
          </span>
          <button className="link" onClick={() => navigate('/app/understand')}>
            Xem giới hạn này
          </button>
        </div>
      ))}

      {view.unverified.count > 0 && (
        <details className="sl-extra" open={view.unverified.open}>
          <summary>
            <Icon name="info" size={16} /> {view.unverified.count} nơi chưa xác minh được điều kiện của bạn
          </summary>
          <p className="hint">Chưa đủ bằng chứng để nói các nơi này hợp với điều kiện bạn đặt. Tự kiểm tra trước nếu muốn chọn.</p>
          <div className="pcards">
            {view.unverified.cards.map((c) => (
              <PlaceCard key={c.id} c={c} {...cardProps} />
            ))}
          </div>
        </details>
      )}

      {view.unmapped.length > 0 && (
        <p className="notice notice--soft">
          <Icon name="info" size={16} /> Chưa kiểm được bằng dữ liệu: {view.unmapped.join(', ')}. Mình chỉ nêu trong lời giải thích, không dùng để chọn.
        </p>
      )}

      <div className="sl-talk">
        <Chat />
        <WhyNotBox />
      </div>

      {compare.length >= 2 && (
        <button className="sl-fab" onClick={() => navigate(`/app/compare/${compare.join(',')}`)}>
          <Icon name="compare" /> So sánh {compare.length} nơi
        </button>
      )}

      <Sheet open={!!dropping} onClose={() => setDropping(null)} label="Bỏ địa điểm">
        {dropping && (
          <div className="dropwhy">
            <h2>Bỏ {dropping.name}?</h2>
            <p className="hint">Cho mình biết lý do để gợi ý sau sát hơn. Không bắt buộc.</p>
            <div className="chips">
              {(Object.keys(DROP_LABEL) as DropReason[]).map((r) => (
                <button
                  key={r}
                  type="button"
                  className="chip"
                  onClick={() => {
                    act({ type: 'drop', place_id: dropping.id, reason: r })
                    setDropping(null)
                  }}
                >
                  {DROP_LABEL[r]}
                </button>
              ))}
            </div>
            <button
              className="btn btn--ghost"
              disabled={busy}
              onClick={() => {
                act({ type: 'drop', place_id: dropping.id })
                setDropping(null)
              }}
            >
              Bỏ, không cần lý do
            </button>
          </div>
        )}
      </Sheet>
    </Page>
  )
}

// Places in the same tab that name each other as alternatives: shown as a pair, not twice.
function similarPairs(cards: Card[]) {
  const ids = new Map(cards.map((c) => [c.id, c]))
  const seen = new Set<string>()
  const out: [Card, Card][] = []
  for (const c of cards)
    for (const a of c.alternatives) {
      const other = ids.get(a.id)
      const key = [c.id, a.id].sort().join()
      if (other && !seen.has(key)) {
        seen.add(key)
        out.push([c, other])
      }
    }
  return out.slice(0, 3)
}

// The one question the rules opened (pattern, free time, rethink): one line, skippable.
function Question() {
  const { view, act, busy } = useDecision()
  const q = view?.pending
  if (!q) return null
  return (
    <section className="sl-ask" aria-live="polite">
      <div>
        <h2>{q.text}</h2>
        <p className="q__why">Vì sao hỏi: {q.reason}</p>
      </div>
      <div className="chips">
        {q.chips.map((c) => (
          <button key={c.id} type="button" className="chip" disabled={busy} onClick={() => act({ type: 'answer', qid: q.qid, chip: c.id })}>
            {c.label}
          </button>
        ))}
      </div>
    </section>
  )
}

function Chat() {
  const { say, busy } = useDecision()
  const [text, setText] = useState('')
  const [reply, setReply] = useState<string | null>(null)
  const send = async (e: FormEvent) => {
    e.preventDefault()
    const t = text.trim()
    if (!t || busy) return
    setText('')
    setReply('')
    await say(t, setReply)
  }
  return (
    <section className="sl-chat">
      <form onSubmit={send}>
        <label className="sl-label" htmlFor="pdchat">
          Nói với mình
        </label>
        <div className="lineinput">
          <input id="pdchat" value={text} maxLength={1000} onChange={(e) => setText(e.target.value)} placeholder="ví dụ: quán này xa quá, hay: muốn chỗ ít người hơn" />
          <kbd>Enter để gửi</kbd>
        </div>
      </form>
      {reply !== null && (
        <p className="ask__remark" aria-live="polite">
          {reply || '…'}
        </p>
      )}
    </section>
  )
}

function WhyNotBox() {
  const { trip } = useTrip()
  const [q, setQ] = useState('')
  const [res, setRes] = useState<WhyNot | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const ask = async (e: FormEvent) => {
    e.preventDefault()
    if (!q.trim() || !trip.decisionId) return
    setRes(null)
    setMsg(null)
    try {
      const hits = await searchPlaces(q.trim())
      if (!hits.length) return setMsg('Không tìm thấy nơi này trong dữ liệu.')
      setRes(await whyNot(trip.decisionId, hits[0].id))
    } catch {
      setMsg('Chưa tra được, thử lại sau.')
    }
  }
  return (
    <section className="sl-whynot">
      <form onSubmit={ask}>
        <label className="sl-label" htmlFor="whynot">
          Vì sao không thấy một nơi?
        </label>
        <div className="lineinput">
          <input id="whynot" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Tên địa điểm" />
          <button className="link">Tra</button>
        </div>
      </form>
      {msg && <p className="hint">{msg}</p>}
      {res && (
        <div className="sl-whynot__res">
          <b>{res.name ?? q}</b>
          <ul>
            {res.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

export function PlaceCard({ c, comparing, onCompare, onDrop }: { c: Card; comparing: string[]; onCompare: (id: string) => void; onDrop: (c: Card) => void }) {
  const { act, busy } = useDecision()
  const p = placeById(c.id) // clips and evidence quotes come from the snapshot when it has this place
  const add = (e: React.MouseEvent) => {
    act({ type: 'select', place_id: c.id })
    flyToTray(e.currentTarget as HTMLElement)
  }
  const notes = [...c.failed.map((t) => `Không hợp điều kiện của bạn: ${t}`), ...c.unverified, ...c.warnings]
  const low = c.confidence.level === 'low'
  const states = [c.chosen && 'is-chosen', c.locked && 'is-locked', comparing.includes(c.id) && 'is-comparing', c.status === 'unverified' && 'is-unverified', low && 'is-low']
    .filter(Boolean)
    .join(' ')

  return (
    <article className={`pcard ${states}`}>
      <button className="pcard__cover" onClick={() => navigate(placeLink(c.id))} aria-label={`Xem chi tiết ${c.name}`}>
        <PlaceCover id={c.id} fallback={<LineArt variant="spot" seed={c.name.length} />} />
        {c.locked && (
          <span className="pcard__flag">
            <Icon name="lock" size={13} /> Đã khóa
          </span>
        )}
        {c.chosen && !c.locked && (
          <span className="pcard__flag">
            <Icon name="check" size={13} /> Đã chọn
          </span>
        )}
      </button>

      <header className="pcard__head">
        <h3>
          <a
            href={placeLink(c.id)}
            onClick={(e) => {
              e.preventDefault()
              navigate(placeLink(c.id))
            }}
          >
            {c.name}
          </a>
        </h3>
        <p>{[c.category, p ? area(p) : null].filter(Boolean).join(' · ')}</p>
        {c.suggested && <span className="pcard__tag">Gợi ý thêm</span>}
      </header>

      <div className="pcard__two">
        <div>
          <h4>Vì sao phù hợp</h4>
          {c.why.length ? (
            <ul className="pcard__why">
              {c.why.map((w) => (
                <ClaimRow key={w.text} claim={w} place={p} tone="why" />
              ))}
            </ul>
          ) : (
            <p className="unknown">Chưa có lý do rõ</p>
          )}
        </div>
        <div>
          <h4>Đánh đổi</h4>
          {c.tradeoffs.length || notes.length || c.depends_on_unknown ? (
            <ul className="pcard__cost">
              {c.tradeoffs.map((w) => (
                <ClaimRow key={w.text} claim={w} place={p} tone="cost" />
              ))}
              {[...notes, ...(c.depends_on_unknown ? [c.depends_on_unknown] : [])].map((t) => (
                <li key={t}>
                  <Icon name="alert" size={14} /> <span>{t}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="unknown">Chưa thấy điều gì đáng ngại</p>
          )}
        </div>
      </div>

      <div className="pcard__facts">
        {c.visit ? (
          <span className="mono" title="Ước tính">
            <Icon name="clock" size={15} /> {c.visit.short}–{c.visit.long} phút
          </span>
        ) : (
          <span className="unknown">Chưa có thời lượng</span>
        )}
        <ConfidenceTag level={CONF[c.confidence.level]} reason={c.confidence.reason + (c.declined ? ' Có dấu hiệu xuống cấp gần đây.' : '')} />
      </div>
      {c.location.minutes !== null && (
        <p className="pcard__where mono">
          <Icon name="route" size={14} /> ≈{c.location.minutes} phút từ {c.location.center}
          {c.price ? ` · ${c.price}` : ''}
        </p>
      )}

      <footer className="pcard__actions">
        {c.chosen ? (
          <button className="btn btn--small btn--chosen" disabled={busy} onClick={() => onDrop(c)} title="Bỏ khỏi danh sách đã chọn">
            <Icon name="check" size={15} /> Đã chọn
          </button>
        ) : (
          <button className="btn btn--small" disabled={busy} onClick={add}>
            <Icon name="plus" size={15} /> Thêm
          </button>
        )}
        <span className="pcard__links">
          {!c.chosen && (
            <button className="link" onClick={() => onDrop(c)}>
              Bỏ
            </button>
          )}
          <button className="link" aria-pressed={c.locked} disabled={busy} title="Khóa: không bao giờ bị bỏ tự động" onClick={() => act({ type: c.locked ? 'unlock' : 'lock', place_id: c.id })}>
            {c.locked ? 'Mở khóa' : 'Khóa'}
          </button>
          <button className="link" aria-pressed={comparing.includes(c.id)} onClick={() => onCompare(c.id)}>
            {comparing.includes(c.id) ? 'Bỏ so sánh' : 'So sánh'}
          </button>
          <button className="link" onClick={() => navigate(placeLink(c.id))}>
            Chi tiết
          </button>
        </span>
      </footer>
    </article>
  )
}

// Each claim opens its own evidence when the snapshot has it: sample size, agreement, one quote (UX brief §3.3).
function ClaimRow({ claim, place, tone }: { claim: Claim; place: Place | undefined; tone: 'why' | 'cost' }) {
  const [open, setOpen] = useState(false)
  const s = claim.sid && place ? signal(place, claim.sid) : undefined
  const icon = <Icon name={tone === 'why' ? 'check' : 'alert'} size={14} />
  if (!s || !place)
    return (
      <li>
        {icon} <span>{claim.text}</span>
      </li>
    )
  return (
    <li className="claim">
      {icon}
      <span>
        <button className="claim__btn" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          {claim.text}
        </button>
        {open && (
          <span className="claim__ev">
            <small className="mono">
              {Math.round(s.agreement * 100)}% trong {s.n} người nhắc{s.freshnessDays !== null ? ` · mới nhất ${s.freshnessDays} ngày trước` : ''}
            </small>
            {s.quotes[0] && <q>{s.quotes[0].text}</q>}
            <button className="link" onClick={() => navigate(placeLink(place.id))}>
              Xem đủ bằng chứng
            </button>
          </span>
        )}
      </span>
    </li>
  )
}

// A small rose diamond arcs from the button into the curation bar.
export function flyToTray(from: HTMLElement) {
  if (story.reducedMotion) return
  const target = document.querySelector('.curate__count')
  const a = from.getBoundingClientRect()
  const gem = document.createElement('i')
  gem.className = 'gem'
  document.body.appendChild(gem)
  const b = target?.getBoundingClientRect() ?? { left: innerWidth / 2, top: innerHeight - 40, width: 0, height: 0 }
  gsap.set(gem, { x: a.left + a.width / 2, y: a.top + a.height / 2, scale: 0.6, rotate: 45 })
  gsap
    .timeline({ onComplete: () => gem.remove() })
    .to(gem, { x: b.left + b.width / 2, duration: 0.7, ease: 'power1.inOut' }, 0)
    .to(gem, { y: Math.min(a.top, b.top) - 80, duration: 0.35, ease: 'power2.out' }, 0)
    .to(gem, { y: b.top + b.height / 2, duration: 0.35, ease: 'power2.in' }, 0.35)
    .to(gem, { scale: 1.1, rotate: 225, duration: 0.7 }, 0)
    .to(gem, { scale: 0, opacity: 0, duration: 0.2 }, 0.65)
}
