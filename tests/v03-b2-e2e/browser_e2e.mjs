import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";

const baseUrl = process.env.BASE_URL || "http://127.0.0.1:4182";
const accountsPath = process.env.ACCOUNTS_FILE;
const outputDir = path.resolve(process.env.OUTPUT_DIR || ".");
const productRoot = path.resolve(process.env.PRODUCT_ROOT || ".");
const chromePath =
  process.env.CHROME_PATH || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const promptText =
  "今天下午我给阳台上的多肉一盆盆换了新土，手指沾满泥，旁边有黄色马克杯和蓝色喷壶，阳光暖暖的，我心里很踏实。";

assert(accountsPath, "ACCOUNTS_FILE is required");
assert(process.env.PRODUCT_ROOT, "PRODUCT_ROOT is required");
const require = createRequire(path.join(productRoot, "package.json"));
const { chromium } = require("@playwright/test");
const accounts = JSON.parse(await readFile(accountsPath, "utf8"));
const account = accounts.owner;

function hhmm(date) {
  return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

function atMinutes(date, offset) {
  return new Date(date.getTime() + offset * 60_000);
}

const now = new Date();
const firstEnd = hhmm(atMinutes(now, 2));
const secondEnd = hhmm(atMinutes(now, 32));
const requestLog = [];
const consoleErrors = [];
const pageErrors = [];

const browser = await chromium.launch({
  headless: true,
  executablePath: chromePath,
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  colorScheme: "light",
  serviceWorkers: "block",
});
const page = await context.newPage();
page.on("console", (message) => {
  if (message.type() === "error") {
    consoleErrors.push(message.text());
  }
});
page.on("pageerror", (error) => pageErrors.push(error.stack || error.message));
page.on("request", (request) => {
  const url = new URL(request.url());
  if (url.origin === baseUrl) {
    requestLog.push(`${request.method()} ${url.pathname}`);
  }
});

let token;
const loginResponsePromise = page.waitForResponse(
  (response) =>
    response.url() === `${baseUrl}/api/auth/login` && response.request().method() === "POST",
);
await page.goto(`${baseUrl}/login`, { waitUntil: "domcontentloaded" });
await page.locator('form[aria-label="Login form"]').waitFor();
await page.locator("#email").fill(account.email);
await page.locator("#password").fill(account.password);
await page.locator('[data-testid="login-button"]').click();
const loginResponse = await loginResponsePromise;
assert.equal(loginResponse.status(), 200, "real LibreChat login must succeed");
token = (await loginResponse.json()).token;
assert(token, "real login response did not include a token");
await page.waitForURL(/\/c\/new/, { timeout: 30_000 });

const api = async (method, route, data) => {
  const response = await page.request.fetch(`${baseUrl}${route}`, {
    method,
    headers: { Authorization: `Bearer ${token}` },
    data,
  });
  const text = await response.text();
  let body;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  return { status: response.status(), body };
};

const before = await api("GET", "/life-api/api/v1/me");
assert.equal(before.status, 200);
assert.equal(before.body.memory_consent, false);
assert.equal(before.body.image_consent, false);
assert.equal(before.body.egress_consents.semantic_scoring.granted, false);
assert.equal(before.body.egress_consents.prompt_generation.granted, false);
assert.equal(before.body.egress_consents.image_generation.granted, false);

await page.goto(`${baseUrl}/moments/settings`, { waitUntil: "domcontentloaded" });
await page.getByRole("heading", { name: "自动回忆设置" }).waitFor({ timeout: 30_000 });

async function enableSwitch(name, pathSuffix) {
  const control = page.getByRole("switch", { name });
  await control.waitFor({ state: "visible" });
  const enabledDeadline = Date.now() + 30_000;
  while (!(await control.isEnabled())) {
    assert(Date.now() < enabledDeadline, `consent switch did not become enabled: ${name}`);
    await page.waitForTimeout(100);
  }
  const responsePromise = page.waitForResponse(
    (response) =>
      response.request().method() !== "GET" &&
      response.url().includes(pathSuffix) &&
      response.status() === 200,
  );
  await control.click();
  await responsePromise;
}

await enableSwitch("自动整理生活事件和长期事实", "/api/v1/me/settings");
await enableSwitch("允许使用已保存事件生成回忆图片", "/api/v1/me/settings");
await enableSwitch(
  "允许 DeepSeek 对候选回忆进行 P04 语义评分",
  "/moment-egress-consents/semantic_scoring",
);
await enableSwitch(
  "允许 DeepSeek 将入选事件扩写为 Kolors 生图提示词",
  "/moment-egress-consents/prompt_generation",
);
await enableSwitch(
  "允许 Kolors 根据入选生活场景生成图片",
  "/moment-egress-consents/image_generation",
);

await page.waitForTimeout(1_000);
const settingsResponse = await api("GET", "/life-api/api/v1/moment-settings");
assert.equal(settingsResponse.status, 200);
const settings = {
  ...settingsResponse.body,
  enabled: true,
  timezone: "Asia/Hong_Kong",
  ends: [firstEnd, secondEnd, "24:00"],
};
delete settings.proposed;
const savedSettings = await api("PUT", "/life-api/api/v1/moment-settings", settings);
assert.equal(savedSettings.status, 200);
assert.equal(savedSettings.body.enabled, true);
assert.deepEqual(savedSettings.body.ends, [firstEnd, secondEnd, "24:00"]);

const afterConsent = await api("GET", "/life-api/api/v1/me");
assert.equal(afterConsent.body.memory_consent, true);
assert.equal(afterConsent.body.image_consent, true);
assert.equal(afterConsent.body.egress_consents.semantic_scoring.granted, true);
assert.equal(afterConsent.body.egress_consents.prompt_generation.granted, true);
assert.equal(afterConsent.body.egress_consents.image_generation.granted, true);
await page.screenshot({
  path: path.join(outputDir, "consent-settings-desktop-1440.png"),
  fullPage: true,
});

await page.goto(`${baseUrl}/c/new`, { waitUntil: "domcontentloaded" });
const composer = page.locator('[data-testid="text-input"]');
await composer.waitFor({ timeout: 30_000 });
await composer.fill(promptText);
await composer.press("Enter");

await page.getByText(promptText, { exact: true }).first().waitFor({ timeout: 30_000 });
await page.locator('[data-testid="send-button"]').waitFor({ state: "visible", timeout: 120_000 });
await page.screenshot({
  path: path.join(outputDir, "chat-after-send-desktop-1440.png"),
  fullPage: true,
});

const boundary = new Date(`${new Date().toISOString().slice(0, 10)}T${firstEnd}:00+08:00`);
if (boundary.getTime() < Date.now()) {
  boundary.setDate(boundary.getDate() + 1);
}
const deadline = boundary.getTime() + 12 * 60_000;
let momentsBody = null;
let generatedMoment = null;
while (Date.now() < deadline) {
  const response = await api("GET", "/life-api/api/v1/moments");
  assert.equal(response.status, 200);
  momentsBody = response.body;
  generatedMoment = momentsBody.moments.find(
    (moment) =>
      moment.display_kind === "IMAGE" &&
      moment.displayable === true &&
      moment.media?.sha256 &&
      moment.source_memory_ids?.length,
  );
  if (generatedMoment) {
    break;
  }
  await page.waitForTimeout(5_000);
}
assert(generatedMoment, "no real generated image moment appeared after the settlement boundary");

await page.goto(`${baseUrl}/memories`, { waitUntil: "domcontentloaded" });
const imageCard = page.locator('[data-testid="moment-card"]').filter({
  hasText: generatedMoment.caption,
});
await imageCard.waitFor({ timeout: 30_000 });
const thumbnail = imageCard.locator("img");
await thumbnail.waitFor({ state: "visible" });
await thumbnail.evaluate(
  (image) =>
    new Promise((resolve, reject) => {
      if (image.complete && image.naturalWidth > 0) return resolve();
      image.addEventListener("load", () => resolve(), { once: true });
      image.addEventListener("error", () => reject(new Error("image failed")), { once: true });
    }),
);
const desktopImage = await thumbnail.evaluate((image) => ({
  naturalWidth: image.naturalWidth,
  naturalHeight: image.naturalHeight,
  src: image.currentSrc,
}));
await page.screenshot({
  path: path.join(outputDir, "memories-desktop-1440.png"),
  fullPage: true,
});
const desktopSize = await page.evaluate(() => ({
  scrollWidth: document.documentElement.scrollWidth,
  clientWidth: document.documentElement.clientWidth,
}));
assert(desktopSize.scrollWidth <= desktopSize.clientWidth);

await page.setViewportSize({ width: 390, height: 844 });
await page.goto(`${baseUrl}/memories`, { waitUntil: "domcontentloaded" });
const mobileCard = page.locator('[data-testid="moment-card"]').filter({
  hasText: generatedMoment.caption,
});
await mobileCard.locator("img").waitFor({ timeout: 30_000 });
await page.screenshot({
  path: path.join(outputDir, "memories-mobile-390.png"),
  fullPage: true,
});
const mobileSize = await page.evaluate(() => ({
  scrollWidth: document.documentElement.scrollWidth,
  clientWidth: document.documentElement.clientWidth,
}));
assert(mobileSize.scrollWidth <= mobileSize.clientWidth);

const chatPost = requestLog.filter(
  (line) =>
    line.startsWith("POST /api/") &&
    !line.startsWith("POST /api/auth/") &&
    !line.startsWith("POST /life-api/"),
);
assert(chatPost.length >= 1, "real LibreChat chat endpoint was not called");
assert.equal(pageErrors.length, 0, pageErrors.join("\n"));

const result = {
  status: "PASS",
  classification: "REAL_E2E",
  base_url: baseUrl,
  login_mode: "REAL_LIBRECHAT_SESSION",
  prompt: promptText,
  window: {
    enabled_at: savedSettings.body.enabled_at,
    ends: savedSettings.body.ends,
    timezone: savedSettings.body.timezone,
  },
  consent: {
    initial: before.body.egress_consents,
    final: afterConsent.body.egress_consents,
    ui_toggles_used: true,
  },
  chat_requests: chatPost,
  moment_id: generatedMoment.moment_id,
  source_memory_ids: generatedMoment.source_memory_ids,
  caption: generatedMoment.caption,
  image_media: generatedMoment.media,
  thumbnail_natural_size: desktopImage,
  layout: { desktop: desktopSize, mobile: mobileSize },
  screenshots: {
    settings: path.join(outputDir, "consent-settings-desktop-1440.png"),
    chat: path.join(outputDir, "chat-after-send-desktop-1440.png"),
    desktop: path.join(outputDir, "memories-desktop-1440.png"),
    mobile: path.join(outputDir, "memories-mobile-390.png"),
  },
  request_log: requestLog,
  console_errors: consoleErrors,
  page_errors: pageErrors,
  completed_at: new Date().toISOString(),
};
await writeFile(
  path.join(outputDir, "browser-e2e-result.json"),
  JSON.stringify(result, null, 2),
);
console.log(JSON.stringify(result, null, 2));

await context.close();
await browser.close();
