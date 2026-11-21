"""Stage 30: Git実践（衝突・rebase・bisect・復旧・運用）。本物のgitを使い、サンドボックス内の使い捨てリポジトリだけを操作する。"""
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile

from engine.runner import register

S = 30
NOTE = ("作業対象はこの課題のフォルダ内の使い捨てリポジトリだけです。実在のリモート・グローバル設定・他のリポジトリには触れません。"
        "gpg署名やGit LFSのように環境に無いことがあるものは、採取済みの出力や設定から診断します。")

_clock = [1700000000]


def genv(extra=None):
    e = dict(os.environ)
    for k in list(e):
        if k.startswith('GIT_') and k not in ('GIT_EXEC_PATH',):
            e.pop(k)
    _clock[0] += 60
    d = f'{_clock[0]} +0000'
    e.update(GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1', GIT_TERMINAL_PROMPT='0', GIT_EDITOR='true',
             GIT_PAGER='cat', GIT_AUTHOR_NAME='Trainee', GIT_AUTHOR_EMAIL='trainee@example.test',
             GIT_COMMITTER_NAME='Trainee', GIT_COMMITTER_EMAIL='trainee@example.test',
             GIT_AUTHOR_DATE=d, GIT_COMMITTER_DATE=d, LC_ALL='C')
    e.update(extra or {})
    return e


def gr(ctx, repo, *args, inp=None, env=None):
    cmd = ['git'] + (['-C', str(ctx.p(repo))] if repo is not None else []) + list(args)
    r = subprocess.run(cmd, env=genv(env), input=inp, capture_output=True, text=True, timeout=120)
    return r.returncode, r.stdout.strip()


def g(ctx, repo, *args, inp=None, env=None):
    rc, out = gr(ctx, repo, *args, inp=inp, env=env)
    if rc:
        ctx.fail(f'git {" ".join(args[:3])} が失敗しました（{repo}）。作業フォルダの状態を確認してください。')
    return out


def mk(ctx, repo, bare=False):
    ctx.mkdir(repo)
    g(ctx, repo, 'init', '-q', '-b', 'main', *(['--bare'] if bare else []))
    if not bare:
        g(ctx, repo, 'config', 'user.name', 'Trainee')
        g(ctx, repo, 'config', 'user.email', 'trainee@example.test')


def clone(ctx, src, dst):
    g(ctx, None, 'clone', '-q', str(ctx.p(src)), str(ctx.p(dst)))
    g(ctx, dst, 'config', 'user.name', 'Trainee')
    g(ctx, dst, 'config', 'user.email', 'trainee@example.test')
    g(ctx, dst, 'symbolic-ref', 'HEAD', 'refs/heads/main') if gr(ctx, dst, 'rev-parse', '-q', '--verify', 'HEAD')[0] else None


def cm(ctx, repo, msg, files=None, author=None):
    for name, text in (files or {}).items():
        if text is None:
            g(ctx, repo, 'rm', '-q', '-f', name)
        else:
            ctx.write(f'{repo}/{name}', text)
    g(ctx, repo, 'add', '-A')
    env = {}
    if author:
        env = {'GIT_AUTHOR_NAME': author[0], 'GIT_AUTHOR_EMAIL': author[1]}
    g(ctx, repo, 'commit', '-q', '-m', msg, env=env)
    return g(ctx, repo, 'rev-parse', 'HEAD')


def rev(ctx, repo, ref):
    return g(ctx, repo, 'rev-parse', '--verify', '-q', ref + '^{commit}')


def tok():
    return secrets.token_hex(3)


def need_repo(ctx, repo):
    ctx.require(os.path.exists(ctx.p(repo + '/.git')) or os.path.exists(ctx.p(repo + '/HEAD')), f'{repo} のリポジトリが見つかりません。')


def req(ctx, text):
    ctx.write('requirements.txt', text + '\n')


def rj(ctx, name):
    try:
        v = json.loads(ctx.need_file(name))
    except ValueError:
        ctx.fail(name + ' は有効なJSONで保存します。')
    ctx.require(isinstance(v, dict), name + ' の最上位はオブジェクトです。')
    return v


def resolve(ctx, repo, s, what):
    ctx.require(isinstance(s, str) and re.fullmatch(r'[0-9a-f]{7,40}', s.strip()), f'{what} はコミットIDを7桁以上の16進で書きます。')
    rc, out = gr(ctx, repo, 'rev-parse', '--verify', '-q', s.strip() + '^{commit}')
    ctx.require(rc == 0, f'{what} のコミットIDがリポジトリに存在しません。')
    return out


def mission(n, title, story, objectives, setup, check, solution, wrong, explanation, thinking, tools):
    register(id=f'30-{n}', stage=S, title=title, story=story + '\n' + NOTE,
             objectives=objectives, setup=setup, check=check, solution=solution, wrong=wrong,
             hints=[thinking, tools, solution], answer=solution, explanation=explanation,
             tip='履歴を書き換える操作の前には、ブランチやタグで退避先を作るか reflog の位置を控えておくと、いつでも元に戻れます。')


# ============================================================ 1 init / clone / bare
def s1(ctx):
    t = tok()
    ctx.data['tok'] = t
    req(ctx, f'空のbareリポジトリ remote.git を作ってリモートに見立て（git init --bare、既定ブランチはmain）、それを work へcloneします。'
             f'work に memo.txt（中身は {t} だけ）をcommitし、上流を設定してmainへpushしてください。')


def c1(ctx):
    t = ctx.data['tok']
    ctx.require(os.path.isdir(ctx.p('remote.git')), 'remote.git がありません。')
    ctx.require(g(ctx, 'remote.git', 'rev-parse', '--is-bare-repository') == 'true', 'remote.git はbareリポジトリにします（git init --bare）。')
    rc, out = gr(ctx, 'remote.git', 'show', 'main:memo.txt')
    ctx.require(rc == 0 and out == t, 'remote.git のmainに、中身が指定トークンだけの memo.txt がありません。pushしましたか。')
    need_repo(ctx, 'work')
    url = g(ctx, 'work', 'remote', 'get-url', 'origin')
    ctx.require(os.path.realpath(ctx.p('remote.git')) == os.path.realpath(os.path.join(str(ctx.p('work')), url)), 'work の origin が remote.git を指していません（clone で作ります）。')
    rc, up = gr(ctx, 'work', 'rev-parse', '--abbrev-ref', '@{u}')
    ctx.require(rc == 0 and up == 'origin/main', '上流が origin/main になっていません（push -u）。')
    ctx.require(g(ctx, 'work', 'status', '--porcelain') == '', 'work に未コミットの変更が残っています。')


SOL1 = r'''git init --bare -b main remote.git
git clone remote.git work
cd work
git config user.name trainee
git config user.email trainee@example.test
echo '<<tok>>' > memo.txt
git add memo.txt
git commit -m 'add memo'
git push -u origin HEAD:main'''
mission(1, 'init・clone・bareリポジトリをリモートに見立てる',
        'GitHubに出す前に手元で動きを確かめたい。git init --bare で作った空の共有場所を「リモート」に見立て、git clone で作業コピーを作って最初のpushまで通します。',
        ['remote.git がbareで、mainに memo.txt が入っている', 'work が remote.git のcloneで上流が origin/main'], s1, c1, SOL1,
        ["git init work\ncd work\necho '<<tok>>' > memo.txt\ngit add memo.txt\ngit commit -m 'add memo'",
         "git init --bare -b main remote.git\ngit clone remote.git work\ncd work\necho '<<tok>>' > memo.txt\ngit add memo.txt\ngit -c user.name=a -c user.email=a@b.c commit -m x"],
        'git init は .git を作って履歴を始める操作で、--bare は作業ツリーを持たない共有用リポジトリ（サーバー側の形）を作ります。git clone は履歴ごと複製し、元を origin という名前のremoteとして記録します。空のリポジトリをcloneしても動き、最初のpushで HEAD:main のようにブランチ名を明示して push -u すると、上流(origin/main)の対応付けまで一度に済みます。',
        'bareは「中央」、cloneは「手元」の関係です。', 'git init --bare / git clone / git add / git commit / git push -u')


# ============================================================ 2 add -p
def s2(ctx):
    t = tok()
    top = secrets.randbelow(2) == 0
    nt = 60 + 10 * secrets.randbelow(5)
    lines = ['timeout=30'] + [f'opt{i:02d}=on' for i in range(2, 29)] + ['debug=false']
    mk(ctx, 'repo')
    ctx.data['base'] = cm(ctx, 'repo', 'base', {'app.conf': '\n'.join(lines) + '\n'})
    new = lines[:]
    new[0] = f'timeout={nt}'
    new[-1] = 'debug=true'
    ctx.write('repo/app.conf', '\n'.join(new) + '\n')
    ctx.data.update(tok=t, top=top, nt=nt, ans=r'y\nn\n' if top else r'n\ny\n')
    what = 'timeout の変更' if top else 'debug の変更'
    req(ctx, f'repo/app.conf には離れた2か所の変更（timeout と debug）が混ざっています。{what}だけをgit add -pでステージしてcommitし、もう一方は未ステージのまま作業ツリーに残してください。')


def c2(ctx):
    d = ctx.data
    need_repo(ctx, 'repo')
    ctx.require(g(ctx, 'repo', 'rev-parse', 'HEAD') != d['base'], 'まだcommitしていません。')
    ctx.require(rev(ctx, 'repo', 'HEAD~1') == d['base'], 'commitは1つだけ作ります。')
    show = g(ctx, 'repo', 'show', 'HEAD:app.conf').splitlines()
    cur = (ctx.read('repo/app.conf') or '').splitlines()
    ctx.require(f'timeout={d["nt"]}' in cur and 'debug=true' in cur, '作業ツリーの変更を消してはいけません。')
    if d['top']:
        ctx.require(f'timeout={d["nt"]}' in show and 'debug=false' in show, 'commitには timeout の変更だけを含めます。')
    else:
        ctx.require('timeout=30' in show and 'debug=true' in show, 'commitには debug の変更だけを含めます。')
    ctx.require(gr(ctx, 'repo', 'diff', '--cached', '--quiet')[0] == 0, 'ステージに変更が残っています。')
    ctx.require(gr(ctx, 'repo', 'diff', '--quiet')[0] == 1, '残りの変更は未ステージで作業ツリーに残します。')


SOL2 = r'''cd repo
printf '<<ans>>' | git add -p
git commit -m 'tune config\''''.replace("\\''", "'")
mission(2, 'git add -p でhunk単位にステージする',
        'デバッグ用の一時変更と本命の修正が同じファイルに混ざりました。まとめてcommitすると一時変更まで履歴に残ります。git add -p で必要なhunkだけを選んでください（対話の応答は printf でパイプできます）。',
        ['選んだ変更だけがcommitされる', '残りは未ステージで作業ツリーに残る'], s2, c2, SOL2,
        ["cd repo\ngit commit -am 'all'", "cd repo\ngit add -A\ngit commit -m 'all'"],
        'git add -p は変更をhunkに分け、y(ステージ)・n(見送り)・s(分割)・e(手編集)で選びます。標準入力から y/n を流せば非対話でも実行できます。選んだ後は git diff --cached で内容を確認してからcommitします。commit -a は全部を入れてしまうので、混在変更には使いません。',
        '2つの変更は離れているので別々のhunkになります。', 'git add -p（printfで y/n を渡す）と git diff --cached')


# ============================================================ 3 commit --amend
def s3(ctx):
    t = tok()
    mk(ctx, 'repo')
    cm(ctx, 'repo', 'base', {'a.txt': 'a\n'})
    par = cm(ctx, 'repo', 'second', {'a.txt': 'a\nb\n'})
    old = cm(ctx, 'repo', f'fix: {t} mesage', {'fix.txt': 'fix\n'})
    ctx.write('repo/notes.txt', f'notes {t}\n')
    ctx.data.update(tok=t, par=par, old=old, n=int(g(ctx, 'repo', 'rev-list', '--count', 'HEAD')))
    req(ctx, f'直前のcommit「fix: {t} mesage」は、メッセージの誤字（mesage）と、notes.txt の入れ忘れがあります。新しいcommitを増やさず、直前のcommitを修正して「fix: {t} message」にし、notes.txt も含めてください。')


def c3(ctx):
    d = ctx.data
    need_repo(ctx, 'repo')
    ctx.require(g(ctx, 'repo', 'rev-parse', 'HEAD') != d['old'], 'まだ直前のcommitを作り直していません。')
    ctx.require(int(g(ctx, 'repo', 'rev-list', '--count', 'HEAD')) == d['n'], 'commitの数を増やさず、直前のものを置き換えます。')
    ctx.require(rev(ctx, 'repo', 'HEAD~1') == d['par'], '1つ前までの履歴は変えません。')
    ctx.require(g(ctx, 'repo', 'log', '-1', '--format=%s') == f'fix: {d["tok"]} message', 'メッセージが違います。')
    ctx.require(gr(ctx, 'repo', 'cat-file', '-e', 'HEAD:notes.txt')[0] == 0, 'notes.txt が直前のcommitに入っていません。')
    ctx.require(g(ctx, 'repo', 'status', '--porcelain') == '', '作業ツリーに変更が残っています。')


SOL3 = '''cd repo
git add notes.txt
git commit --amend -m 'fix: <<tok>> message\''''.replace("\\''", "'")
mission(3, 'git commit --amend で直前のcommitを直す',
        'pushする前に気づいた、直前commitのメッセージの誤字と入れ忘れたファイル。別のcommitを積まず、直前のcommit自体を作り直します。',
        ['メッセージを直す', 'notes.txt を同じcommitに含める', 'commit数は増えない'], s3, c3, SOL3,
        ["cd repo\ngit add notes.txt\ngit commit -m 'fix: <<tok>> message'", "cd repo\ngit commit --amend -m 'fix: <<tok>> message'"],
        'git commit --amend は直前のcommitを、ステージ内容と新しいメッセージで作り直します（親は同じで、コミットIDは変わる）。--no-edit ならメッセージはそのままです。pushした後のcommitに使うと履歴が書き換わるので、共有前の修正に限ります。',
        'amendは「新しく足す」のではなく「置き換える」操作です。', 'git add のあと git commit --amend')


# ============================================================ 4 branch / switch / restore
def s4(ctx):
    t = tok()
    mk(ctx, 'repo')
    c1 = cm(ctx, 'repo', 'v1', {'config.ini': 'level=1\n', 'app.txt': 'one\n'})
    g(ctx, 'repo', 'tag', 'v1.0')
    c2 = cm(ctx, 'repo', 'v2', {'app.txt': 'two\n'})
    g(ctx, 'repo', 'branch', f'merged-{t}')
    c3 = cm(ctx, 'repo', 'v3', {'app.txt': 'three\n'})
    g(ctx, 'repo', 'branch', f'wip-typo-{t}')
    g(ctx, 'repo', 'switch', '-q', '-c', f'unmerged-{t}')
    cm(ctx, 'repo', 'unmerged work', {'u.txt': 'u\n'})
    g(ctx, 'repo', 'switch', '-q', 'main')
    ctx.write('repo/config.ini', 'level=99\n')
    ctx.write('repo/draft.txt', f'draft {t}\n')
    g(ctx, 'repo', 'add', 'draft.txt')
    ctx.data.update(tok=t, c1=c1, c3=c3)
    req(ctx, f'①config.ini の誤編集を破棄 ②draft.txt はステージだけ取り消す（ファイルは残す） ③ブランチ wip-typo-{t} を feature/{t} に改名 '
             f'④マージ済みの merged-{t} を安全に削除（未マージの unmerged-{t} は残す） ⑤タグ v1.0 から hotfix/{t} を作って、そのブランチに切り替える。')


def c4(ctx):
    d = ctx.data
    t = d['tok']
    need_repo(ctx, 'repo')
    br = g(ctx, 'repo', 'for-each-ref', 'refs/heads', '--format=%(refname:short)').split()
    ctx.require(f'feature/{t}' in br and f'wip-typo-{t}' not in br, f'wip-typo-{t} を feature/{t} に改名します（git branch -m）。')
    ctx.require(rev(ctx, 'repo', f'feature/{t}') == d['c3'], '改名のため、内容（コミット）は変えません。')
    ctx.require(f'merged-{t}' not in br, f'merged-{t} を削除します（git branch -d）。')
    ctx.require(f'unmerged-{t}' in br, f'unmerged-{t} は未マージの作業です。消してはいけません。')
    ctx.require(f'hotfix/{t}' in br and rev(ctx, 'repo', f'hotfix/{t}') == d['c1'], f'hotfix/{t} はタグ v1.0 の位置から作ります。')
    ctx.require(g(ctx, 'repo', 'branch', '--show-current') == f'hotfix/{t}', 'hotfix ブランチに切り替えます（git switch -c）。')
    ctx.require(ctx.read('repo/config.ini') == 'level=1\n', 'config.ini の変更を破棄します（git restore）。')
    ctx.require('draft.txt' not in g(ctx, 'repo', 'ls-files').split() and (ctx.read('repo/draft.txt') or '').startswith('draft'),
                'draft.txt はステージだけ取り消し、ファイルは残します（git restore --staged）。')


SOL4 = '''cd repo
git restore config.ini
git restore --staged draft.txt
git branch -m wip-typo-<<tok>> feature/<<tok>>
git branch -d merged-<<tok>>
git switch -c hotfix/<<tok>> v1.0'''
mission(4, 'branch・switch・restoreで整理する',
        '作業ツリーが散らかっています。誤編集の破棄、ステージの取り消し、ブランチの改名・削除・作成を、安全な専用コマンドで行います。',
        ['restoreでconfig.iniを戻しdraft.txtはunstage', 'branch -m / -d で改名と削除', 'switch -c でタグから作成して切替'], s4, c4, SOL4,
        ["cd repo\ngit reset --hard\ngit branch -m wip-typo-<<tok>> feature/<<tok>>\ngit branch -D merged-<<tok>> unmerged-<<tok>>\ngit switch -c hotfix/<<tok>> v1.0",
         "cd repo\ngit branch -m wip-typo-<<tok>> feature/<<tok>>\ngit branch -d merged-<<tok>>\ngit switch -c hotfix/<<tok>> v1.0"],
        'git switch はブランチ切替専用、git restore はファイル復元専用に checkout を分けたコマンドです。restore <file> は作業ツリーをindexから戻し、restore --staged <file> はindexをHEADに戻して作業ツリーの内容は残します（--source=<commit> で任意の版から戻せます）。branch -m は改名、-d はマージ済みのみ削除（未マージは拒否され、-D で強制）です。reset --hard はステージ中の新規ファイルも失うので、局所的な restore を使います。',
        '「ファイル」の操作は restore、「ブランチ」の操作は branch/switch です。', 'git restore / git restore --staged / git branch -m -d / git switch -c')


# ============================================================ 5 reset
def s5(ctx):
    t = tok()
    for r in ('soft', 'mixed', 'hard'):
        mk(ctx, r)
        cm(ctx, r, 'c1', {'data.txt': 'v1\n'})
        ctx.data['base_' + r] = cm(ctx, r, 'c2', {'data.txt': 'v1\nv2\n'})
        cm(ctx, r, f'c3 {t}', {'data.txt': 'v1\nv2\nv3\n'})
    req(ctx, 'soft・mixed・hard の3つのリポジトリで、直前のcommit(c3)を取り消します。soft はcommitだけ取り消して変更はステージに残す、'
             'mixed は変更を未ステージで残す、hard は変更ごと完全に捨てる。それぞれ git reset のモードを使い分けてください。')


def c5(ctx):
    d = ctx.data
    for r in ('soft', 'mixed', 'hard'):
        need_repo(ctx, r)
        ctx.require(rev(ctx, r, 'HEAD') == d['base_' + r], f'{r}: HEADをc2へ戻します。')
    cur = lambda r: ctx.read(r + '/data.txt') or ''
    ctx.require(g(ctx, 'soft', 'diff', '--cached', '--name-only') == 'data.txt' and gr(ctx, 'soft', 'diff', '--quiet')[0] == 0 and 'v3' in cur('soft'),
                'soft: c3の変更はステージに残ります（--soft）。')
    ctx.require(gr(ctx, 'mixed', 'diff', '--cached', '--quiet')[0] == 0 and g(ctx, 'mixed', 'diff', '--name-only') == 'data.txt' and 'v3' in cur('mixed'),
                'mixed: c3の変更は未ステージの作業ツリーに残ります（--mixed）。')
    ctx.require(g(ctx, 'hard', 'status', '--porcelain') == '' and 'v3' not in cur('hard'), 'hard: c3の変更ごと消えます（--hard）。')


SOL5 = '''git -C soft reset --soft HEAD~1
git -C mixed reset --mixed HEAD~1
git -C hard reset --hard HEAD~1'''
mission(5, 'reset --soft・--mixed・--hard の違い',
        'c3を取り消したいが、変更の行き先が違います。HEAD・index・作業ツリーのどこまで戻すかを、3つのモードで使い分けます。',
        ['soft: 変更はステージに残る', 'mixed: 未ステージで残る', 'hard: 変更も消える'], s5, c5, SOL5,
        ["git -C soft reset --mixed HEAD~1\ngit -C mixed reset --mixed HEAD~1\ngit -C hard reset --mixed HEAD~1", "git -C soft reset --hard HEAD~1\ngit -C mixed reset --hard HEAD~1\ngit -C hard reset --hard HEAD~1"],
        'git reset は HEAD(ブランチ)を動かし、--soft は動かすだけ、--mixed(既定)はさらにindexを戻し、--hard は作業ツリーまで戻します。つまり変更の行き先は、soft=ステージ、mixed=未ステージ、hard=消滅です。hardで消えた変更も reflog から取り戻せますが、未commitの変更は戻せないので注意します。',
        'HEAD → index → 作業ツリー の順に戻る範囲が広がります。', 'git reset --soft / --mixed / --hard HEAD~1')


# ============================================================ 6 revert
def s6(ctx):
    t = tok()
    mk(ctx, 'repo')
    c1 = cm(ctx, 'repo', 'base', {'README': 'r\n'})
    c2 = cm(ctx, 'repo', f'add a {t}', {'a.txt': 'a\n'})
    c3 = cm(ctx, 'repo', f'add buggy {t}', {'bug.txt': 'bug\n'})
    c4 = cm(ctx, 'repo', f'add b {t}', {'b.txt': 'b\n'})
    ctx.data.update(tok=t, cs=[c1, c2, c3, c4])
    req(ctx, f'「add buggy {t}」が本番で問題を起こしました。すでに共有済みなので履歴は書き換えず、その変更だけを打ち消す新しいcommitを積んでください（前後のcommitは残す）。')


def c6(ctx):
    d = ctx.data
    need_repo(ctx, 'repo')
    c1, c2, c3, c4 = d['cs']
    ctx.require(rev(ctx, 'repo', 'HEAD~1') == c4 and int(g(ctx, 'repo', 'rev-list', '--count', 'HEAD')) == 5,
                '既存のcommitを残したまま、新しいcommitを1つだけ積みます（reset で巻き戻さない）。')
    ctx.require(g(ctx, 'repo', 'log', '-1', '--format=%s').startswith('Revert'), '打ち消しcommitは revert で作ります。')
    ctx.require(gr(ctx, 'repo', 'cat-file', '-e', 'HEAD:bug.txt')[0] != 0, 'bug.txt が残っています。')
    ctx.require(all(gr(ctx, 'repo', 'cat-file', '-e', 'HEAD:' + f)[0] == 0 for f in ('a.txt', 'b.txt')), '他の変更(a.txt/b.txt)は残します。')


SOL6 = '''cd repo
git revert --no-edit "$(git log --grep='add buggy <<tok>>' --format=%H -n 1)"'''
mission(6, 'git revert で共有済みの変更を打ち消す',
        '共有済みのcommitを取り消すには、履歴を書き換える reset ではなく、逆向きの変更を新しいcommitとして積みます。',
        ['問題のcommitを打ち消すRevertが1つ増える', '前後のcommitは履歴に残る'], s6, c6, SOL6,
        ["cd repo\ngit reset --hard HEAD~2", "cd repo\ngit reset --hard HEAD~1\ngit revert --no-edit HEAD"],
        'git revert <commit> は対象の逆パッチを新しいcommitにします。履歴を書き換えないので共有ブランチでも安全です。マージcommitを打ち消すときは、どちらの親側を残すか -m 1 で指定します。revert自体をrevertすれば元に戻せます。',
        '「取り消し」は reset（書き換え）か revert（打ち消しを追加）。共有済みは後者です。', 'git log --grep でIDを探し git revert --no-edit')


# ============================================================ 7 merge conflict
def s7(ctx):
    a, b, r = 40 + secrets.randbelow(50), 100 + secrets.randbelow(50), 2 + secrets.randbelow(7)
    base = ['[net]', 'host=example.test', 'timeout=30', '; pad1', '; pad2', '; pad3', '; pad4', '[log]', 'level=info']
    mk(ctx, 'repo')
    cm(ctx, 'repo', 'base', {'settings.conf': '\n'.join(base) + '\n'})
    g(ctx, 'repo', 'switch', '-q', '-c', 'feature/x')
    f = base[:]
    f[2] = f'timeout={b}'
    f.insert(3, f'retries={r}')
    f[-1] = 'level=debug'
    ft = cm(ctx, 'repo', 'feature change', {'settings.conf': '\n'.join(f) + '\n'})
    g(ctx, 'repo', 'switch', '-q', 'main')
    m = base[:]
    m[2] = f'timeout={a}'
    mt = cm(ctx, 'repo', 'main change', {'settings.conf': '\n'.join(m) + '\n'})
    exp = base[:]
    exp[2] = f'timeout={a}'
    exp.insert(3, f'retries={r}')
    exp[-1] = 'level=debug'
    ctx.data.update(a=a, r=r, ft=ft, mt=mt, exp='\n'.join(exp) + '\n')
    req(ctx, f'main に feature/x を merge します。timeout の行が両方で変わっているので衝突します。解消方針: timeout は main 側の値（{a}）、feature/x が足した retries={r} と level=debug は取り込む。'
             'マーカー(<<<<<<< ======= >>>>>>>)を残さず、解消した状態でmerge commitを完成させてください。')


def c7(ctx):
    d = ctx.data
    need_repo(ctx, 'repo')
    ctx.require(gr(ctx, 'repo', 'rev-parse', '-q', '--verify', 'MERGE_HEAD')[0] != 0, 'mergeが途中のままです。解消してcommitまで進めます。')
    ctx.require(gr(ctx, 'repo', 'grep', '-qE', '^(<<<<<<<|=======|>>>>>>>)', 'HEAD', '--', 'settings.conf')[0] != 0, 'commitされたファイルに衝突マーカーが残っています。')
    ctx.require(g(ctx, 'repo', 'show', 'HEAD:settings.conf') + '\n' == d['exp'], f'解消後の内容が方針と違います（timeout={d["a"]}、retries={d["r"]}、level=debug）。')
    ps = g(ctx, 'repo', 'log', '-1', '--format=%P').split()
    ctx.require(ps == [d['mt'], d['ft']], 'main と feature/x を親に持つmerge commitにします。')
    ctx.require(g(ctx, 'repo', 'ls-files', '-u') == '' and g(ctx, 'repo', 'status', '--porcelain') == '', '未解決の項目や変更が残っています。')


SOL7 = '''cd repo
git merge feature/x || true
sed -i -e '/^<<<<<<< /d' -e '/^=======$/,/^>>>>>>> /d' settings.conf
sed -i '/^timeout=/a retries=<<r>>' settings.conf
git add settings.conf
git commit --no-edit'''
mission(7, 'merge の衝突を解消して整合を確認する',
        '同じ行を別々に変更した2つのブランチを merge すると衝突します。マーカーを取り除いて意図した内容にし、git add で解消済みにしてmerge commitを完成させます。',
        ['衝突を方針どおりに解消', 'マーカーが残らない', '2つの親を持つmerge commit'], s7, c7, SOL7,
        ["cd repo\ngit merge feature/x || true\ngit add -A\ngit commit --no-edit", "cd repo\ngit merge feature/x || true\ngit checkout --ours settings.conf\ngit add settings.conf\ngit commit --no-edit",
         "cd repo\ngit merge feature/x || true\ngit merge --abort"],
        'merge の衝突は、ファイルに <<<<<<< (自分側) ======= (相手側) >>>>>>> が書き込まれ、indexに未解決(git ls-files -u)として残ります。内容を整えたら git add で解消を宣言し git commit で完成させます。マーカー付きのまま add すると、そのまま履歴に入るので、git diff --check や grep で残りを確認します。やり直すときは git merge --abort です。',
        '衝突部分だけ手で直し、衝突していない level=debug は自動で入ります。', 'git merge / sed や エディタで編集 / git add / git commit --no-edit')


# ============================================================ 8 rebase
def s8(ctx):
    t = tok()
    mk(ctx, 'repo')
    cm(ctx, 'repo', 'base', {'README': 'r\n'})
    g(ctx, 'repo', 'switch', '-q', '-c', 'feature')
    subs = [f'f1 {t}', f'f2 {t}', f'f3 {t}']
    for i, s in enumerate(subs, 1):
        cm(ctx, 'repo', s, {f'f{i}.txt': f'{i}\n'})
    g(ctx, 'repo', 'switch', '-q', 'main')
    cm(ctx, 'repo', 'm1', {'m1.txt': '1\n'})
    mt = cm(ctx, 'repo', 'm2', {'m2.txt': '2\n'})
    g(ctx, 'repo', 'switch', '-q', 'feature')
    ctx.data.update(subs=subs, mt=mt)
    req(ctx, 'feature は古いmainから分岐していて、その後mainが2つ進みました。merge commit を作らず、feature の3つのcommitを最新のmainの先頭へ付け替えて、履歴を一直線にしてください。')


def c8(ctx):
    d = ctx.data
    need_repo(ctx, 'repo')
    ctx.require(rev(ctx, 'repo', 'main') == d['mt'], 'mainは変えません。')
    ctx.require(g(ctx, 'repo', 'merge-base', 'main', 'feature') == d['mt'], 'featureがmainの先頭から始まっていません（rebase）。')
    ctx.require(g(ctx, 'repo', 'rev-list', '--merges', 'main..feature') == '', 'merge commitが入っています。rebaseで直線にします。')
    got = g(ctx, 'repo', 'log', '--format=%s', 'main..feature').splitlines()[::-1]
    ctx.require(got == d['subs'], 'featureの3つのcommitを順序・メッセージそのままで残します。')


SOL8 = '''cd repo
git switch feature
git rebase main'''
mission(8, 'git rebase で最新のmainへ付け替える',
        'mergeすると合流のcommitが増えて履歴が枝分かれします。rebaseでブランチの根元を付け替え、一直線の履歴にします。',
        ['featureの3つのcommitが残る', 'mainの先頭の上に載る', 'merge commitなし'], s8, c8, SOL8,
        ["cd repo\ngit merge main", "cd repo\ngit switch main\ngit rebase feature"],
        'git rebase main は、featureのcommit群を一度外してmainの先頭に順に当て直します（コミットIDは変わる）。履歴が一直線になり読みやすくなる一方、公開済みブランチに行うと他人の履歴と食い違うので、自分のブランチ限定です。衝突したら解消して git rebase --continue、やめるなら --abort です。',
        '付け替えるのは feature のほうです。', 'git switch feature / git rebase main')


# ============================================================ 9 rebase -i
def s9(ctx):
    t = tok()
    mk(ctx, 'repo')
    cm(ctx, 'repo', 'base', {'README': 'r\n'})
    g(ctx, 'repo', 'switch', '-q', '-c', 'feature')
    cm(ctx, 'repo', f'feat: parser {t}', {'parser.py': 'def parse():\n    pass\n'})
    cm(ctx, 'repo', 'oops typo', {'parser.py': 'def parse():\n    pass\n# fix\n'})
    cm(ctx, 'repo', 'tmp', {'parser.py': 'def parse():\n    pass\n# fix\n# tmp\n'})
    cm(ctx, 'repo', f'docs: updat {t} mesage', {'docs.md': 'docs\n'})
    ctx.data.update(tok=t, tree=g(ctx, 'repo', 'rev-parse', 'HEAD^{tree}'))
    req(ctx, f'feature の4つのcommitを2つに整理します。2番目(oops typo)は fixup、3番目(tmp)は squash で先頭に畳み込み、4番目の誤字入りメッセージ「docs: updat {t} mesage」は reword で「docs: update {t} message」にします。'
             'エディタは開かず、GIT_SEQUENCE_EDITOR と GIT_EDITOR を sed で指定して git rebase -i main を自動実行してください。内容(ツリー)は変えません。')


def c9(ctx):
    d = ctx.data
    t = d['tok']
    need_repo(ctx, 'repo')
    ctx.require(gr(ctx, 'repo', 'rev-parse', '--git-path', 'rebase-merge')[0] == 0 and not os.path.exists(os.path.join(str(ctx.p('repo')), g(ctx, 'repo', 'rev-parse', '--git-path', 'rebase-merge'))),
                'rebaseが途中です。')
    ctx.require(g(ctx, 'repo', 'branch', '--show-current') == 'feature', 'featureブランチ上で完了させます。')
    ctx.require(g(ctx, 'repo', 'rev-list', '--count', 'main..feature') == '2', 'featureは2つのcommitにします。')
    ctx.require(g(ctx, 'repo', 'rev-parse', 'HEAD^{tree}') == d['tree'], '整理しても最終的な内容は変わりません。')
    ctx.require(g(ctx, 'repo', 'log', '-1', '--format=%s') == f'docs: update {t} message', f'最後のcommitを「docs: update {t} message」にreword します。')
    ctx.require(g(ctx, 'repo', 'log', '-1', '--format=%s', 'HEAD~1') == f'feat: parser {t}', '先頭のcommitの件名は変えません。')


SOL9 = '''cd repo
GIT_SEQUENCE_EDITOR="sed -i -e '2s/^pick/fixup/' -e '3s/^pick/squash/' -e '4s/^pick/reword/'" \\
GIT_EDITOR="sed -i -e 's/updat /update /' -e 's/mesage/message/'" \\
git rebase -i main'''
mission(9, 'rebase -i で squash・fixup・reword を自動化する',
        'PRに出す前に、wipや誤字のcommitを整えます。通常は rebase -i のエディタで todo を書き換えますが、GIT_SEQUENCE_EDITOR にsedを指定すれば自動化できます。',
        ['squash/fixupで2commitへ', 'rewordで件名を直す', '対話エディタを使わず実行'], s9, c9, SOL9,
        ["cd repo\nGIT_SEQUENCE_EDITOR=true git rebase -i main", "cd repo\nGIT_SEQUENCE_EDITOR=\"sed -i -e '2s/^pick/fixup/' -e '3s/^pick/squash/'\" git rebase -i main"],
        'git rebase -i の todo は pick/reword/squash/fixup などで1行ずつ操作を決めます。fixup はメッセージを捨てて直前に統合、squash はメッセージも結合、reword は件名の編集です。GIT_SEQUENCE_EDITOR はtodoを編集するコマンド、GIT_EDITOR はcommitメッセージを編集するコマンドで、どちらも sed -i で非対話にできます。実行前後の tree が同じなら内容は保たれています。',
        'todo の行番号は古い順に並びます。', 'GIT_SEQUENCE_EDITOR（todo用）と GIT_EDITOR（メッセージ用）に sed -i を指定')


# ============================================================ 10 cherry-pick
def s10(ctx):
    t = tok()
    mk(ctx, 'repo')
    c0 = cm(ctx, 'repo', 'base', {'README': 'r\n'})
    g(ctx, 'repo', 'switch', '-q', '-c', 'dev')
    cm(ctx, 'repo', 'feat: x', {'x.txt': 'x\n'})
    fx = cm(ctx, 'repo', f'hotfix-{t}: fix crash', {'fix.txt': f'fixed {t}\n'})
    cm(ctx, 'repo', 'feat: y', {'y.txt': 'y\n'})
    g(ctx, 'repo', 'switch', '-q', '-c', 'release', c0)
    cm(ctx, 'repo', 'release prep', {'REL': '1\n'})
    g(ctx, 'repo', 'switch', '-q', 'main')
    ctx.data.update(tok=t, c0=c0, fx=fx)
    req(ctx, f'dev には開発中の変更が3つあり、そのうち「hotfix-{t}: fix crash」だけを release ブランチに取り込みます。どのcommitから来たか分かるよう記録も残してください。')


def c10(ctx):
    d = ctx.data
    need_repo(ctx, 'repo')
    ctx.require(g(ctx, 'repo', 'show', 'release:fix.txt') == f'fixed {d["tok"]}', 'release に hotfix の変更が入っていません。')
    ctx.require(gr(ctx, 'repo', 'cat-file', '-e', 'release:x.txt')[0] != 0 and gr(ctx, 'repo', 'cat-file', '-e', 'release:y.txt')[0] != 0, '他のdevの変更まで入っています。')
    ctx.require(g(ctx, 'repo', 'rev-list', '--count', d['c0'] + '..release') == '2', 'release に積むのは hotfix の1commitだけです。')
    ctx.require(f'(cherry picked from commit {d["fx"]})' in g(ctx, 'repo', 'log', '-1', '--format=%B', 'release'), '取り込み元を記録します（cherry-pick -x）。')


SOL10 = '''cd repo
git switch release
git cherry-pick -x "$(git log dev --grep='hotfix-<<tok>>' --format=%H -n 1)"'''
mission(10, 'cherry-pick で特定のcommitだけを取り込む',
        '修正だけを別のブランチへ運びたいとき、mergeでは余計な変更まで付いてきます。cherry-pick は選んだcommitの変更だけを当てます。',
        ['releaseにhotfixだけが入る', '取り込み元のIDが記録される'], s10, c10, SOL10,
        ["cd repo\ngit switch release\ngit merge dev", "cd repo\ngit switch release\ngit cherry-pick \"$(git log dev --grep='hotfix-<<tok>>' --format=%H -n 1)\""],
        'git cherry-pick <commit> は、そのcommitの差分を現在のブランチに新しいcommitとして適用します（IDは変わる）。-x を付けるとメッセージに「cherry picked from commit ...」が残り、後で追跡できます。範囲指定や、衝突時の --continue/--abort も使えます。',
        'IDは git log --grep で探せます。', 'git switch release / git cherry-pick -x')


# ============================================================ 11 stash
def s11(ctx):
    t = tok()
    mk(ctx, 'repo')
    cm(ctx, 'repo', 'base', {'app.py': 'v1\n', 'notes.txt': 'notes\n'})
    g(ctx, 'repo', 'switch', '-q', '-c', 'hotfix')
    ht = cm(ctx, 'repo', 'hotfix base', {'scratch.txt': 'tracked on hotfix\n'})
    g(ctx, 'repo', 'switch', '-q', 'main')
    ctx.write('repo/notes.txt', 'notes\nold idea\n')
    g(ctx, 'repo', 'stash', 'push', '-q', '-m', f'old-{t}')
    ctx.write('repo/app.py', 'v1\nwip\n')
    ctx.write('repo/scratch.txt', 'my scratch\n')
    ctx.data.update(tok=t, ht=ht)
    req(ctx, f'main の作業中(app.py の編集と未追跡の scratch.txt)に、hotfix ブランチで緊急対応が入りました。hotfix にも scratch.txt があるため、そのままでは切り替えられません。'
             f'①未追跡ファイルを含めて「wip-{t}」の名前で退避 ②hotfix に切り替えてcommitを1つ作る ③main に戻って退避を pop で復元（スタックから消す） '
             f'④過去に退避済みの old-{t} は apply で notes.txt に適用（スタックには残す）。')


def c11(ctx):
    d = ctx.data
    t = d['tok']
    need_repo(ctx, 'repo')
    ctx.require(g(ctx, 'repo', 'branch', '--show-current') == 'main', 'main に戻ります。')
    ctx.require(ctx.read('repo/app.py') == 'v1\nwip\n' and ctx.read('repo/scratch.txt') == 'my scratch\n', 'wip の作業(app.py と未追跡の scratch.txt)がmainの作業ツリーに復元されていません。')
    ctx.require(ctx.read('repo/notes.txt') == 'notes\nold idea\n', f'old-{t} の内容が notes.txt に適用されていません。')
    st = g(ctx, 'repo', 'stash', 'list').splitlines()
    ctx.require(len(st) == 1 and f'old-{t}' in st[0], f'スタックには old-{t} だけ残します（wip は pop、old は apply）。')
    ctx.require(rev(ctx, 'repo', 'hotfix') != d['ht'] and gr(ctx, 'repo', 'merge-base', '--is-ancestor', d['ht'], 'hotfix')[0] == 0, 'hotfix ブランチにcommitを1つ以上積みます。')


SOL11 = '''cd repo
git stash push -u -m "wip-<<tok>>"
git switch hotfix
echo fixed > hotfix.txt
git add hotfix.txt
git commit -m "hotfix <<tok>>"
git switch main
git stash pop
git stash apply'''
mission(11, 'stash の push -u・pop・apply を使い分ける',
        '作業の途中で別ブランチへ移る必要が出ました。stash に一時退避し、戻って復元します。未追跡ファイルを含める -u、復元して消す pop、残す apply の違いが重要です。',
        ['stash push -u で未追跡も退避', 'pop で復元しスタックから消す', 'apply で復元しスタックに残す'], s11, c11, SOL11,
        ["cd repo\ngit stash push -m wip-<<tok>>\ngit switch hotfix\necho fixed > hotfix.txt\ngit add hotfix.txt\ngit commit -m 'hotfix'\ngit switch main\ngit stash pop",
         "cd repo\ngit stash push -u -m wip-<<tok>>\ngit switch hotfix\necho fixed > hotfix.txt\ngit add hotfix.txt\ngit commit -m 'hotfix'\ngit switch main\ngit stash pop\ngit stash pop"],
        'git stash push は追跡中の変更を退避し、-u で未追跡ファイルも、-m で名前を付けます（-a は無視ファイルも）。git stash pop は復元してそのエントリを消し、git stash apply は復元しても残すので、複数ブランチへ同じ変更を当てたいときに使います。git stash list で一覧を確認し、stash@{n} で個別指定できます。',
        '未追跡を含めないと切り替えが失敗します。', 'git stash push -u -m / git stash pop / git stash apply')


# ============================================================ 12 reflog
def s12(ctx):
    t = tok()
    mk(ctx, 'repo')
    c1 = cm(ctx, 'repo', 'c1', {'a.txt': '1\n'})
    c2 = cm(ctx, 'repo', 'c2', {'a.txt': '2\n'})
    cm(ctx, 'repo', 'c3', {'a.txt': '3\n'})
    c4 = cm(ctx, 'repo', f'release {t}', {'a.txt': '4\n'})
    g(ctx, 'repo', 'switch', '-q', '-c', f'feature/{t}', c2)
    cm(ctx, 'repo', 'f1', {'f.txt': '1\n'})
    f2 = cm(ctx, 'repo', f'feature end {t}', {'f.txt': '2\n'})
    g(ctx, 'repo', 'switch', '-q', 'main')
    g(ctx, 'repo', 'branch', '-D', f'feature/{t}')
    g(ctx, 'repo', 'reset', '-q', '--hard', c1)
    ctx.data.update(tok=t, c4=c4, f2=f2)
    req(ctx, f'事故が2つ起きました。main を git reset --hard で3つ巻き戻してしまった（元の先頭は「release {t}」）、'
             f'未マージだった feature/{t} を git branch -D で消してしまった（先頭は「feature end {t}」）。reflog から両方を元に戻してください。')


def c12(ctx):
    d = ctx.data
    t = d['tok']
    need_repo(ctx, 'repo')
    ctx.require(g(ctx, 'repo', 'branch', '--show-current') == 'main' and rev(ctx, 'repo', 'main') == d['c4'], 'main を事故前の先頭(release)へ戻します。')
    ctx.require(g(ctx, 'repo', 'status', '--porcelain') == '', '作業ツリーを整合させます（reset --hard）。')
    rc, v = gr(ctx, 'repo', 'rev-parse', '--verify', '-q', f'refs/heads/feature/{t}^{{commit}}')
    ctx.require(rc == 0 and v == d['f2'], f'feature/{t} を消す前の先頭に作り直します。')


SOL12 = '''cd repo
git reflog | head
git reset --hard "$(git log -g --grep='release <<tok>>' --format=%H -n 1)"
git branch feature/<<tok>> "$(git log -g --grep='feature end <<tok>>' --format=%H -n 1)"'''
mission(12, 'reflogで誤削除・巻き戻しを復旧する',
        'reset --hard やブランチ削除で「消えた」commitも、一定期間は reflog にHEADの移動履歴として残っています。見つけて元に戻します。',
        ['mainを事故前の位置へ', '削除したブランチを再作成'], s12, c12, SOL12,
        ["cd repo\ngit reset --hard ORIG_HEAD", "cd repo\ngit reset --hard \"$(git log -g --grep='release <<tok>>' --format=%H -n 1)\""],
        'git reflog はHEADやブランチが指していた位置の履歴（既定で約90日、到達不能は30日）です。git log -g でも同じ履歴を辿れ、--grep でメッセージから目的のcommitを探せます。見つけたIDに git reset --hard で戻す、git branch <名前> <ID> で再作成する、が基本の復旧です。reflogはローカルだけのもので、cloneには引き継がれません。',
        '消えたcommitのIDはreflogに残っています。', 'git reflog / git log -g --grep / git branch <名前> <ID>')


# ============================================================ 13 bisect
def s13(ctx):
    k = 4 + secrets.randbelow(8)
    mk(ctx, 'repo')
    shas = []
    lines = []
    for i in range(1, 15):
        lines.append(f'step {i}')
        if i == k:
            lines.append('mode=broken')
        shas.append(cm(ctx, 'repo', f'step {i}', {'state.txt': '\n'.join(lines) + '\n'}))
    g(ctx, 'repo', 'tag', 'good', shas[0])
    ctx.write('repo/test.sh', '#!/bin/sh\n! grep -q "mode=broken" state.txt\n', mode=0o755)
    ctx.data.update(bad=shas[k - 1])
    req(ctx, 'repo の履歴(14commit)のどこかで state.txt が壊れました（mode=broken が入る）。判定スクリプト test.sh（壊れていれば失敗）と、正常だった時点のタグ good があります。'
             '二分探索を自動実行して、最初に壊れたcommitのIDを culprit.txt（この課題フォルダ直下）に書き、探索状態も終了させてください。')


def c13(ctx):
    d = ctx.data
    need_repo(ctx, 'repo')
    v = resolve(ctx, 'repo', ctx.need_file('culprit.txt').strip(), 'culprit.txt')
    ctx.require(v == d['bad'], 'そのcommitは「最初に壊れた」ものではありません。bisect で特定します。')
    ctx.require(not os.path.exists(os.path.join(str(ctx.p('repo')), g(ctx, 'repo', 'rev-parse', '--git-path', 'BISECT_LOG'))), 'bisectが終了していません（git bisect reset）。')
    ctx.require(g(ctx, 'repo', 'branch', '--show-current') == 'main', 'main に戻します。')


SOL13 = '''cd repo
git bisect start HEAD good
git bisect run ./test.sh
git rev-parse refs/bisect/bad > ../culprit.txt
git bisect reset'''
mission(13, 'git bisect run で原因commitを自動特定する',
        '「いつから壊れたか」を履歴の二分探索で見つけます。判定スクリプトを渡せば、git bisect run が良い/悪いを自動で判定して原因を絞り込みます。',
        ['最初に壊れたcommitをculprit.txtへ', 'bisect reset で探索を終える'], s13, c13, SOL13,
        ["cd repo\ngit rev-parse HEAD~5 > ../culprit.txt", "cd repo\ngit bisect start HEAD good\ngit bisect run ./test.sh\ngit rev-parse refs/bisect/bad > ../culprit.txt"],
        'git bisect start <bad> <good> で範囲を決め、git bisect run <script> は終了コード0=良い、1〜127(125除く)=悪い として自動で二分探索します（125は判定不能でスキップ）。結果は refs/bisect/bad に入ります。最後に git bisect reset で元のブランチへ戻ります。手動なら git bisect good / bad を繰り返します。',
        '14個ならおよそ4回の判定で特定できます。', 'git bisect start / git bisect run ./test.sh / git bisect reset')


# ============================================================ 14 blame / log -S / -G
def s14(ctx):
    t = tok()
    u, rv = 20 + secrets.randbelow(30), 4 + secrets.randbelow(6)
    mk(ctx, 'repo')
    L = ['# auth module', 'MAX_USERS = 10', 'retry = 3', 'def login(user):', '    return True', '']
    al, bo, ca = ('Alice Dev', 'alice@example.test'), ('Bob Ops', 'bob@example.test'), ('Carol QA', 'carol@example.test')
    cm(ctx, 'repo', 'init auth', {'auth.py': '\n'.join(L)}, author=al)
    L2 = L + [f'def legacy_{t}():', '    return None', '']
    c2 = cm(ctx, 'repo', 'add legacy', {'auth.py': '\n'.join(L2)}, author=bo)
    L3 = [x.replace('MAX_USERS = 10', f'MAX_USERS = {u}') for x in L2]
    c3 = cm(ctx, 'repo', 'raise limit', {'auth.py': '\n'.join(L3)}, author=ca)
    L4 = [x.replace('retry = 3', f'retry = {rv}') for x in L3]
    c4 = cm(ctx, 'repo', 'tune retry', {'auth.py': '\n'.join(L4)}, author=bo)
    L5 = [x.replace('return True', 'return check(user)') for x in L4]
    cm(ctx, 'repo', 'check user', {'auth.py': '\n'.join(L5)}, author=al)
    ctx.data.update(tok=t, rv=rv, blame=c3, pick=c2, rx=c4)
    req(ctx, 'repo/auth.py の履歴を調べて answer.json（課題フォルダ直下）に3つのコミットIDを書いてください。'
             '{"blame": MAX_USERS の行を最後に変えたcommit, "pickaxe": 文字列 legacy_' + t + f' を最初に導入したcommit, "regex": 「retry = {rv}」の行を変えたcommit}}。'
             'IDは7桁以上の16進です。')


def c14(ctx):
    d = ctx.data
    need_repo(ctx, 'repo')
    a = rj(ctx, 'answer.json')
    for key, ek in (('blame', 'blame'), ('pickaxe', 'pick'), ('regex', 'rx')):
        ctx.require(key in a, f'answer.json に {key} がありません。')
        ctx.require(resolve(ctx, 'repo', a[key], key) == d[ek], f'{key} のcommitが違います。')


SOL14 = r'''cd repo
b=$(git blame -L '/^MAX_USERS = /,+1' --porcelain auth.py | head -n 1 | cut -d' ' -f1)
s=$(git log -S'legacy_<<tok>>' --format=%H | tail -n 1)
g=$(git log -G'retry = <<rv>>' --format=%H | tail -n 1)
printf '{"blame":"%s","pickaxe":"%s","regex":"%s"}\n' "$b" "$s" "$g" > ../answer.json'''
mission(14, 'blame と log -S・-G で変更の出どころを探す',
        '「この行は誰がいつ、なぜ変えた？」を履歴から調べます。行単位は git blame、文字列の出現数が増減した変更は log -S（ピッケル）、正規表現に合う差分は log -G です。',
        ['blameで最後に変えたcommit', 'log -S で導入commit', 'log -G で行を変えたcommit'], s14, c14, SOL14,
        ["cd repo\nh=$(git rev-parse HEAD)\nprintf '{\"blame\":\"%s\",\"pickaxe\":\"%s\",\"regex\":\"%s\"}\\n' $h $h $h > ../answer.json",
         "cd repo\nb=$(git log --format=%H -n 1 -- auth.py)\nprintf '{\"blame\":\"%s\",\"pickaxe\":\"%s\",\"regex\":\"%s\"}\\n' $b $b $b > ../answer.json"],
        'git blame -L <範囲> <file> は各行を最後に変えたcommitを示します（--porcelain は機械可読）。git log -S<文字列> は、その文字列の出現回数が変わったcommit（導入や削除）を、-G<正規表現> は差分の行が一致したcommitを列挙します。値だけが書き換わった行は出現数が変わらないので -S では見つからず、-G を使います。古い順にするには tail -n 1 や --reverse です。',
        'S は「回数の増減」、G は「差分の行の一致」です。', 'git blame -L --porcelain / git log -S / git log -G')


# ============================================================ 15 log --graph / diff
def s15(ctx):
    k1, k2, k3 = 2 + secrets.randbelow(3), 2 + secrets.randbelow(3), 1 + secrets.randbelow(3)
    mk(ctx, 'repo')
    ls = lambda n, p='x': ''.join(f'{p}{i}\n' for i in range(n))
    cm(ctx, 'repo', 'v1', {'a.txt': ls(3, 'a'), 'b.txt': ls(3, 'b'), 'c.txt': ls(3, 'c')})
    g(ctx, 'repo', 'tag', 'v1')
    g(ctx, 'repo', 'switch', '-q', '-c', 'feat')
    cm(ctx, 'repo', 'add d', {'d.txt': ls(k1, 'd')})
    g(ctx, 'repo', 'switch', '-q', 'main')
    cm(ctx, 'repo', 'edit a', {'a.txt': ls(3, 'a') + ls(k3, 'n')})
    g(ctx, 'repo', 'merge', '-q', '--no-ff', '-m', 'merge feat', 'feat')
    g(ctx, 'repo', 'switch', '-q', '-c', 'feat2')
    cm(ctx, 'repo', 'add e', {'e.txt': ls(k2, 'e')})
    g(ctx, 'repo', 'switch', '-q', 'main')
    g(ctx, 'repo', 'merge', '-q', '--no-ff', '-m', 'merge feat2', 'feat2')
    g(ctx, 'repo', 'tag', 'v2')
    ctx.write('repo/b.txt', ls(3, 'b') + 'more\n')
    ctx.write('repo/c.txt', ls(3, 'c') + 'more\n')
    g(ctx, 'repo', 'add', 'c.txt')
    ins = k1 + k2 + k3
    ctx.data.update(ins=ins)
    req(ctx, 'repo の枝分かれ・合流の様子を git log --graph --oneline --all で graph.txt（課題フォルダ直下）に保存し、さらに次を answer.json に書いてください。'
             '{"unstaged": 未ステージの変更ファイル, "staged": ステージ済みの変更ファイル, "changed": タグ v1 から v2 の間に変わったファイル（昇順・カンマ区切り）, "insertions": v1からv2の追加行数の合計, "merges": mergeコミットの数}。')


def c15(ctx):
    d = ctx.data
    need_repo(ctx, 'repo')
    gt = ctx.need_file('graph.txt')
    allc = g(ctx, 'repo', 'rev-list', '--all').split()
    ctx.require(all(x[:7] in gt for x in allc), 'graph.txt に全てのcommit(--all)が含まれていません。')
    ctx.require('\\' in gt and '*' in gt, 'graph.txt にグラフの罫線がありません（--graph）。')
    a = rj(ctx, 'answer.json')
    exp = {'unstaged': 'b.txt', 'staged': 'c.txt', 'changed': 'a.txt,d.txt,e.txt', 'insertions': d['ins'], 'merges': 2}
    for k, v in exp.items():
        ctx.require(k in a, f'answer.json に {k} がありません。')
        ctx.require(str(a[k]).strip() == str(v), f'{k} が違います。')


SOL15 = r'''cd repo
git log --graph --oneline --all > ../graph.txt
u=$(git diff --name-only | sort | paste -sd, -)
s=$(git diff --cached --name-only | sort | paste -sd, -)
c=$(git diff --name-only v1 v2 | sort | paste -sd, -)
i=$(git diff --numstat v1 v2 | awk '{n+=$1} END{print n}')
m=$(git log --merges --oneline | wc -l)
printf '{"unstaged":"%s","staged":"%s","changed":"%s","insertions":%s,"merges":%s}\n' "$u" "$s" "$c" "$i" "$m" > ../answer.json'''
mission(15, 'log --graph と diff の種類を使い分ける',
        '履歴の形は git log --graph、差分は比べる対象で3種類（作業ツリーとindex、indexとHEAD、2つのcommit/タグ）に分かれます。',
        ['graph.txtに全commitのグラフ', 'answer.jsonに差分の答え'], s15, c15, SOL15,
        ["cd repo\ngit log --oneline > ../graph.txt\nprintf '{}' > ../answer.json", "cd repo\ngit log --graph --oneline --all > ../graph.txt\ngit diff --name-only HEAD > ../answer.json"],
        'git diff は作業ツリーとindexの差(未ステージ)、git diff --cached(--staged)はindexとHEADの差(ステージ済み)、git diff <A> <B> は2点間の差で、--name-only・--stat・--numstat・--word-diff で表示を変えられます。git log --graph --oneline --all はブランチの分岐・合流を罫線で描き、--merges はmergeコミットだけを出します。',
        '何と何を比べるか、で diff のオプションが決まります。', 'git log --graph --oneline --all / git diff / --cached / v1 v2 --numstat')


# ============================================================ 16 tag
def s16(ctx):
    t = tok()
    ver = f'{1 + secrets.randbelow(4)}.{secrets.randbelow(10)}.{secrets.randbelow(10)}'
    mk(ctx, 'repo')
    cm(ctx, 'repo', 'c1', {'a': '1\n'})
    c2 = cm(ctx, 'repo', f'release {t}', {'a': '2\n'})
    cm(ctx, 'repo', 'c3', {'a': '3\n'})
    cm(ctx, 'repo', 'c4', {'a': '4\n'})
    g(ctx, 'repo', 'tag', f'tmp-{t}')
    key = secrets.token_hex(8).upper()
    kind = ['unverified', 'bad', 'good'][secrets.randbelow(3)]
    body = {'unverified': f"gpg: Signature made Mon 01 Jan 2024 10:00:00 JST\ngpg:                using RSA key {key}\ngpg: Can't check signature: No public key\nerror: could not verify the tag 'v{ver}-signed'",
            'bad': f"gpg: Signature made Mon 01 Jan 2024 10:00:00 JST\ngpg:                using RSA key {key}\ngpg: BAD signature from \"Rel Eng <rel@example.test>\" [unknown]\nerror: could not verify the tag 'v{ver}-signed'",
            'good': f"gpg: Signature made Mon 01 Jan 2024 10:00:00 JST\ngpg:                using RSA key {key}\ngpg: Good signature from \"Rel Eng <rel@example.test>\" [full]"}[kind]
    ctx.write('tag-verify.txt', f'$ git tag -v v{ver}-signed\nobject 0123456789abcdef0123456789abcdef01234567\ntype commit\ntag v{ver}-signed\ntagger Rel Eng <rel@example.test> 1704070800 +0900\n\nRelease {ver}\n' + body + '\n')
    ctx.data.update(tok=t, ver=ver, c2=c2, key=key, verdict=kind)
    ctx.data['ro'] = hashlib.sha256(ctx.need_file('tag-verify.txt').encode()).hexdigest()
    req(ctx, f'①コミット「release {t}」に注釈付きタグ v{ver}（メッセージ「Release {ver}」）を付ける ②間違えて付けた軽量タグ tmp-{t} を削除 '
             f'③採取済みの署名検証の出力 tag-verify.txt（環境にgpgが無いため記録）を診断し、verdict.json に {{"verdict": "good"|"bad"|"unverified", "key": 署名の鍵ID}} を書く。')


def c16(ctx):
    d = ctx.data
    t = d['tok']
    need_repo(ctx, 'repo')
    tag = f'refs/tags/v{d["ver"]}'
    ctx.require(gr(ctx, 'repo', 'cat-file', '-t', tag) == (0, 'tag'), f'v{d["ver"]} は注釈付きタグ（git tag -a）にします。')
    ctx.require(rev(ctx, 'repo', f'v{d["ver"]}') == d['c2'], f'タグは「release {t}」のcommitに付けます。')
    ctx.require(g(ctx, 'repo', 'for-each-ref', tag, '--format=%(contents:subject)') == f'Release {d["ver"]}', 'タグのメッセージが違います。')
    ctx.require(gr(ctx, 'repo', 'rev-parse', '-q', '--verify', f'refs/tags/tmp-{t}')[0] != 0, f'tmp-{t} を削除します（git tag -d）。')
    ctx.require(hashlib.sha256(ctx.need_file('tag-verify.txt').encode()).hexdigest() == d['ro'], 'tag-verify.txt は原本です。変更しないでください。')
    v = rj(ctx, 'verdict.json')
    ctx.require(v.get('verdict') == d['verdict'], 'verdict が出力と合いません（Good signature=good、BAD signature=bad、No public key=unverified）。')
    ctx.require(str(v.get('key', '')).upper() == d['key'], 'key は gpg の using RSA key の値です。')


SOL16 = r'''cd repo
git tag -a v<<ver>> -m 'Release <<ver>>' "$(git log --grep='release <<tok>>' --format=%H -n 1)"
git tag -d tmp-<<tok>>
cd ..
printf '{"verdict":"<<verdict>>","key":"<<key>>"}\n' > verdict.json'''
mission(16, 'tag（注釈付き・署名の検証結果の診断）',
        'リリースの目印には注釈付きタグを使います。誰がいつ付けたかが記録され、署名(git tag -s)で改ざん検知もできます。署名の確認結果は採取済みの出力から読み取ります。',
        ['注釈付きタグを指定commitに作成', '軽量タグを削除', '署名検証の出力を診断'], s16, c16, SOL16,
        ["cd repo\ngit tag v<<ver>>\ngit tag -d tmp-<<tok>>\ncd ..\nprintf '{\"verdict\":\"good\",\"key\":\"x\"}' > verdict.json",
         "cd repo\ngit tag -a v<<ver>> -m 'Release <<ver>>'\ngit tag -d tmp-<<tok>>\ncd ..\nprintf '{\"verdict\":\"<<verdict>>\",\"key\":\"<<key>>\"}' > verdict.json"],
        'git tag <名前> は軽量タグ（単なる別名）、git tag -a -m は注釈付きタグ（作者・日時・メッセージを持つ独立したオブジェクト）で、リリースには後者を使います。-s は gpg 署名付き、git tag -v は署名の検証です。出力が Good signature なら検証成功、BAD signature なら改ざんや不一致、No public key は公開鍵が未登録で検証不能(unverified)です。削除は git tag -d、リモートへは git push origin <tag> が必要です。',
        '付ける対象のcommitを引数で指定します。', 'git tag -a -m <名前> <commit> / git tag -d / 出力の gpg 行を読む')


# ============================================================ 17 remote / fetch / pull --rebase / force-with-lease
def s17(ctx):
    t = tok()
    mk(ctx, 'origin.git', bare=True)
    mk(ctx, 'backup.git', bare=True)
    clone(ctx, 'origin.git', 'mine')
    base = cm(ctx, 'mine', 'base', {'README': 'r\n'})
    g(ctx, 'mine', 'push', '-q', '-u', 'origin', 'main')
    g(ctx, 'mine', 'switch', '-q', '-c', 'topic')
    cm(ctx, 'mine', 't1', {'t1.txt': '1\n'})
    cm(ctx, 'mine', 't2', {'t2.txt': '2\n'})
    g(ctx, 'mine', 'push', '-q', '-u', 'origin', 'topic')
    clone(ctx, 'origin.git', 'teammate')
    tm = cm(ctx, 'teammate', f'teammate work {t}', {'team.txt': 'T\n'})
    g(ctx, 'teammate', 'push', '-q', 'origin', 'main')
    g(ctx, 'mine', 'reset', '-q', '--soft', 'HEAD~2')
    cm(ctx, 'mine', 'squashed topic', {})
    g(ctx, 'mine', 'switch', '-q', 'main')
    cm(ctx, 'mine', f'local change {t}', {'l.txt': 'L\n'})
    ctx.data.update(tok=t, base=base, tm=tm)
    req(ctx, 'mine には「リモートに無い手元のcommit」、origin.git の main には「同僚が先にpushしたcommit」があり、食い違っています。'
             '①git fetch で状況を取得 ②pull --rebase で同僚の変更の上に自分のcommitを載せ（merge commitを作らない）mainをoriginへpush '
             '③手元でsquashした topic は履歴が書き換わっているので、同僚の更新を踏み潰さない force-with-lease でpush '
             '④バックアップ用に backup.git を remote「backup」として追加し、mainをpush。')


def c17(ctx):
    d = ctx.data
    t = d['tok']
    need_repo(ctx, 'mine')
    om = rev(ctx, 'origin.git', 'main')
    ctx.require(om == rev(ctx, 'mine', 'main'), 'origin の main と手元の main が一致していません（push）。')
    ctx.require(gr(ctx, 'mine', 'merge-base', '--is-ancestor', d['tm'], om)[0] == 0, '同僚のcommitが消えています（--force で上書きしていませんか）。')
    ctx.require(any(f'local change {t}' == s for s in g(ctx, 'mine', 'log', '--format=%s', 'main').splitlines()), '自分のcommitが main にありません。')
    ctx.require(g(ctx, 'origin.git', 'rev-list', '--merges', 'main') == '', 'merge commitができています。pull --rebase で直線にします。')
    ot = rev(ctx, 'origin.git', 'topic')
    ctx.require(ot == rev(ctx, 'mine', 'topic') and g(ctx, 'origin.git', 'rev-list', '--count', d['base'] + '..topic') == '1', 'topic のsquash結果がoriginに反映されていません（--force-with-lease）。')
    rc, url = gr(ctx, 'mine', 'remote', 'get-url', 'backup')
    ctx.require(rc == 0 and os.path.realpath(os.path.join(str(ctx.p('mine')), url)) == os.path.realpath(ctx.p('backup.git')), 'remote backup が backup.git を指していません。')
    ctx.require(rev(ctx, 'backup.git', 'main') == om, 'backup にも main をpushします。')


SOL17 = '''cd mine
git fetch origin
git status -sb
git pull --rebase origin main
git push origin main
git push --force-with-lease origin topic
git remote add backup ../backup.git
git push backup main'''
mission(17, 'remote・fetch・pull --rebase・force-with-lease を安全に使う',
        '共有ブランチの食い違いは、状況を見てから解消するのが安全です。fetch は取得だけ、pull --rebase は取り込みと付け替え、履歴を書き換えた後のpushは --force-with-lease で「他人の更新を踏まないとき限定」で強制します。',
        ['mainを直線でoriginへ', 'topicをforce-with-leaseでpush', 'remote add backup と push'], s17, c17, SOL17,
        ["cd mine\ngit push --force origin main\ngit push --force origin topic", "cd mine\ngit pull origin main\ngit push origin main"],
        'git fetch は origin の最新を取得するだけで作業ツリーを動かしません。git pull --rebase は fetch のあと自分のcommitを最新の上へ付け替えます。書き換えた履歴は通常のpushが拒否されるので、--force は他人のcommitを消す危険があり、--force-with-lease は「手元が知っているリモートの位置から変わっていない場合のみ」強制するため安全です。git remote add <名前> <URL> で送り先を増やせ、git remote -v で確認します。',
        '同僚のcommitを消してはいけません。', 'git fetch / git pull --rebase / git push --force-with-lease / git remote add')


# ============================================================ 18 worktree + sparse-checkout
def s18(ctx):
    t = tok()
    svc = ['billing', 'auth', 'search'][secrets.randbelow(3)]
    mk(ctx, 'repo')
    files = {'README': 'r\n', 'docs/guide.md': 'g\n'}
    for s in ('billing', 'auth', 'search'):
        files[f'services/{s}/main.py'] = f'# {s}\n'
    ctx.data['base'] = cm(ctx, 'repo', 'init monorepo', files)
    ctx.data.update(tok=t, svc=svc)
    req(ctx, f'モノレポ repo で、①作業を中断せずに緊急対応するため、別フォルダ ../wt-hotfix に git worktree でブランチ hotfix/{t} を作り、そこでcommitを1つ作る '
             f'②repo本体の作業ツリーは sparse-checkout（cone）で services/{svc} だけを展開（他のservices・docsはディスクから外す。履歴は保持）。')


def c18(ctx):
    d = ctx.data
    t, svc = d['tok'], d['svc']
    need_repo(ctx, 'repo')
    wl = g(ctx, 'repo', 'worktree', 'list', '--porcelain')
    ctx.require(f'branch refs/heads/hotfix/{t}' in wl, f'hotfix/{t} の worktree がありません（git worktree add -b）。')
    ctx.require(g(ctx, 'repo', 'rev-list', '--count', d['base'] + f'..hotfix/{t}') == '1', f'worktree側でhotfix/{t}にcommitを1つ作ります。')
    ctx.require(f'services/{svc}' in g(ctx, 'repo', 'sparse-checkout', 'list').splitlines(), f'sparse-checkout に services/{svc} を指定します。')
    ctx.require(ctx.isfile(f'repo/services/{svc}/main.py'), f'services/{svc} は展開されたままにします。')
    for s in ('billing', 'auth', 'search'):
        if s != svc:
            ctx.require(not ctx.exists(f'repo/services/{s}'), f'services/{s} はディスクから外します。')
    ctx.require(g(ctx, 'repo', 'ls-tree', '-r', '--name-only', 'HEAD').count('services/') == 3, '履歴の中身は消えていません（作業ツリーだけを絞ります）。')


SOL18 = '''cd repo
git worktree add ../wt-hotfix -b hotfix/<<tok>>
echo fixed > ../wt-hotfix/hotfix.txt
git -C ../wt-hotfix add hotfix.txt
git -C ../wt-hotfix commit -m 'hotfix <<tok>>'
git sparse-checkout set services/<<svc>>'''
mission(18, 'worktree と sparse-checkout で作業場所を分ける',
        'stashや切替をせずに別ブランチで作業するには git worktree、巨大なリポジトリの一部だけを展開するには git sparse-checkout を使います。',
        ['worktreeでhotfixを作業しcommit', 'sparse-checkoutで1つのserviceだけ展開'], s18, c18, SOL18,
        ["cd repo\ngit switch -c hotfix/<<tok>>\ngit sparse-checkout set services/<<svc>>", "cd repo\ngit worktree add ../wt-hotfix -b hotfix/<<tok>>\ngit -C ../wt-hotfix commit --allow-empty -m x\nrm -rf services/auth services/billing services/search"],
        'git worktree add <パス> -b <ブランチ> は同じ.gitを共有する作業ツリーを増やし、ブランチを切り替えずに並行作業できます（一覧は git worktree list、削除は worktree remove）。git sparse-checkout set <ディレクトリ> は cone モードで指定のディレクトリだけを展開し、他は作業ツリーから外します。履歴やindexの情報は保持されるので、いつでも disable や set で戻せます。',
        'worktreeは別フォルダ、sparse は同じフォルダの一部を隠す仕組みです。', 'git worktree add -b / git sparse-checkout set')


# ============================================================ 19 submodule
def s19(ctx):
    mk(ctx, 'util')
    c1 = cm(ctx, 'util', 'util v1', {'util.py': 'v1\n'})
    g(ctx, 'util', 'tag', 'v1.0')
    cm(ctx, 'util', 'util v2 (unreleased)', {'util.py': 'v2\n'})
    ctx.data.update(c1=c1, utip=g(ctx, 'util', 'rev-parse', 'HEAD'))
    mk(ctx, 'app')
    cm(ctx, 'app', 'init app', {'README': 'app\n'})
    req(ctx, 'app に、隣のリポジトリ util を vendor/util として git submodule で組み込み、util のタグ v1.0（最新ではなく安定版）に固定してcommitしてください。'
             'ローカルパスからのsubmoduleは既定でfile転送が禁止されているため、このコマンド1回だけ -c protocol.file.allow=always を付けます。')


def c19(ctx):
    d = ctx.data
    need_repo(ctx, 'app')
    ctx.require('path = vendor/util' in gr(ctx, 'app', 'show', 'HEAD:.gitmodules')[1], '.gitmodules に vendor/util が記録されていません。submodule add のあとcommitします。')
    rc, ent = gr(ctx, 'app', 'ls-tree', 'HEAD', 'vendor/util')
    ctx.require(rc == 0 and ent.startswith('160000 commit '), 'vendor/util がsubmodule(gitlink)としてcommitされていません。')
    ctx.require(ent.split()[2] == d['c1'], 'submoduleをタグ v1.0 のcommitに固定します（最新ではない）。')
    ctx.require(rev(ctx, 'util', 'HEAD') == d['utip'], '元の util は変更しません。')
    ctx.require(g(ctx, 'app', 'status', '--porcelain') == '', '未commitの変更が残っています。')


SOL19 = '''cd app
git -c protocol.file.allow=always submodule add "$(cd ../util && pwd -P)" vendor/util
git -C vendor/util checkout -q v1.0
git add vendor/util
git commit -m 'add util submodule pinned to v1.0\''''.replace("\\''", "'")
mission(19, 'submodule で外部リポジトリを固定して取り込む',
        '別リポジトリのコードを特定の版で取り込むのが git submodule です。親リポジトリは、サブモジュールの「どのcommitか」を記録します。',
        ['.gitmodules とgitlinkをcommit', 'タグ v1.0 のcommitに固定'], s19, c19, SOL19,
        ["cd app\ngit -c protocol.file.allow=always submodule add \"$(cd ../util && pwd -P)\" vendor/util\ngit commit -m 'add util'", "cp -r util app/vendor-util\ncd app\ngit add -A\ngit commit -m 'copy util'"],
        'git submodule add <URL> <パス> は .gitmodules に設定を書き、親のtreeにはgitlink(モード160000でcommit ID)として記録します。固定したい版へ中で checkout して親で git add すると、その版が記録されます。他の人は git clone --recurse-submodules、または clone後に git submodule update --init で取得します。親は常に「特定のcommit」を指すため、submodule側で最新に進めたら親でも commit が必要です。',
        'サブモジュール内で checkout した結果を、親で add して記録します。', 'git submodule add / git -C vendor/util checkout / git add / git commit')


# ============================================================ 20 format-patch / am
def s20(ctx):
    t = tok()
    mk(ctx, 'donor')
    cm(ctx, 'donor', 'base', {'README': 'r\n'})
    clone(ctx, 'donor', 'receiver')
    g(ctx, 'donor', 'switch', '-q', '-c', 'feature')
    al = ('Alice Dev', 'alice@example.test')
    subs = [f'feat: a {t}', f'feat: b {t}', f'fix: c {t}']
    for i, s in enumerate(subs):
        cm(ctx, 'donor', s, {f'p{i}.txt': f'{i}\n'}, author=al)
    g(ctx, 'donor', 'switch', '-q', 'main')
    ctx.data.update(subs=subs, n=int(g(ctx, 'receiver', 'rev-list', '--count', 'HEAD')))
    req(ctx, 'donor の feature ブランチ(mainから3commit)を、ネットワークなしでメール形式のパッチにして receiver へ渡します。'
             'donor で git format-patch を使い、課題フォルダ直下の patches/ に出力し、receiver で git am により、作者情報を保ったまま3commitとして適用してください。')


def c20(ctx):
    d = ctx.data
    need_repo(ctx, 'receiver')
    ps = [f for f in os.listdir(ctx.p('patches'))] if ctx.isdir('patches') else []
    ctx.require(len([f for f in ps if f.endswith('.patch')]) == 3, 'patches/ に3つの .patch を出力します（git format-patch -o）。')
    ctx.require(not os.path.exists(os.path.join(str(ctx.p('receiver')), g(ctx, 'receiver', 'rev-parse', '--git-path', 'rebase-apply'))), 'am が途中です。')
    ctx.require(int(g(ctx, 'receiver', 'rev-list', '--count', 'HEAD')) == d['n'] + 3, 'receiver に3commit増えていません（git am）。')
    ctx.require(g(ctx, 'receiver', 'log', '--format=%s', '-n', '3').splitlines()[::-1] == d['subs'], 'commitの件名・順序が元と違います。')
    ctx.require(set(g(ctx, 'receiver', 'log', '--format=%an', '-n', '3').splitlines()) == {'Alice Dev'}, '作者情報が保たれていません（git diff + git apply ではなく format-patch と am）。')


SOL20 = '''cd donor
git format-patch main..feature -o ../patches
cd ../receiver
git am ../patches/*.patch'''
mission(20, 'format-patch と am でcommitをパッチとして受け渡す',
        'メールやファイルでcommitを渡す古典的な方法です。git format-patch は1commitを1ファイルに、git am はそれをcommitとして適用し、作者・日時・メッセージを引き継ぎます。',
        ['patches/ に3つのパッチ', 'receiverに作者付きで3commit'], s20, c20, SOL20,
        ["cd donor\ngit diff main feature > ../all.patch\ncd ../receiver\ngit apply ../all.patch\ngit add -A\ngit commit -m 'import'", "cd donor\ngit format-patch main..feature -o ../patches"],
        'git format-patch <範囲> -o <dir> は 0001-xxx.patch のように1commit1ファイルのパッチを作ります（件名・作者・日付付き）。git am <パッチ...> はそれらをcommitとして順に適用します。衝突したら解消して git am --continue、中止は --abort です。git diff + git apply だとcommitの区切りと作者情報が失われます。',
        '範囲は main..feature です。', 'git format-patch main..feature -o / git am')


# ============================================================ 21 gitignore / gitattributes / LFS
def s21(ctx):
    t = tok()
    oid = hashlib.sha256(secrets.token_bytes(8)).hexdigest()
    size = 100000 + secrets.randbelow(900000)
    mk(ctx, 'repo')
    cm(ctx, 'repo', 'init', {'src/main.c': 'int main(){}\n', 'build.sh': '#!/bin/sh\n', 'README': 'r\n', 'debug.log': 'oops\n'})
    ctx.write(f'repo/dist-{t}/app.bin', 'bin\n')
    ctx.write('repo/error.log', 'e\n')
    ctx.write('repo/keep.log', 'keep\n')
    ctx.write('repo/.env', 'SECRET=1\n')
    ctx.write('repo/node_modules/x/index.js', '1\n')
    ctx.write('lfs-pointer.txt', f'version https://git-lfs.github.com/spec/v1\noid sha256:{oid}\nsize {size}\n')
    ctx.data.update(tok=t, oid=oid, size=size, ro=hashlib.sha256(ctx.read('lfs-pointer.txt').encode()).hexdigest())
    req(ctx, f'repo の整備: ①.gitignore で dist-{t}/・*.log（ただし keep.log は除外しない）・.env・node_modules/ を無視 ②誤ってcommit済みの debug.log を追跡から外す（ファイルは残す） '
             '③.gitattributes: 全体は text=auto、*.sh は text eol=lf、*.bat は text eol=crlf（改行コード）、*.png は binary、*.psd は Git LFS 管理（filter=lfs diff=lfs merge=lfs -text） '
             '④採取済みのLFSポインタ lfs-pointer.txt から oid と size を取り出して lfs.json（{"oid":..., "size":...}）に書く。')


def c21(ctx):
    d = ctx.data
    t = d['tok']
    need_repo(ctx, 'repo')
    for p in (f'dist-{t}/app.bin', 'error.log', '.env', 'node_modules/x/index.js', 'debug.log'):
        ctx.require(gr(ctx, 'repo', 'check-ignore', '-q', '--no-index', p)[0] == 0, f'{p} が無視されていません。')
    for p in ('keep.log', 'src/main.c'):
        ctx.require(gr(ctx, 'repo', 'check-ignore', '-q', '--no-index', p)[0] == 1, f'{p} は無視しません。')
    ctx.require('debug.log' not in g(ctx, 'repo', 'ls-files').split() and ctx.isfile('repo/debug.log'), 'debug.log は追跡から外し（git rm --cached）、ファイルは残します。')

    def attr(path, name):
        return g(ctx, 'repo', 'check-attr', name, '--', path).rsplit(': ', 1)[1]
    ctx.require(attr('src/main.c', 'text') == 'auto', '全体は * text=auto です。')
    ctx.require(attr('build.sh', 'text') == 'set' and attr('build.sh', 'eol') == 'lf', '*.sh は text eol=lf です。')
    ctx.require(attr('run.bat', 'eol') == 'crlf', '*.bat は eol=crlf です。')
    ctx.require(attr('logo.png', 'text') == 'unset' and attr('logo.png', 'diff') == 'unset', '*.png は binary です。')
    ctx.require(all(attr('art.psd', k) == 'lfs' for k in ('filter', 'diff', 'merge')) and attr('art.psd', 'text') == 'unset', '*.psd はLFS（filter=lfs diff=lfs merge=lfs -text）です。')
    ctx.require(hashlib.sha256(ctx.need_file('lfs-pointer.txt').encode()).hexdigest() == d['ro'], 'lfs-pointer.txt は原本です。')
    j = rj(ctx, 'lfs.json')
    ctx.require(j.get('oid') == d['oid'] and str(j.get('size')) == str(d['size']), 'lfs.json の oid（sha256:は除く）と size がポインタと合いません。')


SOL21 = r'''cd repo
cat > .gitignore <<'EOF'
dist-<<tok>>/
*.log
!keep.log
.env
node_modules/
EOF
git rm --cached debug.log
cat > .gitattributes <<'EOF'
* text=auto
*.sh text eol=lf
*.bat text eol=crlf
*.png binary
*.psd filter=lfs diff=lfs merge=lfs -text
EOF
printf '{"oid":"<<oid>>","size":<<size>>}\n' > ../lfs.json'''
mission(21, '.gitignore と .gitattributes（改行・LFS）を整える',
        '生成物や秘密を履歴に入れない .gitignore、OS間の改行(LF/CRLF)やバイナリ・巨大ファイル(Git LFS)の扱いを決める .gitattributes を整備します。LFSの実体は環境に無いことがあるため、ポインタ形式の出力を読み取って診断します。',
        ['.gitignoreで無視（否定を含む）', '追跡中のdebug.logを外す', '.gitattributesとLFS設定', 'LFSポインタの診断'], s21, c21, SOL21,
        ["cd repo\nprintf 'dist-<<tok>>/\\n*.log\\n.env\\nnode_modules/\\n' > .gitignore\ngit rm --cached debug.log\nprintf '* text=auto\\n' > .gitattributes\nprintf '{}' > ../lfs.json",
         "cd repo\nprintf 'dist-<<tok>>/\\n*.log\\n!keep.log\\n.env\\nnode_modules/\\n' > .gitignore\nprintf '* text=auto\\n*.sh text eol=lf\\n*.bat text eol=crlf\\n*.png binary\\n*.psd filter=lfs diff=lfs merge=lfs -text\\n' > .gitattributes\nprintf '{\"oid\":\"<<oid>>\",\"size\":<<size>>}' > ../lfs.json"],
        '.gitignore は「追跡されていない」ファイルを無視するだけで、すでに追跡中のものは git rm --cached で外す必要があります。後ろの行が優先され、!パターンで例外を作れ、git check-ignore -v で理由を確認できます。.gitattributes は text=auto・eol・binary・filter=lfs などをパス別に決めます（git check-attr で確認）。LFS管理のファイルは、リポジトリには version / oid sha256 / size のポインタが入り、実体は別ストレージに置かれます。git lfs track はこの .gitattributes の行を追加するコマンドです。',
        '否定(!)は上位の *.log より後に書きます。', '.gitignore / git rm --cached / .gitattributes / ポインタの oid と size')


# ============================================================ 22 hooks
def s22(ctx):
    t = tok()
    mk(ctx, 'repo')
    cm(ctx, 'repo', 'init', {'README': 'r\n'})
    ctx.data.update(tok=t)
    req(ctx, f'repo の .git/hooks に2つのhooksを実装します。pre-commit: ステージの追加行に DONOTCOMMIT-{t} を含むcommitを拒否。'
             'commit-msg: メッセージの1行目が「feat: 」「fix: 」「docs: 」のいずれかで始まらなければ拒否。両方とも実行権限が必要です。')


def c22(ctx):
    d = ctx.data
    t = d['tok']
    need_repo(ctx, 'repo')
    for h in ('pre-commit', 'commit-msg'):
        p = ctx.p(f'repo/.git/hooks/{h}')
        ctx.require(p.is_file() and os.access(p, os.X_OK), f'{h} がないか、実行権限がありません（chmod +x）。')
    tmp = tempfile.mkdtemp(prefix='lq-hooks-')
    try:
        r = os.path.join(tmp, 'r')
        shutil.copytree(ctx.p('repo'), r, symlinks=True)
        run = lambda *a: subprocess.run(['git', '-C', r, *a], env=genv(), capture_output=True, text=True, timeout=60).returncode
        with open(os.path.join(r, 'x.txt'), 'w') as f:
            f.write(f'DONOTCOMMIT-{t}\n')
        run('add', 'x.txt')
        ctx.require(run('commit', '-q', '-m', 'feat: ok') != 0, 'pre-commit が禁止語を含むcommitを拒否していません。')
        run('reset', '-q', '--hard')
        run('clean', '-fdq')
        with open(os.path.join(r, 'y.txt'), 'w') as f:
            f.write('fine\n')
        run('add', 'y.txt')
        ctx.require(run('commit', '-q', '-m', 'oops no prefix') != 0, 'commit-msg が形式違反のメッセージを拒否していません。')
        ctx.require(run('commit', '-q', '-m', 'docs: fine') == 0, '正しいcommit（禁止語なし・形式どおり）が通りません。')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


SOL22 = r'''cd repo
cat > .git/hooks/pre-commit <<'EOF'
#!/bin/sh
if git diff --cached | grep -q '^+.*DONOTCOMMIT-<<tok>>'; then
  echo 'forbidden marker found' >&2
  exit 1
fi
EOF
cat > .git/hooks/commit-msg <<'EOF'
#!/bin/sh
head -n 1 "$1" | grep -Eq '^(feat|fix|docs): .+' || { echo 'bad commit message' >&2; exit 1; }
EOF
chmod +x .git/hooks/pre-commit .git/hooks/commit-msg'''
mission(22, 'hooks（pre-commit・commit-msg）を実装する',
        'commit前後に自動でチェックを走らせる仕組みが hooks です。禁止語の混入と、メッセージ規約の違反を、commit時点で止めます。',
        ['pre-commitで禁止語を拒否', 'commit-msgで形式を強制', '実行権限を付ける'], s22, c22, SOL22,
        ["cd repo\nprintf '#!/bin/sh\\nexit 0\\n' > .git/hooks/pre-commit\nprintf '#!/bin/sh\\nexit 0\\n' > .git/hooks/commit-msg\nchmod +x .git/hooks/*",
         "cd repo\nprintf '#!/bin/sh\\ngit diff --cached | grep -q DONOTCOMMIT-<<tok>> && exit 1\\nexit 0\\n' > .git/hooks/pre-commit\nprintf '#!/bin/sh\\ngrep -Eq \"^(feat|fix|docs): \" \"$1\" || exit 1\\n' > .git/hooks/commit-msg"],
        'hooks は .git/hooks/<名前> の実行可能ファイルで、終了コードが0以外ならGitは操作を中止します。pre-commit はコミット作成前（ステージ内容の検査）、commit-msg は引数 $1 のメッセージファイルを検査します。実行権限がないと黙って無視されます。.git/hooks は共有されないため、チームでは git config core.hooksPath で管理するディレクトリを指定します。--no-verify で回避できるので、最終防衛はCIです。',
        'commit-msg には、メッセージを書いたファイルのパスが $1 で渡されます。', 'git diff --cached | grep / chmod +x')


# ============================================================ 23 git config alias / includeIf
def s23(ctx):
    t = tok()
    mk(ctx, 'work/proj')
    mk(ctx, 'personal/proj')
    ctx.write('home/.gitconfig', f'[user]\n\tname = Trainee\n\temail = personal-{t}@example.test\n')
    ctx.write('home/.gitconfig-work', f'[user]\n\temail = {t}@corp.example\n')
    for r in ('work/proj', 'personal/proj'):
        g(ctx, r, 'config', '--unset', 'user.name')
        g(ctx, r, 'config', '--unset', 'user.email')
    ctx.data.update(tok=t)
    req(ctx, 'ホームの設定に見立てた home/.gitconfig を git config --file で編集します（実際のグローバル設定には触れません）。'
             '①alias lg = log --graph --oneline --decorate、alias st = status -sb ②work/ 配下のリポジトリでだけ includeIf（gitdir）で home/.gitconfig-work を読み込み、メールアドレスを仕事用に切り替える。')


def c23(ctx):
    d = ctx.data
    t = d['tok']
    cfg = str(ctx.p('home/.gitconfig'))
    e = {'GIT_CONFIG_GLOBAL': cfg}

    def conf(repo, key):
        return gr(ctx, repo, 'config', '--get', key, env=e)[1]
    ctx.require(conf('personal/proj', 'alias.lg') == 'log --graph --oneline --decorate', 'alias.lg が違います。')
    ctx.require(conf('personal/proj', 'alias.st') == 'status -sb', 'alias.st が違います。')
    ctx.require(conf('personal/proj', 'user.email') == f'personal-{t}@example.test', 'work 以外のリポジトリでは個人用のメールのままにします（無条件の include はだめ）。')
    ctx.require(conf('work/proj', 'user.email') == f'{t}@corp.example', 'work/ 配下で includeIf により仕事用メールになっていません。')


SOL23 = '''base=$(pwd -P)
git config --file home/.gitconfig alias.lg 'log --graph --oneline --decorate'
git config --file home/.gitconfig alias.st 'status -sb'
git config --file home/.gitconfig "includeIf.gitdir:$base/work/.path" .gitconfig-work'''
mission(23, 'git config の alias と includeIf で設定を切り替える',
        'よく使うコマンドは alias に、仕事用と個人用でメールアドレスを使い分けるには includeIf を使います。',
        ['alias.lg と alias.st', 'work/ 配下だけ仕事用の設定を読む'], s23, c23, SOL23,
        ["git config --file home/.gitconfig alias.lg 'log --graph --oneline --decorate'\ngit config --file home/.gitconfig alias.st 'status -sb'\ngit config --file home/.gitconfig include.path .gitconfig-work",
         "git config --file home/.gitconfig alias.lg 'log --oneline'\ngit config --file home/.gitconfig alias.st 'status -sb'"],
        'git config は --system / --global / --local（既定）/ --file で書き込み先を選び、後に読まれるほど優先されます。alias.<名前> でコマンドを短縮でき、[includeIf "gitdir:<パス>/"] は、そのパス配下のリポジトリにいるときだけ path の設定を取り込みます。パスは末尾の / を付けると配下全体に一致し、大文字小文字を区別しないなら gitdir/i です。git config --show-origin --list で、どの設定がどのファイル由来か確認できます。',
        'gitdir の指定は絶対パスです。', 'git config --file / alias.* / includeIf.gitdir:<絶対パス>/.path')


# ============================================================ 24 secret removal
def s24(ctx):
    sec = 'sk_live_' + secrets.token_hex(8)
    pushed = secrets.randbelow(2) == 0
    mk(ctx, 'repo')
    cm(ctx, 'repo', 'init', {'README': 'r\n', 'src.txt': 'v1\n'})
    c2 = cm(ctx, 'repo', 'add config', {'config.env': f'API_TOKEN={sec}\n', 'src.txt': 'v2\n'})
    blob = g(ctx, 'repo', 'rev-parse', f'{c2}:config.env')
    cm(ctx, 'repo', 'remove config', {'config.env': None, 'src.txt': 'v3\n'})
    if pushed:
        mk(ctx, 'origin.git', bare=True)
        g(ctx, 'repo', 'remote', 'add', 'origin', '../origin.git')
        g(ctx, 'repo', 'push', '-q', 'origin', 'main')
    ctx.data.update(sec=sec, blob=blob, pushed=pushed, pcmd='git push --force origin main' if pushed else 'git remote -v',
                    fp='true' if pushed else 'false')
    req(ctx, f'config.env に本物のAPIキー（{sec}）をcommitしてしまい、後のcommitで消したものの履歴に残っています。履歴全体から config.env を完全に消し（git filter-branch か filter-repo。ここでは標準の filter-branch）、'
             'バックアップref(refs/original)・reflog・到達不能オブジェクトまで片付けてください。リモート(origin.git)が存在するなら書き換えた履歴を反映します。'
             '最後に判断を rotate.json に書く: {"rotate_secret": 鍵を無効化して再発行するか, "force_push": 強制pushが必要か, "reclone_all": 全員がcloneし直すべきか}。')


def c24(ctx):
    d = ctx.data
    need_repo(ctx, 'repo')
    ctx.require(g(ctx, 'repo', 'log', '--all', '--format=%H', f'-S{d["sec"]}') == '', '履歴にまだ秘密情報が残っています。')
    ctx.require(g(ctx, 'repo', 'for-each-ref', 'refs/original') == '', 'filter-branch のバックアップ refs/original が残っています（秘密が参照されたまま）。')
    ctx.require(gr(ctx, 'repo', 'cat-file', '-e', d['blob'])[0] != 0, '秘密を含むオブジェクトがまだ存在します（reflog expire と gc --prune=now）。')
    ctx.require(ctx.read('repo/src.txt') == 'v3\n' and ctx.isfile('repo/README') and not ctx.exists('repo/config.env'), '他のファイルの最新内容は保ちます。')
    ctx.require(int(g(ctx, 'repo', 'rev-list', '--count', 'HEAD')) >= 2, '履歴が失われすぎています。')
    if d['pushed']:
        ctx.require(g(ctx, 'origin.git', 'log', '--all', '--format=%H', f'-S{d["sec"]}') == '', 'リモートにまだ秘密情報が残っています。')
        ctx.require(rev(ctx, 'origin.git', 'main') == rev(ctx, 'repo', 'main'), 'リモートのmainを書き換えた履歴に更新します（force push）。')
    j = rj(ctx, 'rotate.json')
    ctx.require(j.get('rotate_secret') is True, '履歴を消しても漏れた可能性は消えません。鍵は必ず無効化・再発行します。')
    ctx.require(j.get('force_push') is d['pushed'] and j.get('reclone_all') is d['pushed'],
                '共有済み(push済み)なら強制pushと全員のclone作り直しが必要、手元だけなら不要です。')


SOL24 = r'''cd repo
FILTER_BRANCH_SQUELCH_WARNING=1 git filter-branch --index-filter 'git rm --cached --ignore-unmatch -q config.env' -- --all
rm -rf .git/refs/original
git reflog expire --expire=now --all
git gc --prune=now
<<pcmd>>
printf '{"rotate_secret":true,"force_push":<<fp>>,"reclone_all":<<fp>>}\n' > ../rotate.json'''
mission(24, '誤コミットした秘密情報を履歴から除去する',
        '秘密をcommitしてしまったら、消したcommitを足すだけでは履歴に残ります。filter-repo か filter-branch で全履歴から除去し、再発行と周知の判断まで行うのが対応の全体像です。',
        ['全履歴・refs/original・到達不能オブジェクトから除去', '共有済みなら強制push', 'rotate.jsonの判断'], s24, c24, SOL24,
        ["cd repo\ngit rm config.env\ngit commit -m 'remove secret'\nprintf '{\"rotate_secret\":false,\"force_push\":false,\"reclone_all\":false}' > ../rotate.json",
         "cd repo\nFILTER_BRANCH_SQUELCH_WARNING=1 git filter-branch --index-filter 'git rm --cached --ignore-unmatch -q config.env' -- --all\nprintf '{\"rotate_secret\":true,\"force_push\":<<fp>>,\"reclone_all\":<<fp>>}' > ../rotate.json"],
        '履歴からの完全除去には git filter-repo --path config.env --invert-paths（別途導入が必要で推奨）か、標準の git filter-branch --index-filter を使います。filter-branch は元の履歴を refs/original に退避するので、削除し、git reflog expire --expire=now --all と git gc --prune=now でオブジェクトも消します。共有済みなら書き換えた履歴を --force でpushし、他のcloneとforkには古い履歴が残るため全員がcloneし直します。ただし一度公開された秘密は漏れた前提で、必ず鍵を失効して再発行(rotate)します。履歴の削除は再発行の代わりにはなりません。',
        '消しただけでは、過去のcommitから取り出せます。', 'git filter-branch --index-filter / refs/original / reflog expire / gc --prune=now')


# ============================================================ 25 branch strategy / PR cleanup
def s25(ctx):
    t = tok()
    trunk = secrets.randbelow(2) == 0
    strat = 'trunk' if trunk else 'gitflow'
    base = 'main' if trunk else 'develop'
    ctx.write('team.txt', ('チーム状況: 本番へ1日に何度も自動デプロイする。リリースは常に最新の1系統だけ。ブランチは短命(1日以内)でmainへ統合し、未完成の機能はフィーチャーフラグで隠す。\n' if trunk else
                           'チーム状況: 四半期ごとの定期リリース。v1とv2の旧系統を並行して保守する。リリース前にQA期間があり、リリース用ブランチと hotfix を分けて運用したい。\n'))
    ctx.data['ro'] = hashlib.sha256(ctx.read('team.txt').encode()).hexdigest()
    mk(ctx, 'repo')
    cm(ctx, 'repo', 'base', {'README': 'r\n'})
    g(ctx, 'repo', 'branch', 'develop')
    g(ctx, 'repo', 'switch', '-q', '-c', f'feature/{t}')
    cm(ctx, 'repo', 'wip', {'report.txt': 'l1\n'})
    cm(ctx, 'repo', 'wip2', {'report.txt': 'l1\nl2\n'})
    cm(ctx, 'repo', 'fix typo', {'report.txt': 'l1\nl2\nl3\n'})
    g(ctx, 'repo', 'switch', '-q', base)
    bt = cm(ctx, 'repo', 'other work', {'other.txt': 'o\n'})
    g(ctx, 'repo', 'switch', '-q', f'feature/{t}')
    ctx.data.update(tok=t, strat=strat, base=base, bt=bt)
    req(ctx, 'team.txt のチーム状況から、ブランチ戦略（trunk または gitflow）と、PRの宛先ブランチ(base)を判断して strategy.json に {"strategy": ..., "base": ...} と書きます（GitFlow なら統合先は develop、trunk-based なら main）。'
             f'そのうえで feature/{t} の3つの細かいcommit(wip など)を、baseの最新の上に載せた「1つのcommit」にまとめ直してください。件名は「feat: 」で始め、wip を含めません。')


def c25(ctx):
    d = ctx.data
    t = d['tok']
    need_repo(ctx, 'repo')
    ctx.require(hashlib.sha256(ctx.need_file('team.txt').encode()).hexdigest() == d['ro'], 'team.txt は原本です。')
    j = rj(ctx, 'strategy.json')
    ctx.require(j.get('strategy') == d['strat'] and j.get('base') == d['base'], 'チーム状況に合う戦略とbaseを選びます（頻繁にデプロイ=trunk→main、定期リリース+複数系統の保守=gitflow→develop）。')
    f, b = f'feature/{t}', d['base']
    ctx.require(rev(ctx, 'repo', b) == d['bt'], f'{b} は変えません。')
    ctx.require(gr(ctx, 'repo', 'merge-base', '--is-ancestor', b, f)[0] == 0, f'{f} を {b} の最新の上に載せます（rebase）。')
    ctx.require(g(ctx, 'repo', 'rev-list', '--count', f'{b}..{f}') == '1', 'PR用に1つのcommitにまとめます。')
    sub = g(ctx, 'repo', 'log', '-1', '--format=%s', f)
    ctx.require(sub.startswith('feat: ') and 'wip' not in sub.lower(), '件名は「feat: ...」で wip を含めません。')
    ctx.require(g(ctx, 'repo', 'show', f'{f}:report.txt') == 'l1\nl2\nl3', 'report.txt の最終内容は保ちます。')


SOL25 = '''cd repo
git switch feature/<<tok>>
git rebase <<base>>
git reset --soft <<base>>
git commit -m 'feat: <<tok>> add report'
printf '{"strategy":"<<strat>>","base":"<<base>>"}\\n' > ../strategy.json'''
mission(25, 'ブランチ戦略（trunk・GitFlow）の選択とPR前の整理',
        'ブランチ戦略はチームの運用に合わせて選びます。PRを出す前には、細かいwipを整理し、最新のbaseに載せて1つの意味のある変更にまとめます。',
        ['戦略とbaseをstrategy.jsonへ', '1つのfeat commitへ整理'], s25, c25, SOL25,
        ["cd repo\ngit merge <<base>>\nprintf '{\"strategy\":\"<<strat>>\",\"base\":\"<<base>>\"}' > ../strategy.json", "cd repo\ngit rebase <<base>>\nprintf '{\"strategy\":\"trunk\",\"base\":\"main\"}' > ../strategy.json"],
        'trunk-based は短命ブランチを頻繁にmainへ統合し、フィーチャーフラグで未完成を隠す方式で、継続的デプロイ向きです。GitFlow は main・develop・feature・release・hotfix を使い分け、定期リリースや複数バージョンの保守向きですが、運用は重くなります。PR前は git rebase <base> で最新に追従し、git reset --soft <base> で変更を保ったままcommitを解き、まとまったメッセージで再commitするのが簡単な整理方法です（rebase -i の squash でも可）。',
        'チームのデプロイ頻度が判断材料です。', 'git rebase <base> / git reset --soft <base> / git commit')


# ============================================================ 26 gc / fsck / dangling
def s26(ctx):
    t = tok()
    mk(ctx, 'repo')
    cm(ctx, 'repo', 'c1', {'a.txt': '1\n'})
    cm(ctx, 'repo', 'c2', {'a.txt': '2\n'})
    g(ctx, 'repo', 'switch', '-q', '-c', 'tmp')
    lost = cm(ctx, 'repo', f'lost work {t}', {'lost.txt': f'precious {t}\n'})
    g(ctx, 'repo', 'switch', '-q', 'main')
    g(ctx, 'repo', 'branch', '-D', 'tmp')
    g(ctx, 'repo', 'reflog', 'expire', '--expire=now', '--all')
    ctx.data.update(tok=t, lost=lost)
    req(ctx, f'ブランチ tmp を消してreflogも期限切れにした後で、そこにあった「lost work {t}」が必要だと分かりました。どのブランチからも辿れない（dangling）commitを git fsck で見つけ、'
             f'rescued/{t} ブランチとして救出し、そのあと git gc で整理して、リポジトリが健全(fsck エラーなし)であることを確認してください。')


def c26(ctx):
    d = ctx.data
    t = d['tok']
    need_repo(ctx, 'repo')
    rc, v = gr(ctx, 'repo', 'rev-parse', '--verify', '-q', f'refs/heads/rescued/{t}^{{commit}}')
    ctx.require(rc == 0 and v == d['lost'], f'rescued/{t} が「lost work」のcommitを指していません。')
    ctx.require(gr(ctx, 'repo', 'fsck', '--full')[0] == 0, 'git fsck がエラーを報告しています。')
    cnt = g(ctx, 'repo', 'count-objects', '-v')
    ctx.require(int(re.search(r'^packs: (\d+)', cnt, re.M).group(1)) >= 1, '救出のあと git gc でオブジェクトを整理します。')
    ctx.require(gr(ctx, 'repo', 'cat-file', '-e', d['lost'])[0] == 0, '救出したcommitが失われています。gc は救出の後に行います。')


SOL26 = '''cd repo
git fsck --lost-found
sha=$(git fsck --no-reflogs 2>/dev/null | awk '/dangling commit/ {print $3}' | head -n 1)
git branch rescued/<<tok>> "$sha"
git gc'''
mission(26, 'gc・fsck でdangling commitを救出する',
        'reflogも切れたあとでも、gcで掃除されるまでは到達不能なオブジェクトがディスクに残っています。git fsck で探して救出し、その後 git gc で整えます。',
        ['danglingのcommitをブランチで救出', 'git gc 後も健全'], s26, c26, SOL26,
        ["cd repo\ngit gc --prune=now\ngit branch rescued/<<tok>> HEAD", "cd repo\nsha=$(git fsck --no-reflogs 2>/dev/null | awk '/dangling commit/ {print $3}' | head -n 1)\ngit gc --prune=now\ngit branch rescued/<<tok>> \"$sha\""],
        'git fsck --lost-found（--no-reflogs）はオブジェクトの整合性を検査し、どこからも参照されない dangling commit/blob を一覧します。IDが分かれば git branch <名前> <ID> で救出できます。git gc はloose objectをpackにまとめ、到達不能なものを猶予期間(既定2週間)後に削除します。--prune=now は猶予なしで即削除するので、救出前には絶対に使いません。',
        '救出が先、掃除（gc）が後です。', 'git fsck --no-reflogs / git branch <名前> <ID> / git gc')


# ============================================================ 27 shallow / partial clone
def s27(ctx):
    mk(ctx, 'seed')
    for i in range(1, 11):
        cm(ctx, 'seed', f'c{i}', {'f.txt': ''.join(f'{j}\n' for j in range(i))})
    g(ctx, None, 'clone', '-q', '--bare', str(ctx.p('seed')), str(ctx.p('origin.git')))
    shutil.rmtree(ctx.p('seed'))
    g(ctx, 'origin.git', 'config', 'uploadpack.allowFilter', 'true')
    g(ctx, 'origin.git', 'config', 'uploadpack.allowAnySHA1InWant', 'true')
    req(ctx, 'origin.git（10commit）から、①直近3commitだけを取る浅い履歴の shallow、②全commitは取るがファイルの中身(blob)は必要になるまで取らない partial を、それぞれ clone してください。'
             '注意: ローカルパスのcloneは --depth や --filter を無視するため、file:// のURLを指定します。')


def c27(ctx):
    need_repo(ctx, 'shallow')
    need_repo(ctx, 'partial')
    ctx.require(g(ctx, 'shallow', 'rev-parse', '--is-shallow-repository') == 'true', 'shallow は浅いcloneにします（--depth）。')
    ctx.require(g(ctx, 'shallow', 'rev-list', '--count', 'HEAD') == '3', 'shallow は直近3commitだけにします。')
    ctx.require(gr(ctx, 'partial', 'config', 'remote.origin.partialclonefilter')[1] == 'blob:none', 'partial は --filter=blob:none で作ります。')
    ctx.require(gr(ctx, 'partial', 'config', 'remote.origin.promisor')[1] == 'true', 'partial がpromisor remoteとして設定されていません。')
    ctx.require(g(ctx, 'partial', 'rev-list', '--count', 'HEAD') == '10', 'partial は全履歴を持ちます。')


SOL27 = '''git clone --depth 3 "file://$PWD/origin.git" shallow
git clone --filter=blob:none "file://$PWD/origin.git" partial'''
mission(27, 'shallow clone と partial clone で取得量を減らす',
        '巨大なリポジトリを全部取ると時間もディスクも無駄です。履歴の深さを減らす shallow clone と、中身(blob)を必要になるまで取らない partial clone を使い分けます。',
        ['--depth 3 の浅いclone', '--filter=blob:none の部分clone'], s27, c27, SOL27,
        ["git clone --depth 3 origin.git shallow\ngit clone --filter=blob:none origin.git partial", "git clone origin.git shallow\ngit clone origin.git partial"],
        'shallow clone（--depth N）は直近N commitだけを取得し、後から git fetch --deepen N や --unshallow で深くできます。partial clone（--filter=blob:none）は全commit・treeを取り、blobは checkout や参照の時にオンデマンドで取得するため、履歴を保ったまま転送量を減らせます。--filter=tree:0 のようにより絞ることも可能です。どちらもサーバーが対応している必要があり、ローカルパスではなく file:// やhttps/sshのURLが必要です。',
        'file:// を付けないと、オプションが無視されます。', 'git clone --depth / --filter=blob:none / file://$PWD/…')


# ============================================================ 28 clean -fdx dry-run
def s28(ctx):
    t = tok()
    mk(ctx, 'repo')
    cm(ctx, 'repo', 'init', {'a.txt': 'a\n', '.gitignore': 'build-cache/\n.env\n'})
    ctx.write(f'repo/junk-{t}.tmp', 'j\n')
    ctx.write(f'repo/scratch-{t}/note.txt', 'n\n')
    ctx.write('repo/build-cache/x.o', 'o\n')
    ctx.write('repo/.env', 'SECRET=keep\n')
    out = g(ctx, 'repo', 'clean', '-ndx')
    exp = sorted(x.strip() for x in out.splitlines())
    ctx.data.update(tok=t, exp=exp)
    req(ctx, f'repo の掃除です。-x は .gitignore で無視されたファイルまで消すので、先に git clean の dry-run（-n）で消える一覧を確認し、その出力を preview.txt（課題フォルダ直下）に保存します。'
             f'そのうえで、未追跡の junk-{t}.tmp と scratch-{t}/ とビルドキャッシュ build-cache/ は消し、秘密を含む .env だけは残して、git clean -fdx を安全に実行してください。')


def c28(ctx):
    d = ctx.data
    t = d['tok']
    need_repo(ctx, 'repo')
    pv = sorted(x.strip() for x in ctx.need_file('preview.txt').splitlines() if x.strip())
    ctx.require(pv == d['exp'], 'preview.txt は、掃除前に実行した git clean -ndx の出力（Would remove ...）と同じにします。')
    ctx.require(not ctx.exists(f'repo/junk-{t}.tmp') and not ctx.exists(f'repo/scratch-{t}') and not ctx.exists('repo/build-cache'), '対象のファイルが消えていません（git clean -fdx）。')
    ctx.require(ctx.read('repo/.env') == 'SECRET=keep\n', '.env は残します（-e で除外）。')
    ctx.require(ctx.read('repo/a.txt') == 'a\n' and ctx.isfile('repo/.gitignore'), '追跡中のファイルは変わりません。')


SOL28 = '''cd repo
git clean -ndx > ../preview.txt
git clean -fdx -e .env'''
mission(28, 'git clean -fdx を dry-run で確認してから実行する',
        'git clean は元に戻せない削除です。必ず -n（dry-run）で対象を確認してから、除外(-e)を付けて実行します。',
        ['dry-runの出力を保存', '-eで.envだけ守って掃除'], s28, c28, SOL28,
        ["cd repo\ngit clean -fdx", "cd repo\ngit clean -ndx > ../preview.txt\ngit clean -fd"],
        'git clean -n は dry-run（実際には消さず「Would remove」を表示）、-f は実行（確認なしは -f が必須）、-d は未追跡ディレクトリも、-x は .gitignore の無視ファイルも対象にします。ビルド成果物は消したいが .env のような秘密や個人設定は残したいので、-e <パターン> で除外します。実行前の -n は習慣にしてください（git clean -fdx は復元できません）。',
        '-x は無視ファイルも消します。', 'git clean -ndx / git clean -fdx -e .env')
