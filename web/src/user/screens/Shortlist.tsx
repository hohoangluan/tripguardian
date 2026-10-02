import gsap from 'gsap'
import { useRef, useState, type FormEvent, type PointerEvent } from 'react'
import { placeById, signal } from '../../data/store'
import type { Place } from '../../data/types'
import { navigate } from '../../router'
import { story } from '../../scene/story'
import { Chip, ClipCover, ConfidenceTag, Icon, Page, SectionArt, Sheet } from '../../ui/bits'
import { whyNot } from '../pd/api'
import { useDecision } from '../pd/decision'
import type { Card, Claim, DropReason, WhyNot } from '../pd/types'
import { searchPlaces } from '../tu/api'
import { DROP_LABEL, useTrip } from '../trip'

const ART: Record<string, 'sight' | 'nature' | 'food' | 'shop'> = { anchors: 'sight', nature: 'nature', sights: 'sight', chill: 'food', meal: 'food' }
export const CONF = { high: 'Cao', medium: 'Trung bình', low: 'Thấp' } as const

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
          <img src="/img/empty.webp" alt="" />
          <p>{error ?? 'Chưa có gợi ý. Bắt đầu từ bước hiểu chuyến đi.'}</p>
          <button className="btn" onClick={() => navigate('/app/understand')}>
            Hiểu chuyến đi
          </button>
        </div>
      </Page>
    )
  if (!view)
    return (
      <div className="loading" role="status">
        {error ?? 'Đang chuẩn bị gợi ý'}
      </div>
    )

  const anchors = view.groups.find((g) => g.id === 'anchors')
  const groups = view.groups.filter((g) => g.id !== 'anchors')
  const current = groups.find((g) => g.id === tab) ?? groups[0]
  const toggleCompare = (id: string) =>
    setCompare((c) => (c.includes(id) ? c.filter((x) => x !== id) : c.length >= 2 ? [c[1], id] : [...c, id]))
  const cardProps = { comparing: compare, onCompare: toggleCompare, onDrop: setDropping }

  return (
    <Page className="page--wide">
      <header className="phead phead--split">
        <div>
          <h1>Gợi ý cho chuyến của bạn</h1>
          <p>Một tập nhỏ đáng cân nhắc, kèm lý do và cái giá phải đánh đổi. Bạn chốt, mình không chọn thay.</p>
        </div>
      </header>

      {error && (
        <p className="notice" role="alert">
          <Icon name="alert" size={16} /> {error}
        </p>
      )}
      <Question />

      {anchors && (
        <section className="block">
          <h2 className="block__title">{anchors.label}</h2>
          <div className="cards">
            {anchors.cards.map((c) => (
              <PlaceCard key={c.id} c={c} {...cardProps} />
            ))}
          </div>
        </section>
      )}

      <div className="tabs" role="tablist" aria-label="Nhóm địa điểm">
        {groups.map((g) => (
          <button key={g.id} role="tab" aria-selected={current?.id === g.id} className={current?.id === g.id ? 'is-on' : ''} onClick={() => setTab(g.id)}>
            <SectionArt section={ART[g.id] ?? 'sight'} />
            <span className="tabs__label">{g.label}</span>
            <span className="tabs__n">{g.cards.length}</span>
          </button>
        ))}
      </div>

      {view.excluded.by_rule.map((r) => (
        <div className="notice" key={r.rule}>
          <Icon name="lock" size={16} />
          <span>
            {r.label} đã loại {r.count} nơi.
          </span>
        </div>
      ))}

      {current ? (
        <div className="cards">
          {current.cards.map((c) => (
            <PlaceCard key={c.id} c={c} {...cardProps} />
          ))}
        </div>
      ) : (
        <div className="empty">
          <img src="/img/empty.webp" alt="" />
          <p>Chưa có nơi nào qua được điều kiện của bạn.</p>
        </div>
      )}

      {view.unverified.count > 0 && (
        <details className="extra" open={view.unverified.open}>
          <summary>{view.unverified.count} nơi chưa xác minh được điều kiện của bạn</summary>
          <p className="block__hint">Chưa đủ bằng chứng để nói các nơi này hợp với điều kiện bạn đặt. Tự kiểm tra trước nếu muốn chọn.</p>
          <div className="cards">
            {view.unverified.cards.map((c) => (
              <PlaceCard key={c.id} c={c} {...cardProps} />
            ))}
          </div>
        </details>
      )}

      {view.unmapped.length > 0 && <p className="notice notice--soft">Chưa kiểm được trong dữ liệu: {view.unmapped.join(', ')}.</p>}
      <WhyNotBox />
      <Chat />

      {compare.length === 2 && (
        <button className="fab" onClick={() => navigate(`/app/compare/${compare.join(',')}`)}>
          <Icon name="compare" /> So sánh 2 nơi
        </button>
      )}

      <Sheet open={!!dropping} onClose={() => setDropping(null)} label="Bỏ địa điểm">
        {dropping && (
          <div className="dropwhy">
            <h2>Bỏ {dropping.name}?</h2>
            <p className="block__hint">Cho mình biết lý do để gợi ý sau sát hơn. Không bắt buộc.</p>
            <div className="chips">
              {(Object.keys(DROP_LABEL) as DropReason[]).map((r) => (
                <Chip
                  key={r}
                  onClick={() => {
                    act({ type: 'drop', place_id: dropping.id, reason: r })
                    setDropping(null)
                  }}
                >
                  {DROP_LABEL[r]}
                </Chip>
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

// The one question the rules opened (pattern, free time, rethink); the user answers with a chip.
function Question() {
  const { view, act, busy } = useDecision()
  const q = view?.pending
  if (!q) return null
  return (
    <section className="followup" aria-live="polite">
      <p className="bubble bubble--q">{q.text}</p>
      <p className="block__hint">{q.reason}</p>
      <div className="chips">
        {q.chips.map((c) => (
          <Chip key={c.id} onClick={() => !busy && act({ type: 'answer', qid: q.qid, chip: c.id })}>
            {c.label}
          </Chip>
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
    <section className="pdchat">
      <form onSubmit={send}>
        <label className="pdchat__label" htmlFor="pdchat">
          Nói với mình, ví dụ “quán này xa quá” hay “muốn chỗ ít người hơn”
        </label>
        <div className="pdchat__row">
          <input id="pdchat" value={text} maxLength={1000} onChange={(e) => setText(e.target.value)} placeholder="Gõ ở đây" />
          <button className="btn btn--small" disabled={busy || !text.trim()}>
            Gửi
          </button>
        </div>
      </form>
      {reply !== null && (
        <p className="bubble bubble--a" aria-live="polite">
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
    <details className="extra whynot">
      <summary>Vì sao không thấy một nơi?</summary>
      <form onSubmit={ask} className="pdchat__row">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Tên địa điểm" aria-label="Tên địa điểm" />
        <button className="btn btn--small btn--ghost">Tra</button>
      </form>
      {msg && <p className="block__hint">{msg}</p>}
      {res && (
        <div>
          <b>{res.name ?? q}</b>
          <ul>
            {res.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
      )}
    </details>
  )
}

export function PlaceCard({ c, comparing, onCompare, onDrop }: { c: Card; comparing: string[]; onCompare: (id: string) => void; onDrop: (c: Card) => void }) {
  const { act, busy } = useDecision()
  const ref = useRef<HTMLElement>(null)
  const p = placeById(c.id) // clips and evidence quotes come from the snapshot when it has this place

  // A soft 3D tilt under the pointer; off for touch and reduced motion.
  const tilt = (e: PointerEvent) => {
    if (e.pointerType !== 'mouse' || story.reducedMotion || !ref.current) return
    const r = ref.current.getBoundingClientRect()
    const x = (e.clientX - r.left) / r.width - 0.5
    const y = (e.clientY - r.top) / r.height - 0.5
    gsap.to(ref.current, { rotateY: x * 7, rotateX: -y * 7, duration: 0.4, ease: 'power2.out' })
  }
  const untilt = () => ref.current && gsap.to(ref.current, { rotateX: 0, rotateY: 0, duration: 0.6, ease: 'power3.out' })
  const add = (e: React.MouseEvent) => {
    act({ type: 'select', place_id: c.id })
    flyToTray(e.currentTarget as HTMLElement)
  }
  const notes = [...c.failed.map((t) => `Không hợp điều kiện của bạn: ${t}`), ...c.unverified, ...c.warnings]

  return (
    <article ref={ref} className={`pcard${c.chosen ? ' is-chosen' : ''}`} onPointerMove={tilt} onPointerLeave={untilt}>
      {p && p.videos.length > 0 && <ClipCover videos={p.videos} />}
      <header className="pcard__head">
        <button className="pcard__name" onClick={() => navigate(`/app/place/${encodeURIComponent(c.id)}`)}>
          {c.name}
        </button>
        <span className="pcard__meta">{c.category}</span>
        {c.suggested && <span className="pcard__keep">Gợi ý thêm</span>}
        {c.locked && (
          <span className="pcard__lock" title="Đã khóa">
            <Icon name="lock" size={14} />
          </span>
        )}
      </header>

      {c.why.length > 0 && (
        <ul className="pcard__why" aria-label="Vì sao phù hợp">
          {c.why.map((w) => (
            <ClaimRow key={w.text} claim={w} place={p} icon="check" />
          ))}
        </ul>
      )}
      {c.tradeoffs.length > 0 && (
        <ul className="pcard__cost" aria-label="Đánh đổi">
          {c.tradeoffs.map((w) => (
            <ClaimRow key={w.text} claim={w} place={p} icon="alert" />
          ))}
        </ul>
      )}
      {notes.map((t) => (
        <p key={t} className="pcard__basic">
          {t}
        </p>
      ))}
      {c.depends_on_unknown && <p className="pcard__basic">{c.depends_on_unknown}</p>}

      <div className="pcard__facts">
        {c.visit && (
          <span title="Ước tính">
            <Icon name="clock" size={14} /> {c.visit.short}–{c.visit.long} phút
          </span>
        )}
        {c.location.minutes !== null && (
          <span title="Ước tính">
            <Icon name="route" size={14} /> ≈{c.location.minutes} phút từ {c.location.center}
          </span>
        )}
        {c.price && <span>{c.price}</span>}
      </div>
      <ConfidenceTag level={CONF[c.confidence.level]} reason={c.confidence.reason + (c.declined ? ' Có dấu hiệu xuống cấp gần đây.' : '')} />

      {c.alternatives.length > 0 && (
        <p className="pcard__alts">
          Nơi tương tự:{' '}
          {c.alternatives.map((a) => (
            <button
              key={a.id}
              className="link"
              disabled={busy}
              title={c.chosen ? `Đổi sang ${a.name}` : `Xem ${a.name}`}
              onClick={() => (c.chosen ? act({ type: 'swap', place_id: c.id, with_id: a.id }) : navigate(`/app/place/${encodeURIComponent(a.id)}`))}
            >
              {a.name}
            </button>
          ))}
        </p>
      )}

      <div className="pcard__tools">
        <button className={`tbtn${c.locked ? ' is-on' : ''}`} aria-pressed={c.locked} title="Khóa: không bao giờ bị bỏ tự động" disabled={busy} onClick={() => act({ type: c.locked ? 'unlock' : 'lock', place_id: c.id })}>
          <Icon name={c.locked ? 'lock' : 'unlock'} size={15} /> {c.locked ? 'Đã khóa' : 'Khóa'}
        </button>
        <button className={`tbtn${comparing.includes(c.id) ? ' is-on' : ''}`} aria-pressed={comparing.includes(c.id)} onClick={() => onCompare(c.id)}>
          <Icon name="compare" size={15} /> So sánh
        </button>
        {!c.chosen && (
          <button className="tbtn" onClick={() => onDrop(c)}>
            <Icon name="x" size={15} /> Bỏ qua
          </button>
        )}
      </div>

      <footer className="pcard__actions">
        {c.chosen ? (
          <button className="btn btn--small btn--chosen" disabled={busy} onClick={() => onDrop(c)}>
            <Icon name="check" size={16} /> Đã chọn
          </button>
        ) : (
          <button className="btn btn--small" disabled={busy} onClick={add}>
            <Icon name="plus" size={16} /> Thêm vào chuyến
          </button>
        )}
        {p && (
          <button className="pcard__more" onClick={() => navigate(`/app/place/${encodeURIComponent(c.id)}`)}>
            Bằng chứng <Icon name="next" size={15} />
          </button>
        )}
      </footer>
    </article>
  )
}

// Each claim opens its own evidence when the snapshot has it: sample size, agreement, one quote (UX brief §3.3).
function ClaimRow({ claim, place, icon }: { claim: Claim; place: Place | undefined; icon: string }) {
  const [open, setOpen] = useState(false)
  const s = claim.sid && place ? signal(place, claim.sid) : undefined
  if (!s || !place)
    return (
      <li>
        <Icon name={icon} size={14} /> <span>{claim.text}</span>
      </li>
    )
  return (
    <li className="claim">
      <Icon name={icon} size={14} />
      <span>
        <button className="claim__btn" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          {claim.text}
        </button>
        {open && (
          <span className="claim__ev">
            <small>
              {s.n} người nhắc, {Math.round(s.agreement * 100)}% đồng ý{s.freshnessDays !== null ? `, mới nhất ${s.freshnessDays} ngày trước` : ''}
            </small>
            {s.quotes[0] && <q>{s.quotes[0].text}</q>}
            <button className="link" onClick={() => navigate(`/app/place/${encodeURIComponent(place.id)}`)}>
              Xem đủ bằng chứng
            </button>
          </span>
        )}
      </span>
    </li>
  )
}

// A yellow diamond arcs from the button into the curation bar.
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
