# Podman 実VM再検証（2026-11-22）

Ubuntu 24.04.5 LTS のKVM VM `g7-app`（カーネル 6.8.0-147、Podman 4.9.3）で実行した。専用ユーザーでローカルのrootfsをimportし、手動起動とQuadletでHTTP応答とボリュームへの書き込みを確認した。

初期化でユーザーの設定ディレクトリがroot所有になる事象を修正した。障害時の所有権変更は `podman unshare` でUIDとGIDをマッピングし、誤ったイメージ名は `Pull=never` で即座に失敗させる。判定ではユーザーsystemdの生成unitと自動起動設定、実ポートの公開範囲、実マウント、heartbeatの更新を確認する。

永続性の確認範囲は、専用ユーザーのsystemdマネージャーの再起動まで。VMのOS再起動後の挙動は未確認。

再実行は、専用app VM内に `podman`、`uidmap`、`busybox-static` を導入してから行う。

```sh
python3 tools/vmtest/verify_scenario.py g7-app tools/vmtest/scenarios/podman.sh /tmp/training-podman-vm.log
```

## 実出力

```text
VM=g7-app scenario=tools/vmtest/scenarios/podman.sh
bash: warning: setlocale: LC_ALL: cannot change locale (ja_JP.UTF-8)
OS=Ubuntu 24.04.5 LTS KERNEL=6.8.0-147-generic VM_TYPE=kvm
podman version 4.9.3
userdel: dojo-pod mail spool (/var/mail/dojo-pod) not found
専用ユーザー dojo-pod とそのコンテナ・イメージを削除しました。
まずQuadlet常駐を成功させ、breakで障害を作ります。
ASSERT before-setup expected=1 actual=1
手順: /home/dojo-pod/TASKS.txt (sudo -iu dojo-pod で操作)
ASSERT setup expected=0 actual=0
まずQuadlet常駐を成功させ、breakで障害を作ります。
ASSERT before-break expected=1 actual=1
まず dojo-app.container を作って常駐させます。
ASSERT before-quadlet expected=1 actual=1
ASSERT manual rootless run: local import, loopback HTTP and container volume write
障害を入れました。unitが起動せず、直しても書き込めない状態です。原因を調べてください。
ASSERT break expected=0 actual=0
ASSERT failed-unit expected=0 actual=0
ボリュームの所有者が dojo-pod ではありません: 166535
ASSERT broken expected=1 actual=1
ボリュームの所有者が dojo-pod ではありません: 166535
ASSERT image-only-repair expected=1 actual=1
8080/tcp は 127.0.0.1 の指定ポートだけに公開します。
ASSERT wrong-port expected=1 actual=1
全員書き込み可は解決ではありません。
ASSERT world-writable expected=1 actual=1
[Install] WantedBy=default.target を設定します。
ASSERT missing-autostart expected=1 actual=1
dojo-app.container から生成されたunitが必要です。
ASSERT plain-service expected=1 actual=1
--privilegedは使いません。
ASSERT privileged expected=1 actual=1
8080/tcp は 127.0.0.1 の指定ポートだけに公開します。
ASSERT all-interfaces expected=1 actual=1
専用ボリュームを /data に読み書き可能でbind mountします。
ASSERT read-only-volume expected=1 actual=1
コンテナがボリュームに書き込めていません(podman logs dojo-app)。
ASSERT http-without-heartbeat expected=1 actual=1
PASS: rootless Quadlet常駐・公開ポート応答・再起動後の復帰・subuid所有権の修復・実書き込みを確認しました。
ASSERT repaired expected=0 actual=0
ASSERT user manager restart: linger starts Quadlet automatically, HTTP returns expected body
userdel: dojo-pod mail spool (/var/mail/dojo-pod) not found
専用ユーザー dojo-pod とそのコンテナ・イメージを削除しました。
ASSERT reset expected=0 actual=0
ASSERT cleanup: no account, mappings, processes, home, linger, runtime, listeners or state
手順: /home/dojo-pod/TASKS.txt (sudo -iu dojo-pod で操作)
ASSERT second-setup expected=0 actual=0
userdel: dojo-pod mail spool (/var/mail/dojo-pod) not found
専用ユーザー dojo-pod とそのコンテナ・イメージを削除しました。
ASSERT second-reset expected=0 actual=0
ASSERT cleanup: no account, mappings, processes, home, linger, runtime, listeners or state

SCENARIO_EXIT=0
```
