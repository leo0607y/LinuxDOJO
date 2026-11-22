import { chromium } from 'playwright';
import { startServer } from './server.mjs';

export const SHOT_DIR = process.env.SHOT_DIR || '/tmp/danganlog-shots';
export async function setup() {
  const { server, url } = await startServer();
  const browser = await chromium.launch();
  return { server, url, browser, close: async () => { await browser.close(); server.close(); } };
}
export async function openApp(browser, url, opts = {}) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 720 }, colorScheme: 'dark', acceptDownloads: true, ...opts });
  const page = await context.newPage();
  await page.goto(url);
  await page.waitForSelector('.rt.ready', { timeout: 120000 });
  return { context, page };
}
export async function run(page, line) {
  await page.fill('#terminal-input', line);
  await page.press('#terminal-input', 'Enter');
}

/* progress コマンドの出力から、現在のコースの達成数 'N/M' を読む */
export async function progressLine(page, courseName) {
  await run(page, 'progress');
  await page.waitForFunction((n) => [...document.querySelectorAll('.out')].some((o) => o.textContent.includes('合計')), courseName);
  return page.evaluate((n) => { const o = [...document.querySelectorAll('.out')].filter((x) => x.textContent.includes('合計')).pop(); return (o.textContent.split('\n').find((l) => l.includes(n)) || '').trim(); }, courseName);
}
