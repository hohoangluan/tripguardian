# Morph Library Comparison

What each JS SVG-morph library actually does, when it shines, when it fails. Read whenever choosing a library for the MORPH strategy or explaining tradeoffs to the user.

## The honest framing

All commonly-used SVG morph libraries are **polygon interpolators**, not bezier interpolators. They sample input paths into point arrays at a configurable resolution, pad the shorter array to match the longer, then linearly interpolate point-by-point. The output is always a polygon — even if the inputs were beziers.

This is why the TRANSFORM strategy beats every library on quality when it's applicable: TRANSFORM keeps the original beziers and lerps each control point. The libraries only matter when paths have genuinely different topology.

## The libraries

### flubber (MIT, unmaintained since 2019)

**API:** `flubber.interpolate(d1, d2, { maxSegmentLength: N })` returns a function `t => d_at_t`.

**Sampling:** every `maxSegmentLength` units along the path. Smaller = smoother but slower. Default 10. For small shapes use 0.5.

**Limitations:**
- First subpath only (multi-`M` paths are partially ignored)
- Forces closed shapes (open strokes get closed under the hood, breaking line caps)
- Filled shapes only — designed for path interpolation between closed regions
- Polygon output (loses bezier curves)

**When it shines:** filled organic shapes of similar size, moderate detail. Body morphs, blob shapes, illustration fills.

**When it fails:** open strokes (hands), very small shapes (eyes/buttons go triangular), paths with multiple subpaths.

**Verdict:** the default for our MORPH strategy. Solid for what it does, just don't expect miracles.

### Anime.js v4 (MIT)

**API:** `anime({ targets, d: anime.svg.morphTo('#destination'), duration, ease })`.

**Sampling:** polygon-based, similar to flubber. Default precision is reasonable but configurable.

**Improvements over flubber:**
- Native support for `<circle>`, `<rect>`, `<ellipse>`, `<polygon>` — no need for our `ellipseToPath` helper
- Active maintenance, modern v4 API
- Built-in easings, timelines, sequencing

**Limitations:**
- Same first-subpath-only constraint as flubber
- Same polygon output character

**When it shines:** when the user wants a general-purpose animation engine, not just morph. The broader API (timelines, scroll triggers, etc.) is useful for full apps.

**When it fails:** same cases as flubber. The morph quality is comparable.

**Verdict:** good alternative to flubber. If the rest of the app already uses Anime.js, use it. Otherwise the simplicity of flubber wins.

### KUTE.js (MIT)

**API:** `KUTE.fromTo('#a', { path: '#a' }, { path: '#b' }, { duration, easing })`.

**Sampling:** polygon-based. Has two morph components — `svgMorph` (default, polygon) and `svgCubicMorph` (cubic-bezier-aware but limited).

**Improvements:**
- Active maintenance
- Two morph modes, though cubic mode has its own limitations (no multi-subpath support either, per the v2.0.14 release notes)

**Limitations:**
- Same first-subpath constraint
- The cubic mode's restrictions aren't well-documented; we hit unexpected behavior in our snowman tests
- API less intuitive than flubber for one-off morphs

**Verdict:** no clear advantage over flubber for our typical case. Skip unless the user specifically requests it.

### Motion (formerly Framer Motion) (MIT)

**API:** `<motion.path animate={{ d: nextD }} />` — declarative React.

**Under the hood:** uses flubber when paths are too different to interpolate directly, otherwise tries direct interpolation. This is roughly the same architecture as our skill: detect strategy, route to library only when needed.

**When it shines:** React apps already using Motion for other animations. Cleaner API than imperative flubber calls.

**When it fails:** same flubber-class limitations when it falls back to flubber.

**Verdict:** if the user is already in the Motion ecosystem, use it. Otherwise our approach (flubber + strategy detection) is comparable quality with less library overhead.

## Decision matrix

| User context | Recommendation |
|---|---|
| MIT license required, generic React app | flubber (default) |
| Already using Anime.js or want broader animation features | Anime.js |
| Already using Motion | Motion |
| iOS port pipeline | Anything — bezier conversion happens at build time anyway |
| Quick prototype, single morph | flubber |

## What no library handles well

Don't expect any of these to:
- Morph multi-subpath stroke paths (split them yourself before morphing)
- Preserve open-stroke line caps (libraries force-close paths)
- Interpolate gradients/fills (the skill snaps fill at morph end via `setAttribute`; if you want smooth, normalize the source SVGs to share one fill)
- Handle `<image>`, `<text>`, or `<foreignObject>` (those need different techniques entirely)
- Animate the SVG `transform` attribute (do it yourself, see `transform-interpolation.md`)

## Sampling resolution tips

For libraries that expose a sampling resolution parameter:

- **Small shapes (radius < 5px):** use the smallest precision the library allows. flubber: `maxSegmentLength: 0.5`. Otherwise circles become triangles.
- **Medium shapes (radius 5-50px):** default precision is usually fine. flubber's default of 10 reads as acceptable curvature.
- **Large shapes (radius > 50px):** can usually go coarser to save CPU. Visual difference is minor at this scale.

The skill's strategy detection eliminates most cases where this matters by routing small shapes to TRANSFORM, but if the user has a small shape that genuinely needs MORPH, force smaller precision.

## How to detect library availability in the generated component

```js
const HAS_FLUBBER = typeof flubber !== 'undefined';
const HAS_ANIME = typeof anime !== 'undefined' && anime.svg && typeof anime.svg.morphTo === 'function';

// Pick the best available
const MORPH_ENGINE = HAS_ANIME   ? 'anime' :
                     HAS_FLUBBER       ? 'flubber' :
                                         'none';
```

Default to whichever is loaded. If the user wants a specific engine, they can import it in their project; the component will pick it up.
