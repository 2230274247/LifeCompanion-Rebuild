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

const baseURL = process.env.LIFE_UI_BASE_URL || "http://127.0.0.1:3091";
const accountFile = path.join(
  projectRoot,
  "infra",
  "runtime",
  "test-accounts.json",
);
const outputDir = path.resolve(
  __dirname,
  process.argv[2] || "before-backup-final",
);
const viewports = [
  { name: "390x844", width: 390, height: 844 },
  { name: "430x932", width: 430, height: 932 },
  { name: "768x1024", width: 768, height: 1024 },
  { name: "1440x1000", width: 1440, height: 1000 },
  { name: "1920x1080", width: 1920, height: 1080 },
];
const routes = [
  { name: "chat", path: "/c/new" },
  { name: "memories", path: "/memories" },
  { name: "reminders", path: "/reminders" },
  { name: "settings", path: "/memory-settings" },
  { name: "moment-settings", path: "/moments/settings" },
];

function readAccount() {
  const account = JSON.parse(fs.readFileSync(accountFile, "utf8")).librechat;
  if (!account?.email || !account?.password) {
    throw new Error("Missing browser account");
  }
  return account;
}

async function settle(page) {
  await page.waitForTimeout(2600);
  await page.evaluate(() => {
    document
      .querySelectorAll(
        '.ReactQueryDevtools, .ReactQueryDevtoolsPanel, [aria-label="Open React Query Devtools"]',
      )
      .forEach((node) => node.remove());
    for (const element of document.querySelectorAll("*")) {
      if (element instanceof HTMLElement && element.scrollTop) {
        element.scrollTop = 0;
      }
    }
    window.scrollTo(0, 0);
  });
  await page.waitForTimeout(250);
}

async function screenshot(page, name, viewport, result) {
  const filePath = path.join(outputDir, `${name}-${viewport.name}.png`);
  await page.screenshot({
    path: filePath,
    fullPage: false,
    animations: "disabled",
    caret: "hide",
    timeout: 20_000,
  });
  result.push({
    route: new URL(page.url()).pathname,
    viewport: viewport.name,
    screenshot: filePath,
  });
}

async function captureLinkedDetail(page, viewport, result, config) {
  await page.goto(`${baseURL}${config.source}`, {
    waitUntil: "domcontentloaded",
  });
  await settle(page);
  const link = page.locator(config.selector).first();
  if ((await link.count()) === 0) {
    return;
  }
  const href = await link.getAttribute("href");
  if (!href) {
    return;
  }
  await page.goto(`${baseURL}${href}`, { waitUntil: "domcontentloaded" });
  await settle(page);
  await screenshot(page, config.name, viewport, result);
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
  await page.goto(`${baseURL}/login`, { waitUntil: "domcontentloaded" });
  await page.locator("#email").fill(account.email);
  await page.locator("#password").fill(account.password);
  await page.locator('[data-testid="login-button"]').click();
  await page.waitForURL(/\/c\//, { timeout: 30_000 });
  await page.waitForTimeout(1800);

  const result = [];
  for (const viewport of viewports) {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    for (const route of routes) {
      await page.goto(`${baseURL}${route.path}`, {
        waitUntil: "domcontentloaded",
      });
      await settle(page);
      await screenshot(page, route.name, viewport, result);
    }
    await captureLinkedDetail(page, viewport, result, {
      source: "/memories",
      selector: 'a[href^="/memories/evt_"]',
      name: "memory-detail",
    });
    await captureLinkedDetail(page, viewport, result, {
      source: "/reminders",
      selector: 'a[href^="/reminders/"]',
      name: "reminder-detail",
    });
    await captureLinkedDetail(page, viewport, result, {
      source: "/memory-settings",
      selector: 'a[href^="/knowledge/"]',
      name: "knowledge-detail",
    });
  }

  fs.writeFileSync(
    path.join(outputDir, "before-report.json"),
    `${JSON.stringify({ generatedAt: new Date().toISOString(), baseURL, results: result }, null, 2)}\n`,
    "utf8",
  );
  console.log(
    JSON.stringify({
      outputDir,
      screenshots: result.length,
      expected: viewports.length * (routes.length + 3),
    }),
  );
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
