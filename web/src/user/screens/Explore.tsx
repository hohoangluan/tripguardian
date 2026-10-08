import * as Dialog from '@radix-ui/react-dialog'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useDecision } from '../pd/decision'
import type { Card } from '../pd/types'
import { requestStageEntry } from '../journey'
import { nudge, openAssistant, setUi, useUi } from '../store'
import { DROP_LABEL, useTrip, type DropReason } from '../trip'
import { AssistantFloat, AssistantPinned } from '../ui/Assistant'
import { ArtHills, Empty, go, placeHref, PlacePhoto } from '../ui/common'
import { DiscPicker } from '../ui/DiscPicker'
import { Icon } from '../ui/icons'
import { PlaceCard } from '../ui/PlaceCard'
import { SelectedBar } from '../ui/SelectedBar'
import { reducedMotion, useStagedList } from '../ui/useStagedList'
import { FlowBar, Page, useTitle } from '../ui/Shell'

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
  return out.slice(0, 2)
}

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
  useTitle('Chọn nơi')
  const { trip } = useTrip()
  const { view, error, act, busy, reload, more, loadingMore } = useDecision()
  const tab = useUi((u) => u.tab)
  const [cmp, setCmp] = useState<string[]>([])
  const [dropFor, setDropFor] = useState<Card | null>(null)
  const [exOpen, setExOpen] = useState(false)
  const [mode, setMode] = useState<'grid' | 'disc'>('grid')
  const asst = useUi((u) => u.assistant)
  const editTicket = useEditTicket()
  const pinned = asst.open && asst.pinned
  const groups = view?.groups.filter((g) => g.id !== 'anchors' && g.cards.length) ?? []
  const current = groups.find((g) => g.id === tab) ?? groups[0]
  const foodSel = view ? view.groups.flatMap((g) => g.cards).filter((c) => c.chosen && /cà phê|coffee|cafe/i.test(c.category ?? '')).length : 0
  useEffect(() => { if (foodSel >= 3) nudge(`Bạn đã chọn ${foodSel} quán cà phê. Thêm một chỗ ăn trưa chứ?`) }, [foodSel])
  const onCmp = (id: string) => setCmp((c) => (c.includes(id) ? c.filter((x) => x !== id) : c.length >= 3 ? [...c.slice(1), id] : [...c, id]))
  const goCompare = (ids: string[]) => go(`/explore/compare/${ids.map(encodeURIComponent).join(',')}`)
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

  // Scrolling near the end of the grid loads the group's next page.
  const sentinel = useRef<HTMLDivElement>(null)
  const hasMore = Boolean(current && current.cards.length < current.total)
  useEffect(() => {
    const el = sentinel.current
    if (!el || !current || !hasMore) return
    const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) more(current.id) }, { rootMargin: '600px 0px' })
    io.observe(el)
    return () => io.disconnect()
  }, [current?.id, current?.cards.length, hasMore, more]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!trip.decisionId)
    return (
      <>
        <FlowBar step="explore" />
        <Page narrow><Empty art={<ArtHills />} title="Chưa có gợi ý" body={error ?? 'Bắt đầu từ bước Hiểu chuyến đi, chỉ vài câu thôi.'} action={<button type="button" className="tg-btn tg-btn--primary" onClick={() => go('/understand')}>Hiểu chuyến đi</button>} /></Page>
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
  const pairs = similarPairs(current?.cards ?? [])
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
      <FlowBar step="explore" />
      <Page>
        <div className={`tg-xlayout ${pinned ? 'is-pinned' : ''}`}>
          <div className="tg-xmain">
            <header className="tg-xhead">
              <div>
                <p className="tg-kicker">Bước 2 · Chọn nơi</p>
                <h1>Gợi ý cho chuyến của bạn</h1>
                <p>{total - anchors.length} nơi hợp với chuyến của bạn, xếp từ hợp nhất. <button type="button" className="tg-link" onClick={() => openAssistant(true)}>Chat để thu hẹp</button></p>
              </div>
              <div className="tg-xhead__ops">
                <div className="tg-seg" role="group" aria-label="Cách xem"><button type="button" aria-pressed={mode === 'grid'} onClick={() => setMode('grid')}><Icon name="grid" size={15} /> Lưới</button><button type="button" aria-pressed={mode === 'disc'} disabled={!groups.length} onClick={() => setMode('disc')}><Icon name="compass" size={15} /> Đĩa xoay</button></div>
                <button type="button" className="tg-btn tg-btn--ghost tg-btn--sm" onClick={editTicket}><Icon name="sliders" size={16} /> Sửa vé chuyến</button>
              </div>
            </header>

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
                    <div className="tg-req__row">{anchors.map((c) => <button key={c.id} type="button" className="tg-req__row" onClick={() => go(placeHref(c.id))}><PlacePhoto id={c.id} name={c.name} /><span><b>{c.name}</b><br /><small className="tg-muted">{c.area ?? c.category}</small></span></button>)}</div>
                  </section>
                )}
                {mode === 'disc' && current ? (
                  <DiscPicker groups={groups} tab={current.id} onTab={(t) => setUi({ tab: t })} cmp={cmp} onCmp={onCmp} onDrop={setDropFor} onBack={() => setMode('grid')} />
                ) : (
                  <>
                    <div className="tg-tabs" role="tablist" aria-label="Nhóm địa điểm" onKeyDown={(e) => {
                      const i = groups.findIndex((g) => g.id === current?.id)
                      if (e.key === 'ArrowRight') setUi({ tab: groups[(i + 1) % groups.length].id })
                      if (e.key === 'ArrowLeft') setUi({ tab: groups[(i + groups.length - 1) % groups.length].id })
                    }}>
                      {groups.map((g) => <button key={g.id} type="button" role="tab" aria-selected={current?.id === g.id} tabIndex={current?.id === g.id ? 0 : -1} className="tg-tab" onClick={() => setUi({ tab: g.id })}>{g.label}<b>{g.total}</b></button>)}
                    </div>
                    {!current || current.cards.length === 0 ? (
                      <>
                        {question}
                        <Empty art={<ArtHills />} title="Chưa có nơi nào ở nhóm này" body="Thử nhóm khác, hoặc nới giới hạn để có thêm lựa chọn." />
                      </>
                    ) : (
                      <div ref={gridRef} className={`tg-grid ${pinned ? 'is-two' : ''} ${replacing ? 'is-replacing' : ''}`} key={current.id}>
                        {items.flatMap(({ card: c, phase, i: order }, i) => {
                          const out = [<PlaceCard key={c.id} c={c} phase={phase} order={order} onDrop={setDropFor} cmp={cmp.includes(c.id)} onCmp={onCmp} warn={conflicted.has(c.id) ? 'Đang vướng một chỗ cần chú ý' : undefined} />]
                          if (i === 2) pairs.forEach(([a, b]) => out.push(<div key={`sim-${a.id}-${b.id}`} className="tg-similar"><Icon name="swap" size={18} /><span><b>{a.name}</b> và <b>{b.name}</b> khá giống nhau, có lẽ bạn chỉ cần một.</span><button type="button" className="tg-btn tg-btn--ghost tg-btn--sm" onClick={() => goCompare([a.id, b.id])}>So sánh</button></div>))
                          if (i === Math.min(4, items.length - 1) && question) out.push(question)
                          return out
                        })}
                        {hasMore && (
                          <div ref={sentinel} className="tg-grid__more" aria-live="polite" aria-busy={loadingMore === current.id}>
                            {loadingMore === current.id && Array.from({ length: 3 }, (_, i) => <div key={i} className="tg-skel-card"><div className="tg-skel" /><div><span className="tg-skel tg-skel-line" style={{ width: '70%' }} /><span className="tg-skel tg-skel-line" style={{ width: '90%' }} /></div></div>)}
                          </div>
                        )}
                      </div>
                    )}
                  </>
                )}
                {view.unverified.count > 0 && (
                  <details className="tg-unverified" open={view.unverified.open}>
                    <summary><Icon name="info" size={16} /> Chưa xác minh được điều kiện của bạn ({view.unverified.count})</summary>
                    <p>Chưa đủ bằng chứng để nói các nơi này hợp với điều kiện bạn đặt. Tự kiểm tra trước nếu muốn chọn.</p>
                    <div className={`tg-grid ${pinned ? 'is-two' : ''}`}>{view.unverified.cards.map((c) => <PlaceCard key={c.id} c={c} onDrop={setDropFor} cmp={cmp.includes(c.id)} onCmp={onCmp} />)}</div>
                  </details>
                )}
                {view.unmapped.length > 0 && <p className="tg-faint tg-xnote"><Icon name="info" size={14} /> Chưa kiểm được bằng dữ liệu: {view.unmapped.join(', ')}. Mình chỉ nêu trong lời giải thích, không dùng để chọn.</p>}
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
