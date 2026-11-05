const fs = require("node:fs");
const path = require("node:path");

const projectRoot = path.resolve(__dirname, "..", "..");
const librechatRoot = path.join(
  projectRoot,
  ".work",
  "p00-p07-20261103",
  "products",
  "librechat-custom",
);
const { chromium } = require(
  path.join(librechatRoot, "node_modules", "@playwright", "test"),
);

const baseURL = process.env.LIFE_UI_BASE_URL || "http://127.0.0.1:3090";
const lifeTarget =
  process.env.LIFE_UI_FIXTURE_TARGET || "http://127.0.0.1:8036";
const accountFile =
  process.env.LIFE_UI_ACCOUNT_FILE ||
  path.join(projectRoot, "infra", "runtime", "test-accounts.json");
const accountKey = process.env.LIFE_UI_ACCOUNT_KEY || "librechat";
const tokenFile =
  process.env.LIFE_UI_BEARER_TOKEN_FILE ||
  path.join(process.env.TEMP || ".", "life-ui-image-fixture-8036", "token.txt");
const outputDir = path.resolve(
  __dirname,
  process.argv[2] || "after-image-fixture",
);

const viewports = [
  { name: "390x844", width: 390, height: 844 },
  { name: "430x932", width: 430, height: 932 },
  { name: "768x1024", width: 768, height: 1024 },
  { name: "1440x1000", width: 1440, height: 1000 },
  { name: "1920x1080", width: 1920, height: 1080 },
];

function readAccount() {
  const accounts = JSON.parse(fs.readFileSync(accountFile, "utf8"));
  const account = accounts[accountKey];
  if (!account?.email || !account?.password) {
    throw new Error(
      `Missing browser account "${accountKey}" in ${accountFile}`,
    );
  }
  return account;
}

async function installFixtureBridge(context, token) {
  await context.route("**/life-api/**", async (route) => {
    const request = route.request();
    const incoming = new URL(request.url());
    const target = new URL(
      `${incoming.pathname.slice("/life-api".length)}${incoming.search}`,
      lifeTarget,
    );
    const headers = { ...request.headers(), authorization: `Bearer ${token}` };
    delete headers.cookie;
    delete headers.host;
    try {
      const response = await route.fetch({
        url: target.toString(),
        method: request.method(),
        headers,
        body: ["GET", "HEAD"].includes(request.method())
          ? undefined
          : request.postData(),
        maxRedirects: 0,
      });
      await route.fulfill({ response });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (/Request context disposed|Target closed|Target page/i.test(message)) {
        return;
      }
      await route.abort("failed").catch(() => undefined);
      throw error;
    }
  });
}

async function resetScroll(page) {
  await page.evaluate(() => {
    for (const element of document.querySelectorAll("*")) {
      if (element instanceof HTMLElement && element.scrollTop) {
        element.scrollTop = 0;
      }
    }
    window.scrollTo(0, 0);
  });
}

async function waitForMomentImages(page) {
  await page.waitForFunction(
    () => {
      const cards = Array.from(
        document.querySelectorAll('[data-testid="moment-card"]'),
      );
      return (
        cards.length > 0 &&
        cards.every((card) => card.querySelector("img")?.complete)
      );
    },
    { timeout: 20_000 },
  );
  await page.waitForTimeout(800);
}

async function collectPageState(page) {
  return page.evaluate(() => {
    const images = Array.from(document.images);
    return {
      title: document.title,
      url: window.location.href,
      lifeChatHeaders: document.querySelectorAll(
        '[data-testid="life-chat-header"]',
      ).length,
      lifeSiteHeaders: document.querySelectorAll(
        '[data-testid="life-site-header"]',
      ).length,
      activeNavigation: Array.from(
        document.querySelectorAll(
          '[data-testid="life-site-header"] nav a[aria-current="page"]',
        ),
      ).map(
        (element) =>
          element.getAttribute("aria-label") ||
          element.textContent?.trim() ||
          "",
      ),
      momentCards: document.querySelectorAll('[data-testid="moment-card"]')
        .length,
      imageCount: images.length,
      loadedImageCount: images.filter(
        (image) => image.complete && image.naturalWidth > 0,
      ).length,
      brokenImageCount: images.filter(
        (image) => image.complete && image.naturalWidth === 0,
      ).length,
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: Math.max(
        document.documentElement.scrollWidth,
        document.body?.scrollWidth || 0,
      ),
    };
  });
}

async function captureMemories(page, viewport, result) {
  await page.goto(`${baseURL}/memories`, { waitUntil: "domcontentloaded" });
  await page
    .locator('[data-testid="life-site-header"]')
    .waitFor({ timeout: 15_000 });
  await page
    .locator('[data-testid="moment-card"]')
    .first()
    .waitFor({ timeout: 20_000 });
  await waitForMomentImages(page);
  await resetScroll(page);
  await page.evaluate(() => {
    document
      .querySelectorAll(
        '.ReactQueryDevtools, .ReactQueryDevtoolsPanel, [aria-label="Open React Query Devtools"]',
      )
      .forEach((node) => node.remove());
  });
  await page.waitForTimeout(300);

  const screenshot = path.join(
    outputDir,
    `memories-images-${viewport.name}.png`,
  );
  await page.screenshot({
    path: screenshot,
    fullPage: false,
    animations: "disabled",
    caret: "hide",
    timeout: 20_000,
  });
  const state = await collectPageState(page);
  result.push({
    route: "/memories",
    viewport: viewport.name,
    screenshot,
    headerVisible: state.lifeSiteHeaders === 1,
    totalLifeHeaders: state.lifeChatHeaders + state.lifeSiteHeaders,
    activeNavigation: state.activeNavigation,
    momentCards: state.momentCards,
    imageCount: state.imageCount,
    loadedImageCount: state.loadedImageCount,
    brokenImageCount: state.brokenImageCount,
    horizontalOverflow: state.scrollWidth > state.clientWidth + 1,
  });
}

async function captureDetail(page, viewport, result) {
  const card = page.locator('[data-testid="moment-card"]').first();
  await card.focus();
  const focused = await card.evaluate(
    (element) => element === document.activeElement,
  );
  await page.keyboard.press("Enter");
  await page.waitForURL(/\/moments\/mom_/, { timeout: 15_000 });
  await page
    .locator('[data-testid="life-site-header"]')
    .waitFor({ timeout: 15_000 });
  await page.waitForFunction(
    () => {
      const image = document.querySelector(
        'button[aria-haspopup="dialog"] img',
      );
      return image?.complete && image.naturalWidth > 0;
    },
    { timeout: 20_000 },
  );
  await resetScroll(page);
  await page.evaluate(() => {
    document
      .querySelectorAll(
        '.ReactQueryDevtools, .ReactQueryDevtoolsPanel, [aria-label="Open React Query Devtools"]',
      )
      .forEach((node) => node.remove());
  });
  await page.waitForTimeout(500);

  const screenshot = path.join(outputDir, `moment-detail-${viewport.name}.png`);
  await page.screenshot({
    path: screenshot,
    fullPage: false,
    animations: "disabled",
    caret: "hide",
    timeout: 20_000,
  });

  const imageButton = page.locator('button[aria-haspopup="dialog"]').first();
  await imageButton.focus();
  await page.keyboard.press("Enter");
  const dialogOpened = await page
    .locator('[role="dialog"]')
    .isVisible()
    .catch(() => false);
  await page.keyboard.press("Escape");
  const dialogClosed = await page
    .locator('[role="dialog"]')
    .isHidden()
    .catch(() => false);

  const state = await collectPageState(page);
  result.push({
    route: new URL(page.url()).pathname,
    viewport: viewport.name,
    screenshot,
    headerVisible: state.lifeSiteHeaders === 1,
    totalLifeHeaders: state.lifeChatHeaders + state.lifeSiteHeaders,
    activeNavigation: state.activeNavigation,
    imageCount: state.imageCount,
    loadedImageCount: state.loadedImageCount,
    brokenImageCount: state.brokenImageCount,
    horizontalOverflow: state.scrollWidth > state.clientWidth + 1,
    keyboardCardActivation: focused,
    imageDialog: { opened: dialogOpened, closed: dialogClosed },
  });
}

async function inspectTilt(page) {
  await page.goto(`${baseURL}/memories`, { waitUntil: "domcontentloaded" });
  const card = page
    .locator('[data-life-tilt] [data-testid="moment-card"]')
    .first();
  await card.waitFor({ timeout: 20_000 });
  const box = await card.boundingBox();
  if (!box) {
    return { available: false };
  }

  await page.mouse.move(box.x + box.width * 0.8, box.y + box.height * 0.2);
  await page.waitForTimeout(350);
  const active = await page
    .locator("[data-life-tilt]")
    .first()
    .evaluate((element) => ({
      transform: element.style.transform,
      lightX: element.style.getPropertyValue("--life-light-x"),
      lightY: element.style.getPropertyValue("--life-light-y"),
    }));
  await page.mouse.move(2, 2);
  await page.waitForTimeout(350);
  const reset = await page
    .locator("[data-life-tilt]")
    .first()
    .evaluate((element) => ({
      transform: element.style.transform,
      lightX: element.style.getPropertyValue("--life-light-x"),
      lightY: element.style.getPropertyValue("--life-light-y"),
    }));

  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.mouse.move(box.x + box.width * 0.2, box.y + box.height * 0.8);
  await page.waitForTimeout(350);
  const reducedMotion = await page
    .locator("[data-life-tilt]")
    .first()
    .evaluate((element) => ({
      transform: element.style.transform,
      lightX: element.style.getPropertyValue("--life-light-x"),
      lightY: element.style.getPropertyValue("--life-light-y"),
    }));
  await page.emulateMedia({ reducedMotion: "no-preference" });

  return { available: true, active, reset, reducedMotion };
}

async function main() {
  fs.mkdirSync(outputDir, { recursive: true });
  const account = readAccount();
  const token = fs.readFileSync(tokenFile, "utf8").trim();
  const browser = await chromium.launch({
    headless: true,
    channel: process.env.LIFE_UI_CHROMIUM_CHANNEL || "chrome",
  });
  const context = await browser.newContext({
    baseURL,
    locale: "zh-CN",
    viewport: viewports[0],
  });
  await context.addInitScript(() => {
    localStorage.setItem("navVisible", "true");
    localStorage.setItem("lang", JSON.stringify("zh-Hans"));
  });

  const lifeResponses = [];
  context.on("response", (response) => {
    if (response.url().includes("/life-api/")) {
      lifeResponses.push({ status: response.status(), url: response.url() });
    }
  });
  await installFixtureBridge(context, token);

  const page = await context.newPage();
  await page.goto(`${baseURL}/login`, { waitUntil: "domcontentloaded" });
  await page.locator("#email").fill(account.email);
  await page.locator("#password").fill(account.password);
  await page.locator('[data-testid="login-button"]').click();
  await page.waitForURL(/\/c\//, { timeout: 30_000 });
  await page
    .locator('[data-testid="life-chat-header"]')
    .waitFor({ timeout: 15_000 });

  const result = [];
  for (const viewport of viewports) {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    await captureMemories(page, viewport, result);
    await captureDetail(page, viewport, result);
  }

  await page.setViewportSize({ width: 1440, height: 1000 });
  const tilt = await inspectTilt(page);
  const failedResponses = lifeResponses.filter(
    (response) => response.status >= 400,
  );
  const report = {
    generatedAt: new Date().toISOString(),
    baseURL,
    fixtureTarget: lifeTarget,
    accountKey,
    authBridge:
      "Playwright route adapter supplies a test-signed token issued by the isolated fixture core.",
    viewports,
    tilt,
    lifeResponses,
    results: result,
  };
  fs.writeFileSync(
    path.join(outputDir, "image-fixture-report.json"),
    `${JSON.stringify(report, null, 2)}\n`,
    "utf8",
  );

  console.log(
    JSON.stringify({
      outputDir,
      screenshots: result.length,
      routeChecks: result.length,
      headerFailures: result.filter(
        (item) => !item.headerVisible || item.totalLifeHeaders !== 1,
      ).length,
      overflowFailures: result.filter((item) => item.horizontalOverflow).length,
      brokenImages: result.reduce(
        (sum, item) => sum + (item.brokenImageCount || 0),
        0,
      ),
      lifeResponseFailures: failedResponses.length,
      tilt,
    }),
  );

  await context.unrouteAll({ behavior: "ignoreErrors" });
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
