# firewall 実VM再検証（2026-11-22）

環境: 残存Ubuntu 24.04 KVM `g1-app`。現行ソースを同期して再検証。
前担当の変更（www-dataのstateへの通行権、確立済み接続の逆方向プローブ、再読込の冪等性検査）を確認した。追加でloopback HTTP判定を応答全体の受信へ修正。1回のrecvではヘッダーのみ到着して正解を誤拒否した。

再現: `python3 tools/vmtest/verify_scenario.py g1-app tools/vmtest/scenarios/firewall.sh /tmp/training-firewall-vm.log`

正常修復・未完了/故障/抜け道拒否・後始末を確認。無関係なnftテーブルが残ることも確認。90秒タイマーの実時間経過によるロールバックとOS再起動は今回未検証。g1全体の完了ではない。

```text
VM=g1-app scenario=tools/vmtest/scenarios/firewall.sh
bash: warning: setlocale: LC_ALL: cannot change locale (ja_JP.UTF-8)
専用テーブル・namespace・veth・unit・ルールファイルを削除しました。
Created symlink /etc/systemd/system/multi-user.target.wants/dojo-fw-web-18080.service → /etc/systemd/system/dojo-fw-web-18080.service.
Created symlink /etc/systemd/system/multi-user.target.wants/dojo-fw-web-18081.service → /etc/systemd/system/dojo-fw-web-18081.service.
サーバ(app VM)は SSH(22)、HTTP 18080、18081 で待ち受けています。
namespace dojo-fw-peer (10.77.0.2) からのアクセスは、本物のファイアウォール(inputフック)を通ります。
1. sudo dojo-vm-lab firewall break で壊れた状態にし、namespaceから接続できないことを確認する
   (ヒント: sudo ip netns exec dojo-fw-peer curl -m2 http://10.77.0.1:18080/health)
2. /etc/dojo-firewall/rules.nft に、専用テーブル inet dojo_fw のルールを書く。要件:
   - policy drop の input チェーン。lo は許可、確立済み/関連接続は許可
   - tcp 22 と 18080 は許可、18081 は拒否、ICMP は許可
   - 再読込で重複しないよう、冒頭でテーブルを宣言して消す書き方(table / delete table)を調べる
3. 適用は必ず sudo /var/lib/linuxdojo-vm-lab/state/firewall/safe-apply /etc/dojo-firewall/rules.nft を使う(構文検査後に適用し、90秒で自動ロールバック予約)
4. 接続が保てたことを確認して sudo touch /var/lib/linuxdojo-vm-lab/state/firewall/confirm で確定する
5. sudo dojo-vm-lab firewall check
既存の ufw や他の nftables テーブルは変更しないこと。
ASSERT setup expected=0 actual=0
break済みの記録がありません。先に break を実行してください。
ASSERT before-break expected=1 actual=1
dojo-fwh からの入力だけを破棄する壊れたルールを適用しました(本線のSSHは影響なし)。/etc/dojo-firewall/rules.nft を直してください。
ASSERT break expected=0 actual=0
confirm がありません。接続確認後に sudo touch で確定してください。
ASSERT unconfirmed expected=1 actual=1
input フックの policy drop が必要です。
ASSERT broken expected=1 actual=1
適用しました。90秒以内に接続を確認し、問題なければ次を実行してください:
  sudo touch /var/lib/linuxdojo-vm-lab/state/firewall/confirm
確認しないと dojo_fw テーブルは自動で削除されます。
confirm がありません。接続確認後に sudo touch で確定してください。
ASSERT confirm-required expected=1 actual=1
基本ファイアウォールが要件通りに動作し、ルールファイルからの再読込でも同じ結果になりました。
ASSERT repaired expected=0 actual=0
確立済み/関連接続(ct state established,related)が許可されていません。
ASSERT no-established expected=1 actual=1
18081 が拒否されていません。
ASSERT exposed-port expected=1 actual=1
/etc/dojo-firewall/rules.nft を再読込するとルールが重複/変化します。冒頭で table と delete table を書いてください。
ASSERT duplicate-on-reload expected=1 actual=1
基本ファイアウォールが要件通りに動作し、ルールファイルからの再読込でも同じ結果になりました。
ASSERT repaired-again expected=0 actual=0
専用テーブル・namespace・veth・unit・ルールファイルを削除しました。
ASSERT reset expected=0 actual=0
Error: No such file or directory
list table inet dojo_fw
                ^^^^^^^
Device "dojo-fwh" does not exist.
ASSERT cleanup: dedicated nft table/netns/veth/units/state removed; unrelated table preserved

SCENARIO_EXIT=0
```
