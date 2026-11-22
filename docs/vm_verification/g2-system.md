# g2 システム系VMモジュールの実VM検証記録

対象: sshd / mounts / journald / sysctl / limits
環境: tools/vmtest の Ubuntu 24.04 VM (g2-app, KVM, 2048MB, カーネル 6.8.0-147-generic, cgroup2, swapなし)。検証後に destroy 済み。
入れたパッケージ: なし（lvm2・openssh-server・softdog モジュールは最初から入っていた）。
共通: 各モジュールは snapshot `base` を取ったVMで実行。ホスト側の変更なし。

## 結果一覧

| モジュール | 結果 | 備考 |
|---|---|---|
| sshd | 実VMで通った（修正なし） | |
| mounts | 実VMで通った（修正なし） | lvm2とループデバイスは実際に動作 |
| journald | 直して通った | 不具合2件 |
| sysctl | 直して通った | 不具合3件。softdog はVMカーネルに存在 |
| limits | 実VMで通った（修正なし） | OOMは実際に発生 |

## sshd

| step | 終了コード | 判定 |
|---|---|---|
| setup | 0 | PASS |
| check（break前） | 1「まずbreakで…」 | 正しく拒否 |
| break | 0 | PASS（パスワード認証・root許可を実接続で確認して故障化） |
| check（緩い設定のまま） | 1（PasswordAuthentication等を列挙） | 正しく拒否 |
| 正しい解答（sed修正・AllowUsers・sshd -t・reload・ssh_config作成） | ProxyJumpの `id` が dojo-hard を返す | PASS |
| check（正解） | 0 `PASS: sshd -T実効値...` | PASS |
| reset | 0 | 残骸なし |

抜け道テスト（全て check が拒否した）: reloadなしでファイルだけ緩める / Match User で PasswordAuthentication yes / AllowUsers に root 追加 / PermitRootLogin prohibit-password / 正しいファイルだがreload前（「稼働中のsshdでパスワードログインが通ります」）/ ProxyJump の代わりに ProxyCommand / StrictHostKeyChecking no / MaxAuthTries 4 / PermitEmptyPasswords yes。break後の再堅牢化で再度PASS。
reset後: /etc/dojo-sshd・~/dojo-sshd-client・unit・pid・dojo-hard/dojo-hop ユーザー・22223待受なし。OS標準sshd(22)は active のまま。
未検証: 実際の再起動後の挙動。

## mounts

| step | 終了コード | 判定 |
|---|---|---|
| setup | 0 | PASS |
| check（break前） | 1 | 正しく拒否 |
| break | 0（LV・fstab誤UUIDブロック作成） | PASS |
| check（故障状態） | 1「A: fstab の行が不正です」 | 正しく拒否 |
| A: blkidでUUID取得・nofail追加・findmnt --verify・mount -a | | A のみ済みの時点で check は B で拒否 |
| B: swapfile 作成・0600・mkswap・swapon（fstab行なし） | | 「教材ブロック内に swapfile の fstab 行がありません」で拒否、行追加後はCで拒否 |
| C: pvcreate・vgextend・lvextend -L 80M（resize2fsなし） | | 「ファイルシステムがLVの大きさまで拡張されていません」で拒否 |
| resize2fs 後 check | 0 `達成: ...` | PASS |
| reset | 0 | 残骸なし |

抜け道テスト（全て拒否）: ソースを /dev/loop0 にする / nofail なし / A を umount / swapoff / swap行をコメントアウト / swap行をブロック外へ / swap権限644 / data.bin 改ざん。
reset後: losetup・VG/PV/LV・dm・swap・マウント・fstab（元ファイルと diff 一致）すべて残骸なし。break だけ行って reset する 2周目も同様にクリーン。
未検証: 実際の再起動でfstabが効くか、LVM自動検出。

## journald

| step | 終了コード | 判定 |
|---|---|---|
| setup（修正前） | 1 で無言終了 | FAIL（不具合1） |
| setup（修正後） | 0 | PASS |
| check（break前）/ break（設定前） | 1 / 1 | 正しく拒否 |
| 正しいdrop-in作成・restart・flush 後 break | 0 | PASS |
| check（故障） | 1「故障版の設定が残っています」 | 正しく拒否 |
| check（正解）修正後 | 0 `PASS: ...` | PASS（check連続2回もPASS） |
| reset | 0 | 残骸なし |

不具合と修正（labs/vm/guest/modules/journald.sh）:
1. `token=$(tr -dc 'a-f0-9' < /dev/urandom | head -c 12)` がディスパッチャの `set -euo pipefail` でSIGPIPE(141)となり、setup がメッセージ無しで失敗。`od -An -N6 -tx1 /dev/urandom | tr -d ' \n'` に変更。
2. checkが投入する probe 行にトークンが含まれ、check を実行するたびに「トークン付き・タグ dojo-j の件数」が増えた。学習者が正しく数えても answer の total と不一致になる（実機で total が 8→12→14→16 と増加を確認）。probe からトークンを除去（`dojo-probe-<乱数>`）し、集計側の `"probe-" in m` 除外も不要になったため削除。
tests/test_vm_journald.py に両点の回帰テストを追加。

抜け道テスト（全て拒否）: restartなし / answer なし / 誤answer(err=99) / SystemMaxUse=64G / MaxRetentionSec なし / Storage=auto / `=` 抜けの行 / 99-x.conf による上書き / 本体 journald.conf 編集 / /var/log/journal を o+w / `journalctl --vacuum-size=1K`（トークン消失を検出）。
注意: journald を数秒に何度も restart すると start-limit-hit になる（これは検証操作のせいで、学習者が連打した場合も同様。モジュールは対処していない）。
残存: reset は /var/log/journal（学習者が作成した永続ジャーナル）を削除しない。仕様どおり（本体不変）。

## sysctl

| step | 終了コード | 判定 |
|---|---|---|
| setup | 0 | PASS（modinfo softdog 成功、未ロード） |
| check（break前） | 1 | 正しく拒否 |
| break（60-dojo.conf作成前） | 1 | 正しく拒否 |
| break（作成後） | 0 | PASS |
| check（故障） | 1「vm.swappiness が 10 ではありません」 | 正しく拒否 |
| override 削除で解決後 check（修正前） | 1 で無言終了 | FAIL（不具合1） |
| 修正後 check（正解） | 0 PASS | PASS |
| reset | 0 | 残骸なし、vm.swappiness=60/vfs_cache_pressure=100 に復元 |

softdog: VMカーネル(6.8.0-147)に `softdog.ko.zst` があり modinfo/modprobe/rmmod 可能。モジュール変更は不要。
不具合と修正（labs/vm/guest/modules/sysctl.sh）:
1. 99-dojo-override.conf を削除して直すと、`n99=$(grep ... | head -1 | cut ...)` が不一致で pipefail により check が無言でexit 1（正しい解答が落ちる）。両方の代入に `|| true` を付与。
2. このsysctl(procps)は `sysctl --system` で存在しないキー(vm.swapiness)のエラーを出さないため、ログのgrepによる綴りチェックが機能せず、綴りミスの行が前段(50-x.conf)に残っていてもPASSした。60-dojo.conf・99-dojo-override.conf・*dojo*.conf の各キーが /proc/sys に存在するか直接検査する処理を追加。
3. Ubuntuカーネルが既に `blacklist softdog` を /lib/modprobe.d に持つため、`modprobe -c` だけの判定では学習者が install 行のみ書いてもPASSした。blacklist 行と install 行が学習者自身の /etc/modprobe.d/dojo-blacklist.conf に存在することを要求。
tests/test_vm_sysctl.py に回帰テストを追加。

抜け道テスト（修正後・全て拒否）: install行のみ / blacklist行のみ / 50-dojo-x.conf に綴りミス / 60-dojo.conf に綴りミス行追加 / 99に別の値(30) / 60を100/500へ書き換え / sysctl -w のみ（override残存）/ softdog ロード中。
未検証: 再起動後の永続性。

## limits

| step | 終了コード | 判定 |
|---|---|---|
| setup | 0 | 2サービス active |
| check（break前） | 1 | 正しく拒否 |
| break | 0 | mem: `Result=oom-kill NRestarts=5 MemoryMax=16777216`、journal に "killed by the OOM killer"。fd: `Result=exit-code LimitNOFILE=64` |
| check（ドロップインなし） | 1 | 正しく拒否 |
| 正解（mem MemoryMax=128M, fd LimitNOFILE=1024をドロップインで） | 0 `PASS: ...` | PASS |
| reset | 0 | 残骸なし |

MemoryMax=16M で実際に oom-kill となったため、サイズ変更は不要（swapなしVM）。
抜け道テスト（全て拒否）: 片方のみ修復 / MemoryMax=infinity / MemoryMax=64M（動くが範囲外） / LimitNOFILE=infinity / LimitNOFILE=128（起動せず） / ベースunit編集 / ドロップインで ExecStart 差し替え / CPUQuota 解除。daemon-reload のみ（restartなし）でもsystemdがcgroup上限をライブ反映するためPASSするが、cgroup memory.max との一致を確認しているので問題なし。
reset後: unit・ドロップイン・dojo-limitsユーザー・プロセス・/run・失敗ユニットなし（setup→break→reset の2周目も同様）。
