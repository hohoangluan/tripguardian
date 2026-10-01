// Mutable state shared between DOM (scroll, routing) and the WebGL scene.
// Read every frame inside useFrame, so it must not trigger React renders.
export type Mode = 'landing' | 'app'

export const story = {
  mode: 'landing' as Mode,
  progress: 0, // landing scroll progress, 0..1
  dive: 0, // 0..1 while the camera plunges into the mist between pages
  appStep: 0, // question index on /app, rotates the orbit
  pointer: { x: 0, y: 0 }, // -1..1, for subtle parallax
  reducedMotion:
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches,
}

export const clamp01 = (v: number) => Math.min(1, Math.max(0, v))

// Remap p from [a, b] to [0, 1], clamped.
export const span = (p: number, a: number, b: number) => clamp01((p - a) / (b - a))

export const smooth = (t: number) => t * t * (3 - 2 * t)
