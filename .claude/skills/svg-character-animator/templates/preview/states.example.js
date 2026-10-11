// Minimal example STATES_DATA — a circle morphing into a square.
// Copy this file, rename, and replace contents with your own states.
//
// Schema:
//   window.STATES_DATA = {
//     "<state-name>": {
//       paths: {
//         "<id>": {
//           tag: "path" | "circle" | "ellipse",
//           // path attributes (one of):
//           d: "...",                          // for tag=path
//           cx, cy, r: ...,                    // for tag=circle
//           cx, cy, rx, ry: ...,               // for tag=ellipse
//           // styling (free-form — copied to the rendered SVG element):
//           fill, stroke, strokeWidth, strokeLinecap, transform, ...,
//           // optional flags:
//           _orphan: true,                     // appears only in some states; fades in/out
//           _layer: "back" | "front",          // controls draw order for orphans
//         },
//         ...more ids...
//       },
//       defs: "<radialGradient ...>...</radialGradient>",   // optional SVG defs
//       orphanSVG: "<g>...</g>",                            // optional raw decorative SVG
//       idle: "sway" | "breathe" | "bob" | "shake" | "sway-twinkle",
//     },
//     ...more states (2 to 10)...
//   };
//
// Optional knobs (declare BEFORE engine.jsx loads):
//   window.PREVIEW_CONFIG = {
//     title: "...", subtitle: "...",
//     viewBox: "0 0 290 310",
//     size: { width: 290, height: 310 },
//   };
//   window.STRATEGY_OVERRIDES = { body: "MORPH" };      // force a strategy for a path
//   window.STRATEGY_PATH_PATCH = {                       // patch all states' copy of a path
//     body: { fill: "none", stroke: "#c8d0d8", strokeWidth: "1" }
//   };
//   window.PATH_OVERRIDES = {                            // path-editor contract (normally
//     roles: { nose: "orphan" },                         //   written by the UI via localStorage,
//     methods: { body: "CROSSFADE" },                    //   or embedded by the web-player export)
//     durationMs: 800,
//   };

window.PREVIEW_CONFIG = {
  title: "Circle → Square (example)",
  subtitle: "Smallest possible MorphAnimator instance",
  viewBox: "0 0 200 200",
  size: { width: 200, height: 200 },
};

window.STATES_DATA = {
  "circle": {
    paths: {
      shape: {
        tag: "circle",
        cx: "100", cy: "100", r: "60",
        fill: "#3958f5",
      },
    },
    idle: "breathe",
  },
  "square": {
    paths: {
      shape: {
        tag: "path",
        d: "M40 40 L160 40 L160 160 L40 160 Z",
        fill: "#3958f5",
      },
    },
    idle: "sway",
  },
};
