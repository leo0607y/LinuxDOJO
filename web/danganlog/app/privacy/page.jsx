import Link from 'next/link';
import { loadCourse } from '../../lib/course-data.js';
import { support } from '../../lib/support.js';
import styles from '../course/course.module.css';

export const metadata = {
  title: 'サイト情報・プライバシーポリシー | DANGAN LOG',
  description: 'DANGAN LOGの運営者、学習データの保存、外部サービスと広告に関する案内です。'
};

export default function PrivacyPage() {
  const { topics } = loadCourse();
  return (
    <article className={styles.article}>
      <p className={styles.crumbs}><Link href="/">DANGAN LOG</Link> / サイト情報</p>
      <h1>サイト情報・プライバシーポリシー</h1>
      <p>最終更新日: 2026年11月27日</p>

      <section>
        <h2>運営者・お問い合わせ</h2>
        <p>運営者: LinuxDOJOプロジェクト（DANGAN LOG）</p>
        <p>教材やサイトについての連絡は、<a href="https://github.com/leo0607y/LinuxDOJO/issues" target="_blank" rel="noopener noreferrer">LinuxDOJOのGitHub Issues</a>からお願いします。個人情報や支援決済に関する問い合わせは、公開の課題に書かず、{support.contactEmail ? <>次のメールアドレスへお送りください: <a href={`mailto:${support.contactEmail}`}>{support.contactEmail}</a>。</> : '各サービスの窓口をご利用ください。'}</p>
      </section>

      <section>
        <h2>学習データ</h2>
        <p>学習の進み具合、入力履歴、練習ファイル、表示設定は、ブラウザーのlocalStorageに保存します。これらはこのサイトのサーバーへ送信せず、ブラウザーのデータを削除すると失われます。必要な場合は学習画面の「学習データ」からJSONを書き出してください。</p>
        <p>コマンド実行環境（Pyodide）と教材データはこのサイトから配信します。現在、アクセス解析サービスは使用していません。</p>
      </section>

      <section>
        <h2>外部サービスへの情報送信</h2>
        <div className={styles.tablewrap}>
          <table className={styles.table}>
            <thead><tr><th>送信先</th><th>送信・処理される情報</th><th>目的と現在の状態</th></tr></thead>
            <tbody>
              <tr><td>Cloudflare Pages</td><td>ページ配信に伴うIPアドレス、ブラウザー情報、リクエスト先など</td><td>サイトの配信・保護。現在使用中です。</td></tr>
              <tr><td>GitHub</td><td>リンクを開く際のIPアドレス・ブラウザー情報など。投稿時はアカウント情報・投稿内容など</td><td>連絡・不具合報告。リンクを開くとGitHubへ接続します。</td></tr>
              <tr><td>Google AdSense</td><td>広告配信時のIPアドレス、Cookie等の識別子、ブラウザー・広告表示情報など</td><td>{support.adsLive ? '広告配信と測定。学習画面を広い画面で開いたときだけ、GoogleのスクリプトとCookie等を読み込みます。同意が必要な地域では、同意メッセージで選択するまで個人情報に基づく広告は配信されません。' : '広告配信と測定。現在は広告コードを設定しておらず、送信はありません。広告を開始する前にこの案内を更新します。'}</td></tr>
              <tr><td>Buy Me a Coffee</td><td>リンク先を開いた後、同サービスがページ表示・支援決済に必要とする情報</td><td>{support.coffeeUrl ? '任意の支援受付。学習画面の右側のリンクを開いたときだけ接続します。埋め込みウィジェットは使いません。' : '任意の支援受付。現在リンクは未設定です。埋め込みウィジェットは使わず、外部ページへのリンクを予定しています。'}</td></tr>
            </tbody>
          </table>
        </div>
        <p>Cloudflareによるデータの取扱いは<a href="https://www.cloudflare.com/privacypolicy/" target="_blank" rel="noopener noreferrer">Cloudflareのプライバシーポリシー</a>をご確認ください。</p>
        <p>GitHubを利用する場合は<a href="https://docs.github.com/en/site-policy/privacy-policies/github-privacy-statement" target="_blank" rel="noopener noreferrer">GitHubのプライバシーに関する声明</a>をご確認ください。</p>
      </section>

      <section>
        <h2>広告について</h2>
        <p>{support.adsLive ? 'このサイトでは、学習画面の右側にGoogle AdSenseの広告を表示します。広告は幅1280px以上・高さ600px以上の画面でだけ読み込み、操作欄の近くには表示しません。同意が必要な地域では、広告の下の「広告の同意設定」から変更・撤回できます。' : '現在、このサイトでは広告を配信していません。'}Google AdSenseでは、Googleや広告パートナーがCookie等を用いて広告を配信・測定することがあります。Googleによるデータ利用は<a href="https://policies.google.com/technologies/partner-sites?hl=ja" target="_blank" rel="noopener noreferrer">Googleのパートナーサイトでのデータ利用について</a>、パーソナライズ広告の設定は<a href="https://adssettings.google.com/" target="_blank" rel="noopener noreferrer">Google広告設定</a>をご確認ください。</p>
        <p>欧州経済領域、英国、スイスの利用者へ広告を配信する場合は、Google認定・IAB TCF対応の同意管理プラットフォーム（CMP）と同意内容の変更・撤回手段を設定してから広告を有効にします。Cookieを使わない広告であっても、適用される地域・設定に応じた同意要件を確認します。</p>
      </section>

      <section>
        <h2>Buy Me a Coffeeについて</h2>
        <p>支援リンクを設定した場合、クリックするとBuy Me a Coffeeのページへ移動します。支援は任意です。支援時に入力された表示名、メールアドレス、メッセージ、支援額・日付などは、Buy Me a Coffeeからサイト運営者にも共有されることがあります。運営者は支援内容の確認や支援に関する連絡への対応に利用します。カード番号全体は運営者には共有されません。氏名・連絡先・決済情報などの取扱いの詳細は<a href="https://buymeacoffee.com/privacy-policy" target="_blank" rel="noopener noreferrer">Buy Me a Coffeeのプライバシーポリシー</a>をご確認ください。</p>
      </section>

      <section>
        <h2>掲載内容</h2>
        <p>このサイトはLinuxコマンドを学ぶための教材です。現在、常用コースに{topics.length}トピックを掲載しています。教材の誤りや表示上の問題は上記のGitHub Issuesへお知らせください。</p>
      </section>
    </article>
  );
}
