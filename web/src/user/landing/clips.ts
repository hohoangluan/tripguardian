// The landing's story as pre-rendered video (web/scripts/render_landing.mjs): no WebGL on the visitor's machine, the
// same picture everywhere. Each chapter rests on a looping clip (idle-i); reaching another chapter plays the move
// (to-i forward, back-i when scrolling up), one chapter at a time. Two <video> elements take turns, so a clip starts
// hidden and is swapped in on its first frame. Every shown frame hands the page its labels' places from track.json.
import type { ClipFrame, ClipTrack } from './story'

const BASE = '/landing/clips'
const RVFC = typeof HTMLVideoElement !== 'undefined' && 'requestVideoFrameCallback' in HTMLVideoElement.prototype
declare global { interface Window { __tgClip0?: Promise<Blob> } }

export class ClipPlayer {
  private videos: HTMLVideoElement[]
  private front = 0
  private beat = 0
  private target = 0
  private moving = false
  private name = 'idle-0'
  private urls = new Map<string, Promise<string>>()
  private gone = false
  private track: ClipTrack | null = null
  onFrame: (f: ClipFrame, track: ClipTrack) => void = () => {}
  onReady: () => void = () => {}

  constructor(host: HTMLElement, private beats: number) {
    this.videos = [0, 1].map(() => {
      const v = document.createElement('video')
      Object.assign(v, { muted: true, playsInline: true, preload: 'auto', disablePictureInPicture: true })
      v.setAttribute('aria-hidden', 'true')
      v.className = 'tg-l3__vid'
      host.appendChild(v)
      return v
    })
  }

  async start() {
    const track = fetch(`${BASE}/track.json`).then((r) => { if (!r.ok) throw new Error('track'); return r.json() as Promise<ClipTrack> })
    this.track = await track
    await this.show('idle-0', true)
    this.onReady()
    // the next chapters download while the visitor reads the first screen, nearest first
    for (let i = 0; i < this.beats - 1 && !this.gone; i++) {
      await this.url(`to-${i}`).catch(() => {})
      await this.url(`idle-${i + 1}`).catch(() => {})
    }
  }

  // the chapter the scroll is on now: the player gets there one move at a time
  go(beat: number) {
    this.target = Math.max(0, Math.min(this.beats - 1, beat))
    if (!this.moving) void this.step()
  }

  // where the cloud stands now (stage px), for the page's hand-off to the app logo
  mascot(box: { w: number; h: number }) {
    const f = this.frame()
    return f?.m ? this.place(f.m.x, f.m.y, box, f.m.h) : null
  }

  // a track point (render px) on a stage of `box` size: the video covers the stage, centred
  place(x: number, y: number, box: { w: number; h: number }, h = 0) {
    const t = this.track!
    const k = Math.max(box.w / t.w, box.h / t.h)
    return { x: x * k + (box.w - t.w * k) / 2, y: y * k + (box.h - t.h * k) / 2, h: h * k }
  }

  dispose() {
    this.gone = true
    for (const v of this.videos) { v.pause(); v.remove() }
    for (const u of this.urls.values()) void u.then(URL.revokeObjectURL, () => {})
  }

  private url(name: string) {
    let u = this.urls.get(name)
    if (!u) {
      const blob = name === 'idle-0' && window.__tgClip0 ? window.__tgClip0 : fetch(`${BASE}/${name}.mp4`).then((r) => {
        if (!r.ok) throw new Error(name)
        return r.blob()
      })
      u = blob.then((b) => URL.createObjectURL(b))
      u.catch(() => this.urls.delete(name))
      this.urls.set(name, u)
    }
    return u
  }

  private async step() {
    if (this.gone) return
    if (this.target === this.beat) return
    this.moving = true
    const up = this.target > this.beat
    const clip = up ? `to-${this.beat}` : `back-${this.beat - 1}`
    // a long jump runs the moves faster, so the picture catches up with the text
    const rate = Math.abs(this.target - this.beat) > 1 ? 2.2 : 1
    try {
      await this.show(clip, false, rate)
      await this.ended()
      this.beat += up ? 1 : -1
      if (this.target === this.beat) await this.show(`idle-${this.beat}`, true)
    } catch {
      // a clip that did not load: jump straight to the chapter's rest
      this.beat = this.target
      await this.show(`idle-${this.beat}`, true).catch(() => {})
    }
    this.moving = false
    if (this.target !== this.beat) void this.step()
  }

  // plays `name` on the hidden element and swaps it in once its first frame is up
  private async show(name: string, loop: boolean, rate = 1) {
    const src = await this.url(name)
    if (this.gone) return
    const next = this.videos[1 - this.front]
    next.loop = loop
    next.src = src
    next.playbackRate = rate
    await next.play()
    await new Promise<void>((done) => {
      if (RVFC) next.requestVideoFrameCallback(() => done())
      else next.addEventListener('timeupdate', () => done(), { once: true })
    })
    const old = this.videos[this.front]
    this.front = 1 - this.front
    this.name = name
    next.classList.add('is-on')
    old.classList.remove('is-on')
    old.pause()
    this.follow(next, name)
  }

  private ended() {
    const v = this.videos[this.front]
    return new Promise<void>((done) => v.addEventListener('ended', () => done(), { once: true }))
  }

  private frame(v = this.videos[this.front], name = this.name): ClipFrame | null {
    const frames = this.track?.clips[name]
    if (!frames?.length) return null
    return frames[Math.min(frames.length - 1, Math.round(v.currentTime * this.track!.fps))]
  }

  // every frame the element paints, the labels and the itinerary follow it
  private follow(v: HTMLVideoElement, name: string) {
    const tick = () => {
      if (this.gone || this.videos[this.front] !== v || this.name !== name) return
      const f = this.frame(v, name)
      if (f) this.onFrame(f, this.track!)
      if (RVFC) v.requestVideoFrameCallback(tick)
      else requestAnimationFrame(tick)
    }
    tick()
  }
}
