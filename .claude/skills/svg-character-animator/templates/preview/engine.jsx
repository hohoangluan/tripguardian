// Animation engine for the SVG morph-animator preview shell.
// No React here — just preset data, path parsing, strategy detection,
// transform interpolation, tween runners, and the idle animator class.
// Exposes everything as globals on window.MorphEngine for the app to consume.

(function () {
  const STATES = window.STATES_DATA;
  if (!STATES) throw new Error("STATES_DATA not loaded — include your states.js before engine.jsx");

  const PRESETS = {
    morph: {
      easing: {
        // One preset per genuinely distinct feel. `smooth` (easeInOutSine)
        // and `gentle` (easeInOutQuad ×1.5 duration) were removed — both
        // were near-duplicates of ease-in-out; the curve/duration editors
        // cover any in-between. Default duration 800ms is the conventional
        // UI sweet spot.
        "linear": { ease: "linear", duration: 800 },
        "ease-in-out": { ease: "easeInOutQuad", duration: 800 },
        snappy: { ease: "easeOutCubic", duration: 400 },
        bouncy: { ease: "easeOutBack", duration: 800 },
        dreamy: { ease: "easeInOutSine", duration: 2500 },
      },
    },
  };

  const easeFns = {
    linear: t => t,
    easeOutCubic: t => 1 - Math.pow(1 - t, 3),
    easeInOutQuad: t => t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2,
    easeInOutSine: t => -(Math.cos(Math.PI * t) - 1) / 2,
    easeOutBack: t => { const c1 = 1.70158; const c3 = c1 + 1; return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2); },
  };

  // CSS-style cubic-bezier timing function: P0=(0,0), P3=(1,1), user controls
  // P1/P2. Newton-Raphson solve for the parametric t at a given x, then
  // evaluate y. y outside [0,1] (overshoot, easeOutBack-style) is fine.
  // Powers the preview's editable easing-curve UI.
  function cubicBezierEase(x1, y1, x2, y2) {
    const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
    const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
    const sampleX = t => ((ax * t + bx) * t + cx) * t;
    const sampleY = t => ((ay * t + by) * t + cy) * t;
    const sampleDX = t => (3 * ax * t + 2 * bx) * t + cx;
    return (x) => {
      if (x <= 0) return 0;
      if (x >= 1) return 1;
      let t = x;
      for (let i = 0; i < 8; i++) {
        const dx = sampleX(t) - x;
        if (Math.abs(dx) < 1e-6) break;
        const d = sampleDX(t);
        if (Math.abs(d) < 1e-6) break;
        t -= dx / d;
      }
      t = Math.max(0, Math.min(1, t));
      return sampleY(t);
    };
  }

  // Bezier control points equivalent to each named ease — the curve editor's
  // starting handles when a preset is active. easeOutBack's y1 > 1 encodes the
  // overshoot.
  const EASE_BEZIER = {
    linear: [0.25, 0.25, 0.75, 0.75],
    easeInOutQuad: [0.455, 0.03, 0.515, 0.955],
    easeInOutSine: [0.445, 0.05, 0.55, 0.95],
    easeOutCubic: [0.215, 0.61, 0.355, 1],
    easeOutBack: [0.34, 1.56, 0.64, 1],
  };

  // Path parsing — extract command sequence + absolute points so we can lerp control points directly.
  function parsePath(d) {
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
          cur = consumeXY(); pts.push(cur.slice());
          startSubpath = cur.slice();
          break;
        case 'L':
          cur = consumeXY(); pts.push(cur.slice());
          break;
        case 'H': {
          let x = parseFloat(tokens[i++]); if (!isAbs) x += cur[0];
          cur = [x, cur[1]]; pts.push(cur.slice()); break;
        }
        case 'V': {
          let y = parseFloat(tokens[i++]); if (!isAbs) y += cur[1];
          cur = [cur[0], y]; pts.push(cur.slice()); break;
        }
        case 'C': {
          const c1 = consumeXY(), c2 = consumeXY(), end = consumeXY();
          pts.push(c1, c2, end);
          cur = end;
          break;
        }
        case 'Q': {
          const c1 = consumeXY(), end = consumeXY();
          pts.push(c1, end); cur = end; break;
        }
        case 'Z':
          cur = startSubpath.slice(); break;
        default:
          console.warn("Unhandled cmd:", cmd);
          return null;
      }
      // Normalize H/V to L at parse time (the skill's normalization rule).
      // Two reasons: (1) syntactically-different-but-identical structures
      // (L vs H) fingerprint the same and route to TRANSFORM; (2) the
      // interpolator re-emits each segment as "<cmd> x y" — emitting a raw
      // 'H' with an x AND y would parse as TWO horizontal line-tos and
      // visibly break the shape mid-morph (the "body cracks during
      // TRANSFORM" bug).
      const normCmd = cmd.toUpperCase();
      segments.push({ cmd: (normCmd === 'H' || normCmd === 'V') ? 'L' : normCmd, points: pts });
    }
    return segments;
  }

  function structureFingerprint(d) {
    const segs = parsePath(d);
    if (!segs) return null;
    return segs.map(s => s.cmd).join('');
  }

  // Rotation-aware control-point interpolation. Because the two paths share
  // command structure, their control points correspond 1:1. Naively lerping
  // each point (x = pF + (pT-pF)*t) makes a shape that ROTATES between poses
  // collapse toward its centroid at the midpoint — every vertex cuts across the
  // chord instead of following the arc (this is what shrank a character's wings as
  // they swung from horizontal to vertical).
  //
  // Fix: estimate the rigid motion between the two point sets — centroid shift
  // plus the least-squares optimal rotation theta (Kabsch in 2D, via atan2 of
  // summed cross/dot of the centered points) — then for each point lerp only
  // the *residual* in a shared de-rotated frame and rotate it forward by
  // theta*t. A pure rotation animates rigidly (no shrink); a pure deformation
  // (theta ~ 0) degrades to the original linear lerp exactly, so non-rotating
  // parts are unaffected.
  // Estimate the rigid motion (from/to centroids + least-squares 2D rotation,
  // Kabsch via atan2 of summed cross/dot) between matched point sets.
  // `dPairs` is a list of [dFrom, dTo] pairs: pass ONE pair for a single
  // path, or ALL of a `_group`'s pairs so every member shares the same rigid
  // frame — that's what makes nested parts (eye white + pupil + highlight,
  // arm + sleeve) travel the same arc instead of diverging mid-morph.
  function estimateRigidFromDs(dPairs) {
    let n = 0, sumFx = 0, sumFy = 0, sumTx = 0, sumTy = 0;
    const segPairs = [];
    for (const [dF, dT] of dPairs) {
      const sf = parsePath(dF), st = parsePath(dT);
      if (!sf || !st || sf.length !== st.length) return null;
      for (let i = 0; i < sf.length; i++) {
        if (sf[i].cmd !== st[i].cmd) return null;
        const pf = sf[i].points, pt = st[i].points;
        if (pf.length !== pt.length) return null;
        for (let j = 0; j < pf.length; j++) {
          sumFx += pf[j][0]; sumFy += pf[j][1];
          sumTx += pt[j][0]; sumTy += pt[j][1];
          n++;
        }
      }
      segPairs.push([sf, st]);
    }
    if (n === 0) return null;
    const cFx = sumFx / n, cFy = sumFy / n, cTx = sumTx / n, cTy = sumTy / n;
    let cross = 0, dot = 0;
    for (const [sf, st] of segPairs) {
      for (let i = 0; i < sf.length; i++) {
        const pf = sf[i].points, pt = st[i].points;
        for (let j = 0; j < pf.length; j++) {
          const ax = pf[j][0] - cFx, ay = pf[j][1] - cFy;
          const bx = pt[j][0] - cTx, by = pt[j][1] - cTy;
          dot   += ax * bx + ay * by;
          cross += ax * by - ay * bx;
        }
      }
    }
    return { cFx, cFy, cTx, cTy, theta: Math.atan2(cross, dot) };
  }

  function interpolateStructuredPaths(dFrom, dTo, t, rigid) {
    const sf = parsePath(dFrom);
    const st = parsePath(dTo);
    if (!sf || !st || sf.length !== st.length) return null;
    for (let i = 0; i < sf.length; i++) {
      if (sf[i].cmd !== st[i].cmd || sf[i].points.length !== st[i].points.length) return null;
    }
    // A caller-provided rigid frame (from a `_group`) wins; otherwise
    // estimate from this path alone (original behaviour).
    const R = rigid || estimateRigidFromDs([[dFrom, dTo]]);
    if (!R) return '';
    const { cFx, cFy, cTx, cTy, theta } = R;

    const cx = cFx + (cTx - cFx) * t, cy = cFy + (cTy - cFy) * t; // centroid(t)
    const ang = theta * t;
    const cos = Math.cos(ang),   sin = Math.sin(ang);     // forward R(theta*t)
    const cosN = Math.cos(theta), sinN = Math.sin(theta); // R(-theta) on (bx,by): use (cosN, -sinN)

    let out = '';
    for (let i = 0; i < sf.length; i++) {
      const segF = sf[i], segT = st[i];
      out += segF.cmd;
      for (let j = 0; j < segF.points.length; j++) {
        const ax = segF.points[j][0] - cFx, ay = segF.points[j][1] - cFy;
        // to-residual de-rotated into from's frame: R(-theta) * (b - cT)
        const bx0 = segT.points[j][0] - cTx, by0 = segT.points[j][1] - cTy;
        const bx = bx0 * cosN + by0 * sinN;
        const by = -bx0 * sinN + by0 * cosN;
        // lerp residual in shared frame, then rotate forward by theta*t
        const rx = ax + (bx - ax) * t;
        const ry = ay + (by - ay) * t;
        const x = cx + (rx * cos - ry * sin);
        const y = cy + (rx * sin + ry * cos);
        out += ` ${x.toFixed(3)} ${y.toFixed(3)}`;
      }
      out += ' ';
    }
    return out.trim();
  }

  // SVG primitives → path data (so strategy detection treats them uniformly).
  function ellipseToPath(cx, cy, rx, ry) {
    const k = 0.5522847498;
    return `M ${cx-rx} ${cy} C ${cx-rx} ${cy-ry*k}, ${cx-rx*k} ${cy-ry}, ${cx} ${cy-ry} C ${cx+rx*k} ${cy-ry}, ${cx+rx} ${cy-ry*k}, ${cx+rx} ${cy} C ${cx+rx} ${cy+ry*k}, ${cx+rx*k} ${cy+ry}, ${cx} ${cy+ry} C ${cx-rx*k} ${cy+ry}, ${cx-rx} ${cy+ry*k}, ${cx-rx} ${cy} Z`;
  }
  function rectToPath(x, y, w, h, rx, ry) {
    x = +x || 0; y = +y || 0; w = +w; h = +h;
    rx = Math.min(+rx || 0, w / 2);
    ry = Math.min(+ry || +rx || 0, h / 2);
    if (rx === 0 && ry === 0) {
      return `M ${x} ${y} L ${x+w} ${y} L ${x+w} ${y+h} L ${x} ${y+h} Z`;
    }
    const k = 0.5522847498;
    return `M ${x+rx} ${y} L ${x+w-rx} ${y} C ${x+w-rx+rx*k} ${y} ${x+w} ${y+ry-ry*k} ${x+w} ${y+ry} L ${x+w} ${y+h-ry} C ${x+w} ${y+h-ry+ry*k} ${x+w-rx+rx*k} ${y+h} ${x+w-rx} ${y+h} L ${x+rx} ${y+h} C ${x+rx-rx*k} ${y+h} ${x} ${y+h-ry+ry*k} ${x} ${y+h-ry} L ${x} ${y+ry} C ${x} ${y+ry-ry*k} ${x+rx-rx*k} ${y} ${x+rx} ${y} Z`;
  }
  function getPathDOf(p) {
    if (p.tag === "circle") return ellipseToPath(+p.cx, +p.cy, +p.r, +p.r);
    if (p.tag === "ellipse") return ellipseToPath(+p.cx, +p.cy, +p.rx, +p.ry);
    if (p.tag === "rect") return rectToPath(p.x, p.y, p.width, p.height, p.rx, p.ry);
    return p.d;
  }
  function cssEscape(id) { return id.replace(/[^a-zA-Z0-9_-]/g, "_"); }
  function splitSubpaths(d) { const m = d.match(/[Mm][^Mm]*/g); return m || [d]; }

  // Strategy detection per shared path id — two buckets:
  //   TRANSFORM — same command structure across states → lerp every control point.
  //               Preserves bezier curves, strokes, line caps exactly. No library.
  //   MORPH     — different structure → flubber polygon-samples the morph.
  //
  // Fill differences are NOT a strategy axis. Crossfade strategies were removed
  // from the architecture: stacked-copy rendering added complexity for marginal
  // gain over a clean snap at morph-end. If fills differ between states, the
  // tween runner snaps the fill at completion (see runTransition in app.jsx).
  function detectStrategy(id) {
    const stateNames = Object.keys(STATES);
    const fps = stateNames.map(sn => {
      const p = STATES[sn].paths[id];
      if (!p) return null;
      return structureFingerprint(getPathDOf(p));
    });
    if (fps.some(f => f === null)) return "MORPH";
    return new Set(fps).size === 1 ? "TRANSFORM" : "MORPH";
  }

  const ALL_STATE_NAMES = Object.keys(STATES);

  // ---- Editable preview overrides (path roles / transition methods / duration) ----
  // Written by the app's path editor (persisted in localStorage, keyed by the
  // preview title) or embedded verbatim by the exported web player as
  // window.PATH_OVERRIDES. Roles must be applied BEFORE shared-id computation:
  // marking a path "orphan" reroutes it through the orphan fade pipeline, and
  // that split happens once at init (render-once architecture), hence the
  // editor's "apply & reload" for role changes. Methods are a per-id strategy
  // override and can also be flipped live at transition time.
  const OVERRIDES_KEY = "morphPreviewOverrides:" + ((window.PREVIEW_CONFIG && window.PREVIEW_CONFIG.title) || "default");
  const OVERRIDES = (() => {
    if (window.PATH_OVERRIDES) return window.PATH_OVERRIDES;
    try { return JSON.parse(localStorage.getItem(OVERRIDES_KEY)) || {}; }
    catch (e) { return {}; }
  })();
  OVERRIDES.roles = OVERRIDES.roles || {};
  OVERRIDES.methods = OVERRIDES.methods || {};
  Object.entries(OVERRIDES.roles).forEach(([id, role]) => {
    ALL_STATE_NAMES.forEach(sn => {
      const p = STATES[sn].paths[id];
      if (!p) return;
      if (role === "orphan") p._orphan = true;
      else if (role === "shared") delete p._orphan;
    });
  });

  const SHARED_IDS = (() => {
    const sets = ALL_STATE_NAMES.map(s => new Set(Object.keys(STATES[s].paths)));
    const intersection = [...sets[0]].filter(id => sets.every(s => s.has(id)));
    return intersection.filter(id => !ALL_STATE_NAMES.some(s => STATES[s].paths[id]?._orphan));
  })();

  const STRATEGY = {};
  SHARED_IDS.forEach(id => { STRATEGY[id] = detectStrategy(id); });

  // Multi-subpath ids: paths whose `d` contains multiple `M` commands, meaning
  // they're N separate strokes rendered as one logical id (e.g. hands with
  // 4 finger-strokes). These get rigid-body morph treatment — see runRigidTween.
  // We detect at init by checking the first state's d; states are required to
  // agree on subpath count (true in practice for character animations).
  const MULTI_SUBPATH_IDS = SHARED_IDS.filter(id => {
    const firstD = getPathDOf(STATES[ALL_STATE_NAMES[0]].paths[id]);
    return splitSubpaths(firstD).length > 1;
  });

  // Per-id, per-state rigid pose (anchor + angle). Used by runTransition to
  // pick the displayed/target poses for the rigid tween instead of doing a
  // per-subpath control-point lerp that would stretch strokes.
  const RIGID_PARAMS = {};
  MULTI_SUBPATH_IDS.forEach(id => {
    RIGID_PARAMS[id] = {};
    ALL_STATE_NAMES.forEach(sn => {
      const d = getPathDOf(STATES[sn].paths[id]);
      RIGID_PARAMS[id][sn] = computeRigidParams(splitSubpaths(d));
    });
  });

  // Optional per-test overrides: STRATEGY_OVERRIDES = { body: "MORPH", ... }
  // and STRATEGY_PATH_PATCH = { body: { fill: "none", stroke: "#c8d0d8", strokeWidth: "1" } }
  // applied to every state for that path. Useful for debug-stripping a fill so the
  // raw silhouette morph is visible without gradient interference.
  if (window.STRATEGY_OVERRIDES) {
    Object.entries(window.STRATEGY_OVERRIDES).forEach(([id, s]) => {
      if (STRATEGY[id]) STRATEGY[id] = s;
    });
  }
  if (window.STRATEGY_PATH_PATCH) {
    Object.entries(window.STRATEGY_PATH_PATCH).forEach(([id, patch]) => {
      ALL_STATE_NAMES.forEach(sn => {
        if (STATES[sn].paths[id]) Object.assign(STATES[sn].paths[id], patch);
      });
    });
  }

  // Snapshot the auto-detected strategy (after states-file STRATEGY_OVERRIDES,
  // which express authored intent) so the path editor can show "auto (…)" and
  // revert user method overrides. Then apply the user's per-id method choices —
  // TRANSFORM / MORPH / CROSSFADE / SCALE.
  const DETECTED_STRATEGY = { ...STRATEGY };
  Object.entries(OVERRIDES.methods).forEach(([id, m]) => {
    if (STRATEGY[id] && m && m !== "auto") STRATEGY[id] = m;
  });

  // Sort shared ids by anatomical priority so face/character morphs lead body changes.
  const ANATOMY_ORDER = ["eye", "nose", "mouth", "button", "head", "body", "hand"];
  const sortByAnatomy = (ids) => [...ids].sort((a, b) => {
    const score = (id) => {
      const lower = id.toLowerCase();
      for (let i = 0; i < ANATOMY_ORDER.length; i++) if (lower.startsWith(ANATOMY_ORDER[i])) return i;
      return 99;
    };
    return score(a) - score(b);
  });

  // Parse a transform attribute into an ordered list of ops:
  //   [{name: "rotate", args: [deg, cx, cy]}, {name: "matrix", args: [a,b,c,d,e,f]}, ...]
  // Supports rotate / translate / scale / matrix. skewX/skewY parse but compose
  // as identity (rarely needed; matrix is the escape hatch for arbitrary shears).
  function parseTransform(s) {
    if (!s) return null;
    const ops = [];
    const re = /(matrix|translate|rotate|scale|skewX|skewY)\s*\(([^)]+)\)/g;
    let m;
    while ((m = re.exec(s)) !== null) {
      const args = m[2].trim().split(/[\s,]+/).map(parseFloat).filter(v => !Number.isNaN(v));
      ops.push({ name: m[1], args });
    }
    return ops.length ? ops : null;
  }

  // Convert a single op to a 6-element SVG matrix [a, b, c, d, e, f] where
  //   (newX, newY) = (a*x + c*y + e, b*x + d*y + f).
  function opToMatrix(op) {
    const args = op.args;
    switch (op.name) {
      case "matrix":
        return args.slice(0, 6);
      case "translate":
        return [1, 0, 0, 1, args[0] || 0, args[1] || 0];
      case "scale": {
        const sx = args[0] !== undefined ? args[0] : 1;
        const sy = args[1] !== undefined ? args[1] : sx;
        return [sx, 0, 0, sy, 0, 0];
      }
      case "rotate": {
        const deg = args[0] || 0;
        const cx = args[1] || 0, cy = args[2] || 0;
        const rad = deg * Math.PI / 180;
        const cs = Math.cos(rad), sn = Math.sin(rad);
        // rotate(deg cx cy) = translate(cx,cy) · rotate(deg) · translate(-cx,-cy)
        return [cs, sn, -sn, cs, cx - cs * cx + sn * cy, cy - sn * cx - cs * cy];
      }
      default:
        return [1, 0, 0, 1, 0, 0];
    }
  }

  // SVG transform="A B C" applies A first, then B, then C to the element's local
  // coords. The combined matrix is M = A · B · C (matrix multiplication). We
  // accumulate left-to-right.
  function matMul(M1, M2) {
    const [a1, b1, c1, d1, e1, f1] = M1;
    const [a2, b2, c2, d2, e2, f2] = M2;
    return [
      a1 * a2 + c1 * b2,
      b1 * a2 + d1 * b2,
      a1 * c2 + c1 * d2,
      b1 * c2 + d1 * d2,
      a1 * e2 + c1 * f2 + e1,
      b1 * e2 + d1 * f2 + f1,
    ];
  }

  function opsToMatrix(ops) {
    let M = [1, 0, 0, 1, 0, 0];
    for (const op of ops) M = matMul(M, opToMatrix(op));
    return M;
  }

  // Interpolate two transform-op lists by collapsing each side to a single
  // 6-element matrix and lerping component-wise. Matrix lerp isn't a true
  // rotation interpolator (the determinant dips slightly through the curve),
  // but for the small rotation differences our morphs use (< 30°) the visual
  // error is imperceptible — and this approach uniformly handles mixed inputs
  // (matrix on one side, rotate(...) on the other) which the previous parser
  // could not.
  const IDENTITY = [1, 0, 0, 1, 0, 0];
  function interpolateTransform(from, to, t) {
    if (!from && !to) return null;
    const Mf = from ? opsToMatrix(from) : IDENTITY;
    const Mt = to ? opsToMatrix(to) : IDENTITY;
    const M = Mf.map((v, i) => v + (Mt[i] - v) * t);
    const isIdentity =
      Math.abs(M[0] - 1) < 1e-4 && Math.abs(M[1]) < 1e-4 &&
      Math.abs(M[2]) < 1e-4 && Math.abs(M[3] - 1) < 1e-4 &&
      Math.abs(M[4]) < 1e-4 && Math.abs(M[5]) < 1e-4;
    if (isIdentity) return null;
    return `matrix(${M.map(v => v.toFixed(4)).join(' ')})`;
  }

  function runTransformTween({ target, fromD, toD, fromTransform, toTransform, durationMs, easeFn, delayMs = 0, rigid = null, onComplete }) {
    let cancelled = false;
    const fromXf = parseTransform(fromTransform);
    const toXf = parseTransform(toTransform);
    const begin = () => {
      const start = performance.now();
      const step = (now) => {
        if (cancelled) return;
        const t = Math.min(1, (now - start) / durationMs);
        const eased = easeFn(t);
        const interpD = interpolateStructuredPaths(fromD, toD, eased, rigid);
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
          if (onComplete) onComplete();
        }
      };
      requestAnimationFrame(step);
    };
    if (delayMs > 0) setTimeout(begin, delayMs); else begin();
    return { cancel: () => { cancelled = true; } };
  }

  function runMorphTween({ target, fromD, toD, durationMs, easeFn, delayMs = 0, onComplete, isSmall = false }) {
    let interpolator;
    try {
      interpolator = flubber.interpolate(fromD, toD, { maxSegmentLength: isSmall ? 0.5 : 2 });
    } catch (e) {
      console.error('flubber failed', e);
      target.setAttribute('d', toD);
      if (onComplete) setTimeout(onComplete, durationMs);
      return null;
    }
    let cancelled = false;
    const begin = () => {
      const start = performance.now();
      const step = (now) => {
        if (cancelled) return;
        const t = Math.min(1, (now - start) / durationMs);
        const eased = easeFn(t);
        target.setAttribute('d', interpolator(eased));
        if (t < 1) requestAnimationFrame(step);
        else {
          target.setAttribute('d', toD);
          if (onComplete) onComplete();
        }
      };
      requestAnimationFrame(step);
    };
    if (delayMs > 0) setTimeout(begin, delayMs); else begin();
    return { cancel: () => { cancelled = true; } };
  }

  // Flat-color fill interpolation. Fill is still not a strategy axis — but
  // when BOTH sides are plain hex colors (e.g. a character whose palette is
  // its identity, like the Figma critters), lerping RGB per frame reads far
  // better than the end-of-morph snap. url() paint servers keep the snap.
  const HEX_COLOR_RE = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i;
  const CSS_COLOR_NAMES = { white: "#ffffff", black: "#000000" };
  function isFlatColor(v) { return !!v && (HEX_COLOR_RE.test(v) || v in CSS_COLOR_NAMES); }
  function hexToRgb(v) {
    const h = (CSS_COLOR_NAMES[v] || v).slice(1);
    const full = h.length === 3 ? h.split("").map(c => c + c).join("") : h;
    return [parseInt(full.slice(0, 2), 16), parseInt(full.slice(2, 4), 16), parseInt(full.slice(4, 6), 16)];
  }
  function runFillTween({ target, from, to, durationMs, easeFn, delayMs = 0, attr = "fill" }) {
    const a = hexToRgb(from), b = hexToRgb(to);
    let cancelled = false;
    const begin = () => {
      const start = performance.now();
      const step = (now) => {
        if (cancelled) return;
        const t = Math.min(1, (now - start) / durationMs);
        const e = easeFn ? easeFn(t) : t;
        const c = a.map((av, i) => Math.round(av + (b[i] - av) * Math.min(1, Math.max(0, e))));
        target.setAttribute(attr, `rgb(${c[0]}, ${c[1]}, ${c[2]})`);
        if (t < 1) requestAnimationFrame(step);
        else target.setAttribute(attr, to);
      };
      requestAnimationFrame(step);
    };
    if (delayMs > 0) setTimeout(begin, delayMs); else begin();
    // On cancel, settle on the target color so interrupts read the right paint.
    return { cancel: () => { cancelled = true; target.setAttribute(attr, to); } };
  }

  function tweenStyle({ target, prop, from, to, durationMs, delayMs = 0, easeFn, onComplete }) {
    let cancelled = false;
    let timerId = null;
    const begin = () => {
      if (cancelled) return;
      const start = performance.now();
      function step(now) {
        if (cancelled) return;
        const t = Math.min(1, (now - start) / durationMs);
        const eased = easeFn ? easeFn(t) : t;
        target.style[prop] = String(from + (to - from) * eased);
        if (t < 1) requestAnimationFrame(step);
        else if (onComplete) onComplete();
      }
      requestAnimationFrame(step);
    };
    if (delayMs > 0) { timerId = setTimeout(begin, delayMs); } else begin();
    return { cancel: () => { cancelled = true; if (timerId) clearTimeout(timerId); } };
  }

  // Rigid-body parameters for a multi-subpath path. Such paths (e.g. the
  // snowman hands) aren't deformations across states — they're the same N
  // strokes rotated rigidly around a wrist anchor. Lerping per-endpoint
  // makes strokes stretch and line caps drift. Treating them as a single
  // rigid body and animating a wrapper transform fixes that.
  //
  // Returns { anchor: [x, y], angle: deg }:
  //   anchor — the most common endpoint across subpaths (the wrist)
  //   angle  — vector-averaged direction from anchor to each subpath's far endpoint
  function computeRigidParams(subDStrings) {
    if (!subDStrings || subDStrings.length === 0) return { anchor: [0, 0], angle: 0 };
    const endpoints = [];
    for (const sd of subDStrings) {
      const segs = parsePath(sd);
      if (!segs || segs.length === 0) continue;
      // Find first and last segments with non-empty points. Z carries no
      // points; skip those when locating endpoints. NOTE the engine's
      // parsePath uses `.points` (not `.pts` like the export script's parser).
      let firstPt = null;
      for (let i = 0; i < segs.length; i++) {
        if (segs[i].points && segs[i].points.length > 0) { firstPt = segs[i].points[0]; break; }
      }
      let lastPt = null;
      for (let i = segs.length - 1; i >= 0; i--) {
        if (segs[i].points && segs[i].points.length > 0) {
          lastPt = segs[i].points[segs[i].points.length - 1];
          break;
        }
      }
      if (!firstPt || !lastPt) continue;
      endpoints.push({ first: firstPt, last: lastPt });
    }
    if (endpoints.length === 0) return { anchor: [0, 0], angle: 0 };
    // Group nearby points (0.5 SVG-unit tolerance) to find the wrist anchor.
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
    for (const e of endpoints) { addToGroup(e.first); addToGroup(e.last); }
    groups.sort((a, b) => b.count - a.count);
    const wrist = groups[0].center;
    // Find each subpath's fingertip = whichever endpoint isn't the wrist.
    const fingertips = endpoints.map(e => {
      const dFirst = Math.hypot(e.first[0] - wrist[0], e.first[1] - wrist[1]);
      const dLast = Math.hypot(e.last[0] - wrist[0], e.last[1] - wrist[1]);
      return dFirst < dLast ? e.last : e.first;
    });
    // Vector-average the directions so angle wrap-around is handled correctly.
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

  // Animate a wrapper <g> from "displaying state A's pose" to "displaying
  // state B's pose" using a single rigid transform — translate + rotate, no
  // per-stroke deformation.
  //
  // Pre-condition: the wrapper's inner geometry is already at state B's `d`
  // (we snap d's synchronously before calling this so the first painted frame
  // shows the right starting visual).
  //
  // We apply an inverse transform that maps B's pose back to A's pose at
  // progress=0, then animate that transform toward identity (B's pose) at
  // progress=1. The math:
  //
  //   point P_A = R(angle_A - angle_B) * (P_B - B_anchor) + A_anchor
  //
  // Equivalently in CSS:
  //   transform-origin: B_anchor
  //   transform: translate(A_anchor - B_anchor) rotate(angle_A - angle_B)
  function runRigidTween({ target, fromAnchor, fromAngle, toAnchor, toAngle, durationMs, easeFn, delayMs = 0, onComplete }) {
    let cancelled = false;
    const dx0 = fromAnchor[0] - toAnchor[0];
    const dy0 = fromAnchor[1] - toAnchor[1];
    let dAngle0 = fromAngle - toAngle;
    // Wrap to [-180, 180] so we rotate the short way.
    while (dAngle0 > 180) dAngle0 -= 360;
    while (dAngle0 < -180) dAngle0 += 360;

    // Apply the full inverse transform synchronously so the first frame after
    // the d-snap shows state A's visual, not state B's.
    target.style.transformOrigin = `${toAnchor[0]}px ${toAnchor[1]}px`;
    target.style.transform = `translate(${dx0}px, ${dy0}px) rotate(${dAngle0}deg)`;

    const begin = () => {
      const start = performance.now();
      const step = (now) => {
        if (cancelled) return;
        const t = Math.min(1, (now - start) / durationMs);
        const eased = easeFn ? easeFn(t) : t;
        const factor = 1 - eased;  // 1 → 0 across the tween
        const dx = dx0 * factor;
        const dy = dy0 * factor;
        const da = dAngle0 * factor;
        target.style.transform = `translate(${dx}px, ${dy}px) rotate(${da}deg)`;
        if (t < 1) requestAnimationFrame(step);
        else {
          // Clear so subsequent idle/transform compositions start from identity.
          target.style.transform = "";
          target.style.transformOrigin = "";
          if (onComplete) onComplete();
        }
      };
      requestAnimationFrame(step);
    };
    if (delayMs > 0) setTimeout(begin, delayMs); else begin();
    return {
      cancel: () => {
        cancelled = true;
        // On cancel, leave the current transform in place so the next tween
        // can read it / interrupt smoothly. (Not perfect on interrupts; see
        // SKILL.md → "rigid-body interrupts" note.)
      }
    };
  }

  // Bounding box of a path's control points (covers all subpaths). A control-
  // point hull slightly overestimates curvy shapes, but it's stable across
  // states with matching structure and needs no DOM — good enough to drive the
  // SCALE transition mapping.
  function computePathBBox(d) {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    splitSubpaths(d).forEach(sd => {
      const segs = parsePath(sd);
      if (!segs) return;
      segs.forEach(s => s.points.forEach(([x, y]) => {
        if (x < minX) minX = x; if (x > maxX) maxX = x;
        if (y < minY) minY = y; if (y > maxY) maxY = y;
      }));
    });
    if (minX === Infinity) return null;
    return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
  }

  // CROSSFADE method — fade the element out over the first half, swap its
  // geometry/attributes via the provided callback at the midpoint, fade back
  // in. Works uniformly on single <path> elements and multi-subpath <g>
  // wrappers (the swap callback owns the per-subpath d writes).
  function runCrossfadeTween({ target, durationMs, delayMs = 0, swap, onComplete }) {
    let cancelled = false;
    let swapped = false;
    const baseOp = parseFloat(target.style.opacity);
    const maxOp = Number.isFinite(baseOp) && baseOp > 0 ? baseOp : 1;
    const begin = () => {
      const start = performance.now();
      const step = (now) => {
        if (cancelled) return;
        const t = Math.min(1, (now - start) / durationMs);
        if (t < 0.5) {
          target.style.opacity = String(maxOp * (1 - easeFns.easeInOutSine(t * 2)));
        } else {
          if (!swapped) { swapped = true; if (swap) swap(); }
          target.style.opacity = String(maxOp * easeFns.easeInOutSine((t - 0.5) * 2));
        }
        if (t < 1) requestAnimationFrame(step);
        else { target.style.opacity = String(maxOp); if (onComplete) onComplete(); }
      };
      requestAnimationFrame(step);
    };
    if (delayMs > 0) setTimeout(begin, delayMs); else begin();
    return {
      cancel: () => {
        cancelled = true;
        // Interrupt safety: settle geometry on the target pose (the next tween
        // reads the live d and animates from there) and restore visibility so
        // a half-faded shape doesn't linger translucent.
        if (!swapped && swap) { swapped = true; swap(); }
        target.style.opacity = String(maxOp);
      }
    };
  }

  // SCALE method — treat the shape as rigid: animate a translate+scale that
  // maps the FROM bounding box onto the TO bounding box, then swap the real
  // geometry at completion. Reads as "move & resize" with zero contour
  // morphing. Uses CSS transforms in view-box space (assumes viewBox origin
  // 0 0, true for our canvases).
  function runScaleTween({ target, fromBBox, toBBox, durationMs, easeFn, delayMs = 0, swap, onComplete }) {
    let cancelled = false;
    const sx = fromBBox.width > 0.001 ? toBBox.width / fromBBox.width : 1;
    const sy = fromBBox.height > 0.001 ? toBBox.height / fromBBox.height : 1;
    const clear = () => { target.style.transform = ""; target.style.transformOrigin = ""; };
    const begin = () => {
      const start = performance.now();
      target.style.transformOrigin = "0px 0px";
      const step = (now) => {
        if (cancelled) return;
        const t = Math.min(1, (now - start) / durationMs);
        const e = easeFn ? easeFn(t) : t;
        const csx = 1 + (sx - 1) * e, csy = 1 + (sy - 1) * e;
        const tx = (fromBBox.x + (toBBox.x - fromBBox.x) * e) - fromBBox.x * csx;
        const ty = (fromBBox.y + (toBBox.y - fromBBox.y) * e) - fromBBox.y * csy;
        target.style.transform = `translate(${tx}px, ${ty}px) scale(${csx}, ${csy})`;
        if (t < 1) requestAnimationFrame(step);
        else {
          if (swap) swap();
          clear();
          if (onComplete) onComplete();
        }
      };
      requestAnimationFrame(step);
    };
    if (delayMs > 0) setTimeout(begin, delayMs); else begin();
    return {
      cancel: () => {
        cancelled = true;
        // Settle on the target pose so the interrupting tween starts from a
        // clean geometry (same rationale as runCrossfadeTween.cancel).
        if (swap) swap();
        clear();
      }
    };
  }

  // Idle layer — one persistent rAF loop per character whose amplitude is tweened
  // by the morph layer rather than killed/recreated. Bottom-center pivot by default.
  //
  // Config can be:
  //   - a string: a preset kind ("sway", "breathe", "bob", "shake", "sway-twinkle",
  //     "breathe-y", "waggle-sequence")
  //   - an object: { kind, ...params } — same kinds, with optional params like
  //     duration, amplitude, selector, pivot
  //   - a compound: { kind: "compound", parts: [<config>, <config>, ...] } — runs
  //     several sub-animations on potentially different targets. Use this to combine
  //     a whole-body motion (no selector → svgEl) with sub-element motions like
  //     hand-waving on specific paths.
  const BOTTOM_CENTER = "50% 100%";
  const easeInOut = (t) => t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;

  class IdleAnimator {
    // `originOverride` (optional): a transform-origin string ("50% 100%",
    // "137px 360px", …) that replaces the default pivot for whole-body parts
    // (an explicit user edit from the preview's idle-anchor card, so
    // it wins over authored per-part `origin` values too).
    constructor(svgEl, config, getAmplitude, originOverride = null) {
      this.svgEl = svgEl;
      this.config = config;
      this.kind = config; // legacy field — checked by ref/value for change detection
      this.getAmplitude = getAmplitude;
      this.originOverride = originOverride;
      this.start = performance.now();
      this.cancelled = false;
      this.tick = this.tick.bind(this);
      this.twinkles = svgEl.querySelectorAll('[data-twinkle="true"]');
      this.twinklePhases = Array.from(this.twinkles).map(() => Math.random() * Math.PI * 2);
      // Flatten config into a list of parts (each part is its own sub-animation spec)
      this.parts = this._buildParts(config);
      // Cache resolved targets so we can clear their styles on cancel
      this.targets = new Set([svgEl]);
      this.parts.forEach(p => {
        if (p.selector) {
          const el = svgEl.querySelector(p.selector);
          if (el) { p._target = el; this.targets.add(el); }
        } else {
          p._target = svgEl;
        }
      });
      // Transients — one-shot overlays (e.g. "talk") that compose ON TOP of the
      // base parts for a fixed duration, then auto-expire. See playTransient.
      this.transients = [];
      requestAnimationFrame(this.tick);
    }
    _buildParts(config) {
      if (typeof config === "string") return [{ kind: config }];
      if (!config) return [];
      if (config.kind === "compound" && Array.isArray(config.parts)) return config.parts;
      return [config];
    }
    cancel() {
      this.cancelled = true;
      this.targets.forEach(t => {
        t.style.transform = "";
        t.style.transformOrigin = "";
      });
      if (this.twinkles) this.twinkles.forEach(t => { t.style.opacity = ""; t.style.transform = ""; });
    }
    // Drop cached per-part target lists so getBBox-derived pivots (e.g. the
    // blink / look-around eye centers) recompute on the next tick. Used when the
    // animator was created mid-morph (during the fade-in tail): the pivots first
    // resolve against the not-yet-settled (overshooting) geometry, so we refresh
    // them once the morph lands for pixel-correct centering.
    refresh() {
      for (const part of this.parts) part._targets = null;
    }
    tick(now) {
      if (this.cancelled) return;
      const t = (now - this.start) / 1000;
      const amp = this.getAmplitude();
      // Transients compose on top of base parts. Clear their targets' transform
      // FIRST so the base parts re-apply cleanly this frame and neither the base
      // blink-bake nor the transient's appended transform accumulates across
      // frames. (A target with a base part that SETs transform — nod/sway — is
      // re-set right after; a target with only an appending base part — blink —
      // re-appends onto the cleared value.) On the expiry frame the target is
      // still cleared here, then the transient is filtered out below, so the
      // hand-off back to pure base motion is seamless.
      this._talkActive = false;
      if (this.transients.length) {
        for (const tr of this.transients) {
          for (const t of tr.targets) t.el.style.transform = "";
          // Suppress the base blink while an eye-driving transient (talk /
          // look-around / a one-shot blink gesture) runs.
          if ((tr.kind === "talk" || tr.kind === "look-around" || tr.kind === "blink") && (now - tr.start) < tr.durationMs) this._talkActive = true;
        }
      }
      for (const part of this.parts) this._applyPart(part, t, amp);
      if (this.transients.length) {
        this.transients = this.transients.filter(tr => {
          const elapsed = now - tr.start;
          if (elapsed >= tr.durationMs) return false;
          this._applyTransient(tr, elapsed, amp);
          return true;
        });
      }
      requestAnimationFrame(this.tick);
    }
    // Start a one-shot overlay that composes on top of the running idle for
    // `durationMs`, then removes itself. Used by the preview's "Talk" button:
    // a gentle up/down bob on the eyes + mouth that reads as speaking, layered
    // over whatever loop state is active. Also drives the play-once gestures
    // (blink / look-around / look-up) declared in OVERLAYS_DATA.gestures.
    // Re-calling the same `name` restarts it; two gestures may share a `kind`
    // (look-around and look-up are the same gaze with different offsets) and
    // still be distinct transients.
    playTransient(spec) {
      const sel = spec.selectorAll || spec.selector || "";
      const targets = Array.from(this.svgEl.querySelectorAll(sel)).map(el => {
        this.targets.add(el);
        let cy = 0; try { const b = el.getBBox(); cy = b.y + b.height / 2; } catch (e) { /* not rendered */ }
        return { el, cy, isEye: /eye/i.test(el.id) };
      });
      const tr = {
        kind: spec.kind || "talk",
        name: spec.name || spec.kind || "talk",
        targets,
        start: performance.now(),
        durationMs: spec.durationMs || 1500,
        amplitude: spec.amplitude != null ? spec.amplitude : 2.4,
        cycles: spec.cycles != null ? spec.cycles : 4,
        lift: spec.lift || 0,                                  // px to rise (negative = up)
        heightScale: spec.heightScale != null ? spec.heightScale : 1, // eye scaleY
        // look-around gaze params:
        dx: spec.dx != null ? spec.dx : 5,
        dxLeft: spec.dxLeft,
        dy: spec.dy != null ? spec.dy : 5,
        eyeOpen: spec.eyeOpen != null ? spec.eyeOpen : 1,
        // blink gesture params:
        blinks: spec.blinks != null ? spec.blinks : 1,          // squishes per play
        minScale: spec.minScale != null ? spec.minScale : 0.1,  // eye scaleY at full close
      };
      this.transients = this.transients.filter(x => x.name !== tr.name);
      this.transients.push(tr);
      return tr;
    }
    _applyTransient(tr, elapsed, amp) {
      if (tr.kind === "talk") {
        const u = Math.min(1, elapsed / tr.durationMs);
        // Ramp the whole effect in/out so the face rises into the talking pose
        // and settles back without a jolt.
        const ramp = 0.18;
        let env = 1;
        if (u < ramp) env = u / ramp;
        else if (u > 1 - ramp) env = (1 - u) / ramp;
        const e = env * amp;
        const bob = -tr.amplitude * e * Math.sin(u * tr.cycles * 2 * Math.PI);
        const lift = tr.lift * e;                  // rise toward the single-wing-slap eye Y
        const hs = 1 + (tr.heightScale - 1) * e;   // eyes open taller
        for (const { el, cy, isEye } of tr.targets) {
          let tf = `translateY(${lift + bob}px)`;
          if (isEye && hs !== 1) {
            tf += ` translateY(${cy}px) scaleY(${hs}) translateY(${-cy}px)`;
            el.style.transformOrigin = "0 0"; // scaleY bake centers on user-space cy
          }
          el.style.transform = (el.style.transform || "") + " " + tf;
        }
      } else if (tr.kind === "blink") {
        // One-shot blink: `blinks` vertical squishes of the eyes spread evenly
        // over the transient's duration. Same 1 → minScale → 1 sine profile as
        // the looping `blink` idle part, baked around each eye's own Y center so
        // it composes with whatever transform the idle already set.
        const u = Math.min(1, elapsed / tr.durationMs);
        const sy = 1 - (1 - tr.minScale) * amp * Math.abs(Math.sin(u * Math.PI * tr.blinks));
        for (const { el, cy, isEye } of tr.targets) {
          if (!isEye || sy === 1) continue;
          el.style.transformOrigin = "0 0";
          el.style.transform = (el.style.transform || "") +
            ` translateY(${cy}px) scaleY(${sy}) translateY(${-cy}px)`;
        }
      } else if (tr.kind === "look-around") {
        // One-shot gaze: eyes + mouth glance TL → TR → top-center → back down over
        // the transient's duration (one cycle). Same keyframes as the old idle
        // `look-around`; eyes also open taller (eyeOpen) at the up extreme.
        const u = Math.min(1, elapsed / tr.durationMs);
        const dxR = tr.dx, dxL = tr.dxLeft != null ? tr.dxLeft : tr.dx, dy = tr.dy, eyeOpen = tr.eyeOpen || 1;
        const kf = [
          [0.00, [0, 0]],
          [0.16, [-dxL, -dy]], [0.30, [-dxL, -dy]],
          [0.44, [dxR, -dy]],  [0.58, [dxR, -dy]],
          [0.70, [0, -dy]],    [0.82, [0, -dy]],
          [0.94, [0, 0]],      [1.00, [0, 0]],
        ];
        let ox = 0, oy = 0;
        for (let i = 1; i < kf.length; i++) {
          if (u <= kf[i][0]) {
            const p0 = kf[i - 1][0], v0 = kf[i - 1][1], p1 = kf[i][0], v1 = kf[i][1];
            const span = (p1 - p0) || 1, e = easeFns.easeInOutSine(Math.min(1, Math.max(0, (u - p0) / span)));
            ox = v0[0] + (v1[0] - v0[0]) * e; oy = v0[1] + (v1[1] - v0[1]) * e;
            break;
          }
        }
        ox *= amp; oy *= amp;
        const up = dy > 0 ? Math.min(1, -oy / dy) : 0;
        for (const { el, cy, isEye } of tr.targets) {
          el.style.transformOrigin = "0 0";
          el.style.transform = (isEye && eyeOpen !== 1)
            ? `translate(${ox}px, ${oy}px) translateY(${cy}px) scaleY(${1 + (eyeOpen - 1) * up}) translateY(${-cy}px)`
            : `translate(${ox}px, ${oy}px)`;
        }
      }
    }
    _applyPart(part, t, amp) {
      const el = part._target;
      if (!el) return;
      const kind = part.kind || (typeof part === "string" ? part : null);
      switch (kind) {
        case "sway": {
          // Rotate around bottom-center. Without selectorAll it sways the whole
          // SVG (the base body sway). With selectorAll it sways just that element
          // set — composing on top of the base sway to get a graduated lean
          // (e.g. super-happy: head leans extra, feet counter-rotate to stay
          // still). Only the base (no-selectorAll) sway feeds _swayAngle, which
          // the wings' counterSway subtracts — the extras must not clobber it.
          if (part.selectorAll && !part._targets) {
            part._targets = Array.from(this.svgEl.querySelectorAll(part.selectorAll));
            part._targets.forEach(tg => this.targets.add(tg));
          }
          const d = part.duration || 1.5, a = part.amplitude || 2;
          const swayAngle = a * amp * Math.sin(t * 2 * Math.PI / d);
          const origin = this.originOverride || part.origin || BOTTOM_CENTER;
          // For the default bottom-center pivot, BAKE it into translates instead
          // of using transform-origin. Matrix-identical, but it leaves
          // transform-origin free so a later same-element part (e.g. a blink
          // scaleY baked around the eye's own center) composes cleanly — a shared
          // transform-origin would otherwise warp the blink. (50%/100% resolve
          // against the border-box for the root and the view-box for children,
          // matching "50% 100%" in both cases.)
          let tf, useOrigin;
          if (origin === BOTTOM_CENTER) {
            tf = `translate(50%, 100%) rotate(${swayAngle}deg) translate(-50%, -100%)`;
            useOrigin = "0 0";
          } else {
            tf = `rotate(${swayAngle}deg)`;
            useOrigin = origin;
          }
          const targets = part._targets || (el ? [el] : []);
          for (const target of targets) {
            target.style.transform = tf;
            target.style.transformOrigin = useOrigin;
          }
          if (!part.selectorAll) this._swayAngle = swayAngle;
          break;
        }
        case "breathe": {
          const d = part.duration || 2.0, a = part.amplitude || 0.02;
          el.style.transform = `scale(${1 + a * amp * (0.5 + 0.5 * Math.sin(t * 2 * Math.PI / d))})`;
          el.style.transformOrigin = this.originOverride || part.origin || BOTTOM_CENTER;
          break;
        }
        case "breathe-y": {
          // Vertical-only breath: scale Y, leave X at 1. Symmetric around 1.0
          // so the character is always either expanding or contracting —
          // continuous wave with no implicit pause at baseline. Matches the
          // smooth-sine feel of `sway`. Earlier half-wave version (0..a above
          // baseline only) read as a pulse rather than a wave.
          const d = part.duration || 3.5, a = part.amplitude || 0.018;
          el.style.transform = `scaleY(${1 + a * amp * Math.sin(t * 2 * Math.PI / d)})`;
          el.style.transformOrigin = this.originOverride || part.origin || BOTTOM_CENTER;
          break;
        }
        case "bob": {
          const d = part.duration || 1.0, a = part.amplitude || 3;
          el.style.transform = `translateY(${-a * amp * (0.5 + 0.5 * Math.sin(t * 2 * Math.PI / d))}px)`;
          el.style.transformOrigin = this.originOverride || part.origin || BOTTOM_CENTER;
          break;
        }
        case "float": {
          // Buoyant flight. One combined transform on the (usually root) element:
          //   - baseLift: a raised baseline so the character flies HIGHER.
          //   - asymmetric vertical bob: quick rise, slow fall (`asymmetry` = the
          //     fraction of the cycle spent descending) → "floaty, lands slowly".
          //   - drift: a gentle horizontal sway, and rotate: a slight body tilt.
          // The three motions use incommensurate periods so the loop never quite
          // repeats (the skill's "weightless / floating in water" recipe). They're
          // combined into ONE transform because separate root parts clobber each
          // other (last writer wins). Center origin per the floating-pivot rule.
          const d = part.duration || 1.6, a = part.amplitude || 8, baseLift = part.baseLift || 0;
          const asym = part.asymmetry != null ? part.asymmetry : 0.5; // fraction of cycle descending
          const rotAmp = part.rotate || 0, rotDur = part.rotateDuration || d * 1.7;
          const driftAmp = part.drift || 0, driftDur = part.driftDuration || d * 1.3;
          const phase = (t % d) / d, rise = Math.max(0.05, 1 - asym);
          const h = phase < rise
            ? easeFns.easeInOutSine(phase / rise)                 // rise (quick)
            : 1 - easeFns.easeInOutSine((phase - rise) / asym);   // fall (slow if asym > 0.5)
          const ty = -(baseLift + a * h) * amp;
          const tx = driftAmp * amp * Math.sin(t * 2 * Math.PI / driftDur);
          const rot = rotAmp * amp * Math.sin(t * 2 * Math.PI / rotDur);
          el.style.transform = `translate(${tx}px, ${ty}px) rotate(${rot}deg)`;
          el.style.transformOrigin = this.originOverride || part.origin || "50% 50%";
          break;
        }
        case "nod": {
          // Lift a SET of elements (e.g. head + face) straight up in a gentle
          // rhythm — a "singing" head-raise. translateY only (no rotation), so
          // it reads as looking up rather than a left-right tilt/sway. The lift
          // stays at/above the baseline (0 → up → 0) so it always raises, never
          // dips. Target the whole head assembly (head, fur, eyes, mouth) so the
          // face rides with the head instead of detaching.
          if (part.selectorAll && !part._targets) {
            part._targets = Array.from(this.svgEl.querySelectorAll(part.selectorAll));
            part._targets.forEach(tg => this.targets.add(tg));
          }
          const d = part.duration || 1.3, a = part.amplitude || 3.5;
          const lift = -a * amp * (0.5 - 0.5 * Math.cos(t * 2 * Math.PI / d));
          const tf = `translateY(${lift}px)`;
          const targets = part._targets || (el ? [el] : []);
          for (const target of targets) target.style.transform = tf;
          break;
        }
        case "face-lift": {
          // Seat the eyes/mouth a touch higher at rest (constant upward offset,
          // `lift` px; optional eye-only `eyeScale` for slightly taller eyes).
          // SETs the transform; ordered before `blink`, which appends its squish
          // on top. amp-gated so it relaxes during a morph.
          if (part.selectorAll && !part._targets) {
            part._targets = Array.from(this.svgEl.querySelectorAll(part.selectorAll)).map(target => {
              this.targets.add(target);
              let cy = 0; try { const b = target.getBBox(); cy = b.y + b.height / 2; } catch (e) { /* not rendered */ }
              return { el: target, cy, isEye: /eye/i.test(target.id) };
            });
          }
          const flLift = (part.lift || 0) * amp;
          const flScale = part.eyeScale ? 1 + (part.eyeScale - 1) * amp : 1;
          for (const { el: target, cy, isEye } of part._targets) {
            target.style.transform = (isEye && flScale !== 1)
              ? `translateY(${-flLift}px) translateY(${cy}px) scaleY(${flScale}) translateY(${-cy}px)`
              : `translateY(${-flLift}px)`;
            // Origin 0 0 (not 50% 50%): the scaleY bake above does its own
            // centering around the user-space cy, exactly like `blink`.
            target.style.transformOrigin = "0 0";
          }
          break;
        }
        case "look-around": {
          // Choreographed gaze: the eyes + mouth glance top-left → top-right →
          // top-center → back down, looping. `baseLift` seats the face higher at
          // rest; `dy` is the extra rise at the up positions (set so the top of
          // the glance reaches the single-wing-slap eye height); `eyeOpen` scales
          // the eyes taller as they look up. Mouth only translates. The base body
          // idle (breathe-y on the root) is a different element, so this SETs the
          // face transform directly. amp-gated so the gaze recenters in a morph.
          if (part.selectorAll && !part._targets) {
            part._targets = Array.from(this.svgEl.querySelectorAll(part.selectorAll)).map(target => {
              this.targets.add(target);
              let cy = 0; try { const b = target.getBBox(); cy = b.y + b.height / 2; } catch (e) { /* not rendered */ }
              return { el: target, cy, isEye: /eye/i.test(target.id) };
            });
          }
          const cycle = part.cycleDuration || 5.5;
          const dxR = part.dx != null ? part.dx : 5;          // rightward glance
          const dxL = part.dxLeft != null ? part.dxLeft : dxR; // leftward glance (defaults symmetric)
          const dy = part.dy != null ? part.dy : 4.5;
          const baseLift = part.baseLift || 0;
          const eyeOpen = part.eyeOpen || 1;
          // [phase, [ox, oy]] keyframes; eased (sine) move from the previous
          // keyframe, holds where two consecutive keyframes share a value.
          const kf = [
            [0.00, [0, 0]],
            [0.16, [-dxL, -dy]], [0.30, [-dxL, -dy]],  // glance top-left, hold
            [0.44, [dxR, -dy]],  [0.58, [dxR, -dy]],   // glance top-right, hold
            [0.70, [0, -dy]],   [0.82, [0, -dy]],      // glance top-center, hold
            [0.94, [0, 0]],     [1.00, [0, 0]],        // settle back down, rest
          ];
          const ph = (t % cycle) / cycle;
          let ox = 0, oy = 0;
          for (let i = 1; i < kf.length; i++) {
            if (ph <= kf[i][0]) {
              const p0 = kf[i - 1][0], v0 = kf[i - 1][1];
              const p1 = kf[i][0], v1 = kf[i][1];
              const span = (p1 - p0) || 1;
              const e = easeFns.easeInOutSine(Math.min(1, Math.max(0, (ph - p0) / span)));
              ox = v0[0] + (v1[0] - v0[0]) * e;
              oy = v0[1] + (v1[1] - v0[1]) * e;
              break;
            }
          }
          ox *= amp; oy *= amp;
          const totalY = oy - baseLift * amp;                  // up = negative
          const up = dy > 0 ? Math.min(1, -oy / dy) : 0;       // 0 at rest → 1 fully up
          for (const { el: target, cy, isEye } of part._targets) {
            if (isEye && eyeOpen !== 1) {
              const sc = 1 + (eyeOpen - 1) * up;
              target.style.transform = `translate(${ox}px, ${totalY}px) translateY(${cy}px) scaleY(${sc}) translateY(${-cy}px)`;
            } else {
              target.style.transform = `translate(${ox}px, ${totalY}px)`;
            }
            // Origin 0 0 so the eye scaleY bake centers correctly (matches blink).
            target.style.transformOrigin = "0 0";
          }
          break;
        }
        case "blink": {
          // Occasional quick eye-blink: a vertical squish (open=1 most of the
          // cycle, a fast close→open near the end), in sync across both eyes.
          //
          // The squish is BAKED around each eye's own Y center via translateY
          // (not transform-origin) and APPENDED to whatever transform an earlier
          // part already set on the eye (the happy face-lift, the super-happy
          // head-sway). That lets it compose without a transform-origin conflict.
          // Place this part AFTER the lift/sway part so its fresh transform is
          // the base; the regex strips our own previous bake for the no-base case
          // (e.g. sad, where nothing else writes the eye transform).
          if (!part._targets) {
            const sel = part.selectorAll || part.selector || "";
            part._targets = Array.from(this.svgEl.querySelectorAll(sel)).map(target => {
              this.targets.add(target);
              let cy = 0;
              try { const b = target.getBBox(); cy = b.y + b.height / 2; } catch (e) { /* not rendered */ }
              return { el: target, cy };
            });
          }
          const period = part.period || 3.5;        // seconds between blinks
          const blinkDur = part.blinkDuration || 0.16; // seconds per blink
          const minScale = part.minScale != null ? part.minScale : 0.1;
          const ph = t % period;
          let sy = 1;
          if (ph > period - blinkDur) {
            const u = (ph - (period - blinkDur)) / blinkDur; // 0..1
            sy = 1 - (1 - minScale) * Math.sin(u * Math.PI);  // 1 → minScale → 1
          }
          sy = 1 - (1 - sy) * amp; // settle open during morphs
          if (this._talkActive) sy = 1; // no blinking while talking
          const bakeRe = / ?translateY\([-\d.]+px\) scaleY\([-\d.]+\) translateY\([-\d.]+px\)$/;
          for (const { el: target, cy } of part._targets) {
            const base = (target.style.transform || "").replace(bakeRe, "");
            target.style.transform = (sy === 1)
              ? base
              : `${base} translateY(${cy}px) scaleY(${sy}) translateY(${-cy}px)`.trim();
          }
          break;
        }
        case "shake": {
          const d = part.duration || 0.3, a = part.amplitude || 1;
          el.style.transform = `rotate(${a * amp * Math.sin(t * 2 * Math.PI / d)}deg)`;
          el.style.transformOrigin = this.originOverride || part.origin || BOTTOM_CENTER;
          break;
        }
        case "waggle-sequence": {
          // Choreographed cycle: ramp to -A° (waggle left), brief hold, ramp
          // through center to +A° (waggle right), brief hold, ramp back to 0,
          // rest at center. `restFraction` controls how much of the cycle is
          // the long center rest (default 0.25). Within the motion budget,
          // the holds at extremes are now tiny (1 unit each) so the body
          // sweeps continuously rather than slamming and freezing. Ramps use
          // sine easing for the same smooth feel as `sway`.
          const cycle = part.cycleDuration || 2.4;
          const A = part.amplitude || 3;
          const rest = part.restFraction !== undefined ? part.restFraction : 0.25;
          const motion = 1 - rest;
          // Ratios within the motion budget: ramp/hold/ramp/hold/ramp = 4/0.4/4/0.4/4
          // Sum = 12.8 units; holds are ~3% of motion each (was ~17%).
          const TOTAL_UNITS = 12.8;
          const u = motion / TOTAL_UNITS;
          const rampLeftEnd = 4 * u;
          const holdLeftEnd = rampLeftEnd + 0.4 * u;
          const rampToRightEnd = holdLeftEnd + 4 * u;
          const holdRightEnd = rampToRightEnd + 0.4 * u;
          const rampBackEnd = motion;
          const ease = easeFns.easeInOutSine; // smoother than quadratic easeInOut
          const phase = (t % cycle) / cycle;
          let angle = 0;
          if (phase < rampLeftEnd) {
            angle = -A * ease(phase / rampLeftEnd);
          } else if (phase < holdLeftEnd) {
            angle = -A;
          } else if (phase < rampToRightEnd) {
            angle = -A + 2 * A * ease((phase - holdLeftEnd) / (rampToRightEnd - holdLeftEnd));
          } else if (phase < holdRightEnd) {
            angle = A;
          } else if (phase < rampBackEnd) {
            angle = A * (1 - ease((phase - holdRightEnd) / (rampBackEnd - holdRightEnd)));
          } else {
            angle = 0;
          }
          el.style.transform = `rotate(${angle * amp}deg)`;
          el.style.transformOrigin = this.originOverride || part.origin || BOTTOM_CENTER;
          break;
        }
        case "rotate-around-point": {
          if (part.selectorAll && !part._targets) {
            part._targets = Array.from(this.svgEl.querySelectorAll(part.selectorAll));
            part._targets.forEach(t => this.targets.add(t));
          }
          const d = part.duration || 1.0, a = part.amplitude || 8;
          const pivot = part.pivot || [0, 0];
          let gateAmp = 1;
          if (part.gateCycle && part.gateRange) {
            const gPhase = (t % part.gateCycle) / part.gateCycle;
            const [from, to] = part.gateRange;
            const fade = part.gateFade !== undefined ? part.gateFade : 0.05;
            if (gPhase < from || gPhase > to) gateAmp = 0;
            else if (gPhase < from + fade) gateAmp = easeInOut((gPhase - from) / fade);
            else if (gPhase > to - fade) gateAmp = easeInOut((to - gPhase) / fade);
            else gateAmp = 1;
          }
          // `bias` adds a constant rotation offset (e.g. to rest a wing DOWN
          // from a raised pose); amp-gated like the oscillation so it relaxes
          // during a morph. bias 0 reproduces the original behaviour exactly.
          const flapAngle = (a * gateAmp * Math.sin(t * 2 * Math.PI / d + (part.phase || 0)) + (part.bias || 0)) * amp;
          const counterSway = part.counterSway ? (this._swayAngle || 0) : 0;
          // `liftUndo` (px, +y/down): an amp-scaled translate composed AFTER the
          // rotation. When the wing geometry is baked with a vertical lift for its
          // DOWN rest pose, `bias` rotates it back up while this cancels the baked
          // lift as amp→1 — so the flap lands at the EXACT un-lifted original
          // position, yet at rest (amp→0) the lifted-down pose is unchanged.
          const lu = (part.liftUndo || 0) * amp;
          const rot = `rotate(${flapAngle - counterSway}deg)` + (lu ? ` translate(0px, ${lu}px)` : "");
          const origin = `${pivot[0]}px ${pivot[1]}px`;
          const targets = part._targets || (el ? [el] : []);
          for (const target of targets) {
            target.style.transform = rot;
            target.style.transformOrigin = origin;
          }
          break;
        }
        case "spin": {
          // Continuously rotate each matched element about its OWN center — a
          // steady pinwheel spin (not a bounded oscillation). Used for decorative
          // swirls. Each element's center is measured once via getBBox
          // (view-box coords, which is what px transform-origin resolves to here).
          //
          // The spin runs at a constant rate, independent of the idle amplitude:
          // these are orphan decorations that fade in/out via the morph engine's
          // opacity tweens, so there's no morph geometry for the spin to fight,
          // and gating a cumulative angle by amp would visibly unwind them during
          // a transition.
          //
          // Every element starts at angle 0, so the spin hands off seamlessly
          // from the transition's last frame (orphans arrive unrotated — the pop
          // entrance only scales/fades). For variety, `alternate: true` flips
          // direction on every other element (they diverge smoothly from 0). A
          // nonzero `stagger` would instead offset each element's START angle,
          // which shows as a jump at hand-off, so it defaults to 0. `direction:
          // -1` reverses the base direction.
          if (!part._targets) {
            const sel = part.selectorAll || part.selector || "";
            part._targets = Array.from(this.svgEl.querySelectorAll(sel)).map((target, i) => {
              this.targets.add(target);
              let cx = 0, cy = 0;
              try { const b = target.getBBox(); cx = b.x + b.width / 2; cy = b.y + b.height / 2; } catch (e) { /* not rendered */ }
              return { el: target, cx, cy, i };
            });
          }
          const d = part.duration || 5;
          const dir = part.direction || 1;
          const stagger = part.stagger || 0;
          const alternate = part.alternate;
          for (const { el: target, cx, cy, i } of part._targets) {
            const edir = (alternate && (i % 2 === 1)) ? -dir : dir;
            // % 360 keeps the angle bounded over long sessions (visually
            // identical, since 360k and 0 are the same orientation).
            const angle = (edir * ((t + i * stagger) / d) * 360) % 360;
            target.style.transform = `rotate(${angle}deg)`;
            target.style.transformOrigin = `${cx}px ${cy}px`;
          }
          break;
        }
        case "drip": {
          // A tear-style drop: wells up at the eye, holds, then falls a short way
          // while fading out, rests, and loops. The cycle is ordered
          // rise → hold → fall → rest, so t=0 starts with the well-up. The drop
          // is _idleOwned (hidden by the entrance, see runTransition), so the
          // drip fully owns it — no popIn racing the first fall. Gated by amp:
          // the well-up rides the entrance amp ramp (0→1) and a transition AWAY
          // fades it out.
          //
          // Config (ms unless noted): riseMs (well-up), holdMs (pause before
          // falling), fallMs, restMs (hidden gap), fallDistance (px), riseScale,
          // transformOrigin (the eye point, for the well-up scale).
          if (!part._targets) {
            const sel = part.selectorAll || part.selector || "";
            part._targets = Array.from(this.svgEl.querySelectorAll(sel));
            part._targets.forEach(target => this.targets.add(target));
          }
          const holdMs = part.holdMs != null ? part.holdMs : 400;
          const fallMs = part.fallMs != null ? part.fallMs : 1000;
          const restMs = part.restMs != null ? part.restMs : 500;
          const riseMs = part.riseMs != null ? part.riseMs : 350;
          const fallDist = part.fallDistance != null ? part.fallDistance : 10;
          const riseScale = part.riseScale != null ? part.riseScale : 0.6;
          const origin = part.transformOrigin || "50% 50%";
          const cycleMs = riseMs + holdMs + fallMs + restMs;
          const ph = (t * 1000) % cycleMs;
          let opacity, ty, scale;
          if (ph < riseMs) {
            // eased well-up
            const e = easeFns.easeInOutSine(ph / riseMs);
            opacity = e; ty = 0; scale = riseScale + (1 - riseScale) * e;
          } else if (ph < riseMs + holdMs) {
            opacity = 1; ty = 0; scale = 1;
          } else if (ph < riseMs + holdMs + fallMs) {
            // ease-in-out so the fall + fade accelerate then settle (smoother).
            const e = easeFns.easeInOutSine((ph - riseMs - holdMs) / fallMs);
            opacity = 1 - e;        // fade as it falls
            ty = fallDist * e;      // gentle eased descent
            scale = 1;
          } else {
            opacity = 0; ty = 0; scale = riseScale; // hidden rest
          }
          for (const target of part._targets) {
            target.style.opacity = String(opacity * amp);
            target.style.transform = `translate(0px, ${ty}px) scale(${scale})`;
            target.style.transformOrigin = origin;
          }
          break;
        }
        case "bloom": {
          // Loop the appear/disappear of decorative elements around the character.
          // Each matched element gets a random phase so they don't pulse in sync.
          // Modulates scale only (not opacity), so the morph engine's existing
          // opacity tweens for the same elements during transitions don't fight
          // this loop — entrance/exit fades work on opacity, bloom owns scale.
          // When scale reaches 0, the element is effectively invisible.
          if (!part._targets) {
            const sel = part.selectorAll || part.selector || "";
            part._targets = Array.from(this.svgEl.querySelectorAll(sel)).map(target => {
              this.targets.add(target);
              return { el: target, phase: Math.random() * Math.PI * 2 };
            });
          }
          const d = part.duration || 3.5;
          const [sMin, sMax] = part.scaleRange || [0, 1.05];
          for (const { el: target, phase } of part._targets) {
            const cyclePos = 0.5 + 0.5 * Math.sin(t * 2 * Math.PI / d + phase);
            const rawSc = sMin + (sMax - sMin) * cyclePos;
            // At amp=0, scale stays at 1 (no modulation, lets opacity tweens own
            // visibility during transitions). At amp=1, full bloom cycle.
            const sc = 1 + (rawSc - 1) * amp;
            target.style.transform = `scale(${sc})`;
            target.style.transformOrigin = "50% 50%";
          }
          break;
        }
        case "pop-loop": {
          // Loop the appear/hold/disappear of decorative elements. Each matched
          // element gets a staggered phase (evenly spaced around the cycle) so
          // they pop in one-by-one rather than in sync. During the visible
          // portion of each cycle, the element can also rotate and translate,
          // enabling things like:
          //   - squiggle decorations that rotate as they appear
          //   - a tear that drops downward
          //   - stars that spin while present
          //
          // Config:
          //   selectorAll:        CSS selector for the elements to drive
          //   cycleDuration:      seconds per full appear→hold→disappear cycle
          //   visibilityFraction: fraction of cycle the element is fully visible
          //   fadeFraction:       fraction of cycle to fade in (also used to fade out)
          //   scaleRange:         [from, to] — scale during fade-in (and reverse on fade-out)
          //   rotateRange:        [from, to] — rotation degrees during visible window
          //   translateRange:     [[fx, fy], [tx, ty]] — translation during visible window
          //   staggerMode:        "even" (default) or "random"
          //   originSelf:         scale/rotate about each element's OWN center
          //                       (pop in place) instead of the shared origin
          if (!part._targets) {
            const sel = part.selectorAll || part.selector || "";
            const els = Array.from(this.svgEl.querySelectorAll(sel));
            const mode = part.staggerMode || "even";
            // phaseStep: fixed phase gap between successive elements (the spacing
            // between when each appears), as a fraction of the cycle. Default
            // spreads them evenly (1/count).
            const phaseStep = part.phaseStep;
            part._targets = els.map((target, i) => {
              this.targets.add(target);
              const phaseOffset = mode === "random"
                ? Math.random()
                : (phaseStep != null ? (i * phaseStep) % 1 : (els.length > 1 ? i / els.length : 0));
              // originSelf: about each element's own view-box bbox center, so it
              // pops in place. Otherwise the shared transformOrigin (default
              // 50% 50% = view-box center) makes elements converge on the center
              // (e.g. stars flying toward the head).
              let origin = part.transformOrigin || "50% 50%";
              if (part.originSelf) {
                try { const b = target.getBBox(); origin = `${b.x + b.width / 2}px ${b.y + b.height / 2}px`; } catch (e) { /* not rendered */ }
              }
              return { el: target, phaseOffset, origin };
            });
          }
          const cycle = part.cycleDuration || 3.0;
          const visFrac = part.visibilityFraction != null ? part.visibilityFraction : 0.55;
          const fadeFrac = part.fadeFraction != null ? part.fadeFraction : 0.15;
          const [sFrom, sTo] = part.scaleRange || [0.3, 1.0];
          const [rFrom, rTo] = part.rotateRange || [0, 0];
          const [tFrom, tTo] = part.translateRange || [[0, 0], [0, 0]];
          for (const { el: target, phaseOffset, origin } of part._targets) {
            const phase = ((t / cycle) + phaseOffset) % 1;
            // Phase windows within the cycle:
            //   [0,                    fadeFrac]                                    fade-in
            //   [fadeFrac,             fadeFrac + visFrac]                          visible / hold
            //   [fadeFrac + visFrac,   2*fadeFrac + visFrac]                        fade-out
            //   [2*fadeFrac + visFrac, 1]                                            hidden rest
            let opacity = 0, scale = sFrom, rot = rFrom, tx = tFrom[0], ty = tFrom[1];
            const visStart = fadeFrac, visEnd = fadeFrac + visFrac;
            const fadeOutEnd = visEnd + fadeFrac;
            if (phase < visStart) {
              const u = phase / fadeFrac;
              const e = easeFns.easeOutBack(u);
              opacity = u;
              scale = sFrom + (sTo - sFrom) * e;
              // Hold motion at start of visible window
              rot = rFrom;
              tx = tFrom[0]; ty = tFrom[1];
            } else if (phase < visEnd) {
              const u = (phase - visStart) / visFrac;
              opacity = 1;
              scale = sTo;
              rot = rFrom + (rTo - rFrom) * u;
              tx = tFrom[0] + (tTo[0] - tFrom[0]) * u;
              ty = tFrom[1] + (tTo[1] - tFrom[1]) * u;
            } else if (phase < fadeOutEnd) {
              const u = (phase - visEnd) / fadeFrac;
              opacity = 1 - u;
              scale = sTo - (sTo - sFrom) * u;
              rot = rTo;
              tx = tTo[0]; ty = tTo[1];
            } // else hidden
            // amp gates opacity: during morphs amp→0 so the loop's elements fade
            // with the transition (no leftover lingering into the next state),
            // and on entrance amp ramps 0→1 so they fade in as the loop starts.
            target.style.opacity = String(opacity * amp);
            target.style.transform =
              `translate(${tx}px, ${ty}px) scale(${scale}) rotate(${rot}deg)`;
            target.style.transformOrigin = origin;
          }
          break;
        }
        case "sway-twinkle": {
          // Compound preset retained for backward-compat with earlier states files.
          const d = part.duration || 1.8, a = part.amplitude || 1.5;
          el.style.transform = `rotate(${a * amp * Math.sin(t * 2 * Math.PI / d)}deg)`;
          el.style.transformOrigin = this.originOverride || part.origin || BOTTOM_CENTER;
          this.twinkles.forEach((tw, i) => {
            const phase = this.twinklePhases[i];
            const period = 0.6 + (i * 0.13) % 0.4;
            const base = parseFloat(tw.dataset.targetOpacity) || 1;
            const v = amp * base * (0.75 + 0.25 * Math.sin(t * 2 * Math.PI / period + phase));
            const sc = 0.92 + 0.08 * amp * Math.sin(t * 2 * Math.PI / period + phase);
            tw.style.opacity = String(v);
            tw.style.transform = `scale(${sc})`;
            tw.style.transformOrigin = "50% 50%";
          });
          break;
        }
        case "twinkle": {
          // Just the twinkle component, no whole-body motion. Used inside compound
          // configs alongside other parts.
          this.twinkles.forEach((tw, i) => {
            const phase = this.twinklePhases[i];
            const period = 0.6 + (i * 0.13) % 0.4;
            const base = parseFloat(tw.dataset.targetOpacity) || 1;
            const v = amp * base * (0.75 + 0.25 * Math.sin(t * 2 * Math.PI / period + phase));
            const sc = 0.92 + 0.08 * amp * Math.sin(t * 2 * Math.PI / period + phase);
            tw.style.opacity = String(v);
            tw.style.transform = `scale(${sc})`;
            tw.style.transformOrigin = "50% 50%";
          });
          break;
        }
      }
    }
  }

  // ParticleSystem — continuously spawns ephemeral clones of "template"
  // elements at random spawn positions, animates each with the floatUp /
  // floatDrift pattern (opacity 0 → 1 → 0, slight upward drift, slight scale
  // and rotation jitter), and removes them when the animation completes.
  //
  // Inspired by the guitar-widget reference: separate spawn events feeding
  // into a single animation pipeline give a much more "alive" feel than
  // modulating fixed orphans in place.
  //
  // Templates: each template is an existing SVG element in the document.
  // The system clones it on each spawn (stripping ids to avoid duplicates)
  // and wraps the clone in a positioning <g>. Templates stay in place at
  // opacity 0 so they don't render statically (the app hides them when a
  // state has a `particles` config) but remain available for getBBox() and
  // cloneNode().
  //
  // Config:
  //   templates:   array of CSS selectors resolved against the SVG root.
  //                Every matched element is added to the pool.
  //   spawnArea:   { x: [lo, hi], y: [lo, hi] } in SVG user-space coords.
  //                Rectangular spawn area. Default if neither is set.
  //   spawnArc:    { center: [cx, cy], radius: [rMin, rMax], angle: [aMin, aMax] }
  //                Polar spawn area — picks angle in [aMin, aMax] degrees and
  //                radius in [rMin, rMax], then converts to (x, y). Use this
  //                for "particles emerging from a halo around a feature."
  //                Angle convention: 0° = right, 90° = down (SVG y), 180° = left,
  //                270° = up. Top semicircle is [180°, 360°].
  //   drift:       { x: [lo, hi], y: [lo, hi] } total displacement during a
  //                particle's lifetime, sampled per particle. y is typically
  //                negative (upward) since SVG y increases downward.
  //   scaleRange:  [from, to] — the particle starts small, scales up at the
  //                opacity-peak, then shrinks slightly as it fades out.
  //   rotationJitter: max ± degrees of end-rotation. Default 15.
  //   interval:    ms between spawns.
  //   burst:       number of particles spawned immediately on start (to avoid
  //                an empty stage during the first interval).
  //   duration:    base lifetime ms per particle. Each particle gets a random
  //                jitter of ±durationJitter ms (default 600).
  //   layer:       "front" (default) or "behind". When "behind", the particle
  //                layer is inserted before the first shared path so particles
  //                render behind the character (peeking around the silhouette).
  class ParticleSystem {
    constructor(svgEl, config) {
      this.svgEl = svgEl;
      this.config = config || {};
      this.intervalId = null;
      this.alive = new Set();
      this.layer = document.createElementNS("http://www.w3.org/2000/svg", "g");
      this.layer.setAttribute("class", "particle-layer");
      this.layer.style.pointerEvents = "none";
      // Layer placement controls whether particles render in front of or behind
      // the character. "behind" inserts the particle layer just before the first
      // shared path — so back-layer orphans and the new particle layer render
      // first, then the character body covers part of the particles, giving a
      // "peeking out from behind" effect.
      if (this.config.layer === "behind") {
        const firstShared = svgEl.querySelector('[id^="path-"]:not([id*="orphan"])');
        if (firstShared && firstShared.parentNode === svgEl) {
          svgEl.insertBefore(this.layer, firstShared);
        } else {
          svgEl.appendChild(this.layer);
        }
      } else {
        svgEl.appendChild(this.layer);
      }
      this._resolveTemplates();
    }
    _resolveTemplates() {
      const sels = this.config.templates || [];
      this.templates = [];
      for (const sel of sels) {
        const els = this.svgEl.querySelectorAll(sel);
        for (const el of els) {
          let bbox = { x: 0, y: 0, width: 0, height: 0 };
          try { bbox = el.getBBox(); } catch (e) { /* not in render tree yet */ }
          this.templates.push({ el, bbox });
        }
      }
    }
    start() {
      if (this.intervalId) return;
      const interval = this.config.interval || 500;
      const burst = this.config.burst || 0;
      for (let i = 0; i < burst; i++) {
        // Stagger burst spawns slightly so they don't pop in perfectly synced
        setTimeout(() => this.spawn(), i * Math.min(120, interval / 2));
      }
      this.intervalId = setInterval(() => this.spawn(), interval);
    }
    cancel() {
      // Stop spawning; existing particles finish naturally.
      if (this.intervalId) { clearInterval(this.intervalId); this.intervalId = null; }
    }
    // Restart spawning after a cancel(). Used when a transition that started
    // by stopping emission (e.g. state-5 → state-1) gets redirected back to
    // a particle state mid-flight (state-5 → state-1 → state-5).
    resume() {
      if (this.intervalId) return;  // already running
      const interval = this.config.interval || 500;
      this.intervalId = setInterval(() => this.spawn(), interval);
    }
    // Live-update the spawn interval. Required because setInterval captures the
    // delay at construction; mutating config.interval alone won't change cadence.
    // All other config fields (spawnArc, drift, scaleRange, duration, ...) are
    // re-read on every spawn(), so mutating them in place takes effect naturally.
    setIntervalMs(ms) {
      this.config.interval = ms;
      if (this.intervalId) {
        clearInterval(this.intervalId);
        this.intervalId = setInterval(() => this.spawn(), ms);
      }
    }
    // Imperatively trigger a burst. Used by the slider UI so the user can
    // immediately see the spawn-rate change without waiting for the next tick.
    triggerBurst(n) {
      const interval = this.config.interval || 500;
      for (let i = 0; i < n; i++) {
        setTimeout(() => this.spawn(), i * Math.min(120, interval / 2));
      }
    }
    destroy() {
      this.cancel();
      // Yank any still-alive particles so we don't leave stale DOM nodes if
      // the state changes mid-animation. (Web Animations API onfinish callbacks
      // fire on cleanup naturally, but we don't want to wait.)
      this.alive.forEach(p => { if (p.parentNode) p.parentNode.removeChild(p); });
      this.alive.clear();
      if (this.layer && this.layer.parentNode) this.layer.parentNode.removeChild(this.layer);
    }
    spawn() {
      if (!this.templates.length) return;
      const tpl = this.templates[Math.floor(Math.random() * this.templates.length)];

      // Clone the template and strip ids on the clone subtree to avoid id collisions.
      const clone = tpl.el.cloneNode(true);
      if (clone.hasAttribute("id")) clone.removeAttribute("id");
      clone.querySelectorAll && clone.querySelectorAll("[id]").forEach(c => c.removeAttribute("id"));
      // The cloned template might inherit opacity 0 from its hidden template.
      // Force it visible so our wrapper opacity controls visibility.
      clone.style.opacity = "1";

      // Random spawn position. Two shapes supported:
      //   spawnArc — polar, used for "around a feature" emergence
      //   spawnArea — rect, used for general scatter
      let x, y;
      if (this.config.spawnArc) {
        const arc = this.config.spawnArc;
        const [aMin, aMax] = arc.angle || [180, 360];
        const [rMin, rMax] = arc.radius || [40, 60];
        const [cx, cy] = arc.center || [0, 0];
        const angDeg = aMin + Math.random() * (aMax - aMin);
        const ang = angDeg * Math.PI / 180;
        const r = rMin + Math.random() * (rMax - rMin);
        x = cx + r * Math.cos(ang);
        y = cy + r * Math.sin(ang);
      } else {
        const sa = this.config.spawnArea || { x: [40, 250], y: [60, 220] };
        x = sa.x[0] + Math.random() * (sa.x[1] - sa.x[0]);
        y = sa.y[0] + Math.random() * (sa.y[1] - sa.y[0]);
      }

      // Random drift target
      const dr = this.config.drift || { x: [-25, 25], y: [-80, -40] };
      const dx = dr.x[0] + Math.random() * (dr.x[1] - dr.x[0]);
      const dy = dr.y[0] + Math.random() * (dr.y[1] - dr.y[0]);

      const sRange = this.config.scaleRange || [0.6, 1.0];
      const sFrom = sRange[0], sTo = sRange[1];
      const rotJit = this.config.rotationJitter !== undefined ? this.config.rotationJitter : 15;
      const rotEnd = (Math.random() - 0.5) * 2 * rotJit;

      const baseDur = this.config.duration || 3000;
      const durJit = this.config.durationJitter !== undefined ? this.config.durationJitter : 600;
      const duration = baseDur + (Math.random() - 0.5) * 2 * durJit;

      // Position math: template has its own coords (cx, cy etc.). Wrapping in
      // a <g> and applying translate(x - tplCx, y - tplCy) shifts the visible
      // center to (x, y). Setting transform-origin to (tplCx, tplCy) means
      // scale/rotate happen around the template's own center, so the visible
      // particle scales/rotates around (x, y) after translation. See engine
      // comments on rotate-around-point for the same pattern.
      const tplCx = tpl.bbox.x + tpl.bbox.width / 2;
      const tplCy = tpl.bbox.y + tpl.bbox.height / 2;
      const dxOff = x - tplCx;
      const dyOff = y - tplCy;

      const wrapper = document.createElementNS("http://www.w3.org/2000/svg", "g");
      wrapper.appendChild(clone);
      wrapper.style.transformOrigin = `${tplCx}px ${tplCy}px`;
      this.layer.appendChild(wrapper);
      this.alive.add(wrapper);

      // Four-keyframe animation. Curve: fade in fast, hold, fade out as the
      // particle drifts. Matches the floatUp / soloFloat pattern in the
      // guitar widget but tuned to be gentler for a happy decoration.
      const anim = wrapper.animate([
        { transform: `translate(${dxOff}px, ${dyOff}px) scale(${sFrom * 0.4}) rotate(0deg)`,
          opacity: 0, offset: 0 },
        { transform: `translate(${dxOff + dx * 0.2}px, ${dyOff + dy * 0.2}px) scale(${sTo}) rotate(${rotEnd * 0.25}deg)`,
          opacity: 1, offset: 0.18 },
        { transform: `translate(${dxOff + dx * 0.6}px, ${dyOff + dy * 0.6}px) scale(${(sFrom + sTo) / 2}) rotate(${rotEnd * 0.7}deg)`,
          opacity: 0.85, offset: 0.65 },
        { transform: `translate(${dxOff + dx}px, ${dyOff + dy}px) scale(${sFrom * 0.7}) rotate(${rotEnd}deg)`,
          opacity: 0, offset: 1 },
      ], {
        duration: duration,
        easing: "cubic-bezier(0.25, 0.46, 0.45, 0.94)", // ease-out-quart-ish
        fill: "forwards",
      });

      anim.onfinish = () => {
        if (wrapper.parentNode) wrapper.parentNode.removeChild(wrapper);
        this.alive.delete(wrapper);
      };
      anim.oncancel = anim.onfinish;
    }
  }

  window.MorphEngine = {
    STATES, PRESETS, easeFns, cubicBezierEase, EASE_BEZIER,
    ALL_STATE_NAMES, SHARED_IDS, STRATEGY, DETECTED_STRATEGY,
    OVERRIDES, OVERRIDES_KEY,
    MULTI_SUBPATH_IDS, RIGID_PARAMS,
    getPathDOf, cssEscape, splitSubpaths, structureFingerprint,
    sortByAnatomy, parsePath, computePathBBox, estimateRigidFromDs,
    runTransformTween, runMorphTween, tweenStyle, runRigidTween,
    runCrossfadeTween, runScaleTween, runFillTween, isFlatColor,
    computeRigidParams,
    IdleAnimator, ParticleSystem,
  };
})();
