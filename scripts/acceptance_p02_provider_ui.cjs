const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
execFileSync('python', [path.join(__dirname, 'verify_rebuild_workspace.py')], { cwd: root });
const { chromium } = require(
  path.join(root, 'products/librechat-custom/node_modules/playwright'),
);

(async () => {
  const runtime = path.join(root, 'infra/runtime/p00');
  const evidence = path.join(root, 'evidence/p02');
  const accounts = JSON.parse(fs.readFileSync(path.join(runtime, 'accounts.json'), 'utf8'));
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const report = { status: 'FAIL', provider_calls: 0, scope: 'live provider configuration, no chat submitted' };
  let blockedRequests = 0;
  await page.route('**/api/ask/**', async (route) => {
    blockedRequests++;
    await route.abort();
  });
  try {
    await page.goto('http://127.0.0.1:3031/login');
    await page.locator('input[name="email"]').fill(accounts.a.email);
    await page.locator('input[name="password"]').fill(accounts.a.password);
    const endpointResponse = page.waitForResponse(
      (response) => new URL(response.url()).pathname === '/api/endpoints' && response.status() === 200,
      { timeout: 45000 },
    );
    const modelsResponsePromise = page.waitForResponse(
      (response) => new URL(response.url()).pathname === '/api/models' && response.status() === 200,
      { timeout: 45000 },
    );
    await page.locator('button[type="submit"]').click();
    await page.waitForURL(/\/c\//, { timeout: 45000 });
    const endpoints = await (await endpointResponse).json();
    const modelsResponse = { status: 200, body: await (await modelsResponsePromise).json() };
    await page.goto('http://127.0.0.1:3031/c/new');
    await page.locator('textarea').first().waitFor();
    const candidates = Array.isArray(endpoints)
      ? endpoints
      : Array.isArray(endpoints.endpoints)
        ? endpoints.endpoints
        : Object.entries(endpoints).map(([name, value]) => ({ name, ...value }));
    const deepseek = candidates.find((item) => item.name === 'DeepSeek');
    report.provider_shape = candidates.map((item) => {
      const safe = {};
      for (const key of ['name', 'type', 'models', 'modelDisplayLabel', 'titleConvo']) {
        if (item[key] !== undefined) safe[key] = item[key];
      }
      return safe;
    });
    assert.ok(deepseek, 'DeepSeek endpoint must exist');
    assert.equal(modelsResponse.status, 200);
    assert.ok(
      JSON.stringify(modelsResponse.body).includes('deepseek-flash'),
      'DeepSeek model must be advertised',
    );
    assert.equal(await page.locator('textarea').first().inputValue(), '');
    assert.equal(blockedRequests, 0);
    report.status = 'PASS';
    report.endpoint = 'DeepSeek';
    report.model = 'deepseek-flash';
    report.models_http_status = modelsResponse.status;
    report.available_fields = Object.keys(deepseek).sort();
    report.config_verified_by = 'YAML + live /api/endpoints advertisement';
    report.blocked_generation_attempts = blockedRequests;
    await page.screenshot({ path: path.join(evidence, 'deepseek-provider-live-ui.png'), fullPage: true });
  } finally {
    fs.writeFileSync(path.join(evidence, 'deepseek-provider-live-ui.json'), JSON.stringify(report, null, 2));
    await browser.close();
  }
  console.log(JSON.stringify(report));
})().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
