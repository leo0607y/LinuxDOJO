#!/usr/bin/env python3
"""Rootless real-VM harness for the LinuxDOJO VM labs (stdlib only).

Everything lives under ~/.cache/linuxdojo-vm/. No sudo, no host packages, no host network changes.
  prepare                       fetch qemu (apt-get download + dpkg -x) and the verified Ubuntu 24.04 image
  up NAME [--role] [--mem]      boot (create on first use) a VM; cloud-init is the learner's exported bundle
  ssh NAME CMD...               wait for cloud-init, run CMD in the guest
  install NAME                  re-export the bundle and sync dispatcher+modules into the guest
  run-module NAME MOD [--steps] run setup,check,reset (default) through sudo dojo-vm-lab
  snapshot|restore NAME [TAG]   offline qcow2 internal snapshots (VM is stopped, then restarted)
  down NAME | destroy NAME

Networking: user-mode NAT (hostfwd 127.0.0.1:PORT -> guest :22, internet for apt) on NIC 1.
Private app<->client link on NIC 2 is a qemu `-netdev socket` (TCP): the app VM listens on
127.0.0.1:LINKPORT, the client connects, so start the app first. Guests get 192.168.77.10 (app)
and 192.168.77.11 (client) on that link.
"""
import argparse, hashlib, json, os, re, shlex, shutil, signal, socket, subprocess, sys, time, urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CACHE = Path(os.environ.get("LINUXDOJO_VM_CACHE", Path.home() / ".cache/linuxdojo-vm"))
DL, ROOT, SHARE, IMGS, VMS = CACHE / "dl", CACHE / "root", CACHE / "share", CACHE / "images", CACHE / "vms"
IMG_BASE = "https://cloud-images.ubuntu.com/releases/noble/release/"
IMG_NAME = "ubuntu-24.04-server-cloudimg-amd64.img"
PKGS = ["qemu-system-x86", "qemu-utils", "qemu-system-common", "qemu-system-data", "qemu-block-extra"]
LINK_BASE_PORT = 24500
sys.path.insert(0, str(REPO))


def log(*a):
    print("[vmtest]", *a, flush=True)


def run(cmd, timeout=120, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kw)


def qenv():
    env = dict(os.environ)
    libs = [str(ROOT / "usr/lib/x86_64-linux-gnu"), str(ROOT / "lib/x86_64-linux-gnu")]
    env["LD_LIBRARY_PATH"] = ":".join(libs + [env.get("LD_LIBRARY_PATH", "")])
    return env


def qbin(name):
    p = ROOT / "usr/bin" / name
    if not p.exists():
        sys.exit(f"{name} missing: run `vmtest.py prepare` first")
    return str(p)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def fetch(url, dest, timeout=600):
    log("download", url)
    with urllib.request.urlopen(url, timeout=60) as r, open(dest, "wb") as f:
        t0 = time.time()
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
            if time.time() - t0 > timeout:
                raise TimeoutError(url)


# ---------------------------------------------------------------- prepare
def cmd_prepare(a):
    for d in (DL, ROOT, SHARE, IMGS, VMS):
        d.mkdir(parents=True, exist_ok=True)
    if not (ROOT / "usr/bin/qemu-system-x86_64").exists():
        sim = run(["apt-get", "-s", "install", *PKGS], timeout=120).stdout
        names = [l.split()[1] for l in sim.splitlines() if l.startswith("Inst ")]
        # libs that are only recommended/gui are skipped; resolver output already lists hard deps.
        log("packages to fetch:", len(names), " ".join(names))
        for n in names:
            if not list(DL.glob(n + "_*.deb")):
                r = run(["apt-get", "download", n], timeout=300, cwd=DL)
                if r.returncode:
                    sys.exit(f"apt-get download {n} failed: {r.stderr}")
        for deb in sorted(DL.glob("*.deb")):
            r = run(["dpkg", "-x", str(deb), str(ROOT)], timeout=120)
            if r.returncode:
                sys.exit(f"dpkg -x {deb.name}: {r.stderr}")
    # merged firmware dir for -L
    for src in ("usr/share/qemu", "usr/share/seabios", "usr/lib/ipxe/qemu", "usr/share/ipxe/qemu"):
        s = ROOT / src
        if s.is_dir():
            for f in s.iterdir():
                t = SHARE / f.name
                if not t.exists() and not t.is_symlink():
                    t.symlink_to(f)
    r = run([qbin("qemu-system-x86_64"), "--version"], env=qenv())
    log(r.stdout.splitlines()[0] if r.stdout else r.stderr)
    ok = run([qbin("qemu-system-x86_64"), "-L", str(SHARE), "-machine", "q35,accel=kvm", "-display", "none",
              "-S", "-monitor", "none", "-serial", "none", "-nodefaults", "-daemonize",
              "-pidfile", str(CACHE / "probe.pid")], env=qenv(), timeout=30)
    if ok.returncode == 0:
        try:
            os.kill(int((CACHE / "probe.pid").read_text()), signal.SIGKILL)
        except OSError:
            pass
        log("kvm probe ok")
    else:
        log("kvm probe failed:", ok.stderr.strip())
    img = IMGS / IMG_NAME
    sums = IMGS / "SHA256SUMS"
    fetch(IMG_BASE + "SHA256SUMS", sums, 60)
    want = None
    for line in sums.read_text().splitlines():
        h, _, n = line.partition(" ")
        if n.strip().lstrip("*") == IMG_NAME:
            want = h
    if not want:
        sys.exit("image not listed in SHA256SUMS")
    gpg = shutil.which("gpg")
    if gpg:  # best effort signature check of SHA256SUMS
        try:
            fetch(IMG_BASE + "SHA256SUMS.gpg", IMGS / "SHA256SUMS.gpg", 60)
            home = IMGS / "gnupg"; home.mkdir(mode=0o700, exist_ok=True)
            run([gpg, "--homedir", str(home), "--keyserver", "hkps://keyserver.ubuntu.com", "--recv-keys",
                 "D2EB44626FDDC30B513D5BB71A5D6C4C7DB87C81"], timeout=60)
            v = run([gpg, "--homedir", str(home), "--verify", str(IMGS / "SHA256SUMS.gpg"), str(sums)], timeout=30)
            log("gpg verify of SHA256SUMS:", "OK" if v.returncode == 0 else "not verified (" + v.stderr.strip().splitlines()[-1] + ")")
        except Exception as e:
            log("gpg step skipped:", e)
    if not img.exists() or sha256(img) != want:
        fetch(IMG_BASE + IMG_NAME, img)
    got = sha256(img)
    if got != want:
        img.unlink()
        sys.exit(f"SHA256 MISMATCH {got} != {want}; image deleted")
    (IMGS / "base.sha256").write_text(want + "\n")
    log("image verified sha256", want)


# ---------------------------------------------------------------- vm state
def vdir(name):
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,30}", name):
        sys.exit("bad VM name")
    return VMS / name


def load(name):
    p = vdir(name) / "vm.json"
    if not p.exists():
        sys.exit(f"no such VM {name}")
    return json.loads(p.read_text())


def save(name, st):
    (vdir(name) / "vm.json").write_text(json.dumps(st, indent=1))


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except (OSError, TypeError):
        return False


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def ssh_base(st, tty=False):
    return ["ssh", "-i", st["key"], "-p", str(st["port"]), "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR", "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=5", "-o", "ServerAliveInterval=10", "ubuntu@127.0.0.1"]


def render_user_data(role, pubkey):
    from engine import vm_labs
    main = vm_labs.render_cloud_init(role)  # exactly what a learner gets
    link_ip = "192.168.77.10" if role == "app" else "192.168.77.11"
    mac = "52:54:00:77:00:10" if role == "app" else "52:54:00:77:00:11"
    extra = f"""#cloud-config
ssh_authorized_keys:
  - {pubkey}
write_files:
  - path: /etc/netplan/60-dojo-link.yaml
    permissions: '0600'
    content: |
      network:
        version: 2
        ethernets:
          dojolink:
            match: {{macaddress: "{mac}"}}
            addresses: [{link_ip}/24]
"""
    b = "==DOJOBOUNDARY=="
    def part(t):
        return f"--{b}\nContent-Type: text/cloud-config; charset=\"utf-8\"\nMIME-Version: 1.0\n\n{t}\n"
    # merge_how: lists in write_files must append, not replace
    merge = "merge_how:\n - name: list\n   settings: [append]\n - name: dict\n   settings: [no_replace, recurse_list]\n"
    extra = extra.replace("#cloud-config\n", "#cloud-config\n" + merge, 1)
    return f"Content-Type: multipart/mixed; boundary=\"{b}\"\nMIME-Version: 1.0\n\n" + part(main) + part(extra) + f"--{b}--\n"


def start_qemu(name, st):
    d = vdir(name)
    q = [qbin("qemu-system-x86_64"), "-L", str(SHARE), "-machine", "q35,accel=kvm", "-cpu", "host",
         "-smp", str(st.get("cpus", 2)), "-m", str(st["mem"]), "-display", "none", "-monitor", "none",
         "-serial", f"file:{d/'serial.log'}", "-daemonize", "-pidfile", str(d / "qemu.pid"),
         "-drive", f"file={d/'disk.qcow2'},if=virtio,format=qcow2",
         "-netdev", f"user,id=n0,hostfwd=tcp:127.0.0.1:{st['port']}-:22",
         "-device", "virtio-net-pci,netdev=n0",
         "-device", "virtio-rng-pci"]
    if st.get("seed_port"):
        q += ["-smbios", f"type=1,serial=ds=nocloud-net;s=http://10.0.2.2:{st['seed_port']}/"]
    lp = st["link_port"]
    mac = "52:54:00:77:00:10" if st["role"] == "app" else "52:54:00:77:00:11"
    nd = f"socket,id=n1,listen=127.0.0.1:{lp}" if st["role"] == "app" else f"socket,id=n1,connect=127.0.0.1:{lp}"
    q += ["-netdev", nd, "-device", f"virtio-net-pci,netdev=n1,mac={mac}"]
    r = run(q, env=qenv(), timeout=60)
    if r.returncode:
        sys.exit("qemu failed: " + r.stderr)
    st["pid"] = int((d / "qemu.pid").read_text())
    save(name, st)


def start_seed(name, st):
    d = vdir(name)
    seed = d / "seed"
    if not (seed / "user-data").exists():
        return
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-I", "-m", "http.server", str(port), "--bind", "127.0.0.1",
                             "--directory", str(seed)], stdout=open(d / "seed-http.log", "w"),
                            stderr=subprocess.STDOUT, start_new_session=True, cwd="/")
    st["seed_port"], st["seed_pid"] = port, proc.pid
    save(name, st)
    time.sleep(0.5)


def cmd_up(a):
    d = vdir(a.name)
    if (d / "vm.json").exists():
        st = load(a.name)
        if alive(st.get("pid")):
            return log(a.name, "already running, ssh port", st["port"])
        st["seed_port"] = None
        if st.get("seed_pid") and alive(st["seed_pid"]):
            os.kill(st["seed_pid"], signal.SIGTERM)
        start_qemu(a.name, st)
        return log("restarted existing VM", a.name)
    base, want = IMGS / IMG_NAME, (IMGS / "base.sha256")
    if not base.exists() or not want.exists() or sha256(base) != want.read_text().strip():
        sys.exit("base image not verified: run `vmtest.py prepare`")
    d.mkdir(parents=True)
    key = d / "id_ed25519"
    run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "vmtest-ephemeral", "-f", str(key)])
    r = run([qbin("qemu-img"), "create", "-f", "qcow2", "-F", "qcow2", "-b", str(base), str(d / "disk.qcow2"), "16G"],
            env=qenv())
    if r.returncode:
        sys.exit(r.stderr)
    seed = d / "seed"; seed.mkdir()
    (seed / "user-data").write_text(render_user_data(a.role, (d / "id_ed25519.pub").read_text().strip()))
    (seed / "meta-data").write_text(f"instance-id: dojo-{a.name}-{int(time.time())}\nlocal-hostname: linuxdojo-{a.role}\n")
    (seed / "vendor-data").write_text("")
    st = {"name": a.name, "role": a.role, "mem": a.mem, "cpus": a.cpus, "port": free_port(), "key": str(key),
          "link_port": int(os.environ.get("VMTEST_LINK_PORT", LINK_BASE_PORT)),
          "created": time.time()}
    save(a.name, st)
    start_seed(a.name, st)
    start_qemu(a.name, st)
    log(f"booted {a.name} role={a.role} ssh=127.0.0.1:{st['port']} serial={d/'serial.log'}")


def wait_ssh(st, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not alive(st.get("pid")):
            sys.exit("VM process died; see serial.log")
        try:
            if run(ssh_base(st) + ["true"], timeout=15).returncode == 0:
                return
        except subprocess.TimeoutExpired:
            pass
        time.sleep(3)
    sys.exit("ssh timeout")


def ensure_ready(name, timeout=900):
    st = load(name)
    if st.get("ready"):
        wait_ssh(st, 120)
        return st
    wait_ssh(st, 300)
    t0 = time.time()
    r = run(ssh_base(st) + ["cloud-init status --wait --long 2>&1 | tr -d .; exit ${PIPESTATUS[0]}"], timeout=timeout)
    log("cloud-init:", r.stdout.strip().replace("\n", " | "), f"({time.time()-t0:.0f}s)")
    if r.returncode not in (0, 2):
        if os.environ.get("VMTEST_STRICT"):
            sys.exit("cloud-init failed rc=%s\n%s" % (r.returncode, r.stdout + r.stderr))
        log("WARNING cloud-init reported errors (rc=%s); continuing, inspect /var/log/cloud-init-output.log" % r.returncode)
    st = load(name)
    st["ready"] = True
    if st.get("seed_pid") and alive(st["seed_pid"]):
        os.kill(st["seed_pid"], signal.SIGTERM)
    save(name, st)
    return st


def cmd_ssh(a):
    st = ensure_ready(a.name)
    try:
        r = run(ssh_base(st) + [" ".join(a.cmd)], timeout=a.timeout)
    except subprocess.TimeoutExpired:
        print("TIMEOUT"); return 124
    sys.stdout.write(r.stdout); sys.stderr.write(r.stderr)
    return r.returncode


def cmd_install(a):
    from engine import vm_labs
    st = ensure_ready(a.name)
    out = CACHE / "bundle"
    if out.exists():
        shutil.rmtree(out)
    vm_labs.export_bundle(out)
    base = ssh_base(st)
    scp = ["scp", "-r", "-i", st["key"], "-P", str(st["port"]), "-o", "StrictHostKeyChecking=no",
           "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR", str(out / "guest"), "ubuntu@127.0.0.1:/tmp/dojo-guest"]
    run(base + ["rm -rf /tmp/dojo-guest"], timeout=30)
    r = run(scp, timeout=120)
    if r.returncode:
        sys.exit(r.stderr)
    script = ("set -e; sudo install -d -m0755 -o root -g root /usr/local/lib/linuxdojo-vm-lab /usr/local/lib/linuxdojo-vm-lab/modules;"
              "sudo install -m0755 -o root -g root /tmp/dojo-guest/dojo-vm-lab /usr/local/sbin/dojo-vm-lab;"
              "sudo rm -f /usr/local/lib/linuxdojo-vm-lab/modules/*.sh;"
              "for f in /tmp/dojo-guest/modules/*.sh; do sudo install -m0755 -o root -g root \"$f\" /usr/local/lib/linuxdojo-vm-lab/modules/; done;"
              "sudo dojo-vm-lab list | wc -l")
    r = run(base + [script], timeout=60)
    print("modules installed in guest:", r.stdout.strip(), r.stderr.strip())
    return r.returncode


def cmd_run_module(a):
    st = ensure_ready(a.name)
    if not a.no_sync:
        cmd_install(argparse.Namespace(name=a.name))
    rc_all = 0
    for step in a.steps.split(","):
        t0 = time.time()
        try:
            r = run(ssh_base(st) + [f"sudo dojo-vm-lab {shlex.quote(a.module)} {shlex.quote(step)}"], timeout=a.timeout)
            out, rc = r.stdout + r.stderr, r.returncode
        except subprocess.TimeoutExpired:
            out, rc = "TIMEOUT", 124
        print(f"=== {a.module} {step}: exit={rc} ({time.time()-t0:.1f}s)\n{out.rstrip()}")
        rc_all = rc_all or rc
    return rc_all


def stop(name, timeout=60):
    st = load(name)
    pid = st.get("pid")
    if alive(pid):
        try:
            run(ssh_base(st) + ["sudo systemctl poweroff"], timeout=15)
        except Exception:
            pass
        t0 = time.time()
        while alive(pid) and time.time() - t0 < timeout:
            time.sleep(1)
        if alive(pid):
            os.kill(pid, signal.SIGKILL)
    if st.get("seed_pid") and alive(st["seed_pid"]):
        os.kill(st["seed_pid"], signal.SIGTERM)


def cmd_down(a):
    stop(a.name); log("stopped", a.name)


def cmd_destroy(a):
    if (vdir(a.name) / "vm.json").exists():
        stop(a.name, 5)
    shutil.rmtree(vdir(a.name), ignore_errors=True)
    log("destroyed", a.name)


def cmd_snapshot(a):
    stop(a.name)
    r = run([qbin("qemu-img"), "snapshot", "-c", a.tag, str(vdir(a.name) / "disk.qcow2")], env=qenv())
    print(r.stdout + r.stderr)
    st = load(a.name); st["seed_port"] = None; start_qemu(a.name, st)
    return r.returncode


def cmd_restore(a):
    stop(a.name)
    r = run([qbin("qemu-img"), "snapshot", "-a", a.tag, str(vdir(a.name) / "disk.qcow2")], env=qenv())
    print(r.stdout + r.stderr)
    st = load(a.name); st["seed_port"] = None; start_qemu(a.name, st)
    return r.returncode


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="c", required=True)
    s.add_parser("prepare").set_defaults(f=cmd_prepare)
    x = s.add_parser("up"); x.add_argument("name"); x.add_argument("--role", choices=["app", "client"], default="app")
    x.add_argument("--mem", type=int, default=2048); x.add_argument("--cpus", type=int, default=2); x.set_defaults(f=cmd_up)
    x = s.add_parser("ssh"); x.add_argument("name"); x.add_argument("--timeout", type=int, default=300)
    x.add_argument("cmd", nargs=argparse.REMAINDER); x.set_defaults(f=cmd_ssh)
    x = s.add_parser("install"); x.add_argument("name"); x.set_defaults(f=cmd_install)
    x = s.add_parser("run-module"); x.add_argument("name"); x.add_argument("module")
    x.add_argument("--steps", default="setup,check,reset"); x.add_argument("--timeout", type=int, default=300)
    x.add_argument("--no-sync", action="store_true"); x.set_defaults(f=cmd_run_module)
    for n, f in (("snapshot", cmd_snapshot), ("restore", cmd_restore)):
        x = s.add_parser(n); x.add_argument("name"); x.add_argument("tag", nargs="?", default="clean"); x.set_defaults(f=f)
    for n, f in (("down", cmd_down), ("destroy", cmd_destroy)):
        x = s.add_parser(n); x.add_argument("name"); x.set_defaults(f=f)
    a = p.parse_args()
    sys.exit(a.f(a) or 0)


if __name__ == "__main__":
    main()
