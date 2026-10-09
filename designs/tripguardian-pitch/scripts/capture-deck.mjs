import { chromium } from "../../../web/node_modules/playwright-core/index.mjs";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const project = path.resolve(here, "..");
const browserPath = path.resolve(project, "../../.cache/ms-playwright/chromium-1169/chrome-linux/chrome");
const url = process.argv[2] || "http://127.0.0.1:4311/tripguardian-pitch/TripGuardian%20Pitch.html";
const browser = await chromium.launch({ headless: true, executablePath: browserPath });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
const errors = [];

page.on("console", (message) => {
  if (message.type() === "error") errors.push(message.text());
});
page.on("pageerror", (error) => errors.push(error.message));

await page.goto(url, { waitUntil: "networkidle" });
await page.evaluate(() => document.querySelector("deck-stage").setAttribute("noscale", ""));
await fs.mkdir(path.join(project, "shots"), { recursive: true });
const slideCount = await page.locator("deck-stage > section[data-label]").count();

for (let index = 0; index < slideCount; index += 1) {
  await page.evaluate((slide) => document.querySelector("deck-stage").goTo(slide), index);
  await page.waitForTimeout(1900);
  const target = page.locator("deck-stage > [data-deck-active]");
  const overflow = await target.evaluate((node) => ({
    x: node.scrollWidth > node.clientWidth,
    y: node.scrollHeight > node.clientHeight,
  }));
  if (overflow.x || overflow.y) errors.push(`slide ${index + 1} overflows: ${JSON.stringify(overflow)}`);
  await target.screenshot({ path: path.join(project, "shots", `slide-${String(index + 1).padStart(2, "0")}.png`) });
}

await browser.close();
if (errors.length) {
  console.error(errors.join("\n"));
  process.exit(1);
}
console.log(`ok: captured ${slideCount} slides without console errors or section overflow`);
