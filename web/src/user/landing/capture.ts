// Dev only (web/capture.html): the landing's scene drawn at chosen moments, for web/scripts/render_landing.mjs. Each
// call seeks the story timeline, draws one frame at a fixed clock and returns the picture with the labels' places.
import gsap from 'gsap'
import { fetchLandscape } from './bin'
import points from './points.json'
import { AREAS, FOCUS, SCENE_PLACES } from './route'
import { DalatScene, type SceneState } from './scene'
import { CLIP_H, CLIP_W, stateTweens } from './story'

declare global { interface Window { __cap?: { ready: () => boolean; frame: (time: number, t: number, dt: number, shot: boolean) => unknown } } }

const cv = document.getElementById('cv') as HTMLCanvasElement
Object.assign(cv.style, { width: `${CLIP_W}px`, height: `${CLIP_H}px` })
const land = await fetchLandscape()
const scene = DalatScene.create(cv, { points: points as [number, number][], five: SCENE_PLACES, focus: FOCUS, land }, false)!
scene.resize(CLIP_W, CLIP_H)
const dummy = (n: number) => Array.from({ length: n }, () => document.createElement('i'))
scene.bindLabels('five', dummy(SCENE_PLACES.length))
scene.bindLabels('area', dummy(AREAS.length), AREAS)
const state: SceneState = { cam: 0, dots: 1, five: 0, route: 0, travel: 0, areas: 1, shift: 0.2, hour: 0, stamp: 0, lift: 0 }
const tl = stateTweens(gsap.timeline({ paused: true, defaults: { ease: 'none' } }), state)
window.__cap = {
  ready: () => !scene.busy,
  frame(time, t, dt, shot) {
    tl.seek(time, false)
    scene.set({ ...state })
    const out = scene.capture(t, dt)
    return { ...out, tr: state.travel, png: shot ? scene.canvas.toDataURL('image/png') : null }
  },
}
