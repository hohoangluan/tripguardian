import { useEffect, useRef, useState } from 'react'
import { info } from '../lib'
import { whyNot } from '../pd/api'
import { useDecision } from '../pd/decision'
import { editMsg, dismissNudge, openAssistant, pushMsg, useUi } from '../store'
import { useTrip } from '../trip'
import { searchPlaces } from '../tu/api'
import { ACCEPT, takeFiles, withAttachments, type Attachment } from '../tu/attach'
import { PlacePhoto } from './common'
import { openPlace } from './PlaceSheet'
import { BotAvatar, Icon } from './icons'
import { canListen, listen, setSound, speak, stopSpeaking, useVoice } from './voice'

const CHIPS = ['Yên tĩnh hơn', 'Ít di chuyển hơn', 'Thêm một chỗ ăn trưa', 'Vì sao không gợi ý Langbiang?']
// "vì sao không gợi ý X" is answered from the data (why-not), not by the agent.
const WHY_NOT = /(?:vì sao|tại sao|sao)\s+(?:không|chưa)\s+(?:gợi ý|thấy|có)\s+(.+?)\s*\??$/i

const SAY_MAX = 1000 // the Decision turn takes 1000 characters (src/decision/tools.py)

function useSend() {
  const { say, view } = useDecision()
  const { trip } = useTrip()
  return async (typed: string, files: Attachment[] = []) => {
    pushMsg({ role: 'user', text: typed, files: files.map((f) => f.name) })
    // A bot reply is read aloud only when the user turned sound on (speak checks).
    const finish = (id: number, patch: { text: string; places?: string[] }) => { editMsg(id, patch); speak(patch.text) }
    const why = WHY_NOT.exec(typed)
    if (why && trip.decisionId) {
      const bot = pushMsg({ role: 'bot', text: 'Mình tra trong dữ liệu…' })
      try {
        const hits = await searchPlaces(why[1])
        if (!hits.length) return finish(bot, { text: `Mình không thấy "${why[1]}" trong dữ liệu Đà Lạt của mình, nên không gợi ý được. Mình không đoán nơi khi chưa có dữ liệu.` })
        const r = await whyNot(trip.decisionId, hits[0].id)
        const shown = view?.groups.some((g) => g.cards.some((c) => c.id === hits[0].id))
        finish(bot, {
          text: shown ? `${r.name ?? hits[0].name} đang có trong danh sách gợi ý.` : r.listed ? `${r.name ?? hits[0].name}: ${r.reasons.join(' ')}.` : r.reasons.length ? `${r.name ?? hits[0].name}: ${r.reasons.join(' ')} Mình không tự bỏ giới hạn; muốn thì bạn nới ở vé chuyến, mình nói rõ cái giá.` : `${r.name ?? hits[0].name} chưa có lý do rõ để loại; có thể nó chỉ xếp sau những nơi hợp hơn.`,
          places: [hits[0].id],
        })
      } catch {
        finish(bot, { text: 'Chưa tra được, bạn thử lại sau nhé.' })
      }
      return
    }
    const bot = pushMsg({ role: 'bot', text: '' })
    let said = ''
    const diff = await say(withAttachments(typed, files, SAY_MAX), (soFar) => { said = soFar; editMsg(bot, { text: soFar }) })
    // The places that came in (a few), else the ones that left: a whole rebuilt list would bury the reply.
    const changed = diff ? (diff.added.length ? diff.added.slice(0, 6) : diff.removed.slice(0, 3)) : []
    if (changed.length) editMsg(bot, { places: changed })
    speak(said)
  }
}

const HELLO = 'Chào bạn, mình là TripGuardian, trợ lý ảo của chuyến đi này (không phải người thật). Nói điều bạn muốn đổi trong danh sách, ví dụ "bỏ mấy chỗ đông đi" hay "thêm một quán ăn tối gần hồ". Mọi thay đổi hiện ngay trên lưới và hoàn tác được.'
const MIC_PROBLEM: Record<string, string> = { 'not-allowed': 'Trình duyệt chưa cho dùng micro.', 'audio-capture': 'Không thấy micro.', network: 'Chưa nghe được vì mạng.', 'no-speech': 'Mình chưa nghe thấy gì, bạn thử nói lại nhé.', unavailable: 'Phần nghe giọng nói chưa sẵn sàng, bạn gõ giúp mình nhé.' }

function Body() {
  const a = useUi((u) => u.assistant)
  const { busy } = useDecision()
  const voice = useVoice()
  const send = useSend()
  const [text, setText] = useState('')
  const [files, setFiles] = useState<Attachment[]>([])
  const [note, setNote] = useState<string | null>(null)
  const [drag, setDrag] = useState(false)
  const [listening, setListening] = useState(false)
  const [sending, setSending] = useState(false) // the recording stopped and is being read
  const endRef = useRef<HTMLDivElement>(null)
  const picker = useRef<HTMLInputElement>(null)
  const stopMic = useRef<((discard?: boolean) => void) | null>(null)
  useEffect(() => { endRef.current?.scrollIntoView({ block: 'end' }) }, [a.msgs])
  useEffect(() => { document.getElementById('tg-asst-in')?.focus({ preventScroll: true }) }, [])
  // Closing the chat ends the voice: nothing keeps talking or listening behind a closed panel.
  useEffect(() => () => { stopSpeaking(); stopMic.current?.(true) }, [])
  const submit = (t: string) => {
    if ((!t.trim() && !files.length) || busy) return
    stopMic.current?.(true)
    send(t.trim(), files)
    setText('')
    setFiles([])
    setNote(null)
  }
  const attach = async (list: FileList | File[] | null) => {
    const got = await takeFiles(list, files)
    setFiles(got.files)
    setNote(got.note ?? (withAttachments('', got.files, SAY_MAX).length < withAttachments('', got.files, 1e9).length ? 'File dài: mình đọc phần đầu mỗi lượt (tối đa khoảng 30 dòng).' : null))
    if (picker.current) picker.current.value = ''
    document.getElementById('tg-asst-in')?.focus()
  }
  const toggleMic = () => {
    if (sending) return
    if (listening) { stopMic.current?.(); return }
    setNote(null)
    const base = text.trim()
    setListening(true)
    stopMic.current = listen(
      (heard) => setText((base ? base + ' ' : '') + heard),
      (problem) => { setListening(false); setSending(false); stopMic.current = null; if (problem) setNote(MIC_PROBLEM[problem] ?? 'Chưa nghe được, bạn thử lại hoặc gõ nhé.') },
      () => setSending(true),
    )
  }
  const status = sending ? 'đang đọc lời bạn…' : listening ? 'đang nghe bạn…' : busy ? 'đang nghĩ…' : voice.speaking ? 'đang nói…' : 'trợ lý ảo · sẵn sàng'
  const soundTitle = voice.sound ? 'Tắt giọng nói của trợ lý' : voice.down ? 'Giọng nói chưa sẵn sàng, trợ lý trả lời bằng chữ' : 'Bật giọng nói: trợ lý đọc to câu trả lời'
  return (
    <>
      <header className="tg-asst__head">
        <div className="tg-asst__who">
          <BotAvatar size={38} live={busy || voice.speaking || listening} />
          <div><h2>TripGuardian <em className="tg-asst__tag">Trợ lý AI</em></h2><small role="status">{status}</small></div>
        </div>
        <div className="tg-asst__ops">
          <button type="button" className={`tg-icon-btn tg-asst__snd ${voice.sound ? 'is-on' : ''}`} aria-pressed={voice.sound} onClick={() => setSound(!voice.sound)} aria-label={soundTitle} title={soundTitle}><Icon name={voice.sound ? 'volume' : 'volumeOff'} size={18} /></button>
          <button type="button" className="tg-icon-btn" onClick={() => openAssistant(false)} aria-label="Đóng khung chat" title="Đóng khung chat"><Icon name="x" size={18} /></button>
        </div>
      </header>
      {voice.speaking && (
        <div className="tg-asst__say" role="status">
          <span className="tg-wave" aria-hidden="true"><i /><i /><i /><i /></span>
          <span>Đang đọc to</span>
          <button type="button" className="tg-icon-btn" onClick={stopSpeaking} aria-label="Dừng đọc" title="Dừng đọc"><Icon name="stop" size={16} /></button>
          <button type="button" className="tg-icon-btn" onClick={() => setSound(false)} aria-label="Tắt tiếng" title="Tắt tiếng"><Icon name="volumeOff" size={16} /></button>
        </div>
      )}
      <div className="tg-asst__log" role="log" aria-live="polite">
        {a.msgs.length === 0 && <div className="tg-msg is-bot"><BotAvatar size={28} /><p>{HELLO}</p></div>}
        {a.msgs.map((m, i) => (
          <div key={m.id} className={`tg-msg is-${m.role}`}>
            {m.role === 'bot' && (a.msgs[i - 1]?.role === 'bot' ? <span className="tg-msg__gap" /> : <BotAvatar size={28} live={!m.text} />)}
            <p>
              {m.text || (m.role === 'bot' ? <span className="tg-dots" aria-label="Đang trả lời"><i /><i /><i /></span> : '')}
              {m.files?.length ? <span className="tg-msg__files">{m.files.map((n) => <span key={n}><Icon name="clip" size={13} />{n}</span>)}</span> : null}
              {m.role === 'bot' && m.text && <button type="button" className="tg-msg__read" onClick={() => speak(m.text, true)} aria-label="Đọc to câu này" title="Đọc to câu này"><Icon name="volume" size={14} /></button>}
            </p>
            {m.places && <div className="tg-msg__chips">{m.places.map((id) => <button key={id} type="button" className="tg-pchip" onClick={() => openPlace(id)}><PlacePhoto id={id} className="tg-pchip__ph" />{info(id)?.name ?? 'Xem nơi này'}</button>)}</div>}
          </div>
        ))}
        <div ref={endRef} />
      </div>
      <div className="tg-asst__chips" role="group" aria-label="Gợi ý câu hỏi">{CHIPS.map((c) => <button key={c} type="button" className="tg-chip" disabled={busy} onClick={() => submit(c)}>{c}</button>)}</div>
      <form
        className={`tg-asst__in ${drag ? 'is-drop' : ''}`}
        onSubmit={(e) => { e.preventDefault(); submit(text) }}
        onDragOver={(e) => { if (e.dataTransfer.types.includes('Files')) { e.preventDefault(); setDrag(true) } }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); attach(e.dataTransfer.files) }}
      >
        {(files.length > 0 || note) && (
          <div className="tg-chat__tray" aria-live="polite">
            {files.map((f) => (
              <span key={f.name} className="tg-chat__att">
                <Icon name="clip" size={14} /><b>{f.name}</b>
                <button type="button" aria-label={`Bỏ ${f.name}`} onClick={() => setFiles((x) => x.filter((y) => y !== f))}><Icon name="x" size={12} /></button>
              </span>
            ))}
            {note && <small role="alert">{note}</small>}
          </div>
        )}
        <input ref={picker} type="file" accept={ACCEPT} multiple hidden onChange={(e) => attach(e.target.files)} />
        <button type="button" className="tg-icon-btn" disabled={busy} onClick={() => picker.current?.click()} aria-label="Đính kèm file danh sách nơi" title="Đính kèm file danh sách nơi (.txt, .csv, .json, .kml)"><Icon name="clip" size={18} /></button>
        <label className="tg-sr" htmlFor="tg-asst-in">Nói với mình</label>
        <input id="tg-asst-in" className="tg-line-input" value={text} maxLength={1000} onChange={(e) => setText(e.target.value)}
          onPaste={(e) => { if (e.clipboardData.files.length) { e.preventDefault(); attach(e.clipboardData.files) } }}
          placeholder={listening ? 'Mình đang nghe…' : 'Nói với mình, ví dụ: yên tĩnh hơn đi'} autoComplete="off" />
        {canListen() && <button type="button" className={`tg-icon-btn tg-asst__mic ${listening ? 'is-live' : ''}`} aria-pressed={listening} disabled={busy} onClick={toggleMic} aria-label={listening ? 'Dừng nghe' : 'Nói bằng giọng'} title={listening ? 'Dừng nghe' : 'Nói bằng giọng (tiếng Việt)'}><Icon name="mic" size={18} /></button>}
        <button type="submit" className="tg-icon-btn" disabled={busy} aria-label="Gửi"><Icon name="send" size={18} /></button>
      </form>
    </>
  )
}

// The open chat is a column beside the list (Explore's layout), never a layer over the cards.
export function AssistantPinned() {
  return <aside className="tg-asst is-pinned" aria-label="Trợ lý"><Body /></aside>
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
          <button type="button" className="tg-fab" onClick={() => openAssistant(true)} aria-keyshortcuts="/" aria-label="Hỏi TripGuardian, trợ lý AI" title="Hỏi TripGuardian, trợ lý AI  ( / )"><BotAvatar size={36} /><span className="tg-fab__label">Hỏi mình</span>{a.nudge && <i className="tg-fab__dot" aria-hidden="true" />}</button>
        </div>
      )}
    </>
  )
}
