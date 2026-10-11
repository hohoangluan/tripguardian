# Path Normalization

The trick that gets paths into the TRANSFORM strategy bucket. SVG editors emit equivalent shapes with different command syntax; normalization makes them comparable.

## Why this matters

The body in state-1 of the snowman test case:
```
M84.0261 235.341 C... L149.554 189.497 C... C... L156.159 282.262 C... Z
                     ^^                              ^^
                     line-to
```

The body in states 2-5:
```
M81.1425 250.771 C... H171.975 C... C... H96.1442 C... Z
                     ^^                  ^^
                     horizontal line-to
```

Without normalization, fingerprints look like `MCLCCLCZ` vs `MCHCCHCZ` — different. The body falls into MORPH. With normalization (`H` → `L`), both become `MCLCCLCZ` — same. The body falls into TRANSFORM, and quality goes from "crossfade" to "real morph."

## The full normalization rules

1. **`H x` → `L x cur_y`** — horizontal line-to becomes line-to using the current y
2. **`V y` → `L cur_x y`** — vertical line-to becomes line-to using the current x
3. **Lowercase (relative) → uppercase (absolute)** — `m`, `l`, `h`, `v`, `c`, `s`, `q`, `t`, `a` all converted to absolute coords using the running position
4. **Implicit-repeat commands → explicit** — `M 0 0 5 5 10 10` (one M, three implicit L pairs) becomes `M 0 0 L 5 5 L 10 10`
5. **`<circle>` and `<ellipse>` elements → cubic-bezier path data** — using k=0.5522847498 for the standard 4-cubic approximation
6. **Whitespace normalization** — single spaces between tokens, no leading/trailing whitespace
7. **Decimal precision** — round to 3 decimal places to avoid floating-point fingerprint mismatches

## The parser

```js
function parsePath(d) {
  // Tokenize: command letters or numbers (incl. scientific notation)
  const tokens = d.match(/[MmLlHhVvCcSsQqTtAaZz]|-?\d*\.?\d+(?:e[+-]?\d+)?/g);
  if (!tokens) return null;

  const segments = [];
  let i = 0;
  let cur = [0, 0];           // current point
  let startSubpath = [0, 0];  // for Z
  let lastCmd = null;

  while (i < tokens.length) {
    let cmd = tokens[i];
    // Implicit-repeat: re-use last command (M's implicit follow-up is L)
    if (!/[MmLlHhVvCcSsQqTtAaZz]/.test(cmd)) {
      cmd = lastCmd === 'M' ? 'L' : lastCmd === 'm' ? 'l' : lastCmd;
    } else {
      i++;
    }
    lastCmd = cmd;

    const isAbs = cmd === cmd.toUpperCase();
    const pts = [];
    const consumeXY = () => {
      let x = parseFloat(tokens[i++]);
      let y = parseFloat(tokens[i++]);
      if (!isAbs) { x += cur[0]; y += cur[1]; }
      return [x, y];
    };

    let normalizedCmd = cmd.toUpperCase();
    switch (normalizedCmd) {
      case 'M':
        cur = consumeXY();
        pts.push([...cur]);
        startSubpath = [...cur];
        break;
      case 'L':
        cur = consumeXY();
        pts.push([...cur]);
        break;
      case 'H': {
        // Normalize: H x → L x cur_y
        let x = parseFloat(tokens[i++]);
        if (!isAbs) x += cur[0];
        cur = [x, cur[1]];
        pts.push([...cur]);
        normalizedCmd = 'L';
        break;
      }
      case 'V': {
        // Normalize: V y → L cur_x y
        let y = parseFloat(tokens[i++]);
        if (!isAbs) y += cur[1];
        cur = [cur[0], y];
        pts.push([...cur]);
        normalizedCmd = 'L';
        break;
      }
      case 'C': {
        const c1 = consumeXY(), c2 = consumeXY(), end = consumeXY();
        pts.push(c1, c2, end);
        cur = end;
        break;
      }
      case 'Q': {
        const c1 = consumeXY(), end = consumeXY();
        pts.push(c1, end);
        cur = end;
        break;
      }
      case 'Z':
        cur = [...startSubpath];
        break;
      // S, T, A: less common, add if needed
    }
    segments.push({ cmd: normalizedCmd, points: pts });
  }
  return segments;
}
```

## Computing the fingerprint

```js
function structureFingerprint(d) {
  const segs = parsePath(d);
  if (!segs) return null;
  return segs.map(s => s.cmd).join('');
}
```

For TRANSFORM eligibility, two paths must have:
1. Identical fingerprints (same command sequence)
2. Identical point counts per segment (parsePath already ensures this once commands match)

## Interpolating two normalized paths

Once we know the structures match, interpolating is just lerping each point:

```js
function interpolateStructuredPaths(dFrom, dTo, t) {
  const sf = parsePath(dFrom);
  const st = parsePath(dTo);
  if (!sf || !st || sf.length !== st.length) return null;

  let out = '';
  for (let i = 0; i < sf.length; i++) {
    const segF = sf[i], segT = st[i];
    if (segF.cmd !== segT.cmd) return null;
    out += segF.cmd;
    for (let j = 0; j < segF.points.length; j++) {
      const pF = segF.points[j], pT = segT.points[j];
      const x = pF[0] + (pT[0] - pF[0]) * t;
      const y = pF[1] + (pT[1] - pF[1]) * t;
      out += ` ${x.toFixed(3)} ${y.toFixed(3)}`;
    }
    out += ' ';
  }
  return out.trim();
}
```

This is the entire TRANSFORM strategy implementation. ~30 lines, no library, perfect quality.

## Converting circles/ellipses to bezier path data

For strategy detection, `<circle>` and `<ellipse>` must produce path data that fingerprints the same way as bezier-approximated circles in `<path>` form.

```js
const k = 0.5522847498; // standard cubic-bezier circle constant

function circleToPath(cx, cy, r) {
  return ellipseToPath(cx, cy, r, r);
}

function ellipseToPath(cx, cy, rx, ry) {
  return `M ${cx - rx} ${cy} ` +
         `C ${cx - rx} ${cy - ry*k}, ${cx - rx*k} ${cy - ry}, ${cx} ${cy - ry} ` +
         `C ${cx + rx*k} ${cy - ry}, ${cx + rx} ${cy - ry*k}, ${cx + rx} ${cy} ` +
         `C ${cx + rx} ${cy + ry*k}, ${cx + rx*k} ${cy + ry}, ${cx} ${cy + ry} ` +
         `C ${cx - rx*k} ${cy + ry}, ${cx - rx} ${cy + ry*k}, ${cx - rx} ${cy} Z`;
}
```

Fingerprint: `MCCCCZ` for any circle or ellipse. So a `<circle>` in state-1 and an `<ellipse>` in state-2 both fingerprint as `MCCCCZ` → TRANSFORM strategy, real point interpolation.

## What this does NOT handle

- **Arc commands (`A`)** — full implementation requires parameterizing the elliptical arc. For most character work, arcs don't appear. If you encounter them, route to MORPH.
- **Smooth-bezier shortcuts (`S`, `T`)** — these reference the previous control point. Less common in Figma exports. Add support if needed by tracking the reflected control point.
- **Paths whose point counts differ** even after structure matches (rare but possible with hand-drawn paths) — route to MORPH.
