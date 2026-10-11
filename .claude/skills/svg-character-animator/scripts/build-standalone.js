#!/usr/bin/env node
/**
 * build-standalone.js — bundle the preview into ONE double-clickable HTML.
 *
 *   node scripts/build-standalone.js              → <repo root>/animator-studio-en.html
 *   node scripts/build-standalone.js --lang cn    → <repo root>/animator-studio-cn.html (Chinese UI)
 *   node scripts/build-standalone.js out.html     → custom output path (combinable with --lang)
 *
 * The served preview needs a local server for exactly one reason: Babel
 * fetches engine.jsx / app.jsx over XHR (blocked on file://). The studio
 * instead EMBEDS the raw sources as strings and boots them on demand:
 *
 *   1. A bundled example or user-selected animation file (*.states.js) runs
 *      (it sets window.STATES_DATA, PREVIEW_CONFIG, OVERLAYS_DATA, …).
 *   2. eval(engine source)  — the engine IIFE runs now, AFTER states exist.
 *   3. Babel.transform(app source) + eval — the full editor renders.
 *
 * UX: the build bundles the public critters and snowman examples as read-only
 * library entries, so GitHub Pages and a freshly downloaded Studio open with
 * a working character immediately. User-loaded files accumulate separately
 * in localStorage. A small bar pinned bottom-left (below the preview column)
 * switches between bundled and user files and adds more. Switching/adding
 * while a character is live reloads the page (the engine is init-once by
 * design) and auto-resumes the chosen file — which is also what makes the path
 * editor's "apply role changes (reloads page)" flow seamless on file://.
 *
 * Everything else already works on file://: Blob downloads (Swift / PNG zip /
 * web player), localStorage (overrides, panel width), canvas rasterization
 * (data: SVG URLs don't taint). The web-player export reads the same embedded
 * sources via window.__STUDIO_SOURCES (see exporters.js).
 *
 * LOCALIZATION: the templates stay English-only. The Chinese build is produced
 * at build time by replacing exact UI-string fragments (see TR_APP / TR_SHELL
 * below). Each entry asserts its English source still exists, so a template
 * edit that breaks a translation fails the build loudly instead of silently
 * shipping mixed-language UI.
 *
 * This file is a BUILD, not a fork: it inlines templates/preview/* and
 * scripts/export-swift.js verbatim. Edit those, then re-run this script.
 * Only CDN scripts (React, flubber, Babel) remain external — the studio
 * needs internet, same as the served preview.
 */
const fs = require('fs');
const path = require('path');

const SKILL = path.join(__dirname, '..');
const PREVIEW = path.join(SKILL, 'templates', 'preview');
const read = (p) => fs.readFileSync(p, 'utf8');

// ---- CLI args ----
const args = process.argv.slice(2);
let lang = 'en';
const li = args.indexOf('--lang');
if (li >= 0) {
  lang = (args[li + 1] || 'en').toLowerCase();
  args.splice(li, 2);
}
if (lang !== 'en' && lang !== 'cn') {
  console.error(`Unknown --lang "${lang}" (expected en or cn)`);
  process.exit(1);
}
const outArg = args[0];

const previewHtml = read(path.join(PREVIEW, 'preview.html'));
const engineSrc = read(path.join(PREVIEW, 'engine.jsx'));
const appSrcEn = read(path.join(PREVIEW, 'app.jsx'));
const exportersSrc = read(path.join(PREVIEW, 'exporters.js'));
const swiftSrc = read(path.join(SKILL, 'scripts', 'export-swift.js'));
const defaultFiles = [
  {
    name: 'builtin:critters.states.js',
    title: 'Critters MorphAnimator',
    code: read(path.join(SKILL, 'examples', 'critters.states.js')),
    builtin: true,
  },
  {
    name: 'builtin:snowman.states.js',
    title: 'Snowman MorphAnimator',
    code: read(path.join(SKILL, 'examples', 'snowman.states.js')),
    builtin: true,
  },
];

// Apply a translation table of [english, chinese] exact-string pairs.
// Every english fragment MUST still exist in the source — otherwise the
// template drifted and the table needs updating.
function applyTr(src, table, label) {
  let out = src;
  for (const [en, cn] of table) {
    if (!out.includes(en)) {
      console.error(`[i18n] "${label}" no longer contains: ${JSON.stringify(en.slice(0, 70))}`);
      process.exit(1);
    }
    out = out.split(en).join(cn);
  }
  return out;
}

// ---- UI strings in templates/preview/app.jsx (the editor) ----
const TR_APP = [
  ['"SVG state-machine animation testbed"', '"SVG 状态机动画测试台"'],
  ['<Stat label="states"', '<Stat label="状态"'],
  ['<Stat label="shared"', '<Stat label="共享部件"'],
  ['<Stat label="decorations"', '<Stat label="装饰"'],
  ['>Paths &amp; transitions</div>', '>路径与过渡</div>'],
  ['Apply {pendingCount} role change{pendingCount > 1 ? "s" : ""} (reloads page)',
   '应用 {pendingCount} 项角色修改（重新加载页面）'],
  ['<option value="shared">character</option>', '<option value="shared">角色</option>'],
  ['<option value="orphan">decoration</option>', '<option value="orphan">装饰</option>'],
  ['? "Role: character parts morph between states; decorations fade in/out" : "Not present in every state — must stay a decoration"',
   '? "角色部件在状态间变形；装饰淡入淡出" : "并非每个状态都有此部件 — 只能作为装饰"'],
  ['{s === "DECORATION" ? "decoration" : METHOD_LABEL[s]', '{s === "DECORATION" ? "装饰" : METHOD_LABEL[s]'],
  ['TRANSFORM: "smooth morph",', 'TRANSFORM: "平滑变形",'],
  ['MORPH: "sampled morph",', 'MORPH: "采样变形",'],
  ['CROSSFADE: "crossfade",', 'CROSSFADE: "交叉淡化",'],
  ['SCALE: "move & resize",', 'SCALE: "移动缩放",'],
  ['"How this part transitions:\\n" +', '"此部件的过渡方式：\\n" +'],
  ['"· smooth morph — exact vertex interpolation (shape DOES deform, highest quality)\\n" +',
   '"· 平滑变形 — 精确顶点插值（形状会变形，质量最高）\\n" +'],
  ['"· sampled morph — polygon-sampled library morph (shape deforms, approximate)\\n" +',
   '"· 采样变形 — 库的多边形采样变形（形状会变形，近似）\\n" +'],
  ['"· crossfade — fade out / fade in, no deformation\\n" +',
   '"· 交叉淡化 — 淡出/淡入，不变形\\n" +'],
  ['"· move & resize — rigid box mapping, no deformation"',
   '"· 移动缩放 — 刚性包围盒映射，不变形"'],
  ['`auto (${METHOD_LABEL[detected] || "?"})`', '`自动（${METHOD_LABEL[detected] || "?"}）`'],
  ['background: "#202024" }}>fade</span>', 'background: "#202024" }}>淡化</span>'],
  ['>Click a part on the canvas (or a row) to select it.</div>', '>点击画布上的部件（或列表中的一行）来选中它。</div>'],
  // Particles
  ['>Particles — {stateName}</div>', '>粒子 — {stateName}</div>'],
  ['<summary>Arc position</summary>', '<summary>生成弧线位置</summary>'],
  ['<summary>Size</summary>', '<summary>大小</summary>'],
  ['<summary>Spawn &amp; lifespan</summary>', '<summary>生成与寿命</summary>'],
  ['label="Center X"', 'label="中心 X"'],
  ['label="Center Y"', 'label="中心 Y"'],
  ['label="Radius"', 'label="半径"'],
  ['label="Angle"', 'label="角度"'],
  ['label="Scale" values={cfg.scaleRange', 'label="缩放" values={cfg.scaleRange'],
  ['label="Interval"', 'label="间隔"'],
  ['label="Burst"', 'label="爆发"'],
  ['label="Duration" values={[cfg.duration', 'label="时长" values={[cfg.duration'],
  ['label="Dur jitter"', 'label="时长抖动"'],
  // SwiftUI export
  ['>Export to SwiftUI</div>', '>导出 SwiftUI</div>'],
  ['placeholder="Type name (e.g. SnowmanAnimator)"', 'placeholder="类型名（如 SnowmanAnimator）"'],
  ['placeholder="Type prefix (e.g. Snowman) — keeps types unique per app"',
   'placeholder="类型前缀（如 Snowman）— 避免多角色类型冲突"'],
  ["{busy ? 'Generating…' : `Export ${typeName}.swift`}", "{busy ? '生成中…' : `导出 ${typeName}.swift`}"],
  ['Last export: <code>', '上次导出：<code>'],
  ['Captures every current edit: duration, easing curve, per-path methods,\n        idle preset + anchor, particle tuning. Background color is preview-only.',
   '包含当前所有编辑：时长、缓动曲线、逐路径方式、待机预设与锚点、粒子调参。背景色仅用于预览。'],
  // Idle presets
  ['label: "authored (per state)"', 'label: "文件自带（每状态）"'],
  ['{ value: "none", label: "none" }', '{ value: "none", label: "无" }'],
  ['{ value: "breathe", label: "breathe" }', '{ value: "breathe", label: "呼吸" }'],
  ['{ value: "breathe-y", label: "breathe-y" }', '{ value: "breathe-y", label: "纵向呼吸" }'],
  ['{ value: "sway", label: "sway" }', '{ value: "sway", label: "摇摆" }'],
  ['{ value: "bob", label: "bob" }', '{ value: "bob", label: "上下浮动" }'],
  ['{ value: "shake", label: "shake" }', '{ value: "shake", label: "抖动" }'],
  ['{ value: "waggle-sequence", label: "waggle" }', '{ value: "waggle-sequence", label: "摆动" }'],
  ['{ value: "float", label: "float" }', '{ value: "float", label: "漂浮" }'],
  ['>Idle {value !== "authored" ? "· override" : ""}</div>', '>待机动画 {value !== "authored" ? "· 覆盖" : ""}</div>'],
  // Idle anchor
  ['>Idle anchor</div>', '>待机锚点</div>'],
  ['label: "bottom-center", value: null, hint: "default — feet on the ground plane"',
   'label: "底部中心", value: null, hint: "默认 — 脚站在地面上"'],
  ['label: "center", value: "50% 50%", hint: "floating objects"',
   'label: "中心", value: "50% 50%", hint: "漂浮物体"'],
  ['label: "top-center", value: "50% 0%", hint: "hanging from above"',
   'label: "顶部中心", value: "50% 0%", hint: "从上方悬挂"'],
  ['title="Click a point on the canvas to place the pivot there"', 'title="在画布上点击一个点作为旋转轴心"'],
  ['{pickArmed ? "click canvas…" : "pick on canvas"}', '{pickArmed ? "点击画布…" : "在画布上选点"}'],
  // Duration
  ['>Duration {isCustom ? "· custom" : "· preset"}</div>', '>时长 {isCustom ? "· 自定义" : "· 预设"}</div>'],
  ['>reset to preset ({presetMs}ms)</button>', '>重置为预设（{presetMs}ms）</button>'],
  // PNG export
  ['>Export PNG sequence</div>', '>导出 PNG 序列帧</div>'],
  ['<label>To state</label>', '<label>目标状态</label>'],
  ['<label>Scale</label>', '<label>缩放</label>'],
  ['        transparent background\n', '        透明背景\n'],
  ['setProgress("recording…");', 'setProgress("录制中…");'],
  ['setProgress("done");', 'setProgress("完成");'],
  ['setProgress("failed: " + e.message);', 'setProgress("失败：" + e.message);'],
  ['title={xray ? "Turn off X-ray first — the wireframe would be recorded into the frames" : ""}',
   'title={xray ? "请先关闭 X-ray — 线框层会被录进每一帧" : ""}'],
  ['{xray ? "Turn off X-ray to record" : busy ? "Recording…" : `Record ${current} → ${effectiveTo || "?"} (.zip)`}',
   '{xray ? "关闭 X-ray 后可录制" : busy ? "录制中…" : `录制 ${current} → ${effectiveTo || "?"}（.zip）`}'],
  ['>Records the live canvas through one transition, then zips the frames. Background is transparent unless unchecked above.</div>',
   '>录制一次实时过渡并打包成序列帧。除非取消上方勾选，背景保持透明。</div>'],
  // Web export
  ['>Export web animation</div>', '>导出网页动画</div>'],
  ['        autoplay (cycle through states)\n', '        自动播放（循环所有状态）\n'],
  ['{busy ? "Bundling…" : "Export player (.html)"}', '{busy ? "打包中…" : "导出播放器（.html）"}'],
  ['Single self-contained file — open directly or embed via &lt;iframe&gt;. Loads React/flubber from CDN.',
   '单个自包含文件 — 可直接打开或用 &lt;iframe&gt; 嵌入。React/flubber 从 CDN 加载。'],
  // Player
  ['title={playing ? "Pause" : "Autoplay"}', 'title={playing ? "暂停" : "自动播放"}'],
  // Canvas chrome
  ['title="Wireframe view: path outlines + bezier anchor/control dots, live during morphs"',
   'title="线框视图：路径轮廓 + 贝塞尔锚点/控制点，变形过程中实时更新"'],
  ['<span className="overlay-label">Play once</span>', '<span className="overlay-label">播放一次</span>'],
  ['{OVERLAYS.talk.label || "Talk"}', '{OVERLAYS.talk.label || "说话"}'],
  ['{OVERLAYS.lookAround.label || "Look around"}', '{OVERLAYS.lookAround.label || "张望"}'],
  ['? "" : `Only in ${(OVERLAYS.lookAround.enabledStates || []).join(" / ")}`',
   '? "" : `仅限 ${(OVERLAYS.lookAround.enabledStates || []).join(" / ")}`'],
  ['title="Drag to resize the edit panel"', 'title="拖动以调整编辑面板宽度"'],
  // Easing / background / config cards
  ['>Easing {bezier ? "· custom curve" : ""}</div>', '>缓动 {bezier ? "· 自定义曲线" : ""}</div>'],
  ['↺ Reset to preset curve ({effectiveEaseName})', '↺ 重置为预设曲线（{effectiveEaseName}）'],
  ['>Background</div>', '>背景</div>'],
  ['Preview only — exports don\'t include the background (Swift & web\n                render transparent; PNG uses it only when "transparent" is unchecked).',
   '仅用于预览 — 导出不包含背景（Swift 与网页导出为透明；PNG 仅在取消勾选"透明背景"时包含）。'],
  ['>Depress ellipse opacity</div>', '>按压椭圆不透明度</div>'],
  ['<label>Opacity</label>', '<label>不透明度</label>'],
  ['>Active config</div>', '>当前配置</div>'],
  ['{bezier ? " · custom curve" : ""}', '{bezier ? " · 自定义曲线" : ""}'],
  ['` · anchor ${idleAnchor}`', '` · 锚点 ${idleAnchor}`'],
];

// ---- UI strings in the studio shell (this file's own HTML/JS) ----
const TR_SHELL = [
  ['<html lang="en">', '<html lang="zh-CN">'],
  ['<title>Animator Studio</title>', '<title>动画工作台 Animator Studio</title>'],
  ['<h1>Animator Studio</h1>', '<h1>动画工作台</h1>'],
  ['<p>SVG state-machine animation — load a file to begin</p>', '<p>SVG 状态机动画 — 载入文件开始</p>'],
  ['<span class="stat-label">states</span>', '<span class="stat-label">状态</span>'],
  ['<span class="stat-label">shared</span>', '<span class="stat-label">共享部件</span>'],
  ['<span class="stat-label">decorations</span>', '<span class="stat-label">装饰</span>'],
  ['title="Click to choose a file"', 'title="点击选择文件"'],
  ['<p class="studio-cta">Drop your animation file here</p>', '<p class="studio-cta">把动画文件拖到这里</p>'],
  ['<p class="studio-sub">or click to choose</p>', '<p class="studio-sub">或点击选择</p>'],
  ['Files end in <code>.states.js</code> — the kind this skill creates\n              (each one is a character with its animation states).<br />\n              Internet needed the first time it opens.',
   '文件以 <code>.states.js</code> 结尾 — 即本技能生成的文件\n              （每个文件是一个带动画状态的角色）。<br />\n              首次打开需要联网。'],
  ['<span class="studio-empty-note">state buttons appear here</span>', '<span class="studio-empty-note">状态按钮将显示在这里</span>'],
  ['<div class="control-label">Paths &amp; transitions</div>', '<div class="control-label">路径与过渡</div>'],
  ['<div class="control-label">Easing</div>', '<div class="control-label">缓动</div>'],
  ['<div class="control-label">Duration</div>', '<div class="control-label">时长</div>'],
  ['<div class="control-label">Idle</div>', '<div class="control-label">待机动画</div>'],
  ['<div class="control-label">Idle anchor</div>', '<div class="control-label">待机锚点</div>'],
  ['<div class="control-label">Background</div>', '<div class="control-label">背景</div>'],
  ['<div class="control-label">Exports</div>', '<div class="control-label">导出</div>'],
  ['<span class="studio-empty-note">load a file first</span>', '<span class="studio-empty-note">请先载入文件</span>'],
  ['title="Switch between loaded files"', 'title="切换已载入的文件"'],
  ['title="Load another animation file"', 'title="载入另一个动画文件"'],
  ['>+ add file</button>', '>+ 添加文件</button>'],
  ['"That file errored while loading: "', '"文件加载出错："'],
  ['"That doesn\'t look like an animation file (*.states.js)."', '"这看起来不是动画文件（*.states.js）。"'],
  ['"Could not start the preview: "', '"无法启动预览："'],
  ['"Could not read the file: "', '"无法读取文件："'],
  ['" — Animator Studio"', '" — 动画工作台"'],
];

const appSrc = lang === 'cn' ? applyTr(appSrcEn, TR_APP, 'templates/preview/app.jsx') : appSrcEn;

// The canonical stylesheet, verbatim.
const css = previewHtml.slice(
  previewHtml.indexOf('<style>') + '<style>'.length,
  previewHtml.indexOf('</style>')
);

// Embed arbitrary source as a JS string literal. JSON.stringify handles
// quotes/backslashes/newlines; escaping `<` keeps script-close sequences from
// terminating our inline script tag.
const esc = (s) => JSON.stringify(s).replace(/</g, '\\u003C');

// Sanitize RAW source inlined directly into a <script> block: a literal
// "</script" anywhere (even in a comment) would terminate the tag. `<\/` is
// byte-identical in JS strings/regexes and harmless in comments.
const inlineJs = (s) => s.replace(/<\/script/gi, '<\\/script');

// The shell template with the embedded-source slots left as placeholders, so
// the CN string replacement can never touch the embedded engine/app/exporter
// sources (only TR_APP is meant to reach app.jsx).
let shell = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Animator Studio</title>
  <style>
${css}
    /* ---- Studio additions ---- */
    /* Empty-state shell: the normal preview layout with a chooser in the canvas */
    #studio-shell .canvas-surface { cursor: pointer; }
    #studio-shell .canvas-surface.is-over { border-color: var(--accent-2); }
    .studio-drop-inner { text-align: center; padding: 24px; max-width: 300px; }
    .studio-cta { margin: 0; font-size: 13px; font-weight: 600; color: var(--text); }
    .studio-sub { margin: 4px 0 0; font-size: 11px; color: var(--text-muted); }
    .studio-hint { margin: 18px 0 0; font-size: 10px; line-height: 1.6; color: var(--text-faint); }
    .studio-hint code { color: var(--text-muted); }
    #studio-error { margin: 10px 0 0; color: #e0447c; font-size: 11px; min-height: 14px; }
    .studio-empty-note { color: var(--text-faint); font-size: 11px; }
    /* File bar — pinned below the preview column, bottom-left */
    #studio-files {
      position: fixed;
      left: 24px;
      bottom: 14px;
      z-index: 40;
      display: none;
      align-items: center;
      gap: 8px;
    }
    #studio-files select {
      padding: 5px 10px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: var(--panel-2);
      color: var(--text);
      font-family: var(--mono);
      font-size: 11px;
      cursor: pointer;
      max-width: 260px;
    }
    #studio-files select:focus { outline: none; border-color: var(--accent-2); }
    .studio-add {
      padding: 5px 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: var(--panel-2);
      color: var(--text-muted);
      font-family: var(--mono);
      font-size: 11px;
      cursor: pointer;
      white-space: nowrap;
    }
    .studio-add:hover { border-color: var(--text-muted); color: var(--text); }
  </style>

  <script crossorigin src="https://unpkg.com/react@18/umd/react.development.js"></script>
  <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"></script>
  <script src="https://unpkg.com/flubber@0.4.2/build/flubber.min.js"></script>
  <!-- Babel transpiles the embedded app source at boot (and the web-player
       export re-uses it). Pinned to 7.x — see templates/preview/preview.html. -->
  <script src="https://unpkg.com/@babel/standalone@7/babel.min.js"></script>
</head>
<body>
  <!-- Empty-state shell: same layout as the live preview, chooser in the canvas.
       Hidden the moment a file boots (the React app renders into #root). -->
  <div class="app" id="studio-shell">
    <header class="header">
      <div class="header-row">
        <div>
          <h1>Animator Studio</h1>
          <p>SVG state-machine animation — load a file to begin</p>
        </div>
        <div class="stat-strip">
          <div class="stat"><span class="stat-value">–</span><span class="stat-label">states</span></div>
          <div class="stat"><span class="stat-value">–</span><span class="stat-label">shared</span></div>
          <div class="stat"><span class="stat-value">–</span><span class="stat-label">decorations</span></div>
        </div>
      </div>
    </header>
    <main class="main">
      <section class="canvas-card">
        <div class="canvas-tools"><button class="xray-btn" disabled>◉ X-ray</button></div>
        <div class="canvas-surface" id="studio-drop" style="background: #16181c;" title="Click to choose a file">
          <div class="studio-drop-inner">
            <p class="studio-cta">Drop your animation file here</p>
            <p class="studio-sub">or click to choose</p>
            <p class="studio-hint">
              Files end in <code>.states.js</code> — the kind this skill creates
              (each one is a character with its animation states).<br />
              Internet needed the first time it opens.
            </p>
            <p id="studio-error"></p>
          </div>
        </div>
        <div class="state-row"><span class="studio-empty-note">state buttons appear here</span></div>
      </section>
      <div class="panel-divider" style="cursor: default;"></div>
      <aside class="controls">
        <div class="control-card"><div class="control-label">Paths &amp; transitions</div><span class="studio-empty-note">—</span></div>
        <div class="control-card"><div class="control-label">Easing</div><span class="studio-empty-note">—</span></div>
        <div class="control-card"><div class="control-label">Duration</div><span class="studio-empty-note">—</span></div>
        <div class="control-card"><div class="control-label">Idle</div><span class="studio-empty-note">—</span></div>
        <div class="control-card"><div class="control-label">Idle anchor</div><span class="studio-empty-note">—</span></div>
        <div class="control-card"><div class="control-label">Background</div><span class="studio-empty-note">—</span></div>
        <div class="control-card"><div class="control-label">Exports</div><span class="studio-empty-note">load a file first</span></div>
      </aside>
    </main>
  </div>

  <div id="root"></div>

  <!-- File bar: switch between loaded files / add another. Pinned bottom-left,
       below the preview column. -->
  <div id="studio-files">
    <select id="studio-switch" title="Switch between loaded files"></select>
    <button class="studio-add" id="studio-add" title="Load another animation file">+ add file</button>
  </div>
  <input type="file" id="studio-input" accept=".js,text/javascript" style="display: none;" />

  <script>
__EXPORTERS_SRC__
  </script>
  <script>
__SWIFT_SRC__
  </script>

  <script>
  // Raw template sources — booted on demand, and consumed by the web-player
  // export (exporters.js prefers __STUDIO_SOURCES over fetching script tags).
  window.__STUDIO_SOURCES = {
    engine: __ENGINE_LITERAL__,
    app: __APP_LITERAL__,
  };
  window.__STUDIO_DEFAULT_FILES = __DEFAULT_FILES_LITERAL__;

  (function () {
    var LIB_KEY = "morphStudioLibrary";     // [{ name, title, code }]
    var ACTIVE_KEY = "morphStudioActive";   // name of the active entry
    var MAX_FILES = 12;

    var shell = document.getElementById("studio-shell");
    var drop = document.getElementById("studio-drop");
    var input = document.getElementById("studio-input");
    var filesBar = document.getElementById("studio-files");
    var switcher = document.getElementById("studio-switch");
    var errEl = document.getElementById("studio-error");
    var booted = false;
    var defaultFiles = Array.isArray(window.__STUDIO_DEFAULT_FILES) ? window.__STUDIO_DEFAULT_FILES : [];

    function showError(msg) { errEl.textContent = msg; }

    function loadUserLib() {
      try { return JSON.parse(localStorage.getItem(LIB_KEY)) || []; } catch (e) { return []; }
    }
    function loadLib() {
      var defaultsByName = {};
      defaultFiles.forEach(function (f) { defaultsByName[f.name] = true; });
      return defaultFiles.concat(loadUserLib().filter(function (f) { return !defaultsByName[f.name]; }));
    }
    function saveUserLib(lib) {
      try {
        localStorage.setItem(LIB_KEY, JSON.stringify(lib));
      } catch (e) {
        // Quota: evict the oldest non-active entry and retry once.
        var active = localStorage.getItem(ACTIVE_KEY);
        var idx = lib.findIndex(function (f) { return f.name !== active; });
        if (idx >= 0) { lib.splice(idx, 1); try { localStorage.setItem(LIB_KEY, JSON.stringify(lib)); } catch (e2) { /* give up */ } }
      }
    }

    function isDefaultName(name) {
      return defaultFiles.some(function (f) { return f.name === name; });
    }

    // Run a states file against a scratch "window" to check it without
    // touching the live page (used when adding while a character is booted).
    function validate(code) {
      var probe = {};
      try { new Function("window", code)(probe); } catch (e) { return "That file errored while loading: " + e.message; }
      if (!probe.STATES_DATA || typeof probe.STATES_DATA !== "object" || Object.keys(probe.STATES_DATA).length < 2) {
        return "That doesn't look like an animation file (*.states.js).";
      }
      return null;
    }

    function refreshBar() {
      var lib = loadLib();
      if (lib.length === 0) { filesBar.style.display = "none"; return; }
      var active = localStorage.getItem(ACTIVE_KEY);
      switcher.innerHTML = "";
      lib.forEach(function (f) {
        var opt = document.createElement("option");
        opt.value = f.name;
        opt.textContent = f.title || f.name;
        if (f.name === active) opt.selected = true;
        switcher.appendChild(opt);
      });
      filesBar.style.display = "flex";
    }

    function remember(code, name) {
      if (!isDefaultName(name)) {
        var lib = loadUserLib();
        var title = (window.PREVIEW_CONFIG && window.PREVIEW_CONFIG.title) || name;
        var existing = lib.findIndex(function (f) { return f.name === name; });
        var entry = { name: name, title: title, code: code };
        if (existing >= 0) lib[existing] = entry; else lib.push(entry);
        while (lib.length > MAX_FILES) lib.shift();
        saveUserLib(lib);
      }
      try { localStorage.setItem(ACTIVE_KEY, name); } catch (e) { /* ignore */ }
      refreshBar();
    }

    function boot(code, name) {
      if (booted) return;
      showError("");
      try {
        new Function(code)(); // states files assign to window.* explicitly
      } catch (e) { showError("That file errored while loading: " + e.message); return; }
      if (!window.STATES_DATA || typeof window.STATES_DATA !== "object" || Object.keys(window.STATES_DATA).length < 2) {
        showError("That doesn't look like an animation file (*.states.js).");
        return;
      }
      try {
        (0, eval)(window.__STUDIO_SOURCES.engine);          // sets window.MorphEngine (reads STATES_DATA + overrides)
        var appJs = Babel.transform(window.__STUDIO_SOURCES.app, { presets: ["react"] }).code;
        (0, eval)(appJs);                                   // renders the full editor into #root
      } catch (e) { console.error(e); showError("Could not start the preview: " + e.message); return; }
      booted = true;
      shell.style.display = "none";
      remember(code, name);
      var title = (window.PREVIEW_CONFIG && window.PREVIEW_CONFIG.title) || name;
      document.title = title + " — Animator Studio";
    }
    // Exposed for scripted use (tests / automation).
    window.__studioBoot = boot;

    function handleFile(file) {
      if (!file) return;
      file.text().then(function (code) {
        if (!booted) { boot(code, file.name); return; }
        // A character is already live: validate off-page, store, reload into it.
        var err = validate(code);
        if (err) { alert(err); return; }
        var probe = {};
        new Function("window", code)(probe);
        var lib = loadUserLib();
        var entryName = isDefaultName(file.name) ? "uploaded:" + file.name : file.name;
        var title = (probe.PREVIEW_CONFIG && probe.PREVIEW_CONFIG.title) || file.name;
        var existing = lib.findIndex(function (f) { return f.name === entryName; });
        var entry = { name: entryName, title: title, code: code };
        if (existing >= 0) lib[existing] = entry; else lib.push(entry);
        while (lib.length > MAX_FILES) lib.shift();
        saveUserLib(lib);
        try { localStorage.setItem(ACTIVE_KEY, entryName); } catch (e) { /* ignore */ }
        location.reload();
      }, function (e) { showError("Could not read the file: " + e.message); });
    }

    // Chooser inside the empty canvas
    drop.addEventListener("click", function () { input.click(); });
    drop.addEventListener("dragover", function (e) { e.preventDefault(); drop.classList.add("is-over"); });
    drop.addEventListener("dragleave", function () { drop.classList.remove("is-over"); });
    drop.addEventListener("drop", function (e) {
      e.preventDefault();
      drop.classList.remove("is-over");
      handleFile(e.dataTransfer.files && e.dataTransfer.files[0]);
    });

    // File bar
    document.getElementById("studio-add").addEventListener("click", function () { input.click(); });
    input.addEventListener("change", function () { handleFile(input.files[0]); input.value = ""; });
    switcher.addEventListener("change", function () {
      try { localStorage.setItem(ACTIVE_KEY, switcher.value); } catch (e) { /* ignore */ }
      location.reload();
    });

    // Auto-resume the active file (also what makes the path editor's
    // "apply role changes (reloads page)" flow seamless on file://).
    try {
      var lib0 = loadLib();
      var activeName = localStorage.getItem(ACTIVE_KEY);
      var entry0 = lib0.find(function (f) { return f.name === activeName; }) || lib0[0] || null;
      if (entry0 && entry0.name !== activeName) {
        try { localStorage.setItem(ACTIVE_KEY, entry0.name); } catch (e) { /* ignore */ }
      }
      refreshBar();
      if (entry0) boot(entry0.code, entry0.name);
    } catch (e) { /* corrupted cache — fall through to the empty shell */ }
  })();
  </script>
</body>
</html>
`;

if (lang === 'cn') shell = applyTr(shell, TR_SHELL, 'studio shell');

const html = shell
  .replace('__EXPORTERS_SRC__', () => inlineJs(exportersSrc))
  .replace('__SWIFT_SRC__', () => inlineJs(swiftSrc))
  .replace('__ENGINE_LITERAL__', () => esc(engineSrc))
  .replace('__APP_LITERAL__', () => esc(appSrc))
  .replace('__DEFAULT_FILES_LITERAL__', () => esc(defaultFiles));

const outPath = outArg
  ? path.resolve(outArg)
  : path.join(SKILL, `animator-studio-${lang}.html`);
fs.writeFileSync(outPath, html);
console.log(`Wrote ${(html.length / 1024).toFixed(0)} KB to ${outPath} (lang: ${lang})`);
