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
      page.setDefaultTimeout(40000);
      await page.goto(fixture.origin + '/login');
      await page.locator('input[name="email"]').fill(account.email);
      await page.locator('input[name="password"]').fill(account.password);
      const login = page.waitForResponse((response) =>
        new URL(response.url()).pathname === '/api/auth/login' && response.status() === 200);
      await page.locator('button[type="submit"]').click();
      const auth = { Authorization: 'Bearer ' + (await (await login).json()).token };
      await page.waitForURL(/\/c\//);
      const detailUrl = fixture.origin + '/moments/' + fixture.moment_id;
      await page.goto(detailUrl);
      await page.getByText('文字回忆，图片服务待配置', { exact: false }).waitFor();
      await page.getByText(fixture.expected_caption, { exact: true }).waitFor();
      assert.equal(await page.locator('main img').count(), 0);
      await page.getByText('查看候选评分与选择依据', { exact: true }).click();
      assert.equal(await page.locator('main details ol > li').count(), 3);
      assert.equal(await page.getByText('本时段入选事件', { exact: false }).count(), 1);
      assert.equal(await page.locator('main details dt').count(), 24);
      const text = await page.locator('main').textContent();
      assert.ok(!text.includes('"memory_id"') && !text.includes('pending_provider'));
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      await page.screenshot({ path: path.join(evidence, `scored-${width}.png`), fullPage: true });
      await page.getByRole('link', { name: '查看记忆', exact: true }).first().click();
      await page.waitForURL(/\/knowledge\//);
      const sourceLink = page.locator('main a[href*="?message="]').first();
      await sourceLink.waitFor();
      const href = await sourceLink.getAttribute('href');
      assert.ok(href.startsWith('/c/') && href.includes('p04-scoring-'));
      await sourceLink.click();
      await page.waitForURL(/\/c\/.*\?message=/);
      const response = await context.request.get(fixture.origin + '/life-api/api/v1/moments/' + fixture.moment_id,
        { headers: auth });
      assert.equal(response.status(), 200);
      const chosenSource = (await response.json()).moment.selection.find((item) =>
        item.source_message_ids.some((id) => href.includes(encodeURIComponent(id))));
      assert.ok(chosenSource);
      // Confirm the actual persisted user message is rendered, without sending chat.
      await page.getByText(/今天终于完成了坚持一年的手写回忆录/, { exact: false }).first().waitFor();
      await page.goto(detailUrl);
      await page.getByText(fixture.expected_caption, { exact: true }).waitFor();
      if (width === 390) {
        const revoked = await context.request.patch(fixture.origin + '/life-api/api/v1/me/settings',
          { headers: auth, data: { image_consent: false } });
        assert.equal(revoked.status(), 200);
        await page.reload();
        await page.getByRole('status').filter({ hasText: '已撤回回忆内容' }).waitFor();
        assert.ok(!(await page.locator('main').textContent()).includes(fixture.expected_caption));
        assert.equal(await page.locator('main details').count(), 0);
        assert.equal(await page.locator('main img').count(), 0);
        await page.screenshot({ path: path.join(evidence, 'scoring-revoked-390.png'), fullPage: true });
      }
      result.scenarios.push({ width, candidates: 3, dimensions: 24, selected: 1,
        source_message_opened: true, image_elements: 0 });
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
    fs.writeFileSync(path.join(evidence, 'scoring-ui.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
  }
})().catch((error) => {
  console.error(error.name + ': ' + error.message);
  process.exitCode = 1;
});
