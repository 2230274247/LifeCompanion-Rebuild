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
const momentId = process.env.MOMENT_ID;
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
const failedResponses = [];
const pageErrors = [];
const directPosts = [];
let authorizationHeader = null;

page.on("console", (message) => {
  if (message.type() === "error") {
    consoleErrors.push(message.text());
  }
});
page.on("pageerror", (error) => pageErrors.push(error.stack || error.message));
page.on("response", (response) => {
  if (response.status() >= 400 && new URL(response.url()).origin === baseUrl) {
    failedResponses.push({
      method: response.request().method(),
      path: new URL(response.url()).pathname,
      status: response.status(),
    });
  }
});
page.on("request", (request) => {
  const url = new URL(request.url());
  const authorization = request.headers()["authorization"];
  if (authorization && url.origin === baseUrl) {
    authorizationHeader = authorization;
  }
  if (
    request.method() === "POST" &&
    url.pathname === "/life-api/api/v1/test/direct-moment"
  ) {
    directPosts.push(url.pathname);
  }
});

async function lifeApi(pathname) {
  assert(authorizationHeader, "authenticated request header is not available");
  return page.evaluate(async ({ target, authorization }) => {
    const response = await fetch(target, {
      credentials: "include",
      headers: { Authorization: authorization },
    });
    const body = await response.json();
    return { status: response.status, body };
  }, { target: `/life-api${pathname}`, authorization: authorizationHeader });
}

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
  const button = page.locator('[data-testid="direct-moment-generate"]');
  await button.waitFor({ state: "visible", timeout: 30_000 });

  const me = await lifeApi("/api/v1/me");
  assert.equal(me.status, 200);
  const permissions = {
    memory_consent: me.body.memory_consent,
    recall_consent: me.body.recall_consent,
    sensitive_consent: me.body.sensitive_consent,
    image_consent: me.body.image_consent,
    notification_consent: me.body.notification_consent,
  };
  assert(Object.values(permissions).every(Boolean), JSON.stringify(permissions));
  const egress = me.body.egress_consents;
  assert.equal(egress.semantic_scoring.granted, true);
  assert.equal(egress.prompt_generation.granted, true);
  assert.equal(egress.image_generation.granted, true);

  const directStatus = await lifeApi("/api/v1/test/direct-moment");
  assert.equal(directStatus.status, 200);
  assert.equal(directStatus.body.enabled, true);
  assert.equal(directStatus.body.provider_ready, true);
  assert.equal(directStatus.body.unlimited, true);

  assert.equal(await button.isEnabled(), true);
  await actions.getByText("测试额度：不限", { exact: true }).waitFor();
  assert.equal(
    await actions.getByText("测试生图预算已用尽", { exact: true }).count(),
    0,
  );
  await page.screenshot({
    path: path.join(outputDir, "chat-unlimited-direct-test-desktop-1440.png"),
    fullPage: true,
  });

  const desktopChatLayout = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  assert(desktopChatLayout.scrollWidth <= desktopChatLayout.clientWidth);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByText(promptText, { exact: true }).first().waitFor({
    timeout: 30_000,
  });
  await page.locator('[data-testid="direct-moment-test-actions"]').waitFor({
    timeout: 30_000,
  });
  await page
    .locator('[data-testid="direct-moment-test-actions"]')
    .getByText("测试额度：不限", { exact: true })
    .waitFor();
  await page.screenshot({
    path: path.join(outputDir, "chat-unlimited-direct-test-mobile-390.png"),
    fullPage: true,
  });
  const mobileChatLayout = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  assert(mobileChatLayout.scrollWidth <= mobileChatLayout.clientWidth);

  await page.goto(`${baseUrl}/memories`, { waitUntil: "domcontentloaded" });
  const card = momentId
    ? page.locator(`[data-testid="moment-card"][href="/moments/${momentId}"]`)
    : page.locator('[data-testid="moment-card"]').filter({ hasText: promptText });
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
  }));
  await page.screenshot({
    path: path.join(outputDir, "memories-existing-real-image-mobile-390.png"),
    fullPage: true,
  });

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.reload({ waitUntil: "domcontentloaded" });
  const desktopCard = momentId
    ? page.locator(`[data-testid="moment-card"][href="/moments/${momentId}"]`)
    : page.locator('[data-testid="moment-card"]').filter({ hasText: promptText });
  await desktopCard.waitFor({ timeout: 30_000 });
  await desktopCard.locator("img").waitFor({ state: "visible", timeout: 30_000 });
  await page.screenshot({
    path: path.join(outputDir, "memories-existing-real-image-desktop-1440.png"),
    fullPage: true,
  });
  const desktopMemoriesLayout = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  assert(desktopMemoriesLayout.scrollWidth <= desktopMemoriesLayout.clientWidth);

  const result = {
    status: "PASS",
    classification: "UNLIMITED_TEST_ONLY",
    account: {
      email: account.email,
      username: account.username,
      librechat_user_id: account.librechat_user_id,
      protected: true,
    },
    permissions,
    egress_consents: egress,
    direct_test_status: directStatus.body,
    conversation_id: conversationId,
    moment_id: momentId || null,
    prompt: promptText,
    direct_test_posts_during_check: directPosts.length,
    button_enabled: true,
    budget_label: "测试额度：不限",
    existing_real_moment_visible: true,
    thumbnail: thumbnailInfo,
    layout: {
      desktop_chat: desktopChatLayout,
      mobile_chat: mobileChatLayout,
      desktop_memories: desktopMemoriesLayout,
    },
    screenshots: {
      desktop_chat: path.join(
        outputDir,
        "chat-unlimited-direct-test-desktop-1440.png",
      ),
      mobile_chat: path.join(
        outputDir,
        "chat-unlimited-direct-test-mobile-390.png",
      ),
      mobile_memories: path.join(
        outputDir,
        "memories-existing-real-image-mobile-390.png",
      ),
      desktop_memories: path.join(
        outputDir,
        "memories-existing-real-image-desktop-1440.png",
      ),
    },
    console_errors: consoleErrors,
    failed_responses: failedResponses,
    page_errors: pageErrors,
    completed_at: new Date().toISOString(),
  };
  await writeFile(
    path.join(outputDir, "browser-unlimited-direct-test-result.json"),
    JSON.stringify(result, null, 2),
  );
  console.log(JSON.stringify(result, null, 2));
} finally {
  await context.close();
  await browser.close();
}
