# Motion Design Basics for SVG Morphs

The 12 classical animation principles, distilled for the specific case of morphing vector graphics in code. Read this when designing custom timing or diagnosing why a morph feels off.

## The four that matter most for SVG morphs

### 1. Easing (slow in, slow out)
Real things don't move linearly. They accelerate and decelerate. **Linear easing on a morph almost always feels wrong** — it reads as mechanical even when the shape itself is organic.

- `power2.inOut` — the safe default. Symmetric, gentle.
- `power3.out` — for "arriving" motions (state opens, modal appears). Front-loaded speed, soft landing.
- `back.out(1.7)` — for playful bounces. The number controls overshoot magnitude (1.0 subtle, 2.0 cartoony).
- `sine.inOut` — for ambient/idle motion. Smoothest possible curve, no perceived "boundary."
- `expo.out` — for snappy UI feedback (button toggles). Almost-instant start, very soft end.

Avoid `linear` except for opacity fades and continuous rotations.

### 2. Anticipation
Before a big move, real things often pull back slightly in the opposite direction. A character about to jump crouches first.

For SVG morphs, anticipation is added as a brief pre-morph keyframe:
```js
tl.to(target, { scale: 0.95, duration: 0.1 })  // anticipation
  .to(target, { d: nextPath, duration: 1.0 });  // the move (your morph tween)
```

Use anticipation when:
- The morph is large/dramatic (face → mask, character → vehicle)
- The user wants "punch" or "weight"
- The aesthetic is `playful` or `bouncy`

Skip anticipation for:
- Small ambient transitions
- `dreamy` or `ambient-loop` aesthetics
- Anything tagged `subtle` or `vintage`

### 3. Follow-through and overlapping action
Different parts of a character don't all stop at the same instant. A tail keeps swinging after the body stops; eyes settle after the head. This is **stagger** in motion-design language.

For SVG morphs, stagger is implemented by offsetting the start of each sub-path's morph by a small delta:
```js
tl.to(paths, {
  d: i => nextPaths[i],  // your morph tween per path
  stagger: 0.05,  // each path starts 50ms after the previous
  duration: 1.0,
});
```

Stagger order matters:
- **Anatomical priority** (eyes → mouth → body) for character-emotion shifts
- **Center-out** for radial expansions
- **Random** for chaotic/dreamcore feels
- **None (sync)** for icon toggles where parts feel like a single unit

### 4. Idle motion (the "alive" trick)
This isn't in the classical 12 principles, but it's the single biggest thing that separates "icon" from "character." A static-then-morph-then-static pattern reads as machine. Continuous low-amplitude idle motion underneath transitions reads as organism.

Implementation: a separate, always-running timeline targeting either the whole component (sway, bob, breathe) or specific sub-paths (twinkle, blink). During morphs, scale this timeline's amplitude down to ~30%, never to zero. After morph, ramp back to 100%.

## The other principles, applied briefly

- **Squash and stretch** — for SVG, this means non-uniform scale during morph (`scaleX: 1.1, scaleY: 0.9` at midpoint). Use sparingly, mainly with `bouncy` aesthetic.
- **Arc** — natural motion follows curves, not straight lines. If a sub-path is translating during morph, give it a slight Y-curve via a midpoint keyframe rather than straight A→B.
- **Timing** — duration encodes mass. Heavier objects need longer durations. A logo morph: 0.4s. A character emotion shift: 1.2s. An ambient loop: 3s+.
- **Exaggeration** — for kawaii/playful work, push amplitudes 20-30% beyond what feels "correct." The exaggeration is what makes it readable as cute.
- **Solid drawing**, **appeal**, **straight ahead vs pose-to-pose**, **secondary action**, **staging** — these are more about the design itself than the morph implementation.

## Diagnostic: why does my morph feel off?

| Symptom | Likely cause | Fix |
|---|---|---|
| Mechanical, robotic | Linear easing | Switch to `power2.inOut` or `sine.inOut` |
| Jarring, abrupt | Too short duration | Increase duration; consider `power3.out` for soft landing |
| Floaty, unsatisfying | No stagger or anticipation | Add stagger (0.03-0.08s) or pre-morph anticipation |
| Dead-feeling between morphs | No idle animation | Add `breathe` or `sway` idle preset |
| Shape "unwinds" weirdly | Point matching picks a bad start-point offset | Rotate the path's start point so both states begin at the same anatomical spot |
| Parts collide or overshoot wildly | Auto-stagger fighting overshoot | Reduce `back.out()` magnitude or remove stagger |

## Quick durations cheat sheet

- 0.15-0.3s — micro-interactions (hover, tap feedback)
- 0.3-0.6s — UI state changes (icon toggle, button state)
- 0.8-1.5s — content transitions (page sections, character emotions)
- 1.5-3s — narrative/dramatic transitions (scene changes)
- 3s+ — ambient loops, breathing, idle

If you're outside these ranges, have a reason.
