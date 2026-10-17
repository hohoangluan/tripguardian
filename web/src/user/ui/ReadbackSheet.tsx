import * as Dialog from '@radix-ui/react-dialog'
import { useRef, useState } from 'react'
import { enterStage, requestStageEntry, JourneyError, mutateJourney, readJourney } from '../journey'
import type { View as DecisionView } from '../pd/types'
import type { Deck, DeckIssue, Readback, TurnInput, Understanding } from '../tu/types'
import { go } from './common'
import { GateAsk, KINDS, LedgerList, MARKERS } from './Gate'
import { Icon } from './icons'
import { Stamp } from './Stamp'

export function ReadbackSheet({ id, initial, missing: initialMissing, onClose, onAdvance, onView }: {
  id: string; initial: Readback; missing: string[]
  onClose: () => void; onAdvance: () => Promise<boolean>; onView: (view: DecisionView) => void
}) {
  const [readback, setReadback] = useState(initial)
  const [missing, setMissing] = useState(initial.missing ?? initialMissing.filter(key => key !== 'readback'))
  const [deck, setDeck] = useState<Deck | null>(initial.deck ?? null)
  const [issues, setIssues] = useState<DeckIssue[]>([])
  const [busy, setBusy] = useState(false)
  const working = useRef(false)
  const [changed, setChanged] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const replace = (next: Readback, needed = next.missing) => {
    setReadback(next)
    if (needed) { setMissing(next.missing ?? needed.filter(key => key !== 'readback')); setDeck(needed.length ? next.deck ?? null : null) }
  }
  const update = async (input: TurnInput) => {
    if (working.current) return
    working.current = true
    setBusy(true); setError(null); setIssues([])
    let fresh = false
    let received = false
    const origin = location.pathname + location.search
    try {
      const result = await mutateJourney(id, 'decision', 'trip', input, {
        state: (data: { understanding: Understanding }) => {
          if (data.understanding.readback) { received = true; replace(data.understanding.readback, []); setChanged(input.kind === 'drop') }
        },
        card: (card: Deck | null) => { if (card?.kind === 'deck') setDeck(card) },
        deck_issues: (data: { issues: DeckIssue[] }) => setIssues(data.issues),
        readback: (next: Readback) => { fresh = true; received = true; replace(next); setChanged(true) },
      })
      if (origin !== location.pathname + location.search) return
      const resultView = (result.result as { view?: DecisionView })?.view
      if (resultView) onView(resultView)
      // Partial required answers have no understanding.readback yet; read the server's remaining gate.
      if (!received && input.kind !== 'readback_ok') replace(await readJourney<Readback>(id, 'trip/readback'))
      if (input.kind === 'readback_ok' && !fresh) await onAdvance()
    } catch (e) {
      if (origin !== location.pathname + location.search) return
      if (e instanceof JourneyError && e.status === 409 && e.readback) { replace(e.readback, e.missing); setChanged(true) }
      else setError('Chưa lưu được thông tin. Bạn thử lại nhé.')
    } finally { working.current = false; setBusy(false) }
  }
  const edit = async () => {
    if (working.current) return
    working.current = true; setBusy(true); setError(null)
    try { await enterStage(id, 'trip'); requestStageEntry(id, 'trip'); onClose(); go('/understand') }
    catch { setError('Chưa mở được Hiểu chuyến. Bạn thử lại nhé.') }
    finally { working.current = false; setBusy(false) }
  }
  // One postcard (ui/Gate.tsx, gate.css): while questions are open each is a page with the rest as tabs; once none are,
  // what TripGuardian has written down is read back as the page itself.
  const asking = missing.length > 0
  const ask = asking && deck
  const drop = (target: string) => update({ kind: 'drop', target })
  const flagged = readback.lines.filter(line => line.kind === 'check')
  const rest = readback.lines.filter(line => line.kind !== 'check')
  const tally = Object.fromEntries(KINDS.map(k => [k, readback.lines.filter(line => line.kind === k).length])) as Record<(typeof KINDS)[number], number>
  return <Dialog.Root open onOpenChange={open => { if (!open && !busy) onClose() }}>
    <Dialog.Portal>
      <Dialog.Overlay className="tg-gt__veil" />
      <Dialog.Content className={`tg tg-gt is-ask ${ask ? 'is-fan' : ''}`} aria-describedby={ask ? undefined : 'readback-description'} onOpenAutoFocus={e => { const front = document.querySelector<HTMLElement>('.tg-gt__front'); if (front) { e.preventDefault(); front.focus({ preventScroll: true }) } }} onCloseAutoFocus={e => { e.preventDefault(); document.querySelector<HTMLButtonElement>('.tg-bar .tg-btn--primary')?.focus() }}>
        <div className="tg-gt__paper" />
        <Dialog.Close className="tg-gt__x" disabled={busy} aria-label="Đóng"><Icon name="x" size={16} /></Dialog.Close>
        {ask ? <GateAsk key={JSON.stringify(deck)} deck={deck} busy={busy} issues={issues} lines={readback.lines} changed={changed} error={error}
            onAnswer={answers => update({ kind: 'deck', answers })} onOther={edit} onDrop={target => update({ kind: 'drop', target })} />
          : <div className="tg-gt__page is-read">
            <aside className="tg-gt__aside" style={{ '--photo': 'url(/img/home/dalat-tea-sunrise.jpg)' } as React.CSSProperties}>
              <Stamp icon={asking ? 'sparkle' : 'route'} className="tg-gt__stamp" />
              <p className="tg-gt__kicker">Trước khi lập lịch</p>
              <p className="tg-gt__num" aria-hidden="true">{readback.lines.length}<small> điều đã ghi nhận</small></p>
              <Dialog.Title className="tg-gt__title">{asking ? <>Còn {missing.length} câu nữa <em>là xếp lịch được</em></> : <>Mình sẽ xếp lịch <em>theo những điều này</em></>}</Dialog.Title>
              <Dialog.Description id="readback-description" className="tg-gt__why">{asking ? 'Còn vài điều chưa rõ. Bạn mở lại phần Tìm hiểu để bổ sung nhé.' : 'Bạn xem lại một lượt. Chỗ nào chưa đúng thì bấm vào dòng đó để sửa.'}</Dialog.Description>
            </aside>
            <div className="tg-gt__stops tg-gt__tally" aria-label="Các điều đã ghi nhận theo nguồn">
              {KINDS.filter(k => tally[k]).map(k => <span key={k} className={`is-${k}`}><i />{MARKERS[k]} {tally[k]}</span>)}
            </div>
            <section className="tg-gt__read" aria-label="Những điều mình đã ghi nhận">
              {changed && <p className="tg-gt__changed" role="status"><Icon name="info" size={16} />Vừa có thay đổi, bạn xem lại nhé</p>}
              {!!flagged.length && <div className="tg-gt__flag"><b><Icon name="warn" size={16} />Cần bạn xem lại</b><LedgerList lines={flagged} busy={busy} onEdit={edit} onDrop={drop} /></div>}
              <LedgerList lines={rest} busy={busy} onEdit={edit} onDrop={drop} />
            </section>
            <footer className="tg-gt__foot">
              <div className="tg-gt__foot-l"><button type="button" className="tg-gt__link" disabled={busy} onClick={edit}><Icon name="edit" size={16} />Sửa trong Tìm hiểu</button></div>
              <div className="tg-gt__foot-r">
                {error && <span className="tg-gt__err" role="alert">{error}</span>}
                {!asking && <button type="button" className="tg-gt__go" disabled={busy || !readback.digest || !readback.lines.length} onClick={() => update({ kind: 'readback_ok', value: readback.digest! })}>{busy ? 'Đang lưu…' : 'Đúng rồi, xếp lịch'}<Icon name="arrow" size={18} /></button>}
              </div>
            </footer>
          </div>}
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>
}
