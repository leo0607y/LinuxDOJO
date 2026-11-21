"""Export a disposable-VM lab bundle without changing the host or launching VMs."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "labs" / "vm"
MODULE_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,40}$")
PACKAGES = ("python3", "curl", "ca-certificates", "acl", "attr", "sysstat", "strace", "util-linux",
            "coreutils", "findutils", "lvm2", "parted", "e2fsprogs", "nftables", "dnsmasq",
            "nginx", "openssl", "sqlite3", "dnsutils", "tcpdump", "iproute2", "rsync", "jq",
            "openssh-client", "openssh-server", "git", "vim", "nano", "tmux", "ripgrep",
            "fzf", "fd-find", "bat", "tree", "ncdu", "gcc", "make", "libc6-dev", "python3-venv", "gnupg")


def lab_catalog(source=None):
    source = Path(source) if source is not None else SOURCE
    modules = source / "guest" / "modules"
    catalog = []
    for path in sorted(modules.glob("*.sh")):
        if path.is_symlink() or not path.is_file() or not MODULE_PATTERN.fullmatch(path.stem):
            raise ValueError("Unsafe VM module path: " + str(path))
        text = path.read_text(encoding="utf-8")
        title = re.search(r"^# title: (.+)$", text, re.MULTILINE)
        catalog.append({"id": path.stem, "title": title.group(1) if title else path.stem,
                        "filename": path.name})
    return catalog


def _entry(destination, data, permissions):
    encoded = base64.b64encode(data).decode("ascii")
    return "\n".join(("  - path: " + json.dumps(destination), "    owner: root:root",
                       "    permissions: " + json.dumps(permissions), "    encoding: b64",
                       "    content: " + json.dumps(encoded)))


def render_cloud_init(role, source=None):
    if role not in ("app", "client"):
        raise ValueError("role must be app or client")
    source = Path(source) if source is not None else SOURCE
    template = source / "cloud-init.yaml.in"
    dispatcher = source / "guest" / "dojo-vm-lab"
    if template.is_symlink() or dispatcher.is_symlink():
        raise ValueError("Template and dispatcher must not be symbolic links")
    marker = f"format=linuxdojo-vm-v1\nrole={role}\nhostname=linuxdojo-{role}\n".encode()
    entries = [_entry("/etc/linuxdojo-vm-lab", marker, "0600"),
               _entry("/usr/local/sbin/dojo-vm-lab", dispatcher.read_bytes(), "0755")]
    for module in lab_catalog(source):
        path = source / "guest" / "modules" / module["filename"]
        entries.append(_entry("/usr/local/lib/linuxdojo-vm-lab/modules/" + path.name,
                              path.read_bytes(), "0755"))
    text = template.read_text(encoding="utf-8")
    text = text.replace("@@HOSTNAME@@", "linuxdojo-" + role)
    text = text.replace("@@PACKAGES@@", "\n".join("  - " + value for value in PACKAGES))
    text = text.replace("@@WRITE_FILES@@", "\n".join(entries))
    if "@@" in text:
        raise ValueError("Unresolved cloud-init template value")
    return text


def export_bundle(output, source=None):
    """Write a new bundle; never replace existing paths or execute guest scripts."""
    source = Path(source) if source is not None else SOURCE
    output = Path(output).expanduser()
    if output.exists() or output.is_symlink():
        raise ValueError("Export destination already exists; choose a new directory")
    catalog = lab_catalog(source)
    if not catalog:
        raise ValueError("No VM modules are available")
    generated = {role + "-cloud-init.yaml": render_cloud_init(role, source) for role in ("app", "client")}
    readme = (source / "README.md").read_text(encoding="utf-8")
    software_guide = source / "SOFTWARE.md"
    output.mkdir(parents=True)
    try:
        for filename, content in generated.items():
            (output / filename).write_text(content, encoding="utf-8")
        (output / "README.md").write_text(readme, encoding="utf-8")
        if software_guide.is_file() and not software_guide.is_symlink():
            shutil.copyfile(software_guide, output / "SOFTWARE.md")
        guest = output / "guest"
        (guest / "modules").mkdir(parents=True)
        dispatcher = source / "guest" / "dojo-vm-lab"
        shutil.copyfile(dispatcher, guest / "dojo-vm-lab")
        for module in catalog:
            shutil.copyfile(source / "guest/modules" / module["filename"], guest / "modules" / module["filename"])
        manifest = {"format": "linuxdojo-vm-v1", "image": "24.04", "names": ["linuxdojo-app", "linuxdojo-client"],
                    "modules": catalog, "validation": "export-and-static-tests; guest runtime requires a disposable VM"}
        (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        hashes = {path.relative_to(output).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in sorted(output.rglob("*")) if path.is_file()}
        (output / "SHA256SUMS.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
    except Exception:
        # Only the new export directory is ours to remove; existing destinations were rejected.
        shutil.rmtree(output)
        raise
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="show available guest labs")
    export = commands.add_parser("export", help="write cloud-init and instructions; do not launch VMs")
    export.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            for lab in lab_catalog():
                print(f"{lab['id']}: {lab['title']}")
        else:
            output = export_bundle(args.output)
            print("VM lab bundle exported to " + str(output))
            print("No VM was launched and no host settings were changed. Read README.md in the bundle.")
        return 0
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
