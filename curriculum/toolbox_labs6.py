"""常用時の事故を防ぐ実ツール実習。専用フォルダの外は変更しない。"""
import hashlib
from pathlib import Path
import secrets
import stat
import tarfile

from curriculum.toolbox_labs import add, fixture, put, read, remember, require


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def regular(root, relative):
    path = root / relative
    require(not Path(relative).is_absolute() and '..' not in Path(relative).parts,
            '相対パスの範囲を確認します。')
    current = root
    for part in Path(relative).parts:
        current /= part
        require(not current.is_symlink(), relative + ' にシンボリックリンクを使いません。')
    require(path.is_file(), relative + ' がありません。')
    return path


def cleanup_setup(root):
    token = secrets.token_hex(4)
    names = ['old ' + token + '.tmp', '-n.tmp', 'line\nbreak.tmp', 'tab\tname.tmp',
             'nested cache/日本語.tmp']
    targets = {}
    for i, name in enumerate(names):
        path = 'cache/' + name
        put(root, path, f'cache {token} {i}\n', 0o600)
        targets[path] = digest(root / path)
    protected = ['cache/current.db', 'cache/keep.txt', 'important/records.tmp', 'important/.secret']
    for name in protected:
        put(root, name, 'DO NOT REMOVE ' + secrets.token_hex(12) + '\n', 0o600)
    (root / 'cache/linked-directory').symlink_to('../important', target_is_directory=True)
    remember(root, {'targets': targets}, protected)


def cleanup_check(root):
    saved = fixture(root)
    targets = saved['targets']
    link = root / 'cache/linked-directory'
    require(link.is_symlink() and link.readlink() == Path('../important'),
            '保護ディレクトリへのリンクを変更しません。')
    plan = regular(root, 'candidates.nul').read_bytes()
    require(plan.endswith(b'\0'), 'candidates.nul はNUL区切りで記録します。')
    items = plan[:-1].split(b'\0')
    require(len(items) == len(targets) and set(items) == {p.encode() for p in targets},
            '対象一覧に抜け・重複・保護ファイルがありませんか。改行を区切りにしません。')
    for name, expected in targets.items():
        require(not (root / name).exists() and not (root / name).is_symlink(),
                name + ' がまだ元の場所にあります。')
        for prefix in ('quarantine/', 'restored/'):
            path = regular(root, prefix + name)
            require(digest(path) == expected and stat.S_IMODE(path.stat().st_mode) == 0o600,
                    prefix + name + ' の内容・権限を保持します。')
    for folder in ('quarantine', 'restored'):
        base = root / folder
        actual = set()
        for path in base.rglob('*'):
            require(not path.is_symlink(), folder + ' にリンクを置きません。')
            if path.is_file():
                actual.add(path.relative_to(base).as_posix())
        require(actual == set(targets), folder + ' の対象が違います。')
    archive = regular(root, 'before-cleanup.tar.gz')
    try:
        with tarfile.open(archive, 'r:gz') as stream:
            files = [m for m in stream.getmembers() if not m.isdir()]
            require(len(files) == len(targets) and {m.name for m in files} == set(targets),
                    '退避アーカイブの対象が違います。')
            for member in files:
                require(member.isfile() and member.mode & 0o777 == 0o600,
                        '退避アーカイブは元の通常ファイルと権限を保持します。')
                require(hashlib.sha256(stream.extractfile(member).read()).hexdigest() == targets[member.name],
                        '退避アーカイブの本文が違います。')
    except tarfile.TarError as error:
        raise ValueError("退避アーカイブを読めません。作成と整合性を確認します。") from error
    sidecar = read(root, 'before-cleanup.sha256').strip().split()
    require(sidecar == [digest(archive), 'before-cleanup.tar.gz'], '退避ファイルのチェックサムが違います。')


CLEANUP_SOLUTION = r'''
find cache -xdev -type f -name '*.tmp' -print0 > candidates.nul
# 実行前の対象一覧。改行やタブも区別して表示する。
while IFS= read -r -d '' path; do printf '%q\n' "$path"; done < candidates.nul
tar -czf before-cleanup.tar.gz --null --verbatim-files-from -T candidates.nul
sha256sum before-cleanup.tar.gz > before-cleanup.sha256
sha256sum -c before-cleanup.sha256
while IFS= read -r -d '' path; do
    mkdir -p -- "quarantine/$(dirname -- "$path")"
    mv -- "$path" "quarantine/$path"
done < candidates.nul
mkdir restored
tar -xzf before-cleanup.tar.gz -C restored
'''

add('safe-cleanup', '削除事故を防ぐ: NUL区切り・リンク非追跡・退避と復元',
    'bash find tar sha256sum mkdir mv dirname', 'bash findutils tar coreutils',
    "cache 内の通常ファイル *.tmp だけを対象に、実削除せず quarantine/ 以下へ元の階層のまま移す。\n"
    "空白・改行・タブ・先頭ハイフンを含む名前がある。cache/linked-directory は追跡せず、important/ と通常データを保持する。\n"
    "1. find のNUL区切り結果を candidates.nul に保存し、bashの printf '%q' 等で対象を確認。\n"
    "2. 変更前に、対象だけの before-cleanup.tar.gz と before-cleanup.sha256 を作り、チェックサムを検証。\n"
    "3. 引用符と -- を使って quarantine/ に移動。ls の出力や改行をファイル一覧の区切りにしない。\n"
    "4. 信頼できる自作アーカイブを restored/ に展開し、内容と600の権限が元通りであることを確認。\n"
    "対象はこの実習フォルダだけ。一般のダウンロードアーカイブを無条件に展開する課題ではない。",
    cleanup_setup, cleanup_check, CLEANUP_SOLUTION,
    [CLEANUP_SOLUTION.replace('-print0', '-print'),
     CLEANUP_SOLUTION.replace('find cache -xdev', 'find -L cache -xdev'),
     "find cache -type f -name '*.tmp' -delete"])
