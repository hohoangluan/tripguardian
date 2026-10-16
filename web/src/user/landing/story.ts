import type { SceneState } from './scene'

// The scroll story's camera and light as GSAP tweens on SceneState, in timeline units (beat i is fully in at time i).
// The live page adds its chapter text around them; the pre-render (web/scripts/render_landing.mjs) plays the same
// tweens frame by frame, so the video and the page tell one story.
export const STORY_LEN = 5.5

export function stateTweens(tl: gsap.core.Timeline, state: SceneState) {
  // the sky keeps the example day's clock: dawn at the start, sunset at the last stop
  tl.to(state, { hour: 0.15, duration: 1 }, 0)
    .to(state, { hour: 0.3, duration: 1 }, 1.1)
    .to(state, { hour: 0.4, duration: 1 }, 2.1)
    .to(state, { hour: 0.45, duration: 0.5 }, 3.15)
    .to(state, { hour: 1, duration: 0.8 }, 3.7)
    .to(state, { stamp: 1, duration: 0.5 }, 4.7)
    .to(state, { cam: 1, duration: 1 }, 0)
    .to(state, { areas: 0, duration: 0.4 }, 0.1)
    .to(state, { cam: 2, duration: 1 }, 1.1)
    .to(state, { dots: 0, duration: 0.6 }, 1.3)
    .to(state, { five: 1, duration: 0.5 }, 1.45)
    .to(state, { route: 1, duration: 0.4 }, 1.55)
    .to(state, { cam: 3, duration: 1 }, 2.1)
    .to(state, { cam: 4, duration: 1 }, 3.1)
    .to(state, { travel: 1, duration: 0.8 }, 3.7)
    .to(state, { cam: 5, duration: 1 }, 4.1)
  return tl
}

// Pre-rendered clips (docs/UI_SPEC_LANDING.md §2): each chapter rests at REST[i] with the cloud alive in a loop
// (idle-i), and the move between two chapters is its own short clip (to-i, and back-i played when scrolling up).
export const REST = [0, 0.95, 1.95, 2.95, 4.5, 5.5]
export const MOVE_S = [1.4, 1.4, 1.4, 2.6, 1.6] // seconds of the move from chapter i to i + 1 (the walk is the long one)
export const FPS = 30
export const IDLE_S = 3 // one way: the loop plays it forth and back, 2 × IDLE_S
export const CLIP_W = 1440
export const CLIP_H = 900

export interface ClipFrame { l: [number, number, number][]; m: { x: number; y: number; h: number } | null; tr: number }
export interface ClipTrack { w: number; h: number; fps: number; stops: number[]; clips: Record<string, ClipFrame[]> }
