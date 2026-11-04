const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
execFileSync('python', [path.join(__dirname, 'verify_rebuild_workspace.py')], { cwd: root });
const { chromium } = require(path.join(root, 'products/librechat-custom/node_modules/playwright'));
const evidence = path.resolve(process.env.LIFE_P05_EVIDENCE);
assert.ok(evidence.startsWith(path.join(root, 'evidence/p05') + path.sep));
const fixture = JSON.parse(fs.readFileSync(path.join(evidence, 'browser-fixture.json'), 'utf8'));
const account = JSON.parse(fs.readFileSync(path.join(root, 'infra/runtime/p00/accounts.json'), 'utf8')).a;
const mode = process.env.LIFE_P05_UI_MODE;
assert.ok(['before', 'after'].includes(mode));
assert.equal(new URL(fixture.origin).hostname, '127.0.0.1');

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  const result = { status: 'FAIL', scenarios: [], model_generation_requests: 0 };
  let page;
  try {
    for (const width of [1440, 390]) {
      const context = await browser.newContext({ viewport: { width, height: width === 390 ? 844 : 1000 },
        hasTouch: width === 390, locale: 'zh-CN' });
      await context.route('**/api/ask/**', async (route) => {
        result.model_generation_requests++;
        await route.abort();
      });
      page = await context.newPage();
      page.setDefaultTimeout(40000);
      await page.goto(fixture.origin + '/login');
      await page.locator('input[name="email"]').fill(account.email);
      await page.locator('input[name="password"]').fill(account.password);
      await page.locator('button[type="submit"]').click();
      await page.waitForURL(/\/c\//);
      await page.goto(fixture.origin + '/c/' + fixture.conversation_id);
      await page.getByText(fixture.text, { exact: true }).first().waitFor();
      if (mode === 'before') {
        await page.getByText('Synthetic acceptance source; no model generation.', { exact: true }).waitFor();
        assert.equal(await page.getByTestId('weather-tool-card').count(), 0);
      } else {
        const card = page.getByTestId('weather-tool-card');
        await card.waitFor();
        if (width === 1440 && !fixture.already_succeeded) {
          await card.getByText('有同名地点，请选择要查询的一处。', { exact: true }).waitFor();
          await page.screenshot({ path: path.join(evidence, 'place-choice-1440.png'), fullPage: true });
          const label = [fixture.place.name, fixture.place.admin1, fixture.place.country].filter(Boolean).join(' · ');
          await card.getByRole('button', { name: label, exact: true }).click();
        }
        await card.getByText(/以上为天气模型估算/).waitFor();
        await card.getByText(/气温:/).waitFor();
        await card.getByRole('link', { name: 'Open-Meteo forecast' }).waitFor();
        const text = await card.textContent();
        assert.ok(text.includes(fixture.place.country));
        assert.ok(text.includes('查询时间'));
        assert.ok(!text.includes('tool_') && !text.includes('TOOL_') && !text.includes('latitude'));
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
        await page.screenshot({ path: path.join(evidence, `weather-${width}.png`), fullPage: true });
        await page.reload();
        await page.getByTestId('weather-tool-card').getByText(/以上为天气模型估算/).waitFor();
        if (width === 390) {
          await page.getByRole('button', { name: '关闭并清除本次查询', exact: true }).click();
          await page.getByTestId('weather-tool-card').waitFor({ state: 'detached' });
          await page.reload();
          await page.getByText(fixture.text, { exact: true }).first().waitFor();
          assert.equal(await page.getByTestId('weather-tool-card').count(), 0);
          await page.screenshot({ path: path.join(evidence, 'cleared-390.png'), fullPage: true });
        }
      }
      if (mode === 'before') {
        await page.screenshot({ path: path.join(evidence, `before-${width}.png`), fullPage: true });
      }
      result.scenarios.push({ width, mode, source_rendered: true });
      await context.close();
    }
    assert.equal(result.model_generation_requests, 0);
    result.status = 'PASS';
  } catch (error) {
    if (page && !page.isClosed()) {
      await page.screenshot({ path: path.join(evidence, `failure-${mode}.png`), fullPage: true });
    }
    throw error;
  } finally {
    await browser.close();
    fs.writeFileSync(path.join(evidence, `ui-${mode}.json`), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
  }
})().catch((error) => { console.error(error.name + ': ' + error.message); process.exitCode = 1; });
