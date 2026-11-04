const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
execFileSync('python', [path.join(__dirname, 'verify_rebuild_workspace.py')], { cwd: root });
const { chromium } = require(
  path.join(root, 'products/librechat-custom/node_modules/playwright'),
);
const runtime = path.join(root, 'infra/runtime/p00');
const scenario = process.argv[2] || 'p00';
const evidence = scenario === 'p00'
  ? path.join(root, 'evidence/p00/browser')
  : path.join(root, 'evidence/p01', scenario);
fs.mkdirSync(evidence, { recursive: true });

(async () => {
  const accounts = JSON.parse(fs.readFileSync(path.join(runtime, 'accounts.json'), 'utf8'));
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('http://127.0.0.1:3031/login', { waitUntil: 'domcontentloaded' });
  await page.locator('input[name="email"]').fill(accounts.a.email);
  await page.locator('input[name="password"]').fill(accounts.a.password);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL(/\/c\//, { timeout: 45000 });
  await page.locator('textarea').first().waitFor({ timeout: 30000 });
  const baselinePath = path.join(runtime, 'baseline-state.json');
  if (fs.existsSync(baselinePath)) {
    const baseline = JSON.parse(fs.readFileSync(baselinePath, 'utf8'));
    if (baseline.c) {
      await page.goto('http://127.0.0.1:3031/c/' + baseline.c.conversation_id, {
        waitUntil: 'domcontentloaded',
      });
      await page.getByText('雨伞', { exact: false }).first().waitFor({ timeout: 30000 });
    }
  }
  const report = { authenticated: true, viewports: [], routes: [], javascript_errors: errors };
  for (const width of [390, 430, 768, 1440, 1920]) {
    await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 });
    await page.waitForTimeout(300);
    await page.screenshot({ path: path.join(evidence, `chat-${width}.png`), fullPage: true });
    report.viewports.push({
      width,
      horizontal_overflow: await page.evaluate(() =>
        document.documentElement.scrollWidth > window.innerWidth + 1),
    });
  }
  if (scenario.startsWith('p01')) {
    await page.setViewportSize({ width: 1440, height: 1000 });
    const documentRequests = [];
    page.on('request', (request) => {
      if (request.isNavigationRequest() && request.frame() === page.mainFrame()) {
        documentRequests.push(new URL(request.url()).pathname);
      }
    });
    const link = page.locator('a[href^="/knowledge/"]').first();
    const href = await link.getAttribute('href');
    const target = await link.getAttribute('target');
    const popupPromise = page.waitForEvent('popup', { timeout: 2500 }).catch(() => null);
    await link.click();
    const popup = await popupPromise;
    const detailPage = popup || page;
    await detailPage.locator('article').waitFor({ timeout: 20000 });
    report.memory_link = {
      href, target, opened_popup: Boolean(popup),
      path: new URL(detailPage.url()).pathname,
      document_requests: documentRequests.slice(),
      article_contains_synthetic_fact: /雨伞|绿色.*盘/.test(
        await detailPage.locator('article').innerText()),
    };
    await detailPage.screenshot({ path: path.join(evidence, 'memory-detail.png'), fullPage: true });
    await detailPage.reload({ waitUntil: 'domcontentloaded' });
    await detailPage.locator('article').waitFor();
    report.memory_link.refresh = 'PASS';
    if (popup) {
      await popup.close();
    } else {
      await page.goBack();
      await page.getByText('雨伞', { exact: false }).first().waitFor();
      report.memory_link.back_to_conversation = new URL(page.url()).pathname.startsWith('/c/');
    }
  }
  for (const route of ['/memories', '/memory-settings', '/reminders', '/moments/settings']) {
    const response = await page.goto('http://127.0.0.1:3031' + route, {
      waitUntil: 'domcontentloaded',
    });
    await page.locator('body').waitFor();
    await page.screenshot({
      path: path.join(evidence, route.replaceAll('/', '_') + '.png'), fullPage: true,
    });
    report.routes.push({ route, http: response.status(), resulting_path: new URL(page.url()).pathname });
  }
  fs.writeFileSync(path.join(evidence, 'browser-baseline.json'), JSON.stringify(report, null, 2));
  await browser.close();
  console.log(JSON.stringify(report));
})().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
