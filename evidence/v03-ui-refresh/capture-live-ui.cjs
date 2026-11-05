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

const baseURL = process.env.LIFE_UI_BASE_URL || "http://127.0.0.1:3001";
const accountFile =
  process.env.LIFE_UI_ACCOUNT_FILE ||
  path.join(projectRoot, "infra", "runtime", "test-accounts.json");
const accountKey = process.env.LIFE_UI_ACCOUNT_KEY || "librechat";
const outputDir = path.resolve(__dirname, process.argv[2] || "after-live-data");

const viewports = [
  { name: "390x844", width: 390, height: 844 },
  { name: "430x932", width: 430, height: 932 },
  { name: "768x1024", width: 768, height: 1024 },
  { name: "1440x1000", width: 1440, height: 1000 },
  { name: "1920x1080", width: 1920, height: 1080 },
];

const routes = [
  { name: "chat", path: "/c/new", header: "life-chat-header" },
  { name: "memories", path: "/memories", header: "life-site-header" },
  { name: "reminders", path: "/reminders", header: "life-site-header" },
  { name: "settings", path: "/memory-settings", header: "life-site-header" },
  {
    name: "moment-settings",
    path: "/moments/settings",
    header: "life-site-header",
  },
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

async function waitForSettledUi(page) {
  await page.waitForTimeout(2400);
  await page
    .waitForFunction(
      () =>
        !document.body.innerText.includes("正在翻开回忆") &&
        !document.body.innerText.includes("正在加载..."),
      { timeout: 12_000 },
    )
    .catch(() => undefined);
  await page.waitForTimeout(800);
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

async function pageMetrics(page, route, viewport) {
  const metrics = await page.evaluate(() => {
    const bodyText = document.body?.innerText || "";
    const images = Array.from(document.images);
    return {
      title: document.title,
      bodyText,
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      bodyScrollWidth: document.body?.scrollWidth || 0,
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
      imageCount: images.length,
      loadedImageCount: images.filter(
        (image) => image.complete && image.naturalWidth > 0,
      ).length,
      brokenImageCount: images.filter(
        (image) => image.complete && image.naturalWidth === 0,
      ).length,
      buttonCount: document.querySelectorAll("button").length,
      disabledButtonCount: document.querySelectorAll("button:disabled").length,
    };
  });

  const boundaryMarkers = [
    "Oops! Something Unexpected Occurred",
    "Something went wrong",
    "Cannot read properties of undefined",
    "Application error",
  ];

  return {
    route: route.path,
    viewport: viewport.name,
    header: route.header,
    headerVisible: await page
      .locator(`[data-testid="${route.header}"]`)
      .isVisible()
      .catch(() => false),
    totalLifeHeaders: metrics.lifeChatHeaders + metrics.lifeSiteHeaders,
    lifeChatHeaders: metrics.lifeChatHeaders,
    lifeSiteHeaders: metrics.lifeSiteHeaders,
    activeNavigation: metrics.activeNavigation,
    horizontalOverflow:
      metrics.scrollWidth > metrics.clientWidth + 1 ||
      metrics.bodyScrollWidth > metrics.clientWidth + 1,
    width: metrics.clientWidth,
    scrollWidth: Math.max(metrics.scrollWidth, metrics.bodyScrollWidth),
    imageCount: metrics.imageCount,
    loadedImageCount: metrics.loadedImageCount,
    brokenImageCount: metrics.brokenImageCount,
    buttonCount: metrics.buttonCount,
    disabledButtonCount: metrics.disabledButtonCount,
    errorBoundary:
      boundaryMarkers.find((marker) => metrics.bodyText.includes(marker)) ||
      null,
    title: metrics.title,
    bodyText: metrics.bodyText.slice(0, 1500),
  };
}

async function captureRoute(page, route, viewport, result) {
  console.log(`capture ${route.name} ${viewport.name}`);
  const consoleErrors = [];
  const pageErrors = [];
  const failedResponses = [];
  const lifeMutationRequests = [];

  const onConsole = (message) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  };
  const onPageError = (error) => pageErrors.push(error.message);
  const onResponse = (response) => {
    if (response.status() >= 400) {
      failedResponses.push({ status: response.status(), url: response.url() });
    }
  };
  const onRequest = (request) => {
    if (
      request.url().includes("/life-api/") &&
      !["GET", "HEAD", "OPTIONS"].includes(request.method())
    ) {
      lifeMutationRequests.push({
        method: request.method(),
        url: request.url(),
      });
    }
  };

  page.on("console", onConsole);
  page.on("pageerror", onPageError);
  page.on("response", onResponse);
  page.on("request", onRequest);

  try {
    await page.goto(`${baseURL}${route.path}`, {
      waitUntil: "domcontentloaded",
      timeout: 30_000,
    });
    await page
      .locator(`[data-testid="${route.header}"]`)
      .waitFor({ state: "visible", timeout: 15_000 })
      .catch(() => undefined);
    await waitForSettledUi(page);
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
      `${route.name}-${viewport.name}.png`,
    );
    let screenshotError = null;
    try {
      await page.screenshot({
        path: screenshot,
        fullPage: false,
        animations: "disabled",
        caret: "hide",
        timeout: 20_000,
      });
    } catch (error) {
      screenshotError = error instanceof Error ? error.message : String(error);
    }

    result.push({
      ...(await pageMetrics(page, route, viewport)),
      screenshot,
      screenshotError,
      consoleErrors,
      pageErrors,
      failedResponses,
      lifeMutationRequests,
    });
  } finally {
    page.off("console", onConsole);
    page.off("pageerror", onPageError);
    page.off("response", onResponse);
    page.off("request", onRequest);
  }
}

async function captureDetails(page, viewport, result) {
  await page.goto(`${baseURL}/memories`, { waitUntil: "domcontentloaded" });
  await page
    .locator('[data-testid="life-site-header"]')
    .waitFor({ timeout: 15_000 });
  await waitForSettledUi(page);
  await resetScroll(page);

  const memoryLink = page.locator('a[href^="/memories/evt_"]').first();
  if ((await memoryLink.count()) > 0) {
    await memoryLink.click();
    await page
      .locator('[data-testid="life-site-header"]')
      .waitFor({ timeout: 15_000 });
    await waitForSettledUi(page);
    await resetScroll(page);
    await page.evaluate(() => {
      document
        .querySelectorAll(
          '.ReactQueryDevtools, .ReactQueryDevtoolsPanel, [aria-label="Open React Query Devtools"]',
        )
        .forEach((node) => node.remove());
    });
    const screenshot = path.join(
      outputDir,
      `memory-detail-${viewport.name}.png`,
    );
    await page.screenshot({
      path: screenshot,
      fullPage: false,
      animations: "disabled",
      caret: "hide",
      timeout: 20_000,
    });
    result.push({
      route: page.url(),
      viewport: viewport.name,
      screenshot,
      ...(await pageMetrics(
        page,
        { path: "/memories/:eventId", header: "life-site-header" },
        viewport,
      )),
    });
  }

  const momentLink = page.locator('[data-testid="moment-card"]').first();
  if ((await momentLink.count()) > 0) {
    await page.goto(`${baseURL}/memories`, { waitUntil: "domcontentloaded" });
    await page
      .locator('[data-testid="life-site-header"]')
      .waitFor({ timeout: 15_000 });
    await waitForSettledUi(page);
    await resetScroll(page);
    await momentLink.click();
    await page
      .locator('[data-testid="life-site-header"]')
      .waitFor({ timeout: 15_000 });
    await waitForSettledUi(page);
    await page.evaluate(() => {
      document
        .querySelectorAll(
          '.ReactQueryDevtools, .ReactQueryDevtoolsPanel, [aria-label="Open React Query Devtools"]',
        )
        .forEach((node) => node.remove());
    });
    const screenshot = path.join(
      outputDir,
      `moment-detail-${viewport.name}.png`,
    );
    await page.screenshot({
      path: screenshot,
      fullPage: false,
      animations: "disabled",
      caret: "hide",
      timeout: 20_000,
    });
    result.push({
      route: page.url(),
      viewport: viewport.name,
      screenshot,
      ...(await pageMetrics(
        page,
        { path: "/moments/:momentId", header: "life-site-header" },
        viewport,
      )),
    });
  }

  await page.goto(`${baseURL}/reminders`, { waitUntil: "domcontentloaded" });
  await page
    .locator('[data-testid="life-site-header"]')
    .waitFor({ timeout: 15_000 });
  await waitForSettledUi(page);
  const reminderLink = page.locator('a[href^="/reminders/"]').first();
  if ((await reminderLink.count()) > 0) {
    const href = await reminderLink.getAttribute("href");
    if (href) {
      await page.goto(`${baseURL}${href}`, { waitUntil: "domcontentloaded" });
      await page
        .locator('[data-testid="life-site-header"]')
        .waitFor({ timeout: 15_000 });
      await waitForSettledUi(page);
      await resetScroll(page);
      await page.evaluate(() => {
        document
          .querySelectorAll(
            '.ReactQueryDevtools, .ReactQueryDevtoolsPanel, [aria-label="Open React Query Devtools"]',
          )
          .forEach((node) => node.remove());
      });
      const screenshot = path.join(
        outputDir,
        `reminder-detail-${viewport.name}.png`,
      );
      await page.screenshot({
        path: screenshot,
        fullPage: false,
        animations: "disabled",
        caret: "hide",
        timeout: 20_000,
      });
      result.push({
        route: page.url(),
        viewport: viewport.name,
        screenshot,
        ...(await pageMetrics(
          page,
          { path: "/reminders/:reminderId", header: "life-site-header" },
          viewport,
        )),
      });
    }
  }

  await page.goto(`${baseURL}/memory-settings`, {
    waitUntil: "domcontentloaded",
  });
  await page
    .locator('[data-testid="life-site-header"]')
    .waitFor({ timeout: 15_000 });
  await waitForSettledUi(page);
  const knowledgeLink = page.locator('a[href^="/knowledge/"]').first();
  if ((await knowledgeLink.count()) > 0) {
    const href = await knowledgeLink.getAttribute("href");
    if (href) {
      await page.goto(`${baseURL}${href}`, { waitUntil: "domcontentloaded" });
      await page
        .locator('[data-testid="life-site-header"]')
        .waitFor({ timeout: 15_000 });
      await waitForSettledUi(page);
      await resetScroll(page);
      await page.evaluate(() => {
        document
          .querySelectorAll(
            '.ReactQueryDevtools, .ReactQueryDevtoolsPanel, [aria-label="Open React Query Devtools"]',
          )
          .forEach((node) => node.remove());
      });
      const screenshot = path.join(
        outputDir,
        `knowledge-detail-${viewport.name}.png`,
      );
      await page.screenshot({
        path: screenshot,
        fullPage: false,
        animations: "disabled",
        caret: "hide",
        timeout: 20_000,
      });
      result.push({
        route: page.url(),
        viewport: viewport.name,
        screenshot,
        ...(await pageMetrics(
          page,
          { path: "/knowledge/:knowledgeId", header: "life-site-header" },
          viewport,
        )),
      });
    }
  }
}

async function main() {
  fs.mkdirSync(outputDir, { recursive: true });
  const account = readAccount();
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

  const page = await context.newPage();
  const loginFailures = [];
  page.on("response", (response) => {
    if (
      response.url().endsWith("/api/auth/login") &&
      response.status() !== 200
    ) {
      loginFailures.push(response.status());
    }
  });

  await page.goto(`${baseURL}/login`, { waitUntil: "domcontentloaded" });
  await page.locator("#email").waitFor({ timeout: 15_000 });
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
    for (const route of routes) {
      await captureRoute(page, route, viewport, result);
    }
    await captureDetails(page, viewport, result);
  }

  const report = {
    generatedAt: new Date().toISOString(),
    baseURL,
    accountKey,
    loginStatus: loginFailures.length === 0 ? 200 : loginFailures.at(-1),
    testHarness: {
      reactQueryDevtoolsRemovedBeforeScreenshots: true,
      settledUiWaitMs: 3200,
    },
    viewports,
    results: result,
  };
  fs.writeFileSync(
    path.join(outputDir, "live-report.json"),
    `${JSON.stringify(report, null, 2)}\n`,
    "utf8",
  );

  console.log(
    JSON.stringify({
      outputDir,
      screenshots: result.filter((item) => item.screenshot).length,
      routes: result.filter((item) => item.header).length,
      headerFailures: result.filter(
        (item) =>
          item.header && (!item.headerVisible || item.totalLifeHeaders !== 1),
      ).length,
      overflowFailures: result.filter((item) => item.horizontalOverflow).length,
      errorBoundaries: result.filter((item) => item.errorBoundary).length,
      pageErrors: result.reduce(
        (sum, item) => sum + (item.pageErrors?.length || 0),
        0,
      ),
      brokenImages: result.reduce(
        (sum, item) => sum + (item.brokenImageCount || 0),
        0,
      ),
      lifeMutations: result.reduce(
        (sum, item) => sum + (item.lifeMutationRequests?.length || 0),
        0,
      ),
    }),
  );

  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
