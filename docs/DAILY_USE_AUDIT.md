# 常用Linuxで事故を避けるための追加監査（2026-11-22）

コマンド名の出現件数ではなく、操作・故障・復旧・後始末の実績で判定する。

## 今回補ったもの
- native `safe-cleanup`: 空白/改行/タブ/先頭ハイフン、NUL一覧、リンク非追跡、事前tar退避/SHA256、隔離移動、別の場所への復元。実ツールテスト成功。ファイル整理・バックアップの索引へ配線済み。
- users: 実VMで過剰sudo、管理グループ混入、期限切れ、sudoers権限の誤りを拒否。resetで専用アカウント/グループ/ホーム/設定を撤去。
- permissions: 実VMで既存/新規ファイルの読取り・書込み拒否・ACL継承を再確認。
- firewall: 実VMで公開範囲・確立済み接続・冪等性・誤設定・撤去を確認。

## 実装を照合して確認した重要な抜け
| 優先 | 抜け | 既存と限界 | 追加する課題・判定 |
|---|---|---|---|
| 1 | cron/atの実デーモンと最小環境 | toolbox_labs.pyのcronは定義を解析しジョブを直接実行。VM softwareはsystemd timer | 専用VMの専用ユーザーcrontabで実時間起動、PATH/環境/重複防止/ログを確認。atdは別の単発ジョブ。削除後に再実行されない |
| 2 | DHCPのリース適用・更新と実キャプチャ | altbootはDHCP OFFERのみ、netconfigは固定IP、native tcpdumpは生成pcap読解 | 隔離netns間で実DHCP ACK/リース適用/renew。誤DNSオプションを検出。実DNS/HTTP通信のpcapで送受信を確認し、専用資源を撤去 |
| 3 | LUKS暗号化ボリュームの解除・復旧 | Stage20は読解、mountsは非暗号化LVM/swap/fstab | 専用loop画像でLUKS2作成/解除/実マウント、誤鍵拒否、鍵追加/古い鍵廃止、header退避とデータ復旧、close後のmapper/loop残骸なし |

未対応を表示上だけ減らすためにPARTIALや検証済みへ変更しない。上記3件はまだ実装・実VM確認待ち。一般の環境差（NetworkManager/systemd-networkd、Wayland/GPU/無線、RHEL/Ubuntu）も別の実機確認が必要。
