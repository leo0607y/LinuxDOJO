// 実際の Pyodide で public/worker.js を動かし、レッスンを最後まで通す確認。
// 事前に `npm ci && npm run prepare-assets` が必要。無ければ skip する。
import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const pyodideDir = join(root, 'node_modules', 'pyodide');
const sourceFile = join(root, 'public', 'python-source.json');
const skip = !existsSync(join(pyodideDir, 'pyodide.js')) || !existsSync(sourceFile);

function startWorker() {
  const require = createRequire(import.meta.url);
  const replies = new Map();
  const context = { console, URL, JSON, Promise, setTimeout, clearTimeout, TextDecoder, TextEncoder };
  context.self = context;
  context.location = { href: pathToFileURL(join(root, 'public', 'worker.js')).href };
  context.postMessage = (m) => replies.get(m.id)(m);
  context.importScripts = () => { context.loadPyodide = (o) => require(join(pyodideDir, 'pyodide.js')).loadPyodide({ ...o, indexURL: pyodideDir + '/' }); };
  context.fetch = async () => ({ ok: true, json: async () => JSON.parse(readFileSync(sourceFile, 'utf8')) });
  vm.createContext(context);
  vm.runInContext(readFileSync(join(root, 'public', 'worker.js'), 'utf8'), context);
  let seq = 0;
  return (payload) => new Promise((resolve) => {
    const id = ++seq; replies.set(id, resolve);
    context.onmessage({ data: { ...payload, id } });
  });
}

test('worker: init, select, wrong answer, hint, correct answer, export/import', { skip, timeout: 300000 }, async () => {
  const send = startWorker();
  const init = await send({ type: 'init' });
  assert.ok(init.ok, init.error);
  const modes = init.result.catalog.modes;
  assert.deepEqual(modes.map((m) => m.id), ['intro', 'basic', 'advanced', 'expert']);
  assert.ok(init.result.catalog.scenarios.length > 100);

  const sel = await send({ type: 'select', mode: 'intro', index: 0 });
  assert.ok(sel.ok, sel.error);
  assert.ok(sel.result.lesson.task);
  const answer = await send({ type: 'answer' });
  assert.ok(answer.result.output.length > 0);
  const command = answer.result.output.split('\n')[0];

  const wrong = await send({ type: 'execute', line: 'zzz-not-a-command' });
  assert.ok(wrong.ok, wrong.error);
  assert.equal(wrong.result.completed, false);
  assert.ok(wrong.result.lesson.task, 'task stays visible after a wrong answer');

  const hint = await send({ type: 'hint' });
  assert.ok(hint.result.output);

  const right = await send({ type: 'execute', line: command });
  assert.ok(right.ok, right.error);
  assert.equal(right.result.completed, true, JSON.stringify(right.result.output));
  assert.ok(right.result.state.completed.intro.length >= 1);

  const exported = await send({ type: 'export' });
  const imported = await send({ type: 'import', state: exported.result.state });
  assert.ok(imported.ok, imported.error);
  assert.equal(imported.result.lesson.id, sel.result.lesson.id);

  const fest = await send({ type: 'select', mode: 'festival', index: 0 });
  assert.ok(fest.ok, fest.error);
  assert.ok(fest.result.lesson.task);
});
