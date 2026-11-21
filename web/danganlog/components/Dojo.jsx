'use client';
/* 学習画面全体。worker.js (Pyodide) との通信と保存はここだけで行う。 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  HISTORY_KEY, STORAGE_KEY, buildCourses, createClient, createHistory, feedbackFor, filterItems,
  firstOpenIndex, lastLine, loadSavedState, pad2, safeStorage, saveState
} from '../lib/core.js';

const MAX_ENTRIES = 200;
let entrySeq = 0;

function friendly(error) {
  return 'うまく実行できませんでした: ' + lastLine(error && error.message);
}

export default function Dojo() {
  const [catalog, setCatalog] = useState(null);
  const [progress, setProgress] = useState(null);
  const [view, setView] = useState(null);
  const [viewMode, setViewMode] = useState('intro');
  const [unit, setUnit] = useState('');
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('loading');
  const [errorText, setErrorText] = useState('');
  const [busy, setBusy] = useState(false);
  const [entries, setEntries] = useState([]);
  const [feedback, setFeedback] = useState({ kind: '', text: '' });
  const [menuOpen, setMenuOpen] = useState(false);
  const [dataMessage, setDataMessage] = useState('');
  const [line, setLine] = useState('');
  const [attempt, setAttempt] = useState(0);

  const clientRef = useRef(null);
  const storageRef = useRef(null);
  const historyRef = useRef(null);
  const inputRef = useRef(null);
  const outRef = useRef(null);
  const helpRef = useRef(null);
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
    if (outRef.current) outRef.current.scrollTop = outRef.current.scrollHeight;
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
      setEntries(v.output ? [{ id: ++entrySeq, prompt: '', command: null, output: v.output }] : []);
      setFeedback({ kind: '', text: v.lesson && v.lesson.shownAnswer ? '入力例: ' + v.lesson.shownAnswer : '' });
      applyView(v);
      setMenuOpen(false);
      if (inputRef.current) inputRef.current.focus();
    } catch (error) {
      setFeedback({ kind: 'ng', text: friendly(error) });
    }
  }, [call, applyView]);

  /* 起動: 実行環境の読み込み → 保存データの復元 → 最初のレッスン */
  useEffect(() => {
    const storage = safeStorage(window);
    storageRef.current = storage;
    let initial = [];
    try { initial = JSON.parse(storage.get(HISTORY_KEY) || '[]'); } catch (e) { initial = []; }
    historyRef.current = createHistory(initial);
    const client = createClient(() => new Worker('/worker.js'));
    clientRef.current = client;
    let cancelled = false;
    setStatus('loading');
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
            setFeedback({ kind: 'ng', text: '保存データを読み込めなかったため、最初から始めます。' });
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

  const chooseCourse = (c) => {
    setUnit(''); setQuery(''); setMenuOpen(false);
    if (view && view.mode === c.id) { setViewMode(c.id); return; }
    setViewMode(c.id);
    selectLesson(c.id, firstOpenIndex(c));
  };

  const submit = async (event) => {
    event.preventDefault();
    const text = line;
    if (!text.trim() || !ready || busy) return;
    setLine('');
    const promptShown = (view && view.prompt) || '$';
    const wasDone = !!(view && view.completed);
    historyRef.current.push(text);
    storageRef.current.set(HISTORY_KEY, JSON.stringify(historyRef.current.items()));
    try {
      const v = await call({ type: 'execute', line: text });
      const fb = feedbackFor(v, wasDone);
      if (text.trim() === 'reset') setEntries(v.output ? [{ id: ++entrySeq, prompt: '', command: null, output: v.output }] : []);
      else addEntry(promptShown, text, (v.output || '').replace(/\n+$/, ''), v.code ? 'error' : (v.completed && !wasDone ? 'success' : ''));
      setFeedback(fb);
      applyView(v);
    } catch (error) {
      addEntry(promptShown, text, friendly(error), 'error');
    }
    if (inputRef.current) inputRef.current.focus();
  };

  const onKey = (event) => {
    const h = historyRef.current;
    if (event.key === 'ArrowUp') {
      const v = h.up(line);
      if (v !== null) { event.preventDefault(); setLine(v); }
    } else if (event.key === 'ArrowDown') {
      const v = h.down();
      if (v !== null) { event.preventDefault(); setLine(v); }
    } else if (event.key === 'l' && event.ctrlKey) {
      event.preventDefault(); setEntries([]);
    }
  };

  const tool = async (type, fallback) => {
    if (!ready || busy) return;
    try {
      const v = await call({ type });
      if (type === 'reset') setEntries([]);
      setFeedback({ kind: 'info', text: v.output || fallback });
      applyView(v);
    } catch (error) {
      setFeedback({ kind: 'ng', text: friendly(error) });
    }
    if (inputRef.current) inputRef.current.focus();
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
      setEntries([{ id: ++entrySeq, prompt: '', command: null, output: '保存データを読み込みました。' }]);
      setFeedback({ kind: '', text: '' });
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

  useEffect(() => {
    const onEsc = (e) => { if (e.key === 'Escape') setMenuOpen(false); };
    document.addEventListener('keydown', onEsc);
    return () => document.removeEventListener('keydown', onEsc);
  }, []);

  const lesson = view && view.lesson;
  const hasNext = !!(view && view.completed && course && view.index + 1 < course.total);
  const units = course ? [...new Set(course.items.map((i) => i.unit).filter(Boolean))] : [];
  const shown = course ? filterItems(course.items, query, unit) : [];
  const current = view && course && view.mode === course.id ? view.index : -1;
  const off = busy || !ready;
  const statusLabel = status === 'ready' ? '準備完了' : status === 'error' ? '読み込み失敗' : '準備中';
  const courseIndex = course ? courses.indexOf(course) : 0;

  return (
    <div className="app-shell">
      <aside className={'sidebar' + (menuOpen ? ' open' : '')} id="sidebar" aria-label="学習ナビゲーション">
        <a className="brand" href="/" aria-label="DANGAN LOG ホーム"><span className="brand-mark">&gt;_</span><span>DANGAN LOG<small>LINUX TRAINING GROUND</small></span></a>
        <div className="side-label">YOUR WORKSPACE <span>01</span></div>
        <button type="button" className="nav-home active" onClick={() => { setMenuOpen(false); window.scrollTo(0, 0); if (inputRef.current) inputRef.current.focus(); }}><span aria-hidden="true">&#9672;</span> 学習ワークスペース</button>
        <div className="side-label course-label">LEARNING PATH</div>
        <nav aria-label="コース選択">
          {courses.map((c, i) => (
            <button type="button" key={c.id} className={'course-nav-item' + (c.id === (course && course.id) ? ' selected' : '')}
              aria-current={c.id === (course && course.id) ? 'true' : undefined} onClick={() => chooseCourse(c)}>
              <span className="nav-number">{pad2(i + 1)}</span><span>{c.name}</span><span className="nav-arrow" aria-hidden="true">&rsaquo;</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="small-terminal">$ keep learning<span className="cursor">_</span></div>
          <p>小さな一歩を、確かな力に。</p>
          <button type="button" className="text-button" onClick={() => openDialog(dataRef)}>学習データの管理 <span aria-hidden="true">&#8599;</span></button>
          <div className="local-note"><i></i> 進捗はこのブラウザーに保存</div>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <button type="button" className="mobile-menu icon-button" aria-label="メニューを開閉" aria-expanded={menuOpen} aria-controls="sidebar" onClick={() => setMenuOpen(!menuOpen)}>&#9776;</button>
          <div className="breadcrumb">WORKSPACE <span>/</span> <strong>Linux道場</strong></div>
          <div className="top-actions">
            <span className={'runtime-status ' + status} role="status"><i></i> {statusLabel}</span>
            <button type="button" className="icon-button" aria-label="使い方" onClick={() => openDialog(helpRef)}>?</button>
          </div>
        </header>
        <div className="main-content">
          <section className="welcome">
            <div>
              <div className="eyebrow"><span></span> LEARN BY DOING</div>
              <h1>Linuxを、<br className="mobile-break" />自分の道具に。</h1>
              <p>読む。試す。わかる。<br className="mobile-break" />その積み重ねで、できることを増やそう。</p>
            </div>
            <div className="progress-summary"><span className="summary-icon" aria-hidden="true">&#10022;</span><div><small>このブラウザーでの学習</small><strong><span>{totalDone}</span> <em>lessons completed</em></strong></div></div>
          </section>
          <section className="course-heading">
            <div><span className="section-kicker">COURSE {pad2(courseIndex + 1)}</span><h2>{course ? course.name : 'はじめてのLinux'}</h2><p>{course ? course.description : 'ターミナルへの最初の一文字から、ひとつずつ。'}</p></div>
            <div className="course-count"><strong>{course ? course.done : 0}</strong><span>/ {course ? course.total : 0} lessons</span></div>
          </section>
          <div className="course-progress" role="progressbar" aria-valuemin={0} aria-valuemax={course ? course.total : 0} aria-valuenow={course ? course.done : 0} aria-label="コースの進み具合">
            <div style={{ width: course && course.total ? Math.round(course.done * 100 / course.total) + '%' : '0%' }}></div>
          </div>
          <div className="study-grid">
            <section className="lesson-panel" aria-labelledby="lesson-title">
              <div className="panel-top"><span className="lesson-number">LESSON {pad2((view ? view.index : 0) + 1)}</span><span className="mode-badge">{course ? course.name : ''}</span></div>
              <h2 id="lesson-title">{lesson ? lesson.title : '教材を読み込んでいます'}</h2>
              <div className="lesson-explanation">{lesson ? lesson.explanation : 'ターミナルは、文字でコンピューターに指示を出す場所です。準備ができると、ここに説明が表示されます。'}</div>
              <div className="task-box"><span>YOUR MISSION</span><p>{lesson ? lesson.task : '教材を読み込んでいます。準備ができたら、ここに今回の課題が表示されます。'}</p></div>
              <div className="lesson-tools">
                <button type="button" disabled={off} onClick={() => tool('hint', 'ヒントはありません。')}><span aria-hidden="true">&#9676;</span> ヒント</button>
                <button type="button" disabled={off} onClick={() => tool('answer', '入力例はありません。')}><span aria-hidden="true">&#8984;</span> 入力例</button>
                <button type="button" disabled={off} onClick={() => tool('reset', '課題を初期状態に戻しました。')}><span aria-hidden="true">&#8635;</span> やり直す</button>
              </div>
              <div className={'lesson-feedback' + (feedback.kind ? ' ' + feedback.kind : '')} role="status" aria-live="polite">{feedback.text}</div>
              {hasNext ? <button type="button" className="next-button" onClick={() => selectLesson(view.mode, view.index + 1)}>次のレッスンへ <span aria-hidden="true">&rarr;</span></button> : null}
              <div className="lesson-footer"><span aria-hidden="true">&#10003;</span> 何度間違えても大丈夫。ヒントを見ても減点なし。</div>
            </section>
            <section className="terminal-panel" aria-label="練習用ターミナル">
              <div className="terminal-bar"><div className="traffic-lights" aria-hidden="true"><i></i><i></i><i></i></div><span>dojo — training terminal</span><span className="terminal-mode">SIMULATED</span></div>
              <div className="terminal-output" ref={outRef} role="log" aria-live="polite" aria-relevant="additions" tabIndex={0}>
                {entries.length === 0 && !(view && view.editor) ? (
                  <div className="terminal-welcome"><span className="terminal-ascii">&gt;_</span><p>Welcome to Linux DOJO.</p><small>ここは、安心して試せる練習の場所です。<br />コマンドを入力して Enter を押してください。</small><div className="terminal-divider"></div><small className="terminal-note">ブラウザー内の模擬環境です。<br />実際のPCの設定やファイルは変更しません。</small></div>
                ) : null}
                {entries.map((e) => (
                  <div className="terminal-entry" key={e.id}>
                    {e.command !== null ? <div className="terminal-command"><span>{e.prompt}</span>{e.command}</div> : null}
                    {e.output ? <div className={'terminal-result' + (e.kind ? ' ' + e.kind : '')}>{e.output}</div> : null}
                  </div>
                ))}
                {view && view.editor ? <pre className="terminal-result" aria-label="エディターの表示" style={{ margin: 0 }}>{view.editor}</pre> : null}
              </div>
              <form className="terminal-form" onSubmit={submit} autoComplete="off" aria-busy={busy}>
                <label htmlFor="terminal-input">{(view && view.prompt) || '$'}</label>
                <input id="terminal-input" ref={inputRef} name="command" aria-label="Linuxコマンドを入力" value={line}
                  onChange={(e) => setLine(e.target.value)} onKeyDown={onKey} spellCheck={false} autoCapitalize="none" autoComplete="off"
                  placeholder={status === 'error' ? '実行環境を読み込めませんでした' : ready ? 'コマンドを入力して Enter' : '教材の実行環境を準備しています…'} disabled={off} />
                <button type="submit" aria-label="コマンドを実行" disabled={off}>&crarr;</button>
              </form>
              <div className={'terminal-bottom' + (ready ? ' ready' : '')}><span><i></i> <span>{ready ? 'Python runtime is ready' : status === 'error' ? 'Python runtime unavailable' : 'Python runtime is loading'}</span></span><span>Enter to run / Up Down history</span></div>
            </section>
          </div>
          {status === 'error' ? (
            <div className="runtime-notice" role="alert"><span>Python実行環境を読み込めませんでした。ネットワーク接続を確認し、「再読み込み」を押してください。詳細: {errorText}</span><button type="button" onClick={() => setAttempt(attempt + 1)}>再読み込み</button></div>
          ) : null}
          <section className="lesson-library">
            <div className="library-heading"><div><span className="section-kicker">YOUR NEXT STEPS</span><h2>レッスン一覧</h2></div>
              <label className="search-box"><span aria-hidden="true">&#8981;</span><input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="レッスンを検索" aria-label="レッスンを検索" /></label></div>
            <div className="unit-filter">
              {units.length > 1 ? [''].concat(units).map((u) => (
                <button type="button" key={u || 'all'} className={u === unit ? 'selected' : ''} aria-pressed={u === unit} onClick={() => setUnit(u)}>{u || 'すべて'}</button>
              )) : null}
            </div>
            <div className="lesson-list">
              {course && shown.length === 0 ? <div className="empty-list">該当するレッスンがありません。</div> : null}
              {!course ? <div className="empty-list">教材を読み込んでいます。</div> : null}
              {shown.map((item) => (
                <button type="button" key={item.id} className={'lesson-card' + (item.done ? ' done' : '') + (item.index === current ? ' current' : '')}
                  aria-current={item.index === current ? 'true' : undefined} disabled={off} onClick={() => selectLesson(course.id, item.index)}>
                  <span className="lesson-step">{item.done ? 'OK' : pad2(item.index + 1)}</span>
                  <div><strong>{item.title}</strong>{item.unit ? <small>{item.unit}</small> : null}</div>
                  <span className="card-arrow" aria-hidden="true">&rarr;</span>
                </button>
              ))}
            </div>
          </section>
          <section className="beyond-browser"><div className="beyond-icon" aria-hidden="true">&#8599;</div><div><span className="section-kicker">BEYOND THE BROWSER</span><h3>本物のLinuxでも、確かめよう。</h3><p>この画面は模擬ターミナルで学ぶコースです。本物のbashを使う実践や、構築・故障調査・復旧のVM実習は、教材をダウンロードして進められます。</p></div><a className="outline-link" href="https://github.com/leo0607y/LinuxDOJO" target="_blank" rel="noopener noreferrer">教材・実習ガイド <span aria-hidden="true">&#8599;</span></a></section>
          <footer className="page-footer"><span>DANGAN LOG <b>/</b> Linux道場</span><span>ひとつずつ、使いこなせるように。</span></footer>
        </div>
      </main>
      <dialog ref={dataRef}>
        <div className="dialog-heading"><h2>学習データ</h2><button type="button" className="icon-button" aria-label="閉じる" onClick={() => closeDialog(dataRef)}>&times;</button></div>
        <p>学習の進み具合と練習ファイルは、このブラウザーに保存されます。別の端末へ移すときは、JSONファイルで書き出してください。</p>
        <div className="data-actions">
          <button type="button" className="primary-button" onClick={exportData}>学習データを書き出す &darr;</button>
          <label className="import-button">保存データを読み込む &uarr;<input type="file" accept="application/json,.json" onChange={importData} /></label>
        </div>
        <p className="dialog-note">読み込むと、現在の練習状態が保存データに置き換わります。共有の端末では、自分のデータを手元にも保存してください。</p>
        <div id="data-message" role="status">{dataMessage}</div>
      </dialog>
      <dialog ref={helpRef}>
        <div className="dialog-heading"><h2>Linux道場の使い方</h2><button type="button" className="icon-button" aria-label="閉じる" onClick={() => closeDialog(helpRef)}>&times;</button></div>
        <ol><li>説明と「YOUR MISSION」を読みます。</li><li>右のターミナルにコマンドを入力し、Enterで実行します。上下キーで過去の入力を呼び出せます。</li><li>結果を確かめて、できたら次のレッスンへ進みます。</li></ol>
        <p>分からないときは「ヒント」を1回ずつ。「入力例」で答えを確認することもできます。総合復習では、作業したあとに <code>check</code> で判定します。</p>
        <p className="dialog-note">初回はPython実行環境の読み込みに時間がかかります。読み込めない場合も、レッスンの説明は読めます。保存データはサーバーへ送信されません。</p>
      </dialog>
    </div>
  );
}
