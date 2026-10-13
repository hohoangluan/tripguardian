import { useEffect, useRef, useState } from 'react'
import { ACCEPT, readAttachment, withAttachments, type Attachment } from '../../tu/attach'
import { Icon } from '../../ui/icons'

// The message box under the chat: words, a list file (read here into lines), or one photo. A photo is shrunk in the
// browser before it leaves (the journey request body is capped at 64 KB) and is only used for this trip.

export type Outgoing = { text: string; shown: string; files: string[]; photo: string | null }

const PHOTO_SIDE = 448 // the image model reads 384 px; a little more keeps detail after JPEG
const PHOTO_MAX_CHARS = 60_000

export async function shrink(file: File): Promise<string> {
  const bmp = await createImageBitmap(file)
  const k = Math.min(1, PHOTO_SIDE / Math.max(bmp.width, bmp.height))
  const c = document.createElement('canvas')
  c.width = Math.round(bmp.width * k)
  c.height = Math.round(bmp.height * k)
  c.getContext('2d')!.drawImage(bmp, 0, 0, c.width, c.height)
  for (const q of [0.82, 0.7, 0.55, 0.4]) {
    const url = c.toDataURL('image/jpeg', q)
    if (url.length <= PHOTO_MAX_CHARS) return url
  }
  throw new Error('too big')
}

export function Composer({ ready, busy, onSend }: { ready: boolean; busy: boolean; onSend: (m: Outgoing) => void }) {
  const [text, setText] = useState('')
  const [files, setFiles] = useState<Attachment[]>([])
  const [photo, setPhoto] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [drag, setDrag] = useState(false)
  const filePick = useRef<HTMLInputElement>(null)
  const photoPick = useRef<HTMLInputElement>(null)
  const box = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const el = box.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`
  }, [text])

  const attach = async (list: FileList | File[] | null) => {
    setNote(null)
    for (const f of Array.from(list ?? []).slice(0, 6)) {
      if (f.type.startsWith('image/')) {
        try { setPhoto(await shrink(f)) } catch { setNote(`Không mở được ảnh ${f.name || ''}. Thử ảnh JPG hoặc PNG khác nhé.`) }
        continue
      }
      try {
        const a = await readAttachment(f)
        if (!a.lines.length) { setNote(`Không đọc được ${f.name}.`); continue }
        setFiles((x) => [...x.filter((y) => y.name !== a.name), a])
      } catch {
        setNote(`Không mở được ${f.name}.`)
      }
    }
    if (filePick.current) filePick.current.value = ''
    if (photoPick.current) photoPick.current.value = ''
    box.current?.focus()
  }

  const submit = () => {
    const t = text.trim()
    if ((!t && !files.length && !photo) || busy || !ready) return
    onSend({ text: withAttachments(t, files), shown: t, files: files.map((f) => f.name), photo })
    setText('')
    setFiles([])
    setPhoto(null)
    setNote(null)
  }

  return (
    <div className="tg-cx__composer">
      <form
        className={`tg-cx__pill ${drag ? 'is-drop' : ''}`}
        onSubmit={(e) => { e.preventDefault(); submit() }}
        onDragOver={(e) => { if (e.dataTransfer.types.includes('Files')) { e.preventDefault(); setDrag(true) } }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); attach(e.dataTransfer.files) }}
      >
        {(files.length > 0 || photo || note) && (
          <div className="tg-cx__tray" aria-live="polite">
            {photo && <span className="tg-cx__att is-pic"><img src={photo} alt="Ảnh sẽ gửi" /><button type="button" aria-label="Bỏ ảnh" onClick={() => setPhoto(null)}><Icon name="x" size={12} /></button></span>}
            {files.map((f) => <span key={f.name} className="tg-cx__att"><Icon name="clip" size={14} /><b>{f.name}</b><button type="button" aria-label={`Bỏ ${f.name}`} onClick={() => setFiles((x) => x.filter((y) => y !== f))}><Icon name="x" size={12} /></button></span>)}
            {note && <small role="alert">{note}</small>}
          </div>
        )}
        <div className="tg-cx__row">
          <input ref={filePick} type="file" accept={ACCEPT} multiple hidden onChange={(e) => attach(e.target.files)} />
          <input ref={photoPick} type="file" accept="image/*" hidden onChange={(e) => attach(e.target.files)} />
          <button type="button" className="tg-cx__ib" aria-label="Đính kèm danh sách địa điểm" title="Đính kèm danh sách địa điểm" disabled={busy} onClick={() => filePick.current?.click()}><Icon name="clip" size={20} /></button>
          <button type="button" className="tg-cx__ib" aria-label="Gửi ảnh" title="Gửi ảnh nơi bạn thích" disabled={busy} onClick={() => photoPick.current?.click()}><Icon name="image" size={20} /></button>
          <textarea
            ref={box}
            rows={1}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onPaste={(e) => { if (e.clipboardData.files.length) { e.preventDefault(); attach(e.clipboardData.files) } }}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); submit() } }}
            placeholder="Kể thêm, hoặc gửi ảnh / link…"
            aria-label="Tin nhắn"
          />
          <button type="submit" className="tg-cx__send" disabled={(!text.trim() && !files.length && !photo) || busy || !ready} aria-label="Gửi"><Icon name="send" size={18} /></button>
        </div>
      </form>
      <p className="tg-cx__note">Ảnh bạn gửi chỉ dùng trong chuyến này.</p>
    </div>
  )
}
