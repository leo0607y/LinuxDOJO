# RHEL-family VM labs (selinux, dnf, firewalld)

## Status: nothing here has been run on a real RHEL-family VM

The three modules `selinux.sh`, `dnf.sh` and `firewalld.sh` were written on an Ubuntu development machine that has no
qemu, no sudo, no SELinux, no rpm, no dnf and no firewalld. The only checks performed were `bash -n` and the unit tests in
`tests/test_vm_rhel.py` (wrong-context rejection, distro-guard rejection, static content checks). Every command
sequence, output format, package name and the behaviors described below is **unverified** until someone runs the labs on
Rocky Linux / AlmaLinux and fixes what breaks. Treat the first run as a debugging session.

Each module refuses to run unless `/etc/os-release` has `ID` of `rocky`, `almalinux`, `rhel` or `centos`
(it prints `<id>: this lab needs a RHEL-family VM` to stderr and returns 1 before any write). On the Ubuntu VMs that the
exporter builds, these three labs are listed by `dojo-vm-lab list` but will always refuse.

## What this repository's exporter does today (Ubuntu only)

`python3 -m engine.vm_labs export` writes `app-cloud-init.yaml` and `client-cloud-init.yaml` rendered from
`labs/vm/cloud-init.yaml.in`. This is Ubuntu-only, plainly:

- The manifest says image `24.04`.
- `PACKAGES` in `engine/vm_labs.py` are Debian/Ubuntu names (`openssh-server`, `libc6-dev`, `python3-venv`, `dnsutils`,
  `fd-find`, `bat`, `iproute2`, ...). Several do not exist under those names on RHEL, and cloud-init's package install
  on a dnf system can fail as a whole when a name is unknown.
- `runcmd` disables `nginx.service` and `dnsmasq.service`, which do not exist on a bare Rocky image (harmless failure).
- No RHEL packages (below) are listed. `engine/vm_labs.py` was deliberately not changed.

What is still useful from the export: the `write_files` section (marker `/etc/linuxdojo-vm-lab`, dispatcher
`/usr/local/sbin/dojo-vm-lab`, every module in `/usr/local/lib/linuxdojo-vm-lab/modules/`). A RHEL VM needs a hand-made
cloud-init that keeps those `write_files` entries and replaces the packages and runcmd (see below).

## Manual steps to get a Rocky / AlmaLinux VM

1. Download a GenericCloud qcow2 image and verify its checksum from the distribution's published CHECKSUM file.
   - Rocky 9: `https://dl.rockylinux.org/pub/rocky/9/images/x86_64/Rocky-9-GenericCloud-Base.latest.x86_64.qcow2`
     (default login user `rocky`)
   - AlmaLinux 9: `https://repo.almalinux.org/almalinux/9/cloud/x86_64/images/AlmaLinux-9-GenericCloud-latest.x86_64.qcow2`
     (default login user `almalinux`)
   - URLs are from memory and unverified; check the distribution's site. The labs target dnf4 (RHEL/Rocky/Alma 8-10),
     not dnf5.
2. Build a RHEL cloud-init: copy the `write_files:` block of an exported `app-cloud-init.yaml` into a new file and write
   `packages:` and `runcmd:` yourself.
3. Launch it. Two options.
   - qemu directly (known approach, not run here):
     `qemu-img create -f qcow2 -F qcow2 -b Rocky.qcow2 app.qcow2 20G`, build a seed ISO with
     `cloud-localds seed-app.iso user-data` (package `cloud-image-utils` on Ubuntu hosts), then
     `qemu-system-x86_64 -enable-kvm -m 2048 -smp 2 -drive file=app.qcow2,if=virtio -drive file=seed-app.iso,format=raw,if=virtio -nic user,hostfwd=tcp::2222-:22 -nographic`
   - multipass: it normally launches Canonical Ubuntu images. Launching a local image via
     `multipass launch file:///abs/path/Rocky.qcow2 --name linuxdojo-app --cloud-init user-data` is supposed to be
     possible for a cloud-init-capable qcow2, but this was not tried and may not work with your multipass version/driver.
     If it fails, use qemu or libvirt (`virt-install --import`).
4. Log in, `sudo cloud-init status --wait`, `getenforce` (must be `Enforcing`), `sudo dojo-vm-lab list`.
5. Run a lab: `sudo dojo-vm-lab selinux setup` and so on. These labs expect to run as root through sudo.
6. Use a fresh VM or snapshot per lab; only `reset` undoes what the module created.

## Packages the cloud-init must install (dnf names, unverified)

Common to all three: `python3 curl iproute openssh-server sudo`.

| Lab | Extra packages | Services that must be running before `setup` |
|---|---|---|
| selinux | `httpd policycoreutils policycoreutils-python-utils audit selinux-policy-targeted` | `auditd`; httpd must NOT already be active/enabled; mode must be `Enforcing` |
| dnf | `dnf rpm-build rpm-sign createrepo_c gnupg2 python3-dnf-plugin-versionlock` | none. `createrepo_c` and `rpm-sign` may live in AppStream/CRB depending on the release; enable CRB (`dnf config-manager --set-enabled crb`) if not found |
| firewalld | `firewalld` | `firewalld`, `sshd` |

Suggested `runcmd` (illustrative): `systemctl enable --now auditd firewalld sshd`.
The dnf lab uses only its own local repo, but installing the build tools above needs the distribution repos to be reachable
once, at provisioning time.

## What each lab claims to check (all unverified on a real system)

- selinux: setup requires Enforcing and auditd; an httpd on a non-default port (8008, an `http_port_t` port) serves
  `/srv/dojo-se/site` and proxies `/api/` to a python backend on 18091. `break` clears the lab's fcontext rule and sets
  `httpd_can_network_connect` off. `check` reads real `getenforce`, `/etc/selinux/config`, `semanage permissive -l`,
  `semanage fcontext -l -C`, `restorecon -Rn`, `getsebool` plus `semanage boolean -l -C`, requires `httpd_t`, performs real
  `curl` requests, then fails if `ausearch -m avc` shows a new `httpd_t` denial during the check.
  Risks: whether `/srv/dojo-se/site` really gets `var_t` and gives a denial; whether the mod_proxy connection is denied
  without the boolean; the `semanage boolean -l -C` output format regex; `ausearch -ts` date handling.
- dnf: builds noarch rpms (`dojo-lib` 1.0/2.0, `dojo-hello` 1.0/2.0, `dojo-plugin` 1.0) with `rpmbuild`, signs them and
  the repodata with a throwaway gpg key, and the learner writes `/etc/yum.repos.d/dojo-lab.repo`. `check` parses the
  `.repo`, then checks installed versions, `rpm -V` cleanliness, the rpm signature key id, the imported gpg-pubkey, a dnf
  history entry mentioning `dojo-hello-2.0`, `dnf versionlock list` and that `dnf check-update dojo-hello` exits 0.
  Risks: the spec files (`printf` escaping inside `%install`), `rpmsign` with the throwaway key, `repo_gpgcheck`
  with a detached `repomd.xml.asc`, `%{SIGPGP:pgpsig}` output, whether the dependency conflict error appears as intended.
- firewalld: a dedicated zone `dojo-lab` bound to a veth interface in a network namespace. `check` requires `confirm`,
  panic off, non-DROP permanent target, a permanent rich rule for 18081, does `firewall-cmd --reload` and then probes from
  the namespace: 22 and 18080 reachable, 18081 actively refused, ping works. Risks: whether an interface that firewalld did
  not create keeps its zone binding across reload, and whether a rich-rule `reject` really appears as a refused connection
  to the client; the auto-rollback helper `arm-rollback` relies on `firewall-cmd --reload`.

## Known limits

- The dispatcher passes `LAB_ROOT`/`LAB_STATE`; SELinux labels on `/var/lib/linuxdojo-vm-lab` were not considered and
  could matter for the python helper services.
- The modules are not wired into any curriculum or objective matrix; that is up to the repository owner.
