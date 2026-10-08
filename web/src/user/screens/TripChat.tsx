import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { FIELD_LABEL, hardText, softText } from '../tu/labels'
import type { Card, Understanding } from '../tu/types'
import { Icon, type IconName } from '../ui/icons'
import { linesOf } from '../ui/Ticket'

// docs/UI_SPEC_USER_WEB.md Trang 3 §Mở đầu. The opening question is a conversation: the user tells the trip,
// the agent says back what it understood (each line editable) and what is still unclear, and only when the
// user agrees does the deck of short questions start.

export interface ChatMsg {
  who: 'ai' | 'me'
  text: string
}
export interface Read {
  target: string
  quote: string
}

// The opening line is the chat's own, not the first question's text: the question deck never repeats it.
export const GREET = 'Chào bạn, mình giúp bạn lên chuyến Đà Lạt. Kể theo cách nào cũng được: đi mấy ngày, với ai, đi bằng gì, thích gì. Chưa nghĩ ra thì chọn một cách bắt đầu bên dưới.'

// The ways to begin, as things the user can say. The first sends itself; the others start a sentence for them to finish.
const WAYS: { icon: IconName; label: string; send?: string; fill?: string; help?: string }[] = [
  { icon: 'sparkle', label: 'Mình chưa có ý tưởng gì', send: 'Mình chưa có ý tưởng gì cả, bạn hỏi mình từng bước nhé.' },
  { icon: 'bookmark', label: 'Mình có vài nơi đã lưu', fill: 'Mình đã lưu vài nơi: ', help: 'Gõ tên các nơi, mỗi nơi một dòng (Shift + Enter để xuống dòng). Mình khớp từng nơi với dữ liệu.' },
  { icon: 'flag', label: 'Mình có một nơi nhất định phải đến', fill: 'Mình nhất định phải đến ', help: 'Gõ tên nơi đó, mình xếp cả chuyến quanh nó.' },
  { icon: 'calendar', label: 'Mình có sẵn một lịch trình', fill: 'Mình có sẵn lịch trình này, bạn kiểm tra giúp: ', help: 'Dán lịch trình vào đây, mình kiểm tra xem đi có kịp không.' },
]

const readLabel = (t: string) => {
  const [kind] = t.split(':')
  return FIELD_LABEL[kind] ?? { soft: 'Sở thích', hard: 'Giới hạn', anchor: 'Nơi muốn đến', unmapped: 'Ghi chú', signal: 'Gợi ý' }[kind] ?? 'Ghi chú'
}

interface Props {
  msgs: ChatMsg[]
  ready: boolean
  busy: boolean
  live: string
  reads: Read[]
  quotes: Record<string, string>
  u: Understanding | null
  card: Card | null
  preview: Set<string>
  leaving: boolean
  onTell: (text: string) => void
  onOpen: (target: string | null) => void
  onEdit: (target: string, value: string | null) => void
  onGo: () => void
}

export function TripChat({ msgs, ready, busy, live, reads, quotes, u, card, preview, leaving, onTell, onOpen, onEdit, onGo }: Props) {
  const [text, setText] = useState('')
  const [help, setHelp] = useState<string | null>(null)
  const end = useRef<HTMLDivElement>(null)
  const box = useRef<HTMLTextAreaElement>(null)
  const told = msgs.some((m) => m.who === 'me')
  const thinking = told && (busy || !ready)
  const summary = told && !thinking && !!u

  useEffect(() => {
    if (!told) box.current?.focus({ preventScroll: true })
  }, [told])
  // Keep the newest line in view as the conversation grows.
  useEffect(() => {
    if (!told) return
    const t = window.setTimeout(() => end.current?.scrollIntoView({ block: 'nearest', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' }), 60)
    return () => window.clearTimeout(t)
  }, [msgs.length, thinking, summary, reads.length, told])
  useEffect(() => {
    const el = box.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`
  }, [text])

  const submit = () => {
    const t = text.trim()
    if (!t || busy || !ready) return
    onTell(t)
    setText('')
  }

  const pick = (w: (typeof WAYS)[number]) => {
    if (w.send) return onTell(w.send)
    setText(w.fill ?? '')
    setHelp(w.help ?? null)
    window.setTimeout(() => { const el = box.current; if (!el) return; el.focus(); el.setSelectionRange(el.value.length, el.value.length) }, 0)
  }

  return (
    <div className={`tg-ask__card tg-chat ${leaving ? 'is-leaving' : ''}`} aria-busy={busy || leaving}>
      <div className="tg-ask__top">
        <span className="tg-ask__ico" aria-hidden="true"><Icon name="sparkle" size={18} /></span>
        <span className="tg-ask__intent"><b>CHUYẾN ĐI</b><span>kể tự nhiên, mình ghi lại</span></span>
      </div>
      <ol className="tg-chat__log" aria-live="polite" aria-label="Trò chuyện về chuyến đi">
        {msgs.map((m, i) => <li key={i} className={`tg-chat__msg is-${m.who}`}><p>{m.text}</p></li>)}
        {!told && (
          <li className="tg-chat__ways" aria-label="Cách bắt đầu">
            {WAYS.map((w) => <button key={w.label} type="button" className="tg-chip" disabled={!ready || busy} onClick={() => pick(w)}><Icon name={w.icon} size={16} />{w.label}</button>)}
          </li>
        )}
        {thinking && (
          <li className="tg-chat__msg is-ai is-live">
            <p>{live || 'Mình đang đọc chuyến đi của bạn'}{!live && <span className="tg-dots" aria-hidden="true"><i /><i /><i /></span>}</p>
            {reads.length > 0 && (
              <ul className="tg-chat__reads" aria-label="Mình đang ghi">
                {reads.map((r) => <li key={r.target}><span>“{r.quote}”</span><Icon name="arrow" size={13} /><b>{readLabel(r.target)}</b></li>)}
              </ul>
            )}
          </li>
        )}
        {summary && u && <li className="tg-chat__msg is-ai is-sum"><Understood u={u} card={card} quotes={quotes} preview={preview} onOpen={onOpen} onEdit={onEdit} /></li>}
      </ol>
      {summary && (
        <div className="tg-chat__go">
          <button type="button" className="tg-btn tg-btn--primary" disabled={busy || leaving} onClick={onGo}>{card ? 'Đúng rồi, hỏi tiếp' : 'Đúng rồi, bắt đầu tìm'} <Icon name="arrow" size={18} /></button>
        </div>
      )}
      {help && !told && <p className="tg-chat__help tg-faint"><Icon name="info" size={13} /> {help}</p>}
      <form className="tg-chat__say" onSubmit={(e) => { e.preventDefault(); submit() }}>
        <label className="tg-sr" htmlFor="tg-chat-box">{told ? 'Sửa hoặc kể thêm' : 'Kể về chuyến đi'}</label>
        <textarea
          id="tg-chat-box"
          ref={box}
          rows={1}
          value={text}
          disabled={leaving}
          onChange={(e) => { setText(e.target.value); if (!e.target.value) setHelp(null) }}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); submit() } }}
          placeholder={told ? 'Có gì chưa đúng? Gõ để sửa hoặc kể thêm…' : 'Ví dụ: 3 ngày cuối tuần với người yêu, đi xe máy, muốn săn mây'}
        />
        <button type="submit" className="tg-chat__send" disabled={!text.trim() || busy || !ready} aria-label="Gửi"><Icon name="send" size={18} /></button>
      </form>
      <div ref={end} className="tg-chat__end" />
    </div>
  )
}

function Understood({ u, card, quotes, preview, onOpen, onEdit }: { u: Understanding; card: Card | null; quotes: Record<string, string>; preview: Set<string>; onOpen: (t: string | null) => void; onEdit: (t: string, v: string | null) => void }) {
  const lines = linesOf(u)
  const flash = (t: string) => (preview.has(t) ? ' tg-flash' : '')
  let i = 0
  const step = () => ({ '--i': i++ }) as CSSProperties
  const empty = !lines.length && !u.anchors.length && !u.hard.length && !u.soft.length
  const unclear = [...(u.safety_pending ? ['một điều về an toàn'] : []), ...u.unknowns.map((k) => (FIELD_LABEL[k] ?? k).toLowerCase())]
  return (
    <div className="tg-chat__sum">
      <h3>Mình đã hiểu như này</h3>
      {empty ? (
        <p className="tg-muted">Mình chưa rút ra được điều gì chắc chắn từ câu này. Bạn kể thêm, hoặc để mình hỏi từng câu ngắn.</p>
      ) : (
        <ul className="tg-chat__rows">
          {lines.map((r) => (
            <li key={r.key} style={step()} className={flash(r.target)}>
              <span>{r.label}</span>
              <b>{r.value}{quotes[r.target] ? <small>từ “{quotes[r.target]}”</small> : r.mark ? <small>mình đoán, sửa được</small> : null}</b>
              <button type="button" className="tg-chat__fix" aria-label={`Sửa ${r.label.toLowerCase()}`} title="Sửa" onClick={() => onOpen(r.key)}><Icon name="edit" size={15} /></button>
            </li>
          ))}
          {u.anchors.map((a) => (
            <li key={a.target} style={step()}>
              <span>{a.priority === 'must' ? 'Nhất định đến' : 'Muốn đến'}</span>
              <b>{a.name ?? a.text}{a.state === 'missing' && <small>chưa tìm thấy trong dữ liệu</small>}{a.state === 'choose' && <small>có vài nơi trùng tên, mình hỏi lại</small>}</b>
              <button type="button" className="tg-chat__fix" aria-label={`Bỏ ${a.name ?? a.text}`} title="Bỏ" onClick={() => onEdit(a.target, null)}><Icon name="x" size={15} /></button>
            </li>
          ))}
          {u.hard.map((h) => (
            <li key={h.target} style={step()} className={flash(h.target)}>
              <span>Giới hạn</span>
              <b>{hardText(h)}</b>
              <button type="button" className="tg-chat__fix" aria-label={`Bỏ giới hạn ${hardText(h)}`} title="Bỏ" onClick={() => onEdit(h.target, null)}><Icon name="x" size={15} /></button>
            </li>
          ))}
        </ul>
      )}
      {u.soft.length > 0 && (
        <div className="tg-chat__soft" style={step()}>
          <span>Gu của bạn</span>
          <div className="tg-ticket__chips">
            {u.soft.map((s) => (
              <span key={s.target} className={`tg-chip tg-chip--dash${flash('soft')}`}>
                {softText(s)}
                <button type="button" className="tg-chip__x" aria-label={`Bỏ ${softText(s)}`} onClick={() => onEdit(s.target, null)}><Icon name="x" size={12} /></button>
              </span>
            ))}
          </div>
        </div>
      )}
      {u.unmapped.length > 0 && <p className="tg-faint tg-chat__note" style={step()}>Mình ghi lại nhưng chưa kiểm được bằng dữ liệu: {u.unmapped.map((x) => `“${x.phrase}”`).join(', ')}.</p>}
      {card ? (
        <div className="tg-chat__next" style={step()}>
          <h3>Mình cần hỏi thêm một số ý</h3>
          {unclear.length > 0 ? <p>Còn chưa rõ: {unclear.slice(0, 5).map((x) => <b key={x} className="tg-chip tg-chip--soft">{x}</b>)}</p> : <p className="tg-muted">Vài câu ngắn để gợi ý sát hơn, câu nào không chắc thì bỏ qua.</p>}
        </div>
      ) : (
        <p className="tg-chat__next" style={step()}><b>Mình đủ hiểu để gợi ý rồi.</b></p>
      )}
    </div>
  )
}
