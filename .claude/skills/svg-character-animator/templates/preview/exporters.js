// Export utilities for the SVG morph-animator preview shell.
// Plain JS (no Babel needed). Exposes window.PreviewExporters:
//   recordPngSequence — capture a live transition frame-by-frame → zip of PNGs
//   buildPlayerHtml   — bundle states + engine + app into ONE standalone .html
//                       web-animation player (React/flubber from CDN)
//   buildZip          — minimal store-only (uncompressed) ZIP writer
//   downloadBlob      — trigger a browser download
//
// Why single-file HTML for "web animation export" instead of a keyframe-baked
// JSON format? The morph engine's per-path strategy detection, rigid-body
// tweens, and idle blending can't be represented as pre-baked keyframed
// vertices without huge files and loss of interactivity. A self-contained HTML
// player replays the EXACT same engine with the user's tuned settings, stays
// one file, and embeds anywhere via <iframe>. PNGs are inside a store-only zip
// (PNG is already compressed; deflate would buy nothing).

(function () {

  // ---------- store-only ZIP ----------

  const CRC_TABLE = (() => {
    const t = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
      t[n] = c >>> 0;
    }
    return t;
  })();

  function crc32(data) {
    let c = 0xffffffff;
    for (let i = 0; i < data.length; i++) c = CRC_TABLE[(c ^ data[i]) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  }

  // files: [{ name: string, blob: Blob }] → Blob (application/zip)
  async function buildZip(files) {
    const encoder = new TextEncoder();
    const parts = [];
    const central = [];
    let offset = 0;
    for (const f of files) {
      const data = new Uint8Array(await f.blob.arrayBuffer());
      const nameBytes = encoder.encode(f.name);
      const crc = crc32(data);
      const local = new DataView(new ArrayBuffer(30));
      local.setUint32(0, 0x04034b50, true);   // local file header signature
      local.setUint16(4, 20, true);            // version needed
      local.setUint16(8, 0, true);             // method 0 = store
      local.setUint32(14, crc, true);
      local.setUint32(18, data.length, true);  // compressed size (= raw, stored)
      local.setUint32(22, data.length, true);  // uncompressed size
      local.setUint16(26, nameBytes.length, true);
      parts.push(new Uint8Array(local.buffer), nameBytes, data);
      central.push({ nameBytes, crc, size: data.length, offset });
      offset += 30 + nameBytes.length + data.length;
    }
    const centralParts = [];
    let centralSize = 0;
    for (const c of central) {
      const cd = new DataView(new ArrayBuffer(46));
      cd.setUint32(0, 0x02014b50, true);       // central directory signature
      cd.setUint16(4, 20, true);
      cd.setUint16(6, 20, true);
      cd.setUint32(16, c.crc, true);
      cd.setUint32(20, c.size, true);
      cd.setUint32(24, c.size, true);
      cd.setUint16(28, c.nameBytes.length, true);
      cd.setUint32(42, c.offset, true);
      centralParts.push(new Uint8Array(cd.buffer), c.nameBytes);
      centralSize += 46 + c.nameBytes.length;
    }
    const end = new DataView(new ArrayBuffer(22));
    end.setUint32(0, 0x06054b50, true);        // end-of-central-directory
    end.setUint16(8, files.length, true);
    end.setUint16(10, files.length, true);
    end.setUint32(12, centralSize, true);
    end.setUint32(16, offset, true);
    return new Blob([...parts, ...centralParts, new Uint8Array(end.buffer)], { type: "application/zip" });
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    // Don't revoke immediately — Safari sometimes loses the download.
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  }

  // ---------- PNG sequence ----------

  function loadImage(url) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = reject;
      img.src = url;
    });
  }

  function canvasToBlob(canvas) {
    return new Promise((resolve, reject) => {
      canvas.toBlob(b => b ? resolve(b) : reject(new Error("toBlob returned null")), "image/png");
    });
  }

  // Records `recordMs` of the LIVE svg element at `fps`, starting the moment
  // `trigger()` runs (frame 0 is captured just before, so the sequence begins
  // on the source pose). Serialization happens per-frame in real time (cheap);
  // rasterization happens afterwards so it can't drop capture frames.
  //
  // Everything the engine animates lives in attributes and inline styles, so
  // XMLSerializer snapshots are faithful. Returns a zip Blob of
  // frame_0000.png … frame_NNNN.png.
  async function recordPngSequence({ svgEl, trigger, recordMs, fps, scale = 2, background = null, onProgress }) {
    const serializer = new XMLSerializer();
    const frames = [serializer.serializeToString(svgEl)];
    const frameInterval = 1000 / fps;
    trigger();
    await new Promise(resolve => {
      const start = performance.now();
      let nextAt = frameInterval;
      const tick = (now) => {
        const e = now - start;
        // Catch up if a frame was missed rather than shifting all later frames.
        while (e >= nextAt && nextAt <= recordMs) {
          frames.push(serializer.serializeToString(svgEl));
          nextAt += frameInterval;
        }
        if (nextAt <= recordMs) requestAnimationFrame(tick);
        else resolve();
      };
      requestAnimationFrame(tick);
    });

    const w = Math.round((parseFloat(svgEl.getAttribute("width")) || 300) * scale);
    const h = Math.round((parseFloat(svgEl.getAttribute("height")) || 300) * scale);
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    const files = [];
    for (let i = 0; i < frames.length; i++) {
      if (onProgress) onProgress(`frame ${i + 1}/${frames.length}`);
      const img = await loadImage("data:image/svg+xml;charset=utf-8," + encodeURIComponent(frames[i]));
      ctx.clearRect(0, 0, w, h);
      if (background) { ctx.fillStyle = background; ctx.fillRect(0, 0, w, h); }
      ctx.drawImage(img, 0, 0, w, h);
      files.push({ name: `frame_${String(i).padStart(4, "0")}.png`, blob: await canvasToBlob(canvas) });
    }
    if (onProgress) onProgress("zipping…");
    return buildZip(files);
  }

  // ---------- standalone web player ----------

  // A literal script-close sequence ("</" + "script>") inside embedded JSON/JS
  // would close our inline tags. `<\/` is an identical escape inside JS strings
  // and regexes, so this is safe. (Spelled split here for the same reason —
  // this very file gets inlined into the standalone studio build.)
  function escapeScript(s) { return s.replace(/<\//g, "<\\/"); }

  // The live runtime caches DOM elements onto config objects it consumes
  // (e.g. IdleAnimator writes part._target = <svg element>), which makes the
  // states graph circular. Strip nodes + functions when serializing — the
  // player rebuilds those caches itself at load.
  function safeStringify(v) {
    return JSON.stringify(v, (key, val) => {
      if (typeof val === "function") return undefined;
      if (typeof Node !== "undefined" && val instanceof Node) return undefined;
      return val;
    });
  }

  const PLAYER_CSS = `
    * { box-sizing: border-box; }
    html, body { margin: 0; padding: 0; }
    body { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; background: transparent; }
    .player { display: inline-flex; flex-direction: column; align-items: center; gap: 12px; padding: 12px; }
    .player-canvas { display: inline-flex; align-items: center; justify-content: center; border: 1px solid #3a3a40; border-radius: 10px; padding: 16px; }
    .player-row { display: flex; gap: 6px; flex-wrap: wrap; justify-content: center; }
    .player-row button { padding: 6px 12px; border-radius: 999px; border: 1px solid #3a3a40; background: #17171a; color: #e8e6e0; font-family: inherit; font-size: 12px; font-weight: 600; cursor: pointer; }
    .player-row button:hover { border-color: #9b9993; }
    .player-row button.is-active { background: #267688; border-color: #267688; color: #fff5f0; }
    .player-row button.player-toggle { border-radius: 999px; min-width: 34px; }
  `;

  // Bundles the CURRENT in-memory animation (live-tuned STATES included) plus
  // the engine + app sources (pre-transpiled here with the already-loaded
  // Babel) into one .html. The app renders its PlayerApp branch because
  // PLAYER_MODE is set. Only external dependency: React/flubber CDN scripts.
  async function buildPlayerHtml({ playerConfig, pathOverrides }) {
    if (!window.Babel) throw new Error("Babel not loaded — cannot transpile engine/app for export.");
    // Source resolution: the standalone studio (file://, no server) embeds the
    // raw engine/app sources as strings; the served preview fetches them from
    // its own <script type="text/babel" src> tags.
    let engineSrc, appSrc;
    if (window.__STUDIO_SOURCES) {
      ({ engine: engineSrc, app: appSrc } = window.__STUDIO_SOURCES);
    } else {
      const babelScripts = Array.from(document.querySelectorAll('script[type="text/babel"][src]'));
      const engineTag = babelScripts.find(s => /engine[^/]*$/.test(s.src));
      const appTag = babelScripts.find(s => /app[^/]*$/.test(s.src));
      if (!engineTag || !appTag) throw new Error("Could not locate engine.jsx / app.jsx script tags.");
      [engineSrc, appSrc] = await Promise.all([
        fetch(engineTag.src).then(r => r.text()),
        fetch(appTag.src).then(r => r.text()),
      ]);
    }
    const engineJs = Babel.transform(engineSrc, { presets: ["react"] }).code;
    const appJs = Babel.transform(appSrc, { presets: ["react"] }).code;

    // Live STATES (particle-slider mutations and all) rather than the source
    // file — the export should match what the user is looking at. Path-role
    // mutations are NOT baked in: pathOverrides re-applies them at load, which
    // keeps the data round-trippable back into the editor.
    const globals = {
      STATES_DATA: window.MorphEngine.STATES,
      PREVIEW_CONFIG: window.PREVIEW_CONFIG || null,
      OVERLAYS_DATA: window.OVERLAYS_DATA || null,
      STRATEGY_OVERRIDES: window.STRATEGY_OVERRIDES || null,
      PATH_OVERRIDES: pathOverrides || {},
      PLAYER_CONFIG: playerConfig || {},
    };
    const globalsJs = Object.entries(globals)
      .map(([k, v]) => `window.${k} = ${escapeScript(safeStringify(v))};`)
      .join("\n") + "\nwindow.PLAYER_MODE = true;";

    const title = (window.PREVIEW_CONFIG && window.PREVIEW_CONFIG.title) || "Morph animation";
    return [
      "<!doctype html>",
      '<html lang="en">',
      "<head>",
      '<meta charset="utf-8" />',
      '<meta name="viewport" content="width=device-width, initial-scale=1" />',
      `<title>${title}</title>`,
      `<style>${PLAYER_CSS}</style>`,
      '<script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></' + "script>",
      '<script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></' + "script>",
      '<script src="https://unpkg.com/flubber@0.4.2/build/flubber.min.js"></' + "script>",
      "</head>",
      "<body>",
      '<div id="root"></div>',
      "<script>\n" + globalsJs + "\n</" + "script>",
      "<script>\n" + escapeScript(engineJs) + "\n</" + "script>",
      "<script>\n" + escapeScript(appJs) + "\n</" + "script>",
      "</body>",
      "</html>",
    ].join("\n");
  }

  window.PreviewExporters = { buildZip, downloadBlob, recordPngSequence, buildPlayerHtml };
})();
