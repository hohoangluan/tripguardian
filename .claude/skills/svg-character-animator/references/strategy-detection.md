# Strategy Detection

For each shared path id across states, decide which of two strategies to use. This decision happens once at component init and is fixed for the lifetime of the component (states don't change at runtime).

## The decision tree

```
For each shared id:
  fp = unique structure fingerprints across states (after normalization)

  if fp.size === 1:  TRANSFORM
  else:              MORPH
```

That's the whole thing. Path normalization (see `path-normalization.md`) is what gives this decision tree teeth — by collapsing equivalent-but-syntactically-different paths to the same fingerprint, it moves the maximum number of ids into TRANSFORM.

## Why only two strategies

Earlier versions of this skill defined four (`TRANSFORM`, `TRANSFORM_CROSSFADE`, `MORPH`, `MORPH_CROSSFADE`), where the two crossfade variants stacked one copy of the path per state and tweened opacity to swap fills smoothly during the morph. We removed them because:

- **Marginal visual gain.** A clean fill-snap at morph-end is usually indistinguishable from a crossfaded one, especially with sub-second durations. Users don't notice; the underlying shape morph dominates perception.
- **Significant complexity.** N stacked copies per crossfaded id, N parallel tweens, N opacity sub-tweens, N×N DOM nodes. The render-once-mutate-via-ref invariant gets harder to preserve.
- **The fill axis isn't load-bearing.** When two states genuinely need different fills, the right answer is usually to normalize the source (use the same gradient, swap colours via stops) rather than morph between two paint servers.

If you truly need fill differences mid-morph, the tween runner now snaps the destination fill at morph end via `target.setAttribute("fill", toFill)` — instant and reliable, no stacked copies.

## Implementation

```js
function detectStrategy(id, STATES) {
  const stateNames = Object.keys(STATES);
  const fps = stateNames.map(sn => {
    const p = STATES[sn].paths[id];
    if (!p) return null;
    return structureFingerprint(getPathDOf(p));
  });
  // If any state lacks this id, the id is an orphan, not shared.
  // Strategy detection only runs on shared ids, so fps.some(null) means
  // something's wrong with shared-id computation.
  if (fps.some(f => f === null)) return "MORPH";
  return new Set(fps).size === 1 ? "TRANSFORM" : "MORPH";
}
```

## Example outputs (snowman test case)

After path normalization (H/V → L) and circle/ellipse → bezier:

```
body       structure=diff  → MORPH       (5 hand-drawn variations of an oval)
head       structure=same  → TRANSFORM
eyel       structure=same  → TRANSFORM
eyer       structure=same  → TRANSFORM
nose       structure=same  → TRANSFORM
handl      structure=same  → TRANSFORM   (multi-subpath, split at render)
handr      structure=same  → TRANSFORM   (multi-subpath, split at render)
button1    structure=same  → TRANSFORM
button2    structure=same  → TRANSFORM
```

8 of 9 shared paths use TRANSFORM. Only `body` invokes flubber.

## When MORPH actually fires

In practice, MORPH only fires when the user is morphing between genuinely different shapes — e.g., a hamburger menu (3 horizontal lines, MLMLML structure) into a close X (2 diagonal lines, MLML structure). The fingerprints differ, so we hand the two `d` strings to flubber.

Even then, for icon-style work with simple shapes, MORPH quality is usually acceptable. The polygon character is hidden by speed (snappy easing, short duration). Where MORPH falls down is slow, large, organic shapes — exactly the cases where the artist would also benefit from manually matching point counts in Figma.

## Strategy-specific implementation notes

### TRANSFORM

```js
function runTransformTween({ target, fromD, toD, durationMs, easeFn, ... }) {
  // RAF loop, lerp each control point each frame, setAttribute('d', interpD)
}
```

Also tween the SVG `transform` attribute alongside `d` — see `transform-interpolation.md`. State-1's head has `transform="rotate(13)"` while others don't; without this, the head appears rotated for the first frame then snaps.

### MORPH

```js
function runMorphTween({ target, fromD, toD, durationMs, easeFn, isSmall }) {
  const interpolator = flubber.interpolate(fromD, toD, {
    maxSegmentLength: isSmall ? 0.5 : 2
  });
  // RAF loop, setAttribute('d', interpolator(t))
}
```

Set `maxSegmentLength: 0.5` for small shapes (eyes, buttons) so polygon sampling stays fine enough to look like a curve. For larger shapes, 2 is fine.

## Handling fill differences

When the destination state's fill differs from the current, snap at the end of the morph:

```js
if (fromPath.fill && toPath.fill && fromPath.fill !== toPath.fill) {
  setTimeout(() => target.setAttribute("fill", toPath.fill), durationMs + offset);
}
```

No tween, no crossfade. If a user later complains the fill swap is too abrupt, the right fix is at the source (normalize fills across states) — not in the runtime.

## What strategy detection does NOT solve

- **Multi-subpath splitting** — that's a separate render-layer concern. Even a TRANSFORM strategy path with `M L M L M L` (multi-stroke) needs splitting at render time so each subpath becomes its own `<path>` element. The strategy applies to each subpath independently.
- **Anatomical stagger order** — strategy is *what* to tween; the scenario preset controls *when* each id starts tweening relative to others. They're independent.
- **Orphan handling** — orphans don't have a strategy because they don't morph. They fade in/out per state via opacity tweens.

## Debugging tip

Always render a "strategy panel" in the demo wrapper showing each shared id's assigned strategy. When the user reports a quality issue, the strategy assignment is usually the first place to look.

```jsx
<div className="strategy-panel">
  Strategy per shared path: {SHARED_IDS.map(id => (
    <span key={id}><code>{id}</code>:{STRATEGY[id]}</span>
  ))}
</div>
```
