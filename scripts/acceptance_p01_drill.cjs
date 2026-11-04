const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
execFileSync('python', [path.join(__dirname, 'verify_rebuild_workspace.py')], { cwd: root });
const { chromium } = require(
  path.join(root, 'products/librechat-custom/node_modules/playwright'),
);
const runtime = path.join(root, 'infra/runtime/p00');
const evidence = path.join(root, 'evidence/p01/drill');
const ownContainer = 'lcr-acceptance-20261103-librechat-1';
fs.mkdirSync(evidence, { recursive: true });
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function ready() {
  for (let attempt = 0; attempt < 60; attempt++) {
    try {
      if ((await fetch('http://127.0.0.1:3091/health', {
        signal: AbortSignal.timeout(1500),
      })).ok) return;
    } catch {}
    await delay(500);
  }
  throw new Error('ISOLATED_CONTAINER_NOT_READY');
}

(async () => {
  const accounts = JSON.parse(fs.readFileSync(path.join(runtime, 'accounts.json'), 'utf8'));
  const baseline = JSON.parse(fs.readFileSync(path.join(runtime, 'baseline-state.json'), 'utf8'));
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const report = { synthetic: true, provider_calls: 0 };
  let stopped = false;
  try {
    await ready();
    await page.goto('http://127.0.0.1:3031/login');
    await page.locator('input[name="email"]').fill(accounts.a.email);
    await page.locator('input[name="password"]').fill(accounts.a.password);
    await page.locator('button[type="submit"]').click();
    await page.waitForURL(/\/c\//);
    await page.goto('http://127.0.0.1:3031/c/' + baseline.d.conversation_id);
    const reminderLink = page.locator('a[href^="/reminders/rem_"]').first();
    const timeChoice = page.getByRole('button', { name: '09:00', exact: true });
    await page.locator('textarea').first().waitFor();
    await Promise.race([
      timeChoice.waitFor({ timeout: 15000 }),
      reminderLink.waitFor({ timeout: 15000 }),
    ]);
    if (await timeChoice.isVisible()) {
      await timeChoice.click();
    }
    await reminderLink.waitFor({ timeout: 25000 });
    report.reminder_href = await reminderLink.getAttribute('href');
    report.no_full_form = (await page.locator('input[type="date"]').count()) === 0;
    await page.screenshot({ path: path.join(evidence, 'reminder-created.png'), fullPage: true });
    await reminderLink.click();
    await page.locator('h2').filter({ hasText: '绿色' }).waitFor();
    report.correct_reminder_detail = new URL(page.url()).pathname === report.reminder_href;
    await page.reload();
    await page.locator('h2').filter({ hasText: '绿色' }).waitFor();
    report.reminder_refresh = true;
    const source = page.locator(`a[href^="/c/${baseline.d.conversation_id}?message="]`);
    report.reminder_source_href = await source.getAttribute('href');
    await page.screenshot({ path: path.join(evidence, 'reminder-detail.png'), fullPage: true });
    await source.click();
    await page.locator('textarea').first().waitFor();
    report.source_return = new URL(page.url()).pathname === '/c/' + baseline.d.conversation_id;

    await page.goto('http://127.0.0.1:3031/c/new');
    const editor = page.locator('textarea').first();
    await editor.waitFor();
    const text = 'P01_SYNTHETIC_RECOVERY: 请保留这条输入，服务暂时不可用。';
    await editor.fill(text);
    // Stop only this run's isolated application to exercise a real gateway failure.
    execFileSync('docker', ['stop', '-t', '2', ownContainer], { stdio: 'pipe' });
    stopped = true;
    await editor.press('Enter');
    await delay(1800);
    report.outage = {
      container: ownContainer,
      editor_retained: await editor.inputValue() === text,
      message_visible: (await page.getByText(text, { exact: true }).count()) > 0,
      friendly_error_visible: /The chat service is temporarily unavailable|聊天服务暂时不可用/.test(
        await page.locator('body').innerText(),
      ),
      internal_error_code_hidden: !(await page.getByText('UPSTREAM_UNAVAILABLE', {
        exact: false,
      }).count()),
      business_success_fabricated: /已创建提醒|已经设置好了/.test(await page.locator('body').innerText()),
    };
    await page.screenshot({ path: path.join(evidence, 'real-upstream-outage.png'), fullPage: true });
    execFileSync('docker', ['start', ownContainer], { stdio: 'pipe' });
    stopped = false;
    await ready();
    await page.reload();
    await page.locator('textarea').first().waitFor();
    report.outage.retained_after_reload = await page.locator('textarea').first().inputValue() === text ||
      (await page.getByText(text, { exact: true }).count()) > 0;
    await page.screenshot({ path: path.join(evidence, 'outage-recovery-reload.png'), fullPage: true });
  } finally {
    if (stopped) execFileSync('docker', ['start', ownContainer], { stdio: 'pipe' });
    fs.writeFileSync(path.join(evidence, 'ui-drill.json'), JSON.stringify(report, null, 2));
    await browser.close();
  }
  console.log(JSON.stringify(report));
})().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
