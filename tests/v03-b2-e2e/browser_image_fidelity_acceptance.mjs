import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";

const chatUrl = process.env.CHAT_URL || "http://127.0.0.1:3093";
const coreUrl = process.env.CORE_URL || "http://127.0.0.1:8034";
const accountsPath = process.env.ACCOUNTS_FILE;
const outputDir = path.resolve(process.env.OUTPUT_DIR || ".");
const productRoot = path.resolve(
  process.env.PRODUCT_ROOT ||
    path.join(process.cwd(), "../../products/librechat-custom"),
);
const chromePath =
  process.env.CHROME_PATH ||
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";

assert(accountsPath, "ACCOUNTS_FILE is required");

const require = createRequire(path.join(productRoot, "package.json"));
const { chromium } = require("@playwright/test");
const account = JSON.parse(
  await readFile(accountsPath, "utf8"),
)["fixed-test"];

const cases = [
  {
    name: "morning_run",
    text: "今天早上六点起床去公园跑步，跑完后觉得精神很好。",
    expected: ["清晨", "公园", "跑步"],
  },
  {
    name: "mint_watering",
    text: "今天下午我在厨房窗边给一盆薄荷浇水，黄色小水壶放在木桌上。",
    expected: ["厨房", "薄荷", "浇水"],
  },
  {
    name: "family_noodles",
    text: "晚上在厨房给家人煮了一碗热汤面，大家吃得很开心。",
    expected: ["厨房", "饭菜", "家人"],
  },
];

await mkdir(outputDir, { recursive: true });
const browser = await chromium.launch({
  headless: true,
  executablePath: chromePath,
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  colorScheme: "light",
  serviceWorkers: "block",
});
const page = await context.newPage();

const api = async (url, options = {}) => {
  const response = await fetch(url, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(options.headers || {}),
    },
    signal: AbortSignal.timeout(180_000),
  });
  const text = await response.text();
  let body;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  return { status: response.status, body, headers: response.headers };
};

let token;
try {
  const loginResponsePromise = page.waitForResponse(
    (response) =>
      response.url() === `${chatUrl}/api/auth/login` &&
      response.request().method() === "POST",
  );
  await page.goto(`${chatUrl}/login`, { waitUntil: "domcontentloaded" });
  await page.locator('form[aria-label="Login form"]').waitFor();
  await page.locator("#email").fill(account.email);
  await page.locator("#password").fill(account.password);
  await page.locator('[data-testid="login-button"]').click();
  const loginResponse = await loginResponsePromise;
  assert.equal(loginResponse.status(), 200, "LibreChat login failed");
  token = (await loginResponse.json()).token;
  assert(token, "LibreChat token missing");
  await page.waitForURL(/\/c\/new/, { timeout: 30_000 });

  for (const item of cases) {
    await page.goto(`${chatUrl}/c/new`, { waitUntil: "domcontentloaded" });
    const composer = page.locator('[data-testid="text-input"]');
    await composer.waitFor({ state: "visible", timeout: 30_000 });
    const deadline = Date.now() + 120_000;
    while (!(await composer.isEnabled()) && Date.now() < deadline) {
      await page.waitForTimeout(500);
    }
    assert(await composer.isEnabled(), `composer unavailable for ${item.name}`);
    await composer.click();
    await page.keyboard.insertText(item.text);
    const sendButton = page.getByRole("button", { name: "发送消息" });
    const armed = Date.now() + 30_000;
    while (!(await sendButton.isEnabled()) && Date.now() < armed) {
      await page.waitForTimeout(200);
    }
    assert(await sendButton.isEnabled(), `send button disabled for ${item.name}`);
    await sendButton.click();
    if (!page.url().match(/\/c\/[0-9a-f-]+$/i)) {
      await page.waitForURL(/\/c\/[0-9a-f-]+$/i, { timeout: 30_000 });
    }
    item.conversationId = new URL(page.url()).pathname.split("/").at(-1);
    assert(
      item.conversationId && item.conversationId !== "new",
      `conversation id missing for ${item.name}`,
    );

    let messages = [];
    const messageDeadline = Date.now() + 120_000;
    while (Date.now() < messageDeadline) {
      const response = await api(
        `${chatUrl}/api/messages?conversationId=${encodeURIComponent(item.conversationId)}`,
      );
      assert.equal(response.status, 200, "message lookup failed");
      messages = response.body.messages || response.body;
      if (
        messages.some(
          (message) => message.isCreatedByUser && message.text === item.text,
        )
      ) {
        break;
      }
      await page.waitForTimeout(500);
    }
    item.source = messages.find(
      (message) =>
        message.isCreatedByUser &&
        message.text === item.text &&
        message.messageId,
    );
    assert(item.source, `source message missing for ${item.name}`);
  }

  const results = [];
  for (const item of cases) {
    const response = await api(
      `${coreUrl}/api/v1/test/direct-moment`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: item.conversationId,
          source_message_id: item.source.messageId,
          text: item.text,
        }),
      },
    );
    assert.equal(
      response.status,
      200,
      `direct moment failed for ${item.name}: ${JSON.stringify(response.body)}`,
    );
    const moment = response.body.moment;
    assert.equal(moment.status, "generated", `${item.name} did not generate`);
    assert(moment.media?.trace_id, `${item.name} trace id missing`);

    const detail = await api(
      `${coreUrl}/api/v1/moments/${encodeURIComponent(moment.moment_id)}`,
    );
    assert.equal(detail.status, 200, `${item.name} detail lookup failed`);
    const image = await fetch(
      `${coreUrl}/api/v1/moments/${encodeURIComponent(moment.moment_id)}/image`,
      {
        headers: { Authorization: `Bearer ${token}` },
        signal: AbortSignal.timeout(60_000),
      },
    );
    assert.equal(image.status, 200, `${item.name} image download failed`);
    const imageBytes = Buffer.from(await image.arrayBuffer());
    const imagePath = path.join(outputDir, `${item.name}-kolors.png`);
    await writeFile(imagePath, imageBytes);
    const evidence = JSON.parse(
      detail.body.moment.prompt_evidence_json || "{}",
    );
    const result = {
      name: item.name,
      source_text: item.text,
      expected_visual_facts: item.expected,
      conversation_id: item.conversationId,
      source_message_id: item.source.messageId,
      moment_id: moment.moment_id,
      event_at: detail.body.moment.event_at,
      message_at: detail.body.moment.message_at,
      generated_at: detail.body.moment.generated_at,
      display_slot: detail.body.moment.display_slot,
      prompt_version: detail.body.moment.prompt_version,
      generation_key: detail.body.moment.generation_key,
      evidence,
      media: detail.body.moment.media,
      image_path: imagePath,
      image_sha256: require("node:crypto")
        .createHash("sha256")
        .update(imageBytes)
        .digest("hex"),
    };
    await writeFile(
      path.join(outputDir, `${item.name}-evidence.json`),
      JSON.stringify(result, null, 2),
    );
    results.push(result);
  }

  const summary = {
    status: "PASS",
    classification: "REAL_KOLORS_API_PATH",
    chat_url: chatUrl,
    core_url: coreUrl,
    conversations: results.map((result) => result.conversation_id),
    provider: "siliconflow",
    model: "Kwai-Kolors/Kolors",
    prompt_version: results[0].prompt_version,
    results,
    completed_at: new Date().toISOString(),
  };
  await writeFile(
    path.join(outputDir, "summary.json"),
    JSON.stringify(summary, null, 2),
  );
  console.log(JSON.stringify(summary, null, 2));
} finally {
  await context.close();
  await browser.close();
}
