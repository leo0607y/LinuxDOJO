/* Original LinuxDOJO simulation, running in a browser worker. No server execution. */
// Pyodide は同じサイトの /pyodide/ から読む (第三者への依存なし)。
const PYODIDE_BASE = new URL('./pyodide/', self.location.href).href;
const SOURCE_URL = new URL('./python-source.json', self.location.href).href;
let runtime;
let initialization;
let queue = Promise.resolve();

/* 読み込みの進み具合を画面へ知らせる。fetch を包み、応答の本文が流れた量を数える。 */
let progressInstalled = false;
function installProgress() {
  if (progressInstalled) return;
  progressInstalled = true;
  const nativeFetch = self.fetch.bind(self);
  let loaded = 0;
  let seen = 0;
  const ESTIMATE = 15200000; /* pyodide 約13.5MB + 教材 約1.4MB。実際の Content-Length が上回ればそちらを使う */
  const report = () => self.postMessage({ progress: { loaded, total: Math.max(seen, ESTIMATE) } });
  self.fetch = async (input, init) => {
    let response;
    try { response = await nativeFetch(input, init); } catch (error) {
      self.postMessage({ fatal: '実行環境のファイルを取得できませんでした (' + String(typeof input === 'string' ? input : input.url).split('/').pop() + ')。ネットワークを確認してください。' });
      throw error;
    }
    if (!response.ok) {
      self.postMessage({ fatal: '実行環境のファイルを取得できませんでした (HTTP ' + response.status + ')。' });
      return response;
    }
    if (!response.body) return response;
    seen += Number(response.headers.get('content-length')) || 0;
    const counter = new TransformStream({
      transform(chunk, controller) { loaded += chunk.byteLength; report(); controller.enqueue(chunk); }
    });
    return new Response(response.body.pipeThrough(counter), { status: response.status, statusText: response.statusText, headers: response.headers });
  };
}

const PYTHON_BRIDGE = String.raw`
import base64, copy, json, os, re, shutil, sys, types
from pathlib import Path, PurePosixPath

# Import the guided curriculum without loading the native-bash practice stages.
if 'curriculum' not in sys.modules:
    _package = types.ModuleType('curriculum')
    _package.__path__ = [str(Path('/dojo-src/curriculum'))]
    sys.modules['curriculum'] = _package
from engine import guided, readiness, save, vim_sim
from curriculum.beginner_lessons import LESSONS

guided.Terminal.VIRTUAL_MODES = True
_WEB_ROOT = Path('/dojo-work/session')
_web_sessions = {}
_web_completed = {mode: [] for mode in LESSONS}
_web_completed['festival'] = {}
_web_review = {}
_web_selected = None
_web_terminal = None
_web_step = None
_web_scenarios = readiness.scenarios()


def _web_catalog():
    return {'modes': [{'id': mode, 'name': guided.MODE_NAMES[mode],
                      'lessons': [{'id': s['id'], 'title': s['title'], 'unit': s.get('unit', '')}
                                  for s in items]} for mode, items in LESSONS.items()],
            'scenarios': [{'id': s['id'], 'title': s['title'], 'pack': s.get('pack', 'basic'),
                           'level': s.get('level', 1)} for s in _web_scenarios]}


def _web_key(mode, index):
    items = _web_scenarios if mode == 'festival' else LESSONS.get(mode)
    if items is None or type(index) is not int or not 0 <= index < len(items):
        raise ValueError('存在するモードと課題番号を選んでください。')
    return mode + ':' + items[index]['id'], items[index]


def _web_files():
    result = []
    if _WEB_ROOT.exists():
        for path in sorted(_WEB_ROOT.rglob('*')):
            if path.is_symlink():
                raise ValueError('保存データにシンボリックリンクは使えません。')
            if path.is_dir():
                result.append({'path': path.relative_to(_WEB_ROOT).as_posix(), 'directory': True})
            elif path.is_file():
                result.append({'path': path.relative_to(_WEB_ROOT).as_posix(),
                               'data': base64.b64encode(path.read_bytes()).decode('ascii')})
    return result


def _web_capture():
    if _web_selected is not None and _web_terminal is not None:
        key, _ = _web_key(_web_selected['mode'], _web_selected['index'])
        session = _web_sessions[key]
        session['progress'] = copy.deepcopy(_web_terminal.progress)
        session['files'] = _web_files()


def _web_export():
    _web_capture()
    return {'version': 1, 'selected': copy.deepcopy(_web_selected),
            'sessions': copy.deepcopy(_web_sessions), 'completed': copy.deepcopy(_web_completed),
            'review': copy.deepcopy(_web_review)}


def _web_validate(state):
    if not isinstance(state, dict) or state.get('version') != 1:
        raise ValueError('対応していない保存データです。')
    sessions = state.get('sessions', {})
    if not isinstance(sessions, dict) or len(sessions) > 1000:
        raise ValueError('保存された課題数が上限を超えています。')
    byte_count = 0
    for key, session in sessions.items():
        if not isinstance(key, str) or not isinstance(session, dict) or not isinstance(session.get('progress'), dict):
            raise ValueError('課題の保存形式が不正です。')
        files = session.get('files', [])
        if not isinstance(files, list) or len(files) > 10000:
            raise ValueError('保存ファイル数が上限を超えています。')
        seen = set()
        for item in files:
            if not isinstance(item, dict) or not isinstance(item.get('path'), str):
                raise ValueError('保存パスが不正です。')
            name = item['path']; path = PurePosixPath(name)
            if not name or len(name) > 1000 or path.is_absolute() or '..' in path.parts or '\\' in name or '\x00' in name or name in seen:
                raise ValueError('保存パスは練習フォルダ内の重複しない相対パスにします。')
            seen.add(name)
            if item.get('directory') is not True:
                encoded = item.get('data')
                if not isinstance(encoded, str):
                    raise ValueError('ファイル内容が不正です。')
                try:
                    content = base64.b64decode(encoded, validate=True)
                except Exception:
                    raise ValueError('ファイル内容を読み込めません。')
                byte_count += len(content)
                if byte_count > 64 * 1024 * 1024:
                    raise ValueError('保存データの上限64MiBを超えています。')
    completed = state.get('completed', {})
    if not isinstance(completed, dict):
        raise ValueError('達成記録の保存形式が不正です。')
    for mode in LESSONS:
        if not isinstance(completed.get(mode, []), list):
            raise ValueError('達成記録の保存形式が不正です。')
    if not isinstance(completed.get('festival', {}), dict):
        raise ValueError('総合課題の達成記録が不正です。')
    review = state.get('review', {})
    if not isinstance(review, dict) or len(review) > 1000:
        raise ValueError('復習対象の保存形式が不正です。')
    known = {mode + ':' + item['id'] for mode, items in LESSONS.items() for item in items}
    known.update('festival:' + item['id'] for item in _web_scenarios)
    for key, item in review.items():
        if (not isinstance(item, dict) or not isinstance(item.get('mode'), str)
                or not isinstance(item.get('id'), str)
                or key != item['mode'] + ':' + item['id'] or key not in known):
            raise ValueError('復習対象の課題情報が不正です。')
    selected = state.get('selected')
    if selected is not None:
        if not isinstance(selected, dict):
            raise ValueError('選択中の課題情報が不正です。')
        _web_key(selected.get('mode'), selected.get('index'))
    return copy.deepcopy(state)


def _web_restore_files(files):
    if _WEB_ROOT.exists():
        shutil.rmtree(_WEB_ROOT)
    _WEB_ROOT.mkdir(parents=True)
    for item in files:
        path = _WEB_ROOT / item['path']
        if item.get('directory') is True:
            path.mkdir(parents=True, exist_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(base64.b64decode(item['data']))


def _web_select(mode, index, fresh=False):
    global _web_selected, _web_terminal, _web_step
    _web_capture()
    key, step = _web_key(mode, index)
    session = _web_sessions.get(key)
    if fresh or session is None:
        if _WEB_ROOT.exists():
            shutil.rmtree(_WEB_ROOT)
        progress = {}
        if mode == 'festival':
            terminal = readiness.prepare(step, _WEB_ROOT.parent, progress)
            # readiness names its root after the scenario; normalize it for snapshots.
            if terminal.root != _WEB_ROOT:
                if _WEB_ROOT.exists(): shutil.rmtree(_WEB_ROOT)
                terminal.root.rename(_WEB_ROOT)
                terminal = guided.Terminal(_WEB_ROOT, progress)
        else:
            terminal = guided.Terminal(_WEB_ROOT, progress)
            guided.prepare_step(terminal, step, fresh=True)
        session = {'progress': progress, 'files': [], 'hintLevel': 0, 'assisted': False,
                   'done': False, 'reviewReady': fresh}
        _web_sessions[key] = session
    else:
        _web_restore_files(session.get('files', []))
        terminal = guided.Terminal(_WEB_ROOT, copy.deepcopy(session['progress']))
    _web_terminal, _web_step = terminal, step
    _web_selected = {'mode': mode, 'index': index}
    return _web_view('課題を初期状態に戻しました。' if fresh else '')


def _web_view(output='', code=0):
    if _web_selected is None:
        return {'catalog': _web_catalog(), 'state': _web_export(), 'output': output, 'code': code}
    mode = _web_selected['mode']; key, _ = _web_key(mode, _web_selected['index'])
    session = _web_sessions[key]
    lesson = {name: _web_step.get(name, '') for name in ('id', 'title', 'task', 'explanation', 'unit')}
    if mode == 'festival':
        lesson['task'] = _web_step['brief']
        lesson['explanation'] = '目的に合う状態を作り、check で結果を判定します。模擬環境で実際のOSには変更を加えません。'
    else:
        if mode == 'intro' and _web_selected['index'] < guided.INTRO_SHOWN_ANSWERS:
            lesson['shownAnswer'] = _web_step['command']
    editor = _web_terminal.progress.get('editor')
    return {'lesson': lesson, 'mode': mode, 'index': _web_selected['index'],
            'output': output, 'code': code, 'completed': session.get('done', False),
            'prompt': _web_terminal.prompt_text(), 'editor': vim_sim.render(editor) if editor else '',
            'state': _web_export()}


def _web_complete():
    mode = _web_selected['mode']; key, _ = _web_key(mode, _web_selected['index'])
    session = _web_sessions[key]; session['done'] = True
    reviewed = key in _web_review and session.get('reviewReady') and not session['assisted']
    if reviewed:
        save.finish_review({'review': _web_review}, mode, _web_step['id'])
    if mode == 'festival':
        previous = _web_completed['festival'].get(_web_step['id'])
        if previous is None or not session['assisted']:
            _web_completed['festival'][_web_step['id']] = {'assisted': session['assisted']}
    elif _web_step['id'] not in _web_completed[mode]:
        _web_completed[mode].append(_web_step['id'])
    return reviewed


def browser_request(request_json):
    global _web_sessions, _web_completed, _web_review, _web_selected, _web_terminal, _web_step
    request = json.loads(request_json)
    kind = request.get('type')
    if kind == 'init':
        return json.dumps(_web_view(), ensure_ascii=False)
    if kind == 'export':
        return json.dumps({'state': _web_export()}, ensure_ascii=False)
    if kind == 'import':
        candidate = _web_validate(request.get('state'))
        _web_sessions = candidate.get('sessions', {})
        _web_completed = {mode: candidate.get('completed', {}).get(mode, []) for mode in LESSONS}
        _web_completed['festival'] = candidate.get('completed', {}).get('festival', {})
        _web_review = candidate.get('review', {})
        selected = candidate.get('selected')
        _web_selected = _web_terminal = _web_step = None
        if selected:
            return json.dumps(_web_select(selected['mode'], selected['index']), ensure_ascii=False)
        return json.dumps(_web_view('保存データを読み込みました。'), ensure_ascii=False)
    if kind == 'resetMode':
        reset_mode = request.get('mode')
        if reset_mode != 'festival' and reset_mode not in LESSONS:
            raise ValueError('初期化するモードを選んでください。')
        prefix = reset_mode + ':'
        for key in [k for k in _web_sessions if k.startswith(prefix)]:
            del _web_sessions[key]
        for key in [k for k in _web_review if k.startswith(prefix)]:
            del _web_review[key]
        _web_completed['festival' if reset_mode == 'festival' else reset_mode] = {} if reset_mode == 'festival' else []
        _web_selected = _web_terminal = _web_step = None
        return json.dumps(_web_select(reset_mode, 0, fresh=True), ensure_ascii=False)
    if kind == 'select':
        return json.dumps(_web_select(request.get('mode'), request.get('index', 0)), ensure_ascii=False)
    if kind == 'review':
        review_mode, lesson_id = request.get('mode'), request.get('lessonId')
        if not isinstance(review_mode, str) or not isinstance(lesson_id, str):
            raise ValueError('復習する課題を選んでください。')
        if review_mode + ':' + lesson_id not in _web_review:
            raise ValueError('その課題は復習対象ではありません。')
        items = _web_scenarios if review_mode == 'festival' else LESSONS[review_mode]
        index = next(i for i, item in enumerate(items) if item['id'] == lesson_id)
        return json.dumps(_web_select(review_mode, index, True), ensure_ascii=False)
    if _web_selected is None:
        raise ValueError('先に課題を選んでください。')
    mode = _web_selected['mode']; key, _ = _web_key(mode, _web_selected['index'])
    session = _web_sessions[key]
    if kind == 'reset':
        return json.dumps(_web_select(mode, _web_selected['index'], True), ensure_ascii=False)
    if kind == 'hint':
        session['assisted'] = True
        level = session.get('hintLevel', 0)
        if mode == 'festival':
            hints = readiness.advice_hints(_web_step)
            output = hints[min(level, len(hints)-1)] if hints else '追加のヒントはありません。'
            last = level >= len(hints) - 1
        else:
            output, last = guided.hint_text(_web_step, level)
        if last and 'answer' not in output:
            output += '\nanswer で入力例を確認できます（見ると復習対象に追加されます）。'
        session['hintLevel'] = level + 1
        return json.dumps(_web_view(output), ensure_ascii=False)
    if kind == 'answer':
        session['assisted'] = True
        session['reviewReady'] = session.get('reviewReady', False) and session.get('done', False)
        save.mark_review({'review': _web_review}, mode, _web_step['id'])
        output = '\n'.join(_web_step['solution']) if mode == 'festival' else '\n'.join(guided.answers(_web_step))
        output += '\n[INFO] 復習対象に追加しました。review で一覧を開けます。reset 後にヒント・答えを使わず達成すると外れます。'
        return json.dumps(_web_view(output), ensure_ascii=False)
    if kind == 'complete':
        text = request.get('line', '')
        if not isinstance(text, str) or len(text) > 4096:
            raise ValueError('入力が長すぎます。')
        start, candidates = _web_terminal.complete(text)
        return json.dumps({'start': start, 'candidates': candidates[:200]}, ensure_ascii=False)
    if kind != 'execute':
        raise ValueError('対応していない操作です。')
    line = request.get('line', '')
    if not isinstance(line, str) or len(line) > 65536:
        raise ValueError('入力が長すぎます。')
    if line.strip() in ('hint', 'answer', 'reset') and not _web_terminal.progress.get('editor'):
        return browser_request(json.dumps({'type': line.strip()}))
    if line.strip() in ('lesson', 'mission') and not _web_terminal.progress.get('editor'):
        return json.dumps(_web_view(_web_step.get('brief', _web_step.get('explanation',''))+'\n'+_web_step.get('task','')), ensure_ascii=False)
    if mode == 'festival' and line.strip() == 'check':
        good, output = readiness.check(_web_step, _web_terminal)
        if good:
            reviewed = _web_complete(); output += '\n[OK] 達成しました。\n'+_web_step['explanation']
            if reviewed: output += '\n[OK] 自力で解き直したので復習対象から外しました。'
        return json.dumps(_web_view(output, 0 if good else 1), ensure_ascii=False)
    result = _web_terminal.execute(line)
    output = result.output
    if mode != 'festival' and guided.accepted(line, result, _web_step, _web_terminal):
        reviewed = _web_complete(); output += '\n[OK] '+_web_step.get('success', '達成しました。')
        if reviewed: output += '\n[OK] 自力で解き直したので復習対象から外しました。'
    return json.dumps(_web_view(output, result.code), ensure_ascii=False)
`;

async function initialize() {
  if (!initialization) initialization = (async () => {
    installProgress();
    importScripts(PYODIDE_BASE + 'pyodide.js');
    runtime = await loadPyodide({ indexURL: PYODIDE_BASE });
    const response = await fetch(SOURCE_URL);
    if (!response.ok) throw new Error('教材データを取得できません。ページを再読み込みしてください。');
    const bundle = await response.json();
    if (!bundle.files || typeof bundle.files !== 'object') throw new Error('教材データの形式が不正です。');
    runtime.FS.mkdirTree('/dojo-src');
    for (const [name, source] of Object.entries(bundle.files)) {
      if (!name.endsWith('.py') || name.startsWith('/') || name.split('/').includes('..')) throw new Error('教材パスが不正です。');
      const target = '/dojo-src/' + name;
      runtime.FS.mkdirTree(target.slice(0, target.lastIndexOf('/')));
      runtime.FS.writeFile(target, source, { encoding: 'utf8' });
    }
    await runtime.runPythonAsync("import sys; sys.path.insert(0, '/dojo-src')");
    await runtime.runPythonAsync(PYTHON_BRIDGE);
  })();
  return initialization;
}

self.onmessage = ({ data }) => {
  queue = queue.catch(() => {}).then(async () => {
    try {
      await initialize();
      runtime.globals.set('_browser_request_json', JSON.stringify(data));
      const serialized = await runtime.runPythonAsync('browser_request(_browser_request_json)');
      self.postMessage({ id: data.id, ok: true, result: JSON.parse(serialized) });
    } catch (error) {
      self.postMessage({ id: data?.id, ok: false, error: String(error.message || error) });
    }
  });
};
