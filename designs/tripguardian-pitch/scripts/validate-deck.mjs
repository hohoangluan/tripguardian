import fs from "node:fs";
import path from "node:path";

const target = process.argv[2];
if (!target) {
  console.error("usage: node validate-deck.mjs <deck.html>");
  process.exit(64);
}

const htmlPath = path.resolve(target);
if (!fs.existsSync(htmlPath)) {
  console.error(`missing deck: ${htmlPath}`);
  process.exit(1);
}

const html = fs.readFileSync(htmlPath, "utf8");
const errors = [];
const sections = [...html.matchAll(/<section\b[^>]*data-label="([^"]+)"[^>]*>/g)];
const anims = [...html.matchAll(/\bdata-anim="([^"]+)"/g)];
const imageRefs = [...html.matchAll(/<img\b[^>]*src="([^"]+)"/g)].map((match) => match[1]);

if (!html.includes('<deck-stage width="1920" height="1080">')) errors.push("deck-stage must be 1920x1080");
if (!html.includes('<script src="deck-stage.js"></script>')) errors.push("deck-stage.js must be loaded");
if (sections.length !== 16) errors.push(`expected 16 slides, found ${sections.length}`);
if (new Set(sections.map((match) => match[1])).size !== 16) errors.push("slide labels must be unique");
if (anims.length < 8 || anims.length > 18) errors.push(`expected 8-18 meaningful builds, found ${anims.length}`);
if (!html.includes("section[data-label] > *:not(img):not(picture):not(video):not(svg):not(canvas)")) errors.push("missing slide wrapper fill rule");
if (!html.includes('deck-stage { font-family: "Be Vietnam Pro", sans-serif; }')) errors.push("deck-stage must set Be Vietnam Pro to override the scaffold host font");
if (!html.includes("--type-title: 64px")) errors.push("missing 64px title token");
if (!html.includes("--type-small: 24px")) errors.push("smallest text token must be 24px");
if (html.includes('id="speaker-notes"')) errors.push("speaker notes are out of scope");
if (html.includes("fonts.googleapis.com") || html.includes("fonts.gstatic.com")) errors.push("remote font reference found");
if (/font-size:\s*(?:[0-9]|1[0-9]|2[0-3])px/.test(html)) errors.push("font size below 24px found");

const requiredCopy = [
  "Layla",
  "Trip State mô phỏng offline",
  "Planning &amp; Validation",
  "Đây là so sánh định vị từ tài liệu công khai, không phải benchmark chất lượng đối đầu.",
];
for (const copy of requiredCopy) {
  if (!html.includes(copy)) errors.push(`missing required copy: ${copy}`);
}

for (const ref of imageRefs) {
  if (/^(?:https?:|\/\/|\.\.\/)/.test(ref)) errors.push(`non-local image reference: ${ref}`);
  const resolved = path.resolve(path.dirname(htmlPath), ref);
  if (!fs.existsSync(resolved)) errors.push(`missing image: ${ref}`);
}

if (errors.length) {
  console.error(errors.map((item) => `- ${item}`).join("\n"));
  process.exit(1);
}

console.log(`ok: ${sections.length} slides, ${anims.length} animations, ${imageRefs.length} local images`);
