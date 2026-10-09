import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { ACCEPT, readAttachment, withAttachments, type Attachment } from '../tu/attach'

// What sits in the composer before sending: a text file read into lines, or a photo shown as a thumbnail.
type Att = { name: string; image?: string; file?: Attachment }
import { FIELD_LABEL, hardText, softText } from '../tu/labels'
import type { Card, Understanding } from '../tu/types'
import { BotAvatar, Icon } from '../ui/icons'
import { linesOf } from '../ui/Ticket'

// docs/UI_SPEC_USER_WEB.md Trang 3 §Mở đầu. The opening question is a conversation: the user tells the trip,
// the agent says back what it understood (each line editable) and what is still unclear, and only when the
// user agrees does the deck of short questions start.

export interface ChatMsg {
  who: 'ai' | 'me'
  text: string
  files?: string[] // names of the files sent with it
  images?: string[] // object URLs of the photos sent with it
}
export interface Read {
  target: string
  quote: string
}

// The opening line is the chat's own, not the first question's text: the question deck never repeats it.
export const GREET = 'Chuyến Đà Lạt bạn đang mong là chuyến như thế nào? Kể tự nhiên thôi: đi cùng ai, mấy ngày, muốn săn mây, sống chậm hay ăn cho đã. Mình lo phần còn lại.'

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
  onTell: (text: string, shown: ChatMsg) => void // text = what the agent reads; shown = the bubble
  onOpen: (target: string | null) => void
  onEdit: (target: string, value: string | null) => void
  onGo: () => void
}

export function TripChat({ msgs, ready, busy, live, reads, quotes, u, card, preview, leaving, onTell, onOpen, onEdit, onGo }: Props) {
  const [text, setText] = useState('')
  const [atts, setAtts] = useState<Att[]>([])
  const [fileNote, setFileNote] = useState<string | null>(null)
  const [drag, setDrag] = useState(false)
  const picker = useRef<HTMLInputElement>(null)
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
    if ((!t && !atts.length) || busy || !ready) return
    const files = atts.flatMap((a) => (a.file ? [a.file] : []))
    const photos = atts.filter((a) => a.image)
    const said = withAttachments(t, files) + (photos.length ? `${t || files.length ? '\n\n' : ''}(Kèm ảnh: ${photos.map((a) => a.name).join(', ')})` : '')
    onTell(said, { who: 'me', text: t, files: files.map((f) => f.name), images: photos.map((a) => a.image!) })
    setText('')
    setAtts([])
    setFileNote(null)
  }

  // A list of places or an itinerary as a file: read here, sent as lines with the next message.
  const attach = async (list: FileList | null) => {
    setFileNote(null)
    for (const f of Array.from(list ?? []).slice(0, 6)) {
      if (f.type.startsWith('image/')) { setAtts((x) => [...x, { name: f.name || 'ảnh', image: URL.createObjectURL(f) }]); continue }
      try {
        const a = await readAttachment(f)
        if (!a.lines.length) { setFileNote(`Không đọc được ${f.name}.`); continue }
        setAtts((x) => [...x.filter((y) => y.name !== a.name), { name: a.name, file: a }])
      } catch {
        setFileNote(`Không mở được ${f.name}.`)
      }
    }
    if (picker.current) picker.current.value = ''
    box.current?.focus()
  }

  return (
    <div className={`tg-ask__card tg-chat ${leaving ? 'is-leaving' : ''}`} aria-busy={busy || leaving}>
      <div className="tg-ask__top">
        <BotAvatar size={40} live={thinking} />
        <span className="tg-ask__intent"><b>TRỢ LÝ TRIPGUARDIAN</b><span>{thinking ? 'đang đọc chuyến đi của bạn…' : 'kể tự nhiên, mình ghi lại'}</span></span>
      </div>
      <ol className="tg-chat__log" aria-live="polite" aria-label="Trò chuyện về chuyến đi">
        {msgs.map((m, i) => {
          const body = (
            <div className={`tg-chat__msg is-${m.who}`}>
              {m.text && <p>{m.text}</p>}
              {m.images?.length ? <div className="tg-chat__pics">{m.images.map((u) => <img key={u} src={u} alt="Ảnh bạn gửi" />)}</div> : null}
              {m.files?.length ? <p className="tg-chat__files">{m.files.map((n) => <span key={n}><Icon name="clip" size={13} />{n}</span>)}</p> : null}
            </div>
          )
          // the avatar sits by the first of a run of the assistant's messages
          return m.who === 'ai' ? <li key={i} className="tg-chat__line">{msgs[i - 1]?.who === 'ai' ? <span className="tg-chat__gap" /> : <BotAvatar />}{body}</li> : <li key={i} className="tg-chat__me">{body}</li>
        })}
        {thinking && (
          <li className="tg-chat__line"><BotAvatar live /><div className="tg-chat__msg is-ai is-live">
            <p>{live || 'Mình đang đọc chuyến đi của bạn'}{!live && <span className="tg-dots" aria-hidden="true"><i /><i /><i /></span>}</p>
            {reads.length > 0 && (
              <ul className="tg-chat__reads" aria-label="Mình đang ghi">
                {reads.map((r) => <li key={r.target}><span>“{r.quote}”</span><Icon name="arrow" size={13} /><b>{readLabel(r.target)}</b></li>)}
              </ul>
            )}
          </div></li>
        )}
        {summary && u && <li className="tg-chat__msg is-ai is-sum tg-chat__indent"><Understood u={u} card={card} quotes={quotes} preview={preview} onOpen={onOpen} onEdit={onEdit} /></li>}
      </ol>
      {summary && (
        <div className="tg-chat__go">
          <button type="button" className="tg-btn tg-btn--primary" disabled={busy || leaving} onClick={onGo}>{card ? 'Đúng rồi, hỏi tiếp' : 'Đúng rồi, bắt đầu tìm'} <Icon name="arrow" size={18} /></button>
        </div>
      )}
      <form
        className={`tg-chat__say ${drag ? 'is-drop' : ''}`}
        onSubmit={(e) => { e.preventDefault(); submit() }}
        onDragOver={(e) => { if (e.dataTransfer.types.includes('Files')) { e.preventDefault(); setDrag(true) } }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); attach(e.dataTransfer.files) }}
      >
        {(atts.length > 0 || fileNote) && (
          <div className="tg-chat__tray" aria-live="polite">
            {atts.map((a) => (
              <span key={a.name + (a.image ?? '')} className={`tg-chat__att ${a.image ? 'is-pic' : ''}`}>
                {a.image ? <img src={a.image} alt={a.name} /> : <><Icon name="clip" size={14} /><b>{a.name}</b></>}
                <button type="button" aria-label={`Bỏ ${a.name}`} onClick={() => setAtts((x) => x.filter((y) => y !== a))}><Icon name="x" size={12} /></button>
              </span>
            ))}
            {fileNote && <small role="alert">{fileNote}</small>}
          </div>
        )}
        <input ref={picker} type="file" accept={`image/*,${ACCEPT}`} multiple hidden onChange={(e) => attach(e.target.files)} />
        <button type="button" className="tg-chat__clip" disabled={leaving || busy} aria-label="Đính kèm ảnh hoặc file" title="Đính kèm ảnh hoặc file" onClick={() => picker.current?.click()}><Icon name="clip" size={18} /></button>
        <textarea
          id="tg-chat-box"
          ref={box}
          rows={1}
          value={text}
          disabled={leaving}
          onChange={(e) => setText(e.target.value)}
          onPaste={(e) => { if (e.clipboardData.files.length) { e.preventDefault(); attach(e.clipboardData.files) } }}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); submit() } }}
          placeholder={told ? 'Nhắn thêm hoặc sửa…' : 'Ví dụ: 3 ngày với người yêu, săn mây, cà phê view đồi…'}
        />
        <button type="submit" className="tg-chat__send" disabled={(!text.trim() && !atts.length) || busy || !ready} aria-label="Gửi"><Icon name="send" size={18} /></button>
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
