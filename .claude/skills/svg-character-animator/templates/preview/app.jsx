// React app for the SVG morph-animator preview shell.
// Mounts to #root. Consumes window.MorphEngine and window.STATES_DATA.
// Renders the redesigned shell: header stat strip, sticky controls panel,
// canvas card with background swatch, collapsible strategy panel.

const { useRef, useState, useEffect, useImperativeHandle, forwardRef } = React;
const E = window.MorphEngine;
const {
  STATES, PRESETS, easeFns, cubicBezierEase, EASE_BEZIER,
  ALL_STATE_NAMES, SHARED_IDS, STRATEGY, DETECTED_STRATEGY,
  OVERRIDES, OVERRIDES_KEY,
  MULTI_SUBPATH_IDS, RIGID_PARAMS,
  getPathDOf, cssEscape, splitSubpaths, computePathBBox, estimateRigidFromDs,
  structureFingerprint, sortByAnatomy, parsePath,
  runTransformTween, runMorphTween, tweenStyle, runRigidTween,
  runCrossfadeTween, runScaleTween, runFillTween, isFlatColor,
  IdleAnimator, ParticleSystem,
} = E;
// Quick lookup — is this id one of the multi-subpath rigid-body ones?
const RIGID_ID_SET = new Set(MULTI_SUBPATH_IDS || []);

// Union of every path id across states (shared + orphans), in first-seen order.
const ALL_PATH_IDS = (() => {
  const seen = [];
  ALL_STATE_NAMES.forEach(sn => Object.keys(STATES[sn].paths).forEach(id => {
    if (!seen.includes(id)) seen.push(id);
  }));
  return seen;
})();
// Reverse of cssEscape for orphan DOM ids (orphan-<escaped>-<state>).
const ESC_TO_ID = (() => {
  const map = {};
  ALL_PATH_IDS.forEach(id => { map[cssEscape(id)] = id; });
  return map;
})();

// Map a clicked DOM element's id back to the logical path id, or null when the
// element isn't part of the editable path set (overlay children, verbatim
// orphanSVG internals, the svg itself).
function domIdToLogicalId(domId) {
  if (!domId) return null;
  let m = domId.match(/^path-(.+?)(?:__sub_\d+)?(?:-rigid)?$/);
  if (m) return ESC_TO_ID[m[1]] || m[1];
  m = domId.match(/^orphan-(.+)$/);
  if (m) {
    for (const sn of ALL_STATE_NAMES) {
      if (m[1].endsWith(`-${sn}`)) {
        const esc = m[1].slice(0, -(sn.length + 1));
        return ESC_TO_ID[esc] || esc;
      }
    }
  }
  return null;
}

// Persist the editor's overrides (roles / methods / durationMs). The engine
// reads this at init (see OVERRIDES in engine.jsx); method changes ALSO apply
// live by mutating STRATEGY, so persistence is only for reloads + web export.
function persistOverrides(partial) {
  Object.assign(OVERRIDES, partial);
  try { localStorage.setItem(OVERRIDES_KEY, JSON.stringify(OVERRIDES)); } catch (e) { /* private mode */ }
}

const VIEWBOX = window.PREVIEW_CONFIG?.viewBox || "0 0 290 310";
const CANVAS_SIZE = window.PREVIEW_CONFIG?.size || { width: 290, height: 310 };
const TITLE = window.PREVIEW_CONFIG?.title || "MorphAnimator Preview";
const SUBTITLE = window.PREVIEW_CONFIG?.subtitle || "SVG state-machine animation testbed";
// Optional one-shot overlays a states file can declare: decoration artwork
// (`emotions`), the `talk` / `lookAround` eye transients, and `gestures` — named
// play-once face transients (blink / look-around / look-up) that need no extra
// artwork. Every key is optional; when OVERLAYS_DATA is absent (critters, …) the
// overlay UI/render is skipped entirely, so this is fully backwards-compatible.
const OVERLAYS = window.OVERLAYS_DATA || null;
const OVERLAY_EMOTIONS = (OVERLAYS && OVERLAYS.emotions) || [];
const OVERLAY_GESTURES = (OVERLAYS && OVERLAYS.gestures) || [];
// A gesture with no `enabledStates` plays from anywhere.
const gestureEnabled = (g, state) => !g.enabledStates || g.enabledStates.includes(state);

function renderInitialElement(domId, p, ctrl) {
  const d = getPathDOf(p);
  // Strip primitive-specific attrs so they don't leak onto the <path> we render.
  const { tag, cx, cy, r, rx, ry, x, y, width, height, _orphan, _layer, _syncGroup, _idleOwned, _group, ...rest } = p;
  const subs = splitSubpaths(d);
  // `ctrl` (orphan opacity control) MUST land on the element carrying id=domId —
  // the one the morph engine and idle loops query (`#orphan-<id>-<state>`) — not
  // the outer `-rigid` wrapper. Otherwise a wrapper opacity:0 would mask the
  // inner opacity the idle sets, leaving multi-subpath orphans invisible.
  const ctrlProps = ctrl
    ? { "data-target-opacity": ctrl.dataTargetOpacity, style: ctrl.style }
    : {};
  if (subs.length > 1) {
    // Multi-subpath shared paths get an OUTER rigid-transform wrapper so the
    // morph engine can apply translate+rotate on `<g id="<id>-rigid">` without
    // colliding with the IDLE animator's transform on `<g id="<id>">`.
    // Single-subpath paths don't need this — they go through runTransformTween
    // which mutates `d` directly, no transform involved.
    return (
      <g key={`${domId}-rigid`} id={`${domId}-rigid`}>
        <g id={domId} data-multi="true" {...ctrlProps}>
          {subs.map((sub, i) => (
            <path key={i} id={`${domId}__sub_${i}`} d={sub} {...rest} />
          ))}
        </g>
      </g>
    );
  }
  const singleStyle = ctrl ? { ...(rest.style || {}), ...ctrl.style } : rest.style;
  return <path key={domId} id={domId} d={d} {...rest} style={singleStyle} {...(ctrl ? { "data-target-opacity": ctrl.dataTargetOpacity } : {})} />;
}

const MorphAnimator = forwardRef(function MorphAnimator(
  { initialState, morphPreset, width, height, onPickPath }, ref
) {
  const svgRef = useRef(null);
  const currentStateRef = useRef(initialState);
  // Track the most-recently-requested target state, separately from the
  // displayed state. Updated synchronously on every transitionTo() call so
  // we can dedupe rapid same-target clicks without blocking redirects to a
  // different target while a morph is still in flight.
  const targetStateRef = useRef(initialState);
  const idleAmplitudeRef = useRef(1.0);
  const idleAnimatorRef = useRef(null);
  const particleSystemRef = useRef(null);
  const orphanPopLoopRef = useRef(null);
  // In-flight one-shot emotion overlays, keyed by name, so a re-click restarts
  // cleanly instead of stacking rAF loops.
  const overlayHandlesRef = useRef({});
  // Which idle config the IdleAnimator should currently run. Decoupled from
  // currentStateRef so the DESTINATION idle can fade in during the morph tail —
  // committing currentStateRef early would re-render (snap) the morphing paths.
  // Idle preset override — replaces every state's authored idle with a
  // simple whole-body preset ("breathe", "waggle-sequence", …) or silences
  // it ("none"). null = play each state's authored idle. Persisted via
  // OVERRIDES.idleOverride, editable live from the Idle card.
  const idleOverrideRef = useRef(OVERRIDES.idleOverride || null);
  const idleConfigRef = useRef(idleOverrideRef.current || STATES[initialState].idle);
  // Idle anchor override — transform-origin for whole-body idle parts.
  // null = each part's own default (bottom-center per the skill). Persisted
  // via OVERRIDES.idleAnchor and editable live from the Anchor card.
  const idleAnchorRef = useRef(OVERRIDES.idleAnchor || null);
  // The current idle-amplitude/idle-swap rAF controller (cancellable on redirect).
  const ampCtrlRef = useRef(null);
  const [, forceRender] = useState(0);
  const activeMorphsRef = useRef([]);
  const presetRef = useRef(morphPreset);
  presetRef.current = morphPreset;

  const cancelMorphs = () => {
    activeMorphsRef.current.forEach(h => { if (h && h.cancel) h.cancel(); });
    activeMorphsRef.current = [];
  };

  // Looping pop-in/pop-out for a state's orphan decorations (state-5 stars).
  // The appear phase reuses the SAME curve as the transition orphan "pop"
  // entrance (popIn below): scale 0.3→1 on easeOutBack with opacity ramping
  // faster than scale. Because orphans render with transform-box: view-box and
  // origin 50% 50%, each star grows out from the view-box center — matching how
  // the stars enter the state.
  //
  // The disappear phase drifts each star OUTWARD while shrinking it, so old
  // stars fly off into the distance as new ones pop in. Outward distance and
  // size are coupled under a single uniform scale about the view-box center
  // (scale>1 = further AND bigger), so we decouple them: translate the star
  // along its own radial direction (away from the view-box center) and scale it
  // DOWN about its own center. Cycle: appear → hold → disappear → rest → repeat.
  const startOrphanPopLoop = (svgEl, stateName, cfg) => {
    let cancelled = false;
    let handles = [];
    const cancelHandles = () => { handles.forEach(h => h && h.cancel && h.cancel()); handles = []; };
    const els = cfg.ids.map(id => svgEl.querySelector(`#orphan-${cssEscape(id)}-${stateName}`)).filter(Boolean);
    if (!els.length) return { cancel: () => {} };

    const popDur  = cfg.popDuration || 360;  // appear duration (matches entrance pop)
    const stagger = cfg.stagger     || 70;   // per-star delay so they pop in sequence
    const holdMs  = cfg.holdMs      || 900;  // visible dwell
    const fadeMs  = cfg.fadeMs      || 300;  // disappear duration
    const restMs  = cfg.restMs      || 450;  // empty gap before the next pop
    const travel  = cfg.travel   != null ? cfg.travel   : 0.55; // outward drift, as a fraction of each star's radius from center
    const endScale = cfg.endScale != null ? cfg.endScale : 0.4;  // shrink target as it flies off

    // View-box center + per-star geometry (own center, radial vector from the
    // center), measured once. getBBox returns view-box-space coords because the
    // orphans render directly in that space (same reason origin 50% 50% works).
    const vb = svgEl.viewBox && svgEl.viewBox.baseVal;
    const vcx = vb && vb.width  ? vb.x + vb.width  / 2 : 145;
    const vcy = vb && vb.height ? vb.y + vb.height / 2 : 155;
    const geomOf = new Map();
    els.forEach(el => {
      let b = null;
      try { b = el.getBBox(); } catch (e) { /* not rendered */ }
      if (b && (b.width || b.height)) {
        const cx = b.x + b.width / 2, cy = b.y + b.height / 2;
        geomOf.set(el, { cx, cy, ox: cx - vcx, oy: cy - vcy });
      } else {
        geomOf.set(el, { cx: vcx, cy: vcy, ox: 0, oy: 0 });
      }
    });

    const maxOpOf = el => parseFloat(el.dataset.targetOpacity) || 1;

    const appear = (el) => {
      const maxOp = maxOpOf(el);
      const start = performance.now();
      el.style.transformOrigin = "50% 50%";
      el.style.opacity = "0";
      el.style.transform = "scale(0.3)";
      const step = (now) => {
        if (cancelled) return;
        const t = Math.min(1, (now - start) / popDur);
        el.style.opacity = String(Math.min(maxOp, t * 1.6 * maxOp));
        el.style.transform = `scale(${0.3 + 0.7 * easeFns.easeOutBack(t)})`;
        if (t < 1) requestAnimationFrame(step);
        else { el.style.opacity = String(maxOp); el.style.transform = "scale(1)"; }
      };
      requestAnimationFrame(step);
    };

    const disappear = (el) => {
      const maxOp = maxOpOf(el);
      const g = geomOf.get(el) || { cx: vcx, cy: vcy, ox: 0, oy: 0 };
      const start = performance.now();
      // Scale about the star's OWN center (so it shrinks in place) and translate
      // that center outward along its radial — a gentle drift away + shrink while
      // the opacity fades to 0. All three share one easeInOutSine curve so the
      // fade reads as a soft fade-out rather than a quick pop.
      el.style.transformOrigin = `${g.cx}px ${g.cy}px`;
      const step = (now) => {
        if (cancelled) return;
        const t = Math.min(1, (now - start) / fadeMs);
        const m = easeFns.easeInOutSine(t); // gentle drift outward + shrink
        const tx = g.ox * travel * m, ty = g.oy * travel * m;
        const sc = 1 + (endScale - 1) * m;
        el.style.opacity = String(maxOp * (1 - m));
        el.style.transform = `translate(${tx}px, ${ty}px) scale(${sc})`;
        if (t < 1) requestAnimationFrame(step);
        else { el.style.opacity = "0"; el.style.transform = `translate(${g.ox * travel}px, ${g.oy * travel}px) scale(${endScale})`; }
      };
      requestAnimationFrame(step);
    };

    // skipAppear: on the first cycle the stars are already on screen from the
    // state's entrance pop, so begin at the hold to avoid an immediate re-pop.
    const runCycle = (skipAppear) => {
      if (cancelled) return;
      cancelHandles();

      const disappearThenRest = () => {
        if (cancelled) return;
        els.forEach((el, i) => {
          const tid = setTimeout(() => disappear(el), i * stagger);
          handles.push({ cancel: () => clearTimeout(tid) });
        });
        const exitTotal = fadeMs + els.length * stagger;
        const restTimer = setTimeout(() => { if (!cancelled) runCycle(false); }, exitTotal + restMs);
        handles.push({ cancel: () => clearTimeout(restTimer) });
      };

      if (skipAppear) {
        const holdTimer = setTimeout(disappearThenRest, holdMs);
        handles.push({ cancel: () => clearTimeout(holdTimer) });
        return;
      }

      els.forEach((el, i) => {
        const tid = setTimeout(() => appear(el), i * stagger);
        handles.push({ cancel: () => clearTimeout(tid) });
      });
      const appearTotal = popDur + els.length * stagger;
      const holdTimer = setTimeout(disappearThenRest, appearTotal + holdMs);
      handles.push({ cancel: () => clearTimeout(holdTimer) });
    };

    runCycle(true);
    // On cancel, leave opacity as-is so a state transition can fade the stars
    // out smoothly; just drop the scale so they rest at natural size.
    return { cancel: () => { cancelled = true; cancelHandles(); els.forEach(el => { el.style.transform = ""; el.style.transformOrigin = ""; }); } };
  };

  // Read the CURRENT visual `d` of a path element. Used when interrupting
  // a morph: the new tween should start from where the path actually is
  // right now, not from the data-model "from" state. Without this, clicking
  // a new state mid-morph would snap the path back to the original state's
  // shape before re-animating — looks like a flinch.
  const readCurrentD = (target, fallbackD) => {
    if (!target) return fallbackD;
    const live = target.getAttribute && target.getAttribute('d');
    return live && live.length > 0 ? live : fallbackD;
  };

  const runTransition = (toStateName) => {
    // Dedupe only against the latest TARGET (not the currently-displayed state).
    // This makes "click state-1 → state-2 → state-1 mid-morph" responsive:
    // currentStateRef would still be state-1 mid-morph, but targetStateRef is
    // already state-2, so the state-1 redirect correctly proceeds.
    if (toStateName === targetStateRef.current) return;
    targetStateRef.current = toStateName;
    cancelMorphs();
    if (orphanPopLoopRef.current) { orphanPopLoopRef.current.cancel(); orphanPopLoopRef.current = null; }
    // Particle handoff at transition start (not at transition end). If we're
    // leaving a state whose particle config differs from where we're heading,
    // stop spawning new particles immediately — alive ones continue their own
    // fade-out animation. The polling effect handles full destroy + recreate
    // when currentStateRef finally updates at morph completion.
    //
    // The else-branch handles rapid back-and-forth (e.g. state-5 → state-1
    // → state-5 mid-morph): if we're heading back to the SAME particle config
    // that we just cancelled, resume emission.
    {
      const fromPart = STATES[currentStateRef.current]?.particles;
      const toPart = STATES[toStateName]?.particles;
      const sys = particleSystemRef.current;
      if (sys) {
        if (fromPart && fromPart !== toPart) {
          sys.cancel();
        } else if (toPart && fromPart === toPart) {
          sys.resume();
        }
      }
    }
    const cfg = presetRef.current;
    const easingCfg = PRESETS.morph.easing[cfg.easing] || PRESETS.morph.easing["ease-in-out"];
    // A user-edited curve (bezier editor) wins over the named preset ease.
    const easeFn = cfg.easingBezier
      ? cubicBezierEase(...cfg.easingBezier)
      : (easeFns[easingCfg.ease] || easeFns.easeInOutQuad);
    // A user-edited duration (Duration card / PLAYER_CONFIG) wins over the
    // easing preset's default.
    const durationMs = cfg.durationMs != null ? cfg.durationMs : easingCfg.duration;

    const fromState = currentStateRef.current;
    const fromPaths = STATES[fromState].paths;
    const toPaths = STATES[toStateName].paths;

    // One cancellable rAF controls BOTH the idle amplitude envelope and the
    // idle-config swap for the whole transition:
    //   [0, rampDur)            fade the (old) idle OUT   1 → 0   (overlaps morph start)
    //   [rampDur, tailStart)    quiet                     0
    //   [tailStart, durationMs) fade the (new) idle IN    0 → 1   (overlaps morph END)
    // so the destination idle is already at full when the morph lands — no
    // post-arrival dwell, symmetric to the fade-out. At tailStart we swap the
    // IdleAnimator to the destination idle (its getBBox pivots are recomputed at
    // completion via refresh(), once the geometry has fully settled).
    const rampDur = durationMs * 0.4;
    const tailStart = Math.max(rampDur, durationMs - rampDur);
    const ampStart = performance.now();
    const ampFrom = idleAmplitudeRef.current;
    if (ampCtrlRef.current) ampCtrlRef.current.cancelled = true;
    const ampCtrl = { cancelled: false };
    ampCtrlRef.current = ampCtrl;
    let idleSwapped = false;
    const ampStep = (now) => {
      if (ampCtrl.cancelled) return;
      const e = now - ampStart;
      if (e < rampDur) idleAmplitudeRef.current = ampFrom + (0 - ampFrom) * easeFns.easeInOutSine(e / rampDur);
      else if (e < tailStart) idleAmplitudeRef.current = 0;
      else if (e < durationMs) idleAmplitudeRef.current = easeFns.easeInOutSine((e - tailStart) / rampDur);
      else idleAmplitudeRef.current = 1;
      if (!idleSwapped && e >= tailStart) {
        idleSwapped = true;
        idleConfigRef.current = idleOverrideRef.current || STATES[toStateName].idle;
        if (idleAnimatorRef.current) idleAnimatorRef.current.cancel();
        if (svgRef.current) svgRef.current.style.transform = "";
        idleAnimatorRef.current = new IdleAnimator(svgRef.current, idleConfigRef.current, () => idleAmplitudeRef.current, idleAnchorRef.current);
      }
      if (e < durationMs) requestAnimationFrame(ampStep);
      else { idleAmplitudeRef.current = 1; if (ampCtrlRef.current === ampCtrl) ampCtrlRef.current = null; }
    };
    requestAnimationFrame(ampStep);

    let morphsRemaining = 0, morphsCompleted = 0;
    const onComplete = () => {
      morphsCompleted++;
      if (morphsCompleted >= morphsRemaining) {
        // Race guard: if a faster subsequent click already redirected us to
        // a new target, don't overwrite currentStateRef back to this old one.
        // (Cancelled tweens don't reach this branch, but staggered tweens that
        // were nearly done can complete after a redirect — be defensive.)
        if (targetStateRef.current !== toStateName) return;
        currentStateRef.current = toStateName;
        forceRender(n => n + 1);
        // The destination idle was already swapped in during the tail; recompute
        // its getBBox pivots now that the morph geometry has fully settled.
        if (idleAnimatorRef.current) idleAnimatorRef.current.refresh();
      }
    };

    // All shared paths morph in unison (the scenario/stagger preset layer was
    // removed — icon-toggle behaviour, stagger 0, is the only mode).
    const offset = 0;

    // Shared rigid frames for `_group`ed paths: estimate ONE rotation +
    // centroid path from the union of the group's points, so nested parts
    // (eye white + pupil + highlight) follow the same trajectory instead of
    // each computing its own Kabsch fit and diverging mid-morph.
    const groupRigid = {};
    {
      const groupDs = {};
      SHARED_IDS.forEach(id => {
        const fp = fromPaths[id], tp = toPaths[id];
        if (!fp || !tp) return;
        const g = fp._group || tp._group;
        if (!g) return;
        (groupDs[g] = groupDs[g] || []).push([getPathDOf(fp), getPathDOf(tp)]);
      });
      Object.entries(groupDs).forEach(([g, list]) => {
        groupRigid[g] = estimateRigidFromDs(list);
      });
    }

    SHARED_IDS.forEach((id) => {
      const fromPath = fromPaths[id];
      const toPath = toPaths[id];
      if (!fromPath || !toPath) return;
      const strategy = STRATEGY[id];
      const fromD = getPathDOf(fromPath);
      const toD = getPathDOf(toPath);

      // User-selected CROSSFADE / SCALE methods (path editor) take the path out
      // of the morph pipeline entirely. Both work uniformly on single <path>
      // elements and multi-subpath <g> wrappers: the swap callback owns the
      // geometry + fill + transform writes.
      if (strategy === "CROSSFADE" || strategy === "SCALE") {
        const isMulti = splitSubpaths(fromD).length > 1 || splitSubpaths(toD).length > 1;
        const target = svgRef.current.querySelector(`#path-${cssEscape(id)}`);
        if (!target) return;
        const toParts = splitSubpaths(toD);
        const swap = () => {
          if (isMulti) {
            toParts.forEach((sub, s) => {
              const el = svgRef.current.querySelector(`#path-${id}__sub_${s}`);
              if (!el) return;
              el.setAttribute("d", sub);
              if (toPath.fill) el.setAttribute("fill", toPath.fill);
            });
          } else {
            target.setAttribute("d", toD);
            if (toPath.fill) target.setAttribute("fill", toPath.fill);
          }
          if (toPath.transform) target.setAttribute("transform", toPath.transform);
          else if (fromPath.transform) target.removeAttribute("transform");
        };
        morphsRemaining++;
        if (strategy === "CROSSFADE") {
          activeMorphsRef.current.push(runCrossfadeTween({
            target, durationMs, delayMs: offset, swap, onComplete
          }));
        } else {
          // For multi-subpath ids use the source fromD for the bbox (per-sub
          // live reads on interrupt aren't worth the complexity here).
          const fromBBox = computePathBBox(isMulti ? fromD : readCurrentD(target, fromD));
          const toBBox = computePathBBox(toD);
          if (fromBBox && toBBox) {
            activeMorphsRef.current.push(runScaleTween({
              target, fromBBox, toBBox, durationMs, easeFn, delayMs: offset, swap, onComplete
            }));
          } else {
            swap();
            onComplete();
          }
        }
        return;
      }

      if (splitSubpaths(fromD).length > 1 || splitSubpaths(toD).length > 1) {
        // Multi-subpath path → rigid-body morph. The hand isn't deforming
        // across states; it's the same N strokes rotated around the wrist.
        // We snap each subpath's `d` to the target state immediately, then
        // animate a CSS transform on the OUTER `<g id="<id>-rigid">` wrapper
        // from "inverse of target→from delta" back to identity. The user
        // sees a smooth rotate+slide between poses, no stretching of strokes.
        //
        // For paths where source/target have different subpath counts (rare;
        // none in the snowman), we still fade the extras in/out — but the
        // main morph goes through the rigid tween.
        const rigidG = svgRef.current.querySelector(`#path-${id}-rigid`);
        const fromRigid = RIGID_PARAMS[id] && RIGID_PARAMS[id][fromState];
        const toRigid = RIGID_PARAMS[id] && RIGID_PARAMS[id][toStateName];
        const fromParts = splitSubpaths(fromD);
        const toParts = splitSubpaths(toD);
        const minCount = Math.min(fromParts.length, toParts.length);

        if (rigidG && fromRigid && toRigid) {
          // Snap subpath d's to target geometry up front. The inverse transform
          // in runRigidTween makes the visual match `fromState`'s pose at
          // progress=0, so this snap is invisible — the user sees a smooth
          // rotate from fromState's hand to toState's hand.
          for (let s = 0; s < toParts.length; s++) {
            const sub = svgRef.current.querySelector(`#path-${id}__sub_${s}`);
            if (sub) sub.setAttribute('d', toParts[s]);
          }
          morphsRemaining++;
          activeMorphsRef.current.push(runRigidTween({
            target: rigidG,
            fromAnchor: fromRigid.anchor, fromAngle: fromRigid.angle,
            toAnchor: toRigid.anchor, toAngle: toRigid.angle,
            durationMs, easeFn, delayMs: offset, onComplete
          }));
        } else {
          // Fallback: original per-subpath lerp (e.g. for multi-subpath ids
          // that aren't in RIGID_PARAMS — shouldn't happen on the snowman).
          for (let s = 0; s < minCount; s++) {
            const sub = svgRef.current.querySelector(`#path-${id}__sub_${s}`);
            if (!sub) continue;
            morphsRemaining++;
            const liveFromD = readCurrentD(sub, fromParts[s]);
            if (strategy === "TRANSFORM" && structureFingerprint(liveFromD) === structureFingerprint(toParts[s])) {
              activeMorphsRef.current.push(runTransformTween({
                target: sub, fromD: liveFromD, toD: toParts[s],
                fromTransform: fromPath.transform || null,
                toTransform: toPath.transform || null,
                durationMs, easeFn, delayMs: offset, onComplete
              }));
            } else {
              activeMorphsRef.current.push(runMorphTween({
                target: sub, fromD: liveFromD, toD: toParts[s],
                durationMs, easeFn, delayMs: offset, onComplete
              }));
            }
          }
        }
        // Handle differing subpath counts via opacity fades (regardless of which
        // branch above ran). Rare; rigid-body matched counts is the common case.
        if (fromParts.length > toParts.length) {
          for (let s = toParts.length; s < fromParts.length; s++) {
            const sub = svgRef.current.querySelector(`#path-${id}__sub_${s}`);
            if (sub) activeMorphsRef.current.push(tweenStyle({ target: sub, prop: "opacity", from: 1, to: 0, durationMs: durationMs * 0.5, delayMs: offset, easeFn }));
          }
        } else if (toParts.length > fromParts.length) {
          for (let s = fromParts.length; s < toParts.length; s++) {
            const sub = svgRef.current.querySelector(`#path-${id}__sub_${s}`);
            if (sub) {
              sub.style.opacity = "0";
              activeMorphsRef.current.push(tweenStyle({ target: sub, prop: "opacity", from: 0, to: 1, durationMs: durationMs * 0.5, delayMs: offset + durationMs * 0.5, easeFn }));
            }
          }
        }
      } else {
        const target = svgRef.current.querySelector(`#path-${id}`);
        if (!target) return;
        morphsRemaining++;
        const isSmall = ["eyel", "eyer", "button1", "button2"].includes(id);
        // Same rationale as the multi-subpath branch above — use the live d
        // so interrupts pick up from current position.
        const liveFromD = readCurrentD(target, fromD);
        // Fingerprint guard: auto-detected TRANSFORM always matches (same
        // command structure across states, and the live d preserves it), but a
        // USER-FORCED "smooth morph" on structurally-different paths would
        // freeze mid-tween and snap at the end (control points can't pair) —
        // fall back to the sampled morph instead, mirroring the Swift
        // exporter's forced-TRANSFORM guard.
        if (strategy === "TRANSFORM" && structureFingerprint(liveFromD) === structureFingerprint(toD)) {
          activeMorphsRef.current.push(runTransformTween({
            target, fromD: liveFromD, toD,
            // Transform attribute interrupts are rarer (only on a few paths).
            // Falling back to the source fromTransform is acceptable for v1;
            // a perfect fix would parse the live transform attr too.
            fromTransform: fromPath.transform || null,
            toTransform: toPath.transform || null,
            rigid: ((fromPath._group || toPath._group) && groupRigid[fromPath._group || toPath._group]) || null,
            durationMs, easeFn, delayMs: offset, onComplete
          }));
        } else {
          activeMorphsRef.current.push(runMorphTween({
            target, fromD: liveFromD, toD, durationMs, easeFn, delayMs: offset, onComplete, isSmall
          }));
        }
        // Fills that differ across states: flat hex colors lerp smoothly with
        // the morph (a character whose palette IS its identity shouldn't color-
        // pop); url() paint servers keep the end-of-morph snap.
        if (fromPath.fill && toPath.fill && fromPath.fill !== toPath.fill) {
          if (isFlatColor(fromPath.fill) && isFlatColor(toPath.fill)) {
            activeMorphsRef.current.push(runFillTween({
              target, from: fromPath.fill, to: toPath.fill, durationMs, easeFn, delayMs: offset
            }));
          } else {
            setTimeout(() => { target.setAttribute("fill", toPath.fill); }, durationMs + offset);
          }
        }
      }
    });

    const fromOrphanIds = Object.keys(fromPaths).filter(id => !SHARED_IDS.includes(id));
    const toOrphanIds = Object.keys(toPaths).filter(id => !SHARED_IDS.includes(id));

    // Two orphan entrance styles, opt-in per destination state:
    //   "fade" (default): just opacity 0 → 1 with easeOutBack overshoot.
    //   "pop": slower, with scale 0.3 → 1.0 alongside opacity. Each element
    //          scales around its own center so it appears to grow in place.
    //          Used for state-5's flowers + dots — feels like things blooming
    //          on the snowman rather than fading in.
    const enterMode = STATES[toStateName].orphanEnter || "fade";
    const enterDur = enterMode === "pop" ? durationMs * 0.8 : durationMs * 0.4;
    const enterDelay = durationMs * 0.5;

    // Parse SVG rotate(angle cx cy) → { angle, cx, cy } so we can set
    // transform-origin to the rotation center and use a plain CSS rotate().
    const parseSvgRotate = (svgXf) => {
      if (!svgXf) return null;
      const m = svgXf.match(/rotate\(\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*\)/);
      if (m) return { angle: parseFloat(m[1]), cx: parseFloat(m[2]), cy: parseFloat(m[3]) };
      const m2 = svgXf.match(/rotate\(\s*([-\d.]+)\s*\)/);
      if (m2) return { angle: parseFloat(m2[1]), cx: null, cy: null };
      return null;
    };

    const popIn = (target, delayMs = 0) => {
      let cancelled = false;
      let done = false;
      let timerId = null;
      const fromScale = parseFloat(target.getAttribute("data-pop-from-scale")) || 0.3;
      const rotFrom = parseFloat(target.getAttribute("data-pop-rotate-from")) || 0;
      const rotTo = parseFloat(target.getAttribute("data-pop-rotate-to")) || 0;
      const durMul = parseFloat(target.getAttribute("data-pop-duration-mul")) || 1;
      const dur = enterDur * durMul;
      const svgXf = target.getAttribute("transform") || "";
      const svgRot = parseSvgRotate(svgXf);
      let defaultOrigin = target.getAttribute("data-pop-origin");
      if (!defaultOrigin) {
        // Default to the element's OWN bbox center so it pops in place. "50% 50%"
        // is the VIEW-BOX center (transform-box: view-box), which makes orphans
        // appear to fly in from the middle of the canvas — e.g. the sad tear
        // briefly showing above the eye before settling at the lower-left.
        try { const b = target.getBBox(); defaultOrigin = `${b.x + b.width / 2}px ${b.y + b.height / 2}px`; }
        catch (e) { defaultOrigin = "50% 50%"; }
      }
      // If the SVG transform has a rotation center, use it as transform-origin
      // so CSS rotate() matches the SVG rotate() exactly.
      const resolvedOrigin = (svgRot && svgRot.cx != null)
        ? `${svgRot.cx}px ${svgRot.cy}px`
        : defaultOrigin;
      const svgRotCSS = svgRot ? `rotate(${svgRot.angle}deg)` : "";
      const maxOp = parseFloat(target.dataset.targetOpacity) || 1;
      const begin = () => {
        if (cancelled) return;
        if (svgXf) target.removeAttribute("transform");
        const start = performance.now();
        target.style.opacity = "0";
        target.style.transformOrigin = resolvedOrigin;
        target.style.transform = `${svgRotCSS} scale(${fromScale}) rotate(${rotFrom}deg)`;
        const step = (now) => {
          if (cancelled) return;
          const t = Math.min(1, (now - start) / dur);
          target.style.opacity = String(Math.min(maxOp, t * 1.6 * maxOp));
          const sc = fromScale + (1 - fromScale) * easeFns.easeOutBack(t);
          const rot = rotFrom + (rotTo - rotFrom) * easeFns.easeOutBack(t);
          target.style.transform = `${svgRotCSS} scale(${sc}) rotate(${rot}deg)`;
          if (t < 1) requestAnimationFrame(step);
          else {
            if (svgXf) target.setAttribute("transform", svgXf);
            target.style.transform = "";
            target.style.transformOrigin = "";
            target.style.opacity = String(maxOp);
            done = true;
          }
        };
        requestAnimationFrame(step);
      };
      if (delayMs > 0) { timerId = setTimeout(begin, delayMs); } else begin();
      return {
        cancel: () => {
          cancelled = true;
          if (timerId) clearTimeout(timerId);
          // A completed pop must be a no-op on cancel: handles linger in
          // activeMorphsRef and get cancelled by the NEXT transition's
          // cancelMorphs(). Without this guard that stale cancel would force
          // opacity to 0, blanking the orphan and skipping its fade-out.
          if (done) return;
          if (svgXf && !target.getAttribute("transform")) {
            target.setAttribute("transform", svgXf);
          }
          target.style.transform = "";
          target.style.transformOrigin = "";
          target.style.opacity = "0";
        }
      };
    };

    ALL_STATE_NAMES.forEach(sn => {
      const orphansInThisState = Object.keys(STATES[sn].paths).filter(id => !SHARED_IDS.includes(id));
      orphansInThisState.forEach(id => {
        const t = svgRef.current.querySelector(`#orphan-${cssEscape(id)}-${sn}`);
        if (!t) return;
        t.style.transform = "";
        t.style.transformOrigin = "";
        // Don't reset fromState orphans to 1 — during fast switching they may
        // already be mid-fade; snapping to 1 causes a visible flash. Leave
        // their current opacity and let the fade-out tween handle it.
        if (sn !== fromState) t.style.opacity = "0";
      });
      if (STATES[sn].orphanSVG) {
        const grp = svgRef.current.querySelector(`#orphan-group-${sn}`);
        if (grp) {
          if (sn !== fromState) grp.style.opacity = "0";
          Array.from(grp.children).forEach(child => {
            child.style.transform = "";
            child.style.transformOrigin = "";
            child.style.opacity = "";
          });
        }
      }
    });
    fromOrphanIds.forEach(id => {
      const t = svgRef.current.querySelector(`#orphan-${cssEscape(id)}-${fromState}`);
      if (!t) return;
      const curOp = parseFloat(t.style.opacity);
      if (curOp > 0.01) {
        activeMorphsRef.current.push(tweenStyle({ target: t, prop: "opacity", from: curOp, to: 0, durationMs: durationMs * 0.4 * curOp, easeFn: easeFns.easeInOutSine }));
      }
    });
    if (STATES[fromState].orphanSVG) {
      const grp = svgRef.current.querySelector(`#orphan-group-${fromState}`);
      if (grp) {
        const curOp = parseFloat(grp.style.opacity);
        if (curOp > 0.01) {
          activeMorphsRef.current.push(tweenStyle({ target: grp, prop: "opacity", from: curOp, to: 0, durationMs: durationMs * 0.4 * curOp, easeFn: easeFns.easeInOutSine }));
        }
      }
    }
    // If the destination state has a particles config, its static orphans are
    // template-only — keep them invisible and skip the entrance tween (the
    // ParticleSystem owns visibility). orphanEnter "none" does the same: the
    // idle loop (e.g. happy's note pop-loop) owns the orphans, so they stay
    // hidden through the morph and the loop fades them in one-by-one afterward
    // instead of a batch entrance.
    const toHasParticles = !!STATES[toStateName].particles;
    toOrphanIds.forEach((id, i) => {
      const t = svgRef.current.querySelector(`#orphan-${cssEscape(id)}-${toStateName}`);
      if (!t) return;
      // _idleOwned orphans (e.g. the sad tear, owned by the drip loop) stay
      // hidden through the morph so the idle fully owns their entrance — no
      // popIn racing the loop's first cycle.
      const idleOwned = STATES[toStateName].paths[id] && STATES[toStateName].paths[id]._idleOwned;
      if (toHasParticles || enterMode === "none" || idleOwned) {
        t.style.opacity = "0";
        return;
      }
      const tgtOp = parseFloat(t.dataset.targetOpacity) || 1;
      if (enterMode === "pop") {
        activeMorphsRef.current.push(popIn(t, enterDelay + i * 60));
      } else {
        activeMorphsRef.current.push(tweenStyle({ target: t, prop: "opacity", from: 0, to: tgtOp, durationMs: enterDur, delayMs: enterDelay, easeFn: easeFns.easeOutBack }));
      }
    });
    if (STATES[toStateName].orphanSVG) {
      const grp = svgRef.current.querySelector(`#orphan-group-${toStateName}`);
      if (grp) {
        if (toHasParticles) {
          grp.style.opacity = "0";
        } else if (enterMode === "pop") {
          // Pop each top-level child of the orphan group around its own center
          // rather than the group's center (otherwise flowers would all scale
          // from the group's bbox center, splaying outward unnaturally).
          grp.style.opacity = "1";
          const children = Array.from(grp.children);
          children.forEach((child, i) => activeMorphsRef.current.push(popIn(child, enterDelay + i * 80)));
        } else {
          activeMorphsRef.current.push(tweenStyle({ target: grp, prop: "opacity", from: 0, to: 1, durationMs: enterDur, delayMs: enterDelay, easeFn: easeFns.easeOutBack }));
        }
      }
    }

    if (morphsRemaining === 0) {
      // Capture this transition's target so a later interrupting click doesn't
      // race the setTimeout. Only commit currentStateRef if this transition is
      // still the most recent one targeted.
      const myTarget = toStateName;
      setTimeout(() => {
        if (targetStateRef.current === myTarget) {
          currentStateRef.current = myTarget;
          forceRender(n => n + 1);
        }
      }, durationMs);
    }
  };

  // One-shot emotion overlay: pop the decoration in at the head, play its
  // signature motion (spin / rise / fall / twinkle), then fade it out. It drives
  // ONLY its own orphan group — never the shared/idle layers — so it composes
  // over any loop state without disturbing the morph or the ambient idle.
  const playEmotionOverlay = (name) => {
    const svg = svgRef.current;
    if (!svg || !OVERLAYS) return;
    const em = OVERLAY_EMOTIONS.find(e => e.name === name);
    if (!em) return;
    const group = svg.querySelector(`#overlay-emotion-${name}`);
    if (!group) return;
    if (overlayHandlesRef.current[name]) overlayHandlesRef.current[name].cancel();

    const children = Array.from(group.querySelectorAll('[data-overlay-child="1"]'));
    if (!children.length) return;
    const enterMs = em.enterMs || 340, holdMs = em.holdMs || 1400, exitMs = em.exitMs || 440;
    const stagger = em.stagger || 0;
    const fromScale = em.fromScale != null ? em.fromScale : 0.3;
    const motion = em.motion || {};
    const prefix = `overlay-${name}-`;

    // Optional eye-tracking: the tear starts at — and rides with — the CURRENT
    // pose's left eye, not its authored sad-pose spot. Measure the live eye
    // center once; offset the whole overlay by the delta from its anchor.
    let trackDx = 0, trackDy = 0, trackOrigin = null;
    if (em.track) {
      const tEl = svg.querySelector(em.track.selector);
      if (tEl) {
        try {
          const b = tEl.getBBox(); const cx = b.x + b.width / 2, cy = b.y + b.height / 2;
          trackDx = cx - em.track.anchor[0]; trackDy = cy - em.track.anchor[1];
          trackOrigin = `${cx}px ${cy}px`;
        } catch (e) { /* not rendered */ }
      }
    }
    // Static nudge (e.g. drop the tear a little down-and-left of the eye).
    if (em.offset) { trackDx += em.offset[0]; trackDy += em.offset[1]; }
    const center = motion.center || [149.5, 164.5];

    const geom = children.map((c, i) => {
      let cx = 0, cy = 0;
      try { const b = c.getBBox(); cx = b.x + b.width / 2; cy = b.y + b.height / 2; } catch (e) { /* not rendered */ }
      const pid = c.id.slice(prefix.length).replace(/-rigid$/, "");
      return {
        el: c, cx, cy,
        ox: cx - center[0], oy: cy - center[1],          // radial vector (for drift)
        dir: (motion.alternate && (i % 2 === 1)) ? -1 : 1, // alternating spin direction
        spins: !motion.spinIds || motion.spinIds.includes(pid),
        maxOp: parseFloat(c.dataset.targetOpacity) || 1,
      };
    });
    group.style.opacity = "1";
    geom.forEach(g => {
      g.el.style.transformOrigin = em.track ? (trackOrigin || `${g.cx}px ${g.cy}px`) : `${g.cx}px ${g.cy}px`;
      g.el.style.opacity = "0";
    });

    let cancelled = false;
    const start = performance.now();
    const total = enterMs + holdMs + exitMs;
    const isPop = motion.kind === "poploop";
    const popCycleMs = (motion.cycleDuration || 2.2) * 1000;
    const popTotal = popCycleMs * (motion.cycles || 2);
    const cleanup = () => {
      group.style.opacity = "0";
      geom.forEach(g => { g.el.style.opacity = "0"; g.el.style.transform = ""; g.el.style.transformOrigin = ""; });
      overlayHandlesRef.current[name] = null;
    };
    const step = (now) => {
      if (cancelled) return;
      const e = now - start;
      let alive = false;
      geom.forEach((g, i) => {
        if (isPop) {
          // Mirror the happy `pop-loop`: each note appears ONE BY ONE (staggered
          // phase), pops in about its own centre (scale + rotate), brief hold,
          // fades; repeated for `cycles` cycles, then a short tail fade-out.
          if (e >= popTotal) { g.el.style.opacity = "0"; return; }
          alive = true;
          const visFrac = motion.visibilityFraction != null ? motion.visibilityFraction : 0.2;
          const fadeFrac = motion.fadeFraction != null ? motion.fadeFraction : 0.1;
          const sr = motion.scaleRange || [0.3, 1.0], rr = motion.rotateRange || [0, 0];
          const phaseOffset = geom.length > 1 ? i / geom.length : 0;
          const phase = ((e / popCycleMs) + phaseOffset) % 1;
          const visStart = fadeFrac, visEnd = fadeFrac + visFrac, fadeOutEnd = visEnd + fadeFrac;
          let op = 0, scale = sr[0], rot = rr[0];
          if (phase < visStart) { const u = phase / fadeFrac; op = u; scale = sr[0] + (sr[1] - sr[0]) * easeFns.easeOutBack(u); }
          else if (phase < visEnd) { const u = (phase - visStart) / visFrac; op = 1; scale = sr[1]; rot = rr[0] + (rr[1] - rr[0]) * u; }
          else if (phase < fadeOutEnd) { const u = (phase - visEnd) / fadeFrac; op = 1 - u; scale = sr[1] - (sr[1] - sr[0]) * u; rot = rr[1]; }
          const tail = 400; if (e > popTotal - tail) op *= Math.max(0, (popTotal - e) / tail);
          g.el.style.opacity = String(op * g.maxOp);
          g.el.style.transform = `scale(${scale}) rotate(${rot}deg)`;
          return;
        }
        const lt = e - i * stagger;
        if (lt < 0) { alive = true; return; }
        if (lt >= total) { g.el.style.opacity = "0"; return; }
        alive = true;
        let op, scale = 1, tx = 0, ty = 0, rot = 0;
        if (lt < enterMs) {
          // Entrance pop (matches the morph engine's "pop": scale fromScale→1).
          const u = lt / enterMs;
          op = Math.min(g.maxOp, u * 1.6 * g.maxOp);
          scale = fromScale + (1 - fromScale) * easeFns.easeOutBack(u);
        } else {
          const inExit = lt > enterMs + holdMs;
          const exitU = inExit ? (lt - enterMs - holdMs) / exitMs : 0;
          op = inExit ? g.maxOp * (1 - exitU) : g.maxOp;
          const mt = (lt - enterMs) / 1000; // seconds since hold began
          switch (motion.kind) {
            case "spin": // down's swirls: only the vectors rotate, alternating dirs
              if (g.spins) rot = g.dir * mt * (360 / (motion.duration || 6));
              break;
            case "wiggle": // happy's notes: pop in place + slight rock (originSelf)
              rot = (motion.wiggleDeg || 7) * Math.sin(mt * 2 * Math.PI / (motion.period || 1.1));
              break;
            case "drift": { // super's stars: drift radially outward + shrink on exit
              const m = easeFns.easeInOutSine(exitU);
              tx = g.ox * (motion.travel || 0.25) * m;
              ty = g.oy * (motion.travel || 0.25) * m;
              scale = 1 + ((motion.endScale != null ? motion.endScale : 0.4) - 1) * m;
              break;
            }
            case "drip": // sad's tear: wells up on enter, falls + fades on exit
              ty = (motion.fallDist || 6) * easeFns.easeInOutSine(exitU);
              break;
          }
        }
        g.el.style.opacity = String(op);
        g.el.style.transform = `translate(${tx + trackDx}px, ${ty + trackDy}px) scale(${scale}) rotate(${rot}deg)`;
      });
      if (alive) requestAnimationFrame(step);
      else cleanup();
    };
    requestAnimationFrame(step);
    overlayHandlesRef.current[name] = { cancel: () => { cancelled = true; cleanup(); } };
  };

  // Walk up from the clicked element to the nearest editable path id and
  // report it (path editor selection), along with the click's position in
  // viewBox coordinates (used by the anchor picker). Clicking empty canvas
  // reports null + the point.
  const handleCanvasClick = (e) => {
    if (!onPickPath) return;
    const rect = svgRef.current.getBoundingClientRect();
    const vb = svgRef.current.viewBox.baseVal;
    const point = {
      x: vb.x + (e.clientX - rect.left) / rect.width * vb.width,
      y: vb.y + (e.clientY - rect.top) / rect.height * vb.height,
    };
    let el = e.target;
    while (el && el !== svgRef.current) {
      const logical = domIdToLogicalId(el.id);
      if (logical) { onPickPath(logical, point); return; }
      el = el.parentElement;
    }
    onPickPath(null, point);
  };

  useImperativeHandle(ref, () => ({
    transitionTo: runTransition,
    getCurrentState: () => currentStateRef.current,
    getSvgEl: () => svgRef.current,
    // Live idle-anchor override: recreate the idle animator with the
    // new pivot so the change is visible immediately.
    setIdleAnchor: (origin) => {
      idleAnchorRef.current = origin || null;
      if (idleAnimatorRef.current) idleAnimatorRef.current.cancel();
      if (svgRef.current) svgRef.current.style.transform = "";
      idleAnimatorRef.current = new IdleAnimator(
        svgRef.current,
        idleConfigRef.current || STATES[currentStateRef.current].idle,
        () => idleAmplitudeRef.current,
        idleAnchorRef.current
      );
    },
    // Live idle-preset override (Idle card). null restores the authored idle.
    setIdleOverride: (kind) => {
      idleOverrideRef.current = kind || null;
      idleConfigRef.current = idleOverrideRef.current || STATES[currentStateRef.current].idle;
      if (idleAnimatorRef.current) idleAnimatorRef.current.cancel();
      if (svgRef.current) svgRef.current.style.transform = "";
      idleAnimatorRef.current = new IdleAnimator(
        svgRef.current,
        idleConfigRef.current,
        () => idleAmplitudeRef.current,
        idleAnchorRef.current
      );
    },
    // One-shot overlays (only meaningful when the states file declares OVERLAYS).
    playOverlay: (name) => playEmotionOverlay(name),
    playTalk: () => {
      if (!idleAnimatorRef.current || !OVERLAYS || !OVERLAYS.talk) return;
      const cfg = { kind: "talk", ...OVERLAYS.talk };
      const eye = svgRef.current && svgRef.current.querySelector('#path-eye1');
      if (eye) {
        try {
          const b = eye.getBBox();
          // Rise UP to the fixed target Y, but never push down if already higher.
          if (cfg.targetEyeY != null) cfg.lift = Math.min(0, cfg.targetEyeY - (b.y + b.height / 2));
          // Scale eyes to a FIXED height (absolute), not a multiplier of the current.
          if (cfg.targetEyeH != null && b.height) cfg.heightScale = cfg.targetEyeH / b.height;
        } catch (e) { /* not rendered */ }
      }
      idleAnimatorRef.current.playTransient(cfg);
    },
    // Play the look-around gaze once (only meaningful from an enabled state; the
    // UI gates the button). Runs as an eye/mouth transient over the idle.
    playLookAround: () => {
      if (idleAnimatorRef.current && OVERLAYS && OVERLAYS.lookAround) {
        idleAnimatorRef.current.playTransient({ kind: "look-around", ...OVERLAYS.lookAround });
      }
    },
    // Play one of the declared `gestures` once (blink / look-around / look-up).
    // Gestures are plain face transients — no extra artwork — so this is just a
    // named playTransient. The UI gates on enabledStates; this re-checks so a
    // code-driven call can't play a gesture from a state it was authored out of
    // (e.g. blinking while asleep, where the eyes are already closed).
    playGesture: (name) => {
      const g = OVERLAY_GESTURES.find(x => x.name === name);
      if (!g || !idleAnimatorRef.current) return;
      if (!gestureEnabled(g, currentStateRef.current)) return;
      idleAnimatorRef.current.playTransient({ kind: g.kind || "blink", ...g });
    },
    // Particle controls — used by the slider UI in App(). The config object
    // is shared by reference with ParticleSystem.config, so mutating
    // STATES[state].particles in place is enough for most fields. Interval
    // is the exception because setInterval captures its delay at start time.
    restartParticleInterval: (ms) => {
      if (particleSystemRef.current) particleSystemRef.current.setIntervalMs(ms);
    },
    triggerParticleBurst: (n) => {
      if (particleSystemRef.current) particleSystemRef.current.triggerBurst(n);
    },
    hasParticleSystem: () => !!particleSystemRef.current,
  }));

  useEffect(() => {
    if (!svgRef.current) return;
    if (idleAnimatorRef.current) idleAnimatorRef.current.cancel();
    svgRef.current.style.transform = "";
    idleConfigRef.current = idleOverrideRef.current || STATES[currentStateRef.current].idle;
    idleAnimatorRef.current = new IdleAnimator(
      svgRef.current,
      idleConfigRef.current,
      () => idleAmplitudeRef.current,
      idleAnchorRef.current
    );
    // ParticleSystem (optional, per-state): a continuous spawn/despawn loop
    // for ephemeral decoration. Lives alongside the IdleAnimator — idle owns
    // body motion, particles own ambient sparkle/flowers/etc.
    const partCfg = STATES[currentStateRef.current].particles;
    if (partCfg) {
      particleSystemRef.current = new ParticleSystem(svgRef.current, partCfg);
      particleSystemRef.current.start();
    }
    return () => {
      if (ampCtrlRef.current) { ampCtrlRef.current.cancelled = true; ampCtrlRef.current = null; }
      if (idleAnimatorRef.current) idleAnimatorRef.current.cancel();
      if (particleSystemRef.current) { particleSystemRef.current.destroy(); particleSystemRef.current = null; }
      if (orphanPopLoopRef.current) { orphanPopLoopRef.current.cancel(); orphanPopLoopRef.current = null; }
    };
    // eslint-disable-next-line
  }, []);

  useEffect(() => {
    const checkInterval = setInterval(() => {
      const cur = STATES[currentStateRef.current];
      // Follow idleConfigRef (which the transition swaps to the destination idle
      // during the morph tail), not currentStateRef — otherwise this would fight
      // the early swap. Falls back to the committed state's idle.
      const wantIdle = idleConfigRef.current || cur.idle;
      if (idleAnimatorRef.current && idleAnimatorRef.current.kind !== wantIdle) {
        idleAnimatorRef.current.cancel();
        svgRef.current.style.transform = "";
        idleAnimatorRef.current = new IdleAnimator(
          svgRef.current,
          wantIdle,
          () => idleAmplitudeRef.current,
          idleAnchorRef.current
        );
      }
      // Particle system follows state: destroy + recreate when the particles
      // config object reference changes, OR when leaving a state that had one.
      const currentPartCfg = cur.particles || null;
      const existingPartCfg = particleSystemRef.current ? particleSystemRef.current.config : null;
      if (currentPartCfg !== existingPartCfg) {
        if (particleSystemRef.current) {
          particleSystemRef.current.destroy();
          particleSystemRef.current = null;
        }
        if (currentPartCfg) {
          particleSystemRef.current = new ParticleSystem(svgRef.current, currentPartCfg);
          particleSystemRef.current.start();
        }
      }
      const popLoopCfg = cur.orphanPopLoop || null;
      const hasPopLoop = !!popLoopCfg;
      const hadPopLoop = !!orphanPopLoopRef.current;
      // Only run once we've fully settled into the state — not mid-morph. While
      // transitioning away, runTransition cancels the loop; gating on settled
      // here prevents this interval from immediately restarting it (which would
      // fight the orphan fade-out) before currentStateRef catches up.
      const settled = currentStateRef.current === targetStateRef.current;
      if (hasPopLoop && !hadPopLoop && settled) {
        orphanPopLoopRef.current = startOrphanPopLoop(svgRef.current, currentStateRef.current, popLoopCfg);
      } else if (!hasPopLoop && hadPopLoop) {
        orphanPopLoopRef.current.cancel();
        orphanPopLoopRef.current = null;
      }
    }, 100);
    return () => {
      clearInterval(checkInterval);
      if (orphanPopLoopRef.current) { orphanPopLoopRef.current.cancel(); orphanPopLoopRef.current = null; }
    };
  }, []);

  const allDefs = ALL_STATE_NAMES.map(s => STATES[s].defs).filter(Boolean).join("\n")
    + (OVERLAYS && OVERLAYS.defs ? "\n" + OVERLAYS.defs : "");
  const initStateName = currentStateRef.current;

  return (
    <svg ref={svgRef} width={width} height={height} viewBox={VIEWBOX} xmlns="http://www.w3.org/2000/svg" style={{ display: "block" }} onClick={handleCanvasClick}>
      <defs dangerouslySetInnerHTML={{ __html: allDefs }} />
      {/* Back-layer orphan paths (rendered behind shared paths).
          Selected by _orphan: true AND _layer: "back".
          When the state has a `particles` config, static orphans render at
          opacity 0 — they stay in the DOM only as template sources for the
          ParticleSystem (which uses cloneNode + getBBox on them). */}
      {ALL_STATE_NAMES.flatMap(stateName =>
        Object.entries(STATES[stateName].paths)
          .filter(([, p]) => p._orphan && p._layer === "back")
          .map(([id, p]) => {
            const hasParticles = !!STATES[stateName].particles;
            // Idle-owned orphans (the sad tear's drip, happy notes' pop-loop)
            // start hidden — the idle loop fades them in. Rendering them visible
            // here would flash them at full opacity for a frame before the loop's
            // first frame runs.
            const idleOwned = p._idleOwned || STATES[stateName].orphanEnter === "none";
            const visible = stateName === currentStateRef.current && !hasParticles && !idleOwned;
            const targetOp = parseFloat(p.opacity) || 1;
            const el = renderInitialElement(`orphan-${cssEscape(id)}-${stateName}`, p, {
              dataTargetOpacity: String(targetOp),
              style: { opacity: visible ? targetOp : 0, transition: "none" }
            });
            return React.cloneElement(el, { key: `${stateName}-${id}` });
          })
      )}
      {SHARED_IDS.flatMap(id => {
        const p = STATES[initStateName].paths[id];
        if (!p) return [];
        return [renderInitialElement(`path-${id}`, p)];
      })}
      {/* Front-layer orphan paths (rendered in front of shared paths but behind
          the verbatim orphanSVG group). Default for _orphan: true entries that
          don't specify _layer, plus anything explicitly set to _layer: "front".
          Same id format as back-layer orphans so the transition fade logic
          (which queries #orphan-<id>-<state>) picks them up automatically. */}
      {ALL_STATE_NAMES.flatMap(stateName =>
        Object.entries(STATES[stateName].paths)
          .filter(([, p]) => p._orphan && p._layer !== "back")
          .map(([id, p]) => {
            const hasParticles = !!STATES[stateName].particles;
            // Idle-owned orphans (the sad tear's drip, happy notes' pop-loop)
            // start hidden — the idle loop fades them in. Rendering them visible
            // here would flash them at full opacity for a frame before the loop's
            // first frame runs.
            const idleOwned = p._idleOwned || STATES[stateName].orphanEnter === "none";
            const visible = stateName === currentStateRef.current && !hasParticles && !idleOwned;
            const targetOp = parseFloat(p.opacity) || 1;
            const el = renderInitialElement(`orphan-${cssEscape(id)}-${stateName}`, p, {
              dataTargetOpacity: String(targetOp),
              style: { opacity: visible ? targetOp : 0, transition: "none" }
            });
            return React.cloneElement(el, { key: `${stateName}-${id}` });
          })
      )}
      {ALL_STATE_NAMES.map(stateName => {
        const sd = STATES[stateName];
        if (!sd.orphanSVG) return null;
        const hasParticles = !!sd.particles;
        const visible = stateName === currentStateRef.current && !hasParticles;
        return (
          <g key={stateName} id={`orphan-group-${stateName}`}
             style={{ opacity: visible ? 1 : 0 }}
             dangerouslySetInnerHTML={{ __html: sd.orphanSVG }} />
        );
      })}
      {/* One-shot emotion overlays — rendered hidden in front of everything;
          playEmotionOverlay() drives each group's children on click. Each child
          carries data-overlay-child so the player can select + measure it. */}
      {OVERLAY_EMOTIONS.map(em => (
        <g key={`ov-${em.name}`} id={`overlay-emotion-${em.name}`} style={{ opacity: 0 }}>
          {Object.entries(em.paths).map(([id, p]) => {
            const targetOp = parseFloat(p.opacity) || 1;
            // Render with NO ctrl so the opacity control lands on the OUTERMOST
            // element — the <path>, or the multi-subpath `-rigid` <g> wrapper —
            // which is the same element the player drives. (ctrl would put the
            // opacity on the INNER <g>, leaving multi-subpath orphans stuck at 0.)
            const el = renderInitialElement(`overlay-${em.name}-${cssEscape(id)}`, p);
            return React.cloneElement(el, {
              key: id,
              "data-overlay-child": "1",
              "data-target-opacity": String(targetOp),
              style: { ...(el.props.style || {}), opacity: 0 },
            });
          })}
        </g>
      ))}
    </svg>
  );
});

// Dark palette — bright fg on deep tinted wells (see preview.html vars).
const STRATEGY_COLOR = {
  TRANSFORM: { fg: "#4fc07a", bg: "#12291c" },
  MORPH: { fg: "#d3a41f", bg: "#2a2310" },
};

function StatStrip({ states, shared, orphans }) {
  const Stat = ({ label, value }) => (
    <div className="stat">
      <span className="stat-value">{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  );
  return (
    <div className="stat-strip">
      <Stat label="states" value={states} />
      <Stat label="shared" value={shared} />
      <Stat label="decorations" value={orphans} />
    </div>
  );
}

const METHOD_OPTIONS = ["auto", "TRANSFORM", "MORPH", "CROSSFADE", "SCALE"];
const METHOD_COLOR = {
  ...STRATEGY_COLOR,
  CROSSFADE: { fg: "#b985e0", bg: "#241a2e" },
  SCALE: { fg: "#5aa7d0", bg: "#14242e" },
};
// Designer-facing method names. The internal TRANSFORM/MORPH strategy names
// describe the interpolation MECHANISM, not whether the shape visibly changes
// — both deform contours (TRANSFORM = exact vertex lerp, MORPH = polygon-
// sampled library). Labeling them "transform"/"morph" made users read
// "transform" as rigid-only and report the label as broken. The two methods
// that genuinely never deform are crossfade and move & resize.
const METHOD_LABEL = {
  TRANSFORM: "smooth morph",
  MORPH: "sampled morph",
  CROSSFADE: "crossfade",
  SCALE: "move & resize",
};
const METHOD_TITLE =
  "How this part transitions:\n" +
  "· smooth morph — exact vertex interpolation (shape DOES deform, highest quality)\n" +
  "· sampled morph — polygon-sampled library morph (shape deforms, approximate)\n" +
  "· crossfade — fade out / fade in, no deformation\n" +
  "· move & resize — rigid box mapping, no deformation";

// Editable per-path panel (replaces the read-only strategy panel):
//   role   — character part (shared, morphs) vs orphan (fades in/out).
//            Roles feed shared-id computation at engine init, so changes
//            persist to localStorage and need a reload to take effect.
//   method — transition method for shared paths: auto (detected), transform,
//            morph, crossfade, scale. Applies LIVE (next transition uses it).
// Clicking a row selects + highlights the path on canvas (and vice versa).
function PathEditor({ selectedId, onSelect, methodOverrides, onMethodChange, pendingRoles, onRoleChange }) {
  const rows = ALL_PATH_IDS.map(id => ({
    id,
    inAllStates: ALL_STATE_NAMES.every(sn => STATES[sn].paths[id]),
    isShared: SHARED_IDS.includes(id),
  }));
  const pendingCount = Object.keys(pendingRoles).length;
  const counts = rows.reduce((acc, r) => {
    // Internal method key ("DECORATION" is the user-facing orphan role).
    const key = r.isShared ? (STRATEGY[r.id] || "TRANSFORM") : "DECORATION";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  return (
    <div className="control-card path-card">
      <div className="control-label">Paths &amp; transitions</div>
      <div className="pe-chips">
        {Object.entries(counts).map(([s, n]) => (
          <span key={s} className="strategy-chip"
            style={{ color: METHOD_COLOR[s]?.fg || "#9b9993", background: METHOD_COLOR[s]?.bg || "#202024" }}>
            {s === "DECORATION" ? "decoration" : METHOD_LABEL[s] || s.toLowerCase()} · {n}
          </span>
        ))}
      </div>
      {pendingCount > 0 && (
        <button className="pe-apply" onClick={() => location.reload()}>
          Apply {pendingCount} role change{pendingCount > 1 ? "s" : ""} (reloads page)
        </button>
      )}
      <div className="pe-list">
        {rows.map(r => {
          const role = pendingRoles[r.id] || (r.isShared ? "shared" : "orphan");
          const method = methodOverrides[r.id] || "auto";
          const detected = DETECTED_STRATEGY[r.id];
          return (
            <div key={r.id}
              className={`pe-row${r.id === selectedId ? " is-selected" : ""}`}
              onClick={() => onSelect(r.id === selectedId ? null : r.id)}>
              <code className="pe-id" title={r.id}>{r.id}</code>
              <select className="pe-select" value={role}
                disabled={!r.inAllStates}
                title={r.inAllStates ? "Role: character parts morph between states; decorations fade in/out" : "Not present in every state — must stay a decoration"}
                onClick={e => e.stopPropagation()}
                onChange={e => onRoleChange(r.id, e.target.value)}>
                <option value="shared">character</option>
                <option value="orphan">decoration</option>
              </select>
              {r.isShared ? (
                <select className="pe-select" value={method}
                  title={METHOD_TITLE}
                  onClick={e => e.stopPropagation()}
                  onChange={e => onMethodChange(r.id, e.target.value)}>
                  {METHOD_OPTIONS.map(m => (
                    <option key={m} value={m}>
                      {m === "auto" ? `auto (${METHOD_LABEL[detected] || "?"})` : METHOD_LABEL[m]}
                    </option>
                  ))}
                </select>
              ) : (
                <span className="strategy-chip" style={{ color: "#9b9993", background: "#202024" }}>fade</span>
              )}
            </div>
          );
        })}
      </div>
      <div className="pe-hint">Click a part on the canvas (or a row) to select it.</div>
    </div>
  );
}

// Compact slider row used by ParticleControls. Renders a label, one or two
// range inputs, and a numeric readout. Two inputs are used for paired ranges
// (e.g. radius min/max) so the user can drag each endpoint independently.
function SliderRow({ label, values, min, max, step, onChange, format }) {
  const fmt = format || ((v) => (Number.isInteger(step) ? v : (+v).toFixed(2)));
  return (
    <div className="slider-row">
      <label>{label}</label>
      <div className="slider-pair">
        {values.map((v, i) => (
          <input
            key={i}
            type="range"
            min={min}
            max={max}
            step={step}
            value={v}
            onChange={e => onChange(i, +e.target.value)}
          />
        ))}
      </div>
      <span className="slider-value">{values.map(fmt).join("–")}</span>
    </div>
  );
}

// Particle tuning UI. Only renders when the current state has a `particles`
// config. Mutates the same object that ParticleSystem holds (by reference)
// so every change is picked up on the next spawn — no React state syncing
// across the boundary. Interval is the exception (handled via the imperative
// restartParticleInterval hook).
function ParticleControls({ stateName, animatorRef, onChange }) {
  const cfg = STATES[stateName]?.particles;
  if (!cfg) return null;
  const set = (mut, opts = {}) => {
    mut(cfg);
    if (opts.restartInterval) animatorRef.current?.restartParticleInterval(cfg.interval);
    if (opts.burst) animatorRef.current?.triggerParticleBurst(opts.burst);
    onChange();
  };
  const arc = cfg.spawnArc || (cfg.spawnArc = { center: [150, 150], radius: [30, 60], angle: [180, 360] });
  return (
    <div className="control-card particle-card">
      <div className="control-label">Particles — {stateName}</div>
      <details open>
        <summary>Arc position</summary>
        <SliderRow label="Center X" values={[arc.center[0]]} min={0} max={290} step={1}
          onChange={(_, v) => set(c => { c.spawnArc.center[0] = v; })} />
        <SliderRow label="Center Y" values={[arc.center[1]]} min={0} max={310} step={1}
          onChange={(_, v) => set(c => { c.spawnArc.center[1] = v; })} />
        <SliderRow label="Radius" values={arc.radius} min={0} max={150} step={1}
          onChange={(i, v) => set(c => { c.spawnArc.radius[i] = v; })} />
        <SliderRow label="Angle" values={arc.angle} min={0} max={360} step={1}
          onChange={(i, v) => set(c => { c.spawnArc.angle[i] = v; })} />
      </details>
      <details open>
        <summary>Size</summary>
        <SliderRow label="Scale" values={cfg.scaleRange || [0.6, 1.0]} min={0.1} max={2.0} step={0.05}
          onChange={(i, v) => set(c => {
            if (!c.scaleRange) c.scaleRange = [0.6, 1.0];
            c.scaleRange[i] = v;
          })} />
      </details>
      <details open>
        <summary>Spawn &amp; lifespan</summary>
        <SliderRow label="Interval" values={[cfg.interval ?? 500]} min={50} max={2000} step={10}
          onChange={(_, v) => set(c => { c.interval = v; }, { restartInterval: true })} />
        <SliderRow label="Burst" values={[cfg.burst ?? 0]} min={0} max={20} step={1}
          onChange={(_, v) => {
            const delta = v - (cfg.burst ?? 0);
            set(c => { c.burst = v; }, delta > 0 ? { burst: delta } : {});
          }} />
        <SliderRow label="Duration" values={[cfg.duration ?? 2500]} min={500} max={6000} step={50}
          onChange={(_, v) => set(c => { c.duration = v; })} />
        <SliderRow label="Dur jitter" values={[cfg.durationJitter ?? 600]} min={0} max={2000} step={25}
          onChange={(_, v) => set(c => { c.durationJitter = v; })} />
      </details>
    </div>
  );
}

// Export panel — generates a self-contained .swift file matching the user's
// currently tuned settings (live STATES, including particle slider mutations)
// and offers it as a download. Uses scripts/export-swift.js loaded as a global.
function ExportPanel({ easing, morphPreset }) {
  const [busy, setBusy] = useState(false);
  const [lastFile, setLastFile] = useState(null);
  // Swift type name: an explicit PREVIEW_CONFIG.exportName wins (lets a states file
  // pick a name distinct from other exports so they don't collide in one Xcode
  // project); otherwise a heuristic from the title ("Snowman …" → "SnowmanAnimator").
  const defaultTypeName = (() => {
    const cfg = window.PREVIEW_CONFIG || {};
    if (cfg.exportName) return cfg.exportName;
    const title = cfg.title || 'Character';
    const first = title.split(/\s+/)[0].replace(/[^A-Za-z0-9]/g, '');
    return (first.charAt(0).toUpperCase() + first.slice(1) || 'Character') + 'Animator';
  })();
  const [typeName, setTypeName] = useState(defaultTypeName);
  // Prefix for the generic top-level Swift types (MorphShape, IdlePart, …) so
  // multiple exported animators can live in ONE app/module without colliding.
  // Defaults to the character name (e.g. "SnowmanAnimator" → "Snowman"); clear it to
  // emit un-prefixed types (fine for a single-animator project).
  const [typePrefix, setTypePrefix] = useState(defaultTypeName.replace(/(Animator|View)$/, ''));

  const handleExport = () => {
    if (!window.SwiftExporter) {
      alert('SwiftExporter not loaded — check that scripts/export-swift.js is included before app.jsx.');
      return;
    }
    setBusy(true);
    try {
      const easingCfg = PRESETS.morph.easing[morphPreset.easing] || PRESETS.morph.easing["ease-in-out"];
      const morphEasing = easingCfg.ease;
      const duration = morphPreset.durationMs != null ? morphPreset.durationMs : easingCfg.duration;
      // PREVIEW_CONFIG may set viewBox/size; fall back to defaults if absent.
      const size = (window.PREVIEW_CONFIG && window.PREVIEW_CONFIG.size) || { width: 290, height: 310 };
      const stateEnum = typeName.replace(/Animator$/, '') + 'State';
      const swift = window.SwiftExporter.exportToSwift(STATES, {
        typeName,
        stateEnum,
        typePrefix: typePrefix || undefined,
        duration,
        morphEasing,
        // The full preview edit set rides along so the Swift build matches
        // what's on screen: custom bezier curve, per-path method overrides
        // (crossfade / scale / forced morph), idle preset + anchor.
        easingBezier: morphPreset.easingBezier || undefined,
        methodOverrides: Object.keys(OVERRIDES.methods || {}).length ? OVERRIDES.methods : undefined,
        idleOverride: OVERRIDES.idleOverride || undefined,
        idleAnchor: OVERRIDES.idleAnchor || undefined,
        viewBox: size,
        sourceName: 'preview-export',
        // One-shot / looping overlays (decorations + talk / look-around), if declared.
        overlays: OVERLAYS || undefined,
      });
      const blob = new Blob([swift], { type: 'text/x-swift' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${typeName}.swift`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      // Don't revoke immediately — Safari sometimes loses the download. Revoke after 30s.
      setTimeout(() => URL.revokeObjectURL(url), 30000);
      setLastFile({ name: `${typeName}.swift`, size: swift.length });
    } catch (e) {
      console.error('Export failed:', e);
      alert('Export failed: ' + e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="control-card export-card">
      <div className="control-label">Export to SwiftUI</div>
      <input
        type="text"
        className="export-typename"
        value={typeName}
        onChange={e => setTypeName(e.target.value.replace(/[^A-Za-z0-9_]/g, ''))}
        placeholder="Type name (e.g. SnowmanAnimator)"
        aria-label="Swift type name"
      />
      <input
        type="text"
        className="export-typename"
        value={typePrefix}
        onChange={e => setTypePrefix(e.target.value.replace(/[^A-Za-z0-9_]/g, ''))}
        placeholder="Type prefix (e.g. Snowman) — keeps types unique per app"
        aria-label="Swift type prefix"
      />
      <button
        className="export-button"
        onClick={handleExport}
        disabled={busy}
      >
        {busy ? 'Generating…' : `Export ${typeName}.swift`}
      </button>
      {lastFile && (
        <div className="export-meta">
          Last export: <code>{lastFile.name}</code> ({(lastFile.size / 1024).toFixed(1)} KB)
        </div>
      )}
      <div className="export-hint">
        Captures every current edit: duration, easing curve, per-path methods,
        idle preset + anchor, particle tuning. Background color is preview-only.
      </div>
    </div>
  );
}

// Interactive cubic-bezier curve editor (CSS timing-function style). P0/P3
// are fixed at (0,0)/(1,1); the user drags P1/P2. Renders inside the Easing
// card: selecting a preset shows its equivalent curve, dragging a handle
// switches to a custom curve that overrides the preset.
function BezierEditor({ value, onChange }) {
  const svgRef = useRef(null);
  const dragRef = useRef(null); // 1 | 2 while dragging that handle
  const [x1, y1, x2, y2] = value;

  // View mapping: x ∈ [0,1] fills the width; the y range leaves generous
  // headroom so overshoot handles (easeOutBack's y=1.56, or user drags) stay
  // inside the svg — outside the viewBox they'd be clipped and undraggable.
  // The rendered size is capped in CSS (.bez-svg max-width) so the editor
  // stays compact inside the card. SVG y is flipped.
  const W = 200, H = 150, PAD = 10;
  const Y_MIN = -0.65, Y_MAX = 1.75;
  const px = x => PAD + x * (W - 2 * PAD);
  const py = y => H - PAD - ((y - Y_MIN) / (Y_MAX - Y_MIN)) * (H - 2 * PAD);
  const fromPx = (mx, my) => [
    Math.min(1, Math.max(0, (mx - PAD) / (W - 2 * PAD))),
    Math.min(Y_MAX, Math.max(Y_MIN, Y_MIN + (H - PAD - my) / (H - 2 * PAD) * (Y_MAX - Y_MIN))),
  ];

  const toLocal = (e) => {
    const r = svgRef.current.getBoundingClientRect();
    return [(e.clientX - r.left) * (W / r.width), (e.clientY - r.top) * (H / r.height)];
  };
  const onPointerDown = (which) => (e) => {
    e.preventDefault();
    try { e.target.setPointerCapture(e.pointerId); } catch (err) { /* synthetic events */ }
    dragRef.current = which;
  };
  const onPointerMove = (e) => {
    if (!dragRef.current) return;
    const [mx, my] = toLocal(e);
    const [nx, ny] = fromPx(mx, my);
    const r = v => Math.round(v * 100) / 100;
    onChange(dragRef.current === 1 ? [r(nx), r(ny), x2, y2] : [x1, y1, r(nx), r(ny)]);
  };
  const onPointerUp = () => { dragRef.current = null; };

  const curve = `M ${px(0)} ${py(0)} C ${px(x1)} ${py(y1)}, ${px(x2)} ${py(y2)}, ${px(1)} ${py(1)}`;
  return (
    <div className="bez-wrap">
      <svg ref={svgRef} className="bez-svg" viewBox={`0 0 ${W} ${H}`}
        onPointerMove={onPointerMove} onPointerUp={onPointerUp}>
        {/* unit box (progress 0→1) */}
        <rect x={px(0)} y={py(1)} width={px(1) - px(0)} height={py(0) - py(1)} className="bez-box" />
        {/* handle arms */}
        <line x1={px(0)} y1={py(0)} x2={px(x1)} y2={py(y1)} className="bez-arm" />
        <line x1={px(1)} y1={py(1)} x2={px(x2)} y2={py(y2)} className="bez-arm" />
        {/* the curve */}
        <path d={curve} className="bez-curve" />
        {/* endpoints + draggable handles */}
        <circle cx={px(0)} cy={py(0)} r="3" className="bez-end" />
        <circle cx={px(1)} cy={py(1)} r="3" className="bez-end" />
        <circle cx={px(x1)} cy={py(y1)} r="6" className="bez-handle" onPointerDown={onPointerDown(1)} />
        <circle cx={px(x2)} cy={py(y2)} r="6" className="bez-handle" onPointerDown={onPointerDown(2)} />
      </svg>
      <code className="bez-readout">cubic-bezier({x1}, {y1}, {x2}, {y2})</code>
    </div>
  );
}

// Idle preset picker — swap every state's authored idle for a quick
// whole-body preset (or silence it) while tuning. "authored" restores the
// per-state idles from the states file.
const IDLE_PRESETS = [
  { value: "authored", label: "authored (per state)" },
  { value: "none", label: "none" },
  { value: "breathe", label: "breathe" },
  { value: "breathe-y", label: "breathe-y" },
  { value: "sway", label: "sway" },
  { value: "bob", label: "bob" },
  { value: "shake", label: "shake" },
  { value: "waggle-sequence", label: "waggle" },
  { value: "float", label: "float" },
];
function IdleCard({ value, onChange }) {
  return (
    <div className="control-card">
      <div className="control-label">Idle {value !== "authored" ? "· override" : ""}</div>
      <select value={value} onChange={e => onChange(e.target.value)}>
        {IDLE_PRESETS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
      </select>
    </div>
  );
}

// Idle anchor editor — sets the transform-origin for whole-body idle
// parts (sway / breathe / shake / …). Presets cover the skill's pivot rules
// (bottom-center for grounded characters, center for floating); "pick on
// canvas" arms a one-shot click that drops the anchor at an exact point —
// e.g. the character's feet when the artwork isn't centered in the canvas.
const ANCHOR_PRESETS = [
  { label: "bottom-center", value: null, hint: "default — feet on the ground plane" },
  { label: "center", value: "50% 50%", hint: "floating objects" },
  { label: "top-center", value: "50% 0%", hint: "hanging from above" },
];
function AnchorCard({ anchor, pickArmed, onArmPick, onChange }) {
  const isPreset = ANCHOR_PRESETS.some(p => p.value === anchor);
  return (
    <div className="control-card">
      <div className="control-label">Idle anchor</div>
      <div className="anchor-row">
        {ANCHOR_PRESETS.map(p => (
          <button key={p.label} title={p.hint}
            className={`anchor-btn${anchor === p.value && !pickArmed ? " is-active" : ""}`}
            onClick={() => onChange(p.value)}>
            {p.label}
          </button>
        ))}
        <button
          className={`anchor-btn${pickArmed ? " is-armed" : (!isPreset ? " is-active" : "")}`}
          title="Click a point on the canvas to place the pivot there"
          onClick={onArmPick}>
          {pickArmed ? "click canvas…" : "pick on canvas"}
        </button>
      </div>
      {!isPreset && anchor && (
        <code className="bez-readout">transform-origin: {anchor}</code>
      )}
    </div>
  );
}

// Transition duration editor. Picking an easing preset resets the value to
// the preset default; any direct edit switches to "custom" and wins
// (persisted so it survives reloads and flows into all three exports).
function DurationCard({ durationMs, isCustom, presetMs, onEdit, onReset }) {
  const clamp = v => Math.max(50, Math.min(10000, Math.round(v)));
  return (
    <div className="control-card">
      <div className="control-label">Duration {isCustom ? "· custom" : "· preset"}</div>
      <div className="dur-row">
        <input type="range" min="100" max="3000" step="50" value={Math.min(3000, durationMs)}
          onChange={e => onEdit(clamp(+e.target.value))} />
        <input type="number" className="dur-num" min="50" max="10000" step="50" value={durationMs}
          onChange={e => onEdit(clamp(+e.target.value || presetMs))} />
        <span className="dur-unit">ms</span>
      </div>
      {isCustom && (
        <button className="dur-reset" onClick={onReset}>reset to preset ({presetMs}ms)</button>
      )}
    </div>
  );
}

// PNG sequence export — records the LIVE canvas through one transition
// (current state → picked target) at the chosen fps, then zips the frames.
// Blocked while X-ray is on: the wireframe layer lives inside the svg, so it
// would be serialized into every captured frame.
function PngExportPanel({ animatorRef, current, morphPreset, bgColor, xray, onTransitioned }) {
  const others = ALL_STATE_NAMES.filter(s => s !== current);
  const [toState, setToState] = useState(others[0]);
  const [fps, setFps] = useState(30);
  const [scale, setScale] = useState(2);
  const [transparent, setTransparent] = useState(true);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState("");
  const effectiveTo = others.includes(toState) ? toState : others[0];

  const handleRecord = async () => {
    if (!window.PreviewExporters) { alert("exporters.js not loaded — include it before app.jsx."); return; }
    const svgEl = animatorRef.current?.getSvgEl();
    if (!svgEl || !effectiveTo) return;
    setBusy(true);
    try {
      const durationMs = morphPreset.durationMs
        ?? (PRESETS.morph.easing[morphPreset.easing]?.duration || 800);
      // Cover the orphan pop entrance (which runs past the morph itself),
      // plus a small settle margin.
      const recordMs = durationMs * 1.5 + 300;
      setProgress("recording…");
      const zip = await window.PreviewExporters.recordPngSequence({
        svgEl,
        trigger: () => { animatorRef.current.transitionTo(effectiveTo); onTransitioned(effectiveTo); },
        recordMs, fps, scale,
        background: transparent ? null : bgColor,
        onProgress: setProgress,
      });
      const slug = (TITLE.split(/\s+/)[0] || "morph").toLowerCase().replace(/[^a-z0-9]/g, "");
      window.PreviewExporters.downloadBlob(zip, `${slug}_${current}-to-${effectiveTo}_${fps}fps.zip`);
      setProgress("done");
    } catch (e) {
      console.error("PNG export failed:", e);
      setProgress("failed: " + e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="control-card export-card">
      <div className="control-label">Export PNG sequence</div>
      <div className="export-row">
        <label>To state</label>
        <select value={effectiveTo || ""} onChange={e => setToState(e.target.value)}>
          {others.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      <div className="export-row">
        <label>FPS</label>
        <select value={fps} onChange={e => setFps(+e.target.value)}>
          {[12, 24, 30, 60].map(f => <option key={f} value={f}>{f}</option>)}
        </select>
      </div>
      <div className="export-row">
        <label>Scale</label>
        <select value={scale} onChange={e => setScale(+e.target.value)}>
          {[1, 2, 3].map(s => <option key={s} value={s}>{s}×</option>)}
        </select>
      </div>
      <label className="export-check">
        <input type="checkbox" checked={transparent} onChange={e => setTransparent(e.target.checked)} />
        transparent background
      </label>
      <button className="export-button" onClick={handleRecord} disabled={busy || !effectiveTo || xray}
        title={xray ? "Turn off X-ray first — the wireframe would be recorded into the frames" : ""}>
        {xray ? "Turn off X-ray to record" : busy ? "Recording…" : `Record ${current} → ${effectiveTo || "?"} (.zip)`}
      </button>
      {progress && <div className="export-progress">{progress}</div>}
      <div className="export-hint">Records the live canvas through one transition, then zips the frames. Background is transparent unless unchecked above.</div>
    </div>
  );
}

// Web animation export — one standalone .html file that replays this exact
// animation (states + engine + minimal player, current tuning baked in).
function WebExportPanel({ morphPreset, bgColor }) {
  const [autoplay, setAutoplay] = useState(true);
  const [busy, setBusy] = useState(false);
  const [lastFile, setLastFile] = useState(null);

  const handleExport = async () => {
    if (!window.PreviewExporters) { alert("exporters.js not loaded — include it before app.jsx."); return; }
    setBusy(true);
    try {
      const html = await window.PreviewExporters.buildPlayerHtml({
        playerConfig: {
          easing: morphPreset.easing,
          durationMs: morphPreset.durationMs,
          easingBezier: morphPreset.easingBezier,
          // No background: the preview's canvas color is preview-only. The
          // player renders transparent so it takes the embedding page's bg.
          autoplay,
          holdMs: 1400,
        },
        pathOverrides: {
          roles: OVERRIDES.roles,
          methods: OVERRIDES.methods,
          idleAnchor: OVERRIDES.idleAnchor || null,
          idleOverride: OVERRIDES.idleOverride || null,
        },
      });
      const slug = (TITLE.split(/\s+/)[0] || "morph").toLowerCase().replace(/[^a-z0-9]/g, "");
      const name = `${slug}-player.html`;
      window.PreviewExporters.downloadBlob(new Blob([html], { type: "text/html" }), name);
      setLastFile({ name, size: html.length });
    } catch (e) {
      console.error("Web export failed:", e);
      alert("Web export failed: " + e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="control-card export-card">
      <div className="control-label">Export web animation</div>
      <label className="export-check">
        <input type="checkbox" checked={autoplay} onChange={e => setAutoplay(e.target.checked)} />
        autoplay (cycle through states)
      </label>
      <button className="export-button" onClick={handleExport} disabled={busy}>
        {busy ? "Bundling…" : "Export player (.html)"}
      </button>
      {lastFile && (
        <div className="export-meta">
          Last export: <code>{lastFile.name}</code> ({(lastFile.size / 1024).toFixed(1)} KB)
        </div>
      )}
      <div className="export-hint">
        Single self-contained file — open directly or embed via &lt;iframe&gt;. Loads React/flubber from CDN.
      </div>
    </div>
  );
}

// Minimal shell rendered by the exported web player (window.PLAYER_MODE).
// Same MorphAnimator, no editor chrome: canvas + state buttons + play/pause.
function PlayerApp() {
  const cfg = window.PLAYER_CONFIG || {};
  const animatorRef = useRef(null);
  const [current, setCurrent] = useState(ALL_STATE_NAMES[0]);
  const [playing, setPlaying] = useState(!!cfg.autoplay);
  const morphPreset = {
    easing: cfg.easing || "ease-in-out",
    durationMs: cfg.durationMs != null ? cfg.durationMs : null,
    easingBezier: cfg.easingBezier || null,
  };
  const stepMs = (morphPreset.durationMs
    || PRESETS.morph.easing[morphPreset.easing]?.duration
    || 800) + (cfg.holdMs != null ? cfg.holdMs : 1400);

  useEffect(() => {
    if (!playing) return;
    const iv = setInterval(() => {
      setCurrent(prev => {
        const next = ALL_STATE_NAMES[(ALL_STATE_NAMES.indexOf(prev) + 1) % ALL_STATE_NAMES.length];
        animatorRef.current?.transitionTo(next);
        return next;
      });
    }, stepMs);
    return () => clearInterval(iv);
  }, [playing, stepMs]);

  return (
    <div className="player">
      <div className="player-canvas" style={{ background: cfg.background || "transparent" }}>
        <MorphAnimator
          ref={animatorRef}
          initialState={ALL_STATE_NAMES[0]}
          morphPreset={morphPreset}
          width={CANVAS_SIZE.width}
          height={CANVAS_SIZE.height}
        />
      </div>
      <div className="player-row">
        {ALL_STATE_NAMES.map(s => (
          <button key={s} className={s === current ? "is-active" : ""}
            onClick={() => { setPlaying(false); animatorRef.current?.transitionTo(s); setCurrent(s); }}>
            {s}
          </button>
        ))}
        <button className="player-toggle" title={playing ? "Pause" : "Autoplay"}
          onClick={() => setPlaying(p => !p)}>
          {playing ? "❚❚" : "▶"}
        </button>
      </div>
    </div>
  );
}

function App() {
  const animatorRef = useRef(null);
  const initialState = ALL_STATE_NAMES[0];
  const [current, setCurrent] = useState(initialState);
  const [easing, setEasing] = useState("ease-in-out");
  // Custom easing curve: null = follow the preset (the editor shows the
  // preset's bezier equivalent); [x1,y1,x2,y2] = user-dragged custom curve,
  // which overrides the named ease everywhere (transitions + exports).
  const [bezier, setBezier] = useState(OVERRIDES.easingBezier || null);
  const effectiveEaseName = (PRESETS.morph.easing[easing]?.ease) || "easeInOutQuad";
  const presetBezier = EASE_BEZIER[effectiveEaseName] || EASE_BEZIER.easeInOutQuad;
  const editBezier = v => { setBezier(v); persistOverrides({ easingBezier: v }); };
  const resetBezier = () => { setBezier(null); persistOverrides({ easingBezier: null }); };
  // Idle anchor: null = per-part default (bottom-center), or a
  // transform-origin string. `anchorPick` arms a one-shot canvas click.
  const [idleAnchor, setIdleAnchorState] = useState(OVERRIDES.idleAnchor || null);
  const [anchorPick, setAnchorPick] = useState(false);
  const applyAnchor = (v) => {
    setIdleAnchorState(v);
    setAnchorPick(false);
    persistOverrides({ idleAnchor: v });
    animatorRef.current?.setIdleAnchor(v);
  };
  const [bgColor, setBgColor] = useState("#16181c");
  // Bump to re-render after mutating a particles config object in place.
  const [particleTick, setParticleTick] = useState(0);
  const initDepressOp = STATES["down"]?.paths?.["Ellipse_893"]?.opacity;
  const [depressOpacity, setDepressOpacity] = useState(initDepressOp ? Math.round(parseFloat(initDepressOp) * 100) : 30);

  // Duration: preset-driven until the user edits it directly (then custom
  // wins and persists).
  const presetMs = Math.round(PRESETS.morph.easing[easing]?.duration || 1200);
  const [durCustom, setDurCustom] = useState(OVERRIDES.durationMs != null);
  const [durationMs, setDurationMs] = useState(OVERRIDES.durationMs != null ? OVERRIDES.durationMs : presetMs);
  useEffect(() => { if (!durCustom) setDurationMs(presetMs); }, [presetMs, durCustom]);
  const editDuration = v => { setDurCustom(true); setDurationMs(v); persistOverrides({ durationMs: v }); };
  const resetDuration = () => { setDurCustom(false); setDurationMs(presetMs); persistOverrides({ durationMs: null }); };

  // Path editor state: canvas-click selection, live method overrides, and
  // role changes pending a reload (roles feed shared-id computation at init).
  const [selectedId, setSelectedId] = useState(null);
  const [methodOverrides, setMethodOverrides] = useState({ ...OVERRIDES.methods });
  const [pendingRoles, setPendingRoles] = useState({});
  const handleMethodChange = (id, m) => {
    const next = { ...methodOverrides };
    if (m === "auto") { delete next[id]; STRATEGY[id] = DETECTED_STRATEGY[id]; }
    else { next[id] = m; STRATEGY[id] = m; }
    setMethodOverrides(next);
    persistOverrides({ methods: next });
  };
  const handleRoleChange = (id, role) => {
    const activeRole = SHARED_IDS.includes(id) ? "shared" : "orphan";
    const nextPending = { ...pendingRoles };
    if (role === activeRole) delete nextPending[id];
    else nextPending[id] = role;
    setPendingRoles(nextPending);
    persistOverrides({ roles: { ...OVERRIDES.roles, [id]: role } });
  };
  // Highlight the selected path on canvas (shared element + every state's
  // orphan copy). filter is otherwise unused on these elements, so it's a
  // safe channel that won't fight the morph/idle transform writes.
  useEffect(() => {
    const els = [];
    if (selectedId) {
      const shared = document.getElementById(`path-${selectedId}`);
      if (shared) els.push(shared);
      ALL_STATE_NAMES.forEach(sn => {
        const o = document.getElementById(`orphan-${cssEscape(selectedId)}-${sn}`);
        if (o) els.push(o);
      });
    }
    els.forEach(el => { el.style.filter = "drop-shadow(0 0 2px rgba(38,118,136,0.95)) drop-shadow(0 0 6px rgba(38,118,136,0.55))"; });
    return () => els.forEach(el => { el.style.filter = ""; });
  }, [selectedId]);

  // Canvas click: an armed anchor pick consumes the click (drops the pivot
  // at that point); otherwise it's a path selection.
  const handlePick = (id, point) => {
    if (anchorPick && point) {
      applyAnchor(`${Math.round(point.x)}px ${Math.round(point.y)}px`);
      return;
    }
    setSelectedId(id);
  };
  // Anchor crosshair position (only for custom px anchors), as % of viewBox.
  const anchorMarker = (() => {
    const m = idleAnchor && idleAnchor.match(/^([\d.]+)px ([\d.]+)px$/);
    if (!m) return null;
    const [, vbX, vbY, vbW, vbH] = (VIEWBOX.match(/^([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+)$/) || [0, 0, 0, 300, 300]).map(Number);
    return { left: ((+m[1] - vbX) / vbW) * 100 + "%", top: ((+m[2] - vbY) / vbH) * 100 + "%" };
  })();

  // Idle preset override (Idle card): applies live, persists.
  const [idleSel, setIdleSel] = useState(OVERRIDES.idleOverride || "authored");
  const applyIdle = (v) => {
    setIdleSel(v);
    const kind = v === "authored" ? null : v;
    persistOverrides({ idleOverride: kind });
    animatorRef.current?.setIdleOverride(kind);
  };

  // X-ray mode: a wireframe layer INSIDE the live svg (so it rides the root
  // idle transform) showing every path's outline, bezier handle arms, and
  // anchor/control dots — sampled from the LIVE d attributes each frame, so
  // it x-rays mid-morph too. A translucent backdrop rect dims the fill
  // render without touching engine-owned element opacities. Per-element
  // transforms (rigid wrappers, element idles) are picked up via getCTM.
  const [xray, setXray] = useState(false);
  const bgColorRef = useRef(bgColor);
  bgColorRef.current = bgColor;
  useEffect(() => {
    if (!xray) return;
    const svgEl = animatorRef.current?.getSvgEl();
    if (!svgEl) return;
    const layer = document.createElementNS("http://www.w3.org/2000/svg", "g");
    layer.setAttribute("id", "xray-layer");
    layer.style.pointerEvents = "none";
    svgEl.appendChild(layer);
    const vb = svgEl.viewBox.baseVal;
    let raf, frame = 0;
    const isVisible = (el) => {
      let n = el;
      while (n && n !== svgEl) {
        const so = n.style && n.style.opacity;
        if (so !== "" && so != null && parseFloat(so) < 0.05) return false;
        n = n.parentElement;
      }
      return true;
    };
    const tick = () => {
      raf = requestAnimationFrame(tick);
      if (frame++ % 2) return; // 30fps is plenty for an inspector
      let html = `<rect x="${vb.x}" y="${vb.y}" width="${vb.width}" height="${vb.height}" fill="${bgColorRef.current}" opacity="0.82"/>`;
      const base = layer.getCTM();
      svgEl.querySelectorAll("path").forEach(el => {
        if (layer.contains(el)) return;
        const d = el.getAttribute("d");
        if (!d || !isVisible(el)) return;
        const segs = parsePath(d);
        let dots = "", arms = "";
        if (segs) {
          let prev = null;
          segs.forEach(s => {
            const pts = s.points;
            if (!pts.length) return;
            const anchor = pts[pts.length - 1];
            if (s.cmd === "C" || s.cmd === "Q") {
              const c1 = pts[0], c2 = pts.length > 2 ? pts[1] : pts[0];
              if (prev) arms += `<line class="xr-arm" x1="${prev[0]}" y1="${prev[1]}" x2="${c1[0]}" y2="${c1[1]}"/>`;
              arms += `<line class="xr-arm" x1="${anchor[0]}" y1="${anchor[1]}" x2="${c2[0]}" y2="${c2[1]}"/>`;
              pts.slice(0, -1).forEach(p => { dots += `<circle class="xr-c" cx="${p[0]}" cy="${p[1]}" r="1.1"/>`; });
            }
            dots += `<circle class="xr-a" cx="${anchor[0]}" cy="${anchor[1]}" r="1.5"/>`;
            prev = anchor;
          });
        }
        // Map the element's user space into the layer's (covers rigid-wrapper
        // g transforms + element idle CSS transforms).
        const m = el.getCTM();
        const rel = base && m ? base.inverse().multiply(m) : null;
        const tf = rel ? ` transform="matrix(${rel.a} ${rel.b} ${rel.c} ${rel.d} ${rel.e} ${rel.f})"` : "";
        html += `<g${tf}><path class="xr-line" d="${d}"/>${arms}${dots}</g>`;
      });
      layer.innerHTML = html;
    };
    tick();
    return () => { cancelAnimationFrame(raf); layer.remove(); };
  }, [xray]);

  const morphPreset = { easing, durationMs, easingBezier: bezier };

  // Resizable edit panel: drag the divider between canvas and panel.
  // Width persists globally (not per character) in its own localStorage key.
  const [panelW, setPanelW] = useState(() => {
    const v = parseInt(localStorage.getItem("morphPreviewPanelW"), 10);
    return Number.isFinite(v) ? Math.min(720, Math.max(340, v)) : 480;
  });
  const [dividerDrag, setDividerDrag] = useState(false);
  useEffect(() => {
    try { localStorage.setItem("morphPreviewPanelW", String(panelW)); } catch (e) { /* private mode */ }
  }, [panelW]);
  const startPanelDrag = (e) => {
    e.preventDefault();
    setDividerDrag(true);
    const startX = e.clientX, startW = panelW;
    const move = (ev) => setPanelW(Math.min(720, Math.max(340, startW + (startX - ev.clientX))));
    const up = () => {
      setDividerDrag(false);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  // Canvas background swatch palette.
  const swatches = [
    { name: "ink", color: "#16181c" },
    { name: "cream", color: "#e7e3d5" },
    { name: "grey", color: "#6b6d73" },
    { name: "orange", color: "#cf4f26" },
    { name: "steel", color: "#33657f" },
    { name: "navy", color: "#262e66" },
    { name: "green", color: "#1d7a50" },
    { name: "mustard", color: "#d3a41f" },
  ];

  const orphanCount = ALL_STATE_NAMES.reduce((acc, sn) => {
    const set = new Set(Object.keys(STATES[sn].paths).filter(id => !SHARED_IDS.includes(id)));
    set.forEach(id => acc.add(id));
    return acc;
  }, new Set()).size;

  return (
    <div className="app">
      <header className="header">
        <div className="header-row">
          <div>
            <h1>{TITLE}</h1>
            <p>{SUBTITLE}</p>
          </div>
          <StatStrip
            states={ALL_STATE_NAMES.length}
            shared={SHARED_IDS.length}
            orphans={orphanCount}
          />
        </div>
      </header>

      <main className="main" style={{ "--panel-w": panelW + "px" }}>
        <section className="canvas-card">
          <div className="canvas-tools">
            <button
              className={`xray-btn${xray ? " is-active" : ""}`}
              title="Wireframe view: path outlines + bezier anchor/control dots, live during morphs"
              onClick={() => setXray(x => !x)}>
              ◉ X-ray
            </button>
          </div>
          <div className={`canvas-surface${anchorPick ? " is-picking" : ""}`} style={{ background: bgColor }}>
            <div className="canvas-wrap">
              <MorphAnimator
                ref={animatorRef}
                initialState={initialState}
                morphPreset={morphPreset}
                width={CANVAS_SIZE.width}
                height={CANVAS_SIZE.height}
                onPickPath={handlePick}
              />
              {anchorMarker && (
                <div className="anchor-marker" style={anchorMarker} title={`idle anchor: ${idleAnchor}`} />
              )}
            </div>
          </div>
          <div className="state-row">
            {ALL_STATE_NAMES.map(s => (
              <button
                key={s}
                className={`state-btn${s === current ? " is-active" : ""}`}
                onClick={() => { animatorRef.current?.transitionTo(s); setCurrent(s); }}
              >
                {s}
              </button>
            ))}
          </div>
          {OVERLAYS && (
            <div className="overlay-row">
              <span className="overlay-label">Play once</span>
              {OVERLAY_EMOTIONS.map(em => (
                <button
                  key={em.name}
                  className="overlay-btn"
                  onClick={() => animatorRef.current?.playOverlay(em.name)}
                >
                  {em.label}
                </button>
              ))}
              {OVERLAY_GESTURES.map(g => (
                <button
                  key={`gesture-${g.name}`}
                  className="overlay-btn is-talk"
                  disabled={!gestureEnabled(g, current)}
                  title={gestureEnabled(g, current) ? "" : `Only in ${g.enabledStates.join(" / ")}`}
                  onClick={() => animatorRef.current?.playGesture(g.name)}
                >
                  {g.label || g.name}
                </button>
              ))}
              {OVERLAYS.talk && (
                <button
                  className="overlay-btn is-talk"
                  onClick={() => animatorRef.current?.playTalk()}
                >
                  {OVERLAYS.talk.label || "Talk"}
                </button>
              )}
              {OVERLAYS.lookAround && (
                <button
                  className="overlay-btn is-talk"
                  disabled={!(OVERLAYS.lookAround.enabledStates || []).includes(current)}
                  title={(OVERLAYS.lookAround.enabledStates || []).includes(current)
                    ? "" : `Only in ${(OVERLAYS.lookAround.enabledStates || []).join(" / ")}`}
                  onClick={() => animatorRef.current?.playLookAround()}
                >
                  {OVERLAYS.lookAround.label || "Look around"}
                </button>
              )}
            </div>
          )}
        </section>

        <div
          className={`panel-divider${dividerDrag ? " is-dragging" : ""}`}
          title="Drag to resize the edit panel"
          onPointerDown={startPanelDrag}
        />

        <aside className="controls">
          <PathEditor
            selectedId={selectedId}
            onSelect={setSelectedId}
            methodOverrides={methodOverrides}
            onMethodChange={handleMethodChange}
            pendingRoles={pendingRoles}
            onRoleChange={handleRoleChange}
          />
          <div className="control-card">
            <div className="control-label">Easing {bezier ? "· custom curve" : ""}</div>
            <select value={easing} onChange={e => setEasing(e.target.value)}>
              {Object.keys(PRESETS.morph.easing).map(k => <option key={k} value={k}>{k}</option>)}
            </select>
            <BezierEditor value={bezier || presetBezier} onChange={editBezier} />
            {bezier && (
              <button className="bez-reset" onClick={resetBezier}>
                ↺ Reset to preset curve ({effectiveEaseName})
              </button>
            )}
          </div>
          <DurationCard
            durationMs={durationMs}
            isCustom={durCustom}
            presetMs={presetMs}
            onEdit={editDuration}
            onReset={resetDuration}
          />
          <IdleCard value={idleSel} onChange={applyIdle} />
          <AnchorCard
            anchor={idleAnchor}
            pickArmed={anchorPick}
            onArmPick={() => setAnchorPick(p => !p)}
            onChange={applyAnchor}
          />
          <div className="control-card">
            <div className="control-label">Background</div>
            <div className="bg-controls">
              <input
                type="color"
                value={bgColor}
                onChange={e => setBgColor(e.target.value)}
                aria-label="Custom background color"
              />
              <div className="swatch-grid">
                {swatches.map(s => (
                  <button
                    key={s.name}
                    title={s.name}
                    onClick={() => setBgColor(s.color)}
                    className={`swatch${bgColor.toLowerCase() === s.color.toLowerCase() ? " is-active" : ""}`}
                    style={{ background: s.color }}
                  />
                ))}
              </div>
              <div className="pe-hint">
                Preview only — exports don't include the background (Swift & web
                render transparent; PNG uses it only when "transparent" is unchecked).
              </div>
            </div>
          </div>
          <ParticleControls
            stateName={current}
            animatorRef={animatorRef}
            onChange={() => setParticleTick(t => t + 1)}
          />
          {STATES["down"]?.paths?.["Ellipse_893"] && (
            <div className="control-card">
              <div className="control-label">Depress ellipse opacity</div>
              <div className="slider-row">
                <label>Opacity</label>
                <div className="slider-pair">
                  <input type="range" min="0" max="100" step="1" value={depressOpacity}
                    onChange={e => {
                      const v = +e.target.value;
                      setDepressOpacity(v);
                      const op = String(v / 100);
                      STATES["down"].paths["Ellipse_893"].opacity = op;
                      const el = document.querySelector('[id*="Ellipse_893"]');
                      if (el) {
                        el.style.opacity = op;
                        el.dataset.targetOpacity = op;
                      }
                    }} />
                </div>
                <span className="slider-value">{depressOpacity}%</span>
              </div>
            </div>
          )}
          <div className="control-card config-readout">
            <div className="control-label">Active config</div>
            <code>{easing} · {durationMs}ms{bezier ? " · custom curve" : ""}{idleAnchor ? ` · anchor ${idleAnchor}` : ""}</code>
          </div>
          <PngExportPanel
            animatorRef={animatorRef}
            current={current}
            morphPreset={morphPreset}
            bgColor={bgColor}
            xray={xray}
            onTransitioned={setCurrent}
          />
          <WebExportPanel
            morphPreset={morphPreset}
            bgColor={bgColor}
          />
          <ExportPanel
            easing={easing}
            morphPreset={morphPreset}
          />
        </aside>
      </main>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(
  window.PLAYER_MODE ? <PlayerApp /> : <App />
);
