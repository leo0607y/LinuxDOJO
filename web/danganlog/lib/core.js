/* 画面に依存しない学習ロジック。worker.js との要求・応答の対応づけ、保存、履歴、コース一覧の組み立て。 */
var STORAGE_KEY = 'dangan-log:state:v1';
var HISTORY_KEY = 'dangan-log:history:v1';

var COURSES = {
  intro: { name: 'はじめてのLinux', description: 'ターミナルへの最初の一文字から、ひとつずつ。' },
  basic: { name: '基本コマンド', description: '移動・作成・検索・編集。毎日使う道具を手になじませる。' },
  advanced: { name: '現場で使う技', description: 'パイプ、正規表現、権限。組み合わせて使いこなす。' },
  expert: { name: 'テーマ別の実践', description: 'ネットワーク、ユーザー管理、Git など分野ごとに深める。' },
  festival: { name: '総合復習・課題まつり', description: '目的だけが示される課題。自分で組み立てて check で判定。' }
};
var COURSE_ORDER = ['intro', 'basic', 'advanced', 'expert', 'festival'];

function pad2(n) { return String(n).padStart(2, '0'); }

function safeStorage(win) {
  return {
    get: function (key) { try { return win.localStorage.getItem(key); } catch (e) { return null; } },
    set: function (key, value) { try { win.localStorage.setItem(key, value); return true; } catch (e) { return false; } },
    remove: function (key) { try { win.localStorage.removeItem(key); } catch (e) { /* 保存できない環境 */ } }
  };
}

function loadSavedState(storage) {
var raw = storage.get(STORAGE_KEY);
  if (!raw) return null;
  try {
    var data = JSON.parse(raw);
    if (data && data.v === 1 && data.state && data.state.version === 1) return data.state;
  } catch (e) { /* 壊れた保存データは捨てる */ }
  storage.remove(STORAGE_KEY);
  return null;
}

function saveState(storage, state) {
  return storage.set(STORAGE_KEY, JSON.stringify({ v: 1, state: state }));
}

function createHistory(initial, limit) {
var items = Array.isArray(initial) ? initial.filter(function (s) { return typeof s === 'string'; }) : [];
var max = limit || 100;
var pos = items.length;
var draft = '';
  return {
    items: function () { return items.slice(); },
    push: function (line) {
      if (line.trim() && items[items.length - 1] !== line) items.push(line);
      if (items.length > max) items.splice(0, items.length - max);
      pos = items.length; draft = '';
    },
    up: function (current) {
      if (!items.length) return null;
      if (pos === items.length) draft = current;
      if (pos > 0) pos -= 1;
      return items[pos];
    },
    down: function () {
      if (pos >= items.length) return null;
      pos += 1;
      return pos === items.length ? draft : items[pos];
    }
  };
}

function isDone(state, mode, id) {
var completed = (state && state.completed) || {};
  if (mode === 'festival') return !!(completed.festival && Object.prototype.hasOwnProperty.call(completed.festival, id));
  return Array.isArray(completed[mode]) && completed[mode].indexOf(id) !== -1;
}

function buildCourses(catalog, state) {
var byMode = {};
  (catalog.modes || []).forEach(function (m) { byMode[m.id] = m; });
var courses = [];
  COURSE_ORDER.forEach(function (id) {
    var items;
    var name;
    if (id === 'festival') {
      items = (catalog.scenarios || []).map(function (s, i) { return { index: i, id: s.id, title: s.title, unit: s.pack || '' }; });
      name = COURSES.festival.name;
    } else if (byMode[id]) {
      items = byMode[id].lessons.map(function (l, i) { return { index: i, id: l.id, title: l.title, unit: l.unit || '' }; });
      name = COURSES[id].name;
    } else {
      return;
    }
    items.forEach(function (item) { item.done = isDone(state, id, item.id); });
    courses.push({
      id: id, name: name, description: COURSES[id].description, items: items,
      total: items.length, done: items.filter(function (i) { return i.done; }).length
    });
  });
  return courses;
}

function firstOpenIndex(course) {
  for (var i = 0; i < course.items.length; i++) if (!course.items[i].done) return i;
  return 0;
}

function filterItems(items, query, unit) {
var q = (query || '').trim().toLowerCase();
  return items.filter(function (item) {
    if (unit && item.unit !== unit) return false;
    return !q || (item.title + ' ' + item.unit + ' ' + item.id).toLowerCase().indexOf(q) !== -1;
  });
}

function lastLine(message) {
var lines = String(message || '').trim().split('\n').filter(Boolean);
  return lines.length ? lines[lines.length - 1] : '不明なエラー';
}

/* 実行結果から、課題欄の下に出すメッセージを決める。課題文そのものは変えない。 */
function feedbackFor(view, wasDone) {
  if (view.completed && !wasDone) return { kind: 'ok', text: '達成です。次のレッスンへ進めます。' };
  if (view.completed) return { kind: 'ok', text: '達成済みのレッスンです。' };
  if (view.code && view.code !== 0) return { kind: 'ng', text: 'まだ達成していません。課題をもう一度読んで、別の入力を試してみましょう。ヒントも使えます。' };
  return { kind: 'info', text: '' };
}

/* worker との要求・応答の対応づけ。makeWorker はテストでは偽物に差し替える。 */
function createClient(makeWorker, timeoutMs, onProgress) {
var worker = null;
var seq = 0;
var pending = {};
  function failAll(error) {
    var all = pending; pending = {};
    Object.keys(all).forEach(function (id) { clearTimeout(all[id].timer); all[id].reject(error); });
  }
  function start() {
    worker = makeWorker();
    worker.onmessage = function (event) {
      var data = event.data || {};
      if (data.progress && onProgress) { onProgress(data.progress); return; }
      if (data.fatal) { failAll(new Error(data.fatal)); return; }
      var entry = pending[data.id];
      if (!entry) return;
      delete pending[data.id];
      clearTimeout(entry.timer);
      if (data.ok) entry.resolve(data.result); else entry.reject(new Error(data.error || '実行に失敗しました。'));
    };
    worker.onerror = function (event) {
      failAll(new Error((event && event.message) || '実行環境の読み込みに失敗しました。'));
    };
  }
  start();
  return {
    request: function (payload) {
      return new Promise(function (resolve, reject) {
        var id = ++seq;
        var timer = setTimeout(function () {
          delete pending[id];
          reject(new Error('応答がありません。時間をおいて再読み込みしてください。'));
        }, timeoutMs || 180000);
        pending[id] = { resolve: resolve, reject: reject, timer: timer };
        try { worker.postMessage(Object.assign({}, payload, { id: id })); } catch (e) { delete pending[id]; clearTimeout(timer); reject(e); }
      });
    },
    restart: function () {
      failAll(new Error('再読み込みしました。'));
      try { worker.terminate(); } catch (e) { /* すでに停止 */ }
      start();
    }
  };
}

export { STORAGE_KEY, HISTORY_KEY, COURSE_ORDER, COURSES, safeStorage, loadSavedState, saveState, createHistory,
  buildCourses, firstOpenIndex, filterItems, feedbackFor, createClient, isDone, lastLine, pad2 };
