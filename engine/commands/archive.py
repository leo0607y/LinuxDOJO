"""練習フォルダだけで動く tar/gzip/gunzip と find の一部。

実際に標準形式のアーカイブを作るが、展開は通常ファイルとディレクトリに限定する。
リンク・絶対パス・親をたどる名前は受け付けない。
"""
import fnmatch
import gzip
import io
import math
from pathlib import PurePosixPath
import tarfile
import zlib

from engine.commands import command, on_check, on_prepare
from engine.guided import Result, TrainingError

LIMIT = 16 * 1024 * 1024


@on_check
def check(scenario, terminal):
    for name, expected in scenario.get('expected_archives', {}).items():
        try:
            path = terminal.path(name)
            if name.endswith('.gz') and path.read_bytes()[:2] != b'\x1f\x8b':
                return False, f'{name} は gzip 圧縮されたアーカイブにしましょう。'
            with tarfile.open(path, 'r:*') as bundle:
                entries = bundle.getmembers()
                if len(entries) > 2000 or sum(max(0, e.size) for e in entries) > LIMIT:
                    return False, f'{name} の内容が目的のバックアップと異なります。'
                if any(not (e.isdir() or e.isfile()) for e in entries):
                    return False, f'{name} にリンクや特殊ファイルを含めないでください。'
                actual = {entry.name: bundle.extractfile(entry).read().decode('utf-8') for entry in entries if entry.isfile()}
            if actual != expected:
                return False, f'{name} に必要なファイルと内容だけが保存されているか確認しましょう。'
        except (OSError, tarfile.TarError, EOFError, UnicodeError, zlib.error):
            return False, f'{name} は読み取れるアーカイブになっていません。'
    return None


@on_prepare
def prepare(terminal, step):
    """既知のバックアップを、テキストの教材データから用意する。"""
    for name, files in step.get('archives', {}).items():
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w:gz' if name.endswith('.gz') else 'w') as bundle:
            for filename, text in files.items():
                info = tarfile.TarInfo(filename)
                data = text.encode('utf-8')
                info.mode, info.size = 0o644, len(data)
                bundle.addfile(info, io.BytesIO(data))
        target = terminal.path(name)
        terminal.ensure_directory(target.parent)
        existed = target.exists()
        target.write_bytes(buffer.getvalue())
        terminal.created(target, existed)
    for name, text in step.get('gzip_files', {}).items():
        target = terminal.path(name)
        terminal.ensure_directory(target.parent)
        existed = target.exists()
        target.write_bytes(gzip.compress(text.encode('utf-8')))
        terminal.created(target, existed)


def _members(terminal, names, base):
    rows = []
    for name in names:
        _archive_name(name)
        path = terminal.path(str(base / name))
        if not path.exists():
            raise TrainingError(f"tar: {name}: No such file or directory")
        candidates = [path] + (sorted(path.rglob('*')) if path.is_dir() else [])
        for item in candidates:
            checked = terminal.path('/home/learner/' + item.relative_to(terminal.active_root).as_posix())
            if len(rows) >= 2000:
                raise TrainingError('この練習では一度に扱うファイルを2000個までにします。')
            arcname = (PurePosixPath(name) / item.relative_to(path).as_posix()).as_posix()
            rows.append((checked, arcname))
    return rows


def _archive_name(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name:
        raise TrainingError('アーカイブ内に練習先の外へ出る名前があります。展開を中止しました。')
    return path


@command('tar')
def tar(terminal, rest, stdin=None, admin=False):
    action, archive, directory, verbose, compressed = None, None, '.', False, False
    names, args = [], list(rest)
    while args:
        arg = args.pop(0)
        if arg in ('-C', '--directory'):
            if not args:
                return Result('tar: -C の後ろにフォルダ名が必要です。', 2)
            directory = args.pop(0)
        elif arg in ('-f', '--file'):
            if not args:
                return Result('tar: -f の後ろに保存先が必要です。', 2)
            archive = args.pop(0)
        elif arg in ('--create', '--list', '--extract', '--gzip', '--verbose'):
            if arg == '--gzip':
                compressed = True
            elif arg == '--verbose':
                verbose = True
            else:
                value = {'--create': 'c', '--list': 't', '--extract': 'x'}[arg]
                if action:
                    return Result('tar: 操作は作成・一覧・展開のどれか1つです。', 2)
                action = value
        elif (arg.startswith('-') and len(arg) > 1) or (action is None and set(arg) <= set('ctxzvf') and arg):
            flags = arg.lstrip('-')
            for i, flag in enumerate(flags):
                if flag in 'ctx':
                    if action:
                        return Result('tar: 操作は作成・一覧・展開のどれか1つです。', 2)
                    action = flag
                elif flag == 'z':
                    compressed = True
                elif flag == 'v':
                    verbose = True
                elif flag == 'f':
                    if i != len(flags) - 1:
                        archive = flags[i + 1:]
                        break
                    if not args:
                        return Result('tar: -f の後ろに保存先が必要です。', 2)
                    archive = args.pop(0)
                else:
                    return None
        else:
            names.append(arg)
    if action is None or archive is None:
        return Result('tar: 作成(-c)・一覧(-t)・展開(-x)と、ファイル(-f)を指定します。', 2)
    base = terminal.path(directory)
    target = terminal.path(archive)
    if not base.is_dir():
        return Result(f'tar: {directory}: Not a directory', 2)
    try:
        if action == 'c':
            if not names:
                return Result('tar: Cowardly refusing to create an empty archive', 2)
            relative_base = PurePosixPath('/home/learner') / base.relative_to(terminal.active_root).as_posix()
            rows = _members(terminal, names, relative_base)
            if target in [p for p, _ in rows]:
                return Result('tar: 保存先をアーカイブ対象の外に指定しましょう。', 2)
            if sum(p.stat().st_size for p, _ in rows if p.is_file()) > LIMIT:
                return Result('tar: この練習の容量上限を超えています。', 2)
            buffer = io.BytesIO()
            with tarfile.open(fileobj=buffer, mode='w:gz' if compressed else 'w') as bundle:
                for path, name in rows:
                    info = tarfile.TarInfo(name)
                    info.mode = terminal.mode_of(path)
                    info.type = tarfile.DIRTYPE if path.is_dir() else tarfile.REGTYPE
                    data = path.read_bytes() if path.is_file() else b''
                    info.size = len(data)
                    bundle.addfile(info, io.BytesIO(data))
            existed = target.exists()
            target.write_bytes(buffer.getvalue())
            terminal.created(target, existed)
            return Result('\n'.join(n for _, n in rows) if verbose else '')
        with tarfile.open(target, 'r:*') as bundle:
            entries = bundle.getmembers()
            if len(entries) > 2000 or sum(max(0, e.size) for e in entries) > LIMIT:
                return Result('tar: この練習の展開上限を超えています。', 2)
            if action == 't':
                return Result('\n'.join(e.name + ('/' if e.isdir() and not e.name.endswith('/') else '') for e in entries))
            selected = [e for e in entries if not names or any(e.name == n or e.name.startswith(n.rstrip('/') + '/') for n in names)]
            # すべて検査してから書き込む。
            destinations = []
            for entry in selected:
                name = _archive_name(entry.name)
                if not (entry.isfile() or entry.isdir()):
                    return Result('tar: リンクや特殊ファイルはこの練習では展開できません。', 2)
                destination = terminal.path('/home/learner/' + (base / str(name)).relative_to(terminal.active_root).as_posix())
                destinations.append((entry, destination))
            for entry, destination in destinations:
                if entry.isdir():
                    terminal.ensure_directory(destination)
                else:
                    terminal.ensure_directory(destination.parent)
                    existed = destination.exists()
                    destination.write_bytes(bundle.extractfile(entry).read())
                    terminal.created(destination, existed)
                terminal.set_mode(destination, entry.mode & 0o777)
            return Result('\n'.join(e.name for e, _ in destinations) if verbose else '')
    except (tarfile.TarError, EOFError, gzip.BadGzipFile, zlib.error) as error:
        return Result(f'tar: アーカイブを読めません: {error}', 2)


@command('gzip')
def compress(terminal, rest, stdin=None, admin=False):
    decompress, keep = False, False
    names = []
    for arg in rest:
        if arg.startswith('-') and len(arg) > 1:
            if set(arg[1:]) - set('dk123456789'):
                return None
            decompress |= 'd' in arg
            keep |= 'k' in arg
        else:
            names.append(arg)
    if not names:
        return Result('gzip: この練習では対象のファイル名を指定します。', 1)
    for name in names:
        source = terminal.path(name)
        if decompress and not name.endswith('.gz'):
            return Result(f'gzip: {name}: unknown suffix -- ignored', 2)
        dest = terminal.path(name[:-3] if decompress else name + '.gz')
        if dest.exists():
            return Result(f'gzip: {dest.name} already exists; not overwritten', 2)
        if source.stat().st_size > LIMIT:
            return Result('gzip: この練習の容量上限を超えています。', 1)
        try:
            if decompress:
                with gzip.open(source, 'rb') as stream:
                    data = stream.read(LIMIT + 1)
                if len(data) > LIMIT:
                    return Result('gzip: この練習の展開上限を超えています。', 1)
            else:
                data = gzip.compress(source.read_bytes())
        except (gzip.BadGzipFile, EOFError, zlib.error):
            return Result(f'gzip: {name}: not in gzip format', 1)
        dest.write_bytes(data)
        terminal.set_mode(dest, terminal.mode_of(source))
        if not keep:
            source.unlink()
            terminal.forget_mode(source)
    return Result()


@command('gunzip')
def gunzip(terminal, rest, stdin=None, admin=False):
    return compress(terminal, ['-d', *rest], stdin, admin)


@command('find')
def find(terminal, rest, stdin=None, admin=False):
    args = list(rest)
    start = args.pop(0) if args and not args[0].startswith('-') else '.'
    root = terminal.path(start)
    if not root.exists():
        return Result(f'find: {start}: No such file or directory', 1)
    filters, maxdepth, deleting = [], None, False
    while args:
        arg = args.pop(0)
        if arg == '-print':
            continue
        if arg == '-delete':
            deleting = True
            continue
        if arg not in ('-name', '-iname', '-type', '-size', '-maxdepth') or not args:
            return None
        value = args.pop(0)
        if arg == '-maxdepth':
            if not value.isdigit():
                return Result('find: -maxdepth は0以上の整数です。', 1)
            maxdepth = int(value)
        elif arg == '-type':
            if value not in ('f', 'd'):
                return Result('find: この練習の種類は f（ファイル）か d（フォルダ）です。', 1)
            filters.append(lambda p, v=value: p.is_file() if v == 'f' else p.is_dir())
        elif arg in ('-name', '-iname'):
            insensitive = arg == '-iname'
            filters.append(lambda p, v=value, insensitive=insensitive: fnmatch.fnmatchcase(p.name.lower() if insensitive else p.name, v.lower() if insensitive else v))
        else:
            import re
            match = re.fullmatch(r'([+-]?)(\d+)([ckMG]?)', value)
            if not match:
                return Result('find: -size は +1k や 0c のように指定します。', 1)
            sign, count, suffix = match.groups()
            unit = {'': 512, 'c': 1, 'k': 1024, 'M': 1024**2, 'G': 1024**3}[suffix]
            def size_filter(p, sign=sign, count=int(count), unit=unit):
                blocks = math.ceil(p.stat().st_size / unit)
                return blocks > count if sign == '+' else blocks < count if sign == '-' else blocks == count
            filters.append(size_filter)
    paths = [root] + (sorted(root.rglob('*')) if root.is_dir() else [])
    matches = []
    for path in paths:
        if not terminal.progress['remote'] and (path == terminal.root / '.remote' or terminal.root / '.remote' in path.parents):
            continue
        relative = path.relative_to(root)
        if maxdepth is not None and len(relative.parts) > maxdepth:
            continue
        checked = terminal.path('/home/learner/' + path.relative_to(terminal.active_root).as_posix())
        if all(test(checked) for test in filters):
            matches.append(checked)
    if deleting:
        if root == terminal.active_root or root == terminal.path('.'):
            matches = [p for p in matches if p != root]
        for path in sorted(matches, key=lambda p: len(p.parts), reverse=True):
            path.rmdir() if path.is_dir() else path.unlink()
            terminal.forget_mode(path)
        return Result()
    return Result('\n'.join(start if p == root else start.rstrip('/') + '/' + p.relative_to(root).as_posix() for p in matches))
