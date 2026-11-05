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
const accountFile =
  process.env.LIFE_UI_ACCOUNT_FILE ||
  path.join(projectRoot, "infra", "runtime", "test-accounts.json");
const accountKey = process.env.LIFE_UI_ACCOUNT_KEY || "librechat";
const outputDir = path.resolve(__dirname, process.argv[2] || "after");

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

async function pageMetrics(page, route, viewport) {
  const metrics = await page.evaluate(() => {
    const bodyText = document.body?.innerText || "";
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
      sendButtons: document.querySelectorAll('[data-testid="send-button"]')
        .length,
      textareas: document.querySelectorAll("textarea").length,
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
      siteNavigationLinks: document.querySelectorAll(
        '[data-testid="life-site-header"] nav a',
      ).length,
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
    siteNavigationLinks: metrics.siteNavigationLinks,
    horizontalOverflow:
      metrics.scrollWidth > metrics.clientWidth + 1 ||
      metrics.bodyScrollWidth > metrics.clientWidth + 1,
    width: metrics.clientWidth,
    scrollWidth: Math.max(metrics.scrollWidth, metrics.bodyScrollWidth),
    sendButtons: metrics.sendButtons,
    textareas: metrics.textareas,
    errorBoundary:
      boundaryMarkers.find((marker) => metrics.bodyText.includes(marker)) ||
      null,
    title: metrics.title,
  };
}

async function captureRoute(page, route, viewport, result) {
  console.log(`capture ${route.name} ${viewport.name}`);
  const consoleErrors = [];
  const pageErrors = [];
  const failedResponses = [];

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

  page.on("console", onConsole);
  page.on("pageerror", onPageError);
  page.on("response", onResponse);

  try {
    await page.goto(`${baseURL}${route.path}`, {
      waitUntil: "domcontentloaded",
      timeout: 30_000,
    });
    await page
      .locator(`[data-testid="${route.header}"]`)
      .waitFor({ state: "visible", timeout: 15_000 })
      .catch(() => undefined);
    await page.evaluate(() => {
      document
        .querySelectorAll(".ReactQueryDevtools")
        .forEach((node) => node.remove());
    });
    await page.waitForTimeout(900);

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
    const metrics = await pageMetrics(page, route, viewport);
    result.push({
      ...metrics,
      screenshot,
      screenshotError,
      consoleErrors,
      pageErrors,
      failedResponses,
    });
  } finally {
    page.off("console", onConsole);
    page.off("pageerror", onPageError);
    page.off("response", onResponse);
  }
}

async function captureMobileDrawer(page, result) {
  console.log("capture mobile drawer");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${baseURL}/c/new`, { waitUntil: "domcontentloaded" });
  await page
    .locator('[data-testid="life-chat-header"]')
    .waitFor({ timeout: 15_000 });
  await page.locator('[data-testid="header-open-sidebar-button"]').click();
  await page
    .locator('[data-testid="life-navigation"]')
    .waitFor({ state: "visible" });
  await page.evaluate(() => {
    document
      .querySelectorAll(".ReactQueryDevtools")
      .forEach((node) => node.remove());
  });
  await page.waitForTimeout(500);

  const screenshot = path.join(outputDir, "chat-mobile-drawer-390x844.png");
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
  const drawerNavigation = await page
    .locator('[data-testid="life-navigation"] a')
    .evaluateAll((links) =>
      links.map((link) => ({
        label: link.getAttribute("aria-label"),
        current: link.getAttribute("aria-current"),
        href: link.getAttribute("href"),
      })),
    );
  result.push({ screenshot, screenshotError, drawerNavigation });
}

async function captureDetail(page, routeName, linkSelector, viewport, result) {
  const link = page.locator(linkSelector).first();
  if ((await link.count()) === 0) {
    return;
  }
  await link.click();
  await page
    .locator('[data-testid="life-site-header"]')
    .waitFor({ timeout: 15_000 });
  await page.waitForTimeout(1500);
  const screenshot = path.join(
    outputDir,
    `${routeName}-detail-${viewport.name}.png`,
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
    route: page.url(),
    viewport: viewport.name,
    screenshot,
    screenshotError,
    headerVisible: await page
      .locator('[data-testid="life-site-header"]')
      .isVisible(),
  });
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
  let detailCaptured = false;
  for (const viewport of viewports) {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    for (const route of routes) {
      await captureRoute(page, route, viewport, result);
      if (
        !detailCaptured &&
        viewport.name === "1440x1000" &&
        route.name === "memories"
      ) {
        await captureDetail(
          page,
          "memories",
          '[data-testid="moment-card"]',
          viewport,
          result,
        );
        detailCaptured = true;
      }
    }
  }

  await captureMobileDrawer(page, result);
  const report = {
    generatedAt: new Date().toISOString(),
    baseURL,
    accountKey,
    loginStatus: loginFailures.length === 0 ? 200 : loginFailures.at(-1),
    testHarness: {
      reactQueryDevtoolsRemovedBeforeScreenshots: true,
    },
    viewports,
    results: result,
  };
  fs.writeFileSync(
    path.join(outputDir, "after-report.json"),
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
    }),
  );

  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
