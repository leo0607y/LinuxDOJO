# AdSense と支援リンクの準備

最終確認: 2026-11-23

## 現在の状態

- `https://danganlog.com/`、`/course/`、`/course/real-linux/` はHTTP 200で公開中。
- 公開中の `ads.txt` とプライバシーポリシーは未設置。AdSenseコードも未設定。AdSenseアカウントの審査状況はこのリポジトリから確認できない。
- `/privacy/` を新設し、運営者、localStorage、Cloudflare Pages、将来のAdSense/BMC外部送信を記載。広告・支援リンクを有効化する前に内容を最終確認し、公開する。
- 運営者が受け取る支援者情報の非公開問い合わせ先（メール等）は未指定。プライバシー上の問い合わせを公開GitHub Issuesへ誘導しないよう、公開前に専用窓口を決める。
- 学習画面では幅1280px以上・高さ800px以上のときだけ右側に支援レールを出す。AdSense枠のプレビューを上に、Buy Me a Coffeeリンクを下に置く。通常ビルドでは広告コードを一切読み込まない。支援リンクは外部ページへの通常リンクで、第三者ウィジェットは埋め込まない。

## 有効化に必要な設定

1. AdSenseへサイトを登録し、サイト所有権を確認して審査を申請する。審査通過前は広告を有効にしない。
2. AdSenseの Privacy & messaging で対象地域の同意メッセージと同意変更・撤回の導線を設定する。EEA・英国・スイスへ広告を配信する場合は、Google認定かつIAB TCF対応CMPを使う。Cookieを使わない広告も地域別の同意要件を確認する。
3. `/privacy/` の広告・外部送信説明を実際の配信設定に合わせて更新する。
4. AdSense実アカウントのclient/slot IDとCMPの同意通知を受け取り、同意処理を確認した後で広告コードを読み込む実装を行う。プレビュー用 `NEXT_PUBLIC_ADSENSE_PREVIEW` は広告通信を行わない。
5. AdSenseでads.txtの案内が出たら、アカウントに表示された正確な行を `web/danganlog/public/ads.txt` に追加する。ads.txtはGoogleが推奨しているが、必須ではない。値を推測して作らない。
6. Buy Me a Coffeeページを作成・公開した後、そのURLを `NEXT_PUBLIC_BMC_URL=https://buymeacoffee.com/<username>` に設定する。支援者名・メール・メッセージ・金額等が運営者にも共有され得ることをプライバシー案内に明記する。
7. AdSenseのAuto adsを無効にするか、学習画面を除外し、広告が右レール以外に自動挿入されないことを確認する。
8. `npm run build` と画面確認を行い、承認・同意設定後にデプロイする。

手動デプロイでは各値を `.env.deploy` に設定する。Cloudflare PagesのGit連携ビルドでは、Pagesのビルド環境変数にも設定する。`.env.deploy.example` は変数名だけを記載し、実際のIDやURLはコミットしない。

## 公式情報

- [AdSenseにサイトを接続して審査を申請する](https://support.google.com/adsense/answer/7584263)
- [プライバシー開示要件](https://support.google.com/publisherpolicies/answer/10437794)
- [EEA・英国・スイスのCMP要件](https://support.google.com/adsense/answer/13554116)
- [Google AdSenseのads.txt](https://support.google.com/adsense/answer/12171612?hl=en-PR)
- [Buy Me a Coffeeのサイトボタン・ウィジェット](https://help.buymeacoffee.com/en/articles/10206530-creative-ways-to-share-your-buy-me-a-coffee-page)
