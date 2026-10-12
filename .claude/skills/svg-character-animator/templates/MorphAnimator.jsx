/**
 * MorphAnimator.jsx — canonical reference template
 *
 * This is the architecture the agent should produce when invoked. Adapt the
 * STATES, idle preset assignments, and orphan content to match the user's
 * actual SVG inputs.
 *
 * Architecture:
 *   - Per-path strategy detection (TRANSFORM or MORPH only — see detectStrategy comment)
 *   - Path normalization (H/V → L, primitives → bezier) before fingerprinting
 *   - Transform attribute interpolated alongside `d`
 *   - Multi-subpath splitting at render time
 *   - Shared paths rendered once, never replaced by React; mutations via refs only
 *   - All states' defs always rendered (gradients resolve regardless of current state)
 *   - Orphans rendered verbatim from source SVGs, fade in/out per state
 *   - Fill differences across states snap at morph end (no crossfade)
 *   - Persistent idle animator with amplitude blending (40% ramp, 0.1 min)
 *   - Bottom-center pivot for all rotation/scale idles
 *
 * Required imports:
 *   - react
 *   - flubber (MIT, default morph library)
 *   - gsap (MIT base library, optional — could use plain rAF if user prefers no deps)
 *
 * Optional:
 *   - @gsap/react (for useGSAP hook)
 */

import React, { useRef, useState, useEffect, useImperativeHandle, forwardRef } from "react";
import * as flubber from "flubber";

// ============================================================
// PRESET LIBRARY (importable from assets/preset-library.json)
// ============================================================

const PRESETS = {
  morph: {
    easing: {
      snappy:  { ease: "easeOutCubic",  duration: 400 },
      gentle:  { ease: "easeInOutQuad", duration: 1200 },
      bouncy:  { ease: "easeOutBack",   duration: 800 },
      dreamy:  { ease: "easeInOutSine", duration: 2500 },
    },
    scenario: {
      "icon-toggle":             { stagger: 0 },
      "page-transition":         { stagger: 30 },
      "character-emotion-shift": { stagger: 50 },
      "ambient-loop":            { stagger: 100 },
    },
    aesthetic: {
      none:     {},
      playful:  { easeOverride: "easeOutBack" },
      vintage:  { durationMultiplier: 1.5 },
      floating: {},
    },
  },
};

// ============================================================
// EASING FUNCTIONS
// ============================================================

const easeFns = {
  linear: t => t,
  easeOutCubic: t => 1 - Math.pow(1 - t, 3),
  easeInOutQuad: t => t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2,
  easeInOutSine: t => -(Math.cos(Math.PI * t) - 1) / 2,
  easeOutBack: t => {
    const c1 = 1.70158; const c3 = c1 + 1;
    return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
  },
};

// ============================================================
// PATH PARSING + NORMALIZATION (see references/path-normalization.md)
// ============================================================

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
    } else { i++; }
    lastCmd = cmd;
    const isAbs = cmd === cmd.toUpperCase();
    const pts = [];
    const consumeXY = () => {
      let x = parseFloat(tokens[i++]), y = parseFloat(tokens[i++]);
      if (!isAbs) { x += cur[0]; y += cur[1]; }
      return [x, y];
    };
    let normalizedCmd = cmd.toUpperCase();
    switch (normalizedCmd) {
      case 'M':
        cur = consumeXY(); pts.push([...cur]); startSubpath = [...cur]; break;
      case 'L':
        cur = consumeXY(); pts.push([...cur]); break;
      case 'H': {
        let x = parseFloat(tokens[i++]); if (!isAbs) x += cur[0];
        cur = [x, cur[1]]; pts.push([...cur]); normalizedCmd = 'L'; break;
      }
      case 'V': {
        let y = parseFloat(tokens[i++]); if (!isAbs) y += cur[1];
        cur = [cur[0], y]; pts.push([...cur]); normalizedCmd = 'L'; break;
      }
      case 'C': {
        const c1 = consumeXY(), c2 = consumeXY(), end = consumeXY();
        pts.push(c1, c2, end); cur = end; break;
      }
      case 'Q': {
        const c1 = consumeXY(), end = consumeXY();
        pts.push(c1, end); cur = end; break;
      }
      case 'Z': cur = [...startSubpath]; break;
    }
    segments.push({ cmd: normalizedCmd, points: pts });
  }
  return segments;
}

function structureFingerprint(d) {
  const segs = parsePath(d);
  return segs ? segs.map(s => s.cmd).join('') : null;
}

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
      const x = segF.points[j][0] + (segT.points[j][0] - segF.points[j][0]) * t;
      const y = segF.points[j][1] + (segT.points[j][1] - segF.points[j][1]) * t;
      out += ` ${x.toFixed(3)} ${y.toFixed(3)}`;
    }
    out += ' ';
  }
  return out.trim();
}

// Convert primitives to bezier path data for uniform processing
const k = 0.5522847498;
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

function ellipseToPath(cx, cy, rx, ry) {
  return `M ${cx-rx} ${cy} C ${cx-rx} ${cy-ry*k}, ${cx-rx*k} ${cy-ry}, ${cx} ${cy-ry} ` +
         `C ${cx+rx*k} ${cy-ry}, ${cx+rx} ${cy-ry*k}, ${cx+rx} ${cy} ` +
         `C ${cx+rx} ${cy+ry*k}, ${cx+rx*k} ${cy+ry}, ${cx} ${cy+ry} ` +
         `C ${cx-rx*k} ${cy+ry}, ${cx-rx} ${cy+ry*k}, ${cx-rx} ${cy} Z`;
}
function getPathDOf(p) {
  if (p.tag === "circle")  return ellipseToPath(+p.cx, +p.cy, +p.r, +p.r);
  if (p.tag === "ellipse") return ellipseToPath(+p.cx, +p.cy, +p.rx, +p.ry);
  if (p.tag === "rect")    return rectToPath(p.x, p.y, p.width, p.height, p.rx, p.ry);
  return p.d;
}

// ============================================================
// TRANSFORM ATTRIBUTE INTERPOLATION (see references/transform-interpolation.md)
// ============================================================

// Parse a transform attribute into an ordered list of ops.
// Supports rotate / translate / scale / matrix. skewX/skewY parse but resolve
// to identity when composed (rarely needed; matrix is the escape hatch for
// arbitrary shears or Figma-exported affines).
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

// Each op → 6-element SVG matrix [a, b, c, d, e, f] where
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
      const deg = args[0] || 0, cx = args[1] || 0, cy = args[2] || 0;
      const rad = deg * Math.PI / 180;
      const cs = Math.cos(rad), sn = Math.sin(rad);
      // rotate(deg cx cy) = translate(cx,cy) · rotate(deg) · translate(-cx,-cy)
      return [cs, sn, -sn, cs, cx - cs * cx + sn * cy, cy - sn * cx - cs * cy];
    }
    default:
      return [1, 0, 0, 1, 0, 0];
  }
}

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

// Collapse each side to a single 6-element matrix and lerp component-wise.
// Matrix lerp isn't a true rotation interpolator (the determinant dips slightly
// through the curve), but for the small rotation differences our morphs use
// (< 30°) the visual error is imperceptible — and this uniformly handles mixed
// inputs (matrix on one side, rotate on the other) which a per-component
// parser cannot.
const IDENTITY_MATRIX = [1, 0, 0, 1, 0, 0];
function interpolateTransform(from, to, t) {
  if (!from && !to) return null;
  const Mf = from ? opsToMatrix(from) : IDENTITY_MATRIX;
  const Mt = to ? opsToMatrix(to) : IDENTITY_MATRIX;
  const M = Mf.map((v, i) => v + (Mt[i] - v) * t);
  const isIdentity =
    Math.abs(M[0] - 1) < 1e-4 && Math.abs(M[1]) < 1e-4 &&
    Math.abs(M[2]) < 1e-4 && Math.abs(M[3] - 1) < 1e-4 &&
    Math.abs(M[4]) < 1e-4 && Math.abs(M[5]) < 1e-4;
  if (isIdentity) return null;
  return `matrix(${M.map(v => v.toFixed(4)).join(' ')})`;
}

// ============================================================
// SUBPATH HELPERS (see SKILL.md, "Multi-subpath splitting")
// ============================================================

function splitSubpaths(d) { return d.match(/[Mm][^Mm]*/g) || [d]; }
function cssEscape(id)    { return id.replace(/[^a-zA-Z0-9_-]/g, "_"); }

// ============================================================
// STRATEGY DETECTION (see references/strategy-detection.md)
// ============================================================

// Two strategies:
//   TRANSFORM — same command structure across states → linearly interpolate each
//               bezier control point. Preserves curves, strokes, line caps exactly.
//   MORPH     — different structure → hand `d` strings to flubber and let it
//               polygon-sample. Used as the fallback whenever TRANSFORM can't apply.
//
// Fill differences across states are NOT a strategy axis. If you need to swap a
// gradient between states, set the fill via setAttribute at the morph midpoint
// (snap), or normalize the source SVGs to use a single fill. Crossfade strategies
// were removed: the stacked-copy approach added complexity for marginal quality
// gain over a clean snap, and TRANSFORM_CROSSFADE was never fully implemented.
function detectStrategy(id, STATES) {
  const stateNames = Object.keys(STATES);
  const fps = stateNames.map(sn => {
    const p = STATES[sn].paths[id];
    if (!p) return null;
    return structureFingerprint(getPathDOf(p));
  });
  if (fps.some(f => f === null)) return "MORPH";
  return new Set(fps).size === 1 ? "TRANSFORM" : "MORPH";
}

// ============================================================
// TWEEN RUNNERS
// ============================================================

function runTransformTween({ target, fromD, toD, fromTransform, toTransform, durationMs, easeFn, delayMs = 0, onComplete }) {
  const fromXf = parseTransform(fromTransform);
  const toXf = parseTransform(toTransform);
  let cancelled = false;
  const begin = () => {
    const start = performance.now();
    const step = (now) => {
      if (cancelled) return;
      const t = Math.min(1, (now - start) / durationMs);
      const eased = easeFn(t);
      const d = interpolateStructuredPaths(fromD, toD, eased);
      if (d) target.setAttribute('d', d);
      if (fromXf || toXf) {
        const xf = interpolateTransform(fromXf, toXf, eased);
        if (xf) target.setAttribute('transform', xf);
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
  delayMs > 0 ? setTimeout(begin, delayMs) : begin();
  return { cancel: () => { cancelled = true; } };
}

function runMorphTween({ target, fromD, toD, durationMs, easeFn, delayMs = 0, onComplete, isSmall = false }) {
  let interpolator;
  try {
    interpolator = flubber.interpolate(fromD, toD, { maxSegmentLength: isSmall ? 0.5 : 2 });
  } catch (e) {
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
      target.setAttribute('d', interpolator(easeFn(t)));
      if (t < 1) requestAnimationFrame(step);
      else { target.setAttribute('d', toD); if (onComplete) onComplete(); }
    };
    requestAnimationFrame(step);
  };
  delayMs > 0 ? setTimeout(begin, delayMs) : begin();
  return { cancel: () => { cancelled = true; } };
}

function tweenStyle({ target, prop, from, to, durationMs, delayMs = 0, easeFn = easeFns.linear, onComplete }) {
  let cancelled = false;
  const begin = () => {
    const start = performance.now();
    const step = (now) => {
      if (cancelled) return;
      const t = Math.min(1, (now - start) / durationMs);
      target.style[prop] = String(from + (to - from) * easeFn(t));
      if (t < 1) requestAnimationFrame(step);
      else if (onComplete) onComplete();
    };
    requestAnimationFrame(step);
  };
  delayMs > 0 ? setTimeout(begin, delayMs) : begin();
  return { cancel: () => { cancelled = true; } };
}

// ============================================================
// IDLE ANIMATOR (see references/idle-animation-recipes.md)
// ============================================================

class IdleAnimator {
  constructor(svgEl, getKind, getAmplitude) {
    this.svgEl = svgEl;
    this.getKind = getKind;
    this.getAmplitude = getAmplitude;
    this.start = performance.now();
    this.cancelled = false;
    this.lastKind = null;
    this.twinkles = svgEl.querySelectorAll('[data-twinkle="true"]');
    this.twinklePhases = Array.from(this.twinkles).map(() => Math.random() * Math.PI * 2);
    requestAnimationFrame(this.tick.bind(this));
  }
  cancel() {
    this.cancelled = true;
    if (this.svgEl) this.svgEl.style.transform = '';
    if (this.twinkles) this.twinkles.forEach(el => { el.style.opacity = ''; el.style.transform = ''; });
  }
  tick(now) {
    if (this.cancelled) return;
    const t = (now - this.start) / 1000;
    const amp = this.getAmplitude();
    const kind = this.getKind();
    if (kind !== this.lastKind) { this.svgEl.style.transform = ''; this.lastKind = kind; }
    const BOTTOM_CENTER = "50% 100%";
    let transform = "";
    switch (kind) {
      case "sway":
        transform = `rotate(${2 * amp * Math.sin(t * 2 * Math.PI / 1.5)}deg)`;
        this.svgEl.style.transformOrigin = BOTTOM_CENTER; break;
      case "breathe":
        transform = `scale(${1 + 0.02 * amp * (0.5 + 0.5 * Math.sin(t * 2 * Math.PI / 2.0))})`;
        this.svgEl.style.transformOrigin = BOTTOM_CENTER; break;
      case "bob":
        transform = `translateY(${-3 * amp * (0.5 + 0.5 * Math.sin(t * 2 * Math.PI / 1.0))}px)`;
        this.svgEl.style.transformOrigin = BOTTOM_CENTER; break;
      case "shake":
        transform = `rotate(${1 * amp * Math.sin(t * 2 * Math.PI / 0.3)}deg)`;
        this.svgEl.style.transformOrigin = BOTTOM_CENTER; break;
      case "sway-twinkle": {
        transform = `rotate(${1.5 * amp * Math.sin(t * 2 * Math.PI / 1.8)}deg)`;
        this.svgEl.style.transformOrigin = BOTTOM_CENTER;
        this.twinkles.forEach((el, i) => {
          const phase = this.twinklePhases[i];
          const period = 0.6 + (i * 0.13) % 0.4;
          const v = 0.75 + 0.25 * amp * Math.sin(t * 2 * Math.PI / period + phase);
          const sc = 0.92 + 0.08 * amp * Math.sin(t * 2 * Math.PI / period + phase);
          el.style.opacity = String(v);
          el.style.transform = `scale(${sc})`;
          el.style.transformOrigin = "50% 50%";
        });
        break;
      }
      case "drift": {
        const dx = 5 * amp * Math.sin(t * 2 * Math.PI / 6.0);
        const dy = 5 * amp * Math.sin(t * 2 * Math.PI / 7.3);
        transform = `translate(${dx}px, ${dy}px)`;
        break;
      }
    }
    this.svgEl.style.transform = transform;
    requestAnimationFrame(this.tick.bind(this));
  }
}

// ============================================================
// INPUT DATA (replace this with the user's actual states)
// ============================================================

// Each state has:
//   - paths: { [id]: { tag, d?, cx?, cy?, r?, rx?, ry?, fill?, stroke?, ..., transform? } }
//     Mark orphan paths with _orphan: true. Use _layer: "back" for background orphans.
//   - defs: SVG <defs> contents (gradients) — string
//   - idle: idle preset name ("sway", "breathe", "bob", "shake", "twinkle", "sway-twinkle", "drift")
//   - orphanSVG (optional): inline SVG for foreground orphan groups (companions, flowers)

const STATES = {
  "state-1": {
    paths: {
      // shared
      body: { tag: "path", d: "M...", fill: "url(#grad1)" },
      head: { tag: "circle", cx: "155", cy: "158", r: "48" },
      // ... orphans
    },
    defs: `<radialGradient id="grad1">...</radialGradient>`,
    idle: "sway",
  },
  // state-2, state-3, ...
};

// ============================================================
// COMPONENT SETUP — these are computed once at module load
// ============================================================

const ALL_STATE_NAMES = Object.keys(STATES);

const SHARED_IDS = (() => {
  const sets = ALL_STATE_NAMES.map(s => new Set(Object.keys(STATES[s].paths)));
  const intersection = [...sets[0]].filter(id => sets.every(s => s.has(id)));
  return intersection.filter(id => !ALL_STATE_NAMES.some(s => STATES[s].paths[id]?._orphan));
})();

const STRATEGY = {};
SHARED_IDS.forEach(id => { STRATEGY[id] = detectStrategy(id, STATES); });

const ANATOMY_ORDER = ["eye", "nose", "mouth", "button", "head", "body", "hand"];
const sortByAnatomy = (ids) => [...ids].sort((a, b) => {
  const score = (id) => {
    for (let i = 0; i < ANATOMY_ORDER.length; i++) {
      if (id.toLowerCase().startsWith(ANATOMY_ORDER[i])) return i;
    }
    return ANATOMY_ORDER.length;
  };
  return score(a) - score(b);
});

// ============================================================
// RENDER HELPERS
// ============================================================

function renderInitialElement(domId, p) {
  const d = getPathDOf(p);
  // Strip primitive-specific attrs so they don't leak onto the <path> we render.
  const { tag, cx, cy, r, rx, ry, x, y, width, height, _orphan, _layer, ...rest } = p;
  const subs = splitSubpaths(d);
  if (subs.length > 1) {
    return (
      <g key={domId} id={domId} data-multi="true">
        {subs.map((sub, i) => (
          <path key={i} id={`${domId}__sub_${i}`} d={sub} {...rest} />
        ))}
      </g>
    );
  }
  return <path key={domId} id={domId} d={d} {...rest} />;
}

// ============================================================
// THE COMPONENT
// ============================================================

const MorphAnimator = forwardRef(function MorphAnimator({
  initialState = ALL_STATE_NAMES[0],
  morphPreset = { easing: "gentle", scenario: "icon-toggle", aesthetic: "none" },
  width = 290, height = 310,
}, ref) {
  const svgRef = useRef(null);
  const currentStateRef = useRef(initialState);
  const idleAmplitudeRef = useRef(1.0);
  const idleAnimatorRef = useRef(null);
  const activeMorphsRef = useRef([]);
  const presetRef = useRef(morphPreset);
  presetRef.current = morphPreset;
  const [, forceRender] = useState(0);

  const cancelMorphs = () => {
    activeMorphsRef.current.forEach(h => h?.cancel?.());
    activeMorphsRef.current = [];
  };

  const runTransition = (toStateName) => {
    if (toStateName === currentStateRef.current) return;
    cancelMorphs();

    const cfg = presetRef.current;
    const easingCfg   = PRESETS.morph.easing[cfg.easing]       || PRESETS.morph.easing.gentle;
    const scenarioCfg = PRESETS.morph.scenario[cfg.scenario]   || PRESETS.morph.scenario["icon-toggle"];
    const aestheticCfg = PRESETS.morph.aesthetic[cfg.aesthetic] || PRESETS.morph.aesthetic.none;
    const easeName = aestheticCfg.easeOverride || easingCfg.ease;
    const easeFn = easeFns[easeName] || easeFns.easeInOutQuad;
    const durationMs = easingCfg.duration * (aestheticCfg.durationMultiplier || 1);

    const fromState = currentStateRef.current;
    const fromPaths = STATES[fromState].paths;
    const toPaths = STATES[toStateName].paths;

    // Idle ramp-down: 40% duration, target 0.1, sine in/out
    const rampDownDur = durationMs * 0.4;
    const rampDownStart = performance.now();
    const rampDownFrom = idleAmplitudeRef.current;
    const rampDownStep = (now) => {
      const t = Math.min(1, (now - rampDownStart) / rampDownDur);
      idleAmplitudeRef.current = rampDownFrom + (0.1 - rampDownFrom) * easeFns.easeInOutSine(t);
      if (t < 1) requestAnimationFrame(rampDownStep);
    };
    requestAnimationFrame(rampDownStep);

    let morphsRemaining = 0, morphsCompleted = 0;
    const onMorphComplete = () => {
      morphsCompleted++;
      if (morphsCompleted >= morphsRemaining) {
        currentStateRef.current = toStateName;
        forceRender(n => n + 1);
        // Idle ramp-up
        const rampUpDur = durationMs * 0.4;
        const rampUpStart = performance.now();
        const rampUpFrom = idleAmplitudeRef.current;
        const rampUpStep = (now) => {
          const t = Math.min(1, (now - rampUpStart) / rampUpDur);
          idleAmplitudeRef.current = rampUpFrom + (1.0 - rampUpFrom) * easeFns.easeInOutSine(t);
          if (t < 1) requestAnimationFrame(rampUpStep);
        };
        requestAnimationFrame(rampUpStep);
      }
    };

    const sharedSorted = sortByAnatomy(SHARED_IDS);
    sharedSorted.forEach((id, i) => {
      const fromPath = fromPaths[id], toPath = toPaths[id];
      if (!fromPath || !toPath) return;
      const strategy = STRATEGY[id];
      const fromD = getPathDOf(fromPath);
      const toD = getPathDOf(toPath);
      const offset = i * (scenarioCfg.stagger || 0);

      // Multi-subpath handling
      const fromParts = splitSubpaths(fromD);
      const toParts = splitSubpaths(toD);
      if (fromParts.length > 1 || toParts.length > 1) {
        const minCount = Math.min(fromParts.length, toParts.length);
        for (let s = 0; s < minCount; s++) {
          const sub = svgRef.current.querySelector(`#path-${id}__sub_${s}`);
          if (!sub) continue;
          morphsRemaining++;
          if (strategy === "TRANSFORM" && structureFingerprint(fromParts[s]) === structureFingerprint(toParts[s])) {
            activeMorphsRef.current.push(runTransformTween({
              target: sub, fromD: fromParts[s], toD: toParts[s],
              fromTransform: fromPath.transform || null, toTransform: toPath.transform || null,
              durationMs, easeFn, delayMs: offset, onComplete: onMorphComplete
            }));
          } else {
            activeMorphsRef.current.push(runMorphTween({
              target: sub, fromD: fromParts[s], toD: toParts[s],
              durationMs, easeFn, delayMs: offset, onComplete: onMorphComplete
            }));
          }
        }
        // Handle subpath count mismatch with opacity fade
        for (let s = minCount; s < fromParts.length; s++) {
          const sub = svgRef.current.querySelector(`#path-${id}__sub_${s}`);
          if (sub) tweenStyle({ target: sub, prop: "opacity", from: 1, to: 0,
            durationMs: durationMs * 0.5, delayMs: offset, easeFn });
        }
        for (let s = minCount; s < toParts.length; s++) {
          const sub = svgRef.current.querySelector(`#path-${id}__sub_${s}`);
          if (sub) {
            sub.style.opacity = "0";
            tweenStyle({ target: sub, prop: "opacity", from: 0, to: 1,
              durationMs: durationMs * 0.5, delayMs: offset + durationMs * 0.5, easeFn });
          }
        }
        return;
      }

      // Single-subpath handling
      const target = svgRef.current.querySelector(`#path-${id}`);
      if (!target) return;
      morphsRemaining++;
      const isSmall = ["eyel", "eyer", "button1", "button2"].includes(id);
      if (strategy === "TRANSFORM") {
        activeMorphsRef.current.push(runTransformTween({
          target, fromD, toD,
          fromTransform: fromPath.transform || null, toTransform: toPath.transform || null,
          durationMs, easeFn, delayMs: offset, onComplete: onMorphComplete
        }));
      } else {
        activeMorphsRef.current.push(runMorphTween({
          target, fromD, toD,
          durationMs, easeFn, delayMs: offset, onComplete: onMorphComplete, isSmall
        }));
      }
      // If fills differ across states, snap the destination fill at completion
      // (no smooth crossfade — see comment on detectStrategy).
      if (fromPath.fill && toPath.fill && fromPath.fill !== toPath.fill) {
        setTimeout(() => { target.setAttribute("fill", toPath.fill); }, durationMs + offset);
      }
    });

    // Orphan fade out/in
    ALL_STATE_NAMES.forEach(sn => {
      const orphans = Object.keys(STATES[sn].paths).filter(id => !SHARED_IDS.includes(id));
      orphans.forEach(id => {
        const t = svgRef.current.querySelector(`#orphan-${cssEscape(id)}-${sn}`);
        if (t) t.style.opacity = sn === fromState ? "1" : "0";
      });
      if (STATES[sn].orphanSVG) {
        const grp = svgRef.current.querySelector(`#orphan-group-${sn}`);
        if (grp) grp.style.opacity = sn === fromState ? "1" : "0";
      }
    });

    const fromOrphanIds = Object.keys(fromPaths).filter(id => !SHARED_IDS.includes(id));
    const toOrphanIds = Object.keys(toPaths).filter(id => !SHARED_IDS.includes(id));
    fromOrphanIds.forEach(id => {
      const t = svgRef.current.querySelector(`#orphan-${cssEscape(id)}-${fromState}`);
      if (t) tweenStyle({ target: t, prop: "opacity", from: 1, to: 0,
        durationMs: durationMs * 0.4, easeFn: easeFns.easeInOutSine });
    });
    if (STATES[fromState].orphanSVG) {
      const grp = svgRef.current.querySelector(`#orphan-group-${fromState}`);
      if (grp) tweenStyle({ target: grp, prop: "opacity", from: 1, to: 0,
        durationMs: durationMs * 0.4, easeFn: easeFns.easeInOutSine });
    }
    toOrphanIds.forEach(id => {
      const t = svgRef.current.querySelector(`#orphan-${cssEscape(id)}-${toStateName}`);
      if (t) tweenStyle({ target: t, prop: "opacity", from: 0, to: 1,
        durationMs: durationMs * 0.4, delayMs: durationMs * 0.5, easeFn: easeFns.easeOutBack });
    });
    if (STATES[toStateName].orphanSVG) {
      const grp = svgRef.current.querySelector(`#orphan-group-${toStateName}`);
      if (grp) tweenStyle({ target: grp, prop: "opacity", from: 0, to: 1,
        durationMs: durationMs * 0.4, delayMs: durationMs * 0.5, easeFn: easeFns.easeOutBack });
    }

    if (morphsRemaining === 0) {
      setTimeout(() => { currentStateRef.current = toStateName; forceRender(n => n + 1); }, durationMs);
    }
  };

  useImperativeHandle(ref, () => ({
    transitionTo: runTransition,
    getCurrentState: () => currentStateRef.current,
  }));

  useEffect(() => {
    if (!svgRef.current) return;
    if (idleAnimatorRef.current) idleAnimatorRef.current.cancel();
    svgRef.current.style.transform = "";
    idleAnimatorRef.current = new IdleAnimator(
      svgRef.current,
      () => STATES[currentStateRef.current].idle,
      () => idleAmplitudeRef.current
    );
    return () => { idleAnimatorRef.current?.cancel(); };
  }, []);

  // All states' defs always rendered so gradient references resolve regardless of current state
  const allDefs = ALL_STATE_NAMES.map(s => STATES[s].defs).filter(Boolean).join("\n");
  const initStateName = currentStateRef.current;

  return (
    <svg ref={svgRef} width={width} height={height} viewBox="0 0 290 310" xmlns="http://www.w3.org/2000/svg">
      <defs dangerouslySetInnerHTML={{ __html: allDefs }} />

      {/* Back-layer orphans from ALL states */}
      {ALL_STATE_NAMES.flatMap(sn =>
        Object.entries(STATES[sn].paths)
          .filter(([, p]) => p._orphan && p._layer === "back")
          .map(([id, p]) => {
            const el = renderInitialElement(`orphan-${cssEscape(id)}-${sn}`, p);
            return React.cloneElement(el, {
              key: `${sn}-${id}`,
              style: { opacity: sn === initStateName ? 1 : 0 }
            });
          })
      )}

      {/* Shared paths — rendered once from the initial state, never replaced by React.
          After mount, the `d` attribute is mutated imperatively via setAttribute on
          refs (see runTransition). Fill mismatch across states is snapped at the
          end of each morph rather than crossfaded. */}
      {SHARED_IDS.flatMap(id => {
        const p = STATES[initStateName].paths[id];
        return p ? [renderInitialElement(`path-${id}`, p)] : [];
      })}

      {/* Front-layer orphan paths — rendered in front of shared paths but behind
          the verbatim orphanSVG groups. Default for _orphan: true entries that
          don't specify _layer (set _layer: "back" to push behind shared paths).
          Same id format as back-layer orphans so the transition fade logic finds them. */}
      {ALL_STATE_NAMES.flatMap(sn =>
        Object.entries(STATES[sn].paths)
          .filter(([, p]) => p._orphan && p._layer !== "back")
          .map(([id, p]) => {
            const el = renderInitialElement(`orphan-${cssEscape(id)}-${sn}`, p);
            return React.cloneElement(el, {
              key: `${sn}-${id}`,
              style: { opacity: sn === initStateName ? 1 : 0 }
            });
          })
      )}

      {/* Foreground orphan groups */}
      {ALL_STATE_NAMES.map(sn => {
        if (!STATES[sn].orphanSVG) return null;
        return (
          <g key={sn} id={`orphan-group-${sn}`}
             style={{ opacity: sn === initStateName ? 1 : 0 }}
             dangerouslySetInnerHTML={{ __html: STATES[sn].orphanSVG }} />
        );
      })}
    </svg>
  );
});

export default MorphAnimator;

// Named exports used by the demo wrapper (App.jsx):
//   STATE_NAMES        — array of state names, in declaration order. Source for the state-button row.
//   STRATEGY_DEBUG     — { [id]: "TRANSFORM" | "MORPH" } for the strategy panel.
//   SHARED_IDS_DEBUG   — list of ids that morph across states (excludes orphans).
export const STATE_NAMES = ALL_STATE_NAMES;
export const STRATEGY_DEBUG = STRATEGY;
export const SHARED_IDS_DEBUG = SHARED_IDS;
