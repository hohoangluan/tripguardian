// Critters — 5 characters as one morphing state machine (cat, bluecat,
// rabbit, ghost, mouse). Source: Figma "svg skill demo", frames exported via
// MCP (exportAsync SVG_STRING with svgIdAttribute) — see
// scripts/figma-to-states.js for the workflow.
//
// Why this is the happy path the skill describes:
//   - All five frames share the SAME ten layer names (legL/legR, earL/earR,
//     body, eyeL/eyeR, mouth, handL/handR), so every part is a shared path —
//     zero orphans, and after normalization everything routes to TRANSFORM.
//   - Fills are flat hex (each character has its own palette). Flat hex fills
//     interpolate smoothly during the morph (runFillTween); only url() paint
//     servers snap at completion.
//
// Normalizations applied to the raw Figma export:
//   - Dropped the barely-visible drop-shadow filters Figma put on the rabbit
//     and mouse hands (0.1-alpha, 15px blur). They existed in only 2 of 5
//     states, and shared paths render ONCE at init — a per-state filter attr
//     can't follow the state anyway. Unify presentation attrs across states,
//     same rule as the gradient-id fix.
//   - mouth paths carry explicit fill: "none" (they're bare strokes; without
//     it the SVG default black fill would blob them).
//
// Idle design (bottom-center pivots at the characters' feet, "100px 196px" —
// canvas is 200×200 with feet at y≈195):
//   - cat      sway + relaxed blink (classic contented cat)
//   - bluecat  loafing flat — slow vertical breathing + sleepy blink
//   - rabbit   quick bob (hoppy) + blink
//   - ghost    float (floating character → center anchor, per the pivot rule)
//   - mouse    nervous: fast tiny sway + darting eyes (look-around) + blink

window.PREVIEW_CONFIG = {
  title: "Critters MorphAnimator",
  subtitle: "5-state Figma morph — cat, bluecat, rabbit, ghost, mouse",
  viewBox: "0 0 200 200",
  size: { width: 200, height: 200 },
  exportName: "CrittersAnimator",
};

const blink = (period, minScale) => ({
  kind: "blink",
  selectorAll: "#path-eyeL, #path-eyeR",
  period,
  blinkDuration: 0.14,
  minScale: minScale != null ? minScale : 0.12,
});
const FEET = "100px 196px";

window.STATES_DATA = {
  "cat": {
    paths: {
      legL: { tag: "rect", x: "80", y: "165", width: "21", height: "30", rx: "10.5", fill: "#D5B33F" },
      legR: { tag: "rect", x: "107", y: "165", width: "23", height: "30", rx: "11.5", fill: "#D5B33F" },
      earL: { tag: "path", d: "M58.4039 48.259C67.5407 45.6249 89.5413 63.759 88.8501 71.9581C88.159 80.1571 58.7005 91.2385 52.3021 87.4987C45.9038 83.759 49.267 50.8931 58.4039 48.259Z", fill: "#F1CA44" },
      earR: { tag: "path", d: "M158.005 51.9705C166.215 55.1608 166.666 86.4705 160.64 90.9388C154.613 95.4071 127.795 79.5096 127.795 73.2401C127.795 66.9705 149.794 48.7802 158.005 51.9705Z", fill: "#F1CA44" },
      body: { tag: "path", d: "M173 123.186C173 142.372 166.093 156.317 153 166.883C139.907 177.449 123.79 180 105 180C88.3565 180 75.1066 176.485 61 166.883C46.8934 157.281 37 144.425 37 123.186C37 101.947 42.7864 87.9585 56 77.5C69.2136 67.0415 81.5 60 105 60C128.5 60 143.811 69.1749 156 80.5C168.189 91.8251 173 104 173 123.186Z", fill: "#F1CA44" },
      eyeL: { tag: "circle", cx: "65", cy: "114", r: "3", fill: "black" },
      eyeR: { tag: "circle", cx: "123", cy: "117", r: "3", fill: "black" },
      mouth: { tag: "path", d: "M87 116C92 122 93.5 116 94.5 116C95.5 116 99 123 103 117", stroke: "black", strokeWidth: "3", strokeLinecap: "round", fill: "none" },
      handL: { tag: "circle", cx: "37.5", cy: "140.5", r: "11.5", fill: "#FFD853" },
      handR: { tag: "circle", cx: "162.5", cy: "149.5", r: "11.5", fill: "#FFD853" },
    },
    idle: {
      kind: "compound",
      parts: [
        { kind: "sway", duration: 2.4, amplitude: 1.4, origin: FEET },
        blink(3.5),
      ],
    },
  },
  "bluecat": {
    paths: {
      legL: { tag: "rect", x: "79", y: "171", width: "19", height: "24", rx: "9.5", fill: "#728ABA" },
      legR: { tag: "rect", x: "102", y: "170", width: "19", height: "24", rx: "9.5", fill: "#728ABA" },
      earL: { tag: "path", d: "M60.0191 101.525C72.0193 101.525 75.874 118.255 72.0194 125.525C68.1648 132.794 53.9356 131.476 49.5192 125.525C45.1028 119.573 48.0189 101.525 60.0191 101.525Z", fill: "#8AA3D4" },
      earR: { tag: "path", d: "M141.966 100.686C152.966 100.686 154.928 118.599 152.467 125.686C150.006 132.773 133.5 130.865 129.967 125.686C126.434 120.507 130.966 100.686 141.966 100.686Z", fill: "#8AA3D4" },
      body: { tag: "path", d: "M190 149.256C190 168.581 176.572 183 154.512 183C132.452 183 116.147 180.985 93.1281 180.985C70.109 180.985 60.0381 183 42.2943 180.985C24.5504 178.971 14 166.754 14 147.428C14 128.102 31.2643 116.015 47.5695 116.015C63.8747 116.015 76.8229 118.029 99.3624 118.029C121.902 118.029 129.879 116.015 150.5 116.015C171.121 116.015 190 129.93 190 149.256Z", fill: "#8AA3D4" },
      eyeL: { tag: "ellipse", cx: "51", cy: "157.5", rx: "3", ry: "2.5", fill: "black" },
      eyeR: { tag: "ellipse", cx: "143", cy: "160.5", rx: "3", ry: "2.5", fill: "black" },
      mouth: { tag: "path", d: "M76.5 158.5C83 163 89.5 158.5 96 158.5C102.5 158.5 106.5 163 115 158.5", stroke: "black", strokeWidth: "3", strokeLinecap: "round", fill: "none" },
      handL: { tag: "circle", cx: "18.5", cy: "163.5", r: "10.5", fill: "#ADC1E9" },
      handR: { tag: "circle", cx: "181.5", cy: "168.5", r: "10.5", fill: "#ADC1E9" },
    },
    idle: {
      kind: "compound",
      parts: [
        { kind: "breathe-y", duration: 4.2, amplitude: 0.02, origin: FEET },
        blink(4.5, 0.1),
      ],
    },
  },
  "rabbit": {
    paths: {
      legL: { tag: "rect", x: "81", y: "170", width: "19", height: "24", rx: "9.5", fill: "#E999C4" },
      legR: { tag: "rect", x: "101", y: "171.768", width: "19", height: "24", rx: "9.5", transform: "rotate(-11.4382 101 171.768)", fill: "#E999C4" },
      earL: { tag: "path", d: "M93.6226 13.3283C121.721 13.5413 108.572 60.318 105.578 67.9822C102.585 75.6465 86.1823 74.9974 81.1111 69.593C76.0399 64.1885 65.5239 13.1152 93.6226 13.3283Z", fill: "#F8ACD5" },
      earR: { tag: "path", d: "M142.14 20.7557C168.001 31.0578 138.528 70.6955 132.501 75.2767C126.474 79.8579 109.296 69.978 109.296 63.55C109.296 57.1221 116.28 10.4535 142.14 20.7557Z", fill: "#F8ACD5" },
      body: { tag: "path", d: "M162.75 126C156.75 145.186 133.552 147 131.25 156.883C128.949 166.766 128.752 180 100.75 180C72.748 180 73.7503 164.383 69.7503 156.883C65.7503 149.383 46.0981 152 37.7511 126C29.4042 100 35.751 82.5 49.2524 69C62.7539 55.5 77.2502 50 100.75 50C124.25 50 142.252 60 155.252 74.5C168.252 89 168.75 106.814 162.75 126Z", fill: "#F8ACD5" },
      eyeL: { tag: "circle", cx: "70", cy: "106", r: "3", fill: "black" },
      eyeR: { tag: "circle", cx: "125", cy: "106", r: "3", fill: "black" },
      mouth: { tag: "path", d: "M90.5 104.5C91 105.5 92.5 108 96.5 108C100.5 108 102 105.5 102.5 104.5", stroke: "black", strokeWidth: "3", strokeLinecap: "round", fill: "none" },
      handL: { tag: "ellipse", cx: "86.5", cy: "147", rx: "10.5", ry: "10", fill: "#FFC7E5" },
      handR: { tag: "ellipse", cx: "109.5", cy: "147", rx: "10.5", ry: "10", fill: "#FFC7E5" },
    },
    idle: {
      kind: "compound",
      parts: [
        { kind: "bob", duration: 1.2, amplitude: 3 },
        blink(3.2),
      ],
    },
  },
  "ghost": {
    paths: {
      legL: { tag: "rect", x: "82", y: "152.338", width: "15", height: "22", rx: "7.5", transform: "rotate(-5.1193 82 152.338)", fill: "#F0F0F0" },
      legR: { tag: "rect", x: "106", y: "152.338", width: "15", height: "22", rx: "7.5", transform: "rotate(-5.1193 106 152.338)", fill: "#F0F0F0" },
      earL: { tag: "path", d: "M69.4355 42.0965C78.603 41.1148 100.678 47.8734 99.984 50.9292C99.2905 53.985 69.7331 58.115 63.3132 56.7212C56.8934 55.3274 60.2679 43.0782 69.4355 42.0965Z", fill: "white" },
      earR: { tag: "path", d: "M123.61 45.9469C131.996 48.4419 137.403 60.1997 132.328 60.9101C127.254 61.6205 98.991 51.4267 97.9947 49.0866C96.9984 46.7465 115.223 43.4518 123.61 45.9469Z", fill: "white" },
      body: { tag: "path", d: "M150.784 113.707C150.784 134.008 160 164.677 140.5 160.5C121 156.323 112.933 163.5 95.364 163.5C77.7949 163.5 76.5286 155.5 51.0285 158.677C25.5283 161.855 41 130.451 41 107.978C41 85.5047 44.1669 66.8016 51.0284 54.5431C57.8898 42.2846 70.5572 28 95.3641 28C120.171 28 134.949 38.6713 143.922 57.6273C152.895 76.5832 150.784 93.4066 150.784 113.707Z", fill: "white" },
      eyeL: { tag: "circle", cx: "68", cy: "73", r: "3", fill: "black" },
      eyeR: { tag: "circle", cx: "110", cy: "73", r: "3", fill: "black" },
      mouth: { tag: "path", d: "M85 73C86 73 88 73 88.5 73C89 73 92 73 93 73", stroke: "black", strokeWidth: "3", strokeLinecap: "round", fill: "none" },
      handL: { tag: "circle", cx: "39", cy: "112", r: "7", fill: "#E6E6E6" },
      handR: { tag: "circle", cx: "153", cy: "119", r: "7", fill: "#E6E6E6" },
    },
    // Floating character → buoyant float with a center anchor (the skill's
    // floating-pivot rule), plus an occasional blink.
    idle: {
      kind: "compound",
      parts: [
        { kind: "float", duration: 2.4, amplitude: 4, drift: 3, rotate: 2 },
        blink(3.8),
      ],
    },
  },
  "mouse": {
    paths: {
      legL: { tag: "rect", x: "76.3784", y: "170", width: "19", height: "24", rx: "9.5", fill: "#B6B6B6" },
      legR: { tag: "rect", x: "108.378", y: "171.768", width: "19", height: "24", rx: "9.5", transform: "rotate(-11.4382 108.378 171.768)", fill: "#B6B6B6" },
      earL: { tag: "path", d: "M50.3784 18C86.3784 1.49996 105.43 48.6451 96.9299 64.6452C88.4296 80.6452 71.93 89.6468 54.9301 83.646C37.9301 77.6451 14.3784 34.5 50.3784 18Z", fill: "#C8C8C8" },
      earR: { tag: "path", d: "M164.165 22.9252C196.665 38.9526 184.025 78.637 159.665 87.4252C135.306 96.2134 125.627 86.4252 115.165 69.4252C104.703 52.4251 131.665 6.89776 164.165 22.9252Z", fill: "#C8C8C8" },
      body: { tag: "path", d: "M151.378 130C144.378 141.5 138.878 143.266 138.878 157.883C138.878 172.5 129.131 181 101.129 181C73.1264 181 65.3784 172.5 62.3784 157.883C59.3784 143.266 52.8783 142 44.8783 124.5C36.8783 107 42.3778 83.9993 53.3781 73C64.3784 62.0007 82.1287 55.5 101.129 55.5C120.128 55.5 142.63 62 151.378 79C160.127 96 158.378 118.5 151.378 130Z", fill: "#C8C8C8" },
      eyeL: { tag: "circle", cx: "70.3784", cy: "107", r: "3", fill: "black" },
      eyeR: { tag: "circle", cx: "125.378", cy: "107", r: "3", fill: "black" },
      mouth: { tag: "path", d: "M94 109.5C95 108.5 97 107 97.5 107C98 107 100.5 109 101.5 109.5", stroke: "black", strokeWidth: "3", strokeLinecap: "round", fill: "none" },
      handL: { tag: "ellipse", cx: "59.8784", cy: "148", rx: "10.5", ry: "10", fill: "#DCDCDC" },
      handR: { tag: "ellipse", cx: "141.878", cy: "143", rx: "10.5", ry: "10", fill: "#DCDCDC" },
    },
    // Nervous: quick tiny sway, face darting around, frequent blinks.
    // The look-around targets the WHOLE face (eyes + mouth): these eyes are
    // the entire feature (no whites for pupils to move within), so the gaze
    // shift is really a face shift — translate-type idles must move every
    // face part together or the mouth visibly stays behind. Blink stays
    // eyes-only (a squish is a per-part animation, not a position change).
    idle: {
      kind: "compound",
      parts: [
        { kind: "sway", duration: 0.9, amplitude: 0.8, origin: FEET },
        { kind: "look-around", selectorAll: "#path-eyeL, #path-eyeR, #path-mouth", cycleDuration: 4, dx: 3, dxLeft: 3, dy: 1.5 },
        blink(2.2, 0.15),
      ],
    },
  },
};
