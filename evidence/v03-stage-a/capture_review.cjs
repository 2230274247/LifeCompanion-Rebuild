const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');
const { chromium } = require('H:/AI For research institute/LifeCompanion-Rebuild/products/librechat-custom/node_modules/playwright');

async function main() {
  const root = path.resolve(__dirname, 'acceptance');
  const latest = fs.readdirSync(root, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort()
    .pop();
  const requested = process.argv[2];
  const output = requested
    ? (path.isAbsolute(requested) ? requested : path.join(root, requested))
    : path.join(root, latest);
  const browser = await chromium.launch({
    headless: true,
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  });
  const consoleMessages = [];
  try {
    for (const width of [1440, 390]) {
      const page = await browser.newPage({ viewport: { width, height: 1000 }, deviceScaleFactor: 1 });
      page.on('console', (message) => consoleMessages.push(`${width}:${message.type()}:${message.text()}`));
      await page.goto(pathToFileURL(path.join(output, 'selection-review.html')).href);
      await page.screenshot({
        path: path.join(output, `selection-review-${width}.png`),
        fullPage: true,
      });
      await page.close();
    }
  } finally {
    await browser.close();
  }
  fs.writeFileSync(path.join(output, 'browser-console.log'), consoleMessages.join('\n'), 'utf8');
  console.log(JSON.stringify({ output, screenshots: ['selection-review-1440.png', 'selection-review-390.png'] }));
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
