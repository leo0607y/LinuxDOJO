import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { searchEntries } from '../lib/course-search.js';
import { buildCourseData } from '../scripts/build-course.mjs';

const file = new URL('../public/course-data.json', import.meta.url);
if (!existsSync(file)) buildCourseData();
const data = JSON.parse(readFileSync(file, 'utf8'));

test('32 topics with goals, and every topic has a goal text', () => {
  assert.equal(data.topics.length, 32);
  for (const t of data.topics) assert.ok(t.goal.length > 10, t.id);
});

test('search finds Japanese purposes and command names', () => {
  const e = data.search;
  assert.equal(searchEntries(e, '圧縮 展開')[0].id, 'archive');
  assert.ok(searchEntries(e, '読めない').some((x) => x.id === 'permissions'));
  assert.equal(searchEntries(e, 'curl')[0].id, 'http');
  assert.deepEqual(searchEntries(e, ''), []);
  assert.deepEqual(searchEntries(e, 'zzzz存在しない語'), []);
});

test('status badges are honest: unverified VM modules are never labelled verified', () => {
  for (const t of data.topics) for (const v of t.vm) {
    if (['users', 'netconfig', 'firewall', 'restore', 'osupdate'].includes(v.id)) assert.match(v.status, /実VM未実施/);
    assert.doesNotMatch(v.status, /^ネイティブ/);
  }
});

test('coverage totals add up and no emoji in data', () => {
  const { exams, total } = data.coverage;
  for (const k of ['rows', 'covered', 'partial', 'missing']) assert.equal(exams.reduce((a, e) => a + e[k], 0), total[k]);
  assert.equal(total.covered + total.partial + total.missing, total.rows);
  assert.doesNotMatch(JSON.stringify(data), /[\u{1F000}-\u{1FAFF}\u2705\u274C\u2728]/u);
});
