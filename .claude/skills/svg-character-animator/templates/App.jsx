/**
 * App.jsx — demo wrapper template
 *
 * Required for every generated MorphAnimator output. Includes:
 *   - State buttons (one per state, click to transition)
 *   - Easing/scenario/aesthetic dropdowns
 *   - Background color picker + swatch palette
 *   - Strategy panel showing per-id assignments (for debugging quality issues)
 */

import React, { useRef, useState } from "react";
import MorphAnimator, {
  STATE_NAMES,
  STRATEGY_DEBUG,
  SHARED_IDS_DEBUG,
} from "./MorphAnimator.jsx";

const STRATEGY_COLOR = {
  TRANSFORM: { fg: "#0a6b3a", bg: "#dcf5e6" },
  MORPH: { fg: "#8a5a00", bg: "#fdf1cf" },
};

const PRESET_OPTIONS = {
  easing: ["snappy", "gentle", "bouncy", "dreamy"],
  scenario: ["icon-toggle", "page-transition", "character-emotion-shift", "ambient-loop"],
  aesthetic: ["none", "playful", "vintage", "floating"],
};

const SWATCHES = [
  { name: "neutral",   color: "#fafbfd" },
  { name: "white",     color: "#ffffff" },
  { name: "midnight",  color: "#0f1729" },
  { name: "warm",      color: "#fff4e0" },
  { name: "mint",      color: "#e0f5e9" },
  { name: "lavender",  color: "#ede4ff" },
  { name: "blush",     color: "#ffe4ec" },
  { name: "ink",       color: "#1a1a1a" },
];

export default function App() {
  const animatorRef = useRef(null);
  const [current, setCurrent] = useState(STATE_NAMES[0]);
  const [easing, setEasing] = useState("gentle");
  const [scenario, setScenario] = useState("character-emotion-shift");
  const [aesthetic, setAesthetic] = useState("playful");
  const [bgColor, setBgColor] = useState("#fafbfd");

  const morphPreset = { easing, scenario, aesthetic };
  const stateNames = STATE_NAMES;

  return (
    <div>
      {/* Controls bar */}
      <div style={{
        background: "white", padding: "12px 24px",
        borderBottom: "1px solid #e1e4e8",
        display: "flex", flexWrap: "wrap", gap: 16, alignItems: "center"
      }}>
        <ControlGroup label="Easing" value={easing} options={PRESET_OPTIONS.easing} onChange={setEasing} />
        <ControlGroup label="Scenario" value={scenario} options={PRESET_OPTIONS.scenario} onChange={setScenario} />
        <ControlGroup label="Aesthetic" value={aesthetic} options={PRESET_OPTIONS.aesthetic} onChange={setAesthetic} />

        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <label style={{ fontSize: 12, color: "#666", fontWeight: 500 }}>Background</label>
          <input
            type="color" value={bgColor} onChange={e => setBgColor(e.target.value)}
            style={{ width: 36, height: 28, padding: 0, border: "1px solid #ddd", borderRadius: 6, cursor: "pointer" }}
          />
          <div style={{ display: "flex", gap: 4 }}>
            {SWATCHES.map(s => (
              <button key={s.name} title={s.name} onClick={() => setBgColor(s.color)}
                style={{
                  width: 22, height: 22, borderRadius: 6,
                  border: bgColor.toLowerCase() === s.color.toLowerCase() ? "2px solid #4a90e2" : "1px solid #ddd",
                  background: s.color, cursor: "pointer", padding: 0,
                }}
              />
            ))}
          </div>
        </div>

        <div style={{ marginLeft: "auto", color: "#888", fontSize: 12 }}>
          <code>{easing} × {scenario} × {aesthetic}</code>
        </div>
      </div>

      {/* Strategy panel (debug info) */}
      <div style={{
        fontSize: 11, color: "#666", padding: "8px 24px",
        background: "#fffbe6", borderBottom: "1px solid #f0e6b0",
        display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center"
      }}>
        <strong style={{ marginRight: 4 }}>Strategy per shared path:</strong>
        {SHARED_IDS_DEBUG.map(id => {
          const s = STRATEGY_DEBUG[id];
          const c = STRATEGY_COLOR[s] || { fg: "#666", bg: "#eee" };
          return (
            <span key={id} style={{
              padding: "2px 8px", borderRadius: 999,
              fontFamily: "ui-monospace, Menlo, monospace",
              background: c.bg, color: c.fg
            }}>
              {id} · {s.toLowerCase()}
            </span>
          );
        })}
      </div>

      {/* Canvas with background picker applied */}
      <div style={{ padding: 24, textAlign: "center" }}>
        <div style={{
          display: "inline-block", border: "1px solid #eee", borderRadius: 12, padding: 16,
          background: bgColor, transition: "background 0.25s ease"
        }}>
          <MorphAnimator ref={animatorRef} initialState={STATE_NAMES[0]} morphPreset={morphPreset} />
        </div>

        {/* State buttons */}
        <div style={{ marginTop: 20, display: "flex", gap: 8, justifyContent: "center", flexWrap: "wrap" }}>
          {stateNames.map(s => (
            <button key={s}
              onClick={() => { animatorRef.current?.transitionTo(s); setCurrent(s); }}
              style={{
                padding: "8px 16px", borderRadius: 8, border: "1px solid #ddd",
                background: s === current ? "#4a90e2" : "white",
                color: s === current ? "white" : "#333",
                cursor: "pointer", fontWeight: 500
              }}>
              {s}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function ControlGroup({ label, value, options, onChange }) {
  return (
    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
      <label style={{ fontSize: 12, color: "#666", fontWeight: 500 }}>{label}</label>
      <select value={value} onChange={e => onChange(e.target.value)}
        style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid #ddd", fontSize: 13, background: "white" }}>
        {options.map(o => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  );
}
