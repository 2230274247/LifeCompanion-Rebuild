import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';

const phase = process.argv[2] === 'after' ? 'after' : 'before';
const baseUrl = process.env.LIFE_UI_BASE_URL || 'http://127.0.0.1:3090';
const accountFile = process.env.LIFE_UI_ACCOUNT_FILE;
const outputDir = path.resolve(process.argv[3] || `evidence/v03-ui-refresh/${phase}`);
const root = process.cwd();
const require = createRequire(path.join(root, 'products/librechat-custom/package.json'));
const { chromium } = require('@playwright/test');

assert(accountFile, 'LIFE_UI_ACCOUNT_FILE is required');

const accounts = JSON.parse(await readFile(accountFile, 'utf8'));
const accountKey = process.env.LIFE_UI_ACCOUNT_KEY || 'c';
const account =
  accounts[accountKey] ?? accounts.a ?? accounts.owner ?? Object.values(accounts)[0];
assert(account?.email && account?.password, 'A synthetic account with email/password is required');

const viewports = [
  { width: 390, height: 844 },
  { width: 430, height: 932 },
  { width: 768, height: 1024 },
  { width: 1440, height: 1000 },
  { width: 1920, height: 1080 },
];
const pages = [
  { id: 'chat', route: '/c/new' },
  { id: 'memories', route: '/memories' },
  { id: 'reminders', route: '/reminders' },
  { id: 'settings', route: '/memory-settings' },
];

const report = {
  phase,
  base_url: baseUrl,
  account_kind: 'existing isolated synthetic account',
  credentials_printed: false,
  status: 'FAIL',
  checks: {},
  pages: [],
  console_errors: [],
  page_errors: [],
  network_errors: [],
};

const browser = await chromium.launch({
  headless: true,
  executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  colorScheme: 'light',
  serviceWorkers: 'block',
  reducedMotion: 'reduce',
});
const page = await context.newPage();

page.on('console', (message) => {
  if (message.type() === 'error') {
    report.console_errors.push(message.text());
  }
});
page.on('pageerror', (error) => report.page_errors.push(error.message));
page.on('response', (response) => {
  const url = new URL(response.url());
  if (url.origin === baseUrl && response.status() >= 400 && !url.pathname.includes('/api/config')) {
    report.network_errors.push(`${response.request().method()} ${url.pathname}: HTTP ${response.status()}`);
  }
});

try {
  await page.goto(`${baseUrl}/login`, { waitUntil: 'domcontentloaded', timeout: 120000 });
  await page.locator('form[aria-label="Login form"]').waitFor({ timeout: 30000 });
  await page.locator('#email').fill(account.email);
  await page.locator('#password').fill(account.password);
  await Promise.all([
    page.waitForURL(/\/c\/new/, { timeout: 30000 }),
    page.locator('[data-testid="login-button"]').click(),
  ]);
  report.checks.login = 'PASS';

  for (const target of pages) {
    const pageReport = { id: target.id, route: target.route, viewports: [] };
    for (const viewport of viewports) {
      await page.setViewportSize(viewport);
      await page.goto(`${baseUrl}${target.route}`, {
        waitUntil: 'domcontentloaded',
        timeout: 120000,
      });
      await page.locator('body').waitFor({ timeout: 30000 });
      await page.waitForTimeout(1200);
      const metrics = await page.evaluate(() => {
        const body = document.body;
        return {
          title: document.title,
          bodyScrollWidth: body.scrollWidth,
          bodyClientWidth: body.clientWidth,
          headerCount: document.querySelectorAll('header').length,
          visibleHeaders: [...document.querySelectorAll('header')].filter((element) => {
            const style = getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
          }).length,
          overflowX: body.scrollWidth > body.clientWidth + 1,
        };
      });
      const name = `${target.id}-${viewport.width}x${viewport.height}.png`;
      await page.screenshot({ path: path.join(outputDir, name), fullPage: true });
      pageReport.viewports.push({ ...viewport, screenshot: name, ...metrics });
    }
    report.pages.push(pageReport);
  }

  report.checks.pages_loaded = report.pages.every((item) => item.viewports.length === viewports.length)
    ? 'PASS'
    : 'FAIL';
  report.checks.no_horizontal_overflow = report.pages.every((item) =>
    item.viewports.every((viewport) => !viewport.overflowX),
  )
    ? 'PASS'
    : 'FAIL';
  report.checks.no_browser_errors =
    report.page_errors.length === 0 && report.console_errors.length === 0 ? 'PASS' : 'FAIL';
  report.status =
    Object.values(report.checks).every((value) => value === 'PASS') ? 'PASS' : 'FAIL';
} catch (error) {
  report.error = error.stack || error.message;
  await page.screenshot({ path: path.join(outputDir, 'failure.png'), fullPage: true }).catch(() => null);
  throw error;
} finally {
  await context.close();
  await browser.close();
  await writeFile(
    path.join(outputDir, `${phase}-report.json`),
    JSON.stringify(report, null, 2),
    'utf8',
  );
  console.log(JSON.stringify({ status: report.status, checks: report.checks }, null, 2));
}
