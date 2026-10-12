// Export the SVG-morph-animator state machine to a self-contained SwiftUI file.
//
// Two entry points:
//   1. Browser (preview shell): `window.SwiftExporter.exportToSwift(states, options)`
//      — called by the "Export" button in the preview to download a .swift file
//        reflecting the user's tuned particle config, easing, etc.
//   2. Node CLI: `node scripts/export-swift.js path/to/<name>.states.js [out.swift]`
//      — emits the Swift source to stdout (or to a file). Use for batch builds.
//
// The output is a single Swift file with no external dependencies. It uses
// SwiftUI + UIKit (for CAEmitterLayer) and requires iOS 15+ (TimelineView).
//
// Architecture mirrored from the JS engine:
//   - Shared paths with consistent command structure across states → MorphShape
//     (Animatable Shape, lerps control points per frame, perfect bezier-preserving)
//   - Shared paths with different structure → fallback "snap at 50%" (v1)
//   - Idle animations as a per-state IdleConfig with sin-based math in
//     TimelineView's body, with the same 40%/0.1/sine amplitude blend during morphs
//   - Particle config emitted to CAEmitterLayer with arc-limited emission via
//     emissionLongitude + emissionRange

(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.SwiftExporter = factory();
}(typeof self !== 'undefined' ? self : this, function () {

  // ---------------------------------------------------------------------------
  // Path parsing (self-contained copy of engine's parser, simplified for export)
  // ---------------------------------------------------------------------------

  function parsePath(d) {
    if (!d || typeof d !== 'string') return null;
    const tokens = d.match(/[MmLlHhVvCcSsQqTtAaZz]|-?\d*\.?\d+(?:e[+-]?\d+)?/g);
    if (!tokens) return null;
    const segments = [];
    let i = 0, cur = [0, 0], startSubpath = [0, 0];
    let lastCmd = null;
    while (i < tokens.length) {
      let cmd = tokens[i];
      if (!/[MmLlHhVvCcSsQqTtAaZz]/.test(cmd)) {
        cmd = lastCmd === 'M' ? 'L' : lastCmd === 'm' ? 'l' : lastCmd;
      } else {
        i++;
      }
      lastCmd = cmd;
      const isAbs = cmd === cmd.toUpperCase();
      const pts = [];
      const consumeXY = () => {
        let x = parseFloat(tokens[i++]), y = parseFloat(tokens[i++]);
        if (!isAbs) { x += cur[0]; y += cur[1]; }
        return [x, y];
      };
      switch (cmd.toUpperCase()) {
        case 'M':
          cur = consumeXY(); pts.push(cur.slice()); startSubpath = cur.slice(); break;
        case 'L':
          cur = consumeXY(); pts.push(cur.slice()); break;
        case 'H': {
          let x = parseFloat(tokens[i++]); if (!isAbs) x += cur[0];
          cur = [x, cur[1]]; pts.push(cur.slice()); break;
        }
        case 'V': {
          let y = parseFloat(tokens[i++]); if (!isAbs) y += cur[1];
          cur = [cur[0], y]; pts.push(cur.slice()); break;
        }
        case 'C': {
          const c1 = consumeXY(), c2 = consumeXY(), to = consumeXY();
          cur = to; pts.push(c1, c2, to); break;
        }
        case 'Q': {
          const c = consumeXY(), to = consumeXY();
          cur = to; pts.push(c, to); break;
        }
        case 'Z':
          cur = startSubpath.slice(); break;
        default:
          // Unsupported (S, T, A). Skip silently — Swift emit will note any gaps.
          return null;
      }
      segments.push({ cmd: cmd.toUpperCase(), pts });
    }
    return segments;
  }

  function ellipseToPath(cx, cy, rx, ry) {
    const k = 0.5522847498;
    return `M ${cx - rx} ${cy} C ${cx - rx} ${cy - ry * k}, ${cx - rx * k} ${cy - ry}, ${cx} ${cy - ry} C ${cx + rx * k} ${cy - ry}, ${cx + rx} ${cy - ry * k}, ${cx + rx} ${cy} C ${cx + rx} ${cy + ry * k}, ${cx + rx * k} ${cy + ry}, ${cx} ${cy + ry} C ${cx - rx * k} ${cy + ry}, ${cx - rx} ${cy + ry * k}, ${cx - rx} ${cy} Z`;
  }
  function rectToPath(x, y, w, h, rx, ry) {
    x = +x || 0; y = +y || 0; w = +w; h = +h;
    rx = Math.min(+rx || 0, w / 2);
    ry = Math.min(+ry || +rx || 0, h / 2);
    if (rx === 0 && ry === 0) return `M ${x} ${y} L ${x + w} ${y} L ${x + w} ${y + h} L ${x} ${y + h} Z`;
    const k = 0.5522847498;
    return `M ${x + rx} ${y} L ${x + w - rx} ${y} C ${x + w - rx + rx * k} ${y} ${x + w} ${y + ry - ry * k} ${x + w} ${y + ry} L ${x + w} ${y + h - ry} C ${x + w} ${y + h - ry + ry * k} ${x + w - rx + rx * k} ${y + h} ${x + w - rx} ${y + h} L ${x + rx} ${y + h} C ${x + rx - rx * k} ${y + h} ${x} ${y + h - ry + ry * k} ${x} ${y + h - ry} L ${x} ${y + ry} C ${x} ${y + ry - ry * k} ${x + rx - rx * k} ${y} ${x + rx} ${y} Z`;
  }
  function getDOf(p) {
    if (p.tag === 'circle') return ellipseToPath(+p.cx, +p.cy, +p.r, +p.r);
    if (p.tag === 'ellipse') return ellipseToPath(+p.cx, +p.cy, +p.rx, +p.ry);
    if (p.tag === 'rect') return rectToPath(p.x, p.y, p.width, p.height, p.rx, p.ry);
    return p.d || '';
  }
  function splitSubpaths(d) { const m = d.match(/[Mm][^Mm]*/g); return m || [d]; }

  // ---------------------------------------------------------------------------
  // Polygon sampling — used by MORPH-strategy paths whose command structure
  // genuinely differs across states. Replaces the v1 "snap at 50%" with a
  // flubber-style polygon morph: sample N evenly-spaced points along each
  // path's perimeter, emit those as CGPoint arrays, and lerp vertex-by-vertex
  // at runtime. Loses bezier precision (curves become polylines) but produces
  // smooth shape interpolation for the snowman body and similar large blobs.
  // ---------------------------------------------------------------------------

  // Evaluate a cubic Bezier at parameter t. Standard formula, no clever tricks.
  function bezier3(p0, p1, p2, p3, t) {
    const it = 1 - t;
    const it2 = it * it, it3 = it2 * it;
    const t2 = t * t, t3 = t2 * t;
    return [
      it3 * p0[0] + 3 * it2 * t * p1[0] + 3 * it * t2 * p2[0] + t3 * p3[0],
      it3 * p0[1] + 3 * it2 * t * p1[1] + 3 * it * t2 * p2[1] + t3 * p3[1],
    ];
  }
  function bezier2(p0, p1, p2, t) {
    const it = 1 - t;
    return [
      it * it * p0[0] + 2 * it * t * p1[0] + t * t * p2[0],
      it * it * p0[1] + 2 * it * t * p1[1] + t * t * p2[1],
    ];
  }

  // Convert parsed segments → a dense polyline by subdividing each curve.
  // Each cubic becomes `subdiv` line segments; lines pass through unchanged.
  // Closepath returns to subpath start.
  function segmentsToPolyline(segments, subdiv = 16) {
    const pts = [];
    let cur = [0, 0];
    let subStart = [0, 0];
    for (const s of segments) {
      switch (s.cmd) {
        case 'M':
          cur = s.pts[0].slice();
          subStart = cur.slice();
          pts.push(cur.slice());
          break;
        case 'L':
        case 'H':
        case 'V':
          cur = s.pts[0].slice();
          pts.push(cur.slice());
          break;
        case 'C': {
          const [c1, c2, to] = s.pts;
          for (let i = 1; i <= subdiv; i++) {
            const t = i / subdiv;
            pts.push(bezier3(cur, c1, c2, to, t));
          }
          cur = to.slice();
          break;
        }
        case 'Q': {
          const [c, to] = s.pts;
          for (let i = 1; i <= subdiv; i++) {
            const t = i / subdiv;
            pts.push(bezier2(cur, c, to, t));
          }
          cur = to.slice();
          break;
        }
        case 'Z':
          if (pts.length === 0 || pts[pts.length - 1][0] !== subStart[0] || pts[pts.length - 1][1] !== subStart[1]) {
            pts.push(subStart.slice());
          }
          cur = subStart.slice();
          break;
      }
    }
    return pts;
  }

  // Resample a polyline to exactly `n` points evenly spaced along arc length.
  function resamplePolyline(polyline, n) {
    if (polyline.length < 2) return new Array(n).fill(polyline[0] || [0, 0]);
    // Cumulative arc lengths
    const cum = [0];
    for (let i = 1; i < polyline.length; i++) {
      const dx = polyline[i][0] - polyline[i - 1][0];
      const dy = polyline[i][1] - polyline[i - 1][1];
      cum.push(cum[i - 1] + Math.hypot(dx, dy));
    }
    const total = cum[cum.length - 1];
    if (total === 0) return new Array(n).fill(polyline[0]);
    const out = [];
    for (let i = 0; i < n; i++) {
      const target = (i / (n - 1)) * total;
      // Find segment containing `target` length
      let lo = 0, hi = cum.length - 1;
      while (lo < hi - 1) {
        const mid = (lo + hi) >> 1;
        if (cum[mid] <= target) lo = mid; else hi = mid;
      }
      const segLen = cum[hi] - cum[lo];
      const t = segLen > 0 ? (target - cum[lo]) / segLen : 0;
      out.push([
        polyline[lo][0] + (polyline[hi][0] - polyline[lo][0]) * t,
        polyline[lo][1] + (polyline[hi][1] - polyline[lo][1]) * t,
      ]);
    }
    return out;
  }

  function samplePolygon(segments, n = 80) {
    if (!segments || segments.length === 0) return new Array(n).fill([0, 0]);
    const dense = segmentsToPolyline(segments, 16);
    return resamplePolyline(dense, n);
  }

  // ---------------------------------------------------------------------------
  // Rigid-body parameters for multi-subpath stroke paths (hands).
  //
  // Multi-subpath stroke paths like the snowman hands aren't deformations of
  // one another across states — they're rigid rotations around a wrist anchor.
  // The 4 strokes have identical lengths in every state, just different angles.
  //
  // If we morph them via control-point lerp (as we do for single-subpath
  // TRANSFORM paths), each stroke's free endpoint moves linearly through the
  // ambient space, which means strokes visibly stretch and squash mid-morph.
  // The line caps drift away from their natural positions.
  //
  // Instead, for multi-subpath paths we:
  //   1. Render ONE canonical state's hand shape (the first state).
  //   2. Per state, compute a (wrist anchor, orientation angle) pair.
  //   3. Animate translation + rotation between displayedState's pair and
  //      targetState's pair via an animatable modifier.
  //
  // Net effect: the hand keeps its exact shape throughout the morph and just
  // rotates+translates rigidly to its new pose. Line caps stay fixed relative
  // to the strokes — no stretching.
  // ---------------------------------------------------------------------------

  // Given the parsed subpaths of a multi-subpath path, find the wrist anchor
  // (the endpoint that's shared by all subpaths within a small tolerance) and
  // compute the average orientation angle (vector-averaged direction from
  // wrist to each subpath's far endpoint).
  function computeRigidParams(parsedSubpaths) {
    if (!parsedSubpaths || parsedSubpaths.length === 0) return { anchor: [0, 0], angle: 0 };
    // Collect both endpoints of each subpath.
    const endpoints = [];
    for (const sub of parsedSubpaths) {
      if (!sub || sub.length === 0) continue;
      const firstPts = sub[0].pts;
      const lastSeg = sub[sub.length - 1];
      const lastPts = lastSeg.pts;
      const first = firstPts[0];
      const last = lastPts[lastPts.length - 1];
      endpoints.push({ first, last });
    }
    // Group nearby points to find the most common endpoint = wrist.
    const TOLERANCE = 0.5;
    const groups = [];
    const addToGroup = (p) => {
      for (const g of groups) {
        if (Math.hypot(g.center[0] - p[0], g.center[1] - p[1]) < TOLERANCE) {
          g.count++;
          g.center[0] = (g.center[0] * (g.count - 1) + p[0]) / g.count;
          g.center[1] = (g.center[1] * (g.count - 1) + p[1]) / g.count;
          return;
        }
      }
      groups.push({ center: p.slice(), count: 1 });
    };
    for (const e of endpoints) {
      addToGroup(e.first);
      addToGroup(e.last);
    }
    groups.sort((a, b) => b.count - a.count);
    const wrist = groups[0].center;
    // For each subpath, the fingertip is whichever endpoint isn't the wrist.
    const fingertips = endpoints.map(e => {
      const dFirst = Math.hypot(e.first[0] - wrist[0], e.first[1] - wrist[1]);
      const dLast = Math.hypot(e.last[0] - wrist[0], e.last[1] - wrist[1]);
      return dFirst < dLast ? e.last : e.first;
    });
    // Vector-average the directions (handles angle wrap-around naturally).
    let vx = 0, vy = 0;
    for (const ft of fingertips) {
      const dx = ft[0] - wrist[0];
      const dy = ft[1] - wrist[1];
      const len = Math.hypot(dx, dy);
      if (len > 0) { vx += dx / len; vy += dy / len; }
    }
    const angle = Math.atan2(vy, vx) * 180 / Math.PI;
    return { anchor: wrist, angle };
  }

  // ---------------------------------------------------------------------------
  // Strategy detection (subset of engine — same fingerprint rule)
  // ---------------------------------------------------------------------------

  function fingerprint(d) {
    const segs = parsePath(d);
    if (!segs) return null;
    // Normalize H/V → L (the skill's normalization rule, matching the JS
    // engine): H, V, and L are one structural class — segmentToSwift renders
    // all three as `.line`, so pairing them across states is exact.
    return segs.map(s => (s.cmd === 'H' || s.cmd === 'V') ? 'L' : s.cmd).join('');
  }
  function detectStrategy(states, stateNames, id) {
    const fps = stateNames.map(sn => {
      const p = states[sn].paths[id];
      return p ? fingerprint(getDOf(p)) : null;
    }).filter(Boolean);
    if (fps.length < 2) return 'TRANSFORM';
    const first = fps[0];
    return fps.every(fp => fp === first) ? 'TRANSFORM' : 'MORPH';
  }

  // ---------------------------------------------------------------------------
  // Swift code generation
  // ---------------------------------------------------------------------------

  // Map engine ease names → SwiftUI Animation builder expressions.
  // SwiftUI doesn't expose each curve as a named function, so we use timingCurve
  // with the standard cubic-bezier control points for fidelity to the JS engine.
  const SWIFT_EASING = {
    'linear':        'Animation.linear(duration: __DUR__)',
    'easeInOutQuad': 'Animation.timingCurve(0.45, 0, 0.55, 1, duration: __DUR__)',
    'easeInOutSine': 'Animation.timingCurve(0.37, 0, 0.63, 1, duration: __DUR__)',
    'easeOutCubic':  'Animation.timingCurve(0.33, 1, 0.68, 1, duration: __DUR__)',
    'easeOutBack':   'Animation.timingCurve(0.34, 1.56, 0.64, 1, duration: __DUR__)',
  };

  function safeId(s) { return s.replace(/[^A-Za-z0-9_]/g, '_'); }

  // Format a number with at most 5 decimal places, no trailing zeros, no exponential.
  function num(n) {
    if (!isFinite(n)) return '0';
    const r = Math.round(n * 100000) / 100000;
    return String(r);
  }
  // Range endpoints — Swift's parser can't disambiguate `-40...-14`, so we
  // parenthesize negative endpoints. Use this for both ends of any literal range.
  function rangeNum(n) {
    const s = num(n);
    return s.startsWith('-') ? `(${s})` : s;
  }
  function pt(p) { return `CGPoint(x: ${num(p[0])}, y: ${num(p[1])})`; }

  function segmentToSwift(seg) {
    switch (seg.cmd) {
      case 'M': return `.move(${pt(seg.pts[0])})`;
      case 'L':
      case 'H':
      case 'V': return `.line(${pt(seg.pts[0])})`;
      case 'C': return `.curve(to: ${pt(seg.pts[2])}, c1: ${pt(seg.pts[0])}, c2: ${pt(seg.pts[1])})`;
      case 'Q': return `.quad(to: ${pt(seg.pts[1])}, c: ${pt(seg.pts[0])})`;
      case 'Z': return `.close`;
      default: return '.close';
    }
  }

  // Build a `Path(...)` from a MorphPathSegment array. When a type prefix is set
  // we give the Path.init a prefix-derived ARGUMENT LABEL (e.g. Path(snowmanScene:
  // [...])) rather than the bare unlabeled Path(_:). Two animators exported into
  // one module both add a `Path.init(_ segments: [XMorphPathSegment])`; with the
  // unlabeled form those overloads compete, and any *un-annotated* `Path([.move…])`
  // in EITHER file (older exports omit the `as` cast) becomes "ambiguous use of
  // 'move'". A unique label per animator means each file's Path init never
  // participates in another's overload resolution. `arg` is the segment array
  // literal body (literal:true) or an expression like PathData.x / lerpSegments(…).
  function segPathExpr(opts, arg, literal) {
    if (opts.segLabel) return literal ? `Path(${opts.segLabel}: [${arg}])` : `Path(${opts.segLabel}: ${arg})`;
    return literal ? `Path([${arg}] as [MorphPathSegment])` : `Path(${arg})`;
  }

  // ---------------------------------------------------------------------------
  // Gradient parsing (<radialGradient> and <linearGradient> in <defs>)
  // ---------------------------------------------------------------------------

  // Parse all gradient definitions from a state's `defs` string. Each is keyed
  // by its `id` attribute so paths' `fill="url(#id)"` can be resolved. Only the
  // attributes we actually use are extracted; everything else is ignored.
  //
  // SVG gradients have a coordinate system controlled by `gradientUnits` (default
  // "objectBoundingBox" but most exporters emit "userSpaceOnUse") and an optional
  // `gradientTransform` matrix. SwiftUI gradients are in normalized [0,1] coords
  // relative to the shape's bounding box, so at orphan emission time we convert
  // the SVG center + radius into bbox-normalized values.
  function parseGradients(defsStr) {
    const out = {};
    if (!defsStr) return out;
    // <radialGradient id="..." gradientTransform="..." gradientUnits="userSpaceOnUse">
    //   <stop offset="..." stop-color="..." stop-opacity="..."/>...
    // </radialGradient>
    const radialRe = /<radialGradient\s+([^>]*?)>(.*?)<\/radialGradient>/gs;
    let m;
    while ((m = radialRe.exec(defsStr)) !== null) {
      const attrs = parseAttrs(m[1]);
      if (!attrs.id) continue;
      const stops = parseStops(m[2]);
      out[attrs.id] = {
        type: 'radial',
        stops,
        gradientTransform: attrs.gradientTransform || null,
        // Default unit-circle params (overridden if attrs present).
        cx: attrs.cx != null ? parseFloat(attrs.cx) : 0,
        cy: attrs.cy != null ? parseFloat(attrs.cy) : 0,
        r: attrs.r != null ? parseFloat(attrs.r) : 1,
        fx: attrs.fx != null ? parseFloat(attrs.fx) : null,
        fy: attrs.fy != null ? parseFloat(attrs.fy) : null,
      };
    }
    const linearRe = /<linearGradient\s+([^>]*?)>(.*?)<\/linearGradient>/gs;
    while ((m = linearRe.exec(defsStr)) !== null) {
      const attrs = parseAttrs(m[1]);
      if (!attrs.id) continue;
      const stops = parseStops(m[2]);
      out[attrs.id] = {
        type: 'linear',
        stops,
        gradientTransform: attrs.gradientTransform || null,
        x1: attrs.x1 != null ? parseFloat(attrs.x1) : 0,
        y1: attrs.y1 != null ? parseFloat(attrs.y1) : 0,
        x2: attrs.x2 != null ? parseFloat(attrs.x2) : 1,
        y2: attrs.y2 != null ? parseFloat(attrs.y2) : 0,
      };
    }
    return out;
  }

  function parseStops(innerHTML) {
    const stops = [];
    const re = /<stop\s+([^/>]*?)\/?>/g;
    let m;
    while ((m = re.exec(innerHTML)) !== null) {
      const a = parseAttrs(m[1]);
      stops.push({
        offset: a.offset != null ? parseFloat(a.offset) : 0,
        color: a.stopColor || a.stop_color || a['stop-color'] || '#000',
        opacity: a.stopOpacity != null ? parseFloat(a.stopOpacity) : 1,
      });
    }
    return stops;
  }

  // Parse <filter> elements from a defs string into shadow/blur descriptors so
  // they can map to SwiftUI .shadow / .blur. Recognizes the Figma-exported
  // patterns: a drop-shadow / colored glow (feOffset? + feGaussianBlur +
  // feColorMatrix) → { type:'shadow', color:[r,g,b], opacity, radius, dx, dy };
  // a plain foreground blur (feGaussianBlur only) → { type:'blur', radius }.
  function parseFilters(defsStr) {
    const out = {};
    if (!defsStr) return out;
    const re = /<filter\b[^>]*\bid="([^"]+)"[^>]*>([\s\S]*?)<\/filter>/g;
    let m;
    while ((m = re.exec(defsStr)) !== null) {
      const id = m[1], body = m[2];
      const gb = body.match(/stdDeviation="([\d.]+)"/);
      const radius = gb ? parseFloat(gb[1]) : 0;
      let dx = 0, dy = 0;
      const off = body.match(/<feOffset\b([^>]*)>/);
      if (off) {
        const ax = off[1].match(/\bdx="(-?[\d.]+)"/); const ay = off[1].match(/\bdy="(-?[\d.]+)"/);
        dx = ax ? parseFloat(ax[1]) : 0; dy = ay ? parseFloat(ay[1]) : 0;
      }
      // A drop-shadow filter has TWO feColorMatrix: the first is `hardAlpha`
      // (in="SourceAlpha", …127 0) which we must skip; the shadow's real color +
      // opacity live in the LATER matrix. Pick the last non-hardAlpha one.
      const cms = [...body.matchAll(/<feColorMatrix\b([^>]*)\bvalues="([^"]+)"/g)];
      const colorCm = cms.filter(x => !/hardAlpha|in="SourceAlpha"/.test(x[1])).pop() || cms[cms.length - 1];
      if (colorCm) {
        const v = colorCm[2].trim().split(/[\s,]+/).map(parseFloat);
        // feColorMatrix rows are 5 wide; RGB come from each row's constant term
        // (indices 4/9/14), the shadow's opacity from the alpha row (index 18).
        const color = v.length >= 15 ? [v[4] || 0, v[9] || 0, v[14] || 0] : [0, 0, 0];
        const opacity = v.length >= 19 ? (v[18] || 1) : 1;
        out[id] = { type: 'shadow', color, opacity, radius, dx, dy };
      } else if (radius) {
        out[id] = { type: 'blur', radius };
      }
    }
    return out;
  }

  // Parse "matrix(a b c d e f)" into { a, b, c, d, e, f }. Returns identity if
  // the input is missing or unrecognized.
  function parseMatrixTransform(s) {
    if (!s) return { a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 };
    const m = /matrix\s*\(\s*([-\d.eE]+)[ ,]+([-\d.eE]+)[ ,]+([-\d.eE]+)[ ,]+([-\d.eE]+)[ ,]+([-\d.eE]+)[ ,]+([-\d.eE]+)\s*\)/.exec(s);
    if (m) return { a: +m[1], b: +m[2], c: +m[3], d: +m[4], e: +m[5], f: +m[6] };
    // Compose translate/rotate/scale into a matrix if present
    let M = { a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 };
    const opRe = /(translate|rotate|scale)\s*\(([^)]+)\)/g;
    let mm;
    while ((mm = opRe.exec(s)) !== null) {
      const nums = mm[2].trim().split(/[\s,]+/).map(parseFloat);
      let N;
      if (mm[1] === 'translate') {
        N = { a: 1, b: 0, c: 0, d: 1, e: nums[0] || 0, f: nums[1] || 0 };
      } else if (mm[1] === 'rotate') {
        const r = (nums[0] * Math.PI) / 180;
        const ca = Math.cos(r), sa = Math.sin(r);
        N = { a: ca, b: sa, c: -sa, d: ca, e: 0, f: 0 };
        if (nums.length === 3) {
          const cx = nums[1], cy = nums[2];
          // R(deg, cx, cy) = T(cx,cy) * R(deg) * T(-cx,-cy)
          N = mulMat({ a: 1, b: 0, c: 0, d: 1, e: cx, f: cy },
            mulMat(N, { a: 1, b: 0, c: 0, d: 1, e: -cx, f: -cy }));
        }
      } else if (mm[1] === 'scale') {
        const sx = nums[0] || 1, sy = nums.length > 1 ? nums[1] : sx;
        N = { a: sx, b: 0, c: 0, d: sy, e: 0, f: 0 };
      }
      M = mulMat(M, N);
    }
    return M;
  }
  function mulMat(A, B) {
    return {
      a: A.a * B.a + A.c * B.b,
      b: A.b * B.a + A.d * B.b,
      c: A.a * B.c + A.c * B.d,
      d: A.b * B.c + A.d * B.d,
      e: A.a * B.e + A.c * B.f + A.e,
      f: A.b * B.e + A.d * B.f + A.f,
    };
  }

  // Compute the bbox of a parsed segment list. Used to map gradient user-space
  // coords into shape-bbox-normalized UnitPoint for SwiftUI's RadialGradient.
  function bboxOfSegments(segs) {
    let xMin = Infinity, yMin = Infinity, xMax = -Infinity, yMax = -Infinity;
    for (const s of segs) {
      for (const p of s.pts) {
        if (p[0] < xMin) xMin = p[0];
        if (p[0] > xMax) xMax = p[0];
        if (p[1] < yMin) yMin = p[1];
        if (p[1] > yMax) yMax = p[1];
      }
    }
    return { x: xMin, y: yMin, width: xMax - xMin, height: yMax - yMin };
  }

  // Curve-aware ("tight") bbox — subdivides beziers so the box matches what the
  // browser's getBBox() returns (the JS overlay code measures live getBBox for
  // eye centers / heights and decoration centers). Used to line up Swift-baked
  // overlay anchors + talk lift/height with the preview.
  function tightBBoxOfSegments(segs) {
    const poly = segmentsToPolyline(segs, 16);
    let xMin = Infinity, yMin = Infinity, xMax = -Infinity, yMax = -Infinity;
    for (const p of poly) {
      if (p[0] < xMin) xMin = p[0];
      if (p[0] > xMax) xMax = p[0];
      if (p[1] < yMin) yMin = p[1];
      if (p[1] > yMax) yMax = p[1];
    }
    if (!isFinite(xMin)) return { x: 0, y: 0, width: 0, height: 0, cx: 0, cy: 0 };
    return { x: xMin, y: yMin, width: xMax - xMin, height: yMax - yMin, cx: (xMin + xMax) / 2, cy: (yMin + yMax) / 2 };
  }

  // Emit a SwiftUI gradient expression for a given fillUrl ("url(#id)").
  //
  // Important: we normalize positions to the CANVAS frame (viewBox), not the
  // shape's bbox. The orphan rendering uses .mask(Path) so the gradient fills
  // the whole canvas and the path clips it. This puts the gradient's center at
  // the SVG user-space coordinate regardless of which path it's masking — which
  // is what `gradientUnits="userSpaceOnUse"` actually means in SVG, and what
  // the JS preview ends up with by chance (since the gradient renders inside
  // the SVG's own coordinate system).
  function gradientToSwift(fillUrl, gradientMap, bbox, canvasW, canvasH) {
    const m = /url\s*\(\s*#([^)]+)\)/.exec(fillUrl);
    if (!m) return null;
    const g = gradientMap[m[1]];
    if (!g) return null;
    const stopsSwift = g.stops.map(st => {
      const c = hexToSwiftColor(st.color);
      const colorWithOpacity = st.opacity != null && st.opacity < 1
        ? `${c}.opacity(${num(st.opacity)})`
        : c;
      return `.init(color: ${colorWithOpacity}, location: ${num(st.offset)})`;
    }).join(', ');

    if (g.type === 'radial') {
      // Apply gradientTransform to derive center + radius in user-space:
      //   center_user = M * (cx, cy)         (for default unit-circle origin)
      //   radius_x    = length of M's first column  = sqrt(a² + b²) * r
      //   radius_y    = length of M's second column = sqrt(c² + d²) * r
      const M = parseMatrixTransform(g.gradientTransform);
      const ucx = M.a * g.cx + M.c * g.cy + M.e;
      const ucy = M.b * g.cx + M.d * g.cy + M.f;
      const rX = Math.hypot(M.a, M.b) * g.r;
      const rY = Math.hypot(M.c, M.d) * g.r;
      // SwiftUI's RadialGradient is circular; use max(rX, rY) for the soft glow
      // case (skewed/elliptical gradients aren't natively supported and would
      // need a custom Metal shader for exact reproduction).
      const endRadius = Math.max(rX, rY);
      // Canvas-normalized UnitPoint (since we render gradient at canvas size + .mask)
      const nx = ucx / canvasW;
      const ny = ucy / canvasH;
      return `RadialGradient(gradient: Gradient(stops: [${stopsSwift}]), center: UnitPoint(x: ${num(nx)}, y: ${num(ny)}), startRadius: 0, endRadius: ${num(endRadius)})`;
    }
    if (g.type === 'linear') {
      // Linear: transform (x1,y1) and (x2,y2) through gradientTransform, then
      // normalize to canvas coords (same rationale as radial).
      const M = parseMatrixTransform(g.gradientTransform);
      const tx = (x, y) => [M.a * x + M.c * y + M.e, M.b * x + M.d * y + M.f];
      const [sx, sy] = tx(g.x1, g.y1);
      const [ex, ey] = tx(g.x2, g.y2);
      return `LinearGradient(gradient: Gradient(stops: [${stopsSwift}]), startPoint: UnitPoint(x: ${num(sx / canvasW)}, y: ${num(sy / canvasH)}), endPoint: UnitPoint(x: ${num(ex / canvasW)}, y: ${num(ey / canvasH)}))`;
    }
    return null;
  }

  // ---------------------------------------------------------------------------
  // Orphan collection (structured _orphan paths + inline orphanSVG markup)
  // ---------------------------------------------------------------------------

  // Apply a `rotate(deg cx cy)` transform to a point. Used to bake transforms
  // into baked path data so the runtime doesn't need to track per-shape rotation.
  function applyRotate(point, deg, cx, cy) {
    const rad = (deg * Math.PI) / 180;
    const cos = Math.cos(rad);
    const sin = Math.sin(rad);
    const dx = point[0] - cx;
    const dy = point[1] - cy;
    return [cos * dx - sin * dy + cx, sin * dx + cos * dy + cy];
  }

  // Extract a single rotation from a path's transform attribute. Returns
  // { deg, pivot: [cx, cy] }. If no rotation, returns { deg: 0, pivot: null }.
  // Only rotate is handled — translate/scale on a path are rare and would
  // need their own animatable channels.
  function parsePerPathTransform(transformStr) {
    const out = { deg: 0, pivot: null };
    if (!transformStr) return out;
    const m = /rotate\s*\(\s*([-\d.eE]+)(?:\s+([-\d.eE]+)\s+([-\d.eE]+))?\s*\)/.exec(transformStr);
    if (!m) return out;
    out.deg = parseFloat(m[1]);
    if (m[2] != null && m[3] != null) {
      out.pivot = [parseFloat(m[2]), parseFloat(m[3])];
    }
    return out;
  }

  // Parse a transform="rotate(deg cx cy) translate(x y)" attribute string and
  // return a list of operations. Only rotate is required for the snowman
  // flowers; translate is supported for completeness. Anything else is dropped
  // with a console.warn at export time.
  function parseTransformAttr(s) {
    if (!s) return [];
    const ops = [];
    const re = /(rotate|translate|scale|matrix)\s*\(([^)]+)\)/g;
    let m;
    while ((m = re.exec(s)) !== null) {
      const kind = m[1];
      const nums = m[2].trim().split(/[,\s]+/).map(parseFloat);
      ops.push({ kind, nums });
    }
    return ops;
  }

  // Apply a list of transform ops to a single point (origin-first to match SVG semantics).
  // Supports rotate(deg [cx cy]), translate(tx [ty]), scale(sx [sy]), matrix(a b c d e f).
  // Earlier versions skipped matrix() which broke the snowman state-4 owl feet
  // (their <rect> elements use matrix(-1 0 0 1 153.25 102) for flip-X + translate).
  function applyTransformToPoint(point, ops) {
    let p = point.slice();
    for (const op of ops) {
      if (op.kind === 'rotate') {
        const [deg, cx = 0, cy = 0] = op.nums;
        p = applyRotate(p, deg, cx, cy);
      } else if (op.kind === 'translate') {
        const [tx = 0, ty = 0] = op.nums;
        p = [p[0] + tx, p[1] + ty];
      } else if (op.kind === 'scale') {
        const [sx, sy = sx] = op.nums;
        p = [sx * p[0], sy * p[1]];
      } else if (op.kind === 'matrix') {
        const [a, b, c, d, e, f] = op.nums;
        p = [a * p[0] + c * p[1] + e, b * p[0] + d * p[1] + f];
      }
    }
    return p;
  }

  // Walk parsed segments and bake the given transform into every control point.
  function bakeTransformIntoSegments(segs, transform) {
    const ops = parseTransformAttr(transform);
    if (ops.length === 0) return segs;
    return segs.map(s => ({
      cmd: s.cmd,
      pts: s.pts.map(p => applyTransformToPoint(p, ops)),
    }));
  }

  // Light regex parser for an orphanSVG markup string. Returns FLATTENED shapes
  // for static orphan rendering (groups are dissolved, contributing opacity/transform
  // to their children). This is used when we want to render every shape individually.
  function parseOrphanSVG(svgStr) {
    if (!svgStr) return [];
    const shapes = [];
    const flat = svgStr.replace(/\s+/g, ' ');
    const groupRe = /<g\s*([^>]*?)>(.*?)<\/g>/g;
    let lastIdx = 0;
    let m;
    while ((m = groupRe.exec(flat)) !== null) {
      collectShapes(flat.slice(lastIdx, m.index), null, null, shapes);
      const groupAttrs = parseAttrs(m[1]);
      const groupOpacity = groupAttrs.opacity ? parseFloat(groupAttrs.opacity) : 1;
      const groupTransform = groupAttrs.transform || null;
      collectShapes(m[2], groupOpacity, groupTransform, shapes);
      lastIdx = m.index + m[0].length;
    }
    collectShapes(flat.slice(lastIdx), null, null, shapes);
    return shapes;
  }

  // Same parser but PRESERVES top-level <g> groups as their own entities. Used
  // by the particle pipeline to extract each flower (or analogous group) as a
  // single particle template — six ellipses making up one flower stay as one
  // image, not six separate particles.
  //
  // Returns an array where each item is:
  //   { kind: 'group', id, opacity, transform, children: [shape] }
  //   { kind: 'shape', ...same as parseOrphanSVG entries }
  function parseOrphanSVGGroups(svgStr) {
    if (!svgStr) return [];
    const entities = [];
    const flat = svgStr.replace(/\s+/g, ' ');
    const groupRe = /<g\s*([^>]*?)>(.*?)<\/g>/g;
    let lastIdx = 0;
    let m;
    while ((m = groupRe.exec(flat)) !== null) {
      // Ungrouped shapes between groups: emit as kind:'shape'
      const between = [];
      collectShapes(flat.slice(lastIdx, m.index), null, null, between);
      between.forEach(s => entities.push({ kind: 'shape', ...s }));

      // The group: emit as kind:'group' with children as shapes
      const groupAttrs = parseAttrs(m[1]);
      const groupOpacity = groupAttrs.opacity ? parseFloat(groupAttrs.opacity) : 1;
      const groupTransform = groupAttrs.transform || null;
      const children = [];
      collectShapes(m[2], null, null, children);  // pass null so children keep their own attrs
      entities.push({
        kind: 'group',
        id: groupAttrs.id || '',
        opacity: groupOpacity,
        transform: groupTransform,
        children,
      });
      lastIdx = m.index + m[0].length;
    }
    const trailing = [];
    collectShapes(flat.slice(lastIdx), null, null, trailing);
    trailing.forEach(s => entities.push({ kind: 'shape', ...s }));
    return entities;
  }

  function collectShapes(fragment, groupOpacity, groupTransform, out) {
    const tagRe = /<(path|ellipse|circle|rect)\s+([^/>]*?)\/?>/g;
    let m;
    while ((m = tagRe.exec(fragment)) !== null) {
      const tag = m[1];
      const attrs = parseAttrs(m[2]);
      let d = '';
      if (tag === 'path') d = attrs.d || '';
      else if (tag === 'ellipse') d = ellipseToPath(+attrs.cx, +attrs.cy, +attrs.rx, +attrs.ry);
      else if (tag === 'circle') d = ellipseToPath(+attrs.cx, +attrs.cy, +attrs.r, +attrs.r);
      else if (tag === 'rect') d = rectToPath(attrs.x, attrs.y, attrs.width, attrs.height, attrs.rx, attrs.ry);
      if (!d) continue;
      // Compose transforms: group's transform applied first, then this shape's.
      const transforms = [groupTransform, attrs.transform].filter(Boolean).join(' ');
      const localOpacity = attrs.opacity ? parseFloat(attrs.opacity) : 1;
      const opacity = (groupOpacity == null ? 1 : groupOpacity) * localOpacity;
      out.push({
        tag,
        d,
        fill: attrs.fill || '#999999',
        opacity,
        transform: transforms,
      });
    }
  }

  // Parse attributes from an opening tag's attribute portion.
  function parseAttrs(s) {
    const attrs = {};
    const re = /([\w-]+)\s*=\s*"([^"]*)"/g;
    let m;
    while ((m = re.exec(s)) !== null) {
      const key = m[1].replace(/-([a-z])/g, (_, c) => c.toUpperCase());
      attrs[key] = m[2];
    }
    return attrs;
  }

  // For each state, collect all orphan shapes — both structured (_orphan: true
  // in paths) and inline (orphanSVG markup). Returns:
  //   { state-1: [{ id, d, fill, opacity, segments }, ...], state-2: [...], ... }
  // Segments are the parsed + transform-baked path data, ready for Swift emit.
  function collectOrphans(states, stateNames, canvasSize) {
    const out = {};
    const canvasW = canvasSize.width;
    const canvasH = canvasSize.height;
    // Build a global gradient map by parsing every state's <defs> string.
    // Gradients are typically state-local in id but with the same id used
    // across states; merging into one map is safe because identical ids
    // mean identical definitions in practice.
    const gradientMap = {};
    for (const sn of stateNames) {
      Object.assign(gradientMap, parseGradients(states[sn].defs));
    }
    for (const sn of stateNames) {
      const list = [];
      const addOrphan = (id, fillRaw, segs, extras = {}) => {
        const bbox = bboxOfSegments(segs);
        let fillExpr;
        let fillKind;
        if (typeof fillRaw === 'string' && /^url\(/i.test(fillRaw)) {
          const gradient = gradientToSwift(fillRaw, gradientMap, bbox, canvasW, canvasH);
          if (gradient) {
            fillExpr = gradient;
            fillKind = 'gradient';
          } else {
            // Fallback: gradient id not found in any state's defs.
            fillExpr = 'Color.gray.opacity(0.4)';
            fillKind = 'fallback';
          }
        } else {
          fillExpr = hexToSwiftColor(fillRaw || '#999999');
          fillKind = 'color';
        }
        list.push({
          id: safeId(`${sn}_${id}`),
          fillExpr,
          fillKind,
          stroke: extras.stroke || null,
          strokeWidth: extras.strokeWidth || null,
          strokeOpacity: extras.strokeOpacity != null ? extras.strokeOpacity : 1,
          opacity: extras.opacity != null ? extras.opacity : 1,
          segments: segs,
          // Layer: "back" → renders behind shared paths (e.g. state-1 ice-cube-bg).
          // Default "front" → renders in front (e.g. state-4 owl, in front of snowman).
          // Matches the JS engine's `_layer` field semantics.
          layer: extras.layer === 'back' ? 'back' : 'front',
        });
      };
      // Structured orphans. SKIP when this state has a particles config —
      // those orphans are particle templates (e.g. the snowman state-5 dots),
      // emitted separately via the particle template extractor.
      if (!states[sn].particles) {
        for (const [id, p] of Object.entries(states[sn].paths)) {
          if (!p._orphan) continue;
          const d = getDOf(p);
          let segs = parsePath(d);
          if (!segs) continue;
          if (p.transform) segs = bakeTransformIntoSegments(segs, p.transform);
          addOrphan(id, p.fill, segs, {
            stroke: p.stroke || null,
            strokeWidth: p.strokeWidth ? parseFloat(p.strokeWidth) : null,
            strokeOpacity: p.strokeOpacity ? parseFloat(p.strokeOpacity) : 1,
            layer: p._layer || 'front',
          });
        }
      }
      // Inline orphanSVG markup — but ONLY for states without a particles config.
      // When a state has particles, the orphanSVG defines particle TEMPLATES (the
      // JS engine clones them per spawn); they're not static decorations and
      // shouldn't render as fixed orphans.
      //
      // OrphanSVG content always renders FRONT layer in the JS engine (the
      // verbatim <g> blocks are appended after the front-layer structured orphans).
      if (states[sn].orphanSVG && !states[sn].particles) {
        const shapes = parseOrphanSVG(states[sn].orphanSVG);
        shapes.forEach((sh, i) => {
          let segs = parsePath(sh.d);
          if (!segs) return;
          if (sh.transform) segs = bakeTransformIntoSegments(segs, sh.transform);
          addOrphan(`inline_${i}`, sh.fill, segs, {
            opacity: sh.opacity,
            layer: 'front',
          });
        });
      }
      out[sn] = list;
    }
    return out;
  }

  // Convert a hex color "#RRGGBB" into a Swift Color literal.
  function hexToSwiftColor(hex) {
    if (!hex) return 'Color.gray';
    if (hex === 'white' || hex === '#fff' || hex === '#ffffff' || hex === '#FFFFFF') return 'Color.white';
    if (hex === 'black' || hex === '#000' || hex === '#000000') return 'Color.black';
    // Anything starting with "url(" — gradient reference, fall back to a neutral.
    if (/^url\(/i.test(hex)) return 'Color.gray.opacity(0.4)';
    // Handle 3-digit shorthand
    let h = hex.replace('#', '');
    if (h.length === 3) h = h.split('').map(c => c + c).join('');
    if (h.length !== 6) return 'Color.gray';
    const r = parseInt(h.slice(0, 2), 16) / 255;
    const g = parseInt(h.slice(2, 4), 16) / 255;
    const b = parseInt(h.slice(4, 6), 16) / 255;
    return `Color(.sRGB, red: ${num(r)}, green: ${num(g)}, blue: ${num(b)}, opacity: 1)`;
  }

  // A filter descriptor (from parseFilters) → a SwiftUI modifier line, or '' if
  // none. Drop-shadow / colored-glow → .shadow(); foreground blur → .blur().
  function filterMod(desc, indent) {
    if (!desc) return '';
    if (desc.type === 'blur') return `\n${indent}.blur(radius: ${num(desc.radius)})`;
    const c = desc.color || [0, 0, 0];
    const col = `Color(.sRGB, red: ${num(c[0])}, green: ${num(c[1])}, blue: ${num(c[2])}, opacity: ${num(desc.opacity != null ? desc.opacity : 1)})`;
    return `\n${indent}.shadow(color: ${col}, radius: ${num(desc.radius)}, x: ${num(desc.dx || 0)}, y: ${num(desc.dy || 0)})`;
  }

  function emitOrphanData(opts) {
    // Orphan rendering: each orphan emits as a static View-returning function
    // call. We can't easily store gradients in a struct (RadialGradient and
    // LinearGradient have different generic parameters than Color), so we
    // emit each orphan as a `someOrphanX_Y_Z()` function returning AnyView,
    // and the per-state `orphanViews(for:)` returns an array of those.
    // The cost is a tiny bit of type erasure; the gain is correct gradient
    // rendering with zero runtime gradient construction.
    const lines = [
      `// MARK: - Orphan decorations (per-state non-morphing shapes)`,
      ``,
      `// Orphans are decorative shapes that exist in only some states (e.g. the`,
      `// ice-cube background in state-1, the flowers in state-5). They don't morph`,
      `// — they appear when their state is the displayed state, hidden otherwise.`,
      `// Transforms are baked into path data at export time. Gradient fills are`,
      `// emitted as proper SwiftUI RadialGradient/LinearGradient with bbox-`,
      `// normalized centers (best-effort — SwiftUI's gradient model can't fully`,
      `// replicate arbitrary SVG gradientTransform matrices).`,
      ``,
    ];
    // Each orphan becomes its own function. Counted globally so names don't collide.
    // We also build a per-id lookup so the back/front split can reference functions
    // by their orphan id (the layer split needs to filter by `o.layer`).
    let globalIdx = 0;
    const perStateFnNames = {};
    const perStateFnNamesById = {};  // key: `${sn}|${o.id}` → fnName
    for (const sn of opts.stateNames) {
      perStateFnNames[sn] = [];
      const list = opts.orphansByState[sn] || [];
      list.forEach((o, i) => {
        const fnName = `orphan_${safeId(sn)}_${i}_${globalIdx++}`;
        perStateFnNames[sn].push(fnName);
        perStateFnNamesById[`${sn}|${o.id}`] = fnName;
        const segs = o.segments.map(segmentToSwift).join(', ');
        const fill = o.fillExpr;
        const stroke = o.stroke ? hexToSwiftColor(o.stroke) : null;
        const sw = o.strokeWidth != null ? num(o.strokeWidth) : '0';
        const op = num(o.opacity != null ? o.opacity : 1);
        lines.push(`@ViewBuilder private func ${fnName}() -> some View {`);
        if (stroke) {
          // Stroke orphans (e.g. state-1 Vector decorations) emit .stroke()
          lines.push(`    ${segPathExpr(opts, segs, true)}`);
          lines.push(`        .stroke(${stroke}.opacity(${num(o.strokeOpacity != null ? o.strokeOpacity : 1)}), lineWidth: ${sw})`);
          lines.push(`        .opacity(${op})`);
        } else if (o.fillKind === 'gradient') {
          // Gradient orphan: render the gradient at full canvas size + mask
          // with the path so UnitPoint coords are canvas-relative (matches
          // SVG's userSpaceOnUse behavior). This avoids SwiftUI's default
          // behavior of normalizing the gradient's UnitPoint to the path's
          // tight bbox.
          lines.push(`    ${fill}`);
          lines.push(`        .frame(width: ${num(opts.viewBox.width)}, height: ${num(opts.viewBox.height)})`);
          lines.push(`        .mask(${segPathExpr(opts, segs, true)}.fill(Color.black))`);
          lines.push(`        .opacity(${op})`);
        } else {
          lines.push(`    ${segPathExpr(opts, segs, true)}`);
          lines.push(`        .fill(${fill})`);
          lines.push(`        .opacity(${op})`);
        }
        lines.push(`}`);
        lines.push(``);
      });
    }
    // Per-state ViewBuilders split by layer. Orphans tagged with _layer="back"
    // render BEHIND shared paths (e.g. state-1 ice-cube-bg). Default-front
    // orphans render IN FRONT (e.g. state-4 owl decorations on top of the snowman).
    // Each orphan is canvas-framed (so idle anchors resolve in view-box coords)
    // and wrapped with its per-element idle (spin, drip, pop-loop, star cycle).
    // idleForElement returns identity for orphans no idle part drives, so static
    // decorations are unaffected.
    const emitLayer = (fnName, layer) => {
      lines.push(`@ViewBuilder private func ${fnName}(for state: ${opts.stateEnum}, t: Double, amplitude: Double) -> some View {`);
      lines.push(`    switch state {`);
      for (const sn of opts.stateNames) {
        lines.push(`    case .${safeId(sn)}:`);
        const list = (opts.orphansByState[sn] || []).filter(o => o.layer === layer);
        const items = list.map(o => ({ fn: perStateFnNamesById[`${sn}|${o.id}`], id: o.id })).filter(x => x.fn);
        if (items.length === 0) {
          lines.push(`        EmptyView()`);
        } else {
          lines.push(`        ZStack {`);
          items.forEach(({ fn, id }) => {
            lines.push(`            ${fn}()`);
            lines.push(`                .frame(width: ${num(opts.viewBox.width)}, height: ${num(opts.viewBox.height)}, alignment: .topLeading)`);
            lines.push(`                .modifier(ElementIdleMod(e: idleForElement("${id}", in: state, t: t, amplitude: amplitude)))`);
          });
          lines.push(`        }`);
        }
      }
      lines.push(`    }`);
      lines.push(`}`);
      lines.push(``);
    };
    emitLayer('backOrphans', 'back');
    emitLayer('frontOrphans', 'front');
    return lines.join('\n');
  }

  // ---------------------------------------------------------------------------
  // Section emitters
  // ---------------------------------------------------------------------------

  function emitHeader(opts) {
    return [
      `//`,
      `// ${opts.typeName}.swift`,
      `// Auto-generated by svg-character-animator skill (scripts/export-swift.js)`,
      `// Generated: ${new Date().toISOString()}`,
      `// Source: ${opts.sourceName || '<unknown>'}`,
      `//`,
      `// Usage:`,
      `//   1. Drop this file into your Xcode project.`,
      `//   2. Embed in any view: \`${opts.typeName}()\` (it manages its own state).`,
      `//      For external control, use the public \`state\` binding initializer.`,
      ...(opts.hasOverlays ? [
      `//   3. To drive states + overlays from code, hold a \`${opts.controllerName}\``,
      `//      (e.g. @StateObject) and pass it in — everything is callable:`,
      `//         @StateObject private var c = ${opts.controllerName}()`,
      `//         ${opts.typeName}(controller: c)`,
      `//         c.setState(.${safeId(opts.stateNames[0])})              // switch looping state`,
      ...(opts.overlayInfo.emotions.length ? [
      `//         c.playOverlay(.${safeId(opts.overlayInfo.emotions[0].name)})               // play a decoration once`,
      `//         c.playOverlay(.${safeId(opts.overlayInfo.emotions[opts.overlayInfo.emotions.length - 1].name)}, loopEvery: 3)     // …or loop every 3s (stopOverlay/stopAllOverlays to end)`,
      ] : []),
      ...((opts.overlayInfo.gestures || []).length ? [
      `//         c.playGesture(.${safeId(opts.overlayInfo.gestures[0].name)})               // one-shot face gesture (stopGesture to end a loop)`,
      ] : []),
      ...(opts.overlayInfo.talk ? [`//         c.playTalk()  /* or */  c.playTalk(loopEvery: 4)   // eye/mouth talk bob`] : []),
      ...(opts.overlayInfo.look ? [`//         c.playLookAround(loopEvery: 8)               // gaze (enabled states only)`] : []),
      ] : []),
      `//`,
      `// Requirements: iOS 15+ (TimelineView), iOS 17+ recommended for smoother`,
      `// keyframeAnimator transitions. No external dependencies.`,
      `//`,
      `// What's exported:`,
      `//   - ${opts.stateNames.length} states, ${opts.sharedIds.length} shared paths`,
      `//   - Per-state idle animations (sway, breathe-y, compound, etc.)`,
      `//   - Per-state particle systems (where configured)`,
      ...(opts.hasOverlays ? [
      ...(opts.overlayInfo.emotions.length ? [
      `//   - ${opts.overlayInfo.emotions.length} one-shot / loopable decoration overlays (${opts.overlayInfo.emotions.map(e => e.name).join(', ')}),`,
      ] : []),
      ...((opts.overlayInfo.gestures || []).length ? [
      `//   - ${opts.overlayInfo.gestures.length} play-once gestures (${opts.overlayInfo.gestures.map(g => g.name).join(', ')}),`,
      ] : []),
      ...(opts.overlayInfo.talk || opts.overlayInfo.look ? [
      `//   - ${[opts.overlayInfo.talk ? 'talk' : null, opts.overlayInfo.look ? 'look-around' : null].filter(Boolean).join(' / ')} eye transient(s),`,
      ] : []),
      `//     all code-callable via ${opts.controllerName} (see Usage step 3)`,
      ] : []),
      `//   - Morph easing: ${opts.easingBezier ? `custom cubic-bezier(${opts.easingBezier.join(', ')})` : opts.morphEasing} @ ${opts.duration}ms`,
      ...(Object.keys(opts.methodOverrides || {}).length ? [
      `//   - Per-path method overrides: ${Object.entries(opts.methodOverrides).map(([k, v]) => `${k}→${String(v).toLowerCase()}`).join(', ')}`,
      ] : []),
      ...(opts.idleOverride ? [`//   - Idle override: every state plays "${opts.idleOverride}" (authored idles replaced)`] : []),
      ...(opts.idleAnchor ? [`//   - Idle anchor override: whole-body idles pivot at ${opts.idleAnchor}`] : []),
      `//   - The preview's background color is preview-only: this view renders on a`,
      `//     transparent canvas — put your own background behind it in the host app.`,
      `//`,
      `// Features handled by this generator:`,
      `//   - TRANSFORM-strategy paths: per-control-point lerp, preserves bezier curves exactly.`,
      `//   - MORPH-strategy paths: polygon-sampled to 80 vertices per state, lerped vertex-by-vertex.`,
      `//   - Multi-subpath stroke paths (hands): rigid-body translate+rotate transition`,
      `//     around the wrist anchor. Stroke caps stay welded to their fingers, no stretching.`,
      `//   - Per-path transform attributes (e.g. head tilt): animated via MorphRotation modifier.`,
      `//   - Orphan SVG decorations: rendered as native SwiftUI Paths with proper fills`,
      `//     (solid color or RadialGradient/LinearGradient matched to source defs).`,
      `//     Gradient fills use .mask() so UnitPoint normalizes to the canvas, matching`,
      `//     SVG's userSpaceOnUse semantics.`,
      `//   - Orphan crossfade: each state's orphan layer fades in/out via a separate`,
      `//     displayedOrphanState driven inside withAnimation at transition start.`,
      `//   - Particle templates: each state's orphanSVG top-level groups are rendered to`,
      `//     UIImages at build time and fed as multiple CAEmitterCells, so the emitter`,
      `//     spawns real flower variants — not a placeholder circle.`,
      `//   - Particle emission gating: emission stops immediately at the start of any`,
      `//     transition leaving the particle state; alive cells finish their lifetime.`,
      `//`,
      `// Known limitations:`,
      `//   - Elliptical/rotated gradients are approximated as circular (max axis radius).`,
      `//     Exact reproduction would need a Metal shader.`,
      `//   - Rapid interrupts during a morph re-snap to displayedState's geometry rather`,
      `//     than continuing from the live mid-morph shape (SwiftUI can't easily read its`,
      `//     own current Shape output). The JS preview reads live d's for smoother interrupts.`,
      `//   - Per-element idle (selectorAll / selector parts) is applied as a full`,
      `//     transform (offset + rotation + scale + blink squish + opacity) via`,
      `//     idleForElement + ElementIdleMod. Looping orphan bursts (orphanPopLoop)`,
      `//     start from their natural t=0 phase rather than the JS "skipAppear" first`,
      `//     cycle — steady-state is identical, only the first ~1s differs.`,
      `//`,
      `// Generated for any well-formed states file. The script handles automatically:`,
      `//   * Any number of states with any state-machine topology (N×N transitions)`,
      `//   * Per-id TRANSFORM vs MORPH strategy (fingerprinted at export time)`,
      `//   * Multi-subpath stroke paths via rigid-body translate+rotate`,
      `//   * Per-path rotate(deg cx cy) attribute animated via MorphRotation`,
      `//   * Orphan back/front layering via the source SVG's _layer hint`,
      `//   * Gradient fills (radial + linear) from <defs>, with userSpaceOnUse semantics`,
      `//   * Particle templates from BOTH orphanSVG groups AND structured _orphan paths`,
      `//   * Per-state idle: sway, breathe, breathe-y, bob, shake, waggle-sequence,`,
      `//     rotate-around-point (with optional gating), and any compound combination`,
      `//   * Crossfade orphan transitions driven by displayedOrphanState`,
      `//   * Layer-aware particle compositing (behind shared paths when configured)`,
      `//`,
      ``,
      `import SwiftUI`,
      // The overlay controller is an ObservableObject with @Published — those live
      // in Combine, and SwiftUI doesn't always re-export their initializers, so
      // import it explicitly whenever a controller is emitted.
      ...(opts.hasOverlays ? [`import Combine`] : []),
      `#if canImport(UIKit)`,
      `import UIKit`,
      `#endif`,
      ``,
    ].join('\n');
  }

  function emitStateEnum(opts) {
    const cases = opts.stateNames.map(s => `case ${safeId(s)}`).join('\n    ');
    return [
      `// MARK: - State enum`,
      ``,
      `public enum ${opts.stateEnum}: String, CaseIterable, Hashable {`,
      `    ${cases}`,
      `}`,
      ``,
    ].join('\n');
  }

  function emitPathSegmentType(opts) {
    // Labeled init arg (Path(snowmanScene:)) so this file's Path.init never competes
    // with another exported animator's — see segPathExpr. Unlabeled only when the
    // prefix was explicitly cleared.
    const initArg = opts && opts.segLabel ? `${opts.segLabel} segments` : `_ segments`;
    return [
      `// MARK: - Path segment representation`,
      ``,
      `enum MorphPathSegment {`,
      `    case move(CGPoint)`,
      `    case line(CGPoint)`,
      `    case curve(to: CGPoint, c1: CGPoint, c2: CGPoint)`,
      `    case quad(to: CGPoint, c: CGPoint)`,
      `    case close`,
      `}`,
      ``,
      `extension Path {`,
      `    init(${initArg}: [MorphPathSegment]) {`,
      `        self.init()`,
      `        for seg in segments {`,
      `            switch seg {`,
      `            case .move(let p): self.move(to: p)`,
      `            case .line(let p): self.addLine(to: p)`,
      `            case .curve(let to, let c1, let c2): self.addCurve(to: to, control1: c1, control2: c2)`,
      `            case .quad(let to, let c): self.addQuadCurve(to: to, control: c)`,
      `            case .close: self.closeSubpath()`,
      `            }`,
      `        }`,
      `    }`,
      `}`,
      ``,
      `// Lerp helpers — TRANSFORM strategy: same segment count + commands across`,
      `// states, lerp every control point. Falls back to snap on mismatch.`,
      `private func lerpP(_ a: CGPoint, _ b: CGPoint, _ t: Double) -> CGPoint {`,
      `    CGPoint(x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t)`,
      `}`,
      `// The control points of one segment, in a fixed slot order. Used by the`,
      `// rotation-aware lerp to walk corresponding points across two same-structure`,
      `// segment lists. Order is irrelevant to the centroid/theta sums and only has`,
      `// to be consistent between the two lists (it is — same command ⇒ same slots).`,
      `private func segPoints(_ s: MorphPathSegment) -> [CGPoint] {`,
      `    switch s {`,
      `    case let .move(p): return [p]`,
      `    case let .line(p): return [p]`,
      `    case let .curve(to, c1, c2): return [to, c1, c2]`,
      `    case let .quad(to, c): return [to, c]`,
      `    case .close: return []`,
      `    }`,
      `}`,
      ``,
      `// Rotation-aware control-point interpolation (2D Kabsch). Naively lerping`,
      `// each control point makes a shape that ROTATES between poses collapse toward`,
      `// its centroid at the midpoint — every vertex cuts across the chord instead`,
      `// of following the arc (this shrank a character's wings as they swung up).`,
      `//`,
      `// Fix: estimate the rigid motion between the two point sets — centroid shift`,
      `// plus the least-squares optimal rotation theta (atan2 of summed cross/dot of`,
      `// the centered points) — then lerp only the *residual* in a shared de-rotated`,
      `// frame and rotate it forward by theta*t. A pure rotation animates rigidly;`,
      `// a pure deformation (theta ~ 0) degrades to plain linear lerp exactly, so`,
      `// non-rotating parts (body, head) are unaffected. Matches the JS engine's`,
      `// interpolateStructuredPaths.`,
      `private func lerpSegments(_ a: [MorphPathSegment], _ b: [MorphPathSegment], _ t: Double) -> [MorphPathSegment] {`,
      `    guard a.count == b.count else { return t < 0.5 ? a : b }`,
      `    // Pass 1: centroids of every control point in each pose.`,
      `    var n = 0.0, sumFx = 0.0, sumFy = 0.0, sumTx = 0.0, sumTy = 0.0`,
      `    for i in 0..<a.count {`,
      `        let pf = segPoints(a[i]), pt = segPoints(b[i])`,
      `        guard pf.count == pt.count else { return t < 0.5 ? a : b }`,
      `        for j in 0..<pf.count {`,
      `            sumFx += pf[j].x; sumFy += pf[j].y`,
      `            sumTx += pt[j].x; sumTy += pt[j].y`,
      `            n += 1`,
      `        }`,
      `    }`,
      `    guard n > 0 else { return a }`,
      `    let cFx = sumFx / n, cFy = sumFy / n, cTx = sumTx / n, cTy = sumTy / n`,
      `    // Pass 2: optimal rotation theta between the centered point clouds.`,
      `    var cross = 0.0, dot = 0.0`,
      `    for i in 0..<a.count {`,
      `        let pf = segPoints(a[i]), pt = segPoints(b[i])`,
      `        for j in 0..<pf.count {`,
      `            let ax = pf[j].x - cFx, ay = pf[j].y - cFy`,
      `            let bx = pt[j].x - cTx, by = pt[j].y - cTy`,
      `            dot += ax * bx + ay * by`,
      `            cross += ax * by - ay * bx`,
      `        }`,
      `    }`,
      `    let theta = atan2(cross, dot)`,
      `    let cxT = cFx + (cTx - cFx) * t, cyT = cFy + (cTy - cFy) * t  // centroid(t)`,
      `    let ang = theta * t`,
      `    let co = cos(ang), si = sin(ang)        // forward R(theta*t)`,
      `    let coN = cos(theta), siN = sin(theta)  // R(-theta) via (coN, -siN)`,
      `    func xform(_ fa: CGPoint, _ fb: CGPoint) -> CGPoint {`,
      `        let ax = fa.x - cFx, ay = fa.y - cFy`,
      `        // to-residual de-rotated into from's frame: R(-theta) * (b - cT)`,
      `        let bx0 = fb.x - cTx, by0 = fb.y - cTy`,
      `        let bx = bx0 * coN + by0 * siN`,
      `        let by = -bx0 * siN + by0 * coN`,
      `        // lerp residual in shared frame, then rotate forward by theta*t`,
      `        let rx = ax + (bx - ax) * t`,
      `        let ry = ay + (by - ay) * t`,
      `        return CGPoint(x: cxT + (rx * co - ry * si), y: cyT + (rx * si + ry * co))`,
      `    }`,
      `    var out: [MorphPathSegment] = []`,
      `    out.reserveCapacity(a.count)`,
      `    for i in 0..<a.count {`,
      `        switch (a[i], b[i]) {`,
      `        case let (.move(p1), .move(p2)): out.append(.move(xform(p1, p2)))`,
      `        case let (.line(p1), .line(p2)): out.append(.line(xform(p1, p2)))`,
      `        case let (.curve(to1, c1a, c2a), .curve(to2, c1b, c2b)):`,
      `            out.append(.curve(to: xform(to1, to2), c1: xform(c1a, c1b), c2: xform(c2a, c2b)))`,
      `        case let (.quad(to1, c1), .quad(to2, c2)):`,
      `            out.append(.quad(to: xform(to1, to2), c: xform(c1, c2)))`,
      `        case (.close, .close): out.append(.close)`,
      `        default: out.append(t < 0.5 ? a[i] : b[i])`,
      `        }`,
      `    }`,
      `    return out`,
      `}`,
      ``,
    ].join('\n');
  }

  // Emit a SwiftUI AnimatableModifier that lerps rotation degrees from
  // (fromDeg, fromPivot) to (toDeg, toPivot) as a function of `progress`.
  // Used per shared id whose transform attribute differs across states
  // (e.g. the snowman head's state-1 tilt of 12.99° around its center).
  function emitMorphRotationModifier(opts) {
    if (!opts.anyPathHasTransform) {
      // No path has a transform — skip emission entirely. The main view will
      // also skip the .modifier(MorphRotation(...)) wrapping when this is false.
      return [
        `// (No paths have per-state rotation transforms — MorphRotation omitted.)`,
        ``,
      ].join('\n');
    }
    return [
      `// MARK: - Per-path rotation animation`,
      ``,
      `// AnimatableModifier that lerps a rotation around a configurable pivot.`,
      `// Used by shared paths whose source SVG had a "rotate(deg cx cy)"`,
      `// transform attribute in one state but not another (or with a different`,
      `// angle/pivot per state). The pivot is given in SVG user-space coords;`,
      `// we convert to UnitPoint via the known canvas size at modifier construction.`,
      `struct MorphRotation: AnimatableModifier {`,
      `    var fromDeg: Double`,
      `    var toDeg: Double`,
      `    let pivotX: Double         // SVG user-space x (constant across the tween)`,
      `    let pivotY: Double         // SVG user-space y`,
      `    let canvasWidth: Double`,
      `    let canvasHeight: Double`,
      `    var progress: Double`,
      ``,
      `    // SwiftUI drives progress smoothly between the values we set in the`,
      `    // main view (0 → 1 during a morph). fromDeg/toDeg are captured at`,
      `    // transition kickoff and stay constant across the tween.`,
      `    var animatableData: Double {`,
      `        get { progress }`,
      `        set { progress = newValue }`,
      `    }`,
      ``,
      `    func body(content: Content) -> some View {`,
      `        let deg = fromDeg + (toDeg - fromDeg) * progress`,
      `        return content.rotationEffect(`,
      `            .degrees(deg),`,
      `            anchor: UnitPoint(x: pivotX / canvasWidth, y: pivotY / canvasHeight)`,
      `        )`,
      `    }`,
      `}`,
      ``,
    ].join('\n');
  }

  // Emit a SwiftUI AnimatableModifier for rigid-body transitions (used by
  // multi-subpath stroke paths like the hands). Renders the canonical shape
  // and animates it from displayedState's (anchor, angle) to targetState's
  // (anchor, angle) — translation + rotation, no deformation.
  function emitRigidBodyModifier(opts) {
    if (opts.multiSubpathIds.length === 0) {
      return [`// (No multi-subpath paths — RigidBody modifier omitted.)`, ``].join('\n');
    }
    return [
      `// MARK: - Rigid-body transitions for multi-subpath paths`,
      ``,
      `// Multi-subpath stroke paths (snowman hands) transition as rigid rotations`,
      `// rather than per-stroke deformations. This modifier lerps an (anchor,`,
      `// angleDelta) pair from displayedState's pose to targetState's pose,`,
      `// applied as .rotationEffect (around the live anchor) + .offset.`,
      `//`,
      `// The rendered shape is ALWAYS the canonical state's geometry. The`,
      `// modifier just repositions it. This preserves stroke-cap positions and`,
      `// stroke lengths perfectly — they were equal across states to begin with.`,
      `struct RigidBody: AnimatableModifier {`,
      `    var fromAngleDelta: Double         // degrees relative to canonical`,
      `    var toAngleDelta: Double`,
      `    var fromOffsetX: Double            // SVG user-space offset from canonical anchor`,
      `    var fromOffsetY: Double`,
      `    var toOffsetX: Double`,
      `    var toOffsetY: Double`,
      `    let canonicalAnchorX: Double       // pivot in SVG user-space (constant)`,
      `    let canonicalAnchorY: Double`,
      `    let canvasWidth: Double`,
      `    let canvasHeight: Double`,
      `    var progress: Double`,
      ``,
      `    var animatableData: Double {`,
      `        get { progress }`,
      `        set { progress = newValue }`,
      `    }`,
      ``,
      `    func body(content: Content) -> some View {`,
      `        let angle = fromAngleDelta + (toAngleDelta - fromAngleDelta) * progress`,
      `        let dx = fromOffsetX + (toOffsetX - fromOffsetX) * progress`,
      `        let dy = fromOffsetY + (toOffsetY - fromOffsetY) * progress`,
      `        // Rotate around the canonical anchor (UnitPoint-normalized), then`,
      `        // offset to reach the target anchor. The order matters: rotating`,
      `        // first keeps the anchor fixed in canvas space during rotation, and`,
      `        // the offset then translates the rotated geometry.`,
      `        return content`,
      `            .rotationEffect(`,
      `                .degrees(angle),`,
      `                anchor: UnitPoint(x: canonicalAnchorX / canvasWidth, y: canonicalAnchorY / canvasHeight)`,
      `            )`,
      `            .offset(x: dx, y: dy)`,
      `    }`,
      `}`,
      ``,
    ].join('\n');
  }

  // Emit the per-(id, state) rotation lookup. Used by the main view to grab
  // fromRot/toRot at transition time. Falls back to (0, no pivot) when a path
  // has no transform in a given state.
  function emitRotationLookup(opts) {
    if (!opts.anyPathHasTransform) return '';
    const lines = [
      `private struct PathRotation { let deg: Double; let pivot: CGPoint? }`,
      ``,
      `private func pathRotation(for id: String, in state: ${opts.stateEnum}) -> PathRotation {`,
      `    switch (id, state) {`,
    ];
    for (const id of opts.sharedIds) {
      for (const sn of opts.stateNames) {
        const tx = opts.pathTransforms[id][sn];
        if (tx.deg === 0) continue;  // default-emission below handles this
        const pivot = tx.pivot
          ? `CGPoint(x: ${num(tx.pivot[0])}, y: ${num(tx.pivot[1])})`
          : `nil`;
        lines.push(`    case ("${id}", .${safeId(sn)}): return PathRotation(deg: ${num(tx.deg)}, pivot: ${pivot})`);
      }
    }
    lines.push(`    default: return PathRotation(deg: 0, pivot: nil)`);
    lines.push(`    }`);
    lines.push(`}`);
    lines.push(``);
    lines.push(`// Returns true if the given id ever has a non-zero rotation in any state.`);
    lines.push(`// Used to skip the MorphRotation modifier wrapping when not needed.`);
    lines.push(`private func hasRotation(_ id: String) -> Bool {`);
    const idsWithRot = opts.sharedIds.filter(id =>
      opts.stateNames.some(sn => opts.pathTransforms[id][sn].deg !== 0)
    );
    if (idsWithRot.length === 0) {
      lines.push(`    return false`);
    } else {
      lines.push(`    switch id {`);
      idsWithRot.forEach(id => lines.push(`    case "${id}": return true`));
      lines.push(`    default: return false`);
      lines.push(`    }`);
    }
    lines.push(`}`);
    lines.push(``);
    return lines.join('\n');
  }

  // Per-(id, state) rigid-body params lookup. For each multi-subpath id, every
  // state has an (anchor, angle). The canonical anchor/angle is the first state's.
  // angleDelta and offset returned by `rigidPose` are relative to the canonical,
  // ready for direct use in the RigidBody modifier.
  function emitRigidLookup(opts) {
    if (opts.multiSubpathIds.length === 0) return '';
    const lines = [
      `// MARK: - Rigid pose lookup (multi-subpath ids only)`,
      ``,
      `private struct RigidPose {`,
      `    let angleDelta: Double      // degrees relative to canonical`,
      `    let offsetX: Double         // SVG user-space offset from canonical anchor`,
      `    let offsetY: Double`,
      `}`,
      ``,
      `private func rigidPose(for id: String, in state: ${opts.stateEnum}) -> RigidPose {`,
      `    switch (id, state) {`,
    ];
    for (const id of opts.multiSubpathIds) {
      const canonical = opts.rigidParams[id][opts.canonicalStateName];
      for (const sn of opts.stateNames) {
        const p = opts.rigidParams[id][sn];
        let delta = p.angle - canonical.angle;
        // Wrap to [-180, 180] so we pick the short direction of rotation.
        while (delta > 180) delta -= 360;
        while (delta < -180) delta += 360;
        const ox = p.anchor[0] - canonical.anchor[0];
        const oy = p.anchor[1] - canonical.anchor[1];
        lines.push(`    case ("${id}", .${safeId(sn)}): return RigidPose(angleDelta: ${num(delta)}, offsetX: ${num(ox)}, offsetY: ${num(oy)})`);
      }
    }
    lines.push(`    default: return RigidPose(angleDelta: 0, offsetX: 0, offsetY: 0)`);
    lines.push(`    }`);
    lines.push(`}`);
    lines.push(``);
    lines.push(`// Canonical anchor (used as the rotation pivot for the rigid body).`);
    lines.push(`private func rigidCanonicalAnchor(for id: String) -> CGPoint {`);
    lines.push(`    switch id {`);
    for (const id of opts.multiSubpathIds) {
      const c = opts.rigidParams[id][opts.canonicalStateName];
      lines.push(`    case "${id}": return CGPoint(x: ${num(c.anchor[0])}, y: ${num(c.anchor[1])})`);
    }
    lines.push(`    default: return CGPoint(x: 0, y: 0)`);
    lines.push(`    }`);
    lines.push(`}`);
    lines.push(``);
    lines.push(`// True if this id should render via rigid-body transitions (multi-subpath).`);
    lines.push(`private func isRigidBody(_ id: String) -> Bool {`);
    if (opts.multiSubpathIds.length === 0) {
      lines.push(`    return false`);
    } else {
      lines.push(`    switch id {`);
      opts.multiSubpathIds.forEach(id => lines.push(`    case "${id}": return true`));
      lines.push(`    default: return false`);
      lines.push(`    }`);
    }
    lines.push(`}`);
    lines.push(``);
    return lines.join('\n');
  }

  function emitMorphShape(opts) {
    return [
      `// MARK: - Animatable shapes`,
      ``,
      `// TRANSFORM-strategy morph: paths share the same command structure across`,
      `// all source states, so we lerp control points directly. Bezier curves are`,
      `// preserved exactly — the silhouette never goes polygonal.`,
      `struct MorphShape: Shape {`,
      `    var from: [MorphPathSegment]`,
      `    var to: [MorphPathSegment]`,
      `    var progress: Double`,
      ``,
      `    var animatableData: Double {`,
      `        get { progress }`,
      `        set { progress = newValue }`,
      `    }`,
      ``,
      `    func path(in rect: CGRect) -> Path {`,
      `        ${segPathExpr(opts, 'lerpSegments(from, to, progress)', false)}`,
      `    }`,
      `}`,
      ``,
      `// MORPH-strategy morph: paths have different command structures across`,
      `// states (e.g. the snowman body, which redraws its silhouette between`,
      `// stress and joy). We pre-sample each state's path at export time into a`,
      `// uniform polygon (N points, evenly spaced along arc length), then lerp`,
      `// vertex-by-vertex. The resulting shape is polygonal — bezier curves are`,
      `// approximated by line segments — but the morph itself is smooth.`,
      `//`,
      `// AnimatablePair lets SwiftUI's animation system drive only progress;`,
      `// the polygon arrays themselves are static (resolved at compile time).`,
      `struct MorphPolygonShape: Shape {`,
      `    var fromPoly: [CGPoint]`,
      `    var toPoly: [CGPoint]`,
      `    var progress: Double`,
      ``,
      `    var animatableData: Double {`,
      `        get { progress }`,
      `        set { progress = newValue }`,
      `    }`,
      ``,
      `    func path(in rect: CGRect) -> Path {`,
      `        var path = Path()`,
      `        let n = min(fromPoly.count, toPoly.count)`,
      `        guard n > 1 else { return path }`,
      `        let t = progress`,
      `        path.move(to: lerpP(fromPoly[0], toPoly[0], t))`,
      `        for i in 1..<n {`,
      `            path.addLine(to: lerpP(fromPoly[i], toPoly[i], t))`,
      `        }`,
      `        path.closeSubpath()`,
      `        return path`,
      `    }`,
      `}`,
      ``,
    ].join('\n');
  }

  function emitPathData(opts, parsed, strategies, polygons) {
    const lines = [`// MARK: - Path data (parsed from source SVG at export time)`, ``, `private enum PathData {`];
    for (const id of opts.sharedIds) {
      const strat = strategies[id];
      const subCount = opts.subpathCounts[id];
      for (const sn of opts.stateNames) {
        const subs = opts.parsedSubs[id]?.[sn] || [];
        // TRANSFORM lerps segments; CROSSFADE / SCALE render each state's
        // segments statically — all three need per-state segment arrays.
        if (strat !== 'MORPH') {
          // Emit one segment array per subpath. If this state has fewer
          // subpaths than the max, pad with the last available subpath so the
          // Swift renderer can always index by subpath count without bounds
          // checks (visually equivalent — those extra "ghost" subpaths morph
          // from current to a duplicate of themselves, i.e. don't change).
          for (let s = 0; s < subCount; s++) {
            const segs = subs[s] || subs[subs.length - 1] || [];
            const swiftSegs = segs.map(segmentToSwift).join(',\n        ');
            lines.push(`    static let ${safeId(id)}_${safeId(sn)}_sub${s}: [MorphPathSegment] = [`);
            lines.push(`        ${swiftSegs}`);
            lines.push(`    ]`);
          }
        } else {
          // MORPH strategy: still polygon-sample the WHOLE path (across all
          // subpaths). Polygon morphing for multi-subpath would need per-sub
          // sampling which we punt on for v1; merged polygon usually fine.
          const poly = polygons[id][sn];
          const swiftPts = poly.map(p => `CGPoint(x: ${num(p[0])}, y: ${num(p[1])})`).join(',\n        ');
          lines.push(`    static let ${safeId(id)}_${safeId(sn)}_poly: [CGPoint] = [`);
          lines.push(`        ${swiftPts}`);
          lines.push(`    ]`);
        }
      }
    }
    lines.push(`}`);
    lines.push(``);
    return lines.join('\n');
  }

  function emitSegmentLookup(opts, strategies) {
    // Every non-MORPH id needs the per-state segment lookup (TRANSFORM lerps
    // them; CROSSFADE / SCALE render them statically per state).
    const segIds = opts.sharedIds.filter(id => strategies[id] !== 'MORPH');
    const morphIds = opts.sharedIds.filter(id => strategies[id] === 'MORPH');
    const byStrat = (s) => opts.sharedIds.filter(id => strategies[id] === s);
    const lines = [
      `// MARK: - Per-state lookup`,
      ``,
      `// Strategy assignments (path-command structure + preview method overrides):`,
      `//   TRANSFORM (${byStrat('TRANSFORM').length}): ${byStrat('TRANSFORM').join(', ')}`,
      `//   MORPH     (${morphIds.length}): ${morphIds.join(', ')}`,
      ...(byStrat('CROSSFADE').length ? [`//   CROSSFADE (${byStrat('CROSSFADE').length}): ${byStrat('CROSSFADE').join(', ')}`] : []),
      ...(byStrat('SCALE').length ? [`//   SCALE     (${byStrat('SCALE').length}): ${byStrat('SCALE').join(', ')}`] : []),
      ``,
      `// Subpath counts per id (most are 1; stroke paths like hands have N).`,
      `private func subpathCount(forId id: String) -> Int {`,
      `    switch id {`,
    ];
    for (const id of opts.sharedIds) {
      lines.push(`    case "${id}": return ${opts.subpathCounts[id]}`);
    }
    lines.push(`    default: return 1`);
    lines.push(`    }`);
    lines.push(`}`);
    lines.push(``);
    lines.push(`// Subpath-aware segment lookup. For each (id, subpathIndex, state) returns`);
    lines.push(`// the parsed segments to feed into MorphShape. Out-of-range subpaths return [].`);
    lines.push(`private func segments(for id: String, subpath s: Int, in state: ${opts.stateEnum}) -> [MorphPathSegment] {`);
    lines.push(`    switch (id, s, state) {`);
    for (const id of segIds) {
      const subCount = opts.subpathCounts[id];
      for (let s = 0; s < subCount; s++) {
        for (const sn of opts.stateNames) {
          lines.push(`    case ("${id}", ${s}, .${safeId(sn)}): return PathData.${safeId(id)}_${safeId(sn)}_sub${s}`);
        }
      }
    }
    lines.push(`    default: return []`);
    lines.push(`    }`);
    lines.push(`}`);
    lines.push(``);
    lines.push(`private func polygon(for id: String, in state: ${opts.stateEnum}) -> [CGPoint] {`);
    lines.push(`    switch (id, state) {`);
    for (const id of morphIds) {
      for (const sn of opts.stateNames) {
        lines.push(`    case ("${id}", .${safeId(sn)}): return PathData.${safeId(id)}_${safeId(sn)}_poly`);
      }
    }
    lines.push(`    default: return []`);
    lines.push(`    }`);
    lines.push(`}`);
    lines.push(``);
    if (opts.hasFillChanges) {
      lines.push(`// Per-state flat fills (ids whose color differs across states). Driven by`);
      lines.push(`// the animated \`fillState\`, so SwiftUI interpolates the color with the`);
      lines.push(`// morph — mirrors the JS engine's runFillTween.`);
      lines.push(`private func fillColor(for id: String, in state: ${opts.stateEnum}) -> Color {`);
      lines.push(`    switch (id, state) {`);
      for (const id of Object.keys(opts.fillByState)) {
        for (const sn of opts.stateNames) {
          lines.push(`    case ("${id}", .${safeId(sn)}): return ${hexToSwiftColor(opts.fillByState[id][sn])}`);
        }
      }
      lines.push(`    default: return Color.gray`);
      lines.push(`    }`);
      lines.push(`}`);
      lines.push(``);
    }
    lines.push(`// Returns true if this shared id uses the polygon (MORPH) renderer.`);
    lines.push(`private func isPolyMorph(_ id: String) -> Bool {`);
    if (morphIds.length === 0) {
      lines.push(`    return false`);
    } else {
      lines.push(`    switch id {`);
      morphIds.forEach(id => lines.push(`    case "${id}": return true`));
      lines.push(`    default: return false`);
      lines.push(`    }`);
    }
    lines.push(`}`);
    lines.push(``);
    return lines.join('\n');
  }

  // Control-point bbox of a parsed segment list (all subpaths). Slightly
  // overestimates curvy shapes but is stable across states and matches the
  // JS engine's computePathBBox, which drives the preview's SCALE method.
  function segsBBox(segsList) {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const segs of segsList) {
      for (const seg of segs) {
        for (const p of (seg.pts || [])) {
          if (p[0] < minX) minX = p[0]; if (p[0] > maxX) maxX = p[0];
          if (p[1] < minY) minY = p[1]; if (p[1] > maxY) maxY = p[1];
        }
      }
    }
    if (minX === Infinity) return { x: 0, y: 0, w: 0, h: 0 };
    return { x: minX, y: minY, w: maxX - minX, h: maxY - minY };
  }

  // Preview method overrides (CROSSFADE / SCALE) — the AnimatableModifiers +
  // per-state bbox lookup they need. Emitted only when a states file / preview
  // session actually forces one of these methods, so override-free exports are
  // byte-identical to before.
  function emitMethodOverrideHelpers(opts) {
    const crossfadeIds = opts.sharedIds.filter(id => opts.strategies[id] === 'CROSSFADE');
    const scaleIds = opts.sharedIds.filter(id => opts.strategies[id] === 'SCALE');
    if (crossfadeIds.length === 0 && scaleIds.length === 0) return '';
    const lines = [
      `// MARK: - Preview method overrides (crossfade / scale)`,
      ``,
    ];
    if (crossfadeIds.length > 0) {
      lines.push(
        `// CROSSFADE method: fade the displayed geometry out over the first half of`,
        `// the morph and the target geometry in over the second half (sine-eased),`,
        `// driven by the same animatable progress as every other morph modifier —`,
        `// matches the JS engine's runCrossfadeTween.`,
        `struct CrossfadeFadeMod: AnimatableModifier {`,
        `    var progress: Double`,
        `    var fadeIn: Bool`,
        `    var animatableData: Double {`,
        `        get { progress }`,
        `        set { progress = newValue }`,
        `    }`,
        `    func body(content: Content) -> some View {`,
        `        let u = fadeIn ? min(1, max(0, (progress - 0.5) * 2)) : min(1, max(0, progress * 2))`,
        `        let eased = -(cos(.pi * u) - 1) / 2`,
        `        return content.opacity(fadeIn ? eased : 1 - eased)`,
        `    }`,
        `}`,
        ``,
      );
    }
    if (scaleIds.length > 0) {
      lines.push(
        `// SCALE method: rigidly map the displayed geometry's bounding box onto the`,
        `// target's (translate + scale about the canvas origin) with zero contour`,
        `// morphing — matches the JS engine's runScaleTween (transform-origin 0 0).`,
        `struct ScaleMorphMod: AnimatableModifier {`,
        `    var progress: Double`,
        `    var from: CGRect`,
        `    var to: CGRect`,
        `    var animatableData: Double {`,
        `        get { progress }`,
        `        set { progress = newValue }`,
        `    }`,
        `    func body(content: Content) -> some View {`,
        `        let sx = from.width > 0.001 ? to.width / from.width : 1`,
        `        let sy = from.height > 0.001 ? to.height / from.height : 1`,
        `        let csx = 1 + (sx - 1) * progress`,
        `        let csy = 1 + (sy - 1) * progress`,
        `        let tx = (from.minX + (to.minX - from.minX) * progress) - from.minX * csx`,
        `        let ty = (from.minY + (to.minY - from.minY) * progress) - from.minY * csy`,
        `        return content`,
        `            .scaleEffect(x: CGFloat(csx), y: CGFloat(csy), anchor: .topLeading)`,
        `            .offset(x: CGFloat(tx), y: CGFloat(ty))`,
        `    }`,
        `}`,
        ``,
        `// Per-state control-point bounding boxes for SCALE-method ids.`,
        `private func scaleBox(for id: String, in state: ${opts.stateEnum}) -> CGRect {`,
        `    switch (id, state) {`,
      );
      for (const id of scaleIds) {
        for (const sn of opts.stateNames) {
          const b = segsBBox(opts.parsedSubs[id][sn]);
          lines.push(`    case ("${id}", .${safeId(sn)}): return CGRect(x: ${num(b.x)}, y: ${num(b.y)}, width: ${num(b.w)}, height: ${num(b.h)})`);
        }
      }
      lines.push(
        `    default: return .zero`,
        `    }`,
        `}`,
        ``,
      );
    }
    return lines.join('\n');
  }

  function emitIdleConfig(opts, states) {
    // Per-state idle config struct literal. The Swift IdleAnimator interprets
    // these the same way the JS IdleAnimator does — same trig, same gating.
    const lines = [
      `// MARK: - Idle animations`,
      ``,
      `// One IdlePart per concurrent motion within a state. The Swift idle layer`,
      `// uses sin(t * 2π / duration) just like the JS engine, scaled by amplitude`,
      `// and the live amplitude (which we ramp during morphs).`,
      `struct IdlePart {`,
      `    var kind: String                     // "sway", "breathe-y", "rotate-around-point", "waggle-sequence"`,
      `    var duration: Double = 1.5`,
      `    var amplitude: Double = 2.0`,
      `    var pivot: CGPoint? = nil            // for rotate-around-point`,
      `    var anchor: UnitPoint? = nil         // pivot override (authored origin / preview anchor card); nil → kind default`,
      `    var selector: String? = nil          // logical id like "handl" (no "#path-" prefix here)`,
      `    var cycleDuration: Double = 4.5      // for waggle-sequence`,
      `    var restFraction: Double = 0.25      // for waggle-sequence`,
      `    var gateCycle: Double? = nil         // optional gate (sec)`,
      `    var gateRange: ClosedRange<Double>? = nil    // [0..1] of gate cycle when active`,
      `    var gateFade: Double = 0.05`,
      `    // "float" (buoyant flight) params:`,
      `    var baseLift: Double = 0             // raised baseline (flies higher)`,
      `    var asymmetry: Double = 0.5          // fraction of the cycle spent descending (slow fall)`,
      `    var floatRotate: Double = 0          // body-tilt amplitude (deg)`,
      `    var rotateDuration: Double = 0       // 0 → derive from duration`,
      `    var drift: Double = 0                // horizontal sway amplitude (px)`,
      `    var driftDuration: Double = 0        // 0 → derive from duration`,
      `}`,
      ``,
      `private func idleParts(for state: ${opts.stateEnum}) -> [IdlePart] {`,
      `    switch state {`,
    ];
    for (const sn of opts.stateNames) {
      const idle = states[sn].idle;
      // Whole-body parts only (no selector / selectorAll) feed the root transform.
      // Per-element parts (selectorAll / selector) are driven by idleForElement
      // (see emitElementIdle) so they attach to their own anatomical pivots.
      const parts = idleConfigToParts(idle).filter(p => !p.selectorAll && !p.selector);
      const swiftParts = parts.map(p => idlePartToSwift(p, opts)).join(',\n        ');
      lines.push(`    case .${safeId(sn)}: return [`);
      if (parts.length === 0) {
        lines.push(`        // No idle configured`);
      } else {
        lines.push(`        ${swiftParts}`);
      }
      lines.push(`    ]`);
    }
    lines.push(`    }`);
    lines.push(`}`);
    lines.push(``);
    return lines.join('\n');
  }

  function idleConfigToParts(idle) {
    if (!idle) return [];
    if (typeof idle === 'string') return [{ kind: idle }];
    if (idle.kind === 'compound' && Array.isArray(idle.parts)) return idle.parts;
    return [idle];
  }

  // Parse a transform-origin string ("136px 360px", "50% 100%", "136 360")
  // into canvas-normalized UnitPoint fractions. Returns null when absent or
  // unparseable (→ the kind's default pivot).
  function originToUnit(originStr, viewBox) {
    if (!originStr) return null;
    const toks = String(originStr).trim().split(/\s+/);
    if (toks.length < 2) return null;
    const conv = (tok, dim) => tok.endsWith('%') ? parseFloat(tok) / 100 : parseFloat(tok) / dim;
    const x = conv(toks[0], viewBox.width);
    const y = conv(toks[1], viewBox.height);
    return (isFinite(x) && isFinite(y)) ? { x, y } : null;
  }

  function idlePartToSwift(p, opts) {
    const lines = [`IdlePart(kind: "${p.kind}"`];
    if (p.duration != null) lines.push(`duration: ${num(p.duration)}`);
    if (p.amplitude != null) lines.push(`amplitude: ${num(p.amplitude)}`);
    if (p.pivot) lines.push(`pivot: CGPoint(x: ${num(p.pivot[0])}, y: ${num(p.pivot[1])})`);
    // Anchor precedence (matches the JS engine): the preview's idle-anchor
    // override wins over the part's authored `origin`, which wins over
    // the kind's default pivot.
    {
      const a = originToUnit(opts && opts.idleAnchor, opts.viewBox) || originToUnit(p.origin, opts.viewBox);
      if (a) lines.push(`anchor: UnitPoint(x: ${num(a.x)}, y: ${num(a.y)})`);
    }
    if (p.selector) {
      const id = String(p.selector).replace(/^#path-/, '');
      lines.push(`selector: "${id}"`);
    }
    if (p.cycleDuration != null) lines.push(`cycleDuration: ${num(p.cycleDuration)}`);
    if (p.restFraction != null) lines.push(`restFraction: ${num(p.restFraction)}`);
    if (p.gateCycle != null) lines.push(`gateCycle: ${num(p.gateCycle)}`);
    if (p.gateRange) lines.push(`gateRange: ${rangeNum(p.gateRange[0])}...${rangeNum(p.gateRange[1])}`);
    if (p.gateFade != null) lines.push(`gateFade: ${num(p.gateFade)}`);
    // "float" params (buoyant flight). `rotate`/`drift` in the config map to
    // floatRotate/drift here (rotate/drift-Duration default to 0 → derived).
    if (p.baseLift != null) lines.push(`baseLift: ${num(p.baseLift)}`);
    if (p.asymmetry != null) lines.push(`asymmetry: ${num(p.asymmetry)}`);
    if (p.rotate != null) lines.push(`floatRotate: ${num(p.rotate)}`);
    if (p.rotateDuration != null) lines.push(`rotateDuration: ${num(p.rotateDuration)}`);
    if (p.drift != null) lines.push(`drift: ${num(p.drift)}`);
    if (p.driftDuration != null) lines.push(`driftDuration: ${num(p.driftDuration)}`);
    return lines.join(', ') + ')';
  }

  function emitIdleEvaluator() {
    // Pure-Swift idle evaluator. Given current time t and amplitude, produce
    // an "IdleTransform" per part — a tuple of (translation, rotation_deg,
    // scaleX, scaleY, origin) that the main view applies via .modifier()-like
    // composition. We keep this simple: each part returns a transform that's
    // applied to either the whole SVG or a named child (selector).
    return [
      `// Each part evaluates to a CGAffineTransform applied via .modifier on the`,
      `// matching layer. Whole-character parts (sway, breathe-y, waggle-sequence)`,
      `// have selector == nil and target the root. rotate-around-point has a`,
      `// selector and targets that named child.`,
      `struct IdleTransform {`,
      `    var translation: CGSize = .zero`,
      `    var rotationDegrees: Double = 0`,
      `    var scale: CGSize = CGSize(width: 1, height: 1)`,
      `    var anchor: UnitPoint = UnitPoint(x: 0.5, y: 1.0)  // bottom-center default`,
      `    var pivotAbsolute: CGPoint? = nil                  // for rotate-around-point`,
      `}`,
      ``,
      `// easeInOutSine in [0, 1]`,
      `private func easeInOutSine(_ t: Double) -> Double { -(cos(.pi * t) - 1) / 2 }`,
      ``,
      `// NOTE: per-element idle (selectorAll / selector parts — wing flaps, blink,`,
      `// spin, drip, nod sub-groups, pop-loop) is handled by idleForElement and the`,
      `// ElementIdleMod modifier in the "Per-element idle" section below, which`,
      `// returns a FULL transform (offset + rotation + scale + squish + opacity),`,
      `// not just a rotation. evaluateIdle here drives only WHOLE-BODY root parts.`,
      ``,
      `private func evaluateIdle(_ part: IdlePart, t: Double, amplitude: Double) -> IdleTransform {`,
      `    var x = IdleTransform()`,
      `    let amp = amplitude`,
      `    switch part.kind {`,
      `    case "sway":`,
      `        x.rotationDegrees = part.amplitude * amp * sin(t * 2 * .pi / part.duration)`,
      `    case "breathe":`,
      `        let v = 1 + part.amplitude * amp * (0.5 + 0.5 * sin(t * 2 * .pi / part.duration))`,
      `        x.scale = CGSize(width: v, height: v)`,
      `    case "breathe-y":`,
      `        let v = 1 + part.amplitude * amp * sin(t * 2 * .pi / part.duration)`,
      `        x.scale = CGSize(width: 1, height: v)`,
      `    case "bob":`,
      `        x.translation = CGSize(width: 0, height: -part.amplitude * amp * (0.5 + 0.5 * sin(t * 2 * .pi / part.duration)))`,
      `    case "nod":`,
      `        // Whole-body head-raise: rises from baseline (0 → up → 0), never dips.`,
      `        x.translation = CGSize(width: 0, height: -part.amplitude * amp * (0.5 - 0.5 * cos(t * 2 * .pi / part.duration)))`,
      `    case "shake":`,
      `        x.rotationDegrees = part.amplitude * amp * sin(t * 2 * .pi / part.duration)`,
      `    case "waggle-sequence":`,
      `        let cycle = part.cycleDuration`,
      `        let A = part.amplitude`,
      `        let rest = part.restFraction`,
      `        let motion = 1 - rest`,
      `        let TOTAL = 12.8`,
      `        let u = motion / TOTAL`,
      `        let rampLeftEnd = 4 * u`,
      `        let holdLeftEnd = rampLeftEnd + 0.4 * u`,
      `        let rampToRightEnd = holdLeftEnd + 4 * u`,
      `        let holdRightEnd = rampToRightEnd + 0.4 * u`,
      `        let rampBackEnd = motion`,
      `        let phase = (t.truncatingRemainder(dividingBy: cycle)) / cycle`,
      `        var angle = 0.0`,
      `        if phase < rampLeftEnd {`,
      `            angle = -A * easeInOutSine(phase / rampLeftEnd)`,
      `        } else if phase < holdLeftEnd {`,
      `            angle = -A`,
      `        } else if phase < rampToRightEnd {`,
      `            angle = -A + 2 * A * easeInOutSine((phase - holdLeftEnd) / (rampToRightEnd - holdLeftEnd))`,
      `        } else if phase < holdRightEnd {`,
      `            angle = A`,
      `        } else if phase < rampBackEnd {`,
      `            angle = A * (1 - easeInOutSine((phase - holdRightEnd) / (rampBackEnd - holdRightEnd)))`,
      `        }`,
      `        x.rotationDegrees = angle * amp`,
      `    case "rotate-around-point":`,
      `        var gateAmp = 1.0`,
      `        if let gateCycle = part.gateCycle, let gateRange = part.gateRange {`,
      `            let gPhase = (t.truncatingRemainder(dividingBy: gateCycle)) / gateCycle`,
      `            let from = gateRange.lowerBound`,
      `            let to = gateRange.upperBound`,
      `            let fade = part.gateFade`,
      `            if gPhase < from || gPhase > to { gateAmp = 0 }`,
      `            else if gPhase < from + fade { gateAmp = easeInOutSine((gPhase - from) / fade) }`,
      `            else if gPhase > to - fade { gateAmp = easeInOutSine((to - gPhase) / fade) }`,
      `        }`,
      `        x.rotationDegrees = part.amplitude * amp * gateAmp * sin(t * 2 * .pi / part.duration)`,
      `        x.pivotAbsolute = part.pivot`,
      `    case "float":`,
      `        // Buoyant flight (ported from the JS engine): a raised baseline plus an`,
      `        // asymmetric vertical bob (quick rise, slow fall), a gentle horizontal`,
      `        // drift, and a slight body tilt — incommensurate periods so it never`,
      `        // quite repeats. Whole-body, anchored at center (matches origin 50% 50%).`,
      `        let d = part.duration`,
      `        let rotDur = part.rotateDuration > 0 ? part.rotateDuration : d * 1.7`,
      `        let driftDur = part.driftDuration > 0 ? part.driftDuration : d * 1.3`,
      `        let phase = (t.truncatingRemainder(dividingBy: d)) / d`,
      `        let rise = max(0.05, 1 - part.asymmetry)`,
      `        let h = phase < rise`,
      `            ? easeInOutSine(phase / rise)`,
      `            : 1 - easeInOutSine((phase - rise) / part.asymmetry)`,
      `        let ty = -(part.baseLift + part.amplitude * h) * amp`,
      `        let tx = part.drift * amp * sin(t * 2 * .pi / driftDur)`,
      `        x.translation = CGSize(width: tx, height: ty)`,
      `        x.rotationDegrees = part.floatRotate * amp * sin(t * 2 * .pi / rotDur)`,
      `        x.anchor = UnitPoint(x: 0.5, y: 0.5)`,
      `    default:`,
      `        break`,
      `    }`,
      `    // An explicit anchor (authored part origin or the preview's idle-anchor`,
      `    // anchor override) wins over the kind's default pivot — matches the JS`,
      `    // engine's originOverride precedence.`,
      `    if let a = part.anchor { x.anchor = a }`,
      `    return x`,
      `}`,
      ``,
    ].join('\n');
  }

  // Per-element idle (selectorAll / selector parts): wing flaps, blink, spin,
  // drip, head-nod sub-groups, pop-loop note bursts, and the orphanPopLoop star
  // cycle. Each is driven by idleForElement(id,state,t,amp), which returns a FULL
  // ElementIdle transform applied via ElementIdleMod to that element's view.
  // Ported 1:1 from the JS IdleAnimator's per-element style writes. Because the
  // source SVG uses transform-box: view-box, every px origin (and "50%") resolves
  // in canvas/view-box coords, so origins bake to UnitPoint(px / canvasSize).
  function emitElementIdle(opts, states, parsed) {
    const cw = opts.viewBox.width, ch = opts.viewBox.height;
    const vcx = cw / 2, vcy = ch / 2;

    const centerOf = (id, sn) => {
      if (parsed[id] && parsed[id][sn] && parsed[id][sn].length) {
        const b = bboxOfSegments(parsed[id][sn]);
        return [b.x + b.width / 2, b.y + b.height / 2];
      }
      const o = (opts.orphansByState[sn] || []).find(o => o.id === id);
      if (o && o.segments && o.segments.length) {
        const b = bboxOfSegments(o.segments);
        return [b.x + b.width / 2, b.y + b.height / 2];
      }
      return [vcx, vcy];
    };
    // Map a selector token to the SAME id used at the render call sites:
    //   #path-Foo        → "Foo"                 (raw shared id)
    //   #orphan-Bar-sn   → safeId("sn_Bar")      (matches the orphan's o.id)
    const stripId = (tok, sn) => {
      tok = tok.trim();
      if (tok.startsWith('#path-')) return tok.slice(6);
      if (tok.startsWith('#orphan-')) {
        let r = tok.slice(8);
        const suf = '-' + sn;
        if (r.endsWith(suf)) r = r.slice(0, r.length - suf.length);
        return safeId(`${sn}_${r}`);
      }
      if (tok.startsWith('#')) return tok.slice(1);
      return tok;
    };
    const resolveSel = (p, sn) => {
      const sel = p.selectorAll || p.selector || '';
      return sel.split(',').map(s => stripId(s, sn)).filter(Boolean);
    };
    const parseOrigin = (s) => {
      if (!s) return [vcx, vcy];
      const toks = String(s).trim().split(/\s+/);
      const conv = (tok, full) => tok.endsWith('%') ? parseFloat(tok) / 100 * full : parseFloat(tok);
      return [conv(toks[0], cw), conv(toks[1] != null ? toks[1] : toks[0], ch)];
    };
    const cgPoint = (xy) => `CGPoint(x: ${num(xy[0])}, y: ${num(xy[1])})`;
    const strArr = (arr) => '[' + arr.map(s => `"${s}"`).join(', ') + ']';

    // Static helpers (emitted once).
    const helpers = [
      `// MARK: - Per-element idle`,
      ``,
      `// A composed idle transform for ONE element (shared path or orphan). Mirrors`,
      `// the JS engine's per-element style.transform / style.opacity writes: an`,
      `// offset, a rotation about an anchor, a scale about an anchor, an appended`,
      `// vertical blink squish, and an optional opacity (when the part owns it).`,
      `struct ElementIdle {`,
      `    var offset: CGSize = .zero`,
      `    var preRotOffset: CGSize = .zero     // translate applied BEFORE the rotation (so it rotates with it)`,
      `    var rotationDeg: Double = 0`,
      `    var rotAnchor: UnitPoint = .center`,
      `    var scaleX: Double = 1`,
      `    var scaleY: Double = 1`,
      `    var scaleAnchor: UnitPoint = .center`,
      `    var blinkScaleY: Double = 1`,
      `    var blinkAnchor: UnitPoint = .center`,
      `    var opacity: Double = 1`,
      `    var setsOpacity: Bool = false`,
      `}`,
      ``,
      `// easeOutBack overshoot — matches the JS engine's easeFns.easeOutBack.`,
      `private func easeOutBack(_ t: Double) -> Double {`,
      `    let c1 = 1.70158, c3 = 1.70158 + 1`,
      `    return 1 + c3 * pow(t - 1, 3) + c1 * pow(t - 1, 2)`,
      `}`,
      ``,
      `// Applies the composed ElementIdle. Modifier order matches the CSS transform`,
      `// list the engine builds: blink squish is innermost (applied first in`,
      `// element-local space), then base scale/rotation, then translate; opacity`,
      `// (drip / pop-loop / star cycle) multiplies the element's own opacity.`,
      `struct ElementIdleMod: ViewModifier {`,
      `    let e: ElementIdle`,
      `    func body(content: Content) -> some View {`,
      `        content`,
      `            .scaleEffect(x: 1, y: e.blinkScaleY, anchor: e.blinkAnchor)`,
      `            .scaleEffect(x: e.scaleX, y: e.scaleY, anchor: e.scaleAnchor)`,
      `            .offset(e.preRotOffset)   // BEFORE rotation → rotates with it (matches CSS "rotate() translate()")`,
      `            .rotationEffect(.degrees(e.rotationDeg), anchor: e.rotAnchor)`,
      `            .offset(e.offset)`,
      `            .opacity(e.setsOpacity ? e.opacity : 1)`,
      `    }`,
      `}`,
      ``,
      `// --- per-kind contributions (ported from the JS IdleAnimator) ---`,
      ``,
      `private func applySwayEl(_ e: inout ElementIdle, amplitude: Double, duration: Double, t: Double, amp: Double) {`,
      `    e.rotationDeg += amplitude * amp * sin(t * 2 * .pi / duration)`,
      `    e.rotAnchor = UnitPoint(x: 0.5, y: 1.0)   // bottom-center`,
      `}`,
      ``,
      `private func applyNod(_ e: inout ElementIdle, amplitude: Double, duration: Double, t: Double, amp: Double) {`,
      `    e.offset.height += -amplitude * amp * (0.5 - 0.5 * cos(t * 2 * .pi / duration))`,
      `}`,
      ``,
      `private func rotPointGate(t: Double, gateCycle: Double, from: Double, to: Double, fade: Double) -> Double {`,
      `    let g = (t.truncatingRemainder(dividingBy: gateCycle)) / gateCycle`,
      `    if g < from || g > to { return 0 }`,
      `    if g < from + fade { return easeInOutSine((g - from) / fade) }`,
      `    if g > to - fade { return easeInOutSine((to - g) / fade) }`,
      `    return 1`,
      `}`,
      ``,
      `private func applyRotPoint(_ e: inout ElementIdle, pivotX: Double, pivotY: Double, amplitude: Double, duration: Double, phase: Double, bias: Double, liftUndo: Double, counterSwayAngle: Double, gateAmp: Double, t: Double, amp: Double, canvasW: Double, canvasH: Double) {`,
      `    // bias: constant rotation offset (e.g. resting a wing down / flapping back`,
      `    // up); liftUndo: amp-scaled downward translate that cancels a baked vertical`,
      `    // lift so the flap lands at the un-lifted position at full amplitude.`,
      `    let flap = (amplitude * gateAmp * sin(t * 2 * .pi / duration + phase) + bias) * amp`,
      `    e.rotationDeg += (flap - counterSwayAngle)`,
      `    e.rotAnchor = UnitPoint(x: pivotX / canvasW, y: pivotY / canvasH)`,
      `    // PRE-rotation offset: the JS engine applies liftUndo as \`translate()\` INSIDE`,
      `    // \`rotate()\`, so the baked lift cancels cleanly. Applying it after the rotation`,
      `    // (a plain .offset) would leave the wing displaced sideways by ~lift·sin(angle).`,
      `    e.preRotOffset.height += liftUndo * amp`,
      `}`,
      ``,
      `private func applyBlink(_ e: inout ElementIdle, center: CGPoint, period: Double, blinkDur: Double, minScale: Double, t: Double, amp: Double, canvasW: Double, canvasH: Double) {`,
      `    let ph = t.truncatingRemainder(dividingBy: period)`,
      `    var sy = 1.0`,
      `    if ph > period - blinkDur {`,
      `        let u = (ph - (period - blinkDur)) / blinkDur`,
      `        sy = 1 - (1 - minScale) * sin(u * .pi)`,
      `    }`,
      `    sy = 1 - (1 - sy) * amp`,
      `    e.blinkScaleY *= sy`,
      `    e.blinkAnchor = UnitPoint(x: center.x / canvasW, y: center.y / canvasH)`,
      `}`,
      ``,
      `private func applySpin(_ e: inout ElementIdle, index: Int, center: CGPoint, duration: Double, direction: Double, stagger: Double, alternate: Bool, t: Double, canvasW: Double, canvasH: Double) {`,
      `    let edir = (alternate && index % 2 == 1) ? -direction : direction`,
      `    let angle = (edir * ((t + Double(index) * stagger) / duration) * 360).truncatingRemainder(dividingBy: 360)`,
      `    e.rotationDeg += angle`,
      `    e.rotAnchor = UnitPoint(x: center.x / canvasW, y: center.y / canvasH)`,
      `}`,
      ``,
      `private func applyDrip(_ e: inout ElementIdle, originX: Double, originY: Double, riseMs: Double, holdMs: Double, fallMs: Double, restMs: Double, fallDist: Double, riseScale: Double, t: Double, amp: Double, canvasW: Double, canvasH: Double) {`,
      `    let cycleMs = riseMs + holdMs + fallMs + restMs`,
      `    let ph = (t * 1000).truncatingRemainder(dividingBy: cycleMs)`,
      `    var opacity = 0.0, ty = 0.0, scale = riseScale`,
      `    if ph < riseMs {`,
      `        let eased = easeInOutSine(ph / riseMs)`,
      `        opacity = eased; ty = 0; scale = riseScale + (1 - riseScale) * eased`,
      `    } else if ph < riseMs + holdMs {`,
      `        opacity = 1; ty = 0; scale = 1`,
      `    } else if ph < riseMs + holdMs + fallMs {`,
      `        let eased = easeInOutSine((ph - riseMs - holdMs) / fallMs)`,
      `        opacity = 1 - eased; ty = fallDist * eased; scale = 1`,
      `    } else {`,
      `        opacity = 0; ty = 0; scale = riseScale`,
      `    }`,
      `    e.offset.height += ty`,
      `    e.scaleX *= scale; e.scaleY *= scale`,
      `    e.scaleAnchor = UnitPoint(x: originX / canvasW, y: originY / canvasH)`,
      `    e.opacity *= opacity * amp; e.setsOpacity = true`,
      `}`,
      ``,
      `private func applyPopLoop(_ e: inout ElementIdle, phaseOffset: Double, cycle: Double, visFrac: Double, fadeFrac: Double, sFrom: Double, sTo: Double, rFrom: Double, rTo: Double, txFrom: Double, tyFrom: Double, txTo: Double, tyTo: Double, originX: Double, originY: Double, t: Double, amp: Double, canvasW: Double, canvasH: Double) {`,
      `    var phase = (t / cycle + phaseOffset).truncatingRemainder(dividingBy: 1)`,
      `    if phase < 0 { phase += 1 }`,
      `    var opacity = 0.0, scale = sFrom, rot = rFrom, tx = txFrom, ty = tyFrom`,
      `    let visStart = fadeFrac, visEnd = fadeFrac + visFrac, fadeOutEnd = fadeFrac + visFrac + fadeFrac`,
      `    if phase < visStart {`,
      `        let u = phase / fadeFrac`,
      `        opacity = u; scale = sFrom + (sTo - sFrom) * easeOutBack(u)`,
      `        rot = rFrom; tx = txFrom; ty = tyFrom`,
      `    } else if phase < visEnd {`,
      `        let u = (phase - visStart) / visFrac`,
      `        opacity = 1; scale = sTo`,
      `        rot = rFrom + (rTo - rFrom) * u`,
      `        tx = txFrom + (txTo - txFrom) * u`,
      `        ty = tyFrom + (tyTo - tyFrom) * u`,
      `    } else if phase < fadeOutEnd {`,
      `        let u = (phase - visEnd) / fadeFrac`,
      `        opacity = 1 - u; scale = sTo - (sTo - sFrom) * u`,
      `        rot = rTo; tx = txTo; ty = tyTo`,
      `    }`,
      `    e.offset.width += tx; e.offset.height += ty`,
      `    e.scaleX *= scale; e.scaleY *= scale`,
      `    e.rotationDeg += rot`,
      `    let a = UnitPoint(x: originX / canvasW, y: originY / canvasH)`,
      `    e.scaleAnchor = a; e.rotAnchor = a`,
      `    e.opacity *= opacity * amp; e.setsOpacity = true`,
      `}`,
      ``,
      `// Looping star burst (state-level orphanPopLoop): each star pops in (back-out`,
      `// overshoot, staggered), holds, then drifts outward along its radial + shrinks`,
      `// while fading, then rests — all derived as one continuous phase of t.`,
      `private func applyOrphanPopLoop(_ e: inout ElementIdle, index: Int, count: Int, center: CGPoint, radial: CGPoint, popDur: Double, stagger: Double, holdMs: Double, fadeMs: Double, restMs: Double, travel: Double, endScale: Double, t: Double, canvasW: Double, canvasH: Double) {`,
      `    let appearTotal = popDur + Double(count) * stagger`,
      `    let exitTotal = fadeMs + Double(count) * stagger`,
      `    let period = appearTotal + holdMs + exitTotal + restMs`,
      `    let ph = (t * 1000).truncatingRemainder(dividingBy: period)`,
      `    let aStart = Double(index) * stagger, aEnd = aStart + popDur`,
      `    let dStart = appearTotal + holdMs + Double(index) * stagger, dEnd = dStart + fadeMs`,
      `    var opacity = 0.0, scale = 1.0, tx = 0.0, ty = 0.0`,
      `    var anchor = UnitPoint(x: 0.5, y: 0.5)   // "50%" = view-box center during appear/hold`,
      `    if ph >= aStart && ph < aEnd {`,
      `        let u = (ph - aStart) / popDur`,
      `        opacity = min(1.0, u * 1.6)`,
      `        scale = 0.3 + 0.7 * easeOutBack(u)`,
      `    } else if ph >= aEnd && ph < dStart {`,
      `        opacity = 1; scale = 1`,
      `    } else if ph >= dStart && ph < dEnd {`,
      `        let m = easeInOutSine((ph - dStart) / fadeMs)`,
      `        tx = radial.x * travel * m; ty = radial.y * travel * m`,
      `        scale = 1 + (endScale - 1) * m`,
      `        opacity = 1 - m`,
      `        anchor = UnitPoint(x: center.x / canvasW, y: center.y / canvasH)`,
      `    }`,
      `    e.offset.width += tx; e.offset.height += ty`,
      `    e.scaleX *= scale; e.scaleY *= scale`,
      `    e.scaleAnchor = anchor`,
      `    e.opacity *= opacity; e.setsOpacity = true`,
      `}`,
      ``,
    ];

    // Generated per-state dispatch. Collect the switch cases and track whether
    // ANY state contributes a per-element block — if none do, we emit a trivial
    // body so `e`/`amp` don't trip "never mutated / never used" warnings
    // (characters whose idle is entirely whole-body / root).
    const body = [];
    let anyPerElement = false;
    for (const sn of opts.stateNames) {
      const safe = safeId(sn);
      const allParts = idleConfigToParts(states[sn].idle);
      const perEl = allParts.filter(p => p.selectorAll || p.selector);
      const popLoop = states[sn].orphanPopLoop;
      body.push(`    case .${safe}:`);
      if (perEl.length === 0 && !popLoop) {
        body.push(`        break`);
        continue;
      }
      anyPerElement = true;
      const usesCounter = perEl.some(p => p.counterSway);
      const baseSway = allParts.find(p => p.kind === 'sway' && !p.selectorAll && !p.selector);
      if (usesCounter) {
        body.push(baseSway
          ? `        let baseSway = ${num(baseSway.amplitude != null ? baseSway.amplitude : 2)} * amp * sin(t * 2 * .pi / ${num(baseSway.duration || 1.5)})`
          : `        let baseSway = 0.0`);
      }
      for (const p of perEl) {
        const ids = resolveSel(p, sn);
        if (ids.length === 0) continue;
        if (p.kind === 'sway') {
          body.push(`        if ${strArr(ids)}.contains(id) {`);
          body.push(`            applySwayEl(&e, amplitude: ${num(p.amplitude != null ? p.amplitude : 2)}, duration: ${num(p.duration || 1.5)}, t: t, amp: amp)`);
          body.push(`        }`);
        } else if (p.kind === 'nod') {
          body.push(`        if ${strArr(ids)}.contains(id) {`);
          body.push(`            applyNod(&e, amplitude: ${num(p.amplitude != null ? p.amplitude : 3.5)}, duration: ${num(p.duration || 1.3)}, t: t, amp: amp)`);
          body.push(`        }`);
        } else if (p.kind === 'rotate-around-point') {
          const pv = p.pivot || [0, 0];
          const counter = p.counterSway ? 'baseSway' : '0';
          body.push(`        if ${strArr(ids)}.contains(id) {`);
          let gate = '1';
          if (p.gateCycle != null && p.gateRange) {
            body.push(`            let gateAmp = rotPointGate(t: t, gateCycle: ${num(p.gateCycle)}, from: ${num(p.gateRange[0])}, to: ${num(p.gateRange[1])}, fade: ${num(p.gateFade != null ? p.gateFade : 0.05)})`);
            gate = 'gateAmp';
          }
          body.push(`            applyRotPoint(&e, pivotX: ${num(pv[0])}, pivotY: ${num(pv[1])}, amplitude: ${num(p.amplitude != null ? p.amplitude : 8)}, duration: ${num(p.duration || 1.0)}, phase: ${num(p.phase || 0)}, bias: ${num(p.bias || 0)}, liftUndo: ${num(p.liftUndo || 0)}, counterSwayAngle: ${counter}, gateAmp: ${gate}, t: t, amp: amp, canvasW: ${num(cw)}, canvasH: ${num(ch)})`);
          body.push(`        }`);
        } else if (p.kind === 'blink') {
          const centers = ids.map(id => centerOf(id, sn));
          // Blink is suppressed while an eye-driving transient (talk / look-around) runs.
          body.push(`        if !blinkSuppressed, let mi = ${strArr(ids)}.firstIndex(of: id) {`);
          body.push(`            let centers: [CGPoint] = [${centers.map(cgPoint).join(', ')}]`);
          body.push(`            applyBlink(&e, center: centers[mi], period: ${num(p.period || 3.5)}, blinkDur: ${num(p.blinkDuration || 0.16)}, minScale: ${num(p.minScale != null ? p.minScale : 0.1)}, t: t, amp: amp, canvasW: ${num(cw)}, canvasH: ${num(ch)})`);
          body.push(`        }`);
        } else if (p.kind === 'spin') {
          const centers = ids.map(id => centerOf(id, sn));
          body.push(`        if let mi = ${strArr(ids)}.firstIndex(of: id) {`);
          body.push(`            let centers: [CGPoint] = [${centers.map(cgPoint).join(', ')}]`);
          body.push(`            applySpin(&e, index: mi, center: centers[mi], duration: ${num(p.duration || 5)}, direction: ${num(p.direction || 1)}, stagger: ${num(p.stagger || 0)}, alternate: ${p.alternate ? 'true' : 'false'}, t: t, canvasW: ${num(cw)}, canvasH: ${num(ch)})`);
          body.push(`        }`);
        } else if (p.kind === 'drip') {
          const o = parseOrigin(p.transformOrigin);
          body.push(`        if ${strArr(ids)}.contains(id) {`);
          body.push(`            applyDrip(&e, originX: ${num(o[0])}, originY: ${num(o[1])}, riseMs: ${num(p.riseMs != null ? p.riseMs : 350)}, holdMs: ${num(p.holdMs != null ? p.holdMs : 400)}, fallMs: ${num(p.fallMs != null ? p.fallMs : 1000)}, restMs: ${num(p.restMs != null ? p.restMs : 500)}, fallDist: ${num(p.fallDistance != null ? p.fallDistance : 10)}, riseScale: ${num(p.riseScale != null ? p.riseScale : 0.6)}, t: t, amp: amp, canvasW: ${num(cw)}, canvasH: ${num(ch)})`);
          body.push(`        }`);
        } else if (p.kind === 'pop-loop') {
          const count = ids.length;
          const sR = p.scaleRange || [0.3, 1.0];
          const rR = p.rotateRange || [0, 0];
          const tRr = p.translateRange || [[0, 0], [0, 0]];
          const origins = ids.map(id => p.originSelf ? centerOf(id, sn) : parseOrigin(p.transformOrigin));
          body.push(`        if let mi = ${strArr(ids)}.firstIndex(of: id) {`);
          body.push(`            let origins: [CGPoint] = [${origins.map(cgPoint).join(', ')}]`);
          body.push(`            let o = origins[mi]`);
          body.push(`            applyPopLoop(&e, phaseOffset: Double(mi) / Double(${count}), cycle: ${num(p.cycleDuration || 3.0)}, visFrac: ${num(p.visibilityFraction != null ? p.visibilityFraction : 0.55)}, fadeFrac: ${num(p.fadeFraction != null ? p.fadeFraction : 0.15)}, sFrom: ${num(sR[0])}, sTo: ${num(sR[1])}, rFrom: ${num(rR[0])}, rTo: ${num(rR[1])}, txFrom: ${num(tRr[0][0])}, tyFrom: ${num(tRr[0][1])}, txTo: ${num(tRr[1][0])}, tyTo: ${num(tRr[1][1])}, originX: o.x, originY: o.y, t: t, amp: amp, canvasW: ${num(cw)}, canvasH: ${num(ch)})`);
          body.push(`        }`);
        }
      }
      if (popLoop) {
        // Qualify to the orphan render id (safeId("state_baseId")) so membership
        // and centers match the call site's idleForElement("state_baseId", ...).
        const ids = (popLoop.ids || []).map(bid => safeId(`${sn}_${bid}`));
        const centers = ids.map(id => centerOf(id, sn));
        const radials = centers.map(c => [c[0] - vcx, c[1] - vcy]);
        body.push(`        if let mi = ${strArr(ids)}.firstIndex(of: id) {`);
        body.push(`            let centers: [CGPoint] = [${centers.map(cgPoint).join(', ')}]`);
        body.push(`            let radials: [CGPoint] = [${radials.map(cgPoint).join(', ')}]`);
        body.push(`            applyOrphanPopLoop(&e, index: mi, count: ${ids.length}, center: centers[mi], radial: radials[mi], popDur: ${num(popLoop.popDuration || 360)}, stagger: ${num(popLoop.stagger || 70)}, holdMs: ${num(popLoop.holdMs || 900)}, fadeMs: ${num(popLoop.fadeMs || 300)}, restMs: ${num(popLoop.restMs || 450)}, travel: ${num(popLoop.travel != null ? popLoop.travel : 0.55)}, endScale: ${num(popLoop.endScale != null ? popLoop.endScale : 0.4)}, t: t, canvasW: ${num(cw)}, canvasH: ${num(ch)})`);
        body.push(`        }`);
      }
    }

    const sig = `private func idleForElement(_ id: String, in state: ${opts.stateEnum}, t: Double, amplitude: Double, blinkSuppressed: Bool = false) -> ElementIdle {`;
    const dispatch = [
      `// Per-element idle dispatch: returns the composed ElementIdle for a given`,
      `// shared-path or orphan id in a state. Identity when nothing targets it.`,
    ];
    if (!anyPerElement) {
      dispatch.push(sig);
      dispatch.push(`    return ElementIdle()   // this character's idle is entirely whole-body`);
      dispatch.push(`}`);
      dispatch.push(``);
    } else {
      dispatch.push(sig);
      dispatch.push(`    var e = ElementIdle()`);
      dispatch.push(`    let amp = amplitude`);
      dispatch.push(`    switch state {`);
      dispatch.push(...body);
      dispatch.push(`    }`);
      dispatch.push(`    return e`);
      dispatch.push(`}`);
      dispatch.push(``);
    }

    return helpers.concat(dispatch).join('\n');
  }

  // ---------------------------------------------------------------------------
  // Overlays (window.OVERLAYS_DATA): one-shot decorations (swirls/tear/notes/
  // stars) + eye transients (talk / look-around). Ported 1:1 from the JS preview
  // (playEmotionOverlay + IdleAnimator.playTransient). Emitted as:
  //   - a public <Prefix>Overlay enum + <Prefix>Controller ObservableObject so
  //     states AND overlays are callable from code;
  //   - each overlay playable once OR looping every N seconds (loopEvery:);
  //   - decoration shapes (with their glow filters) rendered hidden, driven by a
  //     pure time function of the controller's play-start Date (no timers);
  //   - talk / look-around as eye/mouth transient transforms composed over idle.
  // ---------------------------------------------------------------------------

  // Normalize OVERLAYS_DATA into export-ready descriptors (parsed child geometry,
  // resolved fills/filters, per-child radial + spin data, per-state face centers).
  function buildOverlayInfo(opts, states, parsed) {
    const ov = opts.overlays;
    if (!ov) return null;
    // Every section is optional: a states file may declare decoration artwork
    // (`emotions`), the talk / lookAround eye transients, `gestures` (named
    // play-once face transients that need no artwork), or any mix of them.
    const emotionsSrc = Array.isArray(ov.emotions) ? ov.emotions : [];
    const gesturesSrc = Array.isArray(ov.gestures) ? ov.gestures : [];
    if (!emotionsSrc.length && !ov.talk && !ov.lookAround && !gesturesSrc.length) return null;
    const cw = opts.viewBox.width, ch = opts.viewBox.height;

    // Gradients + filters may be referenced from overlay defs OR any state's defs.
    const gradientMap = {};
    for (const sn of opts.stateNames) Object.assign(gradientMap, parseGradients(states[sn].defs || ''));
    Object.assign(gradientMap, parseGradients(ov.defs || ''));
    const filterMap = Object.assign({}, opts.filters, parseFilters(ov.defs || ''));

    const resolveFill = (fillRaw, segs) => {
      if (typeof fillRaw === 'string' && /^url\(/i.test(fillRaw)) {
        const g = gradientToSwift(fillRaw, gradientMap, bboxOfSegments(segs), cw, ch);
        return g ? { expr: g, kind: 'gradient' } : { expr: 'Color.gray.opacity(0.4)', kind: 'fallback' };
      }
      return { expr: hexToSwiftColor(fillRaw || '#999999'), kind: 'color' };
    };
    const resolveFilter = (fref) => {
      const fid = fref && (fref.match(/url\(#([^)]+)\)/) || [])[1];
      return (fid && filterMap[fid]) ? filterMap[fid] : null;
    };

    const emotions = emotionsSrc.map(em => {
      const motion = em.motion || {};
      const kind = motion.kind || 'drift';
      const center = motion.center || [149.5, 164.5];
      const ids = Object.keys(em.paths || {});
      const children = ids.map((id, i) => {
        const p = em.paths[id];
        const d = getDOf(p);
        let segs = parsePath(d);
        if (!segs) return null;
        if (p.transform) segs = bakeTransformIntoSegments(segs, p.transform);
        const bb = tightBBoxOfSegments(segs);
        const fill = resolveFill(p.fill, segs);
        const strokeRaw = p.stroke && p.stroke !== 'none' ? p.stroke : null;
        return {
          segs, fillExpr: fill.expr, fillKind: fill.kind,
          stroke: strokeRaw ? hexToSwiftColor(strokeRaw) : null,
          strokeWidth: p.strokeWidth != null ? parseFloat(p.strokeWidth) : 1,
          strokeOpacity: p.strokeOpacity != null ? parseFloat(p.strokeOpacity) : 1,
          maxOp: p.opacity != null ? parseFloat(p.opacity) : 1,
          filterDesc: resolveFilter(p.filter),
          cx: bb.cx, cy: bb.cy, ox: bb.cx - center[0], oy: bb.cy - center[1],
          dir: (motion.alternate && (i % 2 === 1)) ? -1 : 1,
          spins: !motion.spinIds || motion.spinIds.indexOf(id) !== -1,
        };
      }).filter(Boolean);

      const enterMs = em.enterMs || 340, holdMs = em.holdMs || 1400, exitMs = em.exitMs || 440;
      const cycleMs = (motion.cycleDuration || 2.2) * 1000, cycles = motion.cycles || 2;
      const sr = motion.scaleRange || [0.3, 1.0], rr = motion.rotateRange || [0, 0];
      const info = {
        name: em.name, kind, children,
        enterMs, holdMs, exitMs, totalMs: enterMs + holdMs + exitMs,
        stagger: em.stagger || 0,
        fromScale: em.fromScale != null ? em.fromScale : 0.3,
        cycleMs, cycles, popTotalMs: cycleMs * cycles,
        visFrac: motion.visibilityFraction != null ? motion.visibilityFraction : 0.2,
        fadeFrac: motion.fadeFraction != null ? motion.fadeFraction : 0.1,
        scaleFrom: sr[0], scaleTo: sr[1], rotFrom: rr[0], rotTo: rr[1],
        spinDuration: motion.duration || 6,
        wiggleDeg: motion.wiggleDeg || 7, wigglePeriod: motion.period || 1.1,
        travel: motion.travel != null ? motion.travel : 0.25,
        endScale: motion.endScale != null ? motion.endScale : 0.4,
        fallDist: motion.fallDist || 6,
        isPop: kind === 'poploop',
        track: null,
      };
      if (em.track || em.offset) {
        info.track = {
          selector: em.track ? (em.track.selector || '').replace(/^#path-/, '') : null,
          anchorX: em.track && em.track.anchor ? em.track.anchor[0] : 0,
          anchorY: em.track && em.track.anchor ? em.track.anchor[1] : 0,
          offX: em.offset ? em.offset[0] : 0,
          offY: em.offset ? em.offset[1] : 0,
        };
      }
      return info;
    });

    // FACE ids for talk / look-around / gestures (+ tear tracking); their centers
    // per state. The set is the UNION over every declared transient, since one
    // `overlayTransient` modifier is attached per face id and each transient then
    // picks out the ids it actually drives (a blink gesture only moves the eyes,
    // a gaze moves eyes + mouth/nose).
    const idsFromSel = (sel) => String(sel || '').split(',').map(s => s.trim().replace(/^#path-/, '')).filter(Boolean);
    const faceIds = [...new Set([
      ...idsFromSel(ov.talk && ov.talk.selectorAll),
      ...idsFromSel(ov.lookAround && ov.lookAround.selectorAll),
      ...gesturesSrc.reduce((acc, g) => acc.concat(idsFromSel(g.selectorAll || g.selector)), []),
    ])];
    const eyeIds = faceIds.filter(id => /eye/i.test(id));
    // Talk's targetEyeY / targetEyeH and the tear's tracking anchor are measured
    // against ONE reference eye — the first eye id, whatever it is called.
    const eyeGeoId = eyeIds[0] || 'eye1';
    const centersByState = {}, eye1ByState = {};
    for (const sn of opts.stateNames) {
      centersByState[sn] = {};
      for (const id of faceIds) {
        if (parsed[id] && parsed[id][sn]) {
          const bb = tightBBoxOfSegments(parsed[id][sn]);
          centersByState[sn][id] = [bb.cx, bb.cy];
        }
      }
      if (parsed[eyeGeoId] && parsed[eyeGeoId][sn]) {
        const bb = tightBBoxOfSegments(parsed[eyeGeoId][sn]);
        eye1ByState[sn] = { cx: bb.cx, cy: bb.cy, h: bb.height };
      }
    }

    // Play-once gestures. `look-around` reuses the gaze keyframes (a gesture with
    // dx = 0 collapses the left/right stops into one hold at the top — a plain
    // "look up"); anything else is a `blink` squish on the eyes. An empty
    // enabledStates means "playable from every state".
    const gestures = gesturesSrc.map(g => ({
      name: g.name,
      label: g.label || g.name,
      kind: g.kind === 'look-around' ? 'look-around' : 'blink',
      ids: idsFromSel(g.selectorAll || g.selector),
      durationMs: g.durationMs || (g.kind === 'look-around' ? 5000 : 400),
      enabledStates: (g.enabledStates || []).slice(),
      dx: g.dx != null ? g.dx : 5,
      dxLeft: g.dxLeft != null ? g.dxLeft : (g.dx != null ? g.dx : 5),
      dy: g.dy != null ? g.dy : 5,
      eyeOpen: g.eyeOpen != null ? g.eyeOpen : 1,
      blinks: g.blinks != null ? g.blinks : 1,
      minScale: g.minScale != null ? g.minScale : 0.1,
    }));

    return {
      emotions,
      gestures,
      talk: ov.talk ? {
        amplitude: ov.talk.amplitude != null ? ov.talk.amplitude : 2.4,
        cycles: ov.talk.cycles != null ? ov.talk.cycles : 4,
        durationMs: ov.talk.durationMs || 1500,
        targetEyeY: ov.talk.targetEyeY != null ? ov.talk.targetEyeY : null,
        targetEyeH: ov.talk.targetEyeH != null ? ov.talk.targetEyeH : null,
        lift: ov.talk.lift || 0,
        heightScale: ov.talk.heightScale != null ? ov.talk.heightScale : 1,
      } : null,
      look: ov.lookAround ? {
        dx: ov.lookAround.dx != null ? ov.lookAround.dx : 5,
        dxLeft: ov.lookAround.dxLeft != null ? ov.lookAround.dxLeft : (ov.lookAround.dx != null ? ov.lookAround.dx : 5),
        dy: ov.lookAround.dy != null ? ov.lookAround.dy : 5,
        eyeOpen: ov.lookAround.eyeOpen != null ? ov.lookAround.eyeOpen : 1,
        durationMs: ov.lookAround.durationMs || 5000,
        enabledStates: (ov.lookAround.enabledStates || []).slice(),
      } : null,
      faceIds, eyeIds, centersByState, eye1ByState,
    };
  }

  function emitOverlays(opts) {
    const oi = opts.overlayInfo;
    if (!oi) return '';
    const cw = opts.viewBox.width, ch = opts.viewBox.height;
    const OVR = opts.overlayEnum, GST = opts.gestureEnum, CTRL = opts.controllerName, ENUM = opts.stateEnum;
    const first = safeId(opts.stateNames[0]);
    const emos = oi.emotions;
    const gests = oi.gestures || [];
    const strSet = (arr) => '[' + arr.map(s => `"${s}"`).join(', ') + ']';
    const dblArr = (arr) => '[' + arr.map(num).join(', ') + ']';
    const boolArr = (arr) => '[' + arr.map(b => b ? 'true' : 'false').join(', ') + ']';
    const childFn = (name, i) => `ovChild_${safeId(name)}_${i}`;

    const L = [];
    L.push(`// MARK: - Overlays (callable one-shot decorations + eye transients)`);
    L.push(``);

    // Public overlay enum (decoration overlays only — talk / look-around are their
    // own controller methods, matching the JS playTalk / playLookAround API).
    // Omitted entirely when the character declares no decoration artwork.
    if (emos.length) {
      L.push(`public enum ${OVR}: String, CaseIterable {`);
      for (const e of emos) L.push(`    case ${safeId(e.name)} = "${e.name}"`);
      L.push(`}`);
      L.push(``);
    }
    // Public gesture enum — the play-once face transients (blink / gaze) that
    // need no artwork, mirroring the JS preview's "Play once" gesture buttons.
    if (gests.length) {
      L.push(`public enum ${GST}: String, CaseIterable {`);
      // Explicit raw values: playGesture keys `gesturePlays` by rawValue, and the
      // emitted transient looks the gesture up by its AUTHORED name — which may
      // contain characters (hyphens) that safeId strips from the case identifier.
      for (const g of gests) L.push(`    case ${safeId(g.name)} = "${g.name}"`);
      L.push(`}`);
      L.push(``);
    }
    L.push(`// One in-flight overlay play. loopEvery == nil → play once; otherwise the`);
    L.push(`// overlay's local clock wraps every loopEvery seconds (replays until stopped).`);
    L.push(`struct OverlayPlayback { var start: Date; var loopEvery: Double? }`);
    L.push(``);

    // Controller — the programmatic handle: switch states, fire overlays, talk, look.
    L.push(`// Observable controller: hold one (e.g. @StateObject), pass to ${opts.typeName}(controller:),`);
    L.push(`// then drive everything from code — no view surgery required.`);
    L.push(`//`);
    L.push(`//   @StateObject private var controller = ${CTRL}()`);
    L.push(`//   ${opts.typeName}(controller: controller)`);
    L.push(`//   controller.setState(.${first})            // switch looping behaviour state`);
    if (emos.length) {
      L.push(`//   controller.playOverlay(.${safeId(emos[0].name)})          // play once`);
      L.push(`//   controller.playOverlay(.${safeId(emos[emos.length - 1].name)}, loopEvery: 3)  // loop every 3s`);
    }
    if (gests.length) L.push(`//   controller.playGesture(.${safeId(gests[0].name)})         // one-shot face gesture`);
    if (oi.talk || oi.look) L.push(`//   ${[oi.talk ? 'controller.playTalk()' : null, oi.look ? 'controller.playLookAround()' : null].filter(Boolean).join('; ')}`);
    L.push(`public final class ${CTRL}: ObservableObject {`);
    L.push(`    @Published public var state: ${ENUM}`);
    L.push(`    @Published var plays: [String: OverlayPlayback] = [:]`);
    if (gests.length) L.push(`    @Published var gesturePlays: [String: OverlayPlayback] = [:]`);
    L.push(`    @Published var talkStart: Date? = nil`);
    L.push(`    @Published var lookStart: Date? = nil`);
    L.push(`    @Published var talkLoop: Double? = nil`);
    L.push(`    @Published var lookLoop: Double? = nil`);
    L.push(`    public init(state: ${ENUM} = .${first}) { self.state = state }`);
    L.push(`    /// Switch the looping behaviour state (morphs there).`);
    L.push(`    public func setState(_ s: ${ENUM}) { state = s }`);
    if (emos.length) {
      L.push(`    /// Play a decoration overlay once, or every \`loopEvery\` seconds until stopped.`);
      L.push(`    public func playOverlay(_ o: ${OVR}, loopEvery: TimeInterval? = nil) {`);
      L.push(`        plays[o.rawValue] = OverlayPlayback(start: Date(), loopEvery: loopEvery)`);
      L.push(`    }`);
      L.push(`    public func stopOverlay(_ o: ${OVR}) { plays[o.rawValue] = nil }`);
      L.push(`    public func stopAllOverlays() { plays.removeAll() }`);
    }
    if (gests.length) {
      L.push(`    /// Play a one-shot face gesture (blink / gaze) over the running idle, or`);
      L.push(`    /// repeat it every \`loopEvery\` seconds until stopped. A gesture authored`);
      L.push(`    /// with enabled states is simply ignored while in any other state.`);
      L.push(`    public func playGesture(_ g: ${GST}, loopEvery: TimeInterval? = nil) {`);
      L.push(`        gesturePlays[g.rawValue] = OverlayPlayback(start: Date(), loopEvery: loopEvery)`);
      L.push(`    }`);
      L.push(`    public func stopGesture(_ g: ${GST}) { gesturePlays[g.rawValue] = nil }`);
      L.push(`    public func stopAllGestures() { gesturePlays.removeAll() }`);
    }
    if (oi.talk) {
      L.push(`    /// "Talking" bob on the eyes + mouth, composed over the running idle. Plays`);
      L.push(`    /// once, or repeats every \`loopEvery\` seconds (call stopTalk to end a loop).`);
      L.push(`    public func playTalk(loopEvery: TimeInterval? = nil) { talkStart = Date(); talkLoop = loopEvery }`);
      L.push(`    public func stopTalk() { talkStart = nil; talkLoop = nil }`);
    }
    if (oi.look) {
      L.push(`    /// Look-around gaze (only visible from its enabled states). Plays once, or`);
      L.push(`    /// repeats every \`loopEvery\` seconds (call stopLookAround to end a loop).`);
      L.push(`    public func playLookAround(loopEvery: TimeInterval? = nil) { lookStart = Date(); lookLoop = loopEvery }`);
      L.push(`    public func stopLookAround() { lookStart = nil; lookLoop = nil }`);
    }
    L.push(`}`);
    L.push(``);

    // --- Decoration artwork. Skipped entirely for a gesture-only character. ---
    if (emos.length) {
    // --- Decoration child shapes (rendered hidden; driven by overlayElement) ---
    for (const em of emos) {
      em.children.forEach((c, i) => {
        const segs = c.segs.map(segmentToSwift).join(', ');
        const fMod = filterMod(c.filterDesc, '        ');
        L.push(`@ViewBuilder private func ${childFn(em.name, i)}() -> some View {`);
        if (c.stroke) {
          L.push(`    ${segPathExpr(opts, segs, true)}`);
          L.push(`        .stroke(${c.stroke}.opacity(${num(c.strokeOpacity)}), lineWidth: ${num(c.strokeWidth)})${fMod}`);
        } else if (c.fillKind === 'gradient') {
          L.push(`    ${c.fillExpr}`);
          L.push(`        .frame(width: ${num(cw)}, height: ${num(ch)})`);
          L.push(`        .mask(${segPathExpr(opts, segs, true)}.fill(Color.black))${fMod}`);
        } else {
          L.push(`    ${segPathExpr(opts, segs, true)}`);
          L.push(`        .fill(${c.fillExpr})${fMod}`);
        }
        L.push(`}`);
        L.push(``);
      });
    }

    // --- Motion helpers (ported from playEmotionOverlay.step) ---
    L.push(`// enter (pop-in) → hold (signature motion) → exit (fade + motion tail).`);
    L.push(`// Anchor (< 0 → child's own centre) is the scale/rotate origin in canvas coords.`);
    L.push(`private func overlayNonPop(_ e: inout ElementIdle, ms: Double, index: Int, stagger: Double, enterMs: Double, holdMs: Double, exitMs: Double, fromScale: Double, kind: String, spinDuration: Double, spins: Bool, dir: Double, wiggleDeg: Double, wigglePeriod: Double, travel: Double, endScale: Double, ox: Double, oy: Double, fallDist: Double, maxOp: Double, anchorX: Double, anchorY: Double, trackDx: Double, trackDy: Double, canvasW: Double, canvasH: Double) {`);
    L.push(`    let total = enterMs + holdMs + exitMs`);
    L.push(`    let lt = ms - Double(index) * stagger`);
    L.push(`    if lt < 0 || lt >= total { e.opacity = 0; e.setsOpacity = true; return }`);
    L.push(`    var op = 0.0, scale = 1.0, tx = 0.0, ty = 0.0, rot = 0.0`);
    L.push(`    if lt < enterMs {`);
    L.push(`        let u = lt / enterMs`);
    L.push(`        op = min(maxOp, u * 1.6 * maxOp)`);
    L.push(`        scale = fromScale + (1 - fromScale) * easeOutBack(u)`);
    L.push(`    } else {`);
    L.push(`        let inExit = lt > enterMs + holdMs`);
    L.push(`        let exitU = inExit ? (lt - enterMs - holdMs) / exitMs : 0`);
    L.push(`        op = inExit ? maxOp * (1 - exitU) : maxOp`);
    L.push(`        let mt = (lt - enterMs) / 1000`);
    L.push(`        switch kind {`);
    L.push(`        case "spin": if spins { rot = dir * mt * (360 / spinDuration) }`);
    L.push(`        case "wiggle": rot = wiggleDeg * sin(mt * 2 * .pi / wigglePeriod)`);
    L.push(`        case "drift": let m = easeInOutSine(exitU); tx = ox * travel * m; ty = oy * travel * m; scale = 1 + (endScale - 1) * m`);
    L.push(`        case "drip": ty = fallDist * easeInOutSine(exitU)`);
    L.push(`        default: break`);
    L.push(`        }`);
    L.push(`    }`);
    L.push(`    e.offset.width += tx + trackDx; e.offset.height += ty + trackDy`);
    L.push(`    e.scaleX *= scale; e.scaleY *= scale`);
    L.push(`    e.rotationDeg += rot`);
    L.push(`    let a = UnitPoint(x: anchorX / canvasW, y: anchorY / canvasH)  // caller resolves own-centre`);
    L.push(`    e.scaleAnchor = a; e.rotAnchor = a`);
    L.push(`    e.opacity *= op; e.setsOpacity = true`);
    L.push(`}`);
    L.push(``);
    L.push(`// pop-loop: each child appears one-by-one (phase-offset), pops about its own`);
    L.push(`// centre (easeOutBack), holds, fades — repeated for \`cycles\`, then a tail fade.`);
    L.push(`private func overlayPop(_ e: inout ElementIdle, ms: Double, index: Int, count: Int, cycleMs: Double, popTotalMs: Double, visFrac: Double, fadeFrac: Double, sFrom: Double, sTo: Double, rFrom: Double, rTo: Double, maxOp: Double, anchorX: Double, anchorY: Double, canvasW: Double, canvasH: Double) {`);
    L.push(`    if ms >= popTotalMs { e.opacity = 0; e.setsOpacity = true; return }`);
    L.push(`    let phaseOffset = count > 1 ? Double(index) / Double(count) : 0`);
    L.push(`    var phase = ((ms / cycleMs) + phaseOffset).truncatingRemainder(dividingBy: 1)`);
    L.push(`    if phase < 0 { phase += 1 }`);
    L.push(`    let visStart = fadeFrac, visEnd = fadeFrac + visFrac, fadeOutEnd = visEnd + fadeFrac`);
    L.push(`    var op = 0.0, scale = sFrom, rot = rFrom`);
    L.push(`    if phase < visStart { let u = phase / fadeFrac; op = u; scale = sFrom + (sTo - sFrom) * easeOutBack(u) }`);
    L.push(`    else if phase < visEnd { let u = (phase - visStart) / visFrac; op = 1; scale = sTo; rot = rFrom + (rTo - rFrom) * u }`);
    L.push(`    else if phase < fadeOutEnd { let u = (phase - visEnd) / fadeFrac; op = 1 - u; scale = sTo - (sTo - sFrom) * u; rot = rTo }`);
    L.push(`    let tail = 400.0`);
    L.push(`    if ms > popTotalMs - tail { op *= max(0, (popTotalMs - ms) / tail) }`);
    L.push(`    e.scaleX *= scale; e.scaleY *= scale; e.rotationDeg += rot`);
    L.push(`    let a = UnitPoint(x: anchorX / canvasW, y: anchorY / canvasH)`);
    L.push(`    e.scaleAnchor = a; e.rotAnchor = a`);
    L.push(`    e.opacity *= op * maxOp; e.setsOpacity = true`);
    L.push(`}`);
    L.push(``);

    // --- Per-child ElementIdle dispatch (arrays baked per overlay) ---
    L.push(`// Composed transform for one decoration child at local time \`ms\`. anchorX/Y < 0`);
    L.push(`// means "use the child's own centre"; the tear passes the live eye centre.`);
    L.push(`private func overlayElement(_ overlay: String, index: Int, ms: Double, trackDx: Double, trackDy: Double, anchorX: Double, anchorY: Double) -> ElementIdle {`);
    L.push(`    var e = ElementIdle()`);
    L.push(`    switch overlay {`);
    for (const em of emos) {
      const cs = em.children;
      L.push(`    case "${em.name}":`);
      L.push(`        let cx: [Double] = ${dblArr(cs.map(c => c.cx))}`);
      L.push(`        let cy: [Double] = ${dblArr(cs.map(c => c.cy))}`);
      const useOwn = `let ax = anchorX < 0 ? cx[index] : anchorX; let ay = anchorY < 0 ? cy[index] : anchorY`;
      if (em.isPop) {
        L.push(`        let maxOp: [Double] = ${dblArr(cs.map(c => c.maxOp))}`);
        L.push(`        ${useOwn}`);
        L.push(`        overlayPop(&e, ms: ms, index: index, count: ${cs.length}, cycleMs: ${num(em.cycleMs)}, popTotalMs: ${num(em.popTotalMs)}, visFrac: ${num(em.visFrac)}, fadeFrac: ${num(em.fadeFrac)}, sFrom: ${num(em.scaleFrom)}, sTo: ${num(em.scaleTo)}, rFrom: ${num(em.rotFrom)}, rTo: ${num(em.rotTo)}, maxOp: maxOp[index], anchorX: ax, anchorY: ay, canvasW: ${num(cw)}, canvasH: ${num(ch)})`);
      } else {
        L.push(`        let ox: [Double] = ${dblArr(cs.map(c => c.ox))}`);
        L.push(`        let oy: [Double] = ${dblArr(cs.map(c => c.oy))}`);
        L.push(`        let dir: [Double] = ${dblArr(cs.map(c => c.dir))}`);
        L.push(`        let spins: [Bool] = ${boolArr(cs.map(c => c.spins))}`);
        L.push(`        let maxOp: [Double] = ${dblArr(cs.map(c => c.maxOp))}`);
        L.push(`        ${useOwn}`);
        L.push(`        overlayNonPop(&e, ms: ms, index: index, stagger: ${num(em.stagger)}, enterMs: ${num(em.enterMs)}, holdMs: ${num(em.holdMs)}, exitMs: ${num(em.exitMs)}, fromScale: ${num(em.fromScale)}, kind: "${em.kind}", spinDuration: ${num(em.spinDuration)}, spins: spins[index], dir: dir[index], wiggleDeg: ${num(em.wiggleDeg)}, wigglePeriod: ${num(em.wigglePeriod)}, travel: ${num(em.travel)}, endScale: ${num(em.endScale)}, ox: ox[index], oy: oy[index], fallDist: ${num(em.fallDist)}, maxOp: maxOp[index], anchorX: ax, anchorY: ay, trackDx: trackDx, trackDy: trackDy, canvasW: ${num(cw)}, canvasH: ${num(ch)})`);
      }
    }
    L.push(`    default: break`);
    L.push(`    }`);
    L.push(`    return e`);
    L.push(`}`);
    L.push(``);

    } // end decoration artwork

    // --- Per-state face-element centre + eye1 geometry lookups ---
    L.push(`private func overlayFaceCenter(_ id: String, _ state: ${ENUM}) -> CGPoint {`);
    L.push(`    switch state {`);
    for (const sn of opts.stateNames) {
      const m = oi.centersByState[sn] || {};
      const cases = oi.faceIds.filter(id => m[id]).map(id => `case "${id}": return CGPoint(x: ${num(m[id][0])}, y: ${num(m[id][1])})`);
      L.push(`    case .${safeId(sn)}:`);
      L.push(`        switch id { ${cases.join('; ')}${cases.length ? '; ' : ''}default: return .zero }`);
    }
    L.push(`    }`);
    L.push(`}`);
    L.push(``);
    L.push(`private func overlayEye1Geo(_ state: ${ENUM}) -> (cx: Double, cy: Double, h: Double) {`);
    L.push(`    switch state {`);
    for (const sn of opts.stateNames) {
      const g = oi.eye1ByState[sn] || { cx: cw / 2, cy: ch / 2, h: 1 };
      L.push(`    case .${safeId(sn)}: return (${num(g.cx)}, ${num(g.cy)}, ${num(g.h)})`);
    }
    L.push(`    }`);
    L.push(`}`);
    L.push(``);

    if (emos.length) {
    // --- Per-overlay render groups + the aggregate overlay layer ---
    const trackEmos = emos.filter(e => e.track);
    for (const em of trackEmos) {
      // The tracked selector's live centre per state (defaults to eye1).
      L.push(`// Track offset for "${em.name}": ride the current pose's ${em.track.selector || 'anchor'}.`);
      L.push(`private func overlayTrack_${safeId(em.name)}(_ state: ${ENUM}) -> (dx: Double, dy: Double, ax: Double, ay: Double) {`);
      L.push(`    let g = overlayEye1Geo(state)`);
      L.push(`    return (g.cx - ${num(em.track.anchorX)} + ${num(em.track.offX)}, g.cy - ${num(em.track.anchorY)} + ${num(em.track.offY)}, g.cx, g.cy)`);
      L.push(`}`);
      L.push(``);
    }

    const frame = `.frame(width: ${num(cw)}, height: ${num(ch)}, alignment: .topLeading)`;
    for (const em of emos) {
      const win = em.isPop ? em.popTotalMs : em.totalMs;
      const tracked = !!em.track;
      const sig = tracked
        ? `now: Date, plays: [String: OverlayPlayback], state: ${ENUM}`
        : `now: Date, plays: [String: OverlayPlayback]`;
      L.push(`@ViewBuilder private func overlayGroup_${safeId(em.name)}(${sig}) -> some View {`);
      L.push(`    if let pb = plays["${em.name}"] {`);
      L.push(`        let raw = now.timeIntervalSince(pb.start)`);
      L.push(`        let ms = (pb.loopEvery.map { raw.truncatingRemainder(dividingBy: max($0, 0.001)) } ?? raw) * 1000`);
      L.push(`        if ms < ${num(win)} {`);
      if (tracked) L.push(`            let tk = overlayTrack_${safeId(em.name)}(state)`);
      L.push(`            ZStack {`);
      em.children.forEach((c, i) => {
        const args = tracked
          ? `index: ${i}, ms: ms, trackDx: tk.dx, trackDy: tk.dy, anchorX: tk.ax, anchorY: tk.ay`
          : `index: ${i}, ms: ms, trackDx: 0, trackDy: 0, anchorX: -1, anchorY: -1`;
        L.push(`                ${childFn(em.name, i)}()`);
        L.push(`                    ${frame}`);
        L.push(`                    .modifier(ElementIdleMod(e: overlayElement("${em.name}", ${args})))`);
      });
      L.push(`            }`);
      L.push(`        }`);
      L.push(`    }`);
      L.push(`}`);
      L.push(``);
    }

    L.push(`@ViewBuilder private func overlayLayer(now: Date, plays: [String: OverlayPlayback], state: ${ENUM}) -> some View {`);
    L.push(`    ZStack {`);
    for (const em of emos) {
      L.push(em.track
        ? `        overlayGroup_${safeId(em.name)}(now: now, plays: plays, state: state)`
        : `        overlayGroup_${safeId(em.name)}(now: now, plays: plays)`);
    }
    L.push(`    }`);
    L.push(`    .allowsHitTesting(false)`);
    L.push(`}`);
    L.push(``);

    } // end decoration render groups

    // --- Talk / look-around eye transient (composed over idle on face ids) ---
    // One gaze-keyframe function per gaze source, since each carries its own
    // dx / dxLeft / dy. A gesture with dx = 0 (look-up) collapses the left/right
    // stops into a single hold at the top.
    const gazeKf = (lk) => `[(0,0,0), (0.16,${num(-lk.dxLeft)},${num(-lk.dy)}), (0.30,${num(-lk.dxLeft)},${num(-lk.dy)}), (0.44,${num(lk.dx)},${num(-lk.dy)}), (0.58,${num(lk.dx)},${num(-lk.dy)}), (0.70,0,${num(-lk.dy)}), (0.82,0,${num(-lk.dy)}), (0.94,0,0), (1.0,0,0)]`;
    const emitGaze = (fnName, lk) => {
      L.push(`private func ${fnName}(_ u: Double) -> (Double, Double) {`);
      L.push(`    let kf: [(Double, Double, Double)] = ${gazeKf(lk)}`);
      L.push(`    for i in 1..<kf.count {`);
      L.push(`        if u <= kf[i].0 {`);
      L.push(`            let span = (kf[i].0 - kf[i-1].0) == 0 ? 1 : (kf[i].0 - kf[i-1].0)`);
      L.push(`            let ee = easeInOutSine(min(1, max(0, (u - kf[i-1].0) / span)))`);
      L.push(`            return (kf[i-1].1 + (kf[i].1 - kf[i-1].1) * ee, kf[i-1].2 + (kf[i].2 - kf[i-1].2) * ee)`);
      L.push(`        }`);
      L.push(`    }`);
      L.push(`    return (0, 0)`);
      L.push(`}`);
      L.push(``);
    };
    const gazeFn = (g) => `overlayGaze_${safeId(g.name)}`;
    for (const g of gests) {
      if (g.kind !== 'look-around') continue;
      L.push(`// "${g.name}" gaze keyframes.`);
      emitGaze(gazeFn(g), g);
    }
    if (oi.look) {
      const lk = oi.look;
      L.push(`// look-around gaze keyframes (TL → TR → top-centre → back), eased per segment.`);
      L.push(`private func overlayLookGaze(_ u: Double) -> (Double, Double) {`);
      L.push(`    let kf: [(Double, Double, Double)] = [(0,0,0), (0.16,${num(-lk.dxLeft)},${num(-lk.dy)}), (0.30,${num(-lk.dxLeft)},${num(-lk.dy)}), (0.44,${num(lk.dx)},${num(-lk.dy)}), (0.58,${num(lk.dx)},${num(-lk.dy)}), (0.70,0,${num(-lk.dy)}), (0.82,0,${num(-lk.dy)}), (0.94,0,0), (1.0,0,0)]`);
      L.push(`    for i in 1..<kf.count {`);
      L.push(`        if u <= kf[i].0 {`);
      L.push(`            let span = (kf[i].0 - kf[i-1].0) == 0 ? 1 : (kf[i].0 - kf[i-1].0)`);
      L.push(`            let ee = easeInOutSine(min(1, max(0, (u - kf[i-1].0) / span)))`);
      L.push(`            return (kf[i-1].1 + (kf[i].1 - kf[i-1].1) * ee, kf[i-1].2 + (kf[i].2 - kf[i-1].2) * ee)`);
      L.push(`        }`);
      L.push(`    }`);
      L.push(`    return (0, 0)`);
      L.push(`}`);
      L.push(``);
    }
    L.push(`// Talk / look-around transient for a FACE id, composed on top of its idle.`);
    L.push(`// amp = the live idle amplitude (so it eases with morphs, like the JS engine).`);
    L.push(`private func overlayTransient(_ id: String, now: Date, talkStart: Date?, lookStart: Date?, talkLoop: Double?, lookLoop: Double?, gestures: [String: OverlayPlayback], state: ${ENUM}, amp: Double) -> ElementIdle {`);
    L.push(`    var e = ElementIdle()`);
    L.push(`    let eyes: [String] = ${strSet(oi.eyeIds)}`);
    if (oi.talk) {
      const tk = oi.talk;
      L.push(`    if let ts = talkStart {`);
      L.push(`        let rawS = now.timeIntervalSince(ts)`);
      L.push(`        let ms = (talkLoop.map { rawS.truncatingRemainder(dividingBy: max($0, 0.001)) } ?? rawS) * 1000`);
      L.push(`        if ms >= 0 && ms < ${num(tk.durationMs)} {`);
      L.push(`            let u = min(1, ms / ${num(tk.durationMs)})`);
      L.push(`            let ramp = 0.18`);
      L.push(`            var env = 1.0`);
      L.push(`            if u < ramp { env = u / ramp } else if u > 1 - ramp { env = (1 - u) / ramp }`);
      L.push(`            let ee = env * amp`);
      L.push(`            let bob = -${num(tk.amplitude)} * ee * sin(u * ${num(tk.cycles)} * 2 * .pi)`);
      L.push(`            let g = overlayEye1Geo(state)`);
      L.push(tk.targetEyeY != null
        ? `            let lift = min(0, ${num(tk.targetEyeY)} - g.cy) * ee`
        : `            let lift = ${num(tk.lift)} * ee`);
      L.push(tk.targetEyeH != null
        ? `            let hs = 1 + ((g.h > 0 ? ${num(tk.targetEyeH)} / g.h : 1) - 1) * ee`
        : `            let hs = 1 + (${num(tk.heightScale)} - 1) * ee`);
      L.push(`            e.offset.height += lift + bob`);
      L.push(`            if eyes.contains(id) {`);
      L.push(`                e.scaleY *= hs`);
      L.push(`                e.scaleAnchor = UnitPoint(x: 0, y: overlayFaceCenter(id, state).y / ${num(ch)})`);
      L.push(`            }`);
      L.push(`        }`);
      L.push(`    }`);
    }
    if (oi.look) {
      const lk = oi.look;
      L.push(`    if let ls = lookStart, ${strSet(lk.enabledStates.map(safeId))}.contains(state.rawValue) {`);
      L.push(`        let rawS = now.timeIntervalSince(ls)`);
      L.push(`        let ms = (lookLoop.map { rawS.truncatingRemainder(dividingBy: max($0, 0.001)) } ?? rawS) * 1000`);
      L.push(`        if ms >= 0 && ms < ${num(lk.durationMs)} {`);
      L.push(`            let u = min(1, ms / ${num(lk.durationMs)})`);
      L.push(`            let g = overlayLookGaze(u)`);
      L.push(`            let ox = g.0 * amp, oy = g.1 * amp`);
      L.push(`            let up = ${num(lk.dy)} > 0 ? min(1, -oy / ${num(lk.dy)}) : 0`);
      L.push(`            e.offset.width += ox; e.offset.height += oy`);
      L.push(`            if eyes.contains(id) {`);
      L.push(`                e.scaleY *= 1 + (${num(lk.eyeOpen)} - 1) * up`);
      L.push(`                e.scaleAnchor = UnitPoint(x: 0, y: overlayFaceCenter(id, state).y / ${num(ch)})`);
      L.push(`            }`);
      L.push(`        }`);
      L.push(`    }`);
    }
    for (const g of gests) {
      const gate = g.enabledStates.length
        ? `, ${strSet(g.enabledStates.map(safeId))}.contains(state.rawValue)`
        : '';
      L.push(`    // gesture "${g.name}" (${g.kind})`);
      L.push(`    if let pb = gestures["${g.name}"]${gate}, ${strSet(g.ids)}.contains(id) {`);
      L.push(`        let raw = now.timeIntervalSince(pb.start)`);
      L.push(`        let ms = (pb.loopEvery.map { raw.truncatingRemainder(dividingBy: max($0, 0.001)) } ?? raw) * 1000`);
      L.push(`        if ms >= 0 && ms < ${num(g.durationMs)} {`);
      L.push(`            let u = min(1, ms / ${num(g.durationMs)})`);
      if (g.kind === 'look-around') {
        L.push(`            let gz = ${gazeFn(g)}(u)`);
        L.push(`            let ox = gz.0 * amp, oy = gz.1 * amp`);
        L.push(`            let up = ${num(g.dy)} > 0 ? min(1, -oy / ${num(g.dy)}) : 0`);
        L.push(`            e.offset.width += ox; e.offset.height += oy`);
        L.push(`            if eyes.contains(id) {`);
        L.push(`                e.scaleY *= 1 + (${num(g.eyeOpen)} - 1) * up`);
        L.push(`                e.scaleAnchor = UnitPoint(x: 0, y: overlayFaceCenter(id, state).y / ${num(ch)})`);
        L.push(`            }`);
      } else {
        L.push(`            // 1 -> minScale -> 1, \`blinks\` times across the play.`);
        L.push(`            let sy = 1 - (1 - ${num(g.minScale)}) * amp * abs(sin(u * .pi * ${num(g.blinks)}))`);
        L.push(`            if eyes.contains(id) {`);
        L.push(`                e.scaleY *= sy`);
        L.push(`                e.scaleAnchor = UnitPoint(x: 0, y: overlayFaceCenter(id, state).y / ${num(ch)})`);
        L.push(`            }`);
      }
      L.push(`        }`);
      L.push(`    }`);
    }
    L.push(`    return e`);
    L.push(`}`);
    L.push(``);
    // enabledStates membership uses rawValue since ${ENUM} may not be comparable by string;
    // emit a helper the main view uses for blink-suppression too.
    L.push(`private func overlayTransientActive(now: Date, talkStart: Date?, lookStart: Date?, talkLoop: Double?, lookLoop: Double?, gestures: [String: OverlayPlayback], state: ${ENUM}) -> Bool {`);
    if (oi.talk) {
      L.push(`    if let ts = talkStart { let r = now.timeIntervalSince(ts); let ms = (talkLoop.map { r.truncatingRemainder(dividingBy: max($0, 0.001)) } ?? r) * 1000; if ms >= 0 && ms < ${num(oi.talk.durationMs)} { return true } }`);
    }
    if (oi.look) {
      L.push(`    if let ls = lookStart, ${strSet(oi.look.enabledStates.map(safeId))}.contains(state.rawValue) { let r = now.timeIntervalSince(ls); let ms = (lookLoop.map { r.truncatingRemainder(dividingBy: max($0, 0.001)) } ?? r) * 1000; if ms >= 0 && ms < ${num(oi.look.durationMs)} { return true } }`);
    }
    for (const g of gests) {
      const gate = g.enabledStates.length
        ? `, ${strSet(g.enabledStates.map(safeId))}.contains(state.rawValue)`
        : '';
      L.push(`    if let pb = gestures["${g.name}"]${gate} { let r = now.timeIntervalSince(pb.start); let ms = (pb.loopEvery.map { r.truncatingRemainder(dividingBy: max($0, 0.001)) } ?? r) * 1000; if ms >= 0 && ms < ${num(g.durationMs)} { return true } }`);
    }
    L.push(`    return false`);
    L.push(`}`);
    L.push(``);

    return L.join('\n');
  }

  function emitParticleConfig(opts, states) {
    // Emit per-state particle config. CAEmitterLayer supports arc-limited
    // emission via emitterShape="circle" + emissionLongitude + emissionRange,
    // which matches our spawnArc model with one quirk: CAEmitterLayer's circle
    // shape spawns from the circle's RADIUS (not within an annulus). We pick
    // the midpoint of [rMin, rMax] for emitterSize and accept the simplification.
    const lines = [
      `// MARK: - Particles`,
      ``,
      `struct ParticleSpec {`,
      `    var center: CGPoint`,
      `    var radius: ClosedRange<Double>`,
      `    var angleRangeDeg: ClosedRange<Double>     // SVG convention: 0°=right, 90°=down`,
      `    var driftX: ClosedRange<Double>`,
      `    var driftY: ClosedRange<Double>`,
      `    var scale: ClosedRange<Double>`,
      `    var lifetime: Double                      // ms`,
      `    var lifetimeJitter: Double                // ms`,
      `    var interval: Double                      // ms between spawns`,
      `    var burst: Int`,
      `    var rotationJitterDeg: Double`,
      `}`,
      ``,
      `private func particleSpec(for state: ${opts.stateEnum}) -> ParticleSpec? {`,
      `    switch state {`,
    ];
    for (const sn of opts.stateNames) {
      const ps = states[sn].particles;
      if (!ps) {
        lines.push(`    case .${safeId(sn)}: return nil`);
        continue;
      }
      const arc = ps.spawnArc || { center: [145, 155], radius: [40, 60], angle: [180, 360] };
      const drift = ps.drift || { x: [-20, 20], y: [-50, -20] };
      const scale = ps.scaleRange || [0.6, 1.0];
      const swift = [
        `ParticleSpec(`,
        `        center: CGPoint(x: ${num(arc.center[0])}, y: ${num(arc.center[1])}),`,
        `        radius: ${rangeNum(arc.radius[0])}...${rangeNum(arc.radius[1])},`,
        `        angleRangeDeg: ${rangeNum(arc.angle[0])}...${rangeNum(arc.angle[1])},`,
        `        driftX: ${rangeNum(drift.x[0])}...${rangeNum(drift.x[1])},`,
        `        driftY: ${rangeNum(drift.y[0])}...${rangeNum(drift.y[1])},`,
        `        scale: ${rangeNum(scale[0])}...${rangeNum(scale[1])},`,
        `        lifetime: ${num(ps.duration ?? 2500)},`,
        `        lifetimeJitter: ${num(ps.durationJitter ?? 600)},`,
        `        interval: ${num(ps.interval ?? 500)},`,
        `        burst: ${ps.burst ?? 0},`,
        `        rotationJitterDeg: ${num(ps.rotationJitter ?? 15)}`,
        `    )`
      ].join('\n        ');
      lines.push(`    case .${safeId(sn)}: return ${swift}`);
    }
    lines.push(`    }`);
    lines.push(`}`);
    lines.push(``);
    return lines.join('\n');
  }

  // Emit per-state arrays of particle templates as Swift functions that
  // render UIImages via UIKit drawing. The ParticleHostView reads these
  // templates and configures one CAEmitterCell per template, so the emitter
  // randomly spawns each kind of flower.
  function emitParticleTemplates(opts) {
    const states = Object.keys(opts.particleTemplates);
    // NOTE: always emit the ParticleTemplate struct + particleTemplates(for:)
    // function (returning [] for every state when there are none) — the main
    // view references particleTemplates(for:) unconditionally inside its
    // #if canImport(UIKit) block, so a no-particle character would otherwise
    // fail to compile with "Cannot find 'particleTemplates' in scope".
    const lines = [
      `// MARK: - Particle templates`,
      ``,
      `// Each top-level <g> in an orphanSVG of a state-with-particles becomes`,
      `// one ParticleTemplate. The HTML preview clones these groups per spawn`,
      `// to emit live flower copies; in Swift we render each group to a UIImage`,
      `// once and feed it as a CAEmitterCell.contents. Multiple cells let the`,
      `// emitter randomly spawn each flower variant.`,
      `#if canImport(UIKit)`,
      `// ParticleTemplate is fileprivate because it's used as a parameter on`,
      `// ParticleLayerView (which is internal). Swift requires the type to be`,
      `// at least as accessible as the property/init using it.`,
      `fileprivate struct ParticleTemplate {`,
      `    let imageMaker: () -> UIImage`,
      `    let intrinsicSize: CGSize`,
      `}`,
      ``,
    ];

    // Per-template image-maker functions.
    for (const sn of states) {
      const tmpls = opts.particleTemplates[sn];
      tmpls.forEach((t, ti) => {
        const fnName = `make_${safeId(t.name)}`;
        lines.push(`fileprivate func ${fnName}() -> UIImage {`);
        lines.push(`    let size = CGSize(width: ${num(t.width)}, height: ${num(t.height)})`);
        lines.push(`    // Force 1x bitmap scale so the image's pixel dimensions equal its`);
        lines.push(`    // logical point size. UIGraphicsImageRenderer defaults to screen`);
        lines.push(`    // scale (2x/3x on Retina), which would make CAEmitterLayer render`);
        lines.push(`    // the contents at 2x/3x its intended size since CAEmitter cells`);
        lines.push(`    // size their content from the CGImage's pixel dimensions.`);
        lines.push(`    let format = UIGraphicsImageRendererFormat.default()`);
        lines.push(`    format.scale = 1`);
        lines.push(`    let renderer = UIGraphicsImageRenderer(size: size, format: format)`);
        lines.push(`    return renderer.image { rendererCtx in`);
        lines.push(`        let cg = rendererCtx.cgContext`);
        for (const ch of t.children) {
          // Open a small scope per child so successive setFillColor calls don't leak
          const fill = hexToSwiftUIColor_CGColor(ch.fill);
          const segs = ch.segments;
          lines.push(`        do {`);
          lines.push(`            cg.setFillColor(${fill})`);
          // Walk segments and emit cg.move(to:), cg.addCurve(...), etc.
          for (const seg of segs) {
            switch (seg.cmd) {
              case 'M':
                lines.push(`            cg.move(to: CGPoint(x: ${num(seg.pts[0][0])}, y: ${num(seg.pts[0][1])}))`);
                break;
              case 'L':
              case 'H':
              case 'V':
                lines.push(`            cg.addLine(to: CGPoint(x: ${num(seg.pts[0][0])}, y: ${num(seg.pts[0][1])}))`);
                break;
              case 'C':
                lines.push(`            cg.addCurve(to: CGPoint(x: ${num(seg.pts[2][0])}, y: ${num(seg.pts[2][1])}), control1: CGPoint(x: ${num(seg.pts[0][0])}, y: ${num(seg.pts[0][1])}), control2: CGPoint(x: ${num(seg.pts[1][0])}, y: ${num(seg.pts[1][1])}))`);
                break;
              case 'Q':
                lines.push(`            cg.addQuadCurve(to: CGPoint(x: ${num(seg.pts[1][0])}, y: ${num(seg.pts[1][1])}), control: CGPoint(x: ${num(seg.pts[0][0])}, y: ${num(seg.pts[0][1])}))`);
                break;
              case 'Z':
                lines.push(`            cg.closePath()`);
                break;
            }
          }
          if (ch.opacity != null && ch.opacity < 1) {
            lines.push(`            cg.setAlpha(${num(ch.opacity)})`);
          }
          lines.push(`            cg.fillPath()`);
          if (ch.opacity != null && ch.opacity < 1) {
            lines.push(`            cg.setAlpha(1.0)`);
          }
          lines.push(`        }`);
        }
        lines.push(`    }`);
        lines.push(`}`);
        lines.push(``);
      });
    }

    // Per-state lookup: templates(for: state) -> [ParticleTemplate]
    lines.push(`fileprivate func particleTemplates(for state: ${opts.stateEnum}) -> [ParticleTemplate] {`);
    lines.push(`    switch state {`);
    for (const sn of opts.stateNames) {
      const tmpls = opts.particleTemplates[sn];
      if (!tmpls || tmpls.length === 0) {
        lines.push(`    case .${safeId(sn)}: return []`);
        continue;
      }
      lines.push(`    case .${safeId(sn)}: return [`);
      tmpls.forEach((t, i) => {
        const comma = i < tmpls.length - 1 ? ',' : '';
        lines.push(`        ParticleTemplate(imageMaker: make_${safeId(t.name)}, intrinsicSize: CGSize(width: ${num(t.width)}, height: ${num(t.height)}))${comma}`);
      });
      lines.push(`    ]`);
    }
    lines.push(`    }`);
    lines.push(`}`);
    lines.push(`#endif`);
    lines.push(``);
    return lines.join('\n');
  }

  // Helper: convert hex/named color string → Swift CGColor literal expression.
  function hexToSwiftUIColor_CGColor(hex) {
    if (!hex) return 'UIColor.gray.cgColor';
    if (hex === 'white' || hex === '#fff' || hex === '#ffffff' || hex === '#FFFFFF') return 'UIColor.white.cgColor';
    if (hex === 'black' || hex === '#000' || hex === '#000000') return 'UIColor.black.cgColor';
    if (/^url\(/i.test(hex)) return 'UIColor.gray.cgColor';
    let h = hex.replace('#', '');
    if (h.length === 3) h = h.split('').map(c => c + c).join('');
    if (h.length !== 6) return 'UIColor.gray.cgColor';
    const r = parseInt(h.slice(0, 2), 16) / 255;
    const g = parseInt(h.slice(2, 4), 16) / 255;
    const b = parseInt(h.slice(4, 6), 16) / 255;
    return `UIColor(red: ${num(r)}, green: ${num(g)}, blue: ${num(b)}, alpha: 1).cgColor`;
  }

  function emitParticleLayer(opts) {
    return [
      `#if canImport(UIKit)`,
      `// SwiftUI-native particle emitter. Replaces an earlier CAEmitterLayer`,
      `// implementation that couldn't faithfully reproduce the HTML preview's`,
      `// behavior — CAEmitterLayer can't spawn on a polar arc (it spawns in a`,
      `// full disk), can't animate alpha 0→1→0 (only a constant alphaSpeed),`,
      `// and its renderMode required tuning per character.`,
      `//`,
      `// This implementation matches the JS engine's ParticleSystem 1:1:`,
      `//   - Polar arc spawn: random angle in spawnArc.angle, random radius in`,
      `//     spawnArc.radius, converted to (x, y) via cos/sin around center.`,
      `//   - 4-keyframe lifetime: opacity 0 → 1 → 0.85 → 0; scale 0.4·from → to`,
      `//     → midpoint → 0.7·from; drift 0 → 20% → 60% → 100%.`,
      `//   - Normal alpha compositing (no additive blending).`,
      `//   - Timer-driven spawn with initial burst.`,
      `//   - Emission gate halts new spawns immediately when set false; alive`,
      `//     particles continue their lifetime naturally.`,
      ``,
      `// Live particle data. Created in spawnOne, ages out when elapsed >= lifetime.`,
      `fileprivate struct ParticleAlive: Identifiable {`,
      `    let id = UUID()`,
      `    let templateIndex: Int`,
      `    let spawnX: Double`,
      `    let spawnY: Double`,
      `    let driftX: Double`,
      `    let driftY: Double`,
      `    let scaleFrom: Double         // base scale at endpoints`,
      `    let scaleTo: Double           // peak scale at the opacity peak`,
      `    let rotationEndDeg: Double    // final rotation; lerped from 0`,
      `    let lifetimeSec: Double`,
      `    let bornAt: Date`,
      `}`,
      ``,
      `struct ParticleLayerView: View {`,
      `    let spec: ParticleSpec`,
      `    let imageMakers: [() -> UIImage]   // one per particle variant`,
      `    let emitting: Bool                 // false = stop new spawns (alive ones continue)`,
      `    let canvasW: Double`,
      `    let canvasH: Double`,
      ``,
      `    @State private var particles: [ParticleAlive] = []`,
      `    @State private var spawnTimer: Timer?`,
      `    @State private var burstDone = false`,
      `    // Memoized images — rendered once on appear, reused per frame.`,
      `    // Without this we'd re-render each flower's bitmap on every TimelineView`,
      `    // tick (60 Hz × N alive particles).`,
      `    @State private var images: [UIImage] = []`,
      ``,
      `    var body: some View {`,
      `        // TimelineView re-evaluates body on the system's animation timeline`,
      `        // (~60 fps). We compute each alive particle's interpolated position,`,
      `        // scale, opacity, and rotation from its bornAt timestamp + the current`,
      `        // context.date — no @State writes per frame, so layout stays cheap.`,
      `        TimelineView(.animation) { context in`,
      `            let now = context.date`,
      `            ZStack {`,
      `                ForEach(particles) { p in`,
      `                    particleView(p, now: now)`,
      `                }`,
      `            }`,
      `        }`,
      `        .frame(width: canvasW, height: canvasH)`,
      `        .onAppear {`,
      `            if images.isEmpty { images = imageMakers.map { $0() } }`,
      `            startEmitting()`,
      `        }`,
      `        .onDisappear { stopEmitting() }`,
      `        .onChange(of: emitting) { _, newValue in`,
      `            if newValue { startEmitting() } else { stopEmitting() }`,
      `        }`,
      `    }`,
      ``,
      `    @ViewBuilder`,
      `    private func particleView(_ p: ParticleAlive, now: Date) -> some View {`,
      `        let elapsed = now.timeIntervalSince(p.bornAt)`,
      `        let t = min(max(elapsed / p.lifetimeSec, 0), 1)`,
      `        let (opacity, scale, driftFrac, rotFrac) = interpolateLifecycle(t: t, sFrom: p.scaleFrom, sTo: p.scaleTo)`,
      `        if opacity > 0 {`,
      `            let x = p.spawnX + p.driftX * driftFrac`,
      `            let y = p.spawnY + p.driftY * driftFrac`,
      `            Image(uiImage: images.indices.contains(p.templateIndex) ? images[p.templateIndex] : imageMakers[p.templateIndex]())`,
      `                .scaleEffect(scale)`,
      `                .rotationEffect(.degrees(p.rotationEndDeg * rotFrac))`,
      `                .opacity(opacity)`,
      `                .position(x: x, y: y)`,
      `                .allowsHitTesting(false)`,
      `        }`,
      `    }`,
      ``,
      `    // Four-keyframe lifecycle interpolation — matches the JS engine's CSS`,
      `    // keyframe animation precisely. Linear segments between keyframes.`,
      `    //   t=0.00: opacity 0,    scale 0.4·from, drift 0%,   rot 0%`,
      `    //   t=0.18: opacity 1,    scale to,       drift 20%,  rot 25%`,
      `    //   t=0.65: opacity 0.85, scale midpoint, drift 60%,  rot 70%`,
      `    //   t=1.00: opacity 0,    scale 0.7·from, drift 100%, rot 100%`,
      `    private func interpolateLifecycle(t: Double, sFrom: Double, sTo: Double) -> (opacity: Double, scale: Double, driftFrac: Double, rotFrac: Double) {`,
      `        let sMid = (sFrom + sTo) / 2`,
      `        func lerpKeys(_ keys: [(Double, Double)]) -> Double {`,
      `            if t <= keys[0].0 { return keys[0].1 }`,
      `            if t >= keys.last!.0 { return keys.last!.1 }`,
      `            for i in 0..<(keys.count - 1) {`,
      `                if t <= keys[i + 1].0 {`,
      `                    let local = (t - keys[i].0) / (keys[i + 1].0 - keys[i].0)`,
      `                    return keys[i].1 + (keys[i + 1].1 - keys[i].1) * local`,
      `                }`,
      `            }`,
      `            return keys.last!.1`,
      `        }`,
      `        let opacity = lerpKeys([(0, 0), (0.18, 1), (0.65, 0.85), (1, 0)])`,
      `        let scale   = lerpKeys([(0, sFrom * 0.4), (0.18, sTo), (0.65, sMid), (1, sFrom * 0.7)])`,
      `        let drift   = lerpKeys([(0, 0), (0.18, 0.2), (0.65, 0.6), (1, 1.0)])`,
      `        let rot     = lerpKeys([(0, 0), (0.18, 0.25), (0.65, 0.7), (1, 1.0)])`,
      `        return (opacity, scale, drift, rot)`,
      `    }`,
      ``,
      `    private func startEmitting() {`,
      `        guard emitting, !imageMakers.isEmpty else { return }`,
      `        if !burstDone {`,
      `            burstDone = true`,
      `            // Initial burst — spawn spec.burst particles immediately,`,
      `            // staggered slightly so they don't all pop in on the same frame.`,
      `            for i in 0..<spec.burst {`,
      `                let delay = Double(i) * min(0.12, spec.interval / 1000 / 2)`,
      `                DispatchQueue.main.asyncAfter(deadline: .now() + delay) {`,
      `                    spawnOne()`,
      `                }`,
      `            }`,
      `        }`,
      `        // Periodic spawn at spec.interval (ms).`,
      `        spawnTimer?.invalidate()`,
      `        spawnTimer = Timer.scheduledTimer(withTimeInterval: spec.interval / 1000, repeats: true) { _ in`,
      `            spawnOne()`,
      `        }`,
      `    }`,
      ``,
      `    private func stopEmitting() {`,
      `        spawnTimer?.invalidate()`,
      `        spawnTimer = nil`,
      `        // Alive particles continue their lifecycle naturally — we do NOT`,
      `        // remove them. The TimelineView body ages each one out via opacity=0`,
      `        // once t ≥ 1, and the GC step below drops it from state.`,
      `    }`,
      ``,
      `    private func spawnOne() {`,
      `        guard !imageMakers.isEmpty else { return }`,
      `        // Polar arc spawn — matches the JS engine's spawnArc semantics:`,
      `        // random angle in [angleMin, angleMax] degrees, random radius in`,
      `        // [radiusMin, radiusMax], converted to (x, y) around center.`,
      `        let angleDeg = Double.random(in: spec.angleRangeDeg)`,
      `        let angleRad = angleDeg * .pi / 180`,
      `        let r = Double.random(in: spec.radius)`,
      `        let x = spec.center.x + r * cos(angleRad)`,
      `        let y = spec.center.y + r * sin(angleRad)`,
      `        let dx = Double.random(in: spec.driftX)`,
      `        let dy = Double.random(in: spec.driftY)`,
      `        let lifetime = max(0.1, (spec.lifetime + Double.random(in: -spec.lifetimeJitter...spec.lifetimeJitter)) / 1000)`,
      `        let rot = Double.random(in: -spec.rotationJitterDeg...spec.rotationJitterDeg)`,
      `        let tplIdx = Int.random(in: 0..<imageMakers.count)`,
      `        let particle = ParticleAlive(`,
      `            templateIndex: tplIdx,`,
      `            spawnX: x, spawnY: y,`,
      `            driftX: dx, driftY: dy,`,
      `            scaleFrom: spec.scale.lowerBound,`,
      `            scaleTo: spec.scale.upperBound,`,
      `            rotationEndDeg: rot,`,
      `            lifetimeSec: lifetime,`,
      `            bornAt: Date()`,
      `        )`,
      `        particles.append(particle)`,
      `        // GC after lifetime expires so the array doesn't grow unbounded.`,
      `        DispatchQueue.main.asyncAfter(deadline: .now() + lifetime) {`,
      `            particles.removeAll { $0.id == particle.id }`,
      `        }`,
      `    }`,
      `}`,
      ``,
      `#else`,
      `// macOS / non-UIKit fallback — never instantiated. Main view's overlay`,
      `// is wrapped in #if canImport(UIKit). Stub kept so other code that mentions`,
      `// the type compiles on macOS for Xcode preview iteration of non-particle code.`,
      `struct ParticleLayerView: View {`,
      `    var body: some View { EmptyView() }`,
      `}`,
      `#endif`,
      ``,
    ].join('\n');
  }

  function emitMainView(opts) {
    // A custom curve from the preview's bezier editor wins over the named
    // preset ease — same precedence as the JS engine's runTransition.
    const easingExpr = (opts.easingBezier
      ? `Animation.timingCurve(${opts.easingBezier.map(num).join(', ')}, duration: __DUR__)`
      : (SWIFT_EASING[opts.morphEasing] || SWIFT_EASING.easeInOutQuad))
      .replace('__DUR__', String(opts.duration / 1000));
    // Overlays add a controller, an overlay render layer, and eye transients on
    // the face ids. All of it is gated on HAS so overlay-less characters emit the
    // exact same view as before.
    const HAS = opts.hasOverlays;
    const faceSet = new Set(HAS && opts.overlayInfo ? opts.overlayInfo.faceIds : []);
    const CTRL = opts.controllerName;
    // Gesture playbacks are only published on the controller when the character
    // declares gestures; otherwise the transient helpers take an empty dictionary.
    const GESTURE_ARG = (HAS && opts.overlayInfo.gestures && opts.overlayInfo.gestures.length) ? 'controller.gesturePlays' : '[:]';
    // Emit the correct Shape per id based on its strategy + paint info.
    //   - TRANSFORM ids: one MorphShape per subpath inside a Group (so stroke
    //     caps work per-stroke for multi-subpath hands).
    //   - MORPH ids: one MorphPolygonShape (vertex-lerped polygon).
    //   - Stroke paint emits `.stroke(...)`, fill paint emits `.fill(...)`.
    //   - Per-id rotation transforms are applied via the MorphRotation
    //     AnimatableModifier (only ids with a non-zero rotation in any state).
    const idsWithRotation = new Set(
      opts.sharedIds.filter(id =>
        opts.stateNames.some(sn => opts.pathTransforms[id][sn].deg !== 0)
      )
    );
    const wrapWithRotation = (id, content) => {
      if (!idsWithRotation.has(id)) return content;
      const pivots = opts.stateNames
        .map(sn => opts.pathTransforms[id][sn].pivot)
        .filter(Boolean);
      const pivot = pivots[0] || [0, 0];
      return [
        content,
        `                .modifier(MorphRotation(`,
        `                    fromDeg: pathRotation(for: "${id}", in: displayedState).deg,`,
        `                    toDeg: pathRotation(for: "${id}", in: targetState).deg,`,
        `                    pivotX: ${num(pivot[0])},`,
        `                    pivotY: ${num(pivot[1])},`,
        `                    canvasWidth: ${num(opts.viewBox.width)},`,
        `                    canvasHeight: ${num(opts.viewBox.height)},`,
        `                    progress: morphProgress`,
        `                ))`,
      ].join('\n');
    };

    // Force the wrapped block to the canvas's full frame. CRITICAL for any
    // rotationEffect anchored via UnitPoint(pivotX/canvasW, pivotY/canvasH):
    // SwiftUI normalizes UnitPoint to the modified view's frame, NOT to the
    // canvas. A path's natural frame is its tight bbox, so without this
    // wrapper the anchor lands somewhere inside the bbox instead of at the
    // intended SVG user-space pivot. With .topLeading alignment, the path's
    // absolute coords inside this 290x310 region correspond 1:1 to canvas
    // coords, and UnitPoint(pX/canvasW, pY/canvasH) maps to (pX, pY) exactly.
    const wrapWithCanvasFrame = (content) => {
      return [
        content,
        `                .frame(width: ${num(opts.viewBox.width)}, height: ${num(opts.viewBox.height)}, alignment: .topLeading)`,
      ].join('\n');
    };

    // Wrap a shared-id's render block with its full per-element idle transform
    // (wing flap, blink squish, head-nod sub-group, etc.). idleForElement returns
    // identity for ids no idle part targets, so this is a no-op for most paths.
    const wrapWithSelectorIdle = (id, content) => {
      // Suppress blink WHILE MORPHING. The blink squish is anchored at the
      // displayed-state's eye center, but during a transition the eye geometry is
      // interpolating toward the target pose (a different center), so a blink
      // mid-morph squishes/releases about a stale point — on release it snaps the
      // eye up-and-taller (looks like a sudden scale-up). The JS engine avoids this
      // by re-reading each eye's live getBBox center every frame; SwiftUI can't read
      // its own morphing Shape bounds, so we simply pause blinking during the morph
      // (displayedState != targetState) and resume once it lands. Blinks are brief
      // and occasional, so skipping them for the ~morph window is imperceptible.
      const suppress = HAS
        ? `(faceTransientActive || displayedState != targetState)`
        : `displayedState != targetState`;
      const idleCall = `idleForElement("${id}", in: displayedState, t: t, amplitude: idleAmplitude, blinkSuppressed: ${suppress})`;
      return [
        content,
        `                .modifier(ElementIdleMod(e: ${idleCall}))`,
      ].join('\n');
    };

    // Compose the talk / look-around eye transient over the idle, but only on the
    // FACE ids (eyes + mouth). No-op for every other path (and when no overlays).
    const wrapWithTransient = (id, content) => {
      if (!faceSet.has(id)) return content;
      return [
        content,
        `                .modifier(ElementIdleMod(e: overlayTransient("${id}", now: now, talkStart: controller.talkStart, lookStart: controller.lookStart, talkLoop: controller.talkLoop, lookLoop: controller.lookLoop, gestures: ${GESTURE_ARG}, state: displayedState, amp: idleAmplitude)))`,
      ].join('\n');
    };

    const sharedFills = opts.sharedIds.map(id => {
      const paint = opts.paintInfo[id];
      const fMod = filterMod(opts.sharedFilter[id], '                '); // .shadow/.blur (SVG filter)
      // Element-level opacity (SVG `opacity` attr), applied outermost so it fades
      // the shape (and any shadow) together — matches SVG semantics.
      const opMod = paint.opacity != null && paint.opacity < 1
        ? `\n                .opacity(${num(paint.opacity)})` : '';
      const fillExpr = opts.fillByState[id]
        ? `fillColor(for: "${id}", in: fillState)`
        : (paint.fill ? hexToSwiftColor(paint.fill) : idToFillColor(id));
      const strokeExpr = paint.stroke ? hexToSwiftColor(paint.stroke) : null;
      const subCount = opts.subpathCounts[id];

      const strokeStyle = strokeExpr
        ? `.stroke(${strokeExpr}, style: StrokeStyle(lineWidth: ${num(paint.strokeWidth || 1)}, lineCap: ${mapLineCap(paint.strokeLinecap)}, lineJoin: ${mapLineJoin(paint.strokeLinejoin)}))`
        : `.fill(${fillExpr})`;

      // Static per-state geometry group (from == to → MorphShape renders the
      // state's own segments regardless of progress). Used by the CROSSFADE
      // and SCALE method overrides, which never deform contours.
      const staticGroup = (stateExpr) => {
        const parts = [];
        for (let s = 0; s < subCount; s++) {
          parts.push(`                    MorphShape(`);
          parts.push(`                        from: segments(for: "${id}", subpath: ${s}, in: ${stateExpr}),`);
          parts.push(`                        to: segments(for: "${id}", subpath: ${s}, in: ${stateExpr}),`);
          parts.push(`                        progress: 0`);
          parts.push(`                    )`);
          parts.push(`                    ${strokeStyle}`);
        }
        return [`                Group {`, parts.join('\n'), `                }`].join('\n');
      };

      if (opts.strategies[id] === 'CROSSFADE') {
        // Preview method override: two static stacks — displayed fades out
        // (first half), target fades in (second half). Works uniformly for
        // single- and multi-subpath ids.
        const inner = [
          `                ZStack(alignment: .topLeading) {`,
          staticGroup('displayedState'),
          `                .modifier(CrossfadeFadeMod(progress: morphProgress, fadeIn: false))`,
          staticGroup('targetState'),
          `                .modifier(CrossfadeFadeMod(progress: morphProgress, fadeIn: true))`,
          `                }`,
        ].join('\n');
        return wrapWithRotation(id, wrapWithTransient(id, wrapWithSelectorIdle(id, wrapWithCanvasFrame(inner)))) + fMod + opMod + '\n\n';
      }

      if (opts.strategies[id] === 'SCALE') {
        // Preview method override: displayed geometry rigidly mapped onto the
        // target's bbox; geometry snaps at completion when displayedState
        // commits (same as the JS runScaleTween's end-of-tween swap).
        const inner = [
          staticGroup('displayedState'),
        ].join('\n');
        const framed = wrapWithCanvasFrame(inner) + [
          ``,
          `                .modifier(ScaleMorphMod(`,
          `                    progress: morphProgress,`,
          `                    from: scaleBox(for: "${id}", in: displayedState),`,
          `                    to: scaleBox(for: "${id}", in: targetState)`,
          `                ))`,
        ].join('\n');
        return wrapWithRotation(id, wrapWithTransient(id, wrapWithSelectorIdle(id, framed))) + fMod + opMod + '\n\n';
      }

      if (opts.strategies[id] === 'MORPH') {
        const inner = [
          `                MorphPolygonShape(`,
          `                    fromPoly: polygon(for: "${id}", in: displayedState),`,
          `                    toPoly: polygon(for: "${id}", in: targetState),`,
          `                    progress: morphProgress`,
          `                )`,
          `                ${strokeStyle}`,
        ].join('\n');
        return wrapWithRotation(id, wrapWithTransient(id, wrapWithSelectorIdle(id, wrapWithCanvasFrame(inner)))) + fMod + opMod + '\n\n';
      }
      // Multi-subpath paths render as rigid bodies — emit the canonical shape
      // once (no per-subpath morphing) and wrap with RigidBody modifier that
      // animates (translation, rotation) between displayed/target poses.
      // The per-element idle rotation (e.g. hand waggle) is applied INSIDE
      // the rigid body so it rotates the strokes in their canonical space,
      // then the rigid morph repositions everything during transitions.
      if (opts.multiSubpathIds.includes(id)) {
        const canonicalSafe = safeId(opts.canonicalStateName);
        const subParts = [];
        for (let s = 0; s < subCount; s++) {
          subParts.push(`                    ${segPathExpr(opts, `PathData.${safeId(id)}_${canonicalSafe}_sub${s}`, false)}`);
          subParts.push(`                        ${strokeStyle}`);
        }
        const innerGroup = [
          `                Group {`,
          subParts.join('\n'),
          `                }`,
        ].join('\n');
        const innerWithIdle = wrapWithTransient(id, wrapWithSelectorIdle(id, wrapWithCanvasFrame(innerGroup)));
        const block = [
          innerWithIdle,
          `                .modifier(RigidBody(`,
          `                    fromAngleDelta: rigidPose(for: "${id}", in: displayedState).angleDelta,`,
          `                    toAngleDelta: rigidPose(for: "${id}", in: targetState).angleDelta,`,
          `                    fromOffsetX: rigidPose(for: "${id}", in: displayedState).offsetX,`,
          `                    fromOffsetY: rigidPose(for: "${id}", in: displayedState).offsetY,`,
          `                    toOffsetX: rigidPose(for: "${id}", in: targetState).offsetX,`,
          `                    toOffsetY: rigidPose(for: "${id}", in: targetState).offsetY,`,
          `                    canonicalAnchorX: rigidCanonicalAnchor(for: "${id}").x,`,
          `                    canonicalAnchorY: rigidCanonicalAnchor(for: "${id}").y,`,
          `                    canvasWidth: ${num(opts.viewBox.width)},`,
          `                    canvasHeight: ${num(opts.viewBox.height)},`,
          `                    progress: morphProgress`,
          `                ))`,
        ].join('\n');
        return wrapWithRotation(id, block) + fMod + opMod + '\n\n';
      }

      // Single-subpath TRANSFORM: each subpath as its own MorphShape inside a Group.
      const subParts = [];
      for (let s = 0; s < subCount; s++) {
        subParts.push(`                    MorphShape(`);
        subParts.push(`                        from: segments(for: "${id}", subpath: ${s}, in: displayedState),`);
        subParts.push(`                        to: segments(for: "${id}", subpath: ${s}, in: targetState),`);
        subParts.push(`                        progress: morphProgress`);
        subParts.push(`                    )`);
        subParts.push(`                    ${strokeStyle}`);
      }
      const innerGroup = [
        `                Group {`,
        subParts.join('\n'),
        `                }`,
      ].join('\n');
      const innerWithIdle = wrapWithTransient(id, wrapWithSelectorIdle(id, wrapWithCanvasFrame(innerGroup)));
      return wrapWithRotation(id, innerWithIdle) + fMod + opMod + '\n\n';
    }).join('');

    return [
      `// MARK: - Main animator view`,
      ``,
      `// SwiftUI driver. Owns:`,
      `//   - displayedState / targetState pair for snappy any-to-any morphs`,
      `//   - morphProgress (0…1) driving each MorphShape's animatableData`,
      `//   - idleAmplitude (1.0 normally, ramped to 0.1 during morphs and back)`,
      `// Idle math runs in TimelineView's body so it's frame-driven.`,
      ``,
      `public struct ${opts.typeName}: View {`,
      `    @Binding private var externalState: ${opts.stateEnum}`,
      `    @State private var internalState: ${opts.stateEnum} = .${safeId(opts.stateNames[0])}`,
      `    private let usesExternalBinding: Bool`,
      ``,
      `    // Visual state`,
      `    @State private var displayedState: ${opts.stateEnum} = .${safeId(opts.stateNames[0])}`,
      `    @State private var targetState: ${opts.stateEnum} = .${safeId(opts.stateNames[0])}`,
      `    @State private var morphProgress: Double = 1.0   // 0 = at displayedState, 1 = at targetState`,
      `    @State private var idleAmplitude: Double = 1.0`,
      `    @State private var animStart: Date = .distantPast`,
      `    // Gate for the particle emitter. Set false at the start of any transition`,
      `    // leaving a particle state — new spawns halt immediately, alive cells`,
      `    // continue their lifetime. Restored to true after morph completion`,
      `    // (when the new state's emitter is mounted, if applicable).`,
      `    @State private var particlesEmitting: Bool = true`,
      `    // Drives orphan layer opacity. Updated INSIDE withAnimation at`,
      `    // transition start so SwiftUI animates the per-state orphan opacities`,
      `    // (old state fades out, new state fades in) during the morph instead`,
      `    // of snapping when displayedState updates at morph completion.`,
      `    @State private var displayedOrphanState: ${opts.stateEnum} = .${safeId(opts.stateNames[0])}`,
      ...(opts.hasFillChanges ? [
      `    // Drives per-state flat fills. Updated INSIDE the morph's withAnimation`,
      `    // so SwiftUI interpolates the colors along the same curve as the shapes.`,
      `    @State private var fillState: ${opts.stateEnum} = .${safeId(opts.stateNames[0])}`,
      ] : []),
      ...(HAS ? [
      ``,
      `    // Optional external controller — the code-driven handle for state + overlays`,
      `    // (programmatic control). Absent (a throwaway instance) for the init()/init(state:) paths.`,
      `    @ObservedObject private var controller: ${CTRL}`,
      `    private let usesController: Bool`,
      ] : []),
      ``,
      `    public init() {`,
      `        self._externalState = .constant(.${safeId(opts.stateNames[0])})`,
      `        self.usesExternalBinding = false`,
      ...(HAS ? [`        self.controller = ${CTRL}()`, `        self.usesController = false`] : []),
      `    }`,
      `    public init(state: Binding<${opts.stateEnum}>) {`,
      `        self._externalState = state`,
      `        self.usesExternalBinding = true`,
      ...(HAS ? [`        self.controller = ${CTRL}()`, `        self.usesController = false`] : []),
      `    }`,
      ...(HAS ? [
      `    /// Code-driven control: hold a \`${CTRL}\` (e.g. @StateObject), pass it here,`,
      `    /// then call \`setState\` plus any of ${[opts.overlayInfo.emotions.length ? 'playOverlay' : null, (opts.overlayInfo.gestures || []).length ? 'playGesture' : null, opts.overlayInfo.talk ? 'playTalk' : null, opts.overlayInfo.look ? 'playLookAround' : null].filter(Boolean).join(' / ')} from anywhere.`,
      `    public init(controller: ${CTRL}) {`,
      `        self.controller = controller`,
      `        self.usesController = true`,
      `        self._externalState = .constant(.${safeId(opts.stateNames[0])})`,
      `        self.usesExternalBinding = false`,
      `    }`,
      ] : []),
      ``,
      `    private var currentState: ${opts.stateEnum} {`,
      HAS
        ? `        usesController ? controller.state : (usesExternalBinding ? externalState : internalState)`
        : `        usesExternalBinding ? externalState : internalState`,
      `    }`,
      ``,
      `    public var body: some View {`,
      `        TimelineView(.animation) { context in`,
      `            let t = context.date.timeIntervalSince(animStart)`,
      ...(HAS ? [
      `            let now = context.date`,
      `            // A talk / look-around transient is running → suppress the eye blink`,
      `            // (matches the JS engine's _talkActive gate) so it doesn't fight the gaze.`,
      `            let faceTransientActive = overlayTransientActive(now: now, talkStart: controller.talkStart, lookStart: controller.lookStart, talkLoop: controller.talkLoop, lookLoop: controller.lookLoop, gestures: ${GESTURE_ARG}, state: displayedState)`,
      ] : []),
      `            // Whole-body idle: the JS engine writes each root part to`,
      `            // el.style.transform, so multiple root parts CLOBBER each other —`,
      `            // only the LAST one renders (e.g. waggle's sway overwrites its`,
      `            // breathe-y). Match that exactly by evaluating just the last root`,
      `            // part; combining them (the old behavior) added motion the web`,
      `            // preview never shows (e.g. an extra breathe scale during waggle).`,
      `            let rootTransform = idleParts(for: displayedState).last { $0.selector == nil }`,
      `                .map { evaluateIdle($0, t: t, amplitude: idleAmplitude) } ?? IdleTransform()`,
      `            ZStack {`,
      `                // Z-order (back to front), matching the JS engine's SVG render order:`,
      `                //   1. Back-layer orphans (orphans tagged _layer: "back")`,
      `                //   2. Particle layer (per the source SVG's layer: "behind" hint)`,
      `                //   3. Shared morphable paths (body, head, hands, etc.)`,
      `                //   4. Front-layer orphans (default layer: "front", includes orphanSVG)`,
      `                //`,
      `                // .compositingGroup() flattens each state's orphan stack before the`,
      `                // opacity fade so overlapping transparent shapes don't double-blend`,
      `                // mid-fade (would otherwise look fragmented).`,
      `                ForEach(${opts.stateEnum}.allCases, id: \\.self) { sn in`,
      `                    backOrphans(for: sn, t: t, amplitude: idleAmplitude)`,
      `                        .compositingGroup()`,
      `                        .opacity(sn == displayedOrphanState ? 1 : 0)`,
      `                }`,
      `                #if canImport(UIKit)`,
      `                if let spec = particleSpec(for: displayedState) {`,
      `                    ParticleLayerView(`,
      `                        spec: spec,`,
      `                        imageMakers: particleTemplates(for: displayedState).map { $0.imageMaker },`,
      `                        emitting: particlesEmitting,`,
      `                        canvasW: ${num(opts.viewBox.width)},`,
      `                        canvasH: ${num(opts.viewBox.height)}`,
      `                    )`,
      `                    .allowsHitTesting(false)`,
      `                }`,
      `                #endif`,
      `${sharedFills}`,
      `                ForEach(${opts.stateEnum}.allCases, id: \\.self) { sn in`,
      `                    frontOrphans(for: sn, t: t, amplitude: idleAmplitude)`,
      `                        .compositingGroup()`,
      `                        .opacity(sn == displayedOrphanState ? 1 : 0)`,
      `                }`,
      ...(HAS && opts.overlayInfo.emotions.length ? [
      `                // One-shot / looping overlay decorations, in front of everything.`,
      `                overlayLayer(now: now, plays: controller.plays, state: displayedState)`,
      ] : []),
      `            }`,
      `            .frame(width: ${opts.viewBox.width}, height: ${opts.viewBox.height})`,
      `            .scaleEffect(x: rootTransform.scale.width, y: rootTransform.scale.height, anchor: rootTransform.anchor)`,
      `            .rotationEffect(.degrees(rootTransform.rotationDegrees), anchor: rootTransform.anchor)`,
      `            .offset(rootTransform.translation)`,
      `        }`,
      `        .onAppear {`,
      `            animStart = Date()`,
      `            displayedState = currentState`,
      `            targetState = currentState`,
      `            displayedOrphanState = currentState`,
      `        }`,
      `        .onChange(of: currentState) { _, newValue in`,
      `            transition(to: newValue)`,
      `        }`,
      `    }`,
      ``,
      `    private func transition(to newState: ${opts.stateEnum}) {`,
      `        guard newState != targetState else { return }`,
      `        // Particle handoff: if we're leaving a state that emits particles`,
      `        // and heading somewhere with a different (or no) particle spec, stop`,
      `        // spawning immediately. Alive cells finish naturally during the morph.`,
      `        let fromHasParticles = particleSpec(for: displayedState) != nil`,
      `        // Two specs are "the same" if both are non-nil for now — a robust`,
      `        // equality check would require ParticleSpec: Equatable. For the`,
      `        // snowman this is sufficient because only one state has particles.`,
      `        let toHasParticles = particleSpec(for: newState) != nil`,
      `        if fromHasParticles && !toHasParticles {`,
      `            particlesEmitting = false`,
      `        }`,
      `        targetState = newState`,
      `        morphProgress = 0`,
      `        // Orphan crossfade: fade old state's orphans out + new state's orphans in,`,
      `        // both driven by displayedOrphanState changing INSIDE withAnimation.`,
      `        // Done over ~40% of morph duration to match the JS preview's pacing.`,
      `        withAnimation(.easeInOut(duration: ${(opts.duration / 1000) * 0.4})) {`,
      `            displayedOrphanState = newState`,
      `        }`,
      `        // Ramp idle amplitude down to 0.1`,
      `        withAnimation(.timingCurve(0.37, 0, 0.63, 1, duration: ${(opts.duration / 1000) * 0.4})) {`,
      `            idleAmplitude = 0.1`,
      `        }`,
      `        withAnimation(${easingExpr}) {`,
      `            morphProgress = 1.0`,
      ...(opts.hasFillChanges ? [`            fillState = newState`] : []),
      `        }`,
      `        // After morph completes: snap displayedState forward, ramp idle back up,`,
      `        // and restore particle emission so the destination state's emitter (if any)`,
      `        // starts spawning.`,
      `        DispatchQueue.main.asyncAfter(deadline: .now() + ${opts.duration / 1000}) {`,
      `            displayedState = targetState`,
      `            morphProgress = 1.0`,
      `            particlesEmitting = true`,
      `            withAnimation(.timingCurve(0.37, 0, 0.63, 1, duration: ${(opts.duration / 1000) * 0.4})) {`,
      `                idleAmplitude = 1.0`,
      `            }`,
      `        }`,
      `    }`,
      ``,
      `    // Public helper for the no-binding init: programmatic state change.`,
      `    public mutating func setState(_ s: ${opts.stateEnum}) {`,
      `        internalState = s`,
      `    }`,
      `}`,
      ``,
      `// MARK: - Preview`,
      `#if DEBUG`,
      `struct ${opts.typeName}_Preview: PreviewProvider {`,
      `    static var previews: some View {`,
      `        StatePreviewWrapper()`,
      `    }`,
      `    struct StatePreviewWrapper: View {`,
      `        @State private var s: ${opts.stateEnum} = .${safeId(opts.stateNames[0])}`,
      `        var body: some View {`,
      `            VStack {`,
      `                ${opts.typeName}(state: $s)`,
      `                Picker("State", selection: $s) {`,
      `                    ForEach(${opts.stateEnum}.allCases, id: \\.self) { Text($0.rawValue).tag($0) }`,
      `                }.pickerStyle(.segmented)`,
      `            }.padding()`,
      `        }`,
      `    }`,
      `}`,
      `#endif`,
      ``,
    ].join('\n');
  }

  // SVG strokeLinecap → SwiftUI CGLineCap. SVG accepts "butt" (default), "round", "square".
  function mapLineCap(cap) {
    if (cap === 'round') return '.round';
    if (cap === 'square') return '.square';
    return '.butt';
  }
  function mapLineJoin(join) {
    if (join === 'round') return '.round';
    if (join === 'bevel') return '.bevel';
    return '.miter';
  }

  // Best-effort fill colors per common id. Users will replace these with their
  // own colors or gradient resources. We pick neutral, semantic defaults.
  function idToFillColor(id) {
    const lower = id.toLowerCase();
    if (/body|head/.test(lower)) return 'Color.white';
    if (/eye/.test(lower)) return 'Color(.sRGB, red: 0.235, green: 0.235, blue: 0.235, opacity: 1)';
    if (/nose/.test(lower)) return 'Color.orange';
    if (/hand|arm/.test(lower)) return 'Color(.sRGB, red: 0.235, green: 0.235, blue: 0.235, opacity: 1)';
    if (/button/.test(lower)) return 'Color(.sRGB, red: 0.7, green: 0.83, blue: 0.95, opacity: 1)';
    return 'Color.gray';
  }

  // ---------------------------------------------------------------------------
  // Top-level entry point
  // ---------------------------------------------------------------------------

  function exportToSwift(states, options) {
    const opts = Object.assign({
      typeName: 'CharacterAnimator',
      stateEnum: 'CharacterState',
      duration: 1200,
      morphEasing: 'easeInOutQuad',
      viewBox: { width: 290, height: 310 },
      sourceName: null,
    }, options || {});

    // Always self-namespace. If no explicit typePrefix is given, derive one from
    // the type name (e.g. "SnowmanAnimator" → "Snowman"). This guarantees every
    // generic internal type (MorphShape, ElementIdle, IdlePart, ParticleSpec, …)
    // is prefixed, so two exported animators in one module/app can never collide
    // on those names — you only need distinct typeNames. Pass typePrefix: "" via
    // options to explicitly opt out (single-animator projects).
    if (opts.typePrefix == null) {
      opts.typePrefix = safeId(String(opts.typeName || 'Character')).replace(/(Animator|View)$/, '') || 'Character';
    }
    // Preview idle-preset override: replace every state's authored idle with
    // the chosen whole-body preset (or "none") BEFORE any generation, so the
    // root idle, per-element idle, and header docs all agree — exactly what
    // the preview plays.
    if (opts.idleOverride) {
      const replaced = {};
      for (const sn of Object.keys(states)) {
        replaced[sn] = Object.assign({}, states[sn], { idle: opts.idleOverride });
      }
      states = replaced;
    }
    // Prefix-derived argument label for the Path-from-segments initializer (see
    // segPathExpr): camelCase of the prefix, e.g. "SnowmanScene" → "snowmanScene".
    // Empty only when typePrefix was explicitly cleared ("") to opt out.
    {
      const p = safeId(String(opts.typePrefix || ''));
      opts.segLabel = p ? p.charAt(0).toLowerCase() + p.slice(1) : '';
    }

    opts.stateNames = Object.keys(states);
    // Shared ids: every state's paths has this id AND it's not marked _orphan
    // (orphans are decorations that exist in only some states and don't morph).
    const firstStatePaths = Object.keys(states[opts.stateNames[0]].paths);
    opts.sharedIds = firstStatePaths.filter(id => {
      if (states[opts.stateNames[0]].paths[id]._orphan) return false;
      return opts.stateNames.every(sn =>
        states[sn].paths[id] !== undefined && !states[sn].paths[id]._orphan
      );
    });

    // Parse paths, splitting into subpaths. `parsedSubs[id][sn]` is an array
    // of subpath segment arrays — most paths have 1 subpath, but stroke paths
    // like the hands (`M ... M ... M ... M ...`) have 4. Each subpath morphs
    // as its own MorphShape so stroke caps are preserved per stroke.
    const parsedSubs = {};
    for (const id of opts.sharedIds) {
      parsedSubs[id] = {};
      for (const sn of opts.stateNames) {
        const p = states[sn].paths[id];
        const d = getDOf(p);
        const subs = splitSubpaths(d);
        const subSegs = subs.map(sd => parsePath(sd)).filter(Boolean);
        if (subSegs.length === 0) {
          if (typeof console !== 'undefined') console.warn(`Could not parse path for ${id} in ${sn}`);
          parsedSubs[id][sn] = [[{ cmd: 'M', pts: [[0, 0]] }, { cmd: 'L', pts: [[10, 0]] }, { cmd: 'Z', pts: [] }]];
        } else {
          parsedSubs[id][sn] = subSegs;
        }
      }
    }
    // Flat parsed map (single-subpath view) — used for fingerprinting + polygon
    // sampling, which operate on the merged path regardless of split structure.
    const parsed = {};
    for (const id of opts.sharedIds) {
      parsed[id] = {};
      for (const sn of opts.stateNames) {
        const p = states[sn].paths[id];
        const d = getDOf(p);
        const segs = parsePath(d);
        parsed[id][sn] = segs || parsedSubs[id][sn][0];
      }
    }
    opts.parsedSubs = parsedSubs;
    // Per-id subpath count (max across states — if states disagree we pad with empty).
    opts.subpathCounts = {};
    for (const id of opts.sharedIds) {
      opts.subpathCounts[id] = Math.max(...opts.stateNames.map(sn => parsedSubs[id][sn].length));
    }
    // Per-id paint info (stroke vs fill, line cap, width, color). Read from
    // the first state — paint style is assumed constant per id across states
    // (matches the JS engine's behavior: fill snapping at morph end is the
    // only state-varying paint behavior, handled in the morph completion).
    opts.paintInfo = {};
    for (const id of opts.sharedIds) {
      const p = states[opts.stateNames[0]].paths[id];
      opts.paintInfo[id] = {
        fill: p.fill || null,
        stroke: p.stroke || null,
        strokeWidth: p.strokeWidth ? parseFloat(p.strokeWidth) : null,
        strokeLinecap: p.strokeLinecap || null,
        strokeLinejoin: p.strokeLinejoin || null,
        // Element-level opacity (SVG `opacity` attr) — e.g. the semi-transparent
        // decorative fur / wing dots (0.18 / 0.3). Without this they render solid.
        opacity: p.opacity != null ? parseFloat(p.opacity) : 1,
      };
    }

    // Per-state FLAT fills (each character has its own palette, like the Figma
    // critters). When a shared id's fill differs across states and every value
    // is a plain color, emit a per-state Color lookup driven by an animated
    // `fillState` so the color interpolates with the morph (mirrors the JS
    // engine's runFillTween). url() paint servers keep the single canonical
    // paint (gradient swaps stay a states-file authoring concern).
    const FLAT_COLOR = (v) => !!v && (/^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(v) || v === 'white' || v === 'black');
    opts.fillByState = {};
    for (const id of opts.sharedIds) {
      const fills = opts.stateNames.map(sn => states[sn].paths[id].fill || null);
      const distinct = new Set(fills);
      if (distinct.size > 1 && fills.every(FLAT_COLOR)) {
        opts.fillByState[id] = {};
        opts.stateNames.forEach((sn, i) => { opts.fillByState[id][sn] = fills[i]; });
      }
    }
    opts.hasFillChanges = Object.keys(opts.fillByState).length > 0;

    // Filters (shadows / blurs). Parse every state's defs, then map each shared
    // path's filter attr (taken from the first state, matching render-once init)
    // to its descriptor so the emitter can attach .shadow / .blur.
    opts.filters = {};
    for (const sn of opts.stateNames) Object.assign(opts.filters, parseFilters(states[sn].defs || ''));
    // Overlay defs carry the emotion-decoration glow filters (e.g. the swirl glow).
    if (opts.overlays && opts.overlays.defs) Object.assign(opts.filters, parseFilters(opts.overlays.defs));
    opts.sharedFilter = {};
    for (const id of opts.sharedIds) {
      const fref = states[opts.stateNames[0]].paths[id].filter;
      const fid = fref && (fref.match(/url\(#([^)]+)\)/) || [])[1];
      if (fid && opts.filters[fid]) opts.sharedFilter[id] = opts.filters[fid];
    }

    // Multi-subpath paths use rigid-body translation+rotation between states
    // instead of per-subpath segment lerp. Compute (anchor, angle) per state
    // for each multi-subpath id. The canonical shape is taken from the first
    // state — that state's exact subpath geometry is what gets rendered, and
    // every other state's pose is reached by rotating + translating it.
    opts.multiSubpathIds = opts.sharedIds.filter(id => opts.subpathCounts[id] > 1);
    opts.rigidParams = {};
    for (const id of opts.multiSubpathIds) {
      opts.rigidParams[id] = {};
      for (const sn of opts.stateNames) {
        opts.rigidParams[id][sn] = computeRigidParams(opts.parsedSubs[id][sn]);
      }
    }
    // Canonical = first state. Pre-stored for quick reference in the emitter.
    opts.canonicalStateName = opts.stateNames[0];

    // Per-path transform attribute, parsed per (id, state). Used by the
    // MorphRotation animatable modifier to lerp rotation degrees + pivots
    // smoothly during a morph. v1 supports rotate(deg cx cy) only — the
    // most common case (e.g. the snowman head's state-1 tilt). Other
    // transform kinds (translate/scale/matrix) are baked into the path data
    // by the JS engine already; we don't try to extract them.
    opts.pathTransforms = {};
    let anyPathHasTransform = false;
    for (const id of opts.sharedIds) {
      opts.pathTransforms[id] = {};
      for (const sn of opts.stateNames) {
        const p = states[sn].paths[id];
        const tx = parsePerPathTransform(p.transform);
        opts.pathTransforms[id][sn] = tx;
        if (tx.deg !== 0) anyPathHasTransform = true;
      }
    }
    opts.anyPathHasTransform = anyPathHasTransform;

    // Compute strategy per shared id (TRANSFORM vs MORPH), then apply the
    // preview's per-path method overrides (opts.methodOverrides — the path
    // editor's OVERRIDES.methods). MORPH / CROSSFADE / SCALE can be forced on
    // anything; a forced TRANSFORM only holds when the detected structure
    // actually matches (MorphShape pairs control points 1:1 — mismatched
    // structures would garble), so an invalid force falls back to detection.
    opts.strategies = {};
    const methodOv = opts.methodOverrides || {};
    for (const id of opts.sharedIds) {
      const detected = detectStrategy(states, opts.stateNames, id);
      let forced = String(methodOv[id] || '').toUpperCase();
      if (forced === 'AUTO') forced = '';
      if (forced === 'TRANSFORM' && detected !== 'TRANSFORM') {
        if (typeof console !== 'undefined') console.warn(`export-swift: cannot force TRANSFORM on "${id}" (structures differ across states) — using ${detected}`);
        forced = '';
      }
      opts.strategies[id] = (['MORPH', 'TRANSFORM', 'CROSSFADE', 'SCALE'].includes(forced) && forced) || detected;
    }

    // For MORPH-strategy ids, pre-sample polygons (80 evenly-spaced points)
    const polygons = {};
    const POLY_N = 80;
    for (const id of opts.sharedIds) {
      if (opts.strategies[id] !== 'MORPH') continue;
      polygons[id] = {};
      for (const sn of opts.stateNames) {
        polygons[id][sn] = samplePolygon(parsed[id][sn], POLY_N);
      }
    }

    // Collect orphan elements per state (both structured paths with _orphan: true
    // and inline orphanSVG strings parsed into discrete shapes).
    opts.orphansByState = collectOrphans(states, opts.stateNames, opts.viewBox);

    // Overlays (window.OVERLAYS_DATA): one-shot decorations + eye transients,
    // callable from code. Names are prefixed so multiple animators coexist in a
    // module (the enum/controller are public top-level types).
    opts.overlayInfo = buildOverlayInfo(opts, states, parsed);
    opts.hasOverlays = !!opts.overlayInfo;
    opts.overlayEnum = (opts.typePrefix ? safeId(opts.typePrefix) : 'Character') + 'Overlay';
    opts.gestureEnum = (opts.typePrefix ? safeId(opts.typePrefix) : 'Character') + 'Gesture';
    opts.controllerName = (opts.typePrefix ? safeId(opts.typePrefix) : opts.typeName) + 'Controller';

    // Particle template extraction. When a state has a particles config, ALL
    // of its orphans become spawn templates (matching how the JS engine clones
    // each one per spawn). Templates come from two sources:
    //
    //   1. Top-level <g> groups in the orphanSVG (e.g. snowman state-5's
    //      four flower groups) — each group → one composite template image.
    //   2. Structured _orphan: true paths (e.g. snowman state-5's dot, dot_2)
    //      — each → one single-shape template image.
    //
    // The HTML preview lists these explicitly via templates: [selectors], but
    // for codegen we just include every orphan of a particle-state.
    opts.particleTemplates = {};
    // Helper: turn an array of {segments, fill, opacity} child shapes into a
    // template descriptor with its bbox-relative geometry.
    const buildTemplate = (name, childShapes) => {
      let xMin = Infinity, yMin = Infinity, xMax = -Infinity, yMax = -Infinity;
      for (const c of childShapes) {
        const bb = bboxOfSegments(c.segments);
        xMin = Math.min(xMin, bb.x);
        yMin = Math.min(yMin, bb.y);
        xMax = Math.max(xMax, bb.x + bb.width);
        yMax = Math.max(yMax, bb.y + bb.height);
      }
      if (!isFinite(xMin)) return null;
      const translatedChildren = childShapes.map(c => ({
        segments: c.segments.map(s => ({
          cmd: s.cmd,
          pts: s.pts.map(p => [p[0] - xMin, p[1] - yMin]),
        })),
        fill: c.fill,
        opacity: c.opacity,
      }));
      return {
        name: safeId(name),
        width: xMax - xMin,
        height: yMax - yMin,
        children: translatedChildren,
      };
    };

    for (const sn of opts.stateNames) {
      const sd = states[sn];
      if (!sd.particles) continue;
      const templates = [];

      // (1) orphanSVG top-level groups → one composite template per group
      if (sd.orphanSVG) {
        const entities = parseOrphanSVGGroups(sd.orphanSVG);
        const groups = entities.filter(e => e.kind === 'group');
        groups.forEach((g, gi) => {
          const childShapes = [];
          for (const ch of g.children) {
            let segs = parsePath(ch.d);
            if (!segs) continue;
            if (ch.transform) segs = bakeTransformIntoSegments(segs, ch.transform);
            childShapes.push({
              segments: segs,
              fill: ch.fill,
              opacity: (g.opacity || 1) * (ch.opacity != null ? ch.opacity : 1),
            });
          }
          const t = buildTemplate(`${sn}_${g.id || `tpl_${gi}`}`, childShapes);
          if (t) templates.push(t);
        });
      }

      // (2) Structured _orphan: true paths → one single-shape template each.
      // For the snowman state-5 this picks up `dot` and `dot_2` so they spawn
      // as moving particles alongside the flowers, not as fixed orphans.
      for (const [id, p] of Object.entries(sd.paths)) {
        if (!p._orphan) continue;
        const d = getDOf(p);
        let segs = parsePath(d);
        if (!segs) continue;
        if (p.transform) segs = bakeTransformIntoSegments(segs, p.transform);
        const t = buildTemplate(`${sn}_${id}`, [{
          segments: segs,
          fill: p.fill || '#999999',
          opacity: 1,
        }]);
        if (t) templates.push(t);
      }

      if (templates.length > 0) opts.particleTemplates[sn] = templates;
    }

    const sections = [
      emitHeader(opts),
      emitStateEnum(opts),
      emitPathSegmentType(opts),
      emitMorphRotationModifier(opts),
      emitRigidBodyModifier(opts),
      emitMorphShape(opts),
      emitPathData(opts, parsed, opts.strategies, polygons),
      emitSegmentLookup(opts, opts.strategies),
      emitMethodOverrideHelpers(opts),
      emitRotationLookup(opts),
      emitRigidLookup(opts),
      emitOrphanData(opts),
      emitIdleConfig(opts, states),
      emitIdleEvaluator(),
      emitElementIdle(opts, states, parsed),
      emitParticleConfig(opts, states),
      emitParticleTemplates(opts),
      emitParticleLayer(opts),
      emitOverlays(opts),
      emitMainView(opts),
    ];
    return applyTypePrefix(sections.join('\n'), opts);
  }

  // Namespacing for multi-animator apps. The exporter emits generic top-level
  // type names (MorphShape, IdlePart, ParticleSpec, ElementIdle, …) that are
  // module-`internal`, so two exported files in ONE app/module collide. When
  // opts.typePrefix is set (e.g. "Snowman"), prefix every internal/public top-level
  // type — declaration AND all references — so each file's types are unique.
  //
  // Auto-detected from the generated source rather than a hardcoded list, so it
  // also covers MorphRotation / RigidBody / ParticleTemplate (emitted only for
  // some characters) and any future type without maintenance. Skips:
  //   - private / fileprivate types (file-scoped — they never collide)
  //   - the user's already-unique typeName / stateEnum / <typeName>_Preview
  // Renaming is whole-word (\bName\b) so it never partial-matches a longer id.
  function applyTypePrefix(swift, opts) {
    const raw = opts.typePrefix;
    if (!raw) return swift;
    const prefix = safeId(String(raw));
    if (!prefix) return swift;
    // Top-level decls start at column 0 (file scope); nested types are indented.
    const declRe = /^((?:public |open |final |internal |private |fileprivate )*)(struct|enum|class|actor|protocol)\s+([A-Za-z_][A-Za-z0-9_]*)/gm;
    const exclude = new Set([opts.typeName, opts.stateEnum, `${opts.typeName}_Preview`]);
    const names = new Set();
    let m;
    while ((m = declRe.exec(swift)) !== null) {
      const mods = m[1] || '';
      const name = m[3];
      if (/\b(?:private|fileprivate)\b/.test(mods)) continue; // file-scoped → no collision
      if (exclude.has(name)) continue;                         // already unique per file
      if (name.startsWith(prefix)) continue;                   // already prefixed
      names.add(name);
    }
    let out = swift;
    for (const name of names) {
      out = out.replace(new RegExp(`\\b${name}\\b`, 'g'), prefix + name);
    }
    return out;
  }

  // ---------------------------------------------------------------------------
  // Node CLI: `node scripts/export-swift.js <states.js> [out.swift]`
  // ---------------------------------------------------------------------------

  function nodeMain() {
    const fs = require('fs');
    const path = require('path');
    const vm = require('vm');

    const args = process.argv.slice(2);
    if (args.length < 1) {
      console.error('Usage: node export-swift.js <states.js> [out.swift] [--type Name] [--enum Name] [--type-prefix Prefix]');
      console.error('  --type-prefix Snowman   prefix all generic top-level Swift types (MorphShape→SnowmanMorphShape, …)');
      console.error('                       so multiple exported animators can coexist in one app/module.');
      process.exit(2);
    }
    const inFile = path.resolve(args[0]);
    const code = fs.readFileSync(inFile, 'utf8');
    const ctx = { window: {}, console };
    vm.createContext(ctx);
    vm.runInContext(code, ctx);
    const states = ctx.window.STATES_DATA;
    if (!states) {
      console.error(`States file ${inFile} did not set window.STATES_DATA`);
      process.exit(1);
    }
    const opts = { sourceName: path.basename(inFile) };
    let typeFlag, enumFlag, prefixFlag;
    const valueFlags = new Set(['--type', '--enum', '--type-prefix', '--prefix']);
    for (let i = 1; i < args.length; i++) {
      if (args[i] === '--type') typeFlag = args[++i];
      else if (args[i] === '--enum') enumFlag = args[++i];
      else if (args[i] === '--type-prefix' || args[i] === '--prefix') prefixFlag = args[++i];
    }
    const cfg = ctx.window.PREVIEW_CONFIG || {};
    // Name derivation mirrors the preview Export panel so the CLI and the button
    // agree: explicit --type  >  PREVIEW_CONFIG.exportName  >  first title word +
    // "Animator". stateEnum follows from the type name unless --enum is given; the
    // type prefix, if not passed, is auto-derived inside exportToSwift (never bare).
    const titleName = (() => {
      const first = String(cfg.title || 'Character').split(/\s+/)[0].replace(/[^A-Za-z0-9]/g, '');
      return (first.charAt(0).toUpperCase() + first.slice(1) || 'Character') + 'Animator';
    })();
    opts.typeName = typeFlag || cfg.exportName || titleName;
    opts.stateEnum = enumFlag || (opts.typeName.replace(/Animator$/, '') + 'State');
    if (prefixFlag != null) opts.typePrefix = prefixFlag;
    if (cfg.size) opts.viewBox = cfg.size;
    // OVERLAYS_DATA (optional) drives the code-callable one-shot / looping overlay
    // export (decorations + talk / look-around eye transients).
    if (ctx.window.OVERLAYS_DATA) opts.overlays = ctx.window.OVERLAYS_DATA;
    const swift = exportToSwift(states, opts);
    // The positional out path: first non-flag arg after the states file that
    // isn't itself the VALUE of a preceding value-flag (--type Snowman, etc.).
    const outFile = args.find((a, i) => i >= 1 && !a.startsWith('--') && !valueFlags.has(args[i - 1]));
    if (outFile) {
      fs.writeFileSync(outFile, swift);
      console.error(`Wrote ${swift.length} bytes to ${outFile}`);
    } else {
      process.stdout.write(swift);
    }
  }

  if (typeof module !== 'undefined' && module.exports) {
    if (require.main === module) nodeMain();
  }

  return { exportToSwift };
}));
