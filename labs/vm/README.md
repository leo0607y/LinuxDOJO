# LinuxDOJO：使い捨てVMで構築・調査・復旧する

この実習は、模擬ターミナルでは再現しにくい実際のLinuxカーネル、マウント、systemd、権限、サービスの動きを確認するための別コースです。
通常の実践モードと進捗は別です。実行結果を確認するまでは、VM実習を修了した扱いにしません。

## 準備と対象

新しく作る専用のUbuntu 24.04 VMを使います。既存サーバーや普段使うLinuxへゲスト用スクリプトをコピーして実行しないでください。
ホスト側のエクスポート処理はファイルを書くだけです。Multipassの導入、VMの起動、ホストのネットワーク変更は自動では行いません。

- Multipassとハードウェア仮想化が使えるPCが必要です。ホスト用の導入方法は[公式ドキュメント](https://canonical.com/multipass/docs/latest/how-to-guides/install-multipass/)で確認してください。
- 2台で合計CPU 4個、メモリ4 GiB、仮想ディスク32 GiBを割り当てる例です。ホスト自身の余裕も確保してください。
- 最初のイメージ取得とパッケージ導入にはネット接続が必要です。既存の模擬教材のオフライン利用とは条件が異なります。
- VMの通常のネットワークはホストや外部へ通信できる場合があります。専用VMの作成だけでネットワークが完全隔離されるわけではありません。外部への負荷試験や診断は行いません。
- cloud-initは標準のnginx/dnsmasqサービスを停止・自動起動無効にします。実習では専用の設定・ユニットを使います。

## 1. 教材をエクスポートする

リポジトリのルートで、まだ存在しない出力先を指定します。

```bash
python3 -m engine.vm_labs list
python3 -m engine.vm_labs export --output ./vm-lab-bundle
```

出力には役割ごとのcloud-init、ゲスト用スクリプト、モジュール一覧、ファイルのSHA-256が入ります。
このコマンドはMultipassやsudoを実行しません。既存の出力先は上書きしません。

## 2. 新しいVMを2台作る

同名の既存VMがないことを `multipass list` で確認します。同名があれば別用途のVMを削除せず、この実習用に管理者と構成を調整してください。
この教材のゲストガードは、名前とマーカーが一致する専用VMだけで動作します。

```bash
multipass launch 24.04 --name linuxdojo-app --cpus 2 --memory 2G --disk 16G --timeout 1200 --cloud-init vm-lab-bundle/app-cloud-init.yaml
multipass launch 24.04 --name linuxdojo-client --cpus 2 --memory 2G --disk 16G --timeout 1200 --cloud-init vm-lab-bundle/client-cloud-init.yaml
multipass exec linuxdojo-app -- cloud-init status --wait
multipass exec linuxdojo-client -- cloud-init status --wait
multipass info linuxdojo-app linuxdojo-client
```

cloud-initが失敗した場合は先にその原因を調べます。起動時の完了メッセージだけで、すべてのパッケージ導入が成功したとは判断しません。
`/var/log/cloud-init-output.log` と `cloud-init status --long` を確認してください。

## 3. 最初の復元地点を作る

VMを停止してからスナップショットを作成します。スナップショット機能の対応は利用中のMultipassとドライバーに依存します。
未対応なら、教材用の2台を再作成できることを復旧手段にしてください。ホストの既存VMを変更する必要はありません。

```bash
multipass stop linuxdojo-app linuxdojo-client
multipass snapshot linuxdojo-app --name clean
multipass snapshot linuxdojo-client --name clean
multipass start linuxdojo-app linuxdojo-client
```

## 4. 1課題ずつ実習する

```bash
multipass shell linuxdojo-app
sudo dojo-vm-lab list
```

表示された課題IDを使い、次の順で進めます。`<課題ID>` は山括弧を含めず実際の名前に置き換えます。

```text
sudo dojo-vm-lab <課題ID> setup
sudo dojo-vm-lab <課題ID> check
sudo dojo-vm-lab <課題ID> break
（状態・ログ・設定を調査して修正する）
sudo dojo-vm-lab <課題ID> check
```

- `setup`：正常な初期状態を用意し、確認点と対象を表示します。
- `break`：その課題の専用ファイル・サービスに限定した故障を作ります。正常時は課題のREADME/TASKにあるコマンドで比較します。boot・storage・webstackの修了判定は、故障投入と復旧後の再起動を済ませるまで不合格になります。
- `check`：実際の状態を検査します。失敗時は終了コードが0以外になります。修正してから再実行します。
- `reset`：その課題の専用構成を解除、または初期配置へ戻します。動作は課題の説明に従います。必要な証拠は先に保存します。

1課題ごとに、対象、正常時と故障時の差、調べた根拠、変更内容、修正後の結果を記録してください。
原因を理解せず `reset` だけで復旧した場合は、自力で直した扱いにしません。
各モジュールが表示する指示を読み、課題が要求する再起動や別ユーザー・別VMからの確認も行います。

ネットワーク越しの確認は、`multipass info linuxdojo-app` に表示される実習VMのIPv4アドレスを使います。
サービスの課題で指定されたポートだけを対象にし、`linuxdojo-client` から通常の `curl` などで結果を比較します。
具体的なポートと証明書の検証方法はサービス課題の指示に従ってください。

## 2台でDNSとHTTPを比較する

ホストからapp VMのIPを調べ、両方で課題を準備します。

```bash
multipass info linuxdojo-app
multipass exec linuxdojo-app -- sudo dojo-vm-lab network setup
multipass exec linuxdojo-client -- sudo dojo-vm-lab network setup
multipass shell linuxdojo-client
sudoedit /var/lib/linuxdojo-vm-lab/state/network/app-ip
sudo dojo-vm-lab network check
```

app-ipの `APP_PRIVATE_IP` を、infoに表示されたapp VMのRFC1918 IPv4アドレス1行へ置き換えます。
最初のcheckが成功したら、app側で故障を投入します。

```bash
multipass exec linuxdojo-app -- sudo dojo-vm-lab network break
multipass exec linuxdojo-client -- sudo dojo-vm-lab network check
```

このcheckは不合格になるのが期待値です。clientでIP直指定のHTTP（appの18080番）と、DNS（15353番）の回答を比較します。
app側の `/var/lib/linuxdojo-vm-lab/state/network/dnsmasq.conf` を読み、`address=/app.dojo.test/` の回答だけを正しいapp IPへ戻してください。
`listen-address` やHTTPサーバーを変更して問題を隠さず、`sudo systemctl restart dojo-network-dns.service` 後にclientのcheckを再実行します。
必要ならclientで `sudo tcpdump -ni any 'port 15353 or port 18080'` を使い、この実習の問い合わせと応答を観察します。Ctrl+Cで終了します。

## TLS付きWeb構成を直し、再起動後にも確認する

```bash
multipass shell linuxdojo-app
sudo dojo-vm-lab webstack setup
sudo cat /var/lib/linuxdojo-vm-lab/state/webstack/TASK.txt
sudo dojo-vm-lab webstack break
sudo journalctl -u dojo-webstack-proxy.service -b
sudo ss -ltnp
```

バックエンドの127.0.0.1:18088と、プロキシの8088/8448番を区別します。
`/var/lib/linuxdojo-vm-lab/state/webstack/nginx.conf` の両方のproxy_passを正しい上流ポートへ戻し、次を実行します。

```bash
sudo nginx -t -c /var/lib/linuxdojo-vm-lab/state/webstack/nginx.conf
sudo systemctl reload dojo-webstack-proxy.service
sudo curl --noproxy '*' --cacert /var/lib/linuxdojo-vm-lab/state/webstack/server.crt --resolve app.dojo.test:8448:127.0.0.1 https://app.dojo.test:8448/health
sudo dojo-vm-lab webstack check
```

通信が直っても、修了checkは故障投入後の再起動がまだなら不合格になります。ホスト側から `multipass restart linuxdojo-app` を実行してからcheckを再実行します。
TLS確認では `-k` を使わず、演習用の自己署名公開証明書を明示的に信頼し、SANの名前も検証します。実際の公開CA発行・更新はこの課題に含みません。

clientからも検証する場合は、ホストを経由して**公開証明書だけ**をコピーします。

```bash
multipass transfer linuxdojo-app:/var/lib/linuxdojo-vm-lab/state/webstack/server.crt ./dojo-server.crt
multipass transfer ./dojo-server.crt linuxdojo-client:/home/ubuntu/dojo-server.crt
multipass shell linuxdojo-client
```

clientでappのIPを指定し、`curl --noproxy '*' --cacert /home/ubuntu/dojo-server.crt --resolve app.dojo.test:8448:APPのIP https://app.dojo.test:8448/health` を実行します。
`APPのIP` はinfoで確認した値へ置き換えます。秘密鍵server.keyをclientやホストへコピーする必要はありません。

## 実装済みの範囲と追加の手動実習

導入後の使い方は [SOFTWARE.md](SOFTWARE.md) の `packages`・`software` を順に進めます。
パッケージの導入・設定保持更新・設定故障からの復旧・remove・purgeと、実service/timerの運用・再起動・撤去を段階ごとに検査します。

SSHはapp VMのubuntuユーザーで次のように始めます。

```bash
sudo dojo-vm-lab ssh setup
cat ~/dojo-ssh-client/TASK.txt
```

専用のlocalhost:22222、専用アカウントと鍵を使い、ホスト鍵の指紋照合、実際の接続・scp転送、
authorized_keysの権限障害の診断・復旧、rsync取得を行います。通常のsshd設定は変更しません。
TASK.txtの順に操作し、終了後は `sudo dojo-vm-lab ssh reset` で専用構成を削除します。

| モジュール | 実際に検証する範囲 | このモジュールだけでは扱わない範囲 |
|---|---|---|
| storage | 専用ext4イメージ、inode枯渇、保持データ、再起動後のループマウント | 物理ディスク、パーティション変更、LVM/RAID、破損したルートFS |
| boot | 専用systemdサービスの設定喪失と復旧、再起動後の稼働 | OS起動不能、GRUB、initramfs、レスキューメディア |
| network | 2台間のDNS/HTTP、名前解決と疎通の比較 | 経路故障の自動注入、IPv6、組織のファイアウォール設計 |
| performance | 小さな専用プロセスのログ・入出力・straceによる調査 | 大規模負荷の性能設計、CPU/メモリ/I/O全体のボトルネック測定 |
| permissions | 専用ユーザーと実際のACLによる許可・拒否の確認 | SELinux/AppArmorポリシーの設計・運用 |
| webstack | Nginx→Python→SQLite、TLSの名前検証、502、再起動後の復旧 | PostgreSQL等のDBサーバー運用、公開CA更新、冗長化 |
| packages | 実debの導入・設定・更新・故障復旧・remove・purge | 外部リポジトリ署名鍵の更新、RPMの実操作 |
| software | 実service/timerの導入・設定故障・journal・再起動・撤去 | 常駐アプリごとのreload仕様・クラスタ運用 |
| ssh | 実鍵認証・ホスト鍵検証・scp/rsync・権限障害の復旧 | インターネット公開・組織の鍵管理・踏み台設計 |

不足部分は、次の成果物を作る手動実習として続けます。これらは現時点で自動の故障投入・修了判定を実装していません。

1. **ISOからのOS導入**：別の新規VMと空の仮想ディスクを使い、公式Ubuntu Serverインストーラーから導入します。`os-release`、`lsblk -f`、起動方式、利用者、SSH設定を記録し、スナップショットを作ります。cloud-initイメージの起動成功だけでインストール実習を修了した扱いにはしません。
2. **LVMと容量拡張**：さらに別の使い捨てVMへ追加した空の仮想ディスクだけを対象に、PV/VG/LV・ファイルシステム・マウントの関係を図示します。対象ディスクの識別情報と導入前後の`lsblk`/`pvs`/`vgs`/`lvs`/`df`を記録し、データ保持と容量拡張を確認します。ホストや既存データのあるディスクを教材対象にしません。
3. **起動復旧**：ホスト側のスナップショット復元が動作することを先に確認した別VMで、公式のレスキュー手順を読み、コンソールからのログ取得と復旧計画を作成します。この教材のbootモジュールを実行しただけでGRUB復旧を経験した扱いにはしません。
4. **MACとディストリビューション差**：UbuntuのAppArmorと、別の使い捨てVMでのSELinuxについて、既存の公式プロファイル・監査ログ・許可と拒否の違いを比較します。単に無効化してサービスが動く状態は、ポリシーを修正した成果に数えません。
5. **再構築**：新規VMへWeb構成を作り直し、SQLiteのバックアップAPIで取得したデータを復元します。URL・TLS・既存データ・起動時のサービスを別VMから検証し、構築手順に含まれない手作業を洗い出します。

## 5. スナップショットへ戻る

復元はスナップショット後のVM内の変更を戻します。VM外へ必要な記録をコピーしてから操作します。
`restore` の対話確認では、現在の状態を別のスナップショットへ残すか選べます。

```bash
multipass stop linuxdojo-app linuxdojo-client
multipass restore linuxdojo-app.clean
multipass restore linuxdojo-client.clean
multipass start linuxdojo-app linuxdojo-client
```

起動できなくなったケースでも、ホスト側からスナップショットへ戻せる手段を維持します。
この教材の故障注入は専用のサービスやデータ領域に限定し、ホストのブートローダーや物理ディスクは操作しません。

## この実装で検証したこと・まだ実測が必要なこと

2026-11-21には専用Ubuntu 24.04.5 KVM VMで9モジュールを実行しました。boot・storage・webstack・softwareの故障復旧と再起動後、SSHの実認証・転送と再起動後、実aptの更新・撤去、permissions・performanceを確認しました。networkは2台のVMでDNS故障前後と修復後を検証済みです。詳細は教材本体の `docs/coverage.md` の「実装と検証記録」を参照します。これは教材の特定環境での検証で、全ホスト・全Multipassドライバーの動作確認ではありません。

エクスポート、生成内容の整合性、ゲストスクリプトの構文、VM外で動作を拒否するガードは自動テストします。
開発環境でMultipassが使えない場合、ゲストのパッケージ導入・デバイス作成・再起動・実際の復旧成功までは検証済みとはしません。
VM実習の成功結果は、利用者が専用VMで `setup → check → break → 修正 → check` を実行して確認してください。
このVMコースだけで、ディストリビューション差、任意の起動障害、実機ハードウェア故障、SELinuxの運用まで網羅したことにはなりません。

ゲストガードは、root所有の識別マーカー、指定ホスト名、VMの仮想化方式、スクリプトの所有者を確認します。
rootが意図的に識別情報を書き換える操作まで防ぐセキュリティ境界ではありません。
ホストでマーカーを作って実行を強行する使い方は対象外です。

## 公式の参考資料

- [Multipassとcloud-initによる起動](https://canonical.com/multipass/docs/stable/how-to-guides/manage-instances/launch-customized-instances-with-multipass-and-cloud-init/)
- [snapshot](https://canonical.com/multipass/docs/latest/reference/command-line-interface/snapshot/)
- [restore](https://canonical.com/multipass/docs/latest/reference/command-line-interface/restore/)
