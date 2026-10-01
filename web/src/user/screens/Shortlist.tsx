import gsap from 'gsap'
import { useMemo, useRef, useState, type PointerEvent } from 'react'
import { featureLabel } from '../../data/labels'
import { SECTION_LABEL, signal, useSnapshot, type Section } from '../../data/store'
import type { Place } from '../../data/types'
import { navigate } from '../../router'
import { story } from '../../scene/story'
import { Chip, ConfidenceTag, Icon, Page, SectionArt, Sheet } from '../../ui/bits'
import { buildShortlist, keepPick, sharedTraits, similarGroups, type Candidate, type Claim } from '../planner'
import { area } from '../search'
import { DROP_LABEL, useTrip, type DropReason } from '../trip'

const ORDER: Section[] = ['nature', 'sight', 'food', 'shop']

export function Shortlist() {
  const { snap } = useSnapshot()
  const { trip, dispatch } = useTrip()
  const list = useMemo(() => buildShortlist(snap!.places, trip), [snap, trip])
  const [tab, setTab] = useState<Section>(() => ORDER.find((s) => list.bySection[s].length) ?? 'nature')
  const [compare, setCompare] = useState<string[]>([])
  const [dropping, setDropping] = useState<Candidate | null>(null)
  const [showExtra, setShowExtra] = useState(false)
  const cands = list.bySection[tab]
  const groups = useMemo(() => similarGroups(cands), [cands])
  const grouped = new Set(groups.flat().map((c) => c.place.id))

  const toggleCompare = (id: string) => setCompare((c) => (c.includes(id) ? c.filter((x) => x !== id) : c.length >= 3 ? c : [...c, id]))

  return (
    <Page className="page--wide">
      <header className="phead phead--split">
        <div>
          <h1>Gợi ý cho chuyến của bạn</h1>
          <p>Một tập nhỏ đáng cân nhắc, kèm lý do và cái giá phải đánh đổi. Bạn chốt, mình không chọn thay.</p>
        </div>
      </header>

      <div className="tabs" role="tablist" aria-label="Nhóm địa điểm">
        {ORDER.map((s) => (
          <button key={s} role="tab" aria-selected={tab === s} className={tab === s ? 'is-on' : ''} onClick={() => setTab(s)}>
            <SectionArt section={s} />
            <span className="tabs__label">{SECTION_LABEL[s]}</span>
            <span className="tabs__n">{list.bySection[s].length}</span>
          </button>
        ))}
      </div>

      {list.excludedByRule.map((r) => (
        <div className="notice" key={r.rule}>
          <Icon name="lock" size={16} />
          <span>
            Quy tắc “{r.rule}” đã loại {r.count} nơi.
          </span>
          <button className="link" onClick={() => dispatch({ type: 'relax', key: 'avoidSteep' })}>
            Nới quy tắc này
          </button>
        </div>
      ))}

      {cands.length === 0 ? (
        <div className="empty">
          <img src="/img/empty.webp" alt="" />
          <p>Nhóm này chưa có nơi nào đủ bằng chứng trải nghiệm để gợi ý.</p>
          {list.extra[tab].length > 0 && (
            <button className="link" onClick={() => setShowExtra(true)}>
              Xem {list.extra[tab].length} nơi chỉ có thông tin cơ bản
            </button>
          )}
        </div>
      ) : (
        <>
          {cands.length < 3 && <p className="notice notice--soft">Nhóm này ít lựa chọn vì dữ liệu trải nghiệm còn mỏng. Nới một giới hạn có thể giúp.</p>}
          {groups.map((g) => {
            const pick = keepPick(g)
            return (
              <div className="similar" key={g.map((c) => c.place.id).join()}>
                <p className="similar__head">
                  <Icon name="layers" size={16} />
                  {g.length === 2 ? 'Hai nơi này' : `${g.length} nơi này`} đều là {g[0].place.category?.toLowerCase()}
                  {sharedTraits(g).length ? `, cùng ${sharedTraits(g).map((t) => featureLabel(t).toLowerCase()).join(' và ')}` : ''}. Có lẽ bạn chỉ cần một.
                </p>
                <p className="similar__keep">
                  <span>
                    <b>Nên giữ {pick.keep.place.name}:</b> {pick.reason}.
                  </span>
                  <button className="link" onClick={() => navigate(`/app/compare/${g.map((c) => c.place.id).join(',')}`)}>
                    So sánh chi tiết
                  </button>
                </p>
                <div className="cards cards--group">
                  {[pick.keep, ...g.filter((c) => c !== pick.keep)].map((c) => (
                    <PlaceCard key={c.place.id} c={c} keep={c === pick.keep} comparing={compare.includes(c.place.id)} onCompare={toggleCompare} onDrop={setDropping} />
                  ))}
                </div>
              </div>
            )
          })}
          <div className="cards">
            {cands
              .filter((c) => !grouped.has(c.place.id))
              .map((c) => (
                <PlaceCard key={c.place.id} c={c} comparing={compare.includes(c.place.id)} onCompare={toggleCompare} onDrop={setDropping} />
              ))}
          </div>
        </>
      )}

      {list.extra[tab].length > 0 && cands.length > 0 && (
        <details className="extra" open={showExtra} onToggle={(e) => setShowExtra((e.target as HTMLDetailsElement).open)}>
          <summary>Thêm {list.extra[tab].length} nơi chỉ có thông tin cơ bản từ Google</summary>
          <p className="block__hint">Chưa có bằng chứng trải nghiệm, nên mình không gợi ý chúng như một trải nghiệm. Dùng được làm chỗ ăn hoặc phương án dự phòng.</p>
          <div className="cards">
            {list.extra[tab].map((c) => (
              <PlaceCard key={c.place.id} c={c} comparing={compare.includes(c.place.id)} onCompare={toggleCompare} onDrop={setDropping} />
            ))}
          </div>
        </details>
      )}

      {compare.length >= 2 && (
        <button className="fab" onClick={() => navigate(`/app/compare/${compare.join(',')}`)}>
          <Icon name="compare" /> So sánh {compare.length} nơi
        </button>
      )}

      <Sheet open={!!dropping} onClose={() => setDropping(null)} label="Bỏ địa điểm">
        {dropping && (
          <div className="dropwhy">
            <h2>Bỏ {dropping.place.name}?</h2>
            <p className="block__hint">Cho mình biết lý do để gợi ý sau sát hơn. Không bắt buộc.</p>
            <div className="chips">
              {(Object.keys(DROP_LABEL) as DropReason[]).map((r) => (
                <Chip
                  key={r}
                  onClick={() => {
                    dispatch({ type: 'unselect', id: dropping.place.id, reason: r })
                    setDropping(null)
                  }}
                >
                  {DROP_LABEL[r]}
                </Chip>
              ))}
            </div>
            <button
              className="btn btn--ghost"
              onClick={() => {
                dispatch({ type: 'unselect', id: dropping.place.id })
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

export function PlaceCard({
  c,
  keep,
  comparing,
  onCompare,
  onDrop,
}: {
  c: Candidate
  keep?: boolean
  comparing: boolean
  onCompare: (id: string) => void
  onDrop: (c: Candidate) => void
}) {
  const { trip, dispatch } = useTrip()
  const ref = useRef<HTMLElement>(null)
  const p = c.place
  const chosen = trip.selected.includes(p.id)
  const locked = trip.locked.includes(p.id)

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
    dispatch({ type: 'select', id: p.id })
    flyToTray(e.currentTarget as HTMLElement)
  }

  return (
    <article ref={ref} className={`pcard${chosen ? ' is-chosen' : ''}${p.kind === 'inventory' ? ' is-basic' : ''}`} onPointerMove={tilt} onPointerLeave={untilt}>
      <header className="pcard__head">
        <button className="pcard__name" onClick={() => navigate(`/app/place/${encodeURIComponent(p.id)}`)}>
          {p.name}
        </button>
        <span className="pcard__meta">
          {p.category}
          {area(p) ? `, ${area(p)}` : ''}
        </span>
        {keep && <span className="pcard__keep">Nên giữ</span>}
        {locked && (
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
      {p.kind === 'inventory' && <p className="pcard__basic">Chỉ có thông tin cơ bản, chưa có bằng chứng trải nghiệm.</p>}

      <div className="pcard__facts">
        <span title="Ước tính">
          <Icon name="clock" size={14} /> {c.visit[0]}–{c.visit[1]} phút
        </span>
        {c.fromAnchor < 25 && (
          <span title="Ước tính">
            <Icon name="route" size={14} /> ≈{c.fromAnchor} phút đi
          </span>
        )}
        {p.videos.length > 0 && (
          <span>
            <Icon name="play" size={14} /> {p.videos.length} clip
          </span>
        )}
      </div>
      <ConfidenceTag level={c.confidence.level} reason={c.confidence.reason} />

      <footer className="pcard__actions">
        {chosen ? (
          <button className="btn btn--small btn--chosen" onClick={() => onDrop(c)}>
            <Icon name="check" size={16} /> Đã chọn
          </button>
        ) : (
          <button className="btn btn--small" onClick={add}>
            <Icon name="plus" size={16} /> Thêm
          </button>
        )}
        <button className={`tbtn${locked ? ' is-on' : ''}`} aria-pressed={locked} title="Khóa: không bao giờ bị bỏ tự động" onClick={() => dispatch({ type: 'lock', id: p.id })}>
          <Icon name={locked ? 'lock' : 'unlock'} size={15} /> {locked ? 'Đã khóa' : 'Khóa'}
        </button>
        <button className={`tbtn${comparing ? ' is-on' : ''}`} aria-pressed={comparing} onClick={() => onCompare(p.id)}>
          <Icon name="compare" size={15} /> So sánh
        </button>
        {!chosen && (
          <button className="tbtn" onClick={() => onDrop(c)}>
            <Icon name="x" size={15} /> Không quan tâm
          </button>
        )}
        <button className="link pcard__more" onClick={() => navigate(`/app/place/${encodeURIComponent(p.id)}`)}>
          Xem bằng chứng
        </button>
      </footer>
    </article>
  )
}

// Each claim opens its own evidence: sample size, agreement, one quote (UX brief §3.3).
function ClaimRow({ claim, place, icon }: { claim: Claim; place: Place; icon: string }) {
  const [open, setOpen] = useState(false)
  const s = claim.sid ? signal(place, claim.sid) : undefined
  if (!s)
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
