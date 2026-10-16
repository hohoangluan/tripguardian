import * as Dialog from '@radix-ui/react-dialog'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { impression } from '../events'
import { useDecision } from '../pd/decision'
import type { Card, Group, SearchResult } from '../pd/types'
import { searchList } from '../pd/api'
import { requestStageEntry } from '../journey'
import { openAssistant, setUi, toggleCmp, useUi } from '../store'
import { DROP_LABEL, STEPS, useTrip, type DropReason } from '../trip'
import { placesDelta } from '../tu/labels'
import { AssistantFloat, AssistantPinned } from '../ui/Assistant'
import { ArtHills, Empty, go, PlacePhoto } from '../ui/common'
import { openPlace } from '../ui/PlaceSheet'
import { DiscPicker } from '../ui/DiscPicker'
import { Icon } from '../ui/icons'
import { PlaceCard } from '../ui/PlaceCard'
import { Pager } from '../ui/Pager'
import { SelectedBar } from '../ui/SelectedBar'
import { reducedMotion, useStagedList } from '../ui/useStagedList'
import { FlowBar, Page, useTitle } from '../ui/Shell'
import { LongTripWarning } from '../ui/LongTripWarning'
import { LODGING_TAB, LodgingPanel, useLodgingList } from './Lodging'

const NO_CARDS: Card[] = []
// Back to Hiểu chuyến đi to see or relax a limit: the journey steps back on the server (Decision keeps its picks).
export function useEditTicket() {
  const { trip } = useTrip()
  return () => {
    if (trip.journeyId) requestStageEntry(trip.journeyId, 'trip')
    go('/understand')
  }
}

export function Explore() {
  useTitle('Lựa chọn')
  const { trip } = useTrip()
  const { view, error, act, busy, reload, more, loadingMore, toPlan } = useDecision()
  const tab = useUi((u) => u.tab)
  const cmp = useUi((u) => u.cmp)
  const [dropFor, setDropFor] = useState<Card | null>(null)
  const [exOpen, setExOpen] = useState(false)
  const [mode, setMode] = useState<'grid' | 'disc'>('grid')
  const discHint = useDiscHint(mode === 'disc')
  const asst = useUi((u) => u.assistant)
  const editTicket = useEditTicket()
  const pinned = asst.open && asst.pinned
  const groups = view?.groups.filter((g) => g.id !== 'anchors' && (g.cards.length || g.total)) ?? []
  const current = groups.find((g) => g.id === tab) ?? groups[0]
  const needsLodging = Boolean(view?.lodging) // one lodging per trip: the tab is always there (to pick, or to change)
  const onLodging = needsLodging && tab === LODGING_TAB
  const lodgingList = useLodgingList(needsLodging)
  useEffect(() => { if (mode === 'grid') current?.cards.forEach((c, i) => impression(c.id, current.id, i + 1)) }, [current?.id, current?.cards.length, mode]) // eslint-disable-line react-hooks/exhaustive-deps
  const onCmp = toggleCmp
  const goCompare = (ids: string[]) => go(`/explore/compare/${ids.map(encodeURIComponent).join(',')}`)
  // The header count moved (a chat wish, an edited ticket): show by how much next to it.
  const listed = view ? view.groups.filter((g) => g.id !== 'anchors').reduce((n, g) => n + g.total, 0) : null
  const lastListed = useRef<number | null>(null)
  const [listMove, setListMove] = useState<{ key: number; delta: number } | null>(null)
  useEffect(() => {
    if (listed === null) return
    const before = lastListed.current
    lastListed.current = listed
    if (before !== null && before !== listed) setListMove({ key: Date.now(), delta: listed - before })
  }, [listed])
  // Tabs whose list changed in the last rebuild while the user looked elsewhere: "+N mới" until they open it.
  const [fresh, setFresh] = useState<Record<string, number>>({})
  const loaded = useRef(false) // the first view is no change: nothing on it is "mới"
  useEffect(() => {
    if (!view) return
    if (!loaded.current) { loaded.current = true; return }
    const ch = view.change ?? {}
    setFresh((f) => {
      const next = { ...f }
      for (const [g, c] of Object.entries(ch)) if (c.added > 0 && g !== current?.id) next[g] = c.added
      return next
    })
  }, [view?.change]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (current && fresh[current.id]) setFresh(({ [current.id]: _, ...rest }) => rest) }, [current?.id, fresh]) // eslint-disable-line react-hooks/exhaustive-deps
  const { items, replacing } = useStagedList(current?.id ?? '', current?.cards ?? NO_CARDS, current ? view?.change?.[current.id] : undefined)

  // Kept cards that moved slide from where they were (FLIP) instead of jumping.
  const gridRef = useRef<HTMLDivElement>(null)
  const rects = useRef(new Map<string, DOMRect>())
  useLayoutEffect(() => {
    const el = gridRef.current
    if (!el) return
    const cards = [...el.querySelectorAll<HTMLElement>('[data-place]')]
    if (!reducedMotion())
      cards.forEach((n) => {
        const old = rects.current.get(n.dataset.place!)
        const r = n.getBoundingClientRect()
        if (old && (Math.abs(old.left - r.left) > 2 || Math.abs(old.top - r.top) > 2))
          n.animate([{ transform: `translate(${old.left - r.left}px, ${old.top - r.top}px)` }, { transform: 'none' }], { duration: 280, easing: 'cubic-bezier(.2,.8,.2,1)' })
      })
    rects.current = new Map(cards.map((n) => [n.dataset.place!, n.getBoundingClientRect()]))
  }, [items])

  // A tab is cut into pages; the user picks one and the grid starts again from its top.
  const goPage = (n: number) => {
    if (!current) return
    void more(current.id, n).then(() => gridRef.current?.scrollIntoView({ behavior: reducedMotion() ? 'auto' : 'smooth', block: 'start' }))
  }

  // Typed words search every tab by name, kind or tab; the answer follows the list as it changes (a pick, a chat).
  const [query, setQuery] = useState('')
  const [found, setFound] = useState<SearchResult | null>(null)
  const searching = query.trim().length >= 2
  useEffect(() => {
    if (!searching || !trip.decisionId) { setFound(null); return }
    let live = true
    const t = setTimeout(() => { searchList(trip.decisionId!, query.trim()).then((r) => { if (live) setFound(r) }, () => { if (live) setFound(null) }) }, 300)
    return () => { live = false; clearTimeout(t) }
  }, [query, searching, trip.decisionId, view?.version, view?.selected.length]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!trip.decisionId)
    return (
      <>
        <FlowBar step="explore" />
        <Page narrow><Empty art={<ArtHills />} title="Chưa có gợi ý" body={error ?? 'Bắt đầu từ bước Tìm hiểu, chỉ vài câu thôi.'} action={<button type="button" className="tg-btn tg-btn--primary" onClick={() => go('/understand')}>Tìm hiểu</button>} /></Page>
      </>
    )
  if (!view)
    return (
      <>
        <FlowBar step="explore" />
        <Page>
          {error ? (
            <Empty art={<ArtHills />} title="Chưa tải được gợi ý" body={`${error} Lựa chọn của bạn vẫn còn nguyên.`} action={<button type="button" className="tg-btn tg-btn--primary" onClick={reload}><Icon name="refresh" size={18} /> Thử lại</button>} />
          ) : (
            <>
              <p className="tg-busy" role="status"><i /> Đang chuẩn bị gợi ý cho chuyến của bạn…</p>
              <div className="tg-grid" aria-busy="true">{Array.from({ length: 6 }, (_, i) => <div key={i} className="tg-skel-card"><div className="tg-skel" /><div><span className="tg-skel tg-skel-line" style={{ width: '70%' }} /><span className="tg-skel tg-skel-line" style={{ width: '90%' }} /><span className="tg-skel tg-skel-line" style={{ width: '55%' }} /></div></div>)}</div>
            </>
          )}
        </Page>
      </>
    )

  const anchors = view.groups.find((g) => g.id === 'anchors')?.cards ?? []
  const total = groups.reduce((n, g) => n + g.total, 0) + anchors.length
  const excluded = view.excluded.by_rule.reduce((n, r) => n + r.count, 0)
  const conflicted = new Set(view.feasibility.conflicts.flatMap((c) => c.places))
  const q = view.pending
  const question = q && (
    <div key="ask" className="tg-narrow" aria-live="polite">
      <b>{q.text}</b>
      {q.chips.map((c) => <button key={c.id} type="button" className="tg-chip" disabled={busy} onClick={() => act({ type: 'answer', qid: q.qid, chip: c.id })}>{c.label}</button>)}
      {q.reason && <span className="tg-faint tg-narrow__why">Vì sao hỏi: {q.reason}</span>}
    </div>
  )
  return (
    <>
      <FlowBar step="explore" onAhead={(t) => { if (t === 'plan' && view?.selected.length) void toPlan(); else go(STEPS.find((x) => x.id === t)!.path) }} />
      <Page>
        <div className={`tg-xlayout ${pinned ? 'is-pinned' : ''}`}>
          <div className="tg-xmain">
            <header className="tg-xhead">
              <div>
                <h1>Gợi ý cho chuyến của bạn</h1>
                <p>{total - anchors.length} nơi hợp với chuyến của bạn{listMove && <span key={listMove.key} className={`tg-xhead__delta tg-mono ${listMove.delta < 0 ? 'is-down' : 'is-up'}`}>{placesDelta(listMove.delta)}</span>}, xếp từ hợp nhất. <button type="button" className="tg-link" onClick={() => openAssistant(true)}>Chat để thu hẹp</button></p>
              </div>
              <div className="tg-xhead__ops">
                <div className="tg-seg" role="group" aria-label="Cách xem"><button type="button" aria-pressed={mode === 'grid'} onClick={() => setMode('grid')}><Icon name="grid" size={15} /> Lưới</button><button type="button" aria-pressed={mode === 'disc'} disabled={!groups.length} onClick={() => setMode('disc')}><Icon name="compass" size={15} /> Đĩa xoay</button></div>
                {mode === 'grid' && groups.length > 0 && !discHint.seen && (
                  <p className="tg-seghint" role="note">
                    <span>Thử <b>Đĩa xoay</b>: lăn chuột để lướt từng nơi, ảnh to và rõ hơn.</span>
                    <button type="button" onClick={() => { discHint.dismiss(); setMode('disc') }}>Xem thử</button>
                    <button type="button" className="tg-seghint__x" onClick={discHint.dismiss} aria-label="Ẩn gợi ý"><Icon name="x" size={14} /></button>
                  </p>
                )}
              </div>
            </header>

            <LongTripWarning days={view.days.length} />

            {view.excluded.by_rule.length > 0 && (
              <>
                <button type="button" className="tg-excl" aria-expanded={exOpen} onClick={() => setExOpen((v) => !v)}><Icon name="lock" size={16} /><span><b>Giới hạn của bạn đã loại {excluded} nơi.</b> Bấm để xem vì giới hạn nào.</span><Icon name="chevronDown" size={18} /></button>
                {exOpen && <ul className="tg-excl-list">{view.excluded.by_rule.map((r) => <li key={r.rule}><span>{r.label}</span><span style={{ opacity: 0.7 }}>· loại {r.count} nơi</span><button type="button" className="tg-link" onClick={editTicket}>Nới giới hạn</button></li>)}</ul>}
              </>
            )}

            {total === 0 ? (
              <Empty art={<ArtHills />} title="Giới hạn hiện tại loại hết các nơi" body="Nới một giới hạn để mình gợi ý lại; mình không tự bỏ giới hạn của bạn." action={<button type="button" className="tg-btn tg-btn--primary" onClick={editTicket}>Xem và nới giới hạn</button>} />
            ) : (
              <>
                {total - anchors.length > 0 && total - anchors.length < 4 && <div className="tg-narrow"><b>Chỉ còn {total - anchors.length} nơi hợp.</b><span className="tg-muted">Nới một giới hạn để có thêm lựa chọn?</span><button type="button" className="tg-link" onClick={editTicket}>Xem giới hạn</button></div>}
                {anchors.length > 0 && (
                  <section className="tg-req" aria-labelledby="tg-req-h">
                    <div><h2 id="tg-req-h">Nơi bắt buộc đến</h2><p>Mình xếp cả chuyến quanh các nơi này.</p></div>
                    <div className="tg-req__row">{anchors.map((c) => <button key={c.id} type="button" className="tg-req__row" onClick={(e) => openPlace(c.id, e.currentTarget.querySelector('figure'))}><PlacePhoto id={c.id} name={c.name} /><span><b>{c.name}</b><br /><small className="tg-muted">{c.area ?? c.category}</small></span></button>)}</div>
                  </section>
                )}
                {mode === 'disc' && current ? (
                  <DiscPicker groups={groups} tab={onLodging ? LODGING_TAB : current.id} onTab={(t) => setUi({ tab: t })} cmp={cmp} onCmp={onCmp} onDrop={setDropFor} onBack={() => setMode('grid')} lodging={needsLodging ? lodgingList : null} />
                ) : (
                  <>
                    <label className="tg-xsearch">
                      <Icon name="search" size={18} />
                      <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => { if (e.key === 'Escape') setQuery('') }} placeholder="Tìm theo tên hoặc loại nơi, ví dụ “bánh căn”, “chùa”, “kem”" aria-label="Tìm địa điểm trong mọi nhóm" />
                      {query && <button type="button" className="tg-xsearch__clear" aria-label="Xóa ô tìm" onClick={() => setQuery('')}><Icon name="x" size={16} /></button>}
                    </label>
                    {searching ? <SearchResults q={query.trim()} found={found} groups={groups} cmp={cmp} onCmp={onCmp} onDrop={setDropFor} pinned={pinned} conflicted={conflicted} onClear={() => setQuery('')} /> : <>
                    <div className="tg-tabs" role="tablist" aria-label="Nhóm địa điểm" onKeyDown={(e) => {
                      const i = groups.findIndex((g) => g.id === current?.id)
                      if (e.key === 'ArrowRight') setUi({ tab: groups[(i + 1) % groups.length].id })
                      if (e.key === 'ArrowLeft') setUi({ tab: groups[(i + groups.length - 1) % groups.length].id })
                    }}>
                      {groups.map((g) => { const on = !onLodging && current?.id === g.id; return <button key={g.id} type="button" role="tab" aria-selected={on} tabIndex={on ? 0 : -1} className="tg-tab" onClick={() => setUi({ tab: g.id })}>{g.label}<b>{g.total}</b>{fresh[g.id] ? <i className="tg-tab__new" aria-label={`${fresh[g.id]} nơi mới`}>+{fresh[g.id]} mới</i> : null}</button> })}
                      {needsLodging && <button type="button" role="tab" aria-selected={onLodging} tabIndex={onLodging ? 0 : -1} className="tg-tab" onClick={() => setUi({ tab: LODGING_TAB })}><Icon name="bed" size={15} /> Nơi lưu trú{lodgingList.opts?.total ? <b>{lodgingList.opts.total}</b> : lodgingList.failed ? null : <b className="tg-tab__wait" aria-label="Đang đếm"><i /></b>}{view.lodging?.chosen || view.lodging?.booked ? <Icon name="check" size={14} /> : null}</button>}
                    </div>
                    {onLodging ? <LodgingPanel list={lodgingList} /> : !current || current.cards.length === 0 ? (
                      <>
                        {question}
                        <Empty art={<ArtHills />} title="Chưa có nơi nào ở nhóm này" body="Thử nhóm khác, hoặc nới giới hạn để có thêm lựa chọn." />
                      </>
                    ) : (
                      <div ref={gridRef} className={`tg-grid ${pinned ? 'is-two' : ''} ${replacing ? 'is-replacing' : ''}`} key={current.id}>
                        {items.flatMap(({ card: c, phase, i: order }, i) => {
                          const out = [<PlaceCard key={c.id} c={c} phase={phase} order={order} onDrop={setDropFor} cmp={cmp.includes(c.id)} onCmp={onCmp} warn={conflicted.has(c.id) ? 'Đang vướng một chỗ cần chú ý' : undefined} />]
                          if (i === Math.min(4, items.length - 1) && question) out.push(question)
                          return out
                        })}
                      </div>
                    )}
                    {!onLodging && current && current.cards.length > 0 && <Pager label={current.label} total={current.total} page={current.page ?? 0} pages={current.pages ?? 1} from={(current.offset ?? 0) + 1} to={(current.offset ?? 0) + current.cards.length} busy={loadingMore === current.id} onPage={goPage} />}
                    </>}
                  </>
                )}
                {view.unverified.count > 0 && (
                  <details className="tg-unverified" open={view.unverified.open}>
                    <summary><Icon name="info" size={16} /> Chưa xác minh được điều kiện của bạn ({view.unverified.count})</summary>
                    <p>Chưa đủ bằng chứng để nói các nơi này hợp với điều kiện bạn đặt. Tự kiểm tra trước nếu muốn chọn.</p>
                    <div className={`tg-grid ${pinned ? 'is-two' : ''}`}>{view.unverified.cards.map((c) => <PlaceCard key={c.id} c={c} onDrop={setDropFor} cmp={cmp.includes(c.id)} onCmp={onCmp} />)}</div>
                  </details>
                )}
              </>
            )}
          </div>
          {pinned && <AssistantPinned />}
        </div>
      </Page>

      {cmp.length >= 2 && <button type="button" className="tg-btn tg-btn--primary tg-float-cmp" onClick={() => goCompare(cmp)}><Icon name="swap" size={18} /> So sánh {cmp.length} nơi</button>}
      <SelectedBar onRelax={editTicket} />
      <AssistantFloat />
      <DropSheet card={dropFor} onClose={() => setDropFor(null)} />
    </>
  )
}

// What the search box found: places of every tab, best first, each with its tab; then named places the lists do not hold, and why.
function SearchResults({ q, found, groups, cmp, onCmp, onDrop, pinned, conflicted, onClear }: { q: string; found: SearchResult | null; groups: Group[]; cmp: string[]; onCmp: (id: string) => void; onDrop: (c: Card) => void; pinned: boolean; conflicted: Set<string>; onClear: () => void }) {
  if (!found || found.q !== q) return <p className="tg-busy" role="status"><i /> Đang tìm “{q}”…</p>
  const label = (id?: string | null) => groups.find((g) => g.id === id)?.label
  return (
    <section className="tg-xfound" aria-live="polite">
      <p className="tg-xfound__head">{found.total ? <><b>{found.total} nơi</b> khớp “{q}”{found.total > found.cards.length ? `, hiện ${found.cards.length} nơi hợp nhất` : ''}, xếp từ hợp nhất.</> : <>Không có nơi nào trong gợi ý khớp “{q}”. Thử một chữ ngắn hơn, bỏ dấu, hoặc tên loại nơi như “cà phê”, “chợ”.</>} <button type="button" className="tg-link" onClick={onClear}>Xóa tìm kiếm</button></p>
      {found.cards.length > 0 && (
        <div className={`tg-grid ${pinned ? 'is-two' : ''}`}>
          {found.cards.map((c) => (
            <div key={c.id} className="tg-xfound__item">
              {label(c.group) && <span className="tg-xfound__tab">{label(c.group)}</span>}
              <PlaceCard c={c} onDrop={onDrop} cmp={cmp.includes(c.id)} onCmp={onCmp} warn={conflicted.has(c.id) ? 'Đang vướng một chỗ cần chú ý' : undefined} />
            </div>
          ))}
        </div>
      )}
      {found.outside.length > 0 && (
        <div className="tg-xfound__out">
          <h3>Không nằm trong gợi ý</h3>
          <ul>{found.outside.map((o) => <li key={o.id}><button type="button" className="tg-link" onClick={(e) => openPlace(o.id, e.currentTarget)}>{o.name}</button><span className="tg-muted"> · {o.reasons.join('; ')}</span></li>)}</ul>
        </div>
      )}
    </section>
  )
}

export function DropSheet({ card, onClose, after }: { card: Card | { id: string; name: string } | null; onClose: () => void; after?: () => void }) {
  const { act, busy } = useDecision()
  const drop = async (reason?: DropReason) => {
    if (!card) return
    onClose()
    if (await act({ type: 'drop', place_id: card.id, ...(reason ? { reason } : {}) })) after?.()
  }
  return (
    <Dialog.Root open={Boolean(card)} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="tg tg-overlay" />
        <Dialog.Content className="tg tg-sheet" aria-describedby={undefined}>
          <Dialog.Title>Bỏ {card?.name ?? ''}?</Dialog.Title>
          <p className="tg-muted">Cho mình biết lý do để gợi ý đúng hơn, hoặc bỏ luôn cũng được.</p>
          <div className="tg-sheet__chips">{(Object.keys(DROP_LABEL) as DropReason[]).map((r) => <button key={r} type="button" className="tg-chip" disabled={busy} onClick={() => drop(r)}>{DROP_LABEL[r]}</button>)}</div>
          <div className="tg-sheet__foot"><button type="button" className="tg-link" onClick={onClose}>Giữ lại</button><button type="button" className="tg-btn tg-btn--primary" disabled={busy} onClick={() => drop()}>Bỏ luôn, không cần lý do</button></div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

// A one-time pointer to the disc view: shown until the user dismisses it or has tried the disc once (per browser).
const DISC_HINT = 'tg.disc-hint.v1'
function useDiscHint(inDisc: boolean) {
  const [seen, setSeen] = useState(() => { try { return localStorage.getItem(DISC_HINT) === '1' } catch { return false } })
  const dismiss = () => { setSeen(true); try { localStorage.setItem(DISC_HINT, '1') } catch { /* the hint just shows again next time */ } }
  useEffect(() => { if (inDisc && !seen) dismiss() }, [inDisc]) // eslint-disable-line react-hooks/exhaustive-deps
  return { seen, dismiss }
}
