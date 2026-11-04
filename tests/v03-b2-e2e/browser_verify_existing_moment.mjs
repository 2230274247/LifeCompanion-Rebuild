import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";

const baseUrl = process.env.BASE_URL || "http://127.0.0.1:4182";
const accountsPath = process.env.ACCOUNTS_FILE;
const outputDir = path.resolve(process.env.OUTPUT_DIR || ".");
const productRoot = path.resolve(process.env.PRODUCT_ROOT || ".");
const conversationId = process.env.CONVERSATION_ID;
const promptText = process.env.PROMPT_TEXT;
const chromePath =
  process.env.CHROME_PATH || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";

assert(accountsPath, "ACCOUNTS_FILE is required");
assert(conversationId, "CONVERSATION_ID is required");
assert(promptText, "PROMPT_TEXT is required");
const require = createRequire(path.join(productRoot, "package.json"));
const { chromium } = require("@playwright/test");
const account = JSON.parse(await readFile(accountsPath, "utf8"))["fixed-test"];

const browser = await chromium.launch({ headless: true, executablePath: chromePath });
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  colorScheme: "light",
  serviceWorkers: "block",
});
const page = await context.newPage();
const consoleErrors = [];
const pageErrors = [];
page.on("console", (message) => {
  if (message.type() === "error") {
    consoleErrors.push(message.text());
  }
});
page.on("pageerror", (error) => pageErrors.push(error.stack || error.message));

try {
  await page.goto(`${baseUrl}/login`, { waitUntil: "domcontentloaded" });
  await page.locator('form[aria-label="Login form"]').waitFor();
  await page.locator("#email").fill(account.email);
  await page.locator("#password").fill(account.password);
  await page.locator('[data-testid="login-button"]').click();
  await page.waitForURL(/\/c\/new/, { timeout: 30_000 });

  await page.goto(`${baseUrl}/c/${conversationId}`, {
    waitUntil: "domcontentloaded",
  });
  await page.getByText(promptText, { exact: true }).first().waitFor({
    timeout: 30_000,
  });
  const actions = page.locator('[data-testid="direct-moment-test-actions"]');
  await actions.waitFor({ timeout: 30_000 });
  const memoriesLink = actions.getByRole("link", { name: "打开我的回忆" });
  assert.equal(await memoriesLink.getAttribute("href"), "/memories");
  assert.equal(
    await page.locator('[data-testid="direct-moment-generate"]').isDisabled(),
    true,
    "one-shot budget must now be exhausted",
  );
  await page.screenshot({
    path: path.join(outputDir, "chat-direct-test-button-after-fix-desktop-1440.png"),
    fullPage: true,
  });

  await memoriesLink.click();
  await page.waitForURL(/\/memories(?:\/|$)/, { timeout: 30_000 });
  const card = page.locator('[data-testid="moment-card"]').filter({
    hasText: promptText,
  });
  await card.waitFor({ timeout: 30_000 });
  await card.getByText("AI 生成", { exact: true }).waitFor();
  const thumbnail = card.locator("img");
  await thumbnail.waitFor({ state: "visible", timeout: 30_000 });
  await thumbnail.evaluate(
    (image) =>
      new Promise((resolve, reject) => {
        if (image.complete && image.naturalWidth > 0) return resolve();
        image.addEventListener("load", () => resolve(), { once: true });
        image.addEventListener("error", () => reject(new Error("image failed")), {
          once: true,
        });
      }),
  );
  const thumbnailInfo = await thumbnail.evaluate((image) => ({
    naturalWidth: image.naturalWidth,
    naturalHeight: image.naturalHeight,
    src: image.currentSrc,
  }));
  await page.screenshot({
    path: path.join(outputDir, "direct-moment-desktop-1440.png"),
    fullPage: true,
  });
  const desktopLayout = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  assert(desktopLayout.scrollWidth <= desktopLayout.clientWidth);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload({ waitUntil: "domcontentloaded" });
  const mobileCard = page.locator('[data-testid="moment-card"]').filter({
    hasText: promptText,
  });
  await mobileCard.waitFor({ timeout: 30_000 });
  await mobileCard.locator("img").waitFor({ state: "visible", timeout: 30_000 });
  await page.screenshot({
    path: path.join(outputDir, "direct-moment-mobile-390.png"),
    fullPage: true,
  });
  const mobileLayout = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  assert(mobileLayout.scrollWidth <= mobileLayout.clientWidth);

  const result = {
    status: "PASS",
    classification: "REAL_DIRECT_TEST_DISPLAY",
    test_mode: "DIRECT_TEST_BYPASS",
    conversation_id: conversationId,
    prompt: promptText,
    corrected_link: "/memories",
    one_shot_button_disabled: true,
    thumbnail: thumbnailInfo,
    layout: { desktop: desktopLayout, mobile: mobileLayout },
    screenshots: {
      chat: path.join(outputDir, "chat-direct-test-button-after-fix-desktop-1440.png"),
      desktop: path.join(outputDir, "direct-moment-desktop-1440.png"),
      mobile: path.join(outputDir, "direct-moment-mobile-390.png"),
    },
    console_errors: consoleErrors,
    page_errors: pageErrors,
    completed_at: new Date().toISOString(),
  };
  await writeFile(
    path.join(outputDir, "browser-direct-test-display-result.json"),
    JSON.stringify(result, null, 2),
  );
  console.log(JSON.stringify(result, null, 2));
} finally {
  await context.close();
  await browser.close();
}
