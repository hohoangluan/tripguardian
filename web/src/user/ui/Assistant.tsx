import * as Dialog from '@radix-ui/react-dialog'
import { useEffect, useRef, useState } from 'react'
import { info } from '../lib'
import { whyNot } from '../pd/api'
import { useDecision } from '../pd/decision'
import { editMsg, dismissNudge, openAssistant, pinAssistant, pushMsg, useUi } from '../store'
import { useTrip } from '../trip'
import { searchPlaces } from '../tu/api'
import { go, placeHref, PlacePhoto } from './common'
import { Icon } from './icons'

const CHIPS = ['Yên tĩnh hơn', 'Ít di chuyển hơn', 'Thêm một chỗ ăn trưa', 'Vì sao không gợi ý Langbiang?']
// "vì sao không gợi ý X" is answered from the data (why-not), not by the agent.
const WHY_NOT = /(?:vì sao|tại sao|sao)\s+(?:không|chưa)\s+(?:gợi ý|thấy|có)\s+(.+?)\s*\??$/i

function useSend() {
  const { say, view } = useDecision()
  const { trip } = useTrip()
  return async (text: string) => {
    pushMsg({ role: 'user', text })
    const why = WHY_NOT.exec(text)
    if (why && trip.decisionId) {
      const bot = pushMsg({ role: 'bot', text: 'Mình tra trong dữ liệu…' })
      try {
        const hits = await searchPlaces(why[1])
        if (!hits.length) return editMsg(bot, { text: `Mình không thấy "${why[1]}" trong dữ liệu Đà Lạt của mình, nên không gợi ý được. Mình không đoán nơi khi chưa có dữ liệu.` })
        const r = await whyNot(trip.decisionId, hits[0].id)
        const shown = view?.groups.some((g) => g.cards.some((c) => c.id === hits[0].id))
        editMsg(bot, {
          text: shown ? `${r.name ?? hits[0].name} đang có trong danh sách gợi ý.` : r.listed ? `${r.name ?? hits[0].name}: ${r.reasons.join(' ')}.` : r.reasons.length ? `${r.name ?? hits[0].name}: ${r.reasons.join(' ')} Mình không tự bỏ giới hạn; muốn thì bạn nới ở vé chuyến, mình nói rõ cái giá.` : `${r.name ?? hits[0].name} chưa có lý do rõ để loại; có thể nó chỉ xếp sau những nơi hợp hơn.`,
          places: [hits[0].id],
        })
      } catch {
        editMsg(bot, { text: 'Chưa tra được, bạn thử lại sau nhé.' })
      }
      return
    }
    const bot = pushMsg({ role: 'bot', text: '' })
    const diff = await say(text, (soFar) => editMsg(bot, { text: soFar }))
    // The places that came in (a few), else the ones that left: a whole rebuilt list would bury the reply.
    const changed = diff ? (diff.added.length ? diff.added.slice(0, 6) : diff.removed.slice(0, 3)) : []
    if (changed.length) editMsg(bot, { places: changed })
  }
}

function Body({ pinned, inDialog = false }: { pinned: boolean; inDialog?: boolean }) {
  const a = useUi((u) => u.assistant)
  const { busy } = useDecision()
  const send = useSend()
  const [text, setText] = useState('')
  const endRef = useRef<HTMLDivElement>(null)
  useEffect(() => { endRef.current?.scrollIntoView({ block: 'end' }) }, [a.msgs])
  const submit = (t: string) => {
    if (!t.trim() || busy) return
    send(t.trim())
    setText('')
  }
  return (
    <>
      <header className="tg-asst__head">
        <div><Icon name="sparkle" size={18} />{inDialog ? <Dialog.Title>Hỏi TripGuardian</Dialog.Title> : <h2>Hỏi TripGuardian</h2>}</div>
        <div className="tg-asst__ops">
          <button type="button" className="tg-link" onClick={() => pinAssistant(!pinned)} aria-pressed={pinned}>{pinned ? 'Bỏ ghim' : 'Ghim'}</button>
          <button type="button" className="tg-icon-btn" onClick={() => openAssistant(false)} aria-label="Thu lại"><Icon name="x" size={18} /></button>
        </div>
      </header>
      <div className="tg-asst__log" role="log" aria-live="polite">
        {a.msgs.length === 0 && <p className="tg-asst__intro">Nói điều bạn muốn đổi trong danh sách, ví dụ "bỏ mấy chỗ đông đi" hay "thêm một quán ăn tối gần hồ". Mọi thay đổi hiện ngay trên lưới và hoàn tác được.</p>}
        {a.msgs.map((m) => (
          <div key={m.id} className={`tg-msg is-${m.role}`}>
            <p>{m.text || (m.role === 'bot' ? '…' : '')}</p>
            {m.places && <div className="tg-msg__chips">{m.places.map((id) => <button key={id} type="button" className="tg-pchip" onClick={() => go(placeHref(id))}><PlacePhoto id={id} className="tg-pchip__ph" />{info(id)?.name ?? 'Xem nơi này'}</button>)}</div>}
          </div>
        ))}
        <div ref={endRef} />
      </div>
      <div className="tg-asst__chips" role="group" aria-label="Gợi ý câu hỏi">{CHIPS.map((c) => <button key={c} type="button" className="tg-chip" disabled={busy} onClick={() => submit(c)}>{c}</button>)}</div>
      <form className="tg-asst__in" onSubmit={(e) => { e.preventDefault(); submit(text) }}>
        <label className="tg-sr" htmlFor="tg-asst-in">Nói với mình</label>
        <input id="tg-asst-in" className="tg-line-input" value={text} maxLength={1000} onChange={(e) => setText(e.target.value)} placeholder="Nói với mình, ví dụ: yên tĩnh hơn đi" autoComplete="off" />
        <button type="submit" className="tg-icon-btn" disabled={busy} aria-label="Gửi"><Icon name="send" size={18} /></button>
      </form>
    </>
  )
}

export function AssistantPinned() {
  return <aside className="tg-asst is-pinned" aria-label="Trợ lý"><Body pinned /></aside>
}

export function AssistantFloat() {
  const a = useUi((u) => u.assistant)
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (e.key === '/' && !/INPUT|TEXTAREA/.test(t.tagName) && !t.isContentEditable) { e.preventDefault(); openAssistant(true) }
    }
    addEventListener('keydown', on)
    return () => removeEventListener('keydown', on)
  }, [])
  return (
    <>
      {!a.open && (
        <div className="tg-asst-fab">
          {a.nudge && <div className="tg-nudge" role="status"><span>{a.nudge}</span><button type="button" className="tg-link" onClick={() => openAssistant(true)}>Xem</button><button type="button" className="tg-icon-btn" onClick={dismissNudge} aria-label="Tắt gợi ý"><Icon name="x" size={16} /></button></div>}
          <button type="button" className="tg-fab" onClick={() => openAssistant(true)} aria-keyshortcuts="/" aria-label="Hỏi TripGuardian" title="Hỏi TripGuardian  ( / )"><Icon name="sparkle" size={22} />{a.nudge && <i className="tg-fab__dot" aria-hidden="true" />}</button>
        </div>
      )}
      {a.open && !a.pinned && (
        <Dialog.Root open modal={false} onOpenChange={(o) => !o && openAssistant(false)}>
          <Dialog.Portal>
            <Dialog.Content className="tg tg-asst is-float" aria-describedby={undefined} onInteractOutside={(e) => e.preventDefault()} onOpenAutoFocus={(e) => { e.preventDefault(); document.getElementById('tg-asst-in')?.focus() }}>
              <Body pinned={false} inDialog />
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      )}
    </>
  )
}
