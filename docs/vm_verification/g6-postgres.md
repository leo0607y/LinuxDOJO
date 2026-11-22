# PostgreSQL 実VM再検証（2026-11-22）

Ubuntu 24.04.5 LTS の KVM VM `g6-app` で PostgreSQL 16.15 の専用クラスタ `16/dojo` を作成し、ポート 5433 で検証した。

- `reload` 後は `max_connections=200` と `pending_restart=true`、`restart` 後は `50` と `false` を実 SQL で確認した。`pg_hba.conf` の `trust` を削除してもリロード前は接続できるため、判定は修復を拒否した。
- 修復後は両ロールの TCP SCRAM ログイン、最小権限、論理ダンプから復元した 1000 行の件数とチェックサム、`pg_verifybackup` が通過した。過剰権限、異なる復元先、データの差分、途中で切ったダンプ、壊れた物理バックアップを拒否した。
- PostgreSQL 16 のバックアップマニフェストにはクラスタ識別子がないため、`pg_controldata` の識別子を稼働中の専用クラスタと照合した。`pg_verifybackup` が通る以前のクラスタのバックアップも拒否した。
- 2 周とも `reset` 後に専用の設定・データ・バックアップ・ログ・ソケット・待受・状態ファイルが消えた。標準 `16/main` のクラスタ状態、設定ファイルのチェックサム、稼働 PID は実行前後で一致した。

再実行には Ubuntu 24.04 の専用 `app` VM と、VM 内の `postgresql`・`postgresql-client` パッケージが必要。

```sh
python3 tools/vmtest/verify_scenario.py g6-app tools/vmtest/scenarios/postgres.sh /tmp/training-postgres-verified.log
```

物理バックアップは整合性と由来を検証した。物理復元先の起動と VM 自体の再起動後は未検証。

## 実出力

```text
VM=g6-app scenario=tools/vmtest/scenarios/postgres.sh
bash: warning: setlocale: LC_ALL: cannot change locale (ja_JP.UTF-8)
Guest Ubuntu 24.04.5 LTS, kvm
psql (PostgreSQL) 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1)
まずbreakで故障を作ります。
ASSERT before-setup expected=1 actual=1
Creating new PostgreSQL cluster 16/dojo ...
/usr/lib/postgresql/16/bin/initdb -D /var/lib/postgresql/16/dojo --auth-local peer --auth-host scram-sha-256 --no-instructions
The files belonging to this database system will be owned by user "postgres".
This user must also own the server process.

The database cluster will be initialized with locale "C.UTF-8".
The default database encoding has accordingly been set to "UTF8".
The default text search configuration will be set to "english".

Data page checksums are disabled.

fixing permissions on existing directory /var/lib/postgresql/16/dojo ... ok
creating subdirectories ... ok
selecting dynamic shared memory implementation ... posix
selecting default max_connections ... 100
selecting default shared_buffers ... 128MB
selecting default time zone ... Etc/UTC
creating configuration files ... ok
running bootstrap script ... ok
performing post-bootstrap initialization ... ok
syncing data to disk ... ok
Ver Cluster Port Status Owner    Data directory              Log file
16  dojo    5433 down   postgres /var/lib/postgresql/16/dojo /var/log/postgresql/postgresql-16-dojo.log
専用PostgreSQLクラスタ 16/dojo (ポート5433, 設定 /etc/postgresql/16/dojo, データ /var/lib/postgresql/16/dojo)。標準のmainクラスタは触らない。
操作: sudo -u postgres psql -p 5433 shopdb （unixソケット、peer認証）。shopdbにはshop.orders(1000行)とprivate.secretsがある。
1. ロールshop_app(アプリ用)とshop_ro(読み取り専用)をLOGIN付きで作る。パスワードはSCRAM保存で。
   現在password_encryptionがmd5になっている。設定を直してからパスワードを設定し直すこと。
2. 最小権限: shop_appはshop.ordersの読み書きだけ(SELECT/INSERT/UPDATE+シーケンス)。DROP/TRUNCATE/CREATE/privateは不可。
   shop_roはshopスキーマのSELECTのみ。ALTER DEFAULT PRIVILEGESで、今後作る表にも反映する。superuserは使わない。
3. /etc/postgresql/16/dojo/postgresql.conf: listen_addresses='localhost'を明示、max_connections=50 (末尾の初期値行を直す)。
   /etc/postgresql/16/dojo/pg_hba.conf: host行はループバックのscram-sha-256のみ。replicationのlocal行は残す。
   reloadで足りる変更とrestartが必要な変更を区別: pg_ctlcluster 16 dojo reload / restart。
   SHOW max_connections; と pg_settings.pending_restart で反映を確かめる。
4. 論理バックアップ: sudo -u postgres pg_dump -Fc -p 5433 -f /var/lib/dojo-pg/shop.dump shopdb
   新DB shop_restore を作り pg_restore -d shop_restore。件数とチェックサム(md5(string_agg(...)))を元と照合。
5. 物理バックアップ: sudo -u postgres pg_basebackup -p 5433 -D /var/lib/dojo-pg/base -Fp ; 続けてpg_verifybackup /var/lib/dojo-pg/base
6. sudo dojo-vm-lab postgres break （全部できてから）。故障: trust設定・superuserのアプリ用ロール・誤ったDBへのリストア。
   調査して直す。trustのまま、またはsuperuserのまま通すのは不正解。
7. sudo dojo-vm-lab postgres check ; 終了後 reset （専用クラスタとバックアップのみ削除）
ASSERT setup expected=0 actual=0
専用クラスタが既にあります。resetせず既存データを上書きしません。
ASSERT duplicate-setup expected=1 actual=1
まずbreakで故障を作ります。
ASSERT before-break expected=1 actual=1
listen_addressesをlocalhostだけに、postgresql.confで明示し、restartで反映します。
break前に、手順1〜5を正しく完了させます。
ASSERT incomplete expected=1 actual=1
ASSERT reload keeps max_connections=200 and marks pending_restart
listen_addressesをlocalhostだけに、postgresql.confで明示し、restartで反映します。
break前に、手順1〜5を正しく完了させます。
ASSERT reload-only expected=1 actual=1
ASSERT restart activates max_connections=50 and clears pending_restart
shop_appはログイン可・最小権限・パスワードはSCRAM保存にします。
break前に、手順1〜5を正しく完了させます。
ASSERT missing-roles expected=1 actual=1
/var/lib/dojo-pg/shop.dump にpg_dump -Fcのダンプがありません。
break前に、手順1〜5を正しく完了させます。
ASSERT missing-dump expected=1 actual=1
リストア先データベースshop_restoreがありません。
break前に、手順1〜5を正しく完了させます。
ASSERT missing-restore expected=1 actual=1
/var/lib/dojo-pg/base にpg_basebackup(-Fp)のバックアップがありません。
break前に、手順1〜5を正しく完了させます。
ASSERT missing-basebackup expected=1 actual=1
backup successfully verified
故障を入れました: pg_hbaがtrust、shop_appがsuperuser、ダンプが管理DB(postgres)に復元され、shop_restoreが無い。見つけて直します(元のpg_hbaに丸ごと戻すだけでなく原因を理解すること)。
ASSERT break expected=0 actual=0
ASSERT break restored 1000 rows into postgres, removed shop_restore and elevated shop_app
pg_hba.confにtrustが残っています。
ASSERT broken expected=1 actual=1
パスワード無しでTCP接続できます(shop_app)。pg_hba.confを直し、reloadします。
ASSERT hba-edited-without-reload expected=1 actual=1
shop_appはログイン可・最小権限・パスワードはSCRAM保存にします。
ASSERT still-superuser expected=1 actual=1
リストア先データベースshop_restoreがありません。
ASSERT no-restored-database expected=1 actual=1
管理用のpostgresデータベースにshop/privateスキーマが紛れ込んでいます。間違った先へのリストアを片付けます。
ASSERT still-restored-into-postgres expected=1 actual=1
NOTICE:  drop cascades to table shop.orders
NOTICE:  drop cascades to table private.secrets
PASS: SCRAM/loopback/最小権限・実SQLでの読み書き拒否・pg_dump/pg_restoreの件数とチェックサム・pg_verifybackupを確認しました。
ASSERT repaired expected=0 actual=0
ASSERT both learner roles authenticated with SCRAM over TCP and read 1000 fixture rows
shop_app のループバック接続に有効なSCRAM認証設定がありません。pg_hba.confを確認し、reloadします。
ASSERT scram-rule-for-wrong-role expected=1 actual=1
shop_appがDELETEできます。
ASSERT overprivileged-app expected=1 actual=1
ALTER DEFAULT PRIVILEGESで、今後作る表にもshop_roのSELECT権限だけを付与します。
ASSERT overprivileged-future-tables expected=1 actual=1
shop_restoreの件数/チェックサムが一致しません: 1000:b2723b5eda03c981bea86c281a2b679f (期待 1000:86f22d576147df545a65edcfc72220f9)
ASSERT mismatched-restore expected=1 actual=1
ダンプを最後まで読み取れません。pg_dumpをやり直します。
ASSERT truncated-dump expected=1 actual=1
pg_verifybackupが失敗します:
pg_verifybackup: error: "PG_VERSION" has size 7 on disk but size 3 in the manifest
ASSERT corrupt-basebackup expected=1 actual=1
PASS: SCRAM/loopback/最小権限・実SQLでの読み書き拒否・pg_dump/pg_restoreの件数とチェックサム・pg_verifybackupを確認しました。
ASSERT repaired-again expected=0 actual=0
専用クラスタとバックアップを削除しました。mainクラスタとパッケージは変更していません。
ASSERT reset expected=0 actual=0
ASSERT cleanup: dedicated configuration, data, backups, log, listener and state removed; main unchanged
Creating new PostgreSQL cluster 16/dojo ...
/usr/lib/postgresql/16/bin/initdb -D /var/lib/postgresql/16/dojo --auth-local peer --auth-host scram-sha-256 --no-instructions
The files belonging to this database system will be owned by user "postgres".
This user must also own the server process.

The database cluster will be initialized with locale "C.UTF-8".
The default database encoding has accordingly been set to "UTF8".
The default text search configuration will be set to "english".

Data page checksums are disabled.

fixing permissions on existing directory /var/lib/postgresql/16/dojo ... ok
creating subdirectories ... ok
selecting dynamic shared memory implementation ... posix
selecting default max_connections ... 100
selecting default shared_buffers ... 128MB
selecting default time zone ... Etc/UTC
creating configuration files ... ok
running bootstrap script ... ok
performing post-bootstrap initialization ... ok
syncing data to disk ... ok
Ver Cluster Port Status Owner    Data directory              Log file
16  dojo    5433 down   postgres /var/lib/postgresql/16/dojo /var/log/postgresql/postgresql-16-dojo.log
専用PostgreSQLクラスタ 16/dojo (ポート5433, 設定 /etc/postgresql/16/dojo, データ /var/lib/postgresql/16/dojo)。標準のmainクラスタは触らない。
操作: sudo -u postgres psql -p 5433 shopdb （unixソケット、peer認証）。shopdbにはshop.orders(1000行)とprivate.secretsがある。
1. ロールshop_app(アプリ用)とshop_ro(読み取り専用)をLOGIN付きで作る。パスワードはSCRAM保存で。
   現在password_encryptionがmd5になっている。設定を直してからパスワードを設定し直すこと。
2. 最小権限: shop_appはshop.ordersの読み書きだけ(SELECT/INSERT/UPDATE+シーケンス)。DROP/TRUNCATE/CREATE/privateは不可。
   shop_roはshopスキーマのSELECTのみ。ALTER DEFAULT PRIVILEGESで、今後作る表にも反映する。superuserは使わない。
3. /etc/postgresql/16/dojo/postgresql.conf: listen_addresses='localhost'を明示、max_connections=50 (末尾の初期値行を直す)。
   /etc/postgresql/16/dojo/pg_hba.conf: host行はループバックのscram-sha-256のみ。replicationのlocal行は残す。
   reloadで足りる変更とrestartが必要な変更を区別: pg_ctlcluster 16 dojo reload / restart。
   SHOW max_connections; と pg_settings.pending_restart で反映を確かめる。
4. 論理バックアップ: sudo -u postgres pg_dump -Fc -p 5433 -f /var/lib/dojo-pg/shop.dump shopdb
   新DB shop_restore を作り pg_restore -d shop_restore。件数とチェックサム(md5(string_agg(...)))を元と照合。
5. 物理バックアップ: sudo -u postgres pg_basebackup -p 5433 -D /var/lib/dojo-pg/base -Fp ; 続けてpg_verifybackup /var/lib/dojo-pg/base
6. sudo dojo-vm-lab postgres break （全部できてから）。故障: trust設定・superuserのアプリ用ロール・誤ったDBへのリストア。
   調査して直す。trustのまま、またはsuperuserのまま通すのは不正解。
7. sudo dojo-vm-lab postgres check ; 終了後 reset （専用クラスタとバックアップのみ削除）
ASSERT second-setup expected=0 actual=0
backup successfully verified
バックアップがこのクラスタのものではありません。
break前に、手順1〜5を正しく完了させます。
ASSERT valid-backup-from-previous-cluster expected=1 actual=1
故障を入れました: pg_hbaがtrust、shop_appがsuperuser、ダンプが管理DB(postgres)に復元され、shop_restoreが無い。見つけて直します(元のpg_hbaに丸ごと戻すだけでなく原因を理解すること)。
ASSERT second-break expected=0 actual=0
専用クラスタとバックアップを削除しました。mainクラスタとパッケージは変更していません。
ASSERT second-reset expected=0 actual=0
ASSERT cleanup: dedicated configuration, data, backups, log, listener and state removed; main unchanged

SCENARIO_EXIT=0
```
