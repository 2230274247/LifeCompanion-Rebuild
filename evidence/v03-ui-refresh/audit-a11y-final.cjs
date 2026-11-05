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
const AxeBuilder = require(
  path.join(librechatRoot, "node_modules", "@axe-core", "playwright"),
).default;

const evidenceRoot = __dirname;
const tags = ["wcag2a", "wcag2aa", "wcag21aa", "best-practice"];
const viewports = [
  { name: "390x844", width: 390, height: 844 },
  { name: "1440x1000", width: 1440, height: 1000 },
];

function readAccount(relativePath, key) {
  const accounts = JSON.parse(
    fs.readFileSync(path.join(projectRoot, relativePath), "utf8"),
  );
  const account = accounts[key];
  if (!account?.email || !account?.password) {
    throw new Error(`Missing browser account "${key}"`);
  }
  return account;
}

async function login(page, baseURL, account) {
  await page.goto(`${baseURL}/login`, { waitUntil: "domcontentloaded" });
  await page.locator("#email").fill(account.email);
  await page.locator("#password").fill(account.password);
  await page.locator('[data-testid="login-button"]').click();
  await page.waitForURL(/\/c\//, { timeout: 30_000 });
  await page
    .locator('[data-testid="life-chat-header"]')
    .waitFor({ timeout: 15_000 });
}

async function settle(page, selector) {
  await page.locator(selector).waitFor({ timeout: 20_000 });
  await page.waitForTimeout(2200);
  await page
    .waitForFunction(() => !document.body.innerText.includes("正在翻开回忆"), {
      timeout: 12_000,
    })
    .catch(() => undefined);
  await page.evaluate(() => {
    document
      .querySelectorAll(
        '.ReactQueryDevtools, .ReactQueryDevtoolsPanel, [aria-label="Open React Query Devtools"]',
      )
      .forEach((node) => node.remove());
  });
  await page.waitForTimeout(300);
}

async function scan(page, route, viewport, output) {
  const results = await new AxeBuilder({ page }).withTags(tags).analyze();
  output.push({
    route,
    viewport: viewport.name,
    violationCount: results.violations.length,
    violations: results.violations.map((item) => ({
      id: item.id,
      impact: item.impact,
      nodes: item.nodes.length,
      targets: item.nodes.map((node) => node.target),
      summaries: item.nodes.map((node) => node.failureSummary),
    })),
  });
}

async function scanLinkedDetail(
  page,
  baseURL,
  sourcePath,
  linkSelector,
  routeName,
  viewport,
  output,
) {
  await page.goto(`${baseURL}${sourcePath}`, { waitUntil: "domcontentloaded" });
  await settle(page, '[data-testid="life-site-header"]');
  const link = page.locator(linkSelector).first();
  if ((await link.count()) === 0) {
    return;
  }
  const href = await link.getAttribute("href");
  if (!href) {
    return;
  }
  await page.goto(`${baseURL}${href}`, { waitUntil: "domcontentloaded" });
  await settle(page, '[data-testid="life-site-header"]');
  await scan(page, routeName, viewport, output);
}

async function runLive(browser) {
  const baseURL = "http://127.0.0.1:3001";
  const account = readAccount("infra/runtime/test-accounts.json", "librechat");
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
  await login(page, baseURL, account);

  const routes = [
    ["/c/new", '[data-testid="life-chat-header"]'],
    ["/memories", '[data-testid="life-site-header"]'],
    ["/reminders", '[data-testid="life-site-header"]'],
    ["/memory-settings", '[data-testid="life-site-header"]'],
    ["/moments/settings", '[data-testid="life-site-header"]'],
  ];
  const results = [];
  for (const viewport of viewports) {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    for (const [route, selector] of routes) {
      await page.goto(`${baseURL}${route}`, { waitUntil: "domcontentloaded" });
      await settle(page, selector);
      await scan(page, route, viewport, results);
    }
    await scanLinkedDetail(
      page,
      baseURL,
      "/memories",
      'a[href^="/memories/evt_"]',
      "/memories/:eventId",
      viewport,
      results,
    );
    await scanLinkedDetail(
      page,
      baseURL,
      "/reminders",
      'a[href^="/reminders/"]',
      "/reminders/:reminderId",
      viewport,
      results,
    );
    await scanLinkedDetail(
      page,
      baseURL,
      "/memory-settings",
      'a[href^="/knowledge/"]',
      "/knowledge/:knowledgeId",
      viewport,
      results,
    );
  }

  fs.writeFileSync(
    path.join(evidenceRoot, "accessibility-ui-report-final.json"),
    JSON.stringify(
      {
        generatedAt: new Date().toISOString(),
        baseURL,
        standard: tags,
        scope:
          "Five Life routes at 390 and 1440 after the final inert and decorative-alt fixes.",
        results,
      },
      null,
      2,
    ),
  );
  await context.close();
  return results;
}

async function installFixtureBridge(context, target, token) {
  await context.route("**/life-api/**", async (route) => {
    const request = route.request();
    const incoming = new URL(request.url());
    const targetUrl = new URL(
      `${incoming.pathname.slice("/life-api".length)}${incoming.search}`,
      target,
    );
    const headers = { ...request.headers(), authorization: `Bearer ${token}` };
    delete headers.cookie;
    delete headers.host;
    try {
      const response = await route.fetch({
        url: targetUrl.toString(),
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

async function runFixture(browser) {
  const baseURL = "http://127.0.0.1:3090";
  const target = "http://127.0.0.1:8036";
  const tokenFile = path.join(
    process.env.TEMP || ".",
    "life-ui-image-fixture-8036",
    "token.txt",
  );
  const token = fs.readFileSync(tokenFile, "utf8").trim();
  const account = readAccount("infra/runtime/test-accounts.json", "librechat");
  const context = await browser.newContext({
    baseURL,
    locale: "zh-CN",
    viewport: viewports[0],
  });
  await context.addInitScript(() => {
    localStorage.setItem("navVisible", "true");
    localStorage.setItem("lang", JSON.stringify("zh-Hans"));
  });
  await installFixtureBridge(context, target, token);
  const page = await context.newPage();
  await login(page, baseURL, account);

  const results = [];
  for (const viewport of viewports) {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    await page.goto(`${baseURL}/memories`, { waitUntil: "domcontentloaded" });
    await settle(page, '[data-testid="life-site-header"]');
    await page
      .locator('[data-testid="moment-card"]')
      .first()
      .waitFor({ timeout: 20_000 });
    await scan(page, "/memories", viewport, results);

    await page.locator('[data-testid="moment-card"]').first().focus();
    await page.keyboard.press("Enter");
    await page.waitForURL(/\/moments\/mom_/, { timeout: 15_000 });
    await settle(page, '[data-testid="life-site-header"]');
    await page.waitForFunction(
      () => {
        const image = document.querySelector(
          'button[aria-haspopup="dialog"] img',
        );
        return image?.complete && image.naturalWidth > 0;
      },
      { timeout: 20_000 },
    );
    await scan(page, "/moments/:id", viewport, results);
  }

  fs.writeFileSync(
    path.join(evidenceRoot, "accessibility-image-fixture-report-final.json"),
    JSON.stringify(
      {
        generatedAt: new Date().toISOString(),
        standard: tags,
        scope:
          "Image fixture memories and detail at 390 and 1440 after the final inert and decorative-alt fixes.",
        results,
      },
      null,
      2,
    ),
  );
  await context.close();
  return results;
}

async function main() {
  const browser = await chromium.launch({
    headless: true,
    channel: process.env.LIFE_UI_CHROMIUM_CHANNEL || "chrome",
  });
  try {
    const live = await runLive(browser);
    const fixture = await runFixture(browser);
    const all = [...live, ...fixture];
    const violations = all.reduce((sum, item) => sum + item.violationCount, 0);
    console.log(
      JSON.stringify(
        {
          scans: all.length,
          violations,
          failed: all
            .filter((item) => item.violationCount > 0)
            .map(({ route, viewport, violationCount }) => ({
              route,
              viewport,
              violationCount,
            })),
        },
        null,
        2,
      ),
    );
    if (violations > 0) {
      process.exitCode = 1;
    }
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
