import { useEffect, useRef, useState } from 'react'
import { ACCEPT, readAttachment, withAttachments, type Attachment } from '../../tu/attach'
import { Icon } from '../../ui/icons'

// The message box under the chat: words, a list file (read here into lines), or one photo. A photo is shrunk in the
// browser before it leaves (the journey request body is capped at 64 KB) and is only used for this trip.

export type Outgoing = { text: string; shown: string; files: string[]; photo: string | null }

const PHOTO_SIDE = 448 // the image model reads 384 px; a little more keeps detail after JPEG
const PHOTO_MAX_CHARS = 60_000

// A browser may leave the type empty for a photo (HEIC, a file dragged from a chat app): the extension tells.
const isPicture = (f: File) => f.type.startsWith('image/') || /\.(jpe?g|png|webp|gif|bmp|avif|heic|heif)$/i.test(f.name)

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

export function Composer({ ready, busy, onSend, seed, incoming, dragging }: { ready: boolean; busy: boolean; onSend: (m: Outgoing) => void; seed?: { text: string; n: number } | null; incoming?: { files: File[]; n: number } | null; dragging?: boolean }) {
  const [text, setText] = useState('')
  const [files, setFiles] = useState<Attachment[]>([])
  const [photo, setPhoto] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const filePick = useRef<HTMLInputElement>(null)
  const photoPick = useRef<HTMLInputElement>(null)
  const box = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const el = box.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`
  }, [text])

  useEffect(() => {
    if (incoming?.files.length) void attach(incoming.files)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [incoming])

  useEffect(() => {
    if (!seed) return
    setText(seed.text)
    box.current?.focus()
  }, [seed])

  const attach = async (list: FileList | File[] | null) => {
    setNote(null)
    const all = Array.from(list ?? []).slice(0, 6)
    const pics = all.filter(isPicture)
    if (pics.length) { // one photo goes with a message: the first one that opens is kept
      let kept = false
      for (const f of pics) {
        if (kept) break
        try { setPhoto(await shrink(f)); kept = true } catch { /* try the next one */ }
      }
      setNote(!kept ? `Không mở được ảnh ${pics[0].name || ''}. Thử ảnh JPG, PNG hoặc WebP khác nhé.`
        : pics.length > 1 ? 'Mỗi tin nhắn mình đọc một ảnh, đã lấy ảnh đầu tiên. Ảnh còn lại bạn gửi ở tin sau nhé.' : null)
    }
    for (const f of all) {
      if (isPicture(f)) continue
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
        className={`tg-cx__pill ${dragging ? 'is-drop' : ''}`}
        onSubmit={(e) => { e.preventDefault(); submit() }}
      >
        {(files.length > 0 || photo || note) && (
          <div className="tg-cx__tray" aria-live="polite">
            {photo && <span className="tg-cx__att is-pic"><img src={photo} alt="Ảnh sẽ gửi" /><button type="button" aria-label="Bỏ ảnh" onClick={() => setPhoto(null)}><Icon name="x" size={12} /></button></span>}
            {files.map((f) => <span key={f.name} className="tg-cx__att"><Icon name="clip" size={14} /><b>{f.name}</b><button type="button" aria-label={`Bỏ ${f.name}`} onClick={() => setFiles((x) => x.filter((y) => y !== f))}><Icon name="x" size={12} /></button></span>)}
            {note && <small role="alert">{note}</small>}
          </div>
        )}
        <input ref={filePick} type="file" accept={ACCEPT} multiple hidden onChange={(e) => attach(e.target.files)} />
        <input ref={photoPick} type="file" accept="image/*" multiple hidden onChange={(e) => attach(e.target.files)} />
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
        <div className="tg-cx__row">
          <button type="button" className="tg-cx__ib" aria-label="Đính kèm danh sách địa điểm" title="Đính kèm danh sách địa điểm" disabled={busy} onClick={() => filePick.current?.click()}><Icon name="clip" size={19} /></button>
          <button type="button" className="tg-cx__ib" aria-label="Gửi ảnh" title="Gửi ảnh nơi bạn thích" disabled={busy} onClick={() => photoPick.current?.click()}><Icon name="image" size={19} /></button>
          <button type="submit" className="tg-cx__send" disabled={(!text.trim() && !files.length && !photo) || busy || !ready} aria-label="Gửi"><Icon name="send" size={18} /></button>
        </div>
      </form>
      <p className="tg-cx__note">Ảnh bạn gửi chỉ dùng trong chuyến này.</p>
    </div>
  )
}
