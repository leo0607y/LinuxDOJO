// 画面に依存しない lib/core.js の確認 (偽の worker を使う)。
import test from 'node:test';
import assert from 'node:assert/strict';
import * as core from '../lib/core.js';

class FakeWorker {
  constructor(handler) { this.handler = handler; this.terminated = false; }
  postMessage(msg) { Promise.resolve().then(() => this.onmessage({ data: this.handler(msg) })); }
  terminate() { this.terminated = true; }
}

test('client resolves and rejects by id', async () => {
  const client = core.createClient(() => new FakeWorker((m) => (m.type === 'bad' ? { id: m.id, ok: false, error: 'boom' } : { id: m.id, ok: true, result: { echo: m.type } })));
  assert.deepEqual(await client.request({ type: 'init' }), { echo: 'init' });
  await assert.rejects(client.request({ type: 'bad' }), /boom/);
});

test('client rejects pending requests when the worker errors, and restarts', async () => {
  let worker;
  const client = core.createClient(() => (worker = new FakeWorker(() => ({ id: -1 }))), 5000);
  const p = client.request({ type: 'init' });
  worker.onerror({ message: 'network' });
  await assert.rejects(p, /network/);
  const old = worker;
  client.restart();
  assert.ok(old.terminated);
  assert.notEqual(worker, old);
});

test('request times out', async () => {
  const client = core.createClient(() => new FakeWorker(() => ({ id: -1 })), 20);
  await assert.rejects(client.request({ type: 'init' }), /応答がありません/);
});

test('history navigation keeps the draft', () => {
  const h = core.createHistory(['a', 'b']);
  assert.equal(h.up('draft'), 'b');
  assert.equal(h.up('x'), 'a');
  assert.equal(h.up('x'), 'a');
  assert.equal(h.down(), 'b');
  assert.equal(h.down(), 'draft');
  assert.equal(h.down(), null);
  h.push('b'); h.push('   '); h.push('c');
  assert.deepEqual(h.items(), ['a', 'b', 'c']);
});

test('storage tolerates failures and corrupt data', () => {
  const broken = core.safeStorage({ get localStorage() { throw new Error('denied'); } });
  assert.equal(broken.get('k'), null);
  assert.equal(broken.set('k', 'v'), false);
  const mem = {}; const win = { localStorage: { getItem: (k) => mem[k] ?? null, setItem: (k, v) => { mem[k] = v; }, removeItem: (k) => { delete mem[k]; } } };
  const s = core.safeStorage(win);
  mem[core.STORAGE_KEY] = '{not json';
  assert.equal(core.loadSavedState(s), null);
  assert.equal(mem[core.STORAGE_KEY], undefined);
  core.saveState(s, { version: 1, sessions: {} });
  assert.deepEqual(core.loadSavedState(s), { version: 1, sessions: {} });
});

test('courses, progress and feedback', () => {
  const catalog = { modes: [{ id: 'intro', lessons: [{ id: 'i1', title: 'A', unit: 'u' }, { id: 'i2', title: 'B', unit: 'v' }] }], scenarios: [{ id: 's1', title: 'S', pack: 'p' }] };
  const courses = core.buildCourses(catalog, { completed: { intro: ['i1'], festival: { s1: {} } } });
  assert.deepEqual(courses.map((c) => [c.id, c.done, c.total]), [['intro', 1, 2], ['festival', 1, 1]]);
  assert.equal(core.firstOpenIndex(courses[0]), 1);
  assert.equal(core.filterItems(courses[0].items, 'b', '').length, 1);
  assert.equal(core.filterItems(courses[0].items, '', 'u').length, 1);
  assert.equal(core.feedbackFor({ completed: true }, false).kind, 'ok');
  assert.equal(core.feedbackFor({ completed: false, code: 1 }, false).kind, 'ng');
  assert.equal(core.feedbackFor({ completed: false, code: 0 }, false).text, '');
});
