# AdSense と支援リンクの準備

最終確認: 2026-11-27

## 現在の状態

- 実装は完了済みで、設定値を入れてビルドすれば動く。値が未設定、または形式が不正なら、その機能は出ない(広告通信なし)。`lib/support.js` が検証する。
- 動作確認済み(ダミーIDでビルド): 1280x800以上でだけ右レールに Coffee リンクと広告枠が出る。それ未満では `pagead2.googlesyndication.com` への通信がない。`ads.txt` と `google-adsense-account` メタは、パブリッシャーID設定時だけ生成される。設定なしのビルドでは広告関連の通信・ファイルは一切ない。
- 広告スクリプトは学習画面の右レール内でだけ読み込む。サイトの他のページでは読み込まない。
- 同意メッセージは AdSense の Privacy & messaging(Google の CMP)が広告スクリプトと一緒に表示する。CMP が読み込まれると、広告の下に「広告の同意設定」ボタンが出て、同意の変更・撤回ができる。
- `/privacy/` の広告・Coffee・問い合わせ先の説明は、設定値に合わせてビルド時に切り替わる。
- 実際の AdSense アカウントでの配信、Google CMP の実表示は、アカウントがないためこのリポジトリからは未検証(通信は偽の応答で代替して確認)。

## 有効化の手順(あなたが用意するもの)

| 環境変数 | 内容 | 入手先 |
|---|---|---|
| `NEXT_PUBLIC_BMC_URL` | `https://www.buymeacoffee.com/<username>` | Buy Me a Coffee のページ作成後 |
| `NEXT_PUBLIC_ADSENSE_CLIENT` | `ca-pub-` で始まるパブリッシャーID | AdSense アカウント |
| `NEXT_PUBLIC_ADSENSE_SLOT` | 広告ユニット(ディスプレイ広告)のスロットID(数字) | AdSense > 広告 > 広告ユニット |
| `NEXT_PUBLIC_CONTACT_EMAIL` | 支援者情報などの非公開問い合わせ先(任意だが推奨) | 運営者 |

1. Buy Me a Coffee のページを作り、URL を `NEXT_PUBLIC_BMC_URL` に設定する。Coffee はこれだけで有効になる。
2. AdSense にサイト `danganlog.com` を登録し、所有権を確認して審査を申請する。`NEXT_PUBLIC_ADSENSE_CLIENT` だけ先に設定してデプロイすると、確認用のメタタグと `ads.txt` が出る(広告はまだ出ない)。
3. 審査通過後、Privacy & messaging で対象地域の同意メッセージを作成して公開する。EEA・英国・スイスへ配信する場合は Google 認定・IAB TCF 対応であること。
4. ディスプレイ広告ユニットを作り、スロットIDを `NEXT_PUBLIC_ADSENSE_SLOT` に設定する。
5. AdSense の自動広告(Auto ads)を無効にするか、サイトのこのページを除外する。コードからは制御できないので、管理画面で確認する。
6. `web/danganlog/.env.deploy` に値を書き(Git管理外)、`scripts/deploy.sh` でデプロイする。Pages の Git 連携ビルドなら Pages のビルド環境変数にも設定する。
7. デプロイ後、本番を実ブラウザー(1280x800以上)で開き、広告枠・同意メッセージ・Coffee リンクの表示と、操作欄との重なりがないことを確認する。

実際のIDやURLはコミットしない。

## 公式情報

- [AdSenseにサイトを接続して審査を申請する](https://support.google.com/adsense/answer/7584263)
- [プライバシー開示要件](https://support.google.com/publisherpolicies/answer/10437794)
- [EEA・英国・スイスのCMP要件](https://support.google.com/adsense/answer/13554116)
- [Google AdSenseのads.txt](https://support.google.com/adsense/answer/12171612?hl=en-PR)
- [Buy Me a Coffeeのサイトボタン・ウィジェット](https://help.buymeacoffee.com/en/articles/10206530-creative-ways-to-share-your-buy-me-a-coffee-page)
