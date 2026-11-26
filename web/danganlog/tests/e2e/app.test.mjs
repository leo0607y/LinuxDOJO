/* 実ブラウザー (Chromium) で out/ を静的配信して操作する。事前に npm run build が必要。 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { AxeBuilder } from '@axe-core/playwright';
import { setup, openApp, run, progressLine, SHOT_DIR } from './helpers.mjs';

const env = await setup();
test.after(() => env.close());
const TASK = '「こんにちは」を画面に表示してみましょう。';

test('起動 → モードとレッスン選択 → 誤答でも課題は見えたまま → ヒント → 正解 → リロード後も保持', async () => {
  const { context, page } = await openApp(env.browser, env.url);
  await page.waitForFunction(() => document.querySelector('#lesson-title').textContent.includes('文字でコンピューターにお願いする'));
  await run(page, 'modes'); await run(page, '2');
  await page.waitForFunction(() => document.querySelector('.motd').textContent.includes('基本コマンド'));
  await run(page, 'modes'); await run(page, '1');
  await page.waitForFunction(() => document.querySelector('.motd').textContent.includes('はじめてのLinux'));
  await run(page, 'menu'); await run(page, '2');
  await page.waitForFunction(() => !document.querySelector('#lesson-title').textContent.includes('お願いする'));
  await run(page, 'goto 1');
  await page.waitForFunction(() => document.querySelector('#lesson-title').textContent.includes('お願いする'));

  await run(page, 'zzz');
  await page.waitForSelector('.tag-ng');
  assert.equal(await page.textContent('#mission-text'), TASK);
  assert.ok(await page.locator('#mission-text').isVisible());
  await run(page, 'hint');
  await page.waitForSelector('.tag-hint');
  await run(page, 'echo こんにちは');
  await page.waitForSelector('.tag-ok');
  assert.match(await progressLine(page, 'はじめての'), /1\/24/);
  await page.reload();
  await page.waitForSelector('.rt.ready', { timeout: 120000 });
  assert.match(await progressLine(page, 'はじめての'), /1\/24/);
  assert.ok(await page.evaluate(() => localStorage.getItem('dangan-log:state:v1')));
  await context.close();
});

test('未完了の課題・選択中のレッスン・作業ファイルをリロード後に復元', async () => {
  const { context, page } = await openApp(env.browser, env.url);
  await run(page, 'modes'); await run(page, '2');
  await page.waitForFunction(() => document.querySelector('.motd').textContent.includes('基本コマンド'));
  await run(page, 'goto 5');
  await page.waitForFunction(() => document.querySelector('#lesson-title').textContent.includes('表示した文字をファイルに保存する'));
  await run(page, 'echo partial > memo.txt');
  await run(page, 'cat memo.txt');
  await page.waitForFunction(() => [...document.querySelectorAll('.out')].some((el) => el.textContent.includes('partial')));
  await page.waitForFunction(() => localStorage.getItem('dangan-log:state:v1')?.includes('cGFydGlhbAo='));

  await page.close();
  const resumed = await context.newPage();
  await resumed.goto(env.url);
  await resumed.waitForSelector('.rt.ready', { timeout: 120000 });
  assert.match(await resumed.textContent('#lesson-title'), /表示した文字をファイルに保存する/);
  assert.match(await resumed.textContent('#mission-text'), /memo\.txt/);
  await run(resumed, 'cat memo.txt');
  await resumed.waitForFunction(() => [...document.querySelectorAll('.out')].some((el) => el.textContent.includes('partial')));
  const output = await resumed.locator('.out').filter({ hasText: 'partial' }).last().textContent();
  assert.match(output, /partial/);
  assert.equal(await resumed.locator('.tag-ok').count(), 0, 'a newly opened page restores an unfinished attempt without marking it complete');
  await context.close();
});

test('学習データの書き出しと読み込み', async () => {
  const { context, page } = await openApp(env.browser, env.url);
  await run(page, 'echo こんにちは');
  await page.waitForSelector('.tag-ok');
  await run(page, 'data');
  const [download] = await Promise.all([page.waitForEvent('download'), page.click('button:has-text("書き出す")')]);
  const file = path.join(os.tmpdir(), 'danganlog-e2e-' + process.pid + '.json');
  await download.saveAs(file);
  assert.equal(JSON.parse(fs.readFileSync(file, 'utf8')).app, 'dangan-log');
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await page.waitForSelector('.rt.ready', { timeout: 120000 });
  assert.match(await progressLine(page, 'はじめての'), /0\/24/);
  await run(page, 'data');
  await page.setInputFiles('.import-button input', file);
  await page.waitForFunction(() => document.querySelector('#data-message').textContent.includes('読み込みました'));
  await page.click('button[aria-label="閉じる"]');
  assert.match(await progressLine(page, 'はじめての'), /1\/24/);
  fs.unlinkSync(file);
  await context.close();
});

test('Windows・Mac両方のLinux環境ガイドと練習経路を確認できる', async () => {
  const page = await env.browser.newPage();
  await page.goto(env.url + '/course/real-linux/');
  await page.waitForSelector('h1');
  assert.match(await page.locator('main').textContent(), /WSL 2 と Ubuntu/);
  assert.match(await page.locator('main').textContent(), /wsl --install/);
  assert.match(await page.locator('main').textContent(), /UTMでUbuntuを仮想マシンに入れる/);
  assert.match(await page.locator('main').textContent(), /ターミナルを開く/);
  assert.match(await page.locator('main').textContent(), /PowerShell/);
  assert.match(await page.locator('main').textContent(), /Command \+ Space/);
  assert.match(await page.locator('main').textContent(), /uname -s/);
  assert.match(await page.locator('main').textContent(), /専用VM/);
  assert.ok(await page.locator('a[href="/course/"]').count());
  assert.equal(await page.getByRole('link', { name: '環境の準備' }).count(), 1);
  await page.setViewportSize({ width: 320, height: 740 });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'environment guide fits a narrow screen');
  await page.close();
});

test('総合復習 (festival) モード: 課題が出て、check の失敗でも課題は残る', async () => {
  const { context, page } = await openApp(env.browser, env.url);
  await run(page, 'modes'); await run(page, '5');
  await page.waitForFunction(() => document.querySelector('#lesson-title').textContent.includes('引き継ぎ'));
  const task = await page.textContent('#mission-text');
  await run(page, 'check');
  await page.waitForSelector('.entry');
  assert.equal(await page.textContent('#mission-text'), task);
  await context.close();
});

test('CDN を使わない: ネットワークを遮断しても (自サイト以外はすべて拒否) 動く', async () => {
  const external = [];
  const context = await env.browser.newContext({ viewport: { width: 1280, height: 720 } });
  await context.route('**/*', (route) => {
    const u = new URL(route.request().url());
    if (u.hostname === '127.0.0.1' || u.protocol === 'data:' || u.protocol === 'blob:') return route.continue();
    external.push(u.href); return route.abort();
  });
  const page = await context.newPage();
  await page.goto(env.url);
  await page.waitForSelector('.rt.ready', { timeout: 120000 });
  await run(page, 'echo こんにちは');
  await page.waitForSelector('.tag-ok');
  assert.deepEqual(external, []);
  await context.close();
});

test('読み込みの進み具合の表示と、失敗時の再試行', async () => {
  const context = await env.browser.newContext({ viewport: { width: 1280, height: 720 } });
  let block = true;
  await context.route('**/pyodide.asm.wasm', (route) => (block ? route.abort() : route.continue()));
  const page = await context.newPage();
  await page.goto(env.url);
  assert.ok(await page.locator('[role=progressbar][aria-label="実行環境の読み込み"], .runtime-notice').first().waitFor({ timeout: 30000 }).then(() => true));
  await page.waitForSelector('.runtime-notice');
  assert.ok(await page.locator('button:has-text("再試行")').isVisible());
  block = false;
  await page.click('button:has-text("再試行")');
  await page.waitForSelector('.rt.ready', { timeout: 120000 });
  await context.close();
});

for (const [w, h] of [[1280, 720], [1366, 768], [375, 667]]) {
  test(`画面固定 ${w}x${h}: ページはスクロールせず、誤答のあとも課題が画面内にある`, async () => {
    const { context, page } = await openApp(env.browser, env.url, { viewport: { width: w, height: h } });
    await run(page, 'zzz');
    await page.waitForSelector('.tag-ng');
    const m = await page.evaluate(() => ({ sh: document.scrollingElement.scrollHeight, ih: innerHeight, sw: document.scrollingElement.scrollWidth, iw: innerWidth }));
    assert.ok(m.sh <= m.ih, `scrollHeight ${m.sh} > ${m.ih}`);
    assert.ok(m.sw <= m.iw, 'horizontal scroll');
    const box = await page.locator('#mission-text').boundingBox();
    assert.ok(box && box.y >= 0 && box.y + box.height <= h, 'mission out of viewport');
    const input = await page.locator('#terminal-input').boundingBox();
    assert.ok(input.y + input.height <= h, 'prompt out of viewport');
    await context.close();
  });
}

test('スクリーンショット (375 / 1280, ライト / ダーク)', async () => {
  fs.mkdirSync(SHOT_DIR, { recursive: true });
  for (const [w, h] of [[375, 667], [1280, 720]]) for (const scheme of ['light', 'dark']) {
    const { context, page } = await openApp(env.browser, env.url, { viewport: { width: w, height: h }, colorScheme: scheme });
    await run(page, 'zzz'); await page.waitForSelector('.tag-ng');
    await page.screenshot({ path: path.join(SHOT_DIR, `e2e-${w}-${scheme}.png`) });
    await context.close();
  }
});

test('キーボードだけで操作できる (Tab 移動・コマンド・Tab 補完・Esc)', async () => {
  const { context, page } = await openApp(env.browser, env.url);
  await page.evaluate(() => document.activeElement && document.activeElement.blur());
  let reached = false;
  for (let i = 0; i < 80 && !reached; i++) { await page.keyboard.press('Tab'); reached = await page.evaluate(() => document.activeElement.id === 'terminal-input'); }
  assert.ok(reached, '入力欄へ Tab で到達できる');
  const ring = await page.evaluate(() => getComputedStyle(document.activeElement.parentElement).boxShadow);
  assert.notEqual(ring.trim(), 'none');
  await page.keyboard.type('completion on'); await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelector('.term-out').textContent.includes('Tab 補完を入れました'));
  await page.keyboard.type('hel'); await page.keyboard.press('Tab');
  await page.waitForFunction(() => document.querySelector('#terminal-input').value.trim() === 'help');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelector('.term-out').textContent.includes('completion'));
  await page.keyboard.type('hint'); await page.keyboard.press('Enter');
  await page.waitForSelector('.tag-hint');
  await page.keyboard.type('modes'); await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelector('.term-out').textContent.includes('総合復習'));
  await page.keyboard.type('goto 2'); await page.keyboard.press('Enter');
  await page.waitForFunction(() => !document.querySelector('#lesson-title').textContent.includes('お願いする'));
  await page.keyboard.type('theme light'); await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.documentElement.getAttribute('data-theme') === 'light');
  await context.close();
});

for (const scheme of ['dark', 'light']) for (const [w, h] of [[1280, 720], [375, 667]]) {
  test(`axe アクセシビリティ ${scheme} ${w}px: serious / critical が 0`, async () => {
    const { context, page } = await openApp(env.browser, env.url, { viewport: { width: w, height: h }, colorScheme: scheme });
    await run(page, 'zzz'); await page.waitForSelector('.tag-ng');
    const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'best-practice']).analyze();
    const bad = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
    assert.deepEqual(bad.map((v) => v.id + ': ' + v.nodes.slice(0, 3).map((n) => n.html.slice(0, 90)).join(' | ')), []);
    await context.close();
  });
}

test('ls は本物のファイル一覧として動く (道場のメニューに横取りされない) → 課題が達成になる', async () => {
  const { context, page } = await openApp(env.browser, env.url);
  await page.waitForFunction(() => document.querySelector('#lesson-title').textContent.includes('お願いする'));
  await run(page, 'goto 4');
  await page.waitForFunction(() => document.querySelector('#lesson-title').textContent.includes('今あるものを一覧'));
  await run(page, 'ls');
  await page.waitForSelector('.tag-ok');
  const out = await page.textContent('.term-out');
  assert.ok(out.includes('welcome.txt'), 'ls の出力にファイル名が出る');
  assert.ok(!out.includes('[x]') && !out.includes('番号を入力すると開きます'), 'レッスン一覧は出ない');
  await context.close();
});

test('Tab 補完は初期で切 (打つ練習のため)。切のあいだ Tab は補完せず、入力は変わらない', async () => {
  const { context, page } = await openApp(env.browser, env.url);
  await page.waitForFunction(() => document.querySelector('#lesson-title').textContent.includes('お願いする'));
  await page.focus('#terminal-input');
  await page.keyboard.type('cat wel'); await page.keyboard.press('Tab');
  await page.waitForTimeout(500);
  assert.equal(await page.inputValue('#terminal-input'), 'cat wel');
  assert.equal(await page.locator('.kbtn', { hasText: /^Tab$/ }).count(), 0, '切のときは Tab ボタンを出さない');
  await context.close();
});

test('Tab 補完を入れると、コマンド名・ファイル名・隠しファイルを補完し、設定は再読み込み後も残る', async () => {
  const { context, page } = await openApp(env.browser, env.url);
  await page.waitForFunction(() => document.querySelector('#lesson-title').textContent.includes('お願いする'));
  await run(page, 'completion on');
  await page.focus('#terminal-input');
  await page.keyboard.type('ec'); await page.keyboard.press('Tab');
  await page.waitForFunction(() => document.querySelector('#terminal-input').value === 'echo ');
  await page.fill('#terminal-input', 'cat wel'); await page.keyboard.press('Tab');
  await page.waitForFunction(() => document.querySelector('#terminal-input').value === 'cat welcome.txt ');
  await page.fill('#terminal-input', 'cat .m'); await page.keyboard.press('Tab');
  await page.waitForFunction(() => document.querySelector('#terminal-input').value === 'cat .memo ');
  await page.fill('#terminal-input', 'c'); await page.keyboard.press('Tab');
  await page.waitForFunction(() => /cat\s+cd/.test(document.querySelector('.term-out').textContent), null, { timeout: 5000 });
  assert.equal(await page.inputValue('#terminal-input'), 'c');
  await page.reload();
  await page.waitForSelector('.rt.ready', { timeout: 120000 });
  assert.equal(await page.locator('.foot button[aria-pressed="true"]', { hasText: 'Tab補完' }).count(), 1);
  await context.close();
});

test('学習データ画面: 好きな課題から開始・コース初期化・全データ初期化', async () => {
  const { context, page } = await openApp(env.browser, env.url);
  page.on('dialog', (d) => d.accept());
  await run(page, 'echo こんにちは');
  await page.waitForSelector('.tag-ok');
  assert.match(await progressLine(page, 'はじめての'), /1\/24/);

  // 好きな課題から始める
  await run(page, 'data');
  await page.fill('dialog input[type=number]', '5');
  await page.click('text=ここから始める');
  await page.waitForFunction(() => document.querySelector('#lesson-title').textContent.includes('ファイルの中を読む'));

  // このコースを初期化 (他コースは残る確認のため、先に基礎コースも1問達成)
  await run(page, 'modes'); await run(page, '2');
  await page.waitForFunction(() => document.querySelector('.motd').textContent.includes('基本コマンド'));
  await run(page, 'data');
  await page.click('text=このコースを初期化');
  await page.waitForSelector('.tag-ok');
  await page.waitForFunction(() => document.querySelector('#lesson-title').textContent.length > 0);
  assert.match(await progressLine(page, 'はじめての'), /1\/24/);

  // 全データ初期化
  await run(page, 'data');
  await page.click('text=全データを初期化');
  await page.waitForFunction(() => document.querySelector('#lesson-title').textContent.includes('お願いする'));
  assert.match(await progressLine(page, 'はじめての'), /\b0\/24/);
  await page.reload();
  await page.waitForSelector('.rt.ready', { timeout: 120000 });
  assert.match(await progressLine(page, 'はじめての'), /\b0\/24/);
  await context.close();
});
