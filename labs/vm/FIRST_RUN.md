# 実VMでの初回実行チェックリスト

## 2026-11-22 再開後の実VM確認

追加モジュールは一律未検証ではなく、実出力の記録で区別します。

| 対象 | 確認したこと | 記録 |
|---|---|---|
| sshd / mounts / journald / sysctl / limits | 正解・故障/抜け道拒否・reset（再起動は未確認） | docs/vm_verification/g2-system.md |
| ftp | 認証・chroot・PASV・往復転送・不正状態拒否・reset・再setup/reset | docs/vm_verification/g8-ftp.md |
| users | 最小sudo・ユーザー/グループ修復・過剰権限拒否・reset | docs/vm_verification/g1-users.md |
| lynis | 実監査59→60・対象警告解消・実効値・不正状態拒否・reset | docs/vm_verification/g8-lynis.md |
| postgres | TCP SCRAM・最小権限・論理復元・物理backup検証・2周reset | docs/vm_verification/g6-postgres.md |
| podman | rootless Quadlet・UID/GID・user manager再起動・2周reset | docs/vm_verification/g7-podman.md |
| permissions（再確認） | 既存/新規ファイルのACL・不正状態拒否・reset・再setup/reset | docs/vm_verification/permissions-recheck.md |
| firewall | 実nft/netns通信・確立済み接続・再読込/重複拒否・reset | docs/vm_verification/g1-firewall.md |

前セッションの他担当は中断済みです。これ以外の追加モジュールは、途中変更やVMが残っていても検証済みとはしません。RHEL系の3本も未検証です。最新の根拠は `docs/vm_verification/` を参照してください。

再現はリポジトリの `tools/vmtest/verify_scenario.py` と `tools/vmtest/scenarios/*.sh` を使います。ホストでシナリオのシェルを直接実行せず、専用VMに対して実行します。


追加VMモジュールは順次検証中です。実VMで確認した範囲は下表と `docs/vm_verification/` の実出力を参照し、それ以外は初回実行待ちとして扱います。構文検査や単体テストの成功だけでは実VM検証済みにしません。

使い方は次のとおりです。

1. 専用の使い捨てVMを作り、スナップショットを取ります（`README.md` を参照）。
2. 下の表で必要なパッケージを入れます。「初期イメージに入る」と書いたものは追加不要です。
3. `sudo dojo-vm-lab MODULE setup` → `check`（失敗を確認）→ `break` ができる場合は実行 → 修正 → `check`（成功）→ `reset` の順に流します。
4. 確認項目のうち、想定と違った点を記録します。判定側の誤りであれば、モジュールを直します。
5. 通ったら、`docs/coverage.md` の該当行を「実VM検証済み」に書き換えます。通るまでは、検証済みと書きません。

初回実行待ちの項目は「判定の実装は完了、実VM未検証」であり、実習の内容が正しいという保証ではありません。

## 追加パッケージ（setup が不足を検出して案内するもの）

| モジュール | 必要なパッケージ |
|---|---|
| guard | fail2ban auditd |
| dnsserver | bind9 bind9-utils dnsutils |
| mailserver | postfix（debconf は Local only） |
| fileshare | app: nfs-kernel-server、client: nfs-common |
| apache | apache2 apache2-utils |
| pam | pamtester libpam-pwquality libpam-modules-bin |
| podman | podman uidmap busybox-static slirp4netns dbus-user-session |
| ldap | slapd ldap-utils |
| samba | samba smbclient |
| libvirt | libvirt-clients |
| tuned | tuned |
| kbuild | linux-headers-$(uname -r) gcc make kmod |
| grubrescue | grub-pc-bin grub-common grub2-common file |
| gnupg | osupdate が使います。`engine/vm_labs.py` の PACKAGES に追加済み |

RHEL 系の `selinux`、`dnf`、`firewalld` は、Rocky / AlmaLinux / RHEL の VM が必要です。手順は `RHEL.md` を参照してください。Ubuntu の VM では、これらは一覧に出ますが、常に拒否されます。

## モジュール別の初回確認項目

### users
- `runuser -u dojo-alice -- sudo -n -l CMD` の終了コードが、許可で 0、拒否で 0 以外になるか。
- nologin シェルのユーザーに `runuser -u` が使えるか。
- `userdel -r` がメールスプールの無い状態でも 0 を返すか。

### netconfig
- `networkctl reconfigure dojo0` が、netdev 作成直後に効くか。
- `resolvectl dns` と `resolvectl domain` の出力形式（`Link N (dojo0): ...`）。
- IPv6 の DAD の待ち時間（最大約10秒）で足りるか。
- `linux-modules-extra` が無いイメージで dummy が読めるか。読めなければ setup が失敗します。

### firewall
- `ip netns list` の出力判定（"(id: N)" 付きでも一致するか）。
- `systemd-run --unit=dojo-fw-rollback` の90秒後のロールバックが発火するか。
- ufw が有効なとき、判定が狂わないか。

### restore
- UID 981 と 967 が、cloud image で空いているか。
- `systemctl show -p EnvironmentFiles` の出力形式。
- break 後の root サービスを、復元で正しく置き換えられるか。

### osupdate
- `apt-get update -o Dir::Etc::sourceparts=...` が効くか。
- `_apt` が file: リポジトリを読めるか。
- `gpg --dearmor` で作った keyring に、apt が警告を出さないか。

### sshd
- `SSH_ASKPASS_REQUIRE=force` と `-n` が、OpenSSH 9.6 で動くか。
- `-F` の設定で ProxyJump のエイリアスが解決されるか。
- 緩い設定のとき、root の鍵ログインが実際に成功するか。

### mounts
- `findmnt --tab-file ... --target` の出力と、`findmnt --verify` の `[E]` 表記。
- `mount -a` が、アタッチ中のループデバイスに UUID を解決するか。
- LVM が loop の PV を検出するか。
- 再起動でループデバイスが消えるため、check の再アタッチ案内が機能するか。

### journald
- `journalctl --sync` と `--directory` の動き。
- `systemctl show -P ExecMainStartTimestamp` が、`date -d` で解析できるか。
- Ubuntu 既定の `/var/log/journal` の所有者と権限が、判定を通るか。

### sysctl
- cloud image のカーネルに `softdog` があるか。無ければ、`linux-modules-extra` が必要です。
- `sysctl --system` の "Applying ..." 行の形式。
- 不明キーのエラー文に `swapiness` が含まれるか。

### limits
- `MemoryMax=16M` で実際に OOM kill（`Result=oom-kill`）になるか。
- `journalctl -k` に OOM の記録が出るか。
- `systemctl show` の ExecStart の形式と、`/proc/PID/limits` の解析。

### timesync
- `locales` パッケージが入っているか。
- `timedatectl show-timesync -p SystemNTPServers --value` が、サーバー名を1つ返すか。
- reset で、生成した locale を完全に削除できるか。

### guard
- `fail2ban-regex` の出力形式（"Lines: 1 lines, 0 ignored, 1 matched, 0 missed"）。
- polling の ban が、25秒の待機内に反映されるか。
- `ausearch -ts HH:MM:SS` の範囲と、`auditctl -l` の出力形式。

### dnsserver
- Ubuntu の AppArmor が、`/etc/bind/dojo` と `/var/lib/bind/dojo` の専用 named を許可するか。
- `rndc-confgen -a -k dojo-rndc` が、`dojo-rndc` という名前の鍵を作るか。
- `named-checkzone` の "loaded serial N" の形式。

### mailserver
- `postfix -c /etc/postfix-dojo check` と `start` が、最小の master.cf で動くか。
- エイリアスのループと、root 所有の `Maildir/new` が、想定どおりに deferred になるか。

### fileshare
- NFSv4 の UID マッピング（同名・同 UID のとき）。
- squash された root の書き込みが、拒否されるか UID 65534 か 4294967294 になるか。
- `findmnt` に `soft` と `timeo=` が出るか。
- 2台のVMでの、peer の IP ファイルの受け渡し。

### apache
- `dojo-apache.service` の ExecReload と graceful の動き。
- apache2 のモジュールのパス（`/usr/lib/apache2/modules`）。

### netlink
- veth の bond が、miimon でリンクダウンを検出するか。
- `bridge link` の出力の正規表現。
- `ip route get ... from` がポリシールールを尊重するか。

### pam
- pamtester の pty のプロンプト（`Password:`、chauthtok のプロンプト）。
- `-I tty=... -I rhost=...` が受け付けられるか。受け付けられないと、pam_access が不安定になります。
- root での chauthtok と pam_pwquality（`enforce_for_root`）。

### podman
- enable-linger 直後に、runuser から user の systemd バスへ届くか。
- Podman 4.9 の Quadlet 生成と、`podman import --change 'CMD [...]'`。
- rootless のネットワークでの 18080 の公開。

### ldap
- AppArmor が `/var/lib/ldap/**` と `/run/slapd/**` の専用パスを許可するか。
- `slapadd -n 0` のスキーマ取り込みと、`back_mdb` のモジュールパス。
- ldapi の EXTERNAL 認証が、root で動くか。

### samba
- `map to guest = never` のとき、`guest ok` の共有への匿名アクセスが動くか。
- `testparm --section-name --parameter-name` の出力値。
- smbclient が返す NT_STATUS_* の種類。

### libvirt
- virsh の標準入力バッチが、最初のエラーで止まるか。
- テスト用ドライバーの定義が、1接続内で再生できるか。

### tuned
- tuned のサービスが起動していて、`tuned-adm active` が "Current active profile:" を出すか。
- break の後、`tuned-adm verify` が失敗するか。

### kbuild
- Secure Boot またはカーネルのロックダウンが、`insmod` を止めないか。止めた場合、この実習は回避せず説明を出して終了します。
- runuser で nobody がヘッダーを使ってビルドできるか。

### grubrescue
- 読み取り専用の /usr と、`/dev` `/proc` `/sys` の bind を持つ chroot で、`grub-probe /` と `grub-mkconfig` が動くか。
- `grub-install` が、ループデバイスを受け付けるか。
- MBR の "Geom" 文字列が、boot.img の判定として確実か。
- 実機の `/boot/grub/grub.cfg` のハッシュが、実習の前後で変わらないか。

### selinux / dnf / firewalld（RHEL 系）
- `selinux`: `/srv/dojo-se/site` に `var_t` が付いて AVC 拒否が起きるか、`semanage boolean -l -C` の出力形式。
- `dnf`: `%install` で `printf` を使った spec の生成、`rpmsign` と `repo_gpgcheck=1`、`createrepo_c` と `rpm-sign` が AppStream か CRB にあるか。
- `firewalld`: firewalld が作っていないインターフェースの zone が `--reload` で保たれるか、rich rule の reject が ECONNREFUSED になるか。

## 共通の注意

- ディスパッチャは `set -e` で動きます。各モジュールは、終了コードの取得を書き換えて対応していますが、実行での確認は未実施です。
- 開発中のメモリ使用量、ループバックのサイズ、ポート番号は、実習ごとに固定しています。他の実習と同時に動かさないでください。
- 失敗したときは、モジュールを `reset` してからスナップショットへ戻すのが、最も確実です。
