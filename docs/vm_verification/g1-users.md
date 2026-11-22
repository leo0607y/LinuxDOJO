# users 実VM再検証（2026-11-22）

環境: 既存Ubuntu 24.04 KVM `g1-app`。現行モジュールを同期し、setupから再検証。
ユーザー・シェル・グループ・最小sudoを復旧。許可コマンドはsudo -lで確認し、実行しない。

再現: `python3 tools/vmtest/verify_scenario.py g1-app tools/vmtest/scenarios/users.sh /tmp/training-users-vm.log`

正解・不完全/故障/抜け道拒否・reset後の専用状態消失を実出力で確認。再起動の確認は今回対象外。VMは他課題再開用に保持。lynisは仕様どおり導入済みパッケージを残す。

```text
VM=g1-app scenario=tools/vmtest/scenarios/users.sh
bash: warning: setlocale: LC_ALL: cannot change locale (ja_JP.UTF-8)
まずuserを作成・sudo設定し、breakで事故を作ります。
ASSERT before-setup expected=1 actual=1
app VMのubuntuユーザーで、sudo を付けて操作する。
1. 専用グループ dojo-ops は作成済み (getent group dojo-ops)。
2. ユーザー dojo-alice を作成: ホームあり・シェルは /bin/bash・dojo-ops に所属。
   (useradd のオプション -m -s -G。sudo/adminグループには入れない)
3. /etc/sudoers.d/dojo-users を作る。dojo-alice に「systemctl is-active ssh」だけ
   パスワードなしで許可する。ファイルは root:root 0440。
   直接編集せず、一時ファイルを visudo -cf で検証してから install で置く。
   構文エラーを置くと sudo 全体が壊れる。必ず visudo -cf / visudo -c を使う。
4. 確認: id dojo-alice / getent passwd dojo-alice / sudo -l -U dojo-alice
   sudo runuser -u dojo-alice -- sudo -n -l /usr/bin/id  (許可されないはず)
5. sudo dojo-vm-lab users break   (権限の事故を再現: 何が変わったか自分で調べる)
6. 調査と修復: シェル・グループ・sudoersを元の最小権限に戻す。ALLのまま放置は不正解。
   sudo dojo-vm-lab users check
7. 終了後 sudo dojo-vm-lab users reset (dojo-alice・dojo-ops・sudoersを削除)
checkは許可コマンドを実行せず sudo -l で判定する。
ASSERT setup expected=0 actual=0
まずuserを作成・sudo設定し、breakで事故を作ります。
ASSERT incomplete expected=1 actual=1
/var/lib/linuxdojo-vm-lab/state/users/policy: parsed OK
まずuserを作成・sudo設定し、breakで事故を作ります。
ASSERT before-break expected=1 actual=1
事故が発生しました。dojo-alice のシェル・グループ・sudo権限を調べて最小権限に戻します。
ASSERT break expected=0 actual=0
ログインシェルが /bin/bash ではありません: /usr/sbin/nologin
ASSERT broken expected=1 actual=1
許可が広すぎます: /usr/bin/id も実行できる設定です。
ASSERT sudo-all-shortcut expected=1 actual=1
/var/lib/linuxdojo-vm-lab/state/users/policy: parsed OK
PASS: アカウント・グループ・シェル・sudoers(0440/visudo)・最小権限(sudo -lで判定)の復旧を確認しました。
ASSERT repaired expected=0 actual=0
管理者系グループ sudo に所属しています。
ASSERT admin-group expected=1 actual=1
Removing user dojo-alice from group sudo
sudoersは 0440 root:root にします。
ASSERT bad-mode expected=1 actual=1
アカウントが期限切れ/無効化されています。
ASSERT expired-account expected=1 actual=1
PASS: アカウント・グループ・シェル・sudoers(0440/visudo)・最小権限(sudo -lで判定)の復旧を確認しました。
ASSERT repaired-again expected=0 actual=0
専用のユーザー・グループ・sudoersを削除しました。他のアカウントは変更していません。
ASSERT reset expected=0 actual=0
/etc/sudoers: parsed OK
/etc/sudoers.d/90-cloud-init-users: parsed OK
/etc/sudoers.d/README: parsed OK
ASSERT cleanup: account/group/home/sudoers/state removed, global sudoers valid

SCENARIO_EXIT=0
```
