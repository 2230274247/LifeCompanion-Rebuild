const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
execFileSync('python', [path.join(__dirname, 'verify_rebuild_workspace.py')], { cwd: root });
const { chromium } = require(path.join(root, 'products/librechat-custom/node_modules/playwright'));
const evidence = path.resolve(process.env.LIFE_P04_EVIDENCE);
assert.ok(evidence.startsWith(path.join(root, 'evidence/p04') + path.sep));
const fixture = JSON.parse(fs.readFileSync(path.join(evidence, 'browser-fixture.json'), 'utf8'));
const account = JSON.parse(fs.readFileSync(path.join(root, 'infra/runtime/p00/accounts.json'), 'utf8')).a;
assert.equal(new URL(fixture.origin).hostname, '127.0.0.1');
assert.equal(new URL(fixture.origin).protocol, 'http:');

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  const result = { status: 'FAIL', scenarios: [], model_generation_requests: 0 };
  let activePage;
  try {
    for (const width of [1440, 390]) {
      const context = await browser.newContext({
        viewport: { width, height: width === 390 ? 844 : 1000 },
        hasTouch: width === 390, locale: 'zh-CN',
      });
      await context.route('**/api/ask/**', async (route) => {
        result.model_generation_requests++;
        await route.abort();
      });
      const page = await context.newPage();
      activePage = page;
      page.setDefaultTimeout(45000);
      await page.goto(fixture.origin + '/login');
      await page.locator('input[name="email"]').fill(account.email);
      await page.locator('input[name="password"]').fill(account.password);
      const login = page.waitForResponse((response) =>
        new URL(response.url()).pathname === '/api/auth/login' && response.status() === 200);
      await page.locator('button[type="submit"]').click();
      const auth = { Authorization: 'Bearer ' + (await (await login).json()).token };
      await page.waitForURL(/\/c\//);
      await page.goto(fixture.origin + '/moments/' + fixture.moment_id);
      await page.getByText('图像请求结果尚未确认', { exact: false }).waitFor();
      assert.equal(await page.getByRole('button', { name: /重试|Retry/i }).count(), 0);
      await page.getByText(fixture.expected_caption, { exact: true }).waitFor();
      assert.ok((await page.locator('main').textContent()).includes(fixture.expected_caption));
      assert.equal(await page.locator('main img').count(), 0);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      await page.screenshot({ path: path.join(evidence, `unknown-${width}.png`), fullPage: true });
      if (width === 390) {
        const revoked = await context.request.patch(fixture.origin + '/life-api/api/v1/me/settings', {
          headers: auth, data: { image_consent: false },
        });
        assert.equal(revoked.status(), 200);
        await page.reload();
        await page.getByRole('status').filter({ hasText: 'cancelled' }).waitFor();
        assert.ok(!(await page.locator('main').textContent()).includes(fixture.expected_caption));
        assert.equal(await page.locator('main img').count(), 0);
        await page.screenshot({ path: path.join(evidence, 'revoked-390.png'), fullPage: true });
      }
      result.scenarios.push({ width, unknown_retry_buttons: 0, image_elements: 0 });
      await context.close();
    }
    assert.equal(result.model_generation_requests, 0);
    result.status = 'PASS';
  } catch (error) {
    if (activePage && !activePage.isClosed()) {
      await activePage.screenshot({ path: path.join(evidence, 'failure.png'), fullPage: true });
    }
    throw error;
  } finally {
    await browser.close();
    fs.writeFileSync(path.join(evidence, 'privacy-ui.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
  }
})().catch((error) => {
  console.error(error.name + ': ' + error.message);
  process.exitCode = 1;
});
