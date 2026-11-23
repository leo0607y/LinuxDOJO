import Link from 'next/link';
import styles from '../course.module.css';

export const metadata = {
  title: 'Linux環境を用意する | Linux常用コース',
  description: 'WindowsはWSL 2、MacはUTM仮想マシンを使って、模擬ターミナルから実際のLinux環境へ進む方法を案内します。'
};

export default function RealLinuxGuide() {
  return (
    <article className={styles.article}>
      <p className={styles.crumbs}><Link href="/course/">Linux常用コース</Link> / Linux環境の準備</p>
      <h1>練習用のLinux環境を準備する</h1>
      <p className={styles.lead}>
        ブラウザー版は安全にコマンドを試す模擬ターミナルです。実際のLinuxを使うために、普段のPCへLinuxを入れ直す必要はありません。
        WindowsはWSL 2、Macは仮想マシンを使ってLinuxを起動できます。
      </p>

      <section>
        <h2>まず、ターミナルを開く</h2>
        <p>このページを見ているブラウザー版には、コマンドを入力する欄があります。サイト内の練習には別のターミナルを開く必要はありません。自分のPCでコマンドを試すときは、次のアプリを開きます。</p>
        <ul className={styles.list}>
          <li><strong>Windows:</strong> スタートメニューを開き、「PowerShell」と検索します。WSLを導入するときは、検索結果を右クリックして「管理者として実行」を選びます。導入後にLinuxコマンドを入力する画面はPowerShellではなく、スタートメニューから開く「Ubuntu」です。</li>
          <li><strong>Mac:</strong> Spotlightを開き (Command + Space)、「ターミナル」と入力してReturnキーを押します。これはmacOSを操作する画面です。Linuxの操作とは異なる部分があります。</li>
          <li><strong>Linuxデスクトップ:</strong> アプリ一覧で「Terminal」または「端末」を検索します。多くの環境では Ctrl + Alt + T でも開けます。</li>
        </ul>
      </section>

      <section>
        <h2>Windows: WSL 2 と Ubuntu</h2>
        <ol className={styles.list}>
          <li>
            <strong>対応バージョンを確認します。</strong>
            <p>簡単なインストール方法は Windows 10 バージョン 2004 (ビルド 19041) 以降、または Windows 11 が対象です。Windowsの検索欄に「winver」と入力するとバージョンを確認できます。</p>
          </li>
          <li>
            <strong>管理者として PowerShell を開きます。</strong>
            <p>先ほど開いた管理者PowerShellで次を入力します。</p>
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
        <h2>Mac: UTMでUbuntuを仮想マシンに入れる</h2>
        <p>macOSのターミナルでも、多くの共通コマンドを練習できます。</p>
        <pre className={styles.pre}><code>{'uname -s\npwd'}</code></pre>
        <p><code>uname -s</code> の結果が <code>Darwin</code> ならmacOS上で動いています。macOSはLinuxではないため、Linux固有のサービスや管理操作を練習するときは、Mac上に専用のLinux仮想マシンを作ります。</p>
        <ol className={styles.list}>
          <li>
            <strong>Macの種類を確認します。</strong>
            <p>Appleメニューから「このMacについて」を開き、チップがApple siliconかIntelかを確認します。</p>
          </li>
          <li>
            <strong>UTMをインストールします。</strong>
            <p><a href="https://docs.getutm.app/installation/macos/" target="_blank" rel="noreferrer">UTM公式のmacOSインストール手順</a>を使います。App Store版と公式サイトから取得する方法があります。</p>
          </li>
          <li>
            <strong>Macのチップに合うUbuntu Serverを取得します。</strong>
            <p>Apple siliconはARM64、IntelはAMD64 (x86_64) のイメージを選びます。Ubuntu公式の<a href="https://ubuntu.com/download/server" target="_blank" rel="noreferrer">Ubuntu Serverダウンロード</a>から取得してください。コマンド練習には画面なしのServer版で十分です。</p>
          </li>
          <li>
            <strong>UTMでLinux仮想マシンを作ります。</strong>
            <p>新規仮想マシンで「Virtualize」→「Linux」を選び、取得したISOを指定します。MacのチップとISOの種類を一致させ、Ubuntuのインストーラーでユーザー名とパスワードを設定します。共有フォルダーを選ぶ画面では何も指定しません。UTM公式の<a href="https://docs.getutm.app/guides/ubuntu/" target="_blank" rel="noreferrer">Ubuntu仮想マシンガイド</a>に画面ごとの手順があります。</p>
          </li>
          <li>
            <strong>Ubuntuのシェルで起動を確認します。</strong>
            <pre className={styles.pre}><code>{'whoami\npwd\ncat /etc/os-release'}</code></pre>
            <p>Ubuntuが表示されれば、Linux環境でコマンドを実行できています。</p>
          </li>
        </ol>
        <p>仮想マシンはMac本体とは別に動きます。Linuxの管理操作を試すときも、課題で指定された仮想マシンだけを対象にしてください。</p>
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
          <li><strong>ブラウザー:</strong> 模擬ターミナルです。コマンドとファイル操作を安全に練習できますが、PC上のbashやOS設定は動かしません。</li>
          <li><strong>WSL 2・Linux仮想マシン:</strong> 実際のLinux環境です。WSL 2からはWindowsのドライブにもアクセスできます。ファイル操作は <code>~/linux-practice</code> の中で行い、Windows側のファイルや共有フォルダーを対象にしないでください。</li>
          <li><strong>専用VM:</strong> systemd、ネットワーク、ストレージ、起動・復旧などのOS管理実習用です。課題で指定された専用VMを使い、普段使いのPCや仕事用サーバーでは管理操作を試しません。</li>
        </ul>
      </section>

      <section>
        <h2>目標に合わせた学習順</h2>
        <p>目標を選び、その順でトピックを進めます。問題を順番に消化するより、できるようになりたい作業に合わせて道を選んでください。</p>
        <h3>Linuxが初めて</h3>
        <p><Link href="/">学習画面</Link>で「はじめてのLinux」から「基本コマンド」へ進みます。その後は、<Link href="/course/shell/">シェル</Link>、<Link href="/course/files/">ファイル操作</Link>、<Link href="/course/search/">検索</Link>、<Link href="/course/editor/">編集</Link>の順です。</p>
        <h3>日常の端末作業</h3>
        <p><Link href="/course/shell/">シェル</Link>、<Link href="/course/files/">ファイル操作</Link>、<Link href="/course/search/">検索</Link>、<Link href="/course/text/">テキスト処理</Link>、<Link href="/course/editor/">編集</Link>、<Link href="/course/archive/">圧縮と検証</Link>、<Link href="/course/backup/">同期と復元</Link>、<Link href="/course/git/">Git</Link>、<Link href="/course/ssh/">SSH</Link>、<Link href="/course/tmux/">tmux</Link>へ進みます。</p>
        <h3>開発</h3>
        <p><Link href="/course/shell/">シェル</Link>、<Link href="/course/git/">Git</Link>、<Link href="/course/python/">Python</Link>、<Link href="/course/build/">ビルドとテスト</Link>、<Link href="/course/database/">データベース</Link>、<Link href="/course/tls/">TLS</Link>の順に学びます。</p>
        <h3>Linuxサーバーの運用</h3>
        <p><Link href="/course/packages/">パッケージ</Link>、<Link href="/course/users/">ユーザー</Link>、<Link href="/course/permissions/">権限</Link>、<Link href="/course/services/">サービス</Link>、<Link href="/course/logging/">ログ</Link>、<Link href="/course/network/">ネットワーク</Link>、<Link href="/course/storage/">ストレージ</Link>、<Link href="/course/recovery/">障害復旧</Link>へ進みます。VM実習があるトピックは専用VMで確認します。</p>
        <p>課題の合格表示は、その課題のチェックを通ったことを示します。別環境での操作や理解まで自動で保証するものではありません。</p>
      </section>

      <section>
        <h2>公式の導入手順</h2>
        <ul className={styles.list}>
          <li><a href="https://learn.microsoft.com/en-us/windows/wsl/install" target="_blank" rel="noreferrer">WSLのインストール</a></li>
          <li><a href="https://learn.microsoft.com/en-us/windows/wsl/setup/environment" target="_blank" rel="noreferrer">WSL開発環境とファイル保存</a></li>
          <li><a href="https://learn.microsoft.com/en-us/windows/wsl/basic-commands" target="_blank" rel="noreferrer">WSLの基本コマンド</a></li>
          <li><a href="https://support.apple.com/guide/terminal/open-or-quit-terminal-apd5265185d-f365-44cb-8b09-71a064a42125/mac" target="_blank" rel="noreferrer">Apple: Macでターミナルを開く</a></li>
          <li><a href="https://docs.getutm.app/installation/macos/" target="_blank" rel="noreferrer">UTMのmacOSインストール</a></li>
          <li><a href="https://docs.getutm.app/guides/ubuntu/" target="_blank" rel="noreferrer">UTMでUbuntu仮想マシンを作成</a></li>
          <li><a href="https://ubuntu.com/download/server" target="_blank" rel="noreferrer">Ubuntu Serverのダウンロード</a></li>
        </ul>
      </section>
    </article>
  );
}
