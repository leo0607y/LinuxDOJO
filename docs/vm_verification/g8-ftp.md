# ftp 実VM再検証（2026-11-22）

環境: 残存Ubuntu 24.04 KVM VM `g8-app`。中断前の報告を流用せず、現行ソースを同期して再実行した。

FTP: 正常設定のPASVアドレスを単体テストにも明示。実往復転送、chroot、匿名・リスト外拒否を検証。

再実行:
```sh
python3 tools/vmtest/verify_scenario.py g8-app tools/vmtest/scenarios/ftp.sh /tmp/training-ftp-vm.log
```

正解通過、未完了・故障・抜け道の拒否、reset後の専用資源の消失、2周目のsetup/resetを確認した。VM自体は他の未完了実習の再開に使うため保持。OS再起動後の永続性は今回未検証。

## 実出力

```text
VM=g8-app scenario=tools/vmtest/scenarios/ftp.sh
bash: warning: setlocale: LC_ALL: cannot change locale (ja_JP.UTF-8)
まず break で障害を作ります。
ASSERT before-setup expected=1 actual=1
Created symlink /etc/systemd/system/multi-user.target.wants/dojo-ftp.service → /etc/systemd/system/dojo-ftp.service.
手順: /var/lib/linuxdojo-vm-lab/state/ftp/TASKS.txt (sudoで読む)。次に sudo dojo-vm-lab ftp break
ASSERT setup expected=0 actual=0
まず break で障害を作ります。
ASSERT before-break expected=1 actual=1
FTPが壊れた状態です。ログを調べ、設定とディレクトリ構造を直してください。
ASSERT break expected=0 actual=0
設定の確認: anonymous_enable=NO
設定の確認: pasv_address=127.0.0.1
設定の確認: userlist_enable=YES と userlist_deny=NO(許可リスト方式)
設定の確認: pasv_min_port=30000 / pasv_max_port=30010
ASSERT broken expected=1 actual=1
chrootルート /srv/dojo-ftp は root 所有で書込み不可にします。
ASSERT writable-root expected=1 actual=1
PASS: ログイン・匿名拒否・チェックサム付き往復転送・chroot脱出遮断・PASV範囲・リスト外ユーザー拒否を実接続で確認しました。
ASSERT repaired expected=0 actual=0
設定の確認: allow_writeable_chroot=YES は使わず、chrootルートを root:root 755 にして書込み用サブディレクトリを分けます
ASSERT writable-chroot-shortcut expected=1 actual=1
userlistに無いユーザー dojo-ftp2 が(正しいパスワードで)ログインできてしまいます。
ASSERT extra-user expected=1 actual=1
設定の確認: pasv_address=127.0.0.1
ASSERT missing-pasv-address expected=1 actual=1
PASS: ログイン・匿名拒否・チェックサム付き往復転送・chroot脱出遮断・PASV範囲・リスト外ユーザー拒否を実接続で確認しました。
ASSERT repaired-again expected=0 actual=0
専用vsftpd構成を削除しました。OS標準のvsftpd設定は変更していません。
ASSERT reset expected=0 actual=0
ASSERT cleanup: no dedicated files/accounts/listener/state; OS service unchanged
Created symlink /etc/systemd/system/multi-user.target.wants/dojo-ftp.service → /etc/systemd/system/dojo-ftp.service.
手順: /var/lib/linuxdojo-vm-lab/state/ftp/TASKS.txt (sudoで読む)。次に sudo dojo-vm-lab ftp break
ASSERT second-setup expected=0 actual=0
専用vsftpd構成を削除しました。OS標準のvsftpd設定は変更していません。
ASSERT second-reset expected=0 actual=0

SCENARIO_EXIT=0
```
