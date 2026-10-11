# Transform Attribute Interpolation

SVG elements can carry a `transform` attribute separate from their `d`. If state A has `transform="rotate(13 cx cy)"` and state B has no transform, naively tweening only the `d` leaves the rotation stuck mid-morph then snaps to none at completion. The head jumps.

Always parse and interpolate the transform attribute alongside `d`.

## The parser

```js
function parseTransform(s) {
  if (!s) return null;

  const out = {
    rotate: 0, rotateCx: 0, rotateCy: 0,
    translateX: 0, translateY: 0,
    scaleX: 1, scaleY: 1
  };

  const matches = s.matchAll(/(rotate|translate|scale|matrix)\s*\(([^)]+)\)/g);
  for (const m of matches) {
    const name = m[1];
    const args = m[2].split(/[\s,]+/).map(parseFloat);

    if (name === 'rotate') {
      out.rotate += args[0] || 0;
      out.rotateCx = args[1] || 0;
      out.rotateCy = args[2] || 0;
    } else if (name === 'translate') {
      out.translateX += args[0] || 0;
      out.translateY += args[1] || 0;
    } else if (name === 'scale') {
      out.scaleX *= args[0] || 1;
      out.scaleY *= (args[1] !== undefined ? args[1] : args[0]) || 1;
    }
    // matrix(): decompose to rotate/translate/scale — see below
  }

  return out;
}
```

## The interpolator

```js
function interpolateTransform(from, to, t) {
  const a = from || { rotate: 0, rotateCx: 0, rotateCy: 0, translateX: 0, translateY: 0, scaleX: 1, scaleY: 1 };
  const b = to || { rotate: 0, rotateCx: 0, rotateCy: 0, translateX: 0, translateY: 0, scaleX: 1, scaleY: 1 };

  const lerp = (x, y) => x + (y - x) * t;

  const r = lerp(a.rotate, b.rotate);
  const cx = lerp(a.rotateCx, b.rotateCx);
  const cy = lerp(a.rotateCy, b.rotateCy);
  const tx = lerp(a.translateX, b.translateX);
  const ty = lerp(a.translateY, b.translateY);
  const sx = lerp(a.scaleX, b.scaleX);
  const sy = lerp(a.scaleY, b.scaleY);

  const parts = [];
  if (Math.abs(tx) > 0.001 || Math.abs(ty) > 0.001) {
    parts.push(`translate(${tx.toFixed(3)} ${ty.toFixed(3)})`);
  }
  if (Math.abs(r) > 0.001) {
    parts.push(`rotate(${r.toFixed(3)} ${cx.toFixed(3)} ${cy.toFixed(3)})`);
  }
  if (Math.abs(sx - 1) > 0.001 || Math.abs(sy - 1) > 0.001) {
    parts.push(`scale(${sx.toFixed(3)} ${sy.toFixed(3)})`);
  }

  return parts.length ? parts.join(' ') : null;
}
```

Return `null` (rather than `"translate(0 0) rotate(0 0 0)"`) when the transform reduces to identity — let the caller `removeAttribute('transform')` so the SVG doesn't carry a vestigial no-op transform.

## Integration with TRANSFORM tween

The `runTransformTween` function calls both interpolators per frame:

```js
function runTransformTween({ target, fromD, toD, fromTransform, toTransform, durationMs, easeFn, ...}) {
  const fromXf = parseTransform(fromTransform);
  const toXf = parseTransform(toTransform);
  // ... RAF loop ...
  const step = (now) => {
    const t = Math.min(1, (now - start) / durationMs);
    const eased = easeFn(t);

    const interpD = interpolateStructuredPaths(fromD, toD, eased);
    if (interpD) target.setAttribute('d', interpD);

    if (fromXf || toXf) {
      const xfStr = interpolateTransform(fromXf, toXf, eased);
      if (xfStr) target.setAttribute('transform', xfStr);
      else target.removeAttribute('transform');
    }

    if (t < 1) requestAnimationFrame(step);
    else {
      target.setAttribute('d', toD);
      if (toTransform) target.setAttribute('transform', toTransform);
      else target.removeAttribute('transform');
    }
  };
}
```

## Caveat: rotation center mismatch

When state A has `rotate(13 100 100)` and state B has `rotate(0 50 50)`, naively lerping `(rotateCx, rotateCy)` from (100,100) to (50,50) is geometrically wrong — the rotation appears to drift sideways during the morph.

For most real cases this isn't visible because:
1. One side is usually identity (no rotation), so `rotateCx`/`rotateCy` only matter while interpolating
2. When both sides rotate, the centers are usually similar

If you need correctness: decompose to a single matrix per state, then interpolate matrices via QR decomposition or Lerp+Slerp. That's beyond what most character work needs — flag the edge case to the user instead of overengineering.

## Matrix decomposition (when you need it)

`matrix(a b c d e f)` decomposes to:
- `translate(e f)` — pure translation
- `rotate(atan2(b, a) * 180/π)` — rotation
- `scale(sqrt(a² + b²), (a*d - b*c) / sqrt(a² + b²))` — scale (with potential shear)

For non-degenerate matrices (no shear), this gives a clean decomposition that can be interpolated like the parsed forms above. Add it if a Figma export uses `matrix(...)` syntax (rare for simple character work).

## What this does NOT handle

- **Skew transforms** — `skewX(deg)` and `skewY(deg)`. Add if you encounter them; same pattern as scale.
- **Multiple transforms of the same type** — e.g. `rotate(10) rotate(20)`. The parser sums rotations naively, which is correct for the visual result.
- **Animated `transform-origin` differences** — the rotation center can be specified via `transform-origin` CSS instead of inline rotate args. If the user's source uses this, fall back to reading `getComputedStyle(el).transformOrigin`.
