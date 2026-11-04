import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";

const baseUrl = process.env.BASE_URL || "http://127.0.0.1:4182";
const accountsPath = process.env.ACCOUNTS_FILE;
const outputDir = path.resolve(process.env.OUTPUT_DIR || ".");
const productRoot = path.resolve(process.env.PRODUCT_ROOT || ".");
const conversationId = process.env.CONVERSATION_ID;
const messageId = process.env.MESSAGE_ID;
const sourceText = process.env.SOURCE_TEXT;
const chromePath =
  process.env.CHROME_PATH || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";

assert(accountsPath, "ACCOUNTS_FILE is required");
assert(conversationId, "CONVERSATION_ID is required");
assert(messageId, "MESSAGE_ID is required");
assert(sourceText, "SOURCE_TEXT is required");

const require = createRequire(path.join(productRoot, "package.json"));
const { chromium } = require("@playwright/test");
const account = JSON.parse(await readFile(accountsPath, "utf8"))["fixed-test"];
const browser = await chromium.launch({ headless: true, executablePath: chromePath });
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  serviceWorkers: "block",
});
const page = await context.newPage();
let authorizationHeader = null;

page.on("request", (request) => {
  const authorization = request.headers()["authorization"];
  if (authorization && new URL(request.url()).origin === baseUrl) {
    authorizationHeader = authorization;
  }
});

try {
  await page.goto(`${baseUrl}/login`, { waitUntil: "domcontentloaded" });
  await page.locator('form[aria-label="Login form"]').waitFor();
  await page.locator("#email").fill(account.email);
  await page.locator("#password").fill(account.password);
  await page.locator('[data-testid="login-button"]').click();
  await page.waitForURL(/\/c\/new/, { timeout: 30_000 });

  await page.goto(`${baseUrl}/c/${conversationId}`, {
    waitUntil: "domcontentloaded",
  });
  await page
    .locator('[data-testid="direct-moment-test-actions"]')
    .first()
    .waitFor({ timeout: 30_000 });
  assert(authorizationHeader, "authenticated request header is not available");

  const result = await page.evaluate(
    async ({ authorization, body }) => {
      const response = await fetch("/life-api/api/v1/test/direct-moment", {
        method: "POST",
        headers: {
          Authorization: authorization,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      });
      return { status: response.status, body: await response.json() };
    },
    {
      authorization: authorizationHeader,
      body: {
        conversation_id: conversationId,
        source_message_id: messageId,
        text: `${sourceText} [read-only-source-probe]`,
      },
    },
  );

  assert.equal(result.status, 409, JSON.stringify(result.body));
  assert.equal(
    result.body.detail.code,
    "SOURCE_MESSAGE_CHANGED_OR_DELETED",
    JSON.stringify(result.body),
  );
  const report = {
    status: "PASS",
    classification: "READ_ONLY_SOURCE_CHAIN_PROBE",
    conversation_id: conversationId,
    source_message_id: messageId,
    core_response_status: result.status,
    core_response_code: result.body.detail.code,
    provider_request_expected: false,
    completed_at: new Date().toISOString(),
  };
  await writeFile(
    path.join(outputDir, "source-chain-probe.json"),
    JSON.stringify(report, null, 2),
  );
  console.log(JSON.stringify(report, null, 2));
} finally {
  await context.close();
  await browser.close();
}
