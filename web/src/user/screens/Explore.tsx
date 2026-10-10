import * as Dialog from '@radix-ui/react-dialog'
import { useEffect, useRef, useState } from 'react'
import { useDecision } from '../pd/decision'
import type { Card } from '../pd/types'
import { useSnapshot } from '../../data/store'
import { requestStageEntry } from '../journey'
import { fmtVnd } from '../lib'
import { nudge, openAssistant, setUi, toggleCmp, useUi } from '../store'
import { DROP_LABEL, STEPS, useTrip, type DropReason } from '../trip'
import { placesDelta } from '../tu/labels'
import { AssistantFloat, AssistantPinned } from '../ui/Assistant'
import { ArtHills, Empty, go, PlacePhoto, warmPlaces } from '../ui/common'
import { openPlace } from '../ui/PlaceSheet'
import { DiscPicker } from '../ui/DiscPicker'
import { Icon } from '../ui/icons'
import { PlaceCard } from '../ui/PlaceCard'
import { SelectedBar } from '../ui/SelectedBar'
import { FlowBar, Page, useTitle } from '../ui/Shell'

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
  const { view, error, act, busy, reload, toPlan } = useDecision()
  const tab = useUi((u) => u.tab)
  const cmp = useUi((u) => u.cmp)
  const [dropFor, setDropFor] = useState<Card | null>(null)
  const [exOpen, setExOpen] = useState(false)
  const asst = useUi((u) => u.assistant)
  const editTicket = useEditTicket()
  // The open chat is a column: beside the page, or inside the disc layer, which covers the page.
  const pinned = asst.open
  const groups = view?.groups.filter((g) => g.id !== 'anchors' && g.cards.length) ?? []
  // Until the user picks a tab, open the trip's main interest (e.g. cafés for "thích cà phê"), not the first group.
  const current = groups.find((g) => g.id === tab) ?? groups.find((g) => g.id === view?.focus) ?? groups[0]
  const foodSel = view ? view.groups.flatMap((g) => g.cards).filter((c) => c.chosen && /cà phê|coffee|cafe/i.test(c.category ?? '')).length : 0
  useEffect(() => { if (foodSel >= 3) nudge(`Bạn đã chọn ${foodSel} quán cà phê. Thêm một chỗ ăn trưa chứ?`) }, [foodSel])
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
  useEffect(() => {
    const ch = view?.change ?? {}
    setFresh((f) => {
      const next = { ...f }
      for (const [g, c] of Object.entries(ch)) if (c.added > 0 && g !== current?.id) next[g] = c.added
      return next
    })
  }, [view?.change]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (current && fresh[current.id]) setFresh(({ [current.id]: _, ...rest }) => rest) }, [current?.id, fresh]) // eslint-disable-line react-hooks/exhaustive-deps

  // The photos are fetched ahead of the scroll: the open tab's first cards now, the first of every other tab once idle.
  const { snap } = useSnapshot()
  const openId = current?.id
  useEffect(() => {
    if (!snap || !view) return
    const tabs = view.groups.filter((g) => g.id !== 'anchors')
    warmPlaces(tabs.find((g) => g.id === openId)?.cards.slice(0, 12).map((c) => c.id) ?? [])
    warmPlaces(tabs.filter((g) => g.id !== openId).flatMap((g) => g.cards.slice(0, 4).map((c) => c.id)))
  }, [snap, view, openId])

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
  const count = <>{total - anchors.length} nơi đi được trong chuyến của bạn{listMove && <span key={listMove.key} className={`tg-xhead__delta ${listMove.delta < 0 ? 'is-down' : 'is-up'}`}>{placesDelta(listMove.delta)}</span>}, xếp theo gu của bạn. <button type="button" className="tg-link" onClick={() => openAssistant(true)}>Chat để thu hẹp</button></>
  const budget = view.budget_vnd ? <>Ngân sách bạn đặt: khoảng <b>{fmtVnd(view.budget_vnd)}/người/ngày</b>. Giá trên thẻ là giá mỗi người.</> : <>Chưa biết ngân sách của bạn nên mình chưa so giá. <button type="button" className="tg-link" onClick={editTicket}>Thêm ngân sách</button></>
  // What frames the list: the trip's notes, the limits that cut places out, the places the trip is built around.
  const framing = (
    <>
      {view.notes.map((n) => <p key={n.code} className="tg-xnotice" role="note"><Icon name="info" size={16} />{n.text}</p>)}
      {view.excluded.by_rule.length > 0 && (
        <>
          <button type="button" className="tg-excl" aria-expanded={exOpen} onClick={() => setExOpen((v) => !v)}><Icon name="lock" size={16} /><span><b>Giới hạn của bạn đã loại {excluded} nơi.</b> Bấm để xem vì giới hạn nào.</span><Icon name="chevronDown" size={18} /></button>
          {exOpen && <ul className="tg-excl-list">{view.excluded.by_rule.map((r) => <li key={r.rule}><span>{r.label}</span><span style={{ opacity: 0.7 }}>· loại {r.count} nơi</span><button type="button" className="tg-link" onClick={editTicket}>Nới giới hạn</button></li>)}</ul>}
        </>
      )}
      {total - anchors.length > 0 && total - anchors.length < 4 && <div className="tg-narrow"><b>Chỉ còn {total - anchors.length} nơi hợp.</b><span className="tg-muted">Nới một giới hạn để có thêm lựa chọn?</span><button type="button" className="tg-link" onClick={editTicket}>Xem giới hạn</button></div>}
      {anchors.length > 0 && (
        <section className="tg-req" aria-labelledby="tg-req-h">
          <div><h2 id="tg-req-h">Nơi bắt buộc đến</h2><p>Mình xếp cả chuyến quanh các nơi này.</p></div>
          <div className="tg-req__row">{anchors.map((c) => <button key={c.id} type="button" className="tg-req__row" onClick={(e) => openPlace(c.id, e.currentTarget.querySelector('figure'))}><PlacePhoto id={c.id} name={c.name} /><span><b>{c.name}</b><br /><small className="tg-muted">{c.area ?? c.category}</small></span></button>)}</div>
        </section>
      )}
    </>
  )
  const unverified = (
    <>
      {view.unverified.count > 0 && (
        <details className="tg-unverified" open={view.unverified.open}>
          <summary><Icon name="info" size={16} /> Chưa xác minh được điều kiện của bạn ({view.unverified.count})</summary>
          <p>Chưa đủ bằng chứng để nói các nơi này hợp với điều kiện bạn đặt. Tự kiểm tra trước nếu muốn chọn.</p>
          <div className="tg-grid">{view.unverified.cards.map((c) => <PlaceCard key={c.id} c={c} onDrop={setDropFor} cmp={cmp.includes(c.id)} onCmp={onCmp} />)}</div>
        </details>
      )}
      {view.unmapped.length > 0 && <p className="tg-faint tg-xnote"><Icon name="info" size={14} /> Chưa kiểm được bằng dữ liệu: {view.unmapped.join(', ')}. Mình chỉ nêu trong lời giải thích, không dùng để chọn.</p>}
    </>
  )
  return (
    <>
      <FlowBar step="explore" onAhead={(t) => { if (t === 'plan' && view?.selected.length) void toPlan(); else go(STEPS.find((x) => x.id === t)!.path) }}
        aside={<button type="button" className="tg-tbtn" onClick={editTicket} aria-label="Vé chuyến: những gì bạn đã kể về chuyến đi. Bấm để xem và sửa ở bước Tìm hiểu" title="Vé chuyến: ngày đi, người đi cùng, sở thích và giới hạn bạn đã kể. Sửa ở đây thì danh sách gợi ý đổi theo."><Icon name="ticket" size={19} /><span className="tg-tbtn__l">Vé chuyến</span><Icon name="sliders" size={16} /></button>} />
      {current ? (
        <DiscPicker groups={groups} tab={current.id} onTab={(t) => setUi({ tab: t })} fresh={fresh} cmp={cmp} onCmp={onCmp} onDrop={setDropFor} conflicted={conflicted}
          lead={question}
          foot={<><p className="tg-xhead__budget">{budget}</p>{framing}{unverified}</>}
          chat={pinned ? <AssistantPinned /> : null} />
      ) : (
        <Page>
          <div className={`tg-xlayout ${pinned ? 'is-pinned' : ''}`}>
            <div className="tg-xmain">
              <header className="tg-xhead">
                <div>
                  <p className="tg-kicker">Bước 2 · Lựa chọn</p>
                  <h1>Gợi ý cho chuyến của bạn</h1>
                  <p>{count}</p>
                  <p className="tg-xhead__budget">{budget}</p>
                </div>
              </header>
              {framing}
              {question}
              <Empty art={<ArtHills />} title={total === 0 ? 'Giới hạn hiện tại loại hết các nơi' : 'Chưa có nơi nào để chọn'} body="Nới một giới hạn để mình gợi ý lại; mình không tự bỏ giới hạn của bạn." action={<button type="button" className="tg-btn tg-btn--primary" onClick={editTicket}>Xem và nới giới hạn</button>} />
              {unverified}
            </div>
            {pinned && <AssistantPinned />}
          </div>
        </Page>
      )}

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
