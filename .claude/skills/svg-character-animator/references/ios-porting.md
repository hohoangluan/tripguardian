# iOS Porting Guide

How to take the React + flubber morph component and port it to native SwiftUI. The two-strategy architecture (TRANSFORM, MORPH) carries over directly; only the runtime layer changes.

## The fundamental difference

**JavaScript:** imperative DOM mutation. We loop `requestAnimationFrame`, compute new `d` strings, call `setAttribute('d', newD)`.

**SwiftUI:** declarative animation. You define a custom `Shape` whose `animatableData` is the morph progress (0...1), and SwiftUI's animation system drives the value. The `path(in:)` method computes the interpolated path each frame.

SwiftUI's declarative model is actually cleaner than the JS imperative approach once you wrap your head around it. The two-strategy taxonomy (TRANSFORM, MORPH) ports almost line-for-line; fill differences snap at morph end, same as the web version.

## What carries over directly

The architecture is platform-agnostic. Port these to Swift unchanged:

- **Strategy detection** (TRANSFORM or MORPH) — same decision tree as web
- **Path normalization** (H/V → L, relative → absolute, primitives → bezier) — plain string/math work
- **Structure fingerprinting** — compare command sequences across states
- **Point-by-point interpolation** for TRANSFORM strategy — trivial `lerp` in Swift
- **Transform attribute parsing and interpolation** — same parser, just in Swift
- **Multi-subpath splitting** — split a `d` string into N components, render each as own `Shape`
- **Orphan handling** — render all states' decorations, opacity via `.opacity(state == current ? 1 : 0)`
- **Bottom-center pivot** — use `UnitPoint(x: 0.5, y: 1.0)` in `.rotationEffect(_, anchor:)` and `.scaleEffect(_, anchor:)`
- **Idle×morph amplitude blending** — `@State var idleAmplitude: Double` driven during morphs

## What needs to be rebuilt

### SVG path → SwiftUI Path conversion

SVG `M`, `L`, `C`, `Q`, `Z` map directly to SwiftUI Path's `move(to:)`, `addLine(to:)`, `addCurve(to:control1:control2:)`, `addQuadCurve(to:control:)`, `closeSubpath()`. Write a `Path(svgD: String)` initializer once and reuse forever.

```swift
extension Path {
    init(svgD: String) {
        self.init()
        let segments = parseSVGPath(svgD)  // your parser
        for seg in segments {
            switch seg.cmd {
            case .move(let p): move(to: p)
            case .line(let p): addLine(to: p)
            case .curve(let to, let c1, let c2):
                addCurve(to: to, control1: c1, control2: c2)
            case .quad(let to, let c):
                addQuadCurve(to: to, control: c)
            case .close: closeSubpath()
            }
        }
    }
}
```

For best performance, do this conversion **offline at build time** and bundle the parsed segments as Swift arrays. The runtime then just lerps control points.

### The Animatable Shape

This is SwiftUI's equivalent of our `runTransformTween` function. Custom `Shape` with `Animatable` conformance:

```swift
struct MorphShape: Shape, Animatable {
    let fromSegments: [PathSegment]
    let toSegments: [PathSegment]
    var progress: Double

    var animatableData: Double {
        get { progress }
        set { progress = newValue }
    }

    func path(in rect: CGRect) -> Path {
        var path = Path()
        // fromSegments and toSegments are guaranteed to have same structure
        // (this Shape only used for TRANSFORM strategy)
        for i in 0..<fromSegments.count {
            let from = fromSegments[i]
            let to = toSegments[i]
            // Lerp each control point
            switch (from, to) {
            case (.move(let a), .move(let b)):
                path.move(to: lerp(a, b, progress))
            case (.curve(let aTo, let aC1, let aC2), .curve(let bTo, let bC1, let bC2)):
                path.addCurve(
                    to: lerp(aTo, bTo, progress),
                    control1: lerp(aC1, bC1, progress),
                    control2: lerp(aC2, bC2, progress)
                )
            case (.line(let a), .line(let b)):
                path.addLine(to: lerp(a, b, progress))
            case (.close, .close):
                path.closeSubpath()
            default:
                break  // structure mismatch — shouldn't happen
            }
        }
        return path
    }
}

func lerp(_ a: CGPoint, _ b: CGPoint, _ t: Double) -> CGPoint {
    CGPoint(x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t)
}
```

Drive with `withAnimation`:

```swift
withAnimation(.easeInOut(duration: 1.2)) {
    progress = 1.0
}
```

SwiftUI handles the timing.

### Fill differences across states

The skill no longer crossfades between fills. When `fromPath.fill` differs from `toPath.fill`, snap at morph completion:

```swift
.onChange(of: progress) { _, newValue in
    if newValue >= 1.0 { currentFill = toGradient }
}
```

If you really need a smooth transition between two visibly-different gradients, normalize the source upstream (use the same paint server and animate stop colors) rather than swap paint servers at runtime.

### MORPH (when paths have genuinely different structure)

This is the hard one. SwiftUI has no equivalent of flubber. Three options, ranked by quality:

**Option 1: Pre-match offline.**

Best approach. In the web prototype, the user finalizes the morph design. Once happy, freeze the matched-path ordering. Write a build script that:

1. Reads each state's SVG
2. For each shared id, parses the path data into control points
3. If structures match, emits the points as `Swift [PathSegment]` arrays
4. If structures differ (MORPH case), runs a one-time polygon resampling to make them match, emits the resampled segments

The Swift runtime then only ever runs TRANSFORM-strategy interpolation. No library needed. This is how Apple's SF Symbols animation pipeline works.

**Option 2: Runtime polygon resampling.**

Port flubber's algorithm to Swift: sample both paths at fixed segment lengths via `Path.trimmedPath` and `currentPoint`, pad the shorter, interpolate. About 100 lines of Swift. Lower quality than offline pre-matching (loses bezier curves) but doesn't require a build pipeline.

**Option 3: WKWebView escape hatch.**

Embed the React component in a WKWebView. Quick but not native, not available in widget extensions, and adds significant overhead. Use only for prototyping or non-critical previews.

### Gradient differences across states

SwiftUI's `LinearGradient` and `RadialGradient` can be interpolated *between color stops* if the gradient definitions share structure (same stop count, same positions). Take advantage of this: normalize gradients in source SVGs so only the stop colors differ, then SwiftUI's built-in `Animatable` does the tween for you. If gradients genuinely differ in structure, snap the destination gradient at morph completion (same fill-snap pattern as the web version).

### Multi-subpath splitting

In SVG, you split the `d` into separate `<path>` elements. In SwiftUI, you build a single `Path` with multiple `move(to:)` calls and let SwiftUI render it.

For **animation**, you actually want to split into multiple `MorphShape` views — one per stroke — so each can animate independently. The split happens at parse time, not render time.

```swift
struct HandShape: View {
    let strokeSegments: [[PathSegment]]  // 4 strokes for a hand
    let progress: Double
    let strokeStyle: StrokeStyle

    var body: some View {
        ZStack {
            ForEach(strokeSegments.indices, id: \.self) { i in
                MorphShape(fromSegments: ..., toSegments: ..., progress: progress)
                    .stroke(style: strokeStyle)
            }
        }
    }
}
```

## What's harder on iOS

### Stroke-cap preservation during morph

SwiftUI's `.stroke(style: StrokeStyle(lineCap: .round))` works on static paths. During morph, if your interpolated path has degenerate segments (zero-length lines), line caps render strangely. Same problem we hit in the web version. Solution: keep paths above a minimum length throughout the morph (TRANSFORM strategy naturally does this).

### Precise transform-origin

SwiftUI's `.rotationEffect(_, anchor:)` uses `UnitPoint` (0...1 within the view bounds), which is what you want. But SVG's `transform="rotate(deg cx cy)"` uses absolute coordinates within the viewBox. Convert:

```swift
let anchor = UnitPoint(x: cx / viewBoxWidth, y: cy / viewBoxHeight)
```

Easy but easy to forget.

### Continuous idle animation in widgets

If you're going from this to WidgetKit (e.g., for Uu's WidgetZoo work): widgets don't allow continuous animations except via timeline reloads. The idle animation pattern from the web version doesn't translate directly — you'd need to either:

- Use a `Live Activity` with `TimelineView(.animation)` for continuous animation (iOS 17+)
- Pre-bake N frames at design time and cycle through them as the widget timeline ticks
- Accept that widgets are static between timeline reloads (every 15+ minutes)

The TRANSFORM strategy is well-suited to this — no library, no continuous JS interpreter, just bundled control point arrays the widget runtime interpolates.

## Recommended pipeline for production

If shipping to both web and iOS:

1. **Design and iterate in the web prototype** — fastest feedback loop with flubber and the v7 architecture
2. **Freeze the matched-path correspondences and timing** once the user signs off
3. **Run a build script** that emits Swift bundles:
   - Per-state control point arrays for each shared id
   - Strategy assignments (so the Swift runtime knows TRANSFORM vs MORPH per shared id)
   - Per-state idle preset configs
   - Orphan SVG `d` strings as static `Path` constants
4. **Write the Swift runtime** as a small SwiftUI library that consumes the bundle
5. **The web version remains the source of truth for animation design.** iOS is a faithful port, not an independent implementation.

This mirrors how Apple's design team works for SF Symbols animations: design in their internal authoring tool, export, native runtime renders the export.

## Skeleton file structure

```
MorphAnimator/                          [iOS Swift package]
├── Path+SVG.swift                       — Parse `d` strings to Swift PathSegment enums
├── PathNormalizer.swift                 — H/V → L, relative → absolute, primitives → bezier
├── PathFingerprint.swift                — Structure detection for strategy assignment
├── StrategyDetector.swift               — Returns TRANSFORM or MORPH per shared id
├── Shapes/
│   ├── MorphableShape.swift             — Animatable shape for TRANSFORM
│   └── MultiPathShape.swift             — Container for multi-subpath strokes
├── Idle/
│   └── IdleAnimator.swift               — TimelineView-driven, amplitude-blended
├── Generated/
│   └── States.swift                     — Build script output: control points per state
└── MorphAnimatorView.swift              — Composition: shapes + idle + transition controller
```

## Tooling

- **`PocketSVG`** — community-maintained SVG → CGPath parser. Mature, works with Swift Package Manager.
- **`SwiftUIShape`** — community helpers for animatable shape protocols.
- **WKWebView** — for Strategy 3 escape hatch.

## What does NOT translate

- The React-specific render/animation separation (rendering once, mutating via refs) is irrelevant on iOS — SwiftUI's declarative model handles this automatically via `@State` and `Animatable`.
- The morph library choice — you're writing your own bezier interpolator for TRANSFORM and your own polygon sampler (or pre-matched offline data) for MORPH.
- The demo wrapper with dropdowns and color picker — design this fresh for iOS using SwiftUI controls.
