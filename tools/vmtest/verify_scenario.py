#!/usr/bin/env python3
"""Run a checked-in scenario in an existing dedicated VM and retain real output.

Usage: python3 tools/vmtest/verify_scenario.py NAME SCENARIO LOG
The scenario runs as root in the guest, never on the host.
"""
import argparse
from pathlib import Path
import subprocess

import vmtest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name")
    parser.add_argument("scenario", type=Path)
    parser.add_argument("log", type=Path)
    args = parser.parse_args()
    state = vmtest.ensure_ready(args.name)
    # Sync is sequential: vmtest's bundle directory is shared by all VMs.
    rc = vmtest.cmd_install(argparse.Namespace(name=args.name))
    if rc:
        return rc
    script = args.scenario.read_text()
    args.log.parent.mkdir(parents=True, exist_ok=True)
    with args.log.open("w") as output:
        output.write(f"VM={args.name} scenario={args.scenario}\n")
        output.flush()
        result = subprocess.run(vmtest.ssh_base(state) + ["sudo env LC_ALL=C.UTF-8 bash -se"],
                                input=script, text=True, stdout=output, stderr=subprocess.STDOUT,
                                timeout=1200)
        output.write(f"\nSCENARIO_EXIT={result.returncode}\n")
    print(args.log.read_text())
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
