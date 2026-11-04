import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";

const baseUrl = process.env.BASE_URL || "http://127.0.0.1:4182";
const accountsPath = process.env.ACCOUNTS_FILE;
const outputDir = path.resolve(process.env.OUTPUT_DIR || ".");
const productRoot = path.resolve(process.env.PRODUCT_ROOT || ".");
const accountKey = process.env.ACCOUNT_KEY || "fixed-test";
const chromePath =
  process.env.CHROME_PATH || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const promptText =
  "今天下午我在厨房窗边给一盆薄荷浇水，黄色小水壶放在木桌上，窗外下着细雨，我闻到了清新的叶子味道。";

assert(accountsPath, "ACCOUNTS_FILE is required");
assert(process.env.PRODUCT_ROOT, "PRODUCT_ROOT is required");
const require = createRequire(path.join(productRoot, "package.json"));
const { chromium } = require("@playwright/test");
const accounts = JSON.parse(await readFile(accountsPath, "utf8"));
const account = accounts[accountKey];
assert(account, `account not found: ${accountKey}`);

const requestLog = [];
const directPosts = [];
const consoleErrors = [];
const pageErrors = [];
const browser = await chromium.launch({ headless: true, executablePath: chromePath });
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  colorScheme: "light",
  serviceWorkers: "block",
});
const page = await context.newPage();
page.on("request", (request) => {
  const url = new URL(request.url());
  if (url.origin === baseUrl) {
    requestLog.push(`${request.method()} ${url.pathname}`);
  }
  if (
    request.method() === "POST" &&
    url.pathname === "/life-api/api/v1/test/direct-moment"
  ) {
    directPosts.push(url.pathname);
  }
});
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

  await page.goto(`${baseUrl}/c/new`, { waitUntil: "domcontentloaded" });
  const composer = page.locator('[data-testid="text-input"]');
  await composer.waitFor({ timeout: 30_000 });
  await composer.fill(promptText);
  await composer.press("Enter");
  await page.getByText(promptText, { exact: true }).first().waitFor({
    timeout: 30_000,
  });
  await page.locator('[data-testid="send-button"]').waitFor({
    state: "visible",
    timeout: 120_000,
  });

  const testButton = page.locator('[data-testid="direct-moment-generate"]');
  await testButton.waitFor({ state: "visible", timeout: 30_000 });
  await testButton.waitFor({ state: "attached" });
  const testActions = page.locator('[data-testid="direct-moment-test-actions"]');
  assert.equal(await testActions.count(), 1, "expected one direct-test action panel");
  assert.equal(await testButton.isEnabled(), true, "direct-test button must be enabled");
  await page.screenshot({
    path: path.join(outputDir, "chat-direct-test-button-desktop-1440.png"),
    fullPage: true,
  });

  const directResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/life-api/api/v1/test/direct-moment",
    { timeout: 180_000 },
  );
  await testButton.click();
  const directResponse = await directResponsePromise;
  const directBody = await directResponse.json();
  assert.equal(directResponse.status(), 200, JSON.stringify(directBody));
  assert.equal(directBody.test_mode, "DIRECT_TEST_BYPASS");
  assert.equal(directBody.moment.status, "generated");
  assert.equal(directBody.moment.display_kind, "IMAGE");
  assert.equal(directBody.moment.ai_generated, true);
  assert.equal(directPosts.length, 1, "one explicit click must cause exactly one POST");

  await page.waitForURL(/\/moments(?:\/|$)/, { timeout: 30_000 });
  const card = page.locator('[data-testid="moment-card"]').filter({
    hasText: promptText,
  });
  await card.waitFor({ timeout: 30_000 });
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
  await page.locator('[data-testid="moment-card"]').filter({ hasText: promptText }).waitFor({
    timeout: 30_000,
  });
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
    classification: "REAL_DIRECT_TEST",
    test_mode: "DIRECT_TEST_BYPASS",
    account_key: accountKey,
    prompt: promptText,
    chat_reply_observed: true,
    direct_post_count: directPosts.length,
    direct_response_status: directResponse.status(),
    moment: directBody.moment,
    thumbnail: thumbnailInfo,
    layout: { desktop: desktopLayout, mobile: mobileLayout },
    screenshots: {
      chat: path.join(outputDir, "chat-direct-test-button-desktop-1440.png"),
      desktop: path.join(outputDir, "direct-moment-desktop-1440.png"),
      mobile: path.join(outputDir, "direct-moment-mobile-390.png"),
    },
    request_log: requestLog,
    console_errors: consoleErrors,
    page_errors: pageErrors,
    completed_at: new Date().toISOString(),
  };
  await writeFile(
    path.join(outputDir, "browser-direct-test-result.json"),
    JSON.stringify(result, null, 2),
  );
  console.log(JSON.stringify(result, null, 2));
} catch (error) {
  const failure = {
    status: "FAIL",
    classification: "REAL_DIRECT_TEST",
    error: error.stack || error.message,
    direct_post_count: directPosts.length,
    request_log: requestLog,
    console_errors: consoleErrors,
    page_errors: pageErrors,
    failed_at: new Date().toISOString(),
  };
  await page.screenshot({
    path: path.join(outputDir, "direct-test-failure.png"),
    fullPage: true,
  });
  await writeFile(
    path.join(outputDir, "browser-direct-test-failure.json"),
    JSON.stringify(failure, null, 2),
  );
  throw error;
} finally {
  await context.close();
  await browser.close();
}
