/**
 * 빌드 산출물(dist/index.html)을 열어 콘솔 에러 수집 + 스크린샷.
 * 사용: node scripts/verify.mjs [출력.png] [--step N] [--focus RED|BLUE] [--play]
 */
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const dist = path.resolve(here, "../dist/index.html");
const out = process.argv[2] ?? "shot.png";
const args = process.argv.slice(3);

function argValue(name) {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : null;
}

const browser = await chromium.launch({ args: ["--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: 1680, height: 940 } });

const errors = [];
page.on("console", (msg) => {
  if (msg.type() === "error") errors.push(msg.text());
});
page.on("pageerror", (err) => errors.push(String(err)));

await page.goto("file:///" + dist.replace(/\\/g, "/"));
await page.waitForTimeout(2500);

// 랜딩 스크린샷이 아니면 자동 진입
if (!args.includes("--landing")) {
  const enterBtn = page.locator("text=시뮬레이션 진입");
  if ((await enterBtn.count()) > 0) {
    await enterBtn.click();
    await page.waitForTimeout(1800);
  }
}

const roundArg = argValue("--round");
if (roundArg) {
  const roundInput = page.getByLabel("라운드 직접 이동");
  if ((await roundInput.count()) > 0) {
    await roundInput.fill(String(roundArg));
    await roundInput.press("Enter");
  } else {
    await page.click(`text=R${roundArg}`);
  }
  await page.waitForTimeout(400);
}

const step = argValue("--step");
if (step !== null) {
  for (let i = 0; i < Number(step); i++) {
    await page.keyboard.press("ArrowRight");
    await page.waitForTimeout(120);
  }
}

const focus = argValue("--focus");
if (focus) {
  await page.click(`[data-side="${focus}"] button`);
  await page.waitForTimeout(700);
}

const hover = argValue("--hover");
if (hover) {
  const [hx, hy] = hover.split(",").map(Number);
  await page.mouse.move(hx, hy);
  await page.waitForTimeout(700);
}

if (args.includes("--mugyeol")) {
  await page.click('[aria-label="무결이 열기"]');
  await page.waitForTimeout(800);
  await page.click("text=누가 이겼어");
  await page.waitForTimeout(1400);
}

if (args.includes("--play")) {
  await page.keyboard.press("Space");
  await page.waitForTimeout(2400);
}

await page.waitForTimeout(800);
await page.screenshot({ path: out });

console.log("SCREENSHOT:", out);
if (errors.length) {
  console.log("CONSOLE ERRORS:");
  for (const e of errors.slice(0, 10)) console.log(" -", e.slice(0, 300));
} else {
  console.log("CONSOLE: clean");
}

await browser.close();
