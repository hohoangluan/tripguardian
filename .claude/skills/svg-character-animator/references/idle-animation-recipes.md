# Idle Animation Recipes

Implementation patterns for each idle preset, custom prompt translation, and the idle×morph blending pattern. Load when idle animation is involved.

## The persistence pattern (most important)

Idle animation should run continuously from component mount onward. **Never kill and recreate the idle timeline on state change.** Doing so causes visible stuttering — the user sees the character freeze for a frame before the new idle starts.

Instead:

1. One `IdleAnimator` instance per component, created at mount.
2. The animator's behavior is controlled by `currentStateRef.current` (read each frame, not closed over at construction time).
3. Amplitude is controlled by a separate `idleAmplitudeRef` that gets tweened during morphs.

```js
class IdleAnimator {
  constructor(svgEl, getKind, getAmplitude) {
    this.svgEl = svgEl;
    this.getKind = getKind;          // returns current state's idle preset name
    this.getAmplitude = getAmplitude; // returns current amplitude multiplier
    this.start = performance.now();
    this.cancelled = false;
    requestAnimationFrame(this.tick.bind(this));
  }

  tick(now) {
    if (this.cancelled) return;
    const t = (now - this.start) / 1000;
    const amp = this.getAmplitude();
    const kind = this.getKind();
    // ... apply transform based on kind, scaled by amp ...
    this.svgEl.style.transform = computeTransform(kind, t, amp);
    requestAnimationFrame(this.tick.bind(this));
  }

  cancel() { this.cancelled = true; this.svgEl.style.transform = ''; }
}
```

When the state changes:
- `getKind()` returns the new state's idle preset on the next frame — the visual behavior switches smoothly
- `getAmplitude()` is being tweened down to 0.1 by the morph code, so the switch happens at low amplitude (less noticeable)
- After morph completes, amplitude tweens back to 1.0, full-strength idle resumes

## The idle×morph blend (the calibration that matters)

These specific numbers matter. They were learned through iteration.

```js
// Inside runTransition, before starting morph tweens:
const rampDownDur = morphDurationMs * 0.4;  // 40% of morph duration
const rampDownStart = performance.now();
const rampDownFrom = idleAmplitudeRef.current;
const rampDownStep = (now) => {
  const t = Math.min(1, (now - rampDownStart) / rampDownDur);
  // Sine in-out for smooth in/out, not cubic-out (too abrupt)
  idleAmplitudeRef.current = rampDownFrom + (0.1 - rampDownFrom) * easeFns.easeInOutSine(t);
  if (t < 1) requestAnimationFrame(rampDownStep);
};
requestAnimationFrame(rampDownStep);

// Inside onComplete of morph timeline:
const rampUpDur = morphDurationMs * 0.4;
// ... similar tween from current amp back to 1.0
```

**Why these numbers:**
- **0.1 minimum (not 0.3, not 0):** at 0.3, the residual motion competes visually with the morph. At 0, the character feels dead. 0.1 is "subtly alive but not distracting."
- **40% ramp (not 20%):** 20% ramps too fast — looks like the idle was abruptly cut. 40% is smooth.
- **Sine in-out (not cubic out):** sine has gentle starts and ends, perfect for "this is a temporary pause." Cubic-out feels like an "arrival" curve, wrong semantics.

## The bottom-center pivot principle

All rotation and scale idle animations default to `transform-origin: 50% 100%` (bottom-center).

**Rationale:** characters typically stand on a ground plane. Rotating or scaling around their feet feels right. Rotating around their center makes them look like they're spinning in space.

**Exceptions:**
- Floating/hanging characters (ghost, balloon, jellyfish) → center-center
- Characters anchored from above (lamp, swing) → top-center

Apply as `this.svgEl.style.transformOrigin = "50% 100%"` whenever the preset uses rotation or scale.

## Per-preset implementation

### `sway` — gentle horizontal rotation

```js
case "sway":
  transform = `rotate(${2 * amp * Math.sin(t * 2 * Math.PI / 1.5)}deg)`;
  this.svgEl.style.transformOrigin = "50% 100%";
  break;
```

Amplitude: ±2° at full strength. Period: 1.5s. Sine wave. Reads as "tree in a light breeze."

### `breathe` — uniform scale on a slow loop

```js
case "breathe":
  transform = `scale(${1 + 0.02 * amp * (0.5 + 0.5 * Math.sin(t * 2 * Math.PI / 2.0))})`;
  this.svgEl.style.transformOrigin = "50% 100%";
  break;
```

Scale: 1.0 → 1.02 → 1.0. Period: 2s. The `(0.5 + 0.5 * sin)` keeps the scale ≥ 1.0 (no shrinking below normal size). Reads as "calm breathing."

### `bob` — vertical translation

```js
case "bob":
  transform = `translateY(${-3 * amp * (0.5 + 0.5 * Math.sin(t * 2 * Math.PI / 1.0))}px)`;
  this.svgEl.style.transformOrigin = "50% 100%";  // doesn't affect translate but consistent
  break;
```

Range: 0 to -3px (always above resting position). Period: 1s. Reads as "buoyant object floating."

### `shake` — quick wobble

```js
case "shake":
  transform = `rotate(${1 * amp * Math.sin(t * 2 * Math.PI / 0.3)}deg)`;
  this.svgEl.style.transformOrigin = "50% 100%";
  break;
```

Amplitude: ±1° (subtle — increase to ±3° for stronger reaction). Period: 0.3s (high frequency). Reads as "startled" or "trembling."

### `twinkle` — opacity flicker on decoration children

```js
case "twinkle": {
  // No whole-character transform; just animate selected children
  const twinkles = this.svgEl.querySelectorAll('[data-twinkle="true"]');
  twinkles.forEach((el, i) => {
    const phase = this.twinklePhases[i];  // precomputed random offset
    const period = 0.6 + (i * 0.13) % 0.4;
    const opacity = 0.75 + 0.25 * amp * Math.sin(t * 2 * Math.PI / period + phase);
    const scale = 0.92 + 0.08 * amp * Math.sin(t * 2 * Math.PI / period + phase);
    el.style.opacity = String(opacity);
    el.style.transform = `scale(${scale})`;
    el.style.transformOrigin = "50% 50%";  // twinkles pivot on themselves, not bottom
  });
  break;
}
```

Each twinkle child gets its own random phase and slightly different period for an organic, non-synchronized flicker. Use for stars, sparkles, or any decorative highlight.

### `sway-twinkle` — combo

Apply both the `sway` whole-character transform AND the twinkle child animations. Used for state-5 of the snowman (flower decorations twinkling while the character gently sways).

### `drift` — slow random-walk translation

```js
case "drift":
  // Two independent low-frequency sines on x and y, with different periods
  const dx = 5 * amp * Math.sin(t * 2 * Math.PI / 6.0);
  const dy = 5 * amp * Math.sin(t * 2 * Math.PI / 7.3);  // 7.3 vs 6.0 = noncommensurate, avoids loop
  transform = `translate(${dx}px, ${dy}px)`;
  break;
```

Range: ±5px on both axes. Periods: 6s and 7.3s — incommensurate so the motion never exactly repeats. Reads as "floating in water" or "dreamcore weightlessness."

## Custom prompt translation

When the user describes additional idle behavior in plain language:

### "Eyes blink every X seconds"

```js
const eyeIds = ids.filter(id => /eye/i.test(id));
const blink = () => {
  // Squash y-scale to ~0.1 for 80ms, restore
  eyeIds.forEach(id => {
    const el = document.getElementById(`path-${id}`);
    if (!el) return;
    gsap.to(el, {
      scaleY: 0.05, duration: 0.08, yoyo: true, repeat: 1,
      transformOrigin: "50% 50%"
    });
  });
  setTimeout(blink, 3000 + Math.random() * 2000);  // every 3-5s, randomized
};
blink();
```

### "Tail wags occasionally"

```js
const tailIds = ids.filter(id => /tail/i.test(id));
gsap.to(tailIds.map(id => `#path-${id}`), {
  rotation: 15 * amp, duration: 0.6, ease: "sine.inOut",
  yoyo: true, repeat: -1, transformOrigin: "0% 50%"  // tail base
});
```

### "Snore puff every few seconds" (for sleepy states)

```js
// Create a small <text> or shape that fades in/out at the nose position
const puff = createSnorePuff();  // your decoration helper
setInterval(() => {
  gsap.fromTo(puff, { opacity: 0, scale: 0.5, y: 0 },
    { opacity: 0.7, scale: 1.2, y: -10, duration: 1.5, ease: "sine.out",
      onComplete: () => gsap.to(puff, { opacity: 0, duration: 0.3 }) });
}, 4000 + Math.random() * 3000);
```

### Mapping body-part words to ids

```js
const BODY_PART_PATTERNS = {
  eye: /eye/i,
  mouth: /mouth/i,
  ear: /ear/i,
  tail: /tail/i,
  wing: /wing/i,
  arm: /arm|hand/i,
  leg: /leg|foot/i,
  hair: /hair/i,
  scarf: /scarf/i,
};
```

If the prompt mentions a body part that doesn't match any id, ask the user which id corresponds to that part rather than guessing.

## Reset before re-running

When the current state's idle preset changes (e.g., state-2's `breathe` switches to state-3's `bob`), the SVG element may have leftover `transform` from the previous preset. Before re-running:

```js
this.svgEl.style.transform = '';
```

Without this, the bob preset might start with a stuck rotation from the previous sway, causing a visible jump.

Apply the reset inside the idle animator's `tick` when the kind changes:

```js
tick(now) {
  // ...
  const kind = this.getKind();
  if (kind !== this.lastKind) {
    this.svgEl.style.transform = '';
    this.lastKind = kind;
  }
  // ... apply new transform for this kind ...
}
```

## Case study: the snowman's five-state idle vocabulary

A worked example of how the primitives compose across one character. The snowman has five emotional states; each picks idle primitives that read as that emotion, and the same `IdleAnimator` instance drives all of them — only `STATES[current].idle` is swapped, the timeline never restarts.

| State | Idle config | Why this reads as the emotion |
|---|---|---|
| state-1 (neutral) | `{ kind: "sway", duration: 3.0, amplitude: 2 }` | ±2° rotation around bottom-center, 3s period. Slow, single primitive — the baseline "alive but calm." |
| state-2 (content) | `{ kind: "breathe-y", duration: 3.5, amplitude: 0.025 }` | Vertical-only scale, full sine wave (symmetric around 1.0). Reads as steady breathing, not pulsing. Note: prefer `breathe-y` over the older `breathe` half-wave for snowmen and any character that stands upright — `breathe` reads as a heartbeat pulse. |
| state-3 (content+) | same as state-2 | Same idle as a neighboring state can be intentional — implies "this state shares the same energy, only the silhouette differs." Don't add motion variety just for variety's sake. |
| state-4 (excited) | `compound` of `waggle-sequence` (body) + two gated `rotate-around-point` (hands) | The body sweeps left→right→left with sine ramps and tiny holds at extremes (no slamming). The hands rotate around their *own* anatomical pivots, but only during the body's rest phase — the gate (`gateRange: [0.50, 0.96]` of a shared `gateCycle: 4.5`) silences hand motion during the body sweep so it doesn't visually compete. Reads as "wiggling with excitement, then waving." |
| state-5 (joyful) | `compound` of `breathe-y` (body) + two `rotate-around-point` (hands, ungated) | Breathing torso plus subtle hand sway around their pivots. The flower particles emerging from behind the head (`spawnArc` + `layer: "behind"`) carry the "joyful" feeling — the body itself stays calm so the particles read clearly. |

### Three transferable patterns from the snowman

**1. Compound configs let you separate body motion from limb motion.** Body parts have their own anchors (feet for the torso, shoulder/wrist for hands). Trying to do all motion with one whole-character transform looks robotic. Decompose into:
- A "body" part with `transform-origin: 50% 100%` (bottom-center)
- One `rotate-around-point` per limb with `pivot: [x, y]` at the limb's anatomical joint

```js
{
  kind: "compound",
  parts: [
    { kind: "breathe-y", duration: 3.5, amplitude: 0.025 },           // torso
    { kind: "rotate-around-point", selector: "#path-handl",
      pivot: [105.741, 210.402], amplitude: 6, duration: 1.0 },       // left hand
    { kind: "rotate-around-point", selector: "#path-handr",
      pivot: [194, 215.475], amplitude: -6, duration: 1.0 }           // right hand (negative = mirrored)
  ]
}
```

The pivots are real coordinates in the SVG's viewBox — read them off the source SVG (often the bbox center of the joint area, or the wrist point if visible). Get this wrong and the limb appears to swing from somewhere absurd (the head, the floor).

**2. Gating prevents competing motion.** When a body sweep and a hand wave would both be running simultaneously, the eye gets confused — "what's the main thing?" Pick one to be primary and gate the other on the primary's rest phase:

```js
{ kind: "rotate-around-point", selector: "#path-handl",
  pivot: [102.12, 207.692], amplitude: 10, duration: 0.55,
  gateCycle: 4.5,                  // same as the waggle's cycleDuration
  gateRange: [0.50, 0.96],         // hand-wave active during second half (waggle's rest)
  gateFade: 0.05 }                 // 5% fade-in/out at gate boundaries
```

Inside the gate range, full amplitude. Outside, zero. The 5% fade-in/out at the edges prevents click-on/click-off jarring. Synchronize by giving both parts the same cycle length (here 4.5s).

**3. Same idle preset across emotionally-similar states is fine.** Don't change idle just to differentiate states — the silhouette difference already does that work. Changing idle when the *energy* of the state changes (calm → excited → joyful) is meaningful; changing it within an energy band reads as visual noise.

### Naming convention worth keeping

The snowman uses anatomical id names (`handl`, `handr`, `eyel`, `eyer`, `nose`, `body`, `head`, `button1`, `button2`). The `rotate-around-point` `selector` field uses `#path-<id>` because the renderer prefixes shared-path DOM ids with `path-`. If you rename ids, update the selectors too. Keep ids stable across states or strategy detection breaks.

## Performance notes

Idle runs forever, at 60fps. With 5 simultaneous components running idle, that's 300 transform-style updates per second. This is fine on desktop but can stutter on mobile if combined with other rAF loops.

For optimization:
- Use `transform` (composited) rather than per-frame path rewriting for idle
- Pause idle when component is off-screen via IntersectionObserver
- Avoid animating large numbers of twinkle children — group them into a single CSS animation if there are more than ~20
