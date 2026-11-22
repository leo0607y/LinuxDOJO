# 再開作業の最終検証（2026-11-22）

## 結果

| 対象 | 実行 | 結果 |
|---|---|---|
| Python全体 | `python3 -m unittest discover -s tests` | 624テスト、失敗0、skip48、181.446秒 |
| 実践課題 | `python3 tests/test_all_missions.py` | 501/501 PASS、135.5秒。初期未達成・誤答拒否・想定解・メタデータを確認。Dockerはmockモードを含む |
| 常用索引 | `python3 -m engine.toolbox audit` | 32分野の参照整合性OK |
| サイト | `npm run build` | 静的書き出し成功 |
| サイトNode | `npm test` | 7件成功 |
| 講座Node | `node --test tests/course.test.mjs` | 4件成功 |
| ブラウザ | `npm run test:e2e` | Chromium 14件成功（レイアウト・操作・アクセシビリティを含む） |
| 差分 | `git diff --check` | 成功 |

Pythonのskipは未導入ツールなどの環境条件によるもので、実行済みの成功には含めない。native40件すべての実ツールがこのホストに導入されているという意味ではない。

最後の501問で発見したランダムfixtureの2件を修正した。31-17はERROR行の置換後の期待件数、30-13はランダムな正解と一致し得た誤答例。正解を緩めず、生成と誤答例を直した。該当2問の実操作を再確認後、全501問が通過した。

## 実VM記録

`docs/vm_verification/` にg2（前セッション）の5本、今回のFTP・ACL再確認・firewall・users・lynis・PostgreSQL・Podmanの実出力と再現手順を保存した。正常通過、不完全/故障/抜け道の拒否、reset後の専用資源を確認した範囲を個別に記す。

Podmanは専用ユーザーのsystemdマネージャー再起動後まで。PostgreSQLの物理backupは整合性と由来までで、物理復元先の起動は未検証。各モジュールのOS再起動など、未実行の範囲は個別記録を参照する。

## 次に残ること

- 利用者のサイト見た目確認。`http://127.0.0.1:3106/` を親担当のdevプロセスで起動し、HTTP200を確認。公開デプロイ・pushは未実行。
- 未完了VMモジュールの実検証。WIPを通過扱いにしない。RHEL系3本はRHEL VMが必要。
- `docs/DAILY_USE_AUDIT.md` の実cron、DHCPリース更新/実キャプチャ、LUKS解除/鍵更新/復旧。今回の追加はsafe-cleanupまで。cron担当は設計確認だけで停止し、ファイル/VM変更なし。
- 一時ログは `/tmp/training-final-python.log`、`/tmp/training-release-missions.log`、`/tmp/training-ui-*.log`、`/tmp/training-accepted-{build,course}.log`。恒久的な実VM出力は上記docs内。
