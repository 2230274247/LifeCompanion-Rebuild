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

(async () => {
  const accounts = JSON.parse(fs.readFileSync(path.join(runtime, 'accounts.json'), 'utf8'));
  const sent = JSON.parse(
    fs.readFileSync(path.join(evidence, 'enter-real-chat.json'), 'utf8'),
  );
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const report = { synthetic: true, provider_calls: 0, source: 'existing real Zhipu chat' };
  try {
    await page.goto('http://127.0.0.1:3031/login');
    await page.locator('input[name="email"]').fill(accounts.a.email);
    await page.locator('input[name="password"]').fill(accounts.a.password);
    await page.locator('button[type="submit"]').click();
    await page.waitForURL(/\/c\//, { timeout: 45000 });

    const conversationId = sent.conversation_id;
    const text = 'P01_SYNTHETIC_ENTER: 请只回复“已收到”。';
    await page.goto(`http://127.0.0.1:3031/c/${conversationId}`);
    await page.getByText(text, { exact: true }).waitFor({ timeout: 30000 });
    await page.getByText('已收到', { exact: true }).last().waitFor({ timeout: 30000 });
    report.saved_conversation_id = conversationId;
    report.user_message_restored = true;
    report.real_assistant_reply_restored = true;
    report.reply_is_not_user_prompt_match =
      (await page.locator('.message-content').filter({ hasText: /^已收到$/ }).count()) > 0;
    report.composer_empty = (await page.locator('textarea').first().inputValue()) === '';
    await page.screenshot({ path: path.join(evidence, 'enter-real-chat-persisted.png'), fullPage: true });
  } finally {
    fs.writeFileSync(
      path.join(evidence, 'enter-real-chat-persisted.json'),
      JSON.stringify(report, null, 2),
    );
    await browser.close();
  }
  console.log(JSON.stringify(report));
})().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
