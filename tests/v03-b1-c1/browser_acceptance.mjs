import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import path from 'node:path';

const baseUrl = process.env.BASE_URL || 'http://127.0.0.1:4175';
const fixturePath = process.env.FIXTURE_PATH;
const outputDir = path.resolve(process.env.OUTPUT_DIR);
const productRoot = path.resolve(process.env.PRODUCT_ROOT);
const chromePath =
  process.env.CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

assert(fixturePath, 'FIXTURE_PATH is required');
assert(outputDir, 'OUTPUT_DIR is required');
assert(process.env.PRODUCT_ROOT, 'PRODUCT_ROOT is required');
const require = createRequire(path.join(productRoot, 'package.json'));
const { chromium } = require('@playwright/test');

const fixture = JSON.parse(await readFile(fixturePath, 'utf8'));
const ownerId = fixture.owner.librechat_user_id;
const imageCaption = '清晨在厨房给薄荷浇水，为自己留下一杯热茶。';
const textCaption = '晚饭后沿河散步，听见远处有人练习萨克斯。';
const hiddenCaption = '这条私密内容不得作为正式回忆展示。';

function base64url(value) {
  return Buffer.from(JSON.stringify(value)).toString('base64url');
}

function tokenFor(userId) {
  const header = base64url({ alg: 'HS256', typ: 'JWT' });
  const payload = base64url({
    id: userId,
    exp: Math.floor(Date.now() / 1000) + 900,
  });
  const signature = crypto
    .createHmac('sha256', 'v03-b1-c1-synthetic-jwt-secret')
    .update(`${header}.${payload}`)
    .digest('base64url');
  return `${header}.${payload}.${signature}`;
}

const token = tokenFor(ownerId);
const user = {
  id: ownerId,
  username: 'v03-b1-owner',
  email: 'v03-b1-owner@example.invalid',
  name: 'B1 合成验收用户',
  avatar: '',
  role: 'USER',
  provider: 'local',
  plugins: [],
  personalization: { memories: true },
  createdAt: '2026-11-04T00:00:00.000Z',
  updatedAt: '2026-11-04T00:00:00.000Z',
};
const startupConfig = {
  appTitle: 'LifeCompanion B1/C1 验收',
  socialLogins: [],
  interface: {},
  discordLoginEnabled: false,
  facebookLoginEnabled: false,
  githubLoginEnabled: false,
  googleLoginEnabled: false,
  openidLoginEnabled: false,
  appleLoginEnabled: false,
  samlLoginEnabled: false,
  openidLabel: '',
  openidImageUrl: '',
  openidAutoRedirect: false,
  samlLabel: '',
  samlImageUrl: '',
  serverDomain: baseUrl,
  emailLoginEnabled: true,
  registrationEnabled: false,
  socialLoginEnabled: false,
  passwordResetEnabled: false,
  emailEnabled: false,
  showBirthdayIcon: false,
  helpAndFaqURL: 'https://example.invalid',
  sharedLinksEnabled: false,
  publicSharedLinksEnabled: false,
  allowAccountDeletion: false,
  minPasswordLength: 8,
  modelSpecs: { list: [] },
  endpointsDropParamsMap: {},
};

let loginAccepted = false;
const browserConsoleErrors = [];
const pageErrors = [];
const externalRequests = [];
const lifeRequests = [];
const mockRequests = [];
const isolatedUpstreamMocks = [];

const browser = await chromium.launch({
  headless: true,
  executablePath: chromePath,
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  colorScheme: 'light',
  serviceWorkers: 'block',
});

await context.route('**/*', async (route) => {
  const request = route.request();
  const url = new URL(request.url());
  if (url.origin !== baseUrl) {
    externalRequests.push(url.origin);
    await route.continue();
    return;
  }
  if (url.pathname.startsWith('/life-api/')) {
    lifeRequests.push(`${request.method()} ${url.pathname}`);
    if (url.pathname === '/life-api/api/v1/memories') {
      isolatedUpstreamMocks.push(`${request.method()} ${url.pathname}`);
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          memories: [],
          total: 0,
          page: 1,
          page_size: 20,
          has_more: false,
        }),
      });
      return;
    }
    await route.continue();
    return;
  }
  if (url.pathname === '/health') {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'OK' }),
    });
    return;
  }
  if (!url.pathname.startsWith('/api/')) {
    await route.continue();
    return;
  }

  mockRequests.push(`${request.method()} ${url.pathname}`);
  if (url.pathname === '/api/config') {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(startupConfig),
    });
    return;
  }
  if (url.pathname === '/api/auth/refresh') {
    if (loginAccepted) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ token, user }),
      });
    } else {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: '{}',
      });
    }
    return;
  }
  if (url.pathname === '/api/auth/login') {
    loginAccepted = true;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ token, user }),
    });
    return;
  }
  if (url.pathname === '/api/user') {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(user),
    });
    return;
  }
  if (url.pathname === '/api/user/terms') {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ termsAccepted: true }),
    });
    return;
  }
  if (url.pathname === '/api/search/enabled') {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: 'false',
    });
    return;
  }
  if (url.pathname === '/api/user/settings/favorites') {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: '[]',
    });
    return;
  }
  if (url.pathname === '/api/user/settings/pinned-order') {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: '[]',
    });
    return;
  }
  if (url.pathname === '/api/convos') {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ conversations: [], nextCursor: null }),
    });
    return;
  }
  if (url.pathname === '/api/projects') {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ projects: [], pinned: [] }),
    });
    return;
  }
  if (url.pathname.startsWith('/api/agents')) {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ data: [] }),
    });
    return;
  }
  if (url.pathname.startsWith('/api/assistants')) {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ data: [] }),
    });
    return;
  }
  if (url.pathname.startsWith('/api/files')) {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ files: [] }),
    });
    return;
  }
  if (url.pathname.startsWith('/api/roles/')) {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ name: 'USER', permissions: {} }),
    });
    return;
  }
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({}),
  });
});

const page = await context.newPage();
page.on('console', (message) => {
  if (message.type() === 'error') {
    browserConsoleErrors.push(message.text());
  }
});
page.on('pageerror', (error) => pageErrors.push(error.stack || error.message));

async function assertNoHorizontalOverflow(label) {
  const dimensions = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  assert(
    dimensions.scrollWidth <= dimensions.clientWidth,
    `${label} has horizontal overflow: ${JSON.stringify(dimensions)}`,
  );
  return dimensions;
}

async function waitForLoadedImage(locator, label) {
  await locator.waitFor({ state: 'visible' });
  await locator.evaluate(
    (image) =>
      new Promise((resolve, reject) => {
        if (image.complete && image.naturalWidth > 0) {
          resolve();
          return;
        }
        image.addEventListener('load', () => resolve(), { once: true });
        image.addEventListener('error', () => reject(new Error('image failed')), { once: true });
      }),
  );
  const size = await locator.evaluate((image) => ({
    naturalWidth: image.naturalWidth,
    naturalHeight: image.naturalHeight,
    src: image.currentSrc,
  }));
  assert(size.naturalWidth > 0 && size.naturalHeight > 0, `${label} did not decode`);
  assert(size.src.startsWith('blob:'), `${label} is not an authenticated object URL`);
  return size;
}

await page.goto(`${baseUrl}/login`, { waitUntil: 'domcontentloaded' });
await page.locator('form[aria-label="Login form"]').waitFor();
await page.locator('#email').fill('v03-b1-owner@example.invalid');
await page.locator('#password').fill('Synthetic-B1-C1-Password!');
await page.locator('[data-testid="login-button"]').click();
await page.waitForURL(/\/c\/new/, { timeout: 20000 });

await page.goto(`${baseUrl}/memories`, { waitUntil: 'domcontentloaded' });
await page
  .locator('[data-testid="moment-card"]')
  .first()
  .waitFor({ timeout: 20000 })
  .catch(async (error) => {
    await page.screenshot({
      path: path.join(outputDir, 'debug-memories-timeout.png'),
      fullPage: true,
    });
    console.error(
      JSON.stringify(
        {
          url: page.url(),
          body: (await page.locator('body').innerText()).slice(0, 4000),
          consoleErrors: browserConsoleErrors,
          pageErrors,
          lifeRequests,
          mockRequests,
        },
        null,
        2,
      ),
    );
    throw error;
  });
const cards = page.locator('[data-testid="moment-card"]');
assert.equal(await cards.count(), 2, 'exactly the image and text moments should render');

const imageCard = cards.filter({ hasText: imageCaption });
const textCard = cards.filter({ hasText: textCaption });
assert.equal(await imageCard.count(), 1);
assert.equal(await textCard.count(), 1);
assert.equal(await textCard.locator('img').count(), 0, 'text-only card must not render an image');
assert.equal(await page.getByText(hiddenCaption, { exact: true }).count(), 0);
assert.equal(await page.getByText('AI 生成', { exact: true }).count(), 1);
assert.equal(await page.getByText('AI 创作画面', { exact: true }).count(), 1);
assert.equal(await page.getByText('AI 整理文字', { exact: true }).count(), 1);

const thumbnail = imageCard.locator('img');
const thumbnailSize = await waitForLoadedImage(thumbnail, 'desktop thumbnail');
await page.screenshot({
  path: path.join(outputDir, 'memories-desktop-1440.png'),
  fullPage: true,
});
const desktopLayout = await assertNoHorizontalOverflow('desktop');

await imageCard.click();
await page.waitForURL(new RegExp(`/moments/${fixture.moment_ids.image}`));
const originalButton = page.getByRole('button', { name: '查看回忆原图' });
await originalButton.waitFor();
const detailImage = originalButton.locator('img');
const originalSize = await waitForLoadedImage(detailImage, 'desktop original');
assert.equal(await page.getByText('删除这张衍生回忆', { exact: true }).count(), 1);
equalText(
  await page.getByText('关闭或调整后续自动生图', { exact: true }).count(),
  1,
);
await page.screenshot({
  path: path.join(outputDir, 'moment-detail-desktop-1440.png'),
  fullPage: true,
});

await originalButton.click();
await page.getByRole('dialog').waitFor();
assert.equal(await page.getByText('960 × 1280', { exact: true }).count() > 0, true);
await page.screenshot({
  path: path.join(outputDir, 'moment-original-desktop-1440.png'),
  fullPage: true,
});
await page.keyboard.press('Escape');
await page.getByRole('dialog').waitFor({ state: 'hidden' });

await page.setViewportSize({ width: 390, height: 844 });
await page.goto(`${baseUrl}/memories`, { waitUntil: 'domcontentloaded' });
await page.locator('[data-testid="moment-card"]').first().waitFor({ timeout: 20000 });
assert.equal(await page.locator('[data-testid="moment-card"]').count(), 2);
const mobileImageCard = page.locator('[data-testid="moment-card"]').filter({ hasText: imageCaption });
const mobileThumbnail = await waitForLoadedImage(
  mobileImageCard.locator('img'),
  'mobile thumbnail',
);
await page.screenshot({
  path: path.join(outputDir, 'memories-mobile-390.png'),
  fullPage: true,
});
const mobileLayout = await assertNoHorizontalOverflow('mobile');

const postRequests = lifeRequests.filter((request) => request.startsWith('POST '));
const externalApiRequests = externalRequests.filter(
  (origin) => origin.includes('siliconflow') || origin.includes('api.deepseek.com'),
);
assert.equal(externalApiRequests.length, 0, 'browser must not call a model provider');
assert.equal(
  postRequests.filter((request) => request.includes('/retry')).length,
  0,
  'browser must not trigger a generation retry',
);
assert.equal(pageErrors.length, 0, `page errors: ${pageErrors.join('\n')}`);

const report = {
  status: 'PASS',
  classification: 'REAL_IMAGE_SYNTHETIC_BROWSER_FIXTURE',
  base_url: baseUrl,
  login: {
    mode: 'PLAYWRIGHT_SYNTHETIC_AUTH_MOCK',
    form_submitted: true,
    production_auth_modified: false,
  },
  checks: {
    image_card_visible: 'PASS',
    text_only_card_visible: 'PASS',
    private_skip_not_rendered: 'PASS',
    ai_badge_visible: 'PASS',
    authenticated_blob_thumbnail: 'PASS',
    authenticated_blob_original: 'PASS',
    lightbox_open: 'PASS',
    delete_control_visible: 'PASS',
    stop_auto_images_control_visible: 'PASS',
    desktop_no_horizontal_overflow: 'PASS',
    mobile_no_horizontal_overflow: 'PASS',
    no_provider_network_requests: 'PASS',
  },
  image_evidence: {
    thumbnail_natural_size: thumbnailSize,
    original_natural_size: originalSize,
    mobile_thumbnail_natural_size: mobileThumbnail,
  },
  layout: {
    desktop: desktopLayout,
    mobile: mobileLayout,
  },
  screenshots: {
    desktop_memories: path.join(outputDir, 'memories-desktop-1440.png'),
    desktop_detail: path.join(outputDir, 'moment-detail-desktop-1440.png'),
    desktop_lightbox: path.join(outputDir, 'moment-original-desktop-1440.png'),
    mobile_memories: path.join(outputDir, 'memories-mobile-390.png'),
  },
  requests: {
    life_api: lifeRequests,
    isolated_upstream_mocks: isolatedUpstreamMocks,
    external_origins: [...new Set(externalRequests)],
    siliconflow_or_chat_provider: externalApiRequests,
    automatic_image_generation_requests: 0,
  },
  console_errors: browserConsoleErrors,
  page_errors: pageErrors,
  completed_at: new Date().toISOString(),
};

await writeFile(
  path.join(outputDir, 'browser-verification.json'),
  JSON.stringify(report, null, 2),
);
console.log(JSON.stringify(report, null, 2));

await context.close();
await browser.close();

function equalText(actual, expected) {
  assert.equal(actual, expected);
}
