const { chromium } = require('H:/AI For research institute/LifeCompanion-Rebuild/products/librechat-custom/node_modules/playwright');
const { pathToFileURL } = require('node:url');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    headless: true
  });
  const results = [];
  for (const width of [1440, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 1100 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(pathToFileURL(path.join(__dirname, 'review.html')).href);
    await page.locator('article').last().waitFor();
    await page.screenshot({ path: path.join(__dirname, `review-${width}.png`) });
    await page.locator('#search').fill('S03');
    if (await page.locator('article:visible').count() !== 1) throw Error('SEARCH_FILTER');
    await page.screenshot({ path: path.join(__dirname, `goal-${width}.png`), fullPage: true });
    await page.locator('#search').fill('');
    await page.locator('#split').selectOption('holdout');
    if (await page.locator('article:visible').count() !== 12) throw Error('SPLIT_FILTER');
    await page.locator('#search').fill('S33');
    if (await page.locator('article:visible').count() !== 1) throw Error('HOLDOUT_SEARCH');
    await page.screenshot({ path: path.join(__dirname, `text-only-${width}.png`), fullPage: true });
    const overflow = await page.evaluate(() =>
      document.documentElement.scrollWidth > window.innerWidth);
    results.push({ width, errors, overflow, filter: 'PASS', screenshots: 3 });
    if (overflow || errors.length) throw Error('BROWSER_VALIDATION');
    await page.close();
  }
  await browser.close();
  fs.writeFileSync(path.join(__dirname, 'browser-checks.json'), JSON.stringify(results, null, 2));
  console.log(JSON.stringify(results, null, 2));
})().catch(error => { console.error(error); process.exitCode = 1; });
