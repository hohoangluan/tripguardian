// The assistant's voice. Out: the bot reads its reply aloud through POST /api/harness/speech (role TTS, src/speech)
// only when the user turned sound on (default off, remembered in this browser) or pressed "read this" on one reply.
// In: the browser's Web Speech API (vi-VN), when it has one. Any failure leaves the text, which is always shown.
import { useSyncExternalStore } from 'react'

const SOUND_KEY = 'tg.asst.sound'
const RETRY_AFTER_MS = 5 * 60_000 // a TTS host that answered "unavailable" is not asked again for a while

interface VoiceState {
  sound: boolean
  speaking: boolean // fetching or playing
  down: boolean // the host said it is not available
}

const readSound = () => {
  try {
    return localStorage.getItem(SOUND_KEY) === '1'
  } catch {
    return false
  }
}

let state: VoiceState = { sound: readSound(), speaking: false, down: false }
let downAt = 0
const subs = new Set<() => void>()
const set = (patch: Partial<VoiceState>) => {
  state = { ...state, ...patch }
  subs.forEach((f) => f())
}
const subscribe = (f: () => void) => {
  subs.add(f)
  return () => subs.delete(f)
}
export const useVoice = () => useSyncExternalStore(subscribe, () => state)

let audio: HTMLAudioElement | null = null
let url: string | null = null
let ctl: AbortController | null = null
let ticket = 0 // a newer speak() or a stop invalidates an older one still fetching

export function stopSpeaking() {
  ticket++
  ctl?.abort()
  ctl = null
  if (audio) { audio.pause(); audio.removeAttribute('src'); audio = null }
  if (url) { URL.revokeObjectURL(url); url = null }
  if (state.speaking) set({ speaking: false })
}

export function setSound(on: boolean) {
  try {
    localStorage.setItem(SOUND_KEY, on ? '1' : '0')
  } catch {
    /* private mode: lasts until reload */
  }
  if (!on) stopSpeaking()
  set({ sound: on, down: on ? false : state.down })
  if (on) downAt = 0
}

// `asked`: the user pressed "read this reply", which works with sound off. Otherwise speech needs sound on.
export async function speak(text: string, asked = false) {
  if (!text.trim() || (!asked && !state.sound)) return
  if (state.down && Date.now() - downAt < RETRY_AFTER_MS) return
  stopSpeaking()
  const mine = ticket
  const mineCtl = (ctl = new AbortController())
  set({ speaking: true, down: false })
  try {
    const r = await fetch('/api/harness/speech', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text.slice(0, 2000) }),
      signal: mineCtl.signal,
    })
    if (!r.ok) {
      if (r.status === 503 && mine === ticket) { downAt = Date.now(); set({ down: true }) }
      throw new Error(String(r.status))
    }
    const blob = await r.blob()
    if (mine !== ticket) return
    url = URL.createObjectURL(blob)
    const a = (audio = new Audio(url))
    a.onended = a.onerror = () => { if (mine === ticket) stopSpeaking() }
    await a.play() // refused by the browser's autoplay rules: silent, the text is there
  } catch {
    if (mine === ticket) stopSpeaking()
  }
}

// --- speech in -------------------------------------------------------------------------------------------------
// The browser records (MediaRecorder); the server turns the recording into text with the ASR role (ChunkFormer,
// POST /api/harness/transcribe). The user taps to start and taps to stop; a recording ends by itself after MAX_MS.

const MAX_MS = 30_000
const MIN_BYTES = 1500 // shorter than this holds no word
const MIME = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg']

export const canListen = () =>
  typeof window !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined'

// Starts recording. onText gets the transcript once, when the recording has been read; onEnd(problem) always follows.
// onSending: the recording stopped and is being read. Returns stop(discard): stop(true) throws the recording away.
export function listen(onText: (t: string) => void, onEnd: (problem: string | null) => void, onSending?: () => void): (discard?: boolean) => void {
  stopSpeaking() // the bot does not talk over the user
  let stream: MediaStream | null = null
  let rec: MediaRecorder | null = null
  let timer: ReturnType<typeof setTimeout> | undefined
  let stopped = false
  let discard = false
  const release = () => { clearTimeout(timer); stream?.getTracks().forEach((t) => t.stop()); stream = null }
  const finish = (problem: string | null) => { release(); onEnd(problem) }
  navigator.mediaDevices.getUserMedia({ audio: true }).then(
    (s) => {
      stream = s
      if (stopped) return finish(null)
      const type = MIME.find((m) => MediaRecorder.isTypeSupported(m))
      const r = (rec = new MediaRecorder(s, type ? { mimeType: type } : undefined))
      const chunks: Blob[] = []
      r.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data) }
      r.onstop = async () => {
        release()
        const blob = new Blob(chunks, { type: r.mimeType || type || 'audio/webm' })
        if (discard) return onEnd(null)
        if (blob.size < MIN_BYTES) return onEnd('no-speech')
        onSending?.()
        try {
          const res = await fetch('/api/harness/transcribe', { method: 'POST', headers: { 'Content-Type': blob.type }, body: blob })
          if (res.ok) { onText(((await res.json()) as { text: string }).text); return onEnd(null) }
          onEnd(res.status === 400 ? 'no-speech' : res.status === 503 ? 'unavailable' : 'network')
        } catch {
          onEnd('network')
        }
      }
      r.start()
      timer = setTimeout(() => { if (r.state !== 'inactive') r.stop() }, MAX_MS)
    },
    (e: DOMException) => finish(e?.name === 'NotAllowedError' ? 'not-allowed' : e?.name === 'NotFoundError' ? 'audio-capture' : 'start'),
  )
  return (d = false) => {
    stopped = true
    discard = d
    if (rec && rec.state !== 'inactive') rec.stop()
    else if (!rec && stream) finish(null)
  }
}
