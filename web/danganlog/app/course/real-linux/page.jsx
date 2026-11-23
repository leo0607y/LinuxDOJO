import Link from 'next/link';
import styles from '../course.module.css';

export const metadata = {
  title: '実Linux環境を用意する | Linux常用コース',
  description: 'WindowsではWSL 2とUbuntuを導入し、ブラウザーの模擬端末から実際のLinuxシェルへ進む方法を案内します。'
};

export default function RealLinuxGuide() {
  return (
    <article className={styles.article}>
      <p className={styles.crumbs}><Link href="/course/">Linux常用コース</Link> / 実Linux環境</p>
      <h1>ブラウザーの練習から、実Linuxへ</h1>
      <p className={styles.lead}>
        ブラウザー版は安全にコマンドを試す模擬端末です。実際のLinuxを使うために、普段のPCへLinuxを入れ直す必要はありません。
        WindowsならWSL 2にUbuntuを入れて、Linuxのシェルを起動できます。
      </p>

      <section>
        <h2>Windows: WSL 2 と Ubuntu</h2>
        <ol className={styles.list}>
          <li>
            <strong>対応バージョンを確認します。</strong>
            <p>簡単なインストール方法は Windows 10 version 2004 (build 19041) 以降、または Windows 11 が対象です。Windowsの検索欄に「winver」と入力するとバージョンを確認できます。</p>
          </li>
          <li>
            <strong>管理者として PowerShell を開きます。</strong>
            <p>スタートメニューで PowerShell を検索し、「管理者として実行」を選んで次を入力します。</p>
            <pre className={styles.pre}><code>wsl --install</code></pre>
            <p>標準の手順でWSL 2とUbuntuを導入します。Windowsの再起動を求められたら再起動してください。</p>
          </li>
          <li>
            <strong>Ubuntuを初回起動します。</strong>
            <p>スタートメニューから Ubuntu を開き、Linux用のユーザー名とパスワードを作ります。入力中、パスワードの文字は表示されません。Windowsのログインパスワードとは別のものです。</p>
          </li>
          <li>
            <strong>WSL 2になっていることを確認します。</strong>
            <p>PowerShellで次を実行し、Ubuntuの「VERSION」が 2 であることを確認します。</p>
            <pre className={styles.pre}><code>{'wsl --status\nwsl --list --verbose'}</code></pre>
          </li>
          <li>
            <strong>UbuntuのシェルでLinuxを確認します。</strong>
            <p>Ubuntuの画面で次を入力します。PowerShellではなく、UbuntuのLinuxシェルに入力してください。</p>
            <pre className={styles.pre}><code>{'whoami\npwd\ncat /etc/os-release'}</code></pre>
            <p>最後の出力にUbuntuが表示されれば、Linux環境でコマンドを実行できています。</p>
          </li>
        </ol>

        <h3>練習用の場所を作る</h3>
        <p>Linuxコマンド用の作業ファイルは、Linuxユーザーのホームディレクトリ内に置きます。</p>
        <pre className={styles.pre}><code>{'mkdir -p ~/linux-practice\ncd ~/linux-practice\npwd'}</code></pre>
        <p>Linuxのツールで作業するファイルをLinux側に置く方法は、MicrosoftのWSL開発ガイドでも推奨されています。Windowsのファイルを開く必要があるときは、WSL内で <code>explorer.exe .</code> を実行すると、現在のフォルダーをエクスプローラーで開けます。</p>
      </section>

      <section>
        <h2>WSLがすでに入っている場合</h2>
        <p>インストール時にヘルプだけ表示された場合は、利用できるディストリビューションを確認してからUbuntuを指定します。</p>
        <pre className={styles.pre}><code>{'wsl --list --online\nwsl --install -d Ubuntu'}</code></pre>
        <p>ダウンロードが進まない場合や更新を求められた場合は、下のMicrosoft公式手順を確認してください。既存のディストリビューションを削除・登録解除する必要はありません。</p>
      </section>

      <section>
        <h2>どの環境で何を練習するか</h2>
        <ul className={styles.list}>
          <li><strong>ブラウザー:</strong> 模擬端末です。コマンドとファイル操作を安全に練習できますが、PC上のbashやOS設定は動かしません。</li>
          <li><strong>WSL 2:</strong> 実際のLinuxカーネルを使う環境です。シェル、ファイル、開発ツールの練習に進めます。物理ディスクのパーティション変更やPC本体の起動設定を試す場所ではありません。</li>
          <li><strong>専用VM:</strong> systemd、ネットワーク、ストレージ、起動・復旧などのOS管理実習用です。既存PCや仕事用サーバーではなく、専用VMの手順を使います。</li>
        </ul>
      </section>

      <section>
        <h2>次の学習経路</h2>
        <p>目標を選び、その順でトピックを進めます。問題を順番に消化するより、できるようになりたい作業に合わせて道を選んでください。</p>
        <h3>Linuxが初めて</h3>
        <p><Link href="/">学習画面</Link>の「はじめてのLinux」から「基本コマンド」へ進み、その後 <Link href="/course/shell/">シェル</Link> → <Link href="/course/files/">ファイル操作</Link> → <Link href="/course/search/">検索</Link> → <Link href="/course/editor/">編集</Link> を練習します。</p>
        <h3>日常の端末作業を身につけたい</h3>
        <p><Link href="/course/shell/">シェル</Link> → <Link href="/course/files/">ファイル操作</Link> → <Link href="/course/search/">検索</Link> → <Link href="/course/text/">テキスト処理</Link> → <Link href="/course/editor/">編集</Link> → <Link href="/course/archive/">圧縮と検証</Link> → <Link href="/course/backup/">同期と復元</Link> → <Link href="/course/git/">Git</Link> → <Link href="/course/ssh/">SSH</Link> → <Link href="/course/tmux/">tmux</Link> の順がおすすめです。</p>
        <h3>開発に使いたい</h3>
        <p><Link href="/course/shell/">シェル</Link> → <Link href="/course/git/">Git</Link> → <Link href="/course/python/">Python</Link> → <Link href="/course/build/">ビルドとテスト</Link> → <Link href="/course/database/">データベース</Link> → <Link href="/course/tls/">TLS</Link> を進みます。</p>
        <h3>Linuxサーバーを運用したい</h3>
        <p><Link href="/course/packages/">パッケージ</Link> → <Link href="/course/users/">ユーザー</Link> → <Link href="/course/permissions/">権限</Link> → <Link href="/course/services/">サービス</Link> → <Link href="/course/logging/">ログ</Link> → <Link href="/course/network/">ネットワーク</Link> → <Link href="/course/storage/">ストレージ</Link> → <Link href="/course/recovery/">障害復旧</Link> を進み、VM実習があるトピックは専用VMで確認します。</p>
        <p>課題の合格表示は、その課題のチェックを通ったことを示します。別環境での操作や理解まで自動で保証するものではありません。</p>
      </section>

      <section>
        <h2>Microsoft公式情報</h2>
        <ul className={styles.list}>
          <li><a href="https://learn.microsoft.com/en-us/windows/wsl/install" target="_blank" rel="noreferrer">WSLのインストール</a></li>
          <li><a href="https://learn.microsoft.com/en-us/windows/wsl/setup/environment" target="_blank" rel="noreferrer">WSL開発環境とファイル保存</a></li>
          <li><a href="https://learn.microsoft.com/en-us/windows/wsl/basic-commands" target="_blank" rel="noreferrer">WSLの基本コマンド</a></li>
        </ul>
      </section>
    </article>
  );
}
