const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
execFileSync('python', [path.join(__dirname, 'verify_rebuild_workspace.py')], { cwd: root });
const { chromium } = require(path.join(root, 'products/librechat-custom/node_modules/playwright'));
const evidence = path.resolve(process.env.LIFE_ACCEPTANCE_UI_EVIDENCE || path.join(root, 'evidence/p03'));
assert.ok(evidence === path.join(root, 'evidence/p03') ||
  evidence.startsWith(path.join(root, 'evidence/p03') + path.sep));
fs.mkdirSync(evidence, { recursive: true });
const accounts = JSON.parse(fs.readFileSync(path.join(root, 'infra/runtime/p00/accounts.json'), 'utf8'));
const python = path.join(root, 'infra/runtime/p02/venv/Scripts/python.exe');
const origin = process.env.LIFE_ACCEPTANCE_ORIGIN || 'http://127.0.0.1:3031';
assert.equal(new URL(origin).hostname, '127.0.0.1');
assert.equal(new URL(origin).protocol, 'http:');

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  const report = {
    status: 'FAIL', started_at: new Date().toISOString(), provider_calls: 0,
    scope: 'real browser on persisted synthetic source; generation endpoint blocked; no chat submission',
    scenarios: [],
  };
  let generationAttempts = 0;
  let activePage;
  try {
    for (const mode of ['keyboard-desktop', 'touch-mobile']) {
      execFileSync(python, [path.join(__dirname, 'acceptance_p03_chat_draft.py'), '--prepare-ui'],
        { cwd: root, stdio: 'pipe', timeout: 120000 });
      const fixture = JSON.parse(fs.readFileSync(path.join(evidence, 'ui-draft-fixture.json'), 'utf8'));
      const context = await browser.newContext({
        viewport: mode === 'keyboard-desktop' ? { width: 1440, height: 1000 } : { width: 390, height: 844 },
        hasTouch: mode === 'touch-mobile', locale: 'zh-CN',
      });
      await context.route('**/api/ask/**', async (route) => {
        generationAttempts++;
        await route.abort();
      });
      const page = await context.newPage();
      activePage = page;
      page.setDefaultTimeout(45000);
      await page.goto(origin + '/login');
      await page.locator('input[name="email"]').fill(accounts.a.email);
      await page.locator('input[name="password"]').fill(accounts.a.password);
      const loginResult = page.waitForResponse((response) =>
        new URL(response.url()).pathname === '/api/auth/login' && response.status() === 200);
      await page.locator('button[type="submit"]').click();
      const auth = { Authorization: 'Bearer ' + (await (await loginResult).json()).token };
      await page.waitForURL(/\/c\//);
      await page.goto(origin + '/c/' + fixture.conversation_id);
      const card = page.locator(`[data-testid="reminder-draft-card"][data-source-message-id="${fixture.message_id}"]`);
      await card.waitFor();
      const chip = card.getByRole('button', { name: '09:00', exact: true });
      await chip.scrollIntoViewIfNeeded();
      assert.match(await card.innerText(), /不是银色/);
      assert.equal(await card.locator('input[type="date"], input[type="time"]').count(), 0);
      const dimensions = await chip.boundingBox();
      assert.ok(dimensions.height >= 44);
      await page.screenshot({ path: path.join(evidence, `chips-${mode}-before.png`), fullPage: true });
      const selected = page.waitForResponse((response) =>
        new URL(response.url()).pathname.endsWith(`/reminder-drafts/${fixture.draft_id}/select`));
      if (mode === 'keyboard-desktop') {
        // Tab from a known adjacent button to prove the chip participates in keyboard focus order.
        const firstChip = card.getByRole('button', { name: '08:00', exact: true });
        await firstChip.focus();
        await page.keyboard.press('Tab');
        assert.equal(await chip.evaluate((element) => document.activeElement === element), true);
        await page.keyboard.press('Enter');
      } else {
        await chip.tap();
      }
      const selectedResponse = await selected;
      assert.equal(selectedResponse.status(), 200);
      const saved = await selectedResponse.json();
      assert.equal(saved.status, 'scheduled');
      assert.ok(saved.reminder.reminder_id);
      assert.match(saved.reminder.title, /不是银色/);
      const link = card.locator(`a[href="/reminders/${saved.reminder.reminder_id}"]`);
      await link.waitFor();
      await page.screenshot({ path: path.join(evidence, `chips-${mode}-created.png`), fullPage: true });
      const cancelButton = card.getByRole('button', { name: /取消提醒|取消|Cancel reminder|Cancel/i }).first();
      const cancelled = page.waitForResponse((response) =>
        new URL(response.url()).pathname.endsWith(`/reminder-drafts/${fixture.draft_id}`) &&
        response.request().method() === 'DELETE');
      if (mode === 'touch-mobile') await cancelButton.tap();
      else {
        await cancelButton.focus();
        await page.keyboard.press('Enter');
      }
      const cancelResponse = await cancelled;
      assert.equal(cancelResponse.status(), 200);
      assert.equal((await cancelResponse.json()).status, 'cancelled');
      await page.reload();
      await card.waitFor();
      assert.match(await card.innerText(), /已取消|Cancelled|Canceled/i);
      const detail = await context.request.get(origin + '/life-api/api/v1/reminders/' + saved.reminder.reminder_id,
        { headers: auth });
      assert.equal(detail.status(), 200);
      assert.equal((await detail.json()).reminder.status, 'cancelled');
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
      assert.equal(overflow, false);
      await page.screenshot({ path: path.join(evidence, `chips-${mode}-cancelled.png`), fullPage: true });
      // A fresh browser context supplies a separate authenticated session.
      const fresh = await browser.newContext({ locale: 'zh-CN' });
      await fresh.route('**/api/ask/**', (route) => route.abort());
      const otherPage = await fresh.newPage();
      await otherPage.goto(origin + '/login');
      await otherPage.locator('input[name="email"]').fill(accounts.a.email);
      await otherPage.locator('input[name="password"]').fill(accounts.a.password);
      await otherPage.locator('button[type="submit"]').click();
      await otherPage.waitForURL(/\/c\//, { timeout: 45000 });
      await otherPage.goto(origin + '/c/' + fixture.conversation_id);
      const restored = otherPage.locator(`[data-source-message-id="${fixture.message_id}"]`);
      await restored.waitFor();
      assert.match(await restored.innerText(), /已取消|Cancelled|Canceled/i);
      report.scenarios.push({
        mode, status: 'PASS', draft_id: fixture.draft_id,
        source_message_id: fixture.message_id, reminder_id: saved.reminder.reminder_id,
        only_time_missing: true, negated_constraint_preserved: true,
        touch_target_height: dimensions.height, saved_status: saved.status,
        cancelled_after_reload: true, cancelled_in_fresh_authenticated_session: true,
        horizontal_overflow: overflow,
      });
      await fresh.close();
      await context.close();
    }
    assert.equal(generationAttempts, 0);
    report.status = 'PASS';
  } catch (error) {
    report.error = error.message;
    if (activePage && !activePage.isClosed()) {
      await activePage.screenshot({ path: path.join(evidence, 'chips-failure.png'), fullPage: true });
      report.failure_path = new URL(activePage.url()).pathname;
      report.visible_cards = await activePage.locator('[data-testid="reminder-draft-card"]').count();
    }
    throw error;
  } finally {
    report.generation_attempts = generationAttempts;
    report.ended_at = new Date().toISOString();
    fs.writeFileSync(path.join(evidence, 'chips-live-ui.json'), JSON.stringify(report, null, 2));
    await browser.close();
    console.log(JSON.stringify(report));
  }
})().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
