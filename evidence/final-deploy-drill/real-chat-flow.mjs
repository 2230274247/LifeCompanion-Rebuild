import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";

const baseUrl = process.env.FINAL_DRILL_BASE_URL || "http://127.0.0.1:23001";
const outputDir = path.resolve(process.env.FINAL_DRILL_OUTPUT || "evidence/final-deploy-drill");
const root = process.cwd();
const require = createRequire(path.join(root, "products/librechat-custom/package.json"));
const { chromium } = require("@playwright/test");
const accounts = JSON.parse(await readFile("infra/runtime/final-drill/accounts.json", "utf8"));
const owner = accounts.owner;
const peer = accounts.peer;
const prompt = "今天傍晚我在阳台上给茉莉花浇水，风很凉快。";
const report = {
  status: "FAIL",
  base_url: baseUrl,
  classification: "SYNTHETIC_ISOLATED_ACCOUNT",
  prompt,
  checks: {},
  console_errors: [],
  page_errors: [],
  network_errors: [],
  model_requests: 0,
  credentials_printed: false,
};

function textFromMessage(message) {
  if (typeof message?.text === "string" && message.text) return message.text;
  if (!Array.isArray(message?.content)) return "";
  return message.content
    .map((part) => (typeof part?.text === "string" ? part.text : ""))
    .filter(Boolean)
    .join("\n");
}

async function login(email, password) {
  const response = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  assert.equal(response.status, 200, `login HTTP ${response.status}`);
  const body = await response.json();
  assert(body.token, "login token missing");
  return body.token;
}

async function gatewayGet(token, route) {
  const response = await fetch(`${baseUrl}${route}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const text = await response.text();
  let body;
  try { body = text ? JSON.parse(text) : null; } catch { body = text; }
  return { status: response.status, body };
}

const browser = await chromium.launch({
  headless: true,
  executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  colorScheme: "light",
  serviceWorkers: "block",
});
const page = await context.newPage();
let agentPostSeen = false;
page.on("console", (message) => {
  if (message.type() === "error") report.console_errors.push(message.text());
});
page.on("pageerror", (error) => report.page_errors.push(error.stack || error.message));
page.on("request", (request) => {
  if (request.method() === "POST" && new URL(request.url()).pathname.endsWith("/api/agents")) {
    agentPostSeen = true;
    report.model_requests += 1;
  }
});
page.on("requestfailed", (request) => {
  const url = new URL(request.url());
  if (url.origin === baseUrl) report.network_errors.push(`${request.method()} ${url.pathname}: ${request.failure()?.errorText}`);
});
page.on("response", (response) => {
  const url = new URL(response.url());
  if (url.origin === baseUrl && response.status() >= 400) {
    report.network_errors.push(`${response.request().method()} ${url.pathname}: HTTP ${response.status()}`);
  }
});

try {
  await page.goto(`${baseUrl}/login`, { waitUntil: "domcontentloaded" });
  await page.locator('form[aria-label="Login form"]').waitFor({ timeout: 30000 });
  await page.locator("#email").fill(owner.email);
  await page.locator("#password").fill(owner.password);
  const loginResponsePromise = page.waitForResponse(
    (response) => new URL(response.url()).pathname === "/api/auth/login" && response.request().method() === "POST",
  );
  await page.locator('[data-testid="login-button"]').click();
  const loginResponse = await loginResponsePromise;
  assert.equal(loginResponse.status(), 200, "browser login must succeed");
  const ownerToken = (await loginResponse.json()).token;
  assert(ownerToken, "browser login token missing");
  await page.waitForURL(/\/c\/new/, { timeout: 30000 });
  report.checks.real_browser_login = "PASS";

  await page.goto(`${baseUrl}/c/new`, { waitUntil: "domcontentloaded" });
  const composer = page.locator('[data-testid="text-input"]');
  await composer.waitFor({ timeout: 30000 });
  await composer.fill(prompt);
  await composer.press("Enter");
  await page.waitForURL(/\/c\/(?!new)[^/?#]+/, { timeout: 30000 });
  const conversationId = new URL(page.url()).pathname.split("/").filter(Boolean)[1];
  assert(conversationId && conversationId !== "new", "conversation id missing");

  let persisted = [];
  let assistantText = "";
  const messageDeadline = Date.now() + 120000;
  while (Date.now() < messageDeadline) {
    const response = await page.request.get(`${baseUrl}/api/messages?conversationId=${encodeURIComponent(conversationId)}`, {
      headers: { Authorization: `Bearer ${ownerToken}` },
    });
    if (response.status() === 200) {
      const body = await response.json();
      persisted = Array.isArray(body) ? body : (body.messages || []);
      const user = persisted.find((item) => item.isCreatedByUser === true && item.text === prompt);
      const assistant = persisted.find((item) => item.isCreatedByUser === false && textFromMessage(item));
      if (user && assistant) {
        assistantText = textFromMessage(assistant);
        report.user_message_id = user.messageId;
        report.assistant_message_id = assistant.messageId;
        break;
      }
    }
    await page.waitForTimeout(1000);
  }
  assert(report.user_message_id, "user message was not persisted");
  assert(assistantText.length > 0, "assistant message was not persisted");
  report.model_request_observed = agentPostSeen;
  report.assistant_chars = assistantText.length;
  report.conversation_id = conversationId;
  report.checks.real_model_chat_and_persisted_turns = "PASS";
  await page.screenshot({ path: path.join(outputDir, "chat-desktop-1440.png"), fullPage: true });

  let memory = null;
  let memoryBody = null;
  const memoryDeadline = Date.now() + 180000;
  while (Date.now() < memoryDeadline) {
    const response = await gatewayGet(ownerToken, "/life-api/api/v1/memories?page_size=20");
    assert.equal(response.status, 200, `owner memories HTTP ${response.status}`);
    memoryBody = response.body;
    memory = memoryBody?.memories?.find((item) => /茉莉|阳台|浇水/.test(`${item.title || ""} ${item.summary || ""} ${item.content || ""}`));
    if (memory) break;
    await page.waitForTimeout(2000);
  }
  assert(memory, "owner memory was not published from the real chat turn");
  report.memory = {
    event_id: memory.event_id,
    title: memory.title,
    summary: memory.summary,
    content_chars: String(memory.content || "").length,
    status: memory.status,
    memo_ref_present: Boolean(memory.memo_ref),
  };
  report.checks.real_chat_memory_publish = "PASS";

  const peerToken = await login(peer.email, peer.password);
  const peerList = await gatewayGet(peerToken, "/life-api/api/v1/memories?page_size=20");
  assert.equal(peerList.status, 200, `peer memories HTTP ${peerList.status}`);
  assert.equal(peerList.body.total, 0, "peer must not see owner memories");
  const peerDetail = await gatewayGet(peerToken, `/life-api/api/v1/memories/${memory.event_id}`);
  assert.equal(peerDetail.status, 404, "peer direct memory detail must be hidden");
  const ownerDetail = await gatewayGet(ownerToken, `/life-api/api/v1/memories/${memory.event_id}`);
  assert.equal(ownerDetail.status, 200, "owner direct memory detail must be visible");
  report.checks.owner_peer_isolation = "PASS";

  report.status = "PASS";
} catch (error) {
  report.error_type = error.name;
  report.error_message = error.message;
  await page.screenshot({ path: path.join(outputDir, "failure.png"), fullPage: true }).catch(() => null);
  throw error;
} finally {
  await context.close();
  await browser.close();
  await writeFile(path.join(outputDir, "real-chat-flow.json"), JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify(report, null, 2));
}
