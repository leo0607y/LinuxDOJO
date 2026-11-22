# permissions 実VM再検証（2026-11-22）

環境: 残存Ubuntu 24.04 KVM VM `g3-app`。中断前の報告を流用せず、現行ソースを同期して再実行した。

ACL: 前担当の継承検査強化に加え、getfacl -d が default: 接頭辞を省くため正解を拒否する不具合を修正。全ACLを取得して既定ACLを判定する。

再実行:
```sh
python3 tools/vmtest/verify_scenario.py g3-app tools/vmtest/scenarios/permissions.sh /tmp/training-permissions-vm.log
```

正解通過、未完了・故障・抜け道の拒否、reset後の専用資源の消失、2周目のsetup/resetを確認した。VM自体は他の未完了実習の再開に使うため保持。OS再起動後の永続性は今回未検証。

## 実出力

```text
VM=g3-app scenario=tools/vmtest/scenarios/permissions.sh
bash: warning: setlocale: LC_ALL: cannot change locale (ja_JP.UTF-8)
Only module report files and recorded lab users were removed
setup complete; read TASKS.txt then run break
ASSERT setup expected=0 actual=0
run break and repair first
ASSERT before-break expected=1 actual=1
ACL mask now blocks the named reader; future files also need a default ACL
ASSERT break expected=0 actual=0
reader cannot read existing report
ASSERT broken expected=1 actual=1
default ACL on reports must give dojo-reader r-x
ASSERT missing-default-acl expected=1 actual=1
user::rwx
user:dojo-reader:r-x
group::---
mask::r-x
other::---

user::rw-
user:dojo-reader:r--
group::---
mask::r--
other::---

user::rwx
user:dojo-reader:r-x
group::---
mask::r-x
other::---
default:user::rwx
default:user:dojo-reader:r-x
default:group::---
default:mask::r-x
default:other::---

PASS: existing and newly created files allow reader-only access
ASSERT repaired expected=0 actual=0
default ACL on reports must give dojo-reader r-x
ASSERT removed-default-acl expected=1 actual=1
other user must not read
ASSERT exposed-report expected=1 actual=1
user::rw-
user:dojo-reader:r--
group::---
mask::r--
other::---

user::rwx
user:dojo-reader:r-x
group::---
mask::r-x
other::---
default:user::rwx
default:user:dojo-reader:r-x
default:group::---
default:mask::r-x
default:other::---

PASS: existing and newly created files allow reader-only access
ASSERT repaired-again expected=0 actual=0
Only module report files and recorded lab users were removed
ASSERT reset expected=0 actual=0
ASSERT cleanup: report directory, users and groups absent
setup complete; read TASKS.txt then run break
ASSERT second-setup expected=0 actual=0
Only module report files and recorded lab users were removed
ASSERT second-reset expected=0 actual=0

SCENARIO_EXIT=0
```
