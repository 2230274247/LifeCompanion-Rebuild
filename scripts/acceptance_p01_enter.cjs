const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
execFileSync('python', [path.join(__dirname, 'verify_rebuild_workspace.py')], { cwd: root });
const { chromium } = require(
  path.join(root, 'products/librechat-custom/node_modules/playwright'),
);
const runtime = path.join(root, 'infra/runtime/p00');
const evidence = path.join(root, 'evidence/p01');
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

(async () => {
  const accounts = JSON.parse(fs.readFileSync(path.join(runtime, 'accounts.json'), 'utf8'));
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const report = { synthetic: true, real_provider: 'existing Zhipu glm-4.7', provider_calls: 1 };
  try {
    await page.goto('http://127.0.0.1:3031/login');
    await page.locator('input[name="email"]').fill(accounts.a.email);
    await page.locator('input[name="password"]').fill(accounts.a.password);
    await page.locator('button[type="submit"]').click();
    await page.waitForURL(/\/c\//, { timeout: 45000 });
    await page.goto('http://127.0.0.1:3031/c/new');
    const editor = page.locator('textarea').first();
    await editor.waitFor();
    await editor.fill('P01_SYNTHETIC_IME: Enter during composition must not submit.');
    await editor.dispatchEvent('compositionstart', { data: '中' });
    await editor.dispatchEvent('keydown', {
      key: 'Enter',
      keyCode: 229,
      which: 229,
      isComposing: true,
    });
    report.composition_enter_kept_text = (await editor.inputValue()).includes('P01_SYNTHETIC_IME');
    report.composition_did_not_submit =
      (await page.getByText('P01_SYNTHETIC_IME', { exact: false }).count()) === 0;
    await editor.dispatchEvent('compositionend', { data: '中' });

    const text = 'P01_SYNTHETIC_ENTER: 请只回复“已收到”。';
    await editor.fill(text);
    await editor.press('Enter');
    await page.getByText(text, { exact: true }).waitFor({ timeout: 15000 });
    await page.getByText('已收到', { exact: true }).last().waitFor({ timeout: 90000 });
    await page.waitForFunction(
      () => document.querySelector('textarea')?.value === '',
      { timeout: 10000 },
    );
    report.successful_enter_cleared_input = true;
    report.reply_visible = true;
    await page.waitForURL(/\/c\/[a-f0-9-]{36}$/i, { timeout: 15000 });
    const conversationId = new URL(page.url()).pathname.split('/').pop();
    if (conversationId === 'new') throw new Error('CHAT_DID_NOT_OPEN_SAVED_CONVERSATION');
    report.conversation_id = conversationId;
    await page.reload();
    await page.getByText(text, { exact: true }).waitFor({ timeout: 30000 });
    await page.getByText('已收到', { exact: true }).last().waitFor({ timeout: 30000 });
    report.refresh_restored_real_messages = true;
    await page.screenshot({ path: path.join(evidence, 'enter-real-chat.png'), fullPage: true });
  } finally {
    fs.writeFileSync(
      path.join(evidence, 'enter-real-chat.json'),
      JSON.stringify(report, null, 2),
    );
    await browser.close();
  }
  console.log(JSON.stringify(report));
})().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
