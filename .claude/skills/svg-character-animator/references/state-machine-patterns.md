# State Machine Patterns

How to wire up a full N×N state machine for SVG morphs — any state to any state, with optional auto-sequencing modes. Read for any multi-state (3+) component.

## The data model

Every state is an object containing:
- A unique `name` (string key)
- A map of sub-path id → SVG path data
- An optional `idle` config (preset name + custom prompt nuance)

```js
const states = {
  neutral: {
    paths: { "shape-1": "M...", "shape-2": "M...", ... },
    idle: { preset: "sway", custom: "eyes blink every 3-5s" },
  },
  happy: {
    paths: { "shape-1": "M...", "shape-2": "M...", ... },
    idle: { preset: "bob", custom: "" },
  },
  sleepy: {
    paths: { ... },
    idle: { preset: "breathe", custom: "" },
  },
  // ... up to 10 states
};
```

All states must share the same set of sub-path ids. Validate this at component mount and warn loudly in the console if there's a mismatch.

## The transition API

The component exposes both controlled and imperative APIs:

```jsx
<MorphAnimator
  states={states}
  currentState="neutral"   // controlled
  morphPreset={{ easing: "gentle", scenario: "icon-toggle", aesthetic: "playful" }}
/>

// OR imperative via ref
const ref = useRef();
ref.current.transitionTo("happy");
```

Both modes wire to the same internal `runTransition(fromState, toState)` function.

## Implementing N×N transitions

The naive approach: pre-compute every (from, to) pair. For 10 states that's 100 transitions to define. Don't do this — the animation is the same shape regardless of which state we're coming from.

Right approach: a single `runTransition` function that:

1. Reads the current rendered paths from the DOM (the actual current state, even mid-morph)
2. Targets the destination state's paths
3. Applies the morph timeline based on the current `morphPreset`
4. Updates `currentStateRef` only when the morph completes

```js
const runTransition = (toStateName) => {
  const toPaths = states[toStateName].paths;
  const ids = Object.keys(toPaths);

  const tl = gsap.timeline({
    onComplete: () => {
      currentStateRef.current = toStateName;
      switchIdleTo(toStateName);  // see idle-animation-recipes.md
    },
  });

  // Idle ramp-down (see idle-animation-recipes.md — 0.1 floor over 40% of duration)
  tl.to(idleAmplitudeRef.current, { value: 0.1, duration: morphConfig.duration * 0.4 }, 0);

  // The morph itself — all shared paths in unison
  ids.forEach((id) => {
    const interp = flubber.interpolate(currentD(id), toPaths[id]);  // or the TRANSFORM tween
    tl.to({ t: 0 }, {
      t: 1,
      duration: morphConfig.duration,
      ease: morphConfig.easing,
      onUpdate() { byId(id).setAttribute("d", interp(this.targets()[0].t)); },
    }, 0);
  });

  // Idle ramp-up
  tl.to(idleAmplitudeRef.current, {
    value: 1.0,
    duration: morphConfig.duration * 0.4,
  }, `>-${morphConfig.duration * 0.4}`);  // overlap with end of morph
};
```

## Interrupting in-flight morphs

If the user calls `transitionTo("happy")` while a `neutral → sleepy` morph is running, what should happen?

**Default behavior (recommended):** kill the in-flight morph, start the new one from current rendered paths. The visual handoff is smooth because the new tween reads whatever `d` each path currently has as its starting point — we're already in path-data space.

```js
const runTransition = (toStateName) => {
  if (activeTl.current) activeTl.current.kill();
  activeTl.current = gsap.timeline({ ... });
  // ...
};
```

**Queue mode (alternative):** ignore new requests until current morph completes. Useful for kiosk/auto-play modes where transitions are scripted.

Expose both via prop: `interruptMode: "kill" | "queue"`.

## Auto-sequencing modes

If the user wants the component to cycle states automatically (no external triggering):

```jsx
<MorphAnimator
  states={states}
  autoSequence={{ mode: "linear", interval: 3000 }}
/>
```

Modes:
- `"linear"` — visit states in declaration order, loop back to start
- `"random"` — pick a random non-current state each interval
- `"weighted"` — accept a probability map: `{ neutral: 0.5, happy: 0.3, sleepy: 0.2 }`
- `"shuffle"` — visit each state once in random order, then reshuffle (dreamcore-friendly)

Implementation:
```js
useEffect(() => {
  if (!autoSequence) return;
  const tick = () => {
    const next = pickNext(autoSequence.mode, currentStateRef.current, states, autoSequence);
    runTransition(next);
  };
  const timer = setInterval(tick, autoSequence.interval);
  return () => clearInterval(timer);
}, [autoSequence]);
```

## Transition guards (advanced)

Some state pairs shouldn't be allowed. For example: a snowman in "melted" state shouldn't morph back to "neutral" without going through "freezing" first.

```jsx
<MorphAnimator
  states={states}
  transitionGuard={(from, to) => {
    if (from === "melted" && to === "neutral") return "freezing";
    if (from === "asleep" && to === "excited") return "waking";
    return to;  // allow the requested transition
  }}
/>
```

The guard returns either the destination state (allow), an alternate state (redirect), or `null` (block). Useful for narrative animations and games.

## Initial render

On first mount, the SVG should render the initial state's paths *immediately*, not animate in from nothing. The first morph happens only when `currentState` changes or `transitionTo` is called.

```jsx
const [currentState, setCurrentState] = useState(props.currentState || Object.keys(states)[0]);

// In JSX, render paths from `states[currentState].paths` directly
<svg viewBox="...">
  {Object.entries(states[currentState].paths).map(([id, d]) => (
    <path key={id} id={id} d={d} fill="..." />
  ))}
</svg>
```

The morph only modifies the `d` attribute via imperative `setAttribute` after mount.

## Common pitfalls

- **Forgetting to switch idle on state change.** If state changes without `runTransition` (e.g., on first mount with non-default initial state), idle still needs to be set up for that state.
- **Stale closures in auto-sequence.** Use refs for `currentStateRef` not state — the `setInterval` closure captures the initial state value otherwise.
- **Multiple `currentStateRef` updates from interrupted morphs.** Only update on `onComplete`, not optimistically. Otherwise rapid transitions create incorrect "current" state.
