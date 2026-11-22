'use client';
/* 学習画面全体。worker.js (Pyodide) との通信と保存はここだけで行う。 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  HISTORY_KEY, STORAGE_KEY, buildCourses, createClient, createHistory, feedbackFor, filterItems,
  firstOpenIndex, lastLine, loadSavedState, pad2, safeStorage, saveState
} from '../lib/core.js';

import Masthead from './Masthead.jsx';
import { applyTheme, readPrefs, savePrefs } from './preferences.js';

const MAX_ENTRIES = 200;
const STARTER_COMMANDS = [['hint', '課題のヒント'], ['answer', '入力例を見る'], ['menu', '問題一覧を開く']];
const LOCAL_COMMANDS = ['help', 'hint', 'answer', 'next', 'prev', 'menu', 'modes', 'progress', 'goto', 'theme', 'simple', 'clear', 'data', 'course', 'reset', 'check'];
const HELP_TEXT = [
  'help           このヘルプ',
  'hint           ヒントを1つ (何度でも可。減点なし)',
  'answer         入力例を表示',
  'next / prev    次 / 前のレッスン (next は達成後)',
  'menu [語]      レッスンの一覧。番号を入力すると開く',
  'modes          コースの一覧。番号を入力すると開く',
  'goto N         このコースの N 番へ',
  'progress       進み具合',
  'reset          課題を初期状態に戻す',
  'theme          dark / light 切り替え (theme auto で端末の設定に従う)',
  'simple         シンプル表示 (大きな文字とボタン)',
  'data           学習データの書き出し・読み込み',
  'course         講座ページへ',
  'clear          画面を消す (Ctrl-L)',
  '',
  'Tab で補完、上下キーで入力履歴。レッスンの答えは、ふつうのコマンドとして入力します。'
].join('\n');

function megabytes(n) { return (n / 1048576).toFixed(1); }
function bar(ratio, width) {
  const n = Math.max(0, Math.min(width, Math.round(ratio * width)));
  return '\u2588'.repeat(n) + '\u2591'.repeat(width - n);
}

/* bash の既定 PS1 と同じ配色: 緑の太字 user@host、青の太字 パス、白い $。engine のプロンプト ('練習 learner@dojo-local /home/learner $') を分解する */
function Ps({ prompt }) {
  const m = /^(?:\S+\s+)?(\S+@\S+)\s+(\S+)\s*\$?\s*$/.exec(prompt || '');
  if (!m) return <span className="ps-user">{prompt}</span>;
  const path = m[2] === '/home/learner' ? '~' : m[2].replace(/^\/home\/learner\//, '~/');
  return <span className="ps"><b className="ps-user">{m[1]}</b>:<b className="ps-path">{path}</b>$</span>;
}

/* 出力の行頭にある [OK] [NG] [ヒント] などを色付きのタグにする */
function Lines({ text }) {
  return text.split('\n').map((ln, i) => {
    const m = /^\[(OK|NG|ヒント|ERROR|INFO)\]\s?/.exec(ln);
    return <div className="ln" key={i}>{m ? <span className={'tag tag-' + (m[1] === 'ヒント' ? 'hint' : m[1].toLowerCase())}>[{m[1]}]</span> : null}{m ? ' ' + ln.slice(m[0].length) : ln || '\u00a0'}</div>;
  });
}
let entrySeq = 0;

function friendly(error) {
  return 'うまく実行できませんでした: ' + lastLine(error && error.message);
}

export default function Dojo() {
  const [catalog, setCatalog] = useState(null);
  const [progress, setProgress] = useState(null);
  const [view, setView] = useState(null);
  const [viewMode, setViewMode] = useState('intro');
  const [status, setStatus] = useState('loading');
  const [errorText, setErrorText] = useState('');
  const [busy, setBusy] = useState(false);
  const [entries, setEntries] = useState([]);
  const [dataMessage, setDataMessage] = useState('');
  const [line, setLine] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [loadInfo, setLoadInfo] = useState({ loaded: 0, total: 0 });
  const [theme, setThemeState] = useState('');
  const [simple, setSimpleState] = useState(false);
  const [focused, setFocused] = useState(false);

  const clientRef = useRef(null);
  const storageRef = useRef(null);
  const historyRef = useRef(null);
  const inputRef = useRef(null);
  const outRef = useRef(null);
  const workbenchRef = useRef(null);
  const pendingRef = useRef(null);
  const dataRef = useRef(null);
  const viewRef = useRef(null);
  const catalogRef = useRef(null);
  const stateRef = useRef(null);
  viewRef.current = view;

  const ready = status === 'ready';
  const courses = useMemo(() => (catalog ? buildCourses(catalog, progress) : []), [catalog, progress]);
  const course = courses.find((c) => c.id === viewMode) || courses[0];
  const totalDone = courses.reduce((n, c) => n + c.done, 0);

  const addEntry = useCallback((prompt, command, output, kind) => {
    setEntries((all) => all.concat([{ id: ++entrySeq, prompt, command, output, kind }]).slice(-MAX_ENTRIES));
  }, []);

  useEffect(() => {
    const log = outRef.current;
    const workbench = workbenchRef.current;
    if (log) log.scrollTop = log.scrollHeight;
    if (workbench) workbench.scrollTop = entries.length ? workbench.scrollHeight : 0;
  }, [entries, view]);

  const persist = useCallback((state) => {
    stateRef.current = state;
    setProgress(state);
    if (storageRef.current) saveState(storageRef.current, state);
  }, []);

  const applyView = useCallback((v) => {
    if (v.catalog) { catalogRef.current = v.catalog; setCatalog(v.catalog); }
    if (v.state) persist(v.state);
    if (v.lesson) { setView(v); setViewMode(v.mode); }
  }, [persist]);

  const call = useCallback(async (payload) => {
    setBusy(true);
    try { return await clientRef.current.request(payload); } finally { setBusy(false); }
  }, []);

  const selectLesson = useCallback(async (mode, index) => {
    try {
      const v = await call({ type: 'select', mode, index });
      const first = [];
      if (v.output) first.push({ id: ++entrySeq, prompt: '', command: null, output: v.output });
      if (v.lesson && v.lesson.shownAnswer) first.push({ id: ++entrySeq, prompt: '', command: null, output: '[ヒント] 入力例: ' + v.lesson.shownAnswer });
      setEntries(first);
      applyView(v);
      if (inputRef.current) inputRef.current.focus();
    } catch (error) {
      addEntry('', null, '[NG] ' + friendly(error), '');
    }
  }, [call, applyView]);

  /* 起動: 実行環境の読み込み → 保存データの復元 → 最初のレッスン */
  useEffect(() => {
    const storage = safeStorage(window);
    storageRef.current = storage;
    let initial = [];
    try { initial = JSON.parse(storage.get(HISTORY_KEY) || '[]'); } catch (e) { initial = []; }
    historyRef.current = createHistory(initial);
    const client = createClient(() => new Worker('/worker.js'), 0, (p) => { if (!cancelled) setLoadInfo(p); });
    clientRef.current = client;
    let cancelled = false;
    setStatus('loading');
    setLoadInfo({ loaded: 0, total: 0 });
    setErrorText('');
    (async () => {
      try {
        const first = await client.request({ type: 'init' });
        if (cancelled) return;
        catalogRef.current = first.catalog;
        setCatalog(first.catalog);
        setStatus('ready');
        const saved = loadSavedState(storage);
        let restored = null;
        if (saved) {
          try { restored = await client.request({ type: 'import', state: saved }); } catch (e) {
            storage.remove(STORAGE_KEY);
            setEntries([{ id: ++entrySeq, prompt: '', command: null, output: '[NG] 保存データを読み込めなかったため、最初から始めます。' }]);
          }
        }
        if (cancelled) return;
        if (restored && restored.lesson) {
          setEntries([{ id: ++entrySeq, prompt: '', command: null, output: '前回の続きから再開しました。' }]);
          applyView(restored);
        } else {
          const state = (restored && restored.state) || first.state;
          persist(state);
          const intro = buildCourses(first.catalog, state)[0];
          const v = await client.request({ type: 'select', mode: intro.id, index: firstOpenIndex(intro) });
          if (cancelled) return;
          applyView(v);
        }
      } catch (error) {
        if (cancelled) return;
        setErrorText(lastLine(error && error.message));
        setStatus('error');
      }
    })();
    return () => { cancelled = true; client.terminate && client.terminate(); };
  }, [attempt, applyView, persist]);

  const setTheme = (t) => { setThemeState(t === 'auto' ? '' : t); applyTheme(t === 'auto' ? '' : t); savePrefs({ theme: t === 'auto' ? '' : t }); };
  const effectiveTheme = () => theme || (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
  const setSimple = (v) => { setSimpleState(v); savePrefs({ simple: v }); };

  const say = (kind, text) => addEntry('', null, '[' + kind + '] ' + text, '');
  const total = course ? course.total : 0;

  /* 画面側のコマンド。処理したら true。lesson の答えそのものは engine (worker) に渡す */
  const runLocal = async (raw) => {
    const text = raw.trim();
    const [name, ...args] = text.split(/\s+/);
    const promptShown = (view && view.prompt) || '$';
    const echo = () => addEntry(promptShown, raw, '', '');
    const v0 = viewRef.current;
    const pending = pendingRef.current;
    pendingRef.current = null;
    if (pending && /^\d+$/.test(text)) {
      echo();
      const n = parseInt(text, 10);
      if (pending.kind === 'mode') {
        const c = courses[n - 1];
        if (!c) { say('NG', '1 から ' + courses.length + ' の番号を入力します。'); return true; }
        await selectLesson(c.id, firstOpenIndex(c));
      } else {
        const c = courses.find((x) => x.id === pending.mode);
        if (!c || !(n >= 1 && n <= c.total)) { say('NG', '1 から ' + (c ? c.total : 0) + ' の番号を入力します。'); return true; }
        await selectLesson(c.id, n - 1);
      }
      return true;
    }
    const goto = async (n) => {
      if (!course || !(n >= 1 && n <= total)) { say('NG', '1 から ' + total + ' までの番号を指定します。'); return; }
      await selectLesson(course.id, n - 1);
    };
    switch (name) {
      case 'help': echo(); addEntry('', null, HELP_TEXT, ''); return true;
      case 'clear': setEntries([]); return true;
      case 'theme': {
        echo();
        const a = args[0];
        const next = a === 'dark' || a === 'light' || a === 'auto' ? a : (effectiveTheme() === 'dark' ? 'light' : 'dark');
        setTheme(next); say('OK', 'テーマ: ' + next); return true;
      }
      case 'simple': echo(); setSimple(!simple); say('OK', 'シンプル表示を' + (simple ? '切りました' : '入れました') + '。'); return true;
      case 'data': echo(); openDialog(dataRef); return true;
      case 'course': case 'courses': echo(); say('INFO', '講座ページへ移動します。'); window.location.href = '/course/'; return true;
      case 'modes': case 'mode': {
        echo();
        if (args[0] && /^\d+$/.test(args[0])) {
          const c = courses[parseInt(args[0], 10) - 1];
          if (!c) { say('NG', '1 から ' + courses.length + ' の番号を指定します。'); return true; }
          await selectLesson(c.id, firstOpenIndex(c)); return true;
        }
        addEntry('', null, courses.map((c, i) => pad2(i + 1) + '  ' + (c.id === (course && course.id) ? '>' : ' ') + ' ' + c.name + '  (' + c.done + '/' + c.total + ')').join('\n') + '\n番号を入力すると開きます。', '');
        pendingRef.current = { kind: 'mode' }; return true;
      }
      case 'progress': {
        echo();
        addEntry('', null, courses.map((c) => bar(c.total ? c.done / c.total : 0, 20) + ' ' + String(c.done).padStart(3) + '/' + String(c.total).padEnd(3) + ' ' + c.name).join('\n') + '\n合計 ' + totalDone + ' 達成 (このブラウザーに保存)', '');
        return true;
      }
      case 'menu': case 'ls': case 'lessons': {
        echo();
        if (!course) return true;
        const q = args.join(' ').toLowerCase();
        const rows = course.items.filter((i) => !q || (i.title + ' ' + i.unit).toLowerCase().includes(q));
        if (!rows.length) { say('NG', '該当するレッスンがありません。'); return true; }
        const cur = v0 && v0.mode === course.id ? v0.index : -1;
        addEntry('', null, course.name + ' (' + course.done + '/' + course.total + ')\n' + rows.map((i) => pad2(i.index + 1) + ' ' + (i.index === cur ? '>' : ' ') + (i.done ? '[x] ' : '[ ] ') + i.title + (i.unit ? '  (' + i.unit + ')' : '')).join('\n') + '\n番号を入力すると開きます。menu 語 で絞り込み、modes で別のコース。', '');
        pendingRef.current = { kind: 'lesson', mode: course.id };
        return true;
      }
      case 'goto': case 'open': echo(); await goto(parseInt(args[0], 10)); return true;
      case 'next':
        echo();
        if (v0 && v0.completed && course && v0.index + 1 < total) await selectLesson(v0.mode, v0.index + 1);
        else say('NG', v0 && v0.completed ? 'このコースの最後です。modes で別のコースを選べます。' : 'まだ達成していません。課題を達成すると進めます。(menu で好きなレッスンを開けます)');
        return true;
      case 'prev':
        echo();
        if (v0 && v0.index > 0) await selectLesson(v0.mode, v0.index - 1); else say('NG', 'これが最初のレッスンです。');
        return true;
      case 'hint':
      case 'answer': {
        echo();
        if (!ready || busy) return true;
        try {
          const v = await call({ type: name });
          addEntry('', null, (v.output && /^\[/.test(v.output) ? '' : '[ヒント] ') + (v.output || (name === 'hint' ? 'ヒントはありません。' : '入力例はありません。')), '');
          applyView(v);
        } catch (error) { say('NG', friendly(error)); }
        return true;
      }
      default: return false;
    }
  };

  const submit = async (event) => {
    if (event && event.preventDefault) event.preventDefault();
    const text = line;
    if (!text.trim() || !ready || busy) return;
    setLine('');
    const promptShown = (view && view.prompt) || '$';
    const wasDone = !!(view && view.completed);
    historyRef.current.push(text);
    storageRef.current.set(HISTORY_KEY, JSON.stringify(historyRef.current.items()));
    const first = text.trim().split(/\s+/)[0];
    if (text.trim() !== 'reset' && first !== 'check' && await runLocal(text)) { if (inputRef.current) inputRef.current.focus(); return; }
    pendingRef.current = null;
    try {
      const v = await call({ type: 'execute', line: text });
      const fb = feedbackFor(v, wasDone);
      if (text.trim() === 'reset') setEntries(v.output ? [{ id: ++entrySeq, prompt: '', command: null, output: v.output }] : []);
      else {
        addEntry(promptShown, text, (v.output || '').replace(/\n+$/, ''), v.code ? 'error' : (v.completed && !wasDone ? 'success' : ''));
        if (fb.text && !(v.output || '').includes('[OK]')) addEntry('', null, '[' + (fb.kind === 'ok' ? 'OK' : fb.kind === 'ng' ? 'NG' : 'INFO') + '] ' + fb.text, '');
      }
      applyView(v);
    } catch (error) {
      addEntry(promptShown, text, friendly(error), 'error');
    }
    if (inputRef.current) inputRef.current.focus();
  };

  const complete = () => {
    if (!line || /\s/.test(line)) return false;
    const hits = LOCAL_COMMANDS.filter((c) => c.startsWith(line));
    if (!hits.length) return false;
    if (hits.length === 1) setLine(hits[0] + ' ');
    else {
      let p = hits[0];
      hits.forEach((c) => { while (!c.startsWith(p)) p = p.slice(0, -1); });
      setLine(p);
      addEntry('', null, hits.join('  '), '');
    }
    return true;
  };
  const historyStep = (dir) => {
    const h = historyRef.current;
    const v = dir < 0 ? h.up(line) : h.down();
    if (v !== null) setLine(v);
    return v !== null;
  };

  const onKey = (event) => {
    if (event.key === 'ArrowUp') { if (historyStep(-1)) event.preventDefault(); }
    else if (event.key === 'ArrowDown') { if (historyStep(1)) event.preventDefault(); }
    else if (event.key === 'l' && event.ctrlKey) { event.preventDefault(); setEntries([]); }
    else if (event.key === 'Tab' && !event.shiftKey) { if (complete()) event.preventDefault(); }
  };

  const exportData = async () => {
    if (!ready) { setDataMessage('実行環境の準備ができてから書き出してください。'); return; }
    try {
      const result = await clientRef.current.request({ type: 'export' });
      const blob = new Blob([JSON.stringify({ app: 'dangan-log', state: result.state })], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = 'dangan-log-progress.json';
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setDataMessage('学習データを書き出しました。');
    } catch (error) { setDataMessage(friendly(error)); }
  };

  const importData = async (event) => {
    const input = event.target;
    const file = input.files && input.files[0];
    if (!file) return;
    if (!ready) { setDataMessage('実行環境の準備ができてから読み込んでください。'); input.value = ''; return; }
    if (file.size > 80 * 1024 * 1024) { setDataMessage('ファイルが大きすぎます。'); input.value = ''; return; }
    try {
      const data = JSON.parse(await file.text());
      const v = await call({ type: 'import', state: data.state || data });
      setEntries([{ id: ++entrySeq, prompt: '', command: null, output: '[OK] 保存データを読み込みました。' }]);
      applyView(v);
      setDataMessage('読み込みました。');
      if (!v.lesson && catalogRef.current) {
        const c = buildCourses(catalogRef.current, v.state)[0];
        selectLesson(c.id, firstOpenIndex(c));
      }
    } catch (error) {
      setDataMessage('読み込めませんでした。' + lastLine(error && error.message));
    }
    input.value = '';
  };

  const openDialog = (ref) => { const d = ref.current; if (d) { if (d.showModal) d.showModal(); else d.setAttribute('open', ''); } };
  const closeDialog = (ref) => { const d = ref.current; if (d) { if (d.close) d.close(); else d.removeAttribute('open'); } };

  /* 画面固定: この画面だけ body のスクロールを止め、高さは visualViewport (ソフトキーボードを除いた高さ) に合わせる */
  useEffect(() => {
    const root = document.documentElement;
    root.classList.add('app-lock');
    const vv = window.visualViewport;
    const fit = () => {
      root.style.setProperty('--app-h', (vv ? vv.height : window.innerHeight) + 'px');
      if (vv && vv.offsetTop) window.scrollTo(0, 0);
    };
    fit();
    if (vv) { vv.addEventListener('resize', fit); vv.addEventListener('scroll', fit); }
    window.addEventListener('resize', fit);
    return () => {
      root.classList.remove('app-lock'); root.style.removeProperty('--app-h');
      if (vv) { vv.removeEventListener('resize', fit); vv.removeEventListener('scroll', fit); }
      window.removeEventListener('resize', fit);
    };
  }, []);

  useEffect(() => {
    const p = readPrefs();
    if (p.theme === 'dark' || p.theme === 'light') setThemeState(p.theme);
    if (p.simple) setSimpleState(true);
  }, []);

  /* 実行中に無効化された入力欄は、有効に戻ったとき、操作中なら自動で戻す (キーボードだけでも続けて入力できる) */
  const off = busy || !ready;
  useEffect(() => {
    if (!off && inputRef.current && (document.activeElement === document.body || document.activeElement === null || document.activeElement === inputRef.current)) inputRef.current.focus();
  }, [off]);

  const lesson = view && view.lesson;
  const pct = loadInfo.total ? Math.min(99, Math.floor(loadInfo.loaded * 100 / loadInfo.total)) : 0;
  const lessonNo = view ? pad2(view.index + 1) : '--';
  const hasNext = !!(view && view.completed && course && view.index + 1 < total);
  const hasPrev = !!(view && view.index > 0);
  const act = (cmd) => () => runLocal(cmd);

  return (
    <div className={'tw' + (simple ? ' simple' : '')}>
      <Masthead />
      <main className="screen">
        <div className="workbench" ref={workbenchRef} tabIndex={0} aria-label="レッスンの説明と出力">
          <section className="motd" aria-labelledby="lesson-title" key={viewMode + lessonNo} tabIndex={0}>
            <p className="lesson-meta"><span>問題 <b>{lessonNo}</b>{course && ' / ' + pad2(course.total)}</span>{course?.name}</p>
            <h1 id="lesson-title">{lesson ? lesson.title : 'Linux 道場'}</h1>
            <div className="motd-text">{(lesson ? lesson.explanation : 'ブラウザー内の模擬環境です。実際のPCは変更しません。help で使い方、Tab で補完できます。').split('\n').filter(Boolean).map((line, i) => <p key={i}>{line}</p>)}</div>
            {course && <div className="course-progress">
              <label htmlFor="lesson-progress">コースの達成数 <b>{course.done} / {course.total}</b></label>
              <progress id="lesson-progress" value={course.done} max={course.total} />
            </div>}
          </section>
          <section className="console" aria-labelledby="console-title">
            <div className="console-tools">
              <h2 id="console-title">Linux コマンドを試す</h2>
              {!simple && <button className="help-button" type="button" disabled={off} onClick={act('help')}>操作ヘルプ</button>}
            </div>
            {!simple && ready && lesson && !entries.length && <div className="starter-commands">
              <p>困ったときの操作 <span>Linux コマンドではなく、道場の機能です</span></p>
              {STARTER_COMMANDS.map(([command, label]) => (
                <button key={command} type="button" disabled={off} onClick={() => { inputRef.current?.focus(); runLocal(command); }}>
                  <code>{command}</code><span>{label}</span>
                </button>
              ))}
            </div>}
            <div className="term-out" ref={outRef} role="log" aria-live="polite" aria-relevant="additions" aria-label="ターミナルの出力" tabIndex={0}>
          {status === 'loading' ? (
            <div className="boot">
              <div><Ps prompt="learner@danganlog ~" /> boot pyodide --self-hosted</div>
              <div role="progressbar" aria-label="実行環境の読み込み" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
                [{bar(pct / 100, 24)}] {pct}%{loadInfo.total ? '  ' + megabytes(loadInfo.loaded) + ' / ' + megabytes(loadInfo.total) + ' MB' : ''}
              </div>
              <div className="dim">初回だけ約15MBを読み込みます。2回目以降はブラウザーに残ります。</div>
            </div>
          ) : null}
          {status === 'error' ? (
            <div className="runtime-notice" role="alert">
              <div><span className="tag tag-ng">[NG]</span> 実行環境を読み込めませんでした。ネットワークを確認して再試行してください。</div>
              <div className="dim">詳細: {errorText}</div>
              <button type="button" className="kbtn" onClick={() => setAttempt(attempt + 1)}>再試行</button>
            </div>
          ) : null}
          {entries.map((e) => (
            <div className={'entry' + (e.kind ? ' ' + e.kind : '')} key={e.id}>
              {e.command !== null ? <div className="cmdline"><Ps prompt={e.prompt} /> {e.command}</div> : null}
              {e.output ? <div className="out"><Lines text={e.output} /></div> : null}
            </div>
          ))}
          {view && view.editor ? <pre className="out editor" aria-label="エディターの表示">{view.editor}</pre> : null}
            </div>
          </section>
        </div>
        <div className="mission"><span className="mission-label">今回の課題</span><span id="mission-text">{lesson ? lesson.task : '準備ができると課題が表示されます。'}</span></div>
        <form className="prompt" onSubmit={submit} autoComplete="off" aria-busy={busy}>
          <label htmlFor="terminal-input" className="ps"><Ps prompt={(view && view.prompt) || 'learner@danganlog ~'} /></label>
          <span className="field">
            {ready && !busy && !line && focused ? <span className="caret" aria-hidden="true"></span> : null}
            <input id="terminal-input" ref={inputRef} name="command" value={line} onChange={(e) => setLine(e.target.value)} onKeyDown={onKey}
              onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
              spellCheck={false} autoCapitalize="none" autoCorrect="off" autoComplete="off" enterKeyHint="send" disabled={off}
              aria-label="コマンド" placeholder={status === 'error' ? '(実行環境なし)' : ready ? '' : '(準備中)'} />
          </span>
          <div className="keys" role="group" aria-label="入力キー">
            <button type="button" className="kbtn" disabled={off} onClick={() => { complete(); if (inputRef.current) inputRef.current.focus(); }}>Tab</button>
            <button type="button" className="kbtn" disabled={off} aria-label="前の入力" onClick={() => historyStep(-1)}>&uarr;</button>
            <button type="button" className="kbtn" disabled={off} aria-label="次の入力" onClick={() => historyStep(1)}>&darr;</button>
            <button type="submit" className="kbtn enter" disabled={off}>Enter</button>
          </div>
        </form>
        <div className="actions">
          {simple ? <div className="quick-actions" role="group" aria-label="学習補助">
            <button type="button" className="kbtn" disabled={off} onClick={act('hint')}>ヒント</button>
            <button type="button" className="kbtn" disabled={off} onClick={act('answer')}>入力例</button>
            <button type="button" className="kbtn" disabled={off} onClick={act('modes')}>コース</button>
            <button type="button" className="kbtn" disabled={off} onClick={() => runLocal('help')}>ヘルプ</button>
          </div> : null}
          <nav className="lesson-nav" aria-label="問題の移動">
            <button type="button" className="nav-prev" disabled={off || !hasPrev} onClick={act('prev')}>← 前の問題</button>
            <div className="nav-status" aria-live="polite">
              <span>{course ? course.name + '　' : ''}問題 {lessonNo} / {pad2(total || 0)}</span>
              <small>{view?.completed ? '達成済み。次へ進めます。' : '課題を達成すると次の問題へ進めます。'}</small>
            </div>
            <button type="button" className="nav-next" disabled={off || !hasNext} onClick={act('next')}>
              {view?.completed && view.index + 1 >= total ? 'コース達成' : '次の問題へ →'}
            </button>
            <button type="button" className="nav-list" disabled={off} onClick={act('menu')}>問題一覧</button>
          </nav>
        </div>
      </main>
      <footer className="foot">
        <span className="foot-keys">help / Tab 補完 / ↑↓ 履歴</span>
        <span className="foot-r">
          <button type="button" aria-pressed={simple} onClick={() => setSimple(!simple)}>シンプル表示</button>
          <button type="button" onClick={() => setTheme(effectiveTheme() === 'dark' ? 'light' : 'dark')}>テーマ</button>
          <span className={'rt ' + status}>{status === 'ready' ? 'ready' : status === 'error' ? 'error' : 'loading ' + pct + '%'}</span>
        </span>
      </footer>
      <dialog ref={dataRef} aria-labelledby="data-title">
        <div className="dialog-heading"><h2 id="data-title">学習データ</h2><button type="button" className="kbtn" aria-label="閉じる" onClick={() => closeDialog(dataRef)}>[x]</button></div>
        <p>学習の進み具合と練習ファイルは、このブラウザーに保存されます。別の端末へ移すときは、JSONファイルで書き出してください。</p>
        <div className="data-actions">
          <button type="button" className="kbtn enter" onClick={exportData}>学習データを書き出す</button>
          <label className="kbtn import-button">保存データを読み込む<input type="file" accept="application/json,.json" onChange={importData} /></label>
        </div>
        <p className="dim">読み込むと、現在の練習状態が保存データに置き換わります。保存データはサーバーへ送信されません。</p>
        <div id="data-message" role="status">{dataMessage}</div>
      </dialog>
    </div>
  );
}
