"""ネットワークの模擬コマンド（ping / curl / wget / dig / nslookup / ip / ss / hostname / traceroute / getent / ufw）。

実際の通信は一切しない（socket も subprocess も使わない）。固定の架空データだけを返す。
  - IP は 192.0.2.0/24・198.51.100.0/24・203.0.113.0/24、ドメインは example.com / example.org / *.test
  - 手元の端末（dojo-local）は 192.0.2.10、ssh 先の training-server は 192.0.2.20
状態は terminal.progress["network"]（ufw の設定）に JSON で持つ。課題側は step["ufw"] で初期状態を指定できる。
  step["ufw"] = {"active": True, "incoming": "deny", "rules": [["22/tcp", "ALLOW", "Anywhere"], ...]}
"""
import ipaddress
import re

from engine.commands import command, on_prepare, on_check, register_package
from engine.guided import Result

register_package("dnsutils", "dig や nslookup で DNS（名前解決）を調べるコマンド集", "9.18-training")
register_package("traceroute", "通信が通る経路をたどるコマンド", "2.1.5-training")

NOW_TEXT = "Thu Jan 15 09:30:00 JST 2026"
WGET_NOW = "2026-01-15 09:30:00"
HTTP_DATE = "Thu, 15 Jan 2026 00:30:00 GMT"

IDENTITY = {
    False: {"name": "dojo-local", "v4": "192.0.2.10", "v6": "2001:db8::10", "mac": "52:54:00:12:34:56"},
    True: {"name": "training-server", "v4": "192.0.2.20", "v6": "2001:db8::20", "mac": "52:54:00:ab:cd:ef"},
}
GATEWAY = "192.0.2.1"
RESOLVER = "127.0.0.53"

# ---- DNS のゾーン（固定）
ZONE = {
    "example.com": {"A": ["203.0.113.10"], "AAAA": ["2001:db8:203::10"], "MX": ["10 mail.example.com."],
                    "NS": ["ns1.example.com."], "TXT": ['"v=spf1 mx -all"']},
    "www.example.com": {"CNAME": ["example.com."]},
    "mail.example.com": {"A": ["203.0.113.25"]},
    "ns1.example.com": {"A": ["198.51.100.53"]},
    "example.org": {"A": ["198.51.100.20"]},
    "app.test": {"A": ["192.0.2.30"]},
    "down.test": {"A": ["203.0.113.99"]},
}
EXTRA_HOSTS = {"localhost": "127.0.0.1", "gateway.test": GATEWAY}
ALIVE = {"127.0.0.1", GATEWAY, "192.0.2.10", "192.0.2.20", "192.0.2.30", "198.51.100.1", "198.51.100.20",
         "198.51.100.53", "203.0.113.10", "203.0.113.25"}
DNS_SERVERS = {RESOLVER, "198.51.100.53", GATEWAY}
RECORD_TYPES = ("A", "AAAA", "MX", "NS", "TXT", "CNAME", "PTR")
APP_HOSTS = {"app.test", "localhost", "127.0.0.1"}


def _ident(terminal):
    return IDENTITY[bool(terminal.progress.get("remote"))]


def _missing(cmd, package):
    return Result(f"Command '{cmd}' not found, but can be installed with:\nsudo apt install {package}\n"
                  f"（訓練用の表示です。この練習では {package} がまだ入っていません）", 127)


def _need(terminal, cmd, package):
    return None if package in terminal.progress["packages"] else _missing(cmd, package)


def _valid_ipv4(text):
    try:
        return isinstance(ipaddress.ip_address(text), ipaddress.IPv4Address)
    except ValueError:
        return False


def resolve(terminal, name):
    """名前を (正式名, IPv4) にする。引けなければ None。"""
    name = name.lower().rstrip(".")
    if _valid_ipv4(name):
        return name, name
    me = _ident(terminal)
    if name in (me["name"], "dojo-local", "training-server"):
        return name, IDENTITY[name == "training-server"]["v4"]
    if name in EXTRA_HOSTS:
        return name, EXTRA_HOSTS[name]
    for _ in range(5):
        record = ZONE.get(name)
        if record is None:
            return None
        if "A" in record:
            return name, record["A"][0]
        if "CNAME" in record:
            name = record["CNAME"][0].rstrip(".")
            continue
        return None
    return None


def _reachable(ip):
    return ip in ALIVE or ip.startswith("127.")


# ---------------------------------------------------------------- hostname / getent
@command("hostname")
def hostname(terminal, rest, stdin=None, admin=False):
    me = _ident(terminal)
    if rest == ["-I"]:
        return Result(f"{me['v4']} {me['v6']}")
    if rest == ["-i"]:
        return Result("127.0.1.1")
    if rest in (["-f"], ["-s"]):
        return Result(me["name"])
    return None


@command("getent")
def getent(terminal, rest, stdin=None, admin=False):
    if len(rest) != 2 or rest[0] != "hosts":
        return None
    found = resolve(terminal, rest[1])
    if found is None or not found[0] == rest[1].lower().rstrip("."):
        if found is None:
            return Result("", 2)
    canonical, ip = found
    if canonical != rest[1].lower().rstrip(".") and ip != rest[1]:
        return Result(f"{ip:<15} {canonical} {rest[1]}")
    return Result(f"{ip:<15} {canonical}")


# ---------------------------------------------------------------- ping
def _rtt_base(ip):
    if ip.startswith("127."):
        return 0.03
    if ip.startswith("192.0.2."):
        return 0.4
    if ip.startswith("198.51.100."):
        return 6.0
    return 12.0


@command("ping")
def ping(terminal, rest, stdin=None, admin=False):
    count, target, i = None, None, 0
    while i < len(rest):
        arg = rest[i]
        if arg == "-c" and i + 1 < len(rest) and rest[i + 1].isdigit():
            count, i = int(rest[i + 1]), i + 2
        elif re.fullmatch(r"-c\d+", arg):
            count, i = int(arg[2:]), i + 1
        elif arg in ("-W", "-i") and i + 1 < len(rest) and rest[i + 1].isdigit():
            i += 2
        elif arg in ("-4", "-q"):
            i += 1
        elif arg.startswith("-") or target is not None:
            return None
        else:
            target, i = arg, i + 1
    if target is None:
        return Result("ping: usage error: Destination address required", 2)
    if count is None:
        return Result("実際の ping は、止めるまで送り続けます。この模擬ターミナルでは Ctrl+C で止められないので、"
                      "-c オプションで送る回数を決めて実行しましょう。", 1)
    if not 1 <= count <= 10:
        return Result("この練習では -c に 1 から 10 までの回数を指定します。", 1)
    found = resolve(terminal, target)
    if found is None:
        return Result(f"ping: {target}: Name or service not known", 2)
    name, ip = found
    lines = [f"PING {name} ({ip}) 56(84) bytes of data."]
    alive = _reachable(ip)
    base, ttl = _rtt_base(ip), (64 if ip.startswith(("127.", "192.0.2.")) else 56)
    wobble = (0.0, 0.31, -0.12, 0.18, 0.05, 0.27, -0.08, 0.22, 0.11, 0.02)
    times = []
    if alive:
        who = "localhost (127.0.0.1)" if ip == "127.0.0.1" and name == "localhost" else ip
        for seq in range(1, count + 1):
            value = max(0.02, base + wobble[(seq - 1) % 10] * (0.1 if base < 1 else 1))
            times.append(value)
            shown = f"{value:.3f}" if base < 1 else f"{value:.1f}"
            lines.append(f"64 bytes from {who}: icmp_seq={seq} ttl={ttl} time={shown} ms")
    lines += ["", f"--- {name} ping statistics ---"]
    received = count if alive else 0
    loss = 0 if alive else 100
    total = (count - 1) * 1000 + 3 if alive else count * 1000 + 46
    lines.append(f"{count} packets transmitted, {received} received, {loss}% packet loss, time {total}ms")
    if alive:
        avg = sum(times) / len(times)
        mdev = (sum((x - avg) ** 2 for x in times) / len(times)) ** 0.5
        digits = 3 if base < 1 else 3
        lines.append(f"rtt min/avg/max/mdev = {min(times):.{digits}f}/{avg:.{digits}f}/{max(times):.{digits}f}/{mdev:.{digits}f} ms")
    return Result("\n".join(lines), 0 if alive else 1)


# ---------------------------------------------------------------- ip
def _addr_blocks(me):
    lo = ["1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000",
          "    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00"]
    lo4 = ["    inet 127.0.0.1/8 scope host lo", "       valid_lft forever preferred_lft forever"]
    lo6 = ["    inet6 ::1/128 scope host noprefixroute ", "       valid_lft forever preferred_lft forever"]
    eth = ["2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP group default qlen 1000",
           f"    link/ether {me['mac']} brd ff:ff:ff:ff:ff:ff"]
    prefix = me["v4"].rsplit(".", 1)[0]
    eth4 = [f"    inet {me['v4']}/24 metric 100 brd {prefix}.255 scope global dynamic eth0",
            "       valid_lft 86389sec preferred_lft 86389sec"]
    eth6 = [f"    inet6 {me['v6']}/64 scope global ", "       valid_lft forever preferred_lft forever"]
    return {"lo": (lo, lo4, lo6), "eth0": (eth, eth4, eth6)}


def _ip_addr(me, flags, device):
    blocks = _addr_blocks(me)
    if device not in (None, "lo", "eth0"):
        return Result(f'Device "{device}" does not exist.', 1)
    names = [device] if device else ["lo", "eth0"]
    if "br" in flags:
        rows = []
        for name in names:
            v4 = "127.0.0.1/8" if name == "lo" else f"{me['v4']}/24"
            v6 = "::1/128" if name == "lo" else f"{me['v6']}/64"
            state = "UNKNOWN" if name == "lo" else "UP"
            addrs = ([v4] if "6" not in flags else []) + ([v6] if "4" not in flags else [])
            rows.append(f"{name:<16} {state:<14} {' '.join(addrs)} ")
        return Result("\n".join(rows))
    lines = []
    for name in names:
        head, v4, v6 = blocks[name]
        lines += head + (v4 if "6" not in flags else []) + (v6 if "4" not in flags else [])
    return Result("\n".join(lines))


def _ip_link(me, flags, device):
    blocks = _addr_blocks(me)
    names = [device] if device in ("lo", "eth0") else ["lo", "eth0"]
    if device not in (None, "lo", "eth0"):
        return Result(f'Device "{device}" does not exist.', 1)
    if "br" in flags:
        return Result("\n".join(f"{n:<16} {'UNKNOWN' if n == 'lo' else 'UP':<14} "
                                f"{'00:00:00:00:00:00' if n == 'lo' else me['mac']} <"
                                f"{'LOOPBACK,UP,LOWER_UP' if n == 'lo' else 'BROADCAST,MULTICAST,UP,LOWER_UP'}> " for n in names))
    return Result("\n".join(line for n in names for line in blocks[n][0]))


def _ip_route(me, flags, rest):
    if "6" in flags:
        return Result(f"2001:db8::/64 dev eth0 proto kernel metric 256 pref medium\nfe80::/64 dev eth0 proto kernel metric 256 pref medium\n"
                      f"default via fe80::1 dev eth0 proto ra metric 1024 expires 1700sec pref medium")
    prefix = me["v4"].rsplit(".", 1)[0]
    if rest and rest[0] == "get":
        if len(rest) != 2 or not _valid_ipv4(rest[1]):
            return None
        dest = rest[1]
        if dest.startswith("127."):
            return Result(f"local {dest} dev lo src 127.0.0.1 uid 1000 \n    cache <local> ")
        if dest.startswith(prefix + "."):
            return Result(f"{dest} dev eth0 src {me['v4']} uid 1000 \n    cache ")
        return Result(f"{dest} via {GATEWAY} dev eth0 src {me['v4']} uid 1000 \n    cache ")
    if rest not in ([], ["show"], ["list"]):
        return None
    return Result(f"default via {GATEWAY} dev eth0 proto dhcp src {me['v4']} metric 100 \n"
                  f"{prefix}.0/24 dev eth0 proto kernel scope link src {me['v4']} metric 100 \n"
                  f"{GATEWAY} dev eth0 proto dhcp scope link src {me['v4']} metric 100 ")


@command("ip")
def ip(terminal, rest, stdin=None, admin=False):
    me = _ident(terminal)
    flags, args = set(), []
    for arg in rest:
        if arg == "-4":
            flags.add("4")
        elif arg == "-6":
            flags.add("6")
        elif arg in ("-br", "-brief"):
            flags.add("br")
        elif arg.startswith("-") and not args:
            return None
        else:
            args.append(arg)
    if not args:
        return None
    obj, rest = args[0], args[1:]
    if obj in ("a", "addr", "address"):
        if rest and rest[0] in ("show", "s", "list", "l"):
            rest = rest[1:]
        if rest and rest[0] == "dev":
            rest = rest[1:]
        if len(rest) > 1:
            return None
        return _ip_addr(me, flags, rest[0] if rest else None)
    if obj in ("l", "link"):
        if rest and rest[0] in ("show", "list"):
            rest = rest[1:]
        if len(rest) > 1:
            return None
        return _ip_link(me, flags, rest[0] if rest else None)
    if obj in ("r", "route", "ro"):
        return _ip_route(me, flags, rest)
    return None


# ---------------------------------------------------------------- ss
TCP_LISTEN = [
    ("0.0.0.0", 22, "sshd", 512, 3), ("[::]", 22, "sshd", 512, 4),
    ("127.0.0.53%lo", 53, "systemd-resolve", 301, 14), ("127.0.0.1", 5432, "postgres", 1190, 6),
    ("0.0.0.0", 8080, "python3", 3120, 3),
]
UDP_LISTEN = [("127.0.0.53%lo", 53, "systemd-resolve", 301, 13), ("192.0.2.10%eth0", 68, "systemd-network", 288, 15)]
PORT_NAMES = {22: "ssh", 53: "domain", 68: "bootpc", 5432: "postgresql", 8080: "http-alt"}


def _table(rows):
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    return "\n".join("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip() for row in rows)


@command("ss", sudo=True)
def ss(terminal, rest, stdin=None, admin=False):
    if len(rest) != 1 or not re.fullmatch(r"-[tulnpa]+", rest[0]):
        return None
    letters = set(rest[0][1:])
    tcp, udp = "t" in letters, "u" in letters
    if not tcp and not udp:
        tcp = udp = True
    listening = "l" in letters
    show_all = "a" in letters
    numeric, procs = "n" in letters, "p" in letters
    me = _ident(terminal)
    header = (["Netid"] if (tcp and udp) or udp else []) + ["State", "Recv-Q", "Send-Q", "Local Address:Port", "Peer Address:Port"]
    with_netid = tcp and udp or (udp and not tcp)
    header = (["Netid"] if with_netid else []) + ["State", "Recv-Q", "Send-Q", "Local Address:Port", "Peer Address:Port"]
    if procs:
        header.append("Process")
    rows = [header]

    def port_text(port):
        return str(port) if numeric else PORT_NAMES.get(port, str(port))

    def process_text(name, pid, fd):
        return f'users:(("{name}",pid={pid},fd={fd}))' if admin else ""

    def add(netid, state, local, port, peer, proc):
        row = ([netid] if with_netid else []) + [state, "0", "128" if state == "LISTEN" else "0",
                                                  f"{local}:{port_text(port)}", peer]
        if procs:
            row.append(proc)
        rows.append(row)

    if listening or show_all:
        if tcp:
            for addr, port, name, pid, fd in TCP_LISTEN:
                add("tcp", "LISTEN", addr, port, "[::]:*" if addr == "[::]" else "0.0.0.0:*", process_text(name, pid, fd))
        if udp:
            for addr, port, name, pid, fd in UDP_LISTEN:
                add("udp", "UNCONN", addr, port, "0.0.0.0:*", process_text(name, pid, fd))
    if not listening and tcp or show_all and tcp:
        add("tcp", "ESTAB", me["v4"], 22, "198.51.100.77:" + ("51514" if numeric else "51514"), process_text("sshd", 2210, 4))
    if len(rows) == 1:
        return Result(_table(rows))
    return Result(_table(rows))


# ---------------------------------------------------------------- traceroute
@command("traceroute")
def traceroute(terminal, rest, stdin=None, admin=False):
    missing = _need(terminal, "traceroute", "traceroute")
    if missing:
        return missing
    numeric, maxhops, target, i = False, 30, None, 0
    while i < len(rest):
        arg = rest[i]
        if arg == "-n":
            numeric, i = True, i + 1
        elif arg == "-m" and i + 1 < len(rest) and rest[i + 1].isdigit():
            maxhops, i = int(rest[i + 1]), i + 2
        elif arg.startswith("-") or target is not None:
            return None
        else:
            target, i = arg, i + 1
    if target is None or not 1 <= maxhops <= 30:
        return None
    found = resolve(terminal, target)
    if found is None:
        return Result(f"{target}: Name or service not known\nCannot handle \"host\" cmdline arg `{target}' on position 1 (argc 1)", 2)
    name, dest = found
    lines = [f"traceroute to {name} ({dest}), {maxhops} hops max, 60 byte packets"]
    lan = dest.startswith("192.0.2.") or dest.startswith("127.")
    if lan:
        hops = [(dest, None)]
    elif dest.startswith("198.51.100."):
        hops = [(GATEWAY, "_gateway"), ("198.51.100.1", None), (dest, name)]
    elif dest == "203.0.113.99":
        hops = [(GATEWAY, "_gateway"), ("198.51.100.1", None), ("203.0.113.1", None)] + [None] * 27
    else:
        hops = [(GATEWAY, "_gateway"), ("198.51.100.1", None), None, ("203.0.113.1", None), (dest, name)]
    for number, hop in enumerate(hops[:maxhops], 1):
        if hop is None:
            lines.append(f"{number:>2}  * * *")
            continue
        addr, label = hop
        times = [0.4 + number * 2.9 + step * 0.17 for step in range(3)]
        shown = f"{addr}" if numeric or label is None and addr != dest else f"{label or addr} ({addr})"
        if numeric:
            shown = addr
        elif label is None:
            shown = f"{addr} ({addr})"
        lines.append(f"{number:>2}  {shown}  " + "  ".join(f"{t:.3f} ms" for t in times))
    return Result("\n".join(lines))


# ---------------------------------------------------------------- DNS (dig / nslookup)
def _zone_of(name):
    return ".".join(name.rstrip(".").split(".")[-2:])


def _dns_query(name, rtype):
    """(status, 回答の行 [(owner, type, data)], SOA を付けるか)"""
    name = name.lower().rstrip(".")
    record = ZONE.get(name)
    if record is None:
        return "NXDOMAIN", [], True
    if rtype in record:
        return "NOERROR", [(name, rtype, data) for data in record[rtype]], False
    if "CNAME" in record and rtype != "CNAME":
        target = record["CNAME"][0]
        answers = [(name, "CNAME", target)]
        answers += [(target.rstrip("."), rtype, d) for d in ZONE.get(target.rstrip("."), {}).get(rtype, [])]
        return "NOERROR", answers, False
    return "NOERROR", [], True


def _reverse_name(ip):
    return ".".join(reversed(ip.split("."))) + ".in-addr.arpa"


def _reverse_answers(ip):
    for name, record in ZONE.items():
        if ip in record.get("A", []):
            return [(_reverse_name(ip), "PTR", name + ".")]
    if ip == GATEWAY:
        return [(_reverse_name(ip), "PTR", "gateway.test.")]
    return []


@command("dig")
def dig(terminal, rest, stdin=None, admin=False):
    missing = _need(terminal, "dig", "dnsutils")
    if missing:
        return missing
    server, name, rtype, flags, reverse, i = None, None, None, set(), False, 0
    while i < len(rest):
        arg = rest[i]
        if arg.startswith("@") and len(arg) > 1:
            server = arg[1:]
        elif arg in ("+short", "+noall", "+answer"):
            flags.add(arg[1:])
        elif arg == "-x" and i + 1 < len(rest) and _valid_ipv4(rest[i + 1]):
            name, reverse, i = rest[i + 1], True, i + 1
        elif arg == "-t" and i + 1 < len(rest) and rest[i + 1].upper() in RECORD_TYPES:
            rtype, i = rest[i + 1].upper(), i + 1
        elif arg.upper() in RECORD_TYPES and name is not None and rtype is None:
            rtype = arg.upper()
        elif arg.startswith(("-", "+")) or name is not None:
            return None
        else:
            name = arg
        i += 1
    if name is None:
        return None
    rtype = rtype or ("PTR" if reverse else "A")
    shown_args = " ".join(rest)
    banner = f"; <<>> DiG 9.18.28-0ubuntu0.24.04.1-Ubuntu <<>> {shown_args}"
    srv = server or RESOLVER
    if server and not _valid_ipv4(server) and server not in ZONE:
        return Result(f"dig: couldn't get address for '{server}': not found", 9)
    if server and (resolve(terminal, server) or (None, None))[1] not in DNS_SERVERS:
        comm = f";; communications error to {resolve(terminal, server)[1]}#53: timed out"
        return Result("\n".join([comm, comm, comm, "", banner, "; (1 server found)", ";; global options: +cmd",
                                 ";; no servers could be reached"]), 9)
    srv = (resolve(terminal, server) or (None, srv))[1] if server else srv
    if reverse:
        status, answers, soa = ("NOERROR", _reverse_answers(name), False)
        if not answers:
            status, soa = "NXDOMAIN", True
        qname = _reverse_name(name)
    else:
        status, answers, soa = _dns_query(name, rtype)
        qname = name.lower().rstrip(".")
    lines_answer = [f"{o}.\t300\tIN\t{t}\t{d}" for o, t, d in answers]
    if "short" in flags:
        return Result("\n".join(d for _, _, d in answers))
    if "noall" in flags and "answer" in flags:
        return Result("\n".join(lines_answer))
    if "noall" in flags:
        return Result("")
    zone = _zone_of(qname if not reverse else "in-addr.arpa")
    soa_line = f"{zone}.\t300\tIN\tSOA\tns1.example.com. hostmaster.example.com. 2026011501 7200 3600 1209600 300"
    flag_text = "qr aa rd" if srv == "198.51.100.53" else "qr rd ra"
    out = [banner]
    if server:
        out.append("; (1 server found)")
    out += [";; global options: +cmd", ";; Got answer:",
            f";; ->>HEADER<<- opcode: QUERY, status: {status}, id: 41234",
            f";; flags: {flag_text}; QUERY: 1, ANSWER: {len(answers)}, AUTHORITY: {1 if soa else 0}, ADDITIONAL: 1", "",
            ";; OPT PSEUDOSECTION:", "; EDNS: version: 0, flags:; udp: 65494", ";; QUESTION SECTION:",
            f";{qname}.\t\t\tIN\t{rtype}", ""]
    if answers:
        out += [";; ANSWER SECTION:", *lines_answer, ""]
    if soa:
        out += [";; AUTHORITY SECTION:", soa_line, ""]
    out += [";; Query time: 12 msec", f";; SERVER: {srv}#53({srv}) (UDP)", f";; WHEN: {NOW_TEXT}",
            f";; MSG SIZE  rcvd: {40 + 16 * len(answers) + (60 if soa else 0)}"]
    return Result("\n".join(out))


@command("nslookup")
def nslookup(terminal, rest, stdin=None, admin=False):
    missing = _need(terminal, "nslookup", "dnsutils")
    if missing:
        return missing
    rtype, args = "A", []
    for arg in rest:
        if arg.lower().startswith(("-type=", "-q=")) and arg.split("=", 1)[1].upper() in RECORD_TYPES:
            rtype = arg.split("=", 1)[1].upper()
        elif arg.startswith("-"):
            return None
        else:
            args.append(arg)
    if not 1 <= len(args) <= 2:
        return None
    name, server = args[0], (args[1] if len(args) == 2 else RESOLVER)
    if server not in DNS_SERVERS:
        return Result(f";; communications error to {server}#53: timed out\n;; no servers could be reached", 1)
    head = f"Server:\t\t{server}\nAddress:\t{server}#53\n"
    note = "" if server == "198.51.100.53" else "Non-authoritative answer:\n"
    if _valid_ipv4(name):
        answers = _reverse_answers(name)
        if not answers:
            return Result(f"{head}\n** server can't find {_reverse_name(name)}: NXDOMAIN", 1)
        return Result(f"{head}\n{note}{_reverse_name(name)}\tname = {answers[0][2]}\n\nAuthoritative answers can be found from:".replace(
            "\n\nAuthoritative answers can be found from:", ""))
    key = name.lower().rstrip(".")
    status, answers, _ = _dns_query(key, rtype)
    if status == "NXDOMAIN":
        return Result(f"{head}\n** server can't find {name}: NXDOMAIN", 1)
    lines = []
    if rtype == "A":
        status6, answers6, _ = _dns_query(key, "AAAA")
        if answers and answers[0][1] == "CNAME":
            lines.append(f"{key}\tcanonical name = {answers[0][2]}")
            key = answers[0][2].rstrip(".")
        ips = [d for _, t, d in answers if t == "A"]
        ips6 = [d for _, t, d in answers6 if t == "AAAA"]
        if not answers or not ips:
            return Result(f"{head}\n{note}".rstrip("\n") if not answers else head)
        lines.append(f"Name:\t{key}")
        lines += [f"Address: {a}" for a in ips + ips6]
    else:
        labels = {"MX": "mail exchanger = ", "NS": "nameserver = ", "TXT": "text = ", "CNAME": "canonical name = ", "AAAA": "has AAAA address "}
        if not answers:
            return Result(f"{head}\n{note}*** No {rtype} records found for {name}".replace("\n\n", "\n"))
        for owner, kind, data in answers:
            if kind == "AAAA":
                lines.append(f"{owner}\thas AAAA address {data}")
            else:
                lines.append(f"{owner}\t{labels[kind]}{data}")
    return Result(f"{head}\n{note}" + "\n".join(lines))


# ---------------------------------------------------------------- HTTP (curl / wget)
HOME_HTML = ("<!doctype html>\n<html>\n<head><title>{title}</title></head>\n<body>\n<h1>{title}</h1>\n"
             "<p>This domain is for use in documentation examples.</p>\n</body>\n</html>\n")
NOT_FOUND_HTML = "<html>\n<head><title>404 Not Found</title></head>\n<body>\n<h1>Not Found</h1>\n</body>\n</html>\n"
FORBIDDEN_HTML = "<html>\n<head><title>403 Forbidden</title></head>\n<body>\n<h1>Forbidden</h1>\n</body>\n</html>\n"
STATUS_JSON = '{"status":"ok","version":"1.4.2"}\n'
REPORT_TXT = "report: all systems nominal\nuptime: 3 days\n"
NEW_TXT = "This is the new page.\n"
REASONS = {200: "OK", 301: "Moved Permanently", 302: "Found", 403: "Forbidden", 404: "Not Found"}


def home_html(host):
    return HOME_HTML.format(title="Example Domain" if host.endswith(".com") else "Example Organization")


def _redirect_html(status):
    return (f"<html>\n<head><title>{status} {REASONS[status]}</title></head>\n<body>\n"
            f"<center><h1>{status} {REASONS[status]}</h1></center>\n</body>\n</html>\n")


def parse_url(text):
    match = re.fullmatch(r"(?:(https?)://)?([A-Za-z0-9.-]+)(?::(\d+))?(/[^?#]*)?(?:[?#].*)?", text)
    if not match:
        return None
    scheme = match.group(1) or "http"
    port = int(match.group(3)) if match.group(3) else (443 if scheme == "https" else 80)
    return {"scheme": scheme, "host": match.group(2).lower(), "port": port, "path": match.group(4) or "/"}


def _url_text(u):
    default = 443 if u["scheme"] == "https" else 80
    port = "" if u["port"] == default else f":{u['port']}"
    return f"{u['scheme']}://{u['host']}{port}{u['path']}"


def _resp(status, ctype, body, location=None):
    return {"status": status, "reason": REASONS[status], "type": ctype, "body": body, "location": location}


def request(terminal, u):
    """('ok', 応答) / ('resolve',) / ('refused',) / ('timeout',)"""
    found = resolve(terminal, u["host"])
    if found is None:
        return ("resolve", None)
    _, ip = found
    if ip == "203.0.113.99" or not _reachable(ip):
        return ("timeout", None)
    host, path, scheme = u["host"], u["path"], u["scheme"]
    if host in APP_HOSTS or ip in ("192.0.2.30",):
        if u["port"] != 8080 or scheme != "http":
            return ("refused", None)
        if path == "/health":
            return ("ok", _resp(200, "text/plain", "OK\n"))
        if path == "/":
            return ("ok", _resp(200, "text/plain", "training app v1\n"))
        return ("ok", _resp(404, "text/html", NOT_FOUND_HTML))
    if host in ("example.com", "www.example.com", "example.org"):
        if (scheme, u["port"]) not in (("http", 80), ("https", 443)):
            return ("refused", None)
        if scheme == "http" and host.endswith(".com"):
            target = _url_text({**u, "scheme": "https", "port": 443})
            return ("ok", _resp(301, "text/html", _redirect_html(301), target))
        if path == "/":
            return ("ok", _resp(200, "text/html; charset=UTF-8", home_html(host)))
        if path == "/api/status":
            return ("ok", _resp(200, "application/json", STATUS_JSON))
        if path == "/old":
            return ("ok", _resp(302, "text/html", _redirect_html(302), _url_text({**u, "path": "/new"})))
        if path == "/new":
            return ("ok", _resp(200, "text/plain; charset=UTF-8", NEW_TXT))
        if path == "/files/report.txt":
            return ("ok", _resp(200, "text/plain; charset=UTF-8", REPORT_TXT))
        if path == "/admin":
            return ("ok", _resp(403, "text/html", FORBIDDEN_HTML))
        return ("ok", _resp(404, "text/html", NOT_FOUND_HTML))
    return ("refused", None)


def _headers(u, resp):
    https = u["scheme"] == "https"
    size = len(resp["body"].encode("utf-8"))
    if https:
        lines = [f"HTTP/2 {resp['status']}", f"content-type: {resp['type']}", f"content-length: {size}",
                 "server: training-web/1.0", f"date: {HTTP_DATE}"]
        if resp["location"]:
            lines.append(f"location: {resp['location']}")
    else:
        lines = [f"HTTP/1.1 {resp['status']} {resp['reason']}", "Server: training-web/1.0", f"Date: {HTTP_DATE}",
                 f"Content-Type: {resp['type']}", f"Content-Length: {size}", "Connection: keep-alive"]
        if resp["location"]:
            lines.append(f"Location: {resp['location']}")
    return "\n".join(lines) + "\n"


def _curl_error(kind, u, timeout):
    host, port = u["host"], u["port"]
    if kind == "resolve":
        return 6, f"curl: (6) Could not resolve host: {host}"
    if kind == "refused":
        return 7, f"curl: (7) Failed to connect to {host} port {port} after 2 ms: Couldn't connect to server"
    if timeout:
        return 28, f"curl: (28) Connection timed out after {timeout}001 milliseconds"
    return 28, f"curl: (28) Failed to connect to {host} port {port} after 129985 ms: Couldn't connect to server"


def _write_local(terminal, name, text):
    target = terminal.path(name)
    if target.is_dir():
        raise_error = f"{name} はフォルダです。ファイル名を指定しましょう。"
        from engine.guided import TrainingError
        raise TrainingError(raise_error)
    target.write_text(text, encoding="utf-8")


@command("curl")
def curl(terminal, rest, stdin=None, admin=False):
    missing = _need(terminal, "curl", "curl")
    if missing:
        return missing
    opts, out_name, fmt, timeout, urls, i = set(), None, None, None, [], 0
    longs = {"--head": "I", "--silent": "s", "--location": "L", "--fail": "f", "--include": "i",
             "--show-error": "S", "--remote-name": "O"}
    while i < len(rest):
        arg = rest[i]
        if arg in longs:
            opts.add(longs[arg])
        elif arg in ("--output", "--write-out", "--max-time"):
            if i + 1 >= len(rest):
                return None
            value, i = rest[i + 1], i + 1
            if arg == "--output":
                out_name = value
            elif arg == "--write-out":
                fmt = value
            elif value.isdigit():
                timeout = int(value)
            else:
                return None
        elif arg.startswith("-") and not arg.startswith("--") and len(arg) > 1:
            j = 1
            while j < len(arg):
                ch = arg[j]
                if ch in "IisSLfO":
                    opts.add(ch)
                elif ch in "owm":
                    value = arg[j + 1:] or (rest[i + 1] if i + 1 < len(rest) else None)
                    if value is None:
                        return None
                    if not arg[j + 1:]:
                        i += 1
                    if ch == "o":
                        out_name = value
                    elif ch == "w":
                        fmt = value
                    elif value.isdigit():
                        timeout = int(value)
                    else:
                        return None
                    break
                else:
                    return None
                j += 1
        elif arg.startswith("-"):
            return None
        else:
            urls.append(arg)
        i += 1
    if len(urls) != 1:
        return None
    u = parse_url(urls[0])
    if u is None:
        return Result("curl: (3) URL rejected: Bad hostname", 3)
    silent_errors = "s" in opts and "S" not in opts
    chain, current = [], u
    for _ in range(11):
        kind, resp = request(terminal, current)
        if kind != "ok":
            code, message = _curl_error(kind, current, timeout)
            return Result("" if silent_errors else message, code)
        chain.append((current, resp))
        if "L" in opts and resp["location"]:
            current = parse_url(resp["location"])
            continue
        break
    final_url, final = chain[-1]
    if "f" in opts and final["status"] >= 400:
        text = "" if silent_errors else f"curl: (22) The requested URL returned error: {final['status']}"
        return Result(text, 22)
    shown_chain = chain if "L" in opts else chain[:1]
    pieces = []
    if "I" in opts:
        pieces.append("\n".join(_headers(x, r) for x, r in shown_chain))
        body = None
    else:
        if "i" in opts:
            pieces.append("\n".join(_headers(x, r) for x, r in shown_chain))
        body = final["body"]
    if "O" in opts and out_name is None:
        name = final_url["path"].rsplit("/", 1)[-1]
        if not name:
            return Result("curl: Remote file name has no length!", 23)
        out_name = name
    saved = ""
    if body is not None and out_name is not None:
        if out_name != "/dev/null":
            _write_local(terminal, out_name, (pieces[0] + "\n" if pieces else "") + body)
        if "s" not in opts:
            size = len(body.encode("utf-8"))
            saved = ("  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current\n"
                     "                                 Dload  Upload   Total   Spent    Left  Speed\n"
                     f"100 {size:>5}  100 {size:>5}    0     0  {size * 8:>6}      0 --:--:-- --:--:-- --:--:-- {size * 8:>6}")
        if pieces and out_name == "/dev/null":
            pieces = []
        elif pieces:
            pieces = []
        body = None
    if body is not None:
        pieces.append(body)
    text = "\n".join(p.rstrip("\n") for p in pieces if p is not None)
    if saved:
        text = saved
    if fmt is not None:
        text += (fmt.replace("%{http_code}", str(final["status"])).replace("%{url_effective}", _url_text(final_url))
                 .replace("%{redirect_url}", final["location"] or "").replace("%{size_download}", str(len(final["body"].encode())))
                 .replace("\\n", "\n"))
    return Result(text)


@command("wget")
def wget(terminal, rest, stdin=None, admin=False):
    quiet, out_name, urls, i = False, None, [], 0
    while i < len(rest):
        arg = rest[i]
        if arg == "-q":
            quiet = True
        elif arg == "-O" and i + 1 < len(rest):
            out_name, i = rest[i + 1], i + 1
        elif arg == "-qO" and i + 1 < len(rest):
            quiet, out_name, i = True, rest[i + 1], i + 1
        elif arg == "-qO-":
            quiet, out_name = True, "-"
        elif arg.startswith("-O") and len(arg) > 2:
            out_name = arg[2:]
        elif arg.startswith("-"):
            return None
        else:
            urls.append(arg)
        i += 1
    if len(urls) != 1:
        return None
    u = parse_url(urls[0])
    if u is None:
        return Result(f"{urls[0]}: Invalid URL", 1)
    log = []
    scheme_note = None
    current = u
    final = None
    for _ in range(6):
        log.append(f"--{WGET_NOW}--  {_url_text(current)}")
        kind, resp = request(terminal, current)
        host = current["host"]
        if kind == "resolve":
            log.append(f"Resolving {host} ({host})... failed: Name or service not known.")
            log.append(f"wget: unable to resolve host address ‘{host}’")
            return Result("" if quiet else "\n".join(log), 4)
        ip = resolve(terminal, host)[1]
        log.append(f"Resolving {host} ({host})... {ip}")
        log.append(f"Connecting to {host} ({host})|{ip}|:{current['port']}... " + (
            "connected." if kind == "ok" else "failed: " + ("Connection refused." if kind == "refused" else "Connection timed out.")))
        if kind != "ok":
            return Result("" if quiet else "\n".join(log), 4)
        log.append("HTTP request sent, awaiting response... " + f"{resp['status']} {resp['reason']}")
        if resp["location"] and resp["status"] in (301, 302):
            log.append(f"Location: {resp['location']} [following]")
            current = parse_url(resp["location"])
            continue
        final = resp
        break
    if final["status"] >= 400:
        log.append(f"{WGET_NOW} ERROR {final['status']}: {final['reason']}.")
        return Result("" if quiet else "\n".join(log), 8)
    body = final["body"]
    size = len(body.encode("utf-8"))
    if out_name == "-":
        return Result(body.rstrip("\n") if quiet else "\n".join(log) + "\n" + body.rstrip("\n"))
    name = out_name or (current["path"].rsplit("/", 1)[-1] or "index.html")
    if out_name is None:
        number = 0
        base = name
        while terminal.path(name).exists():
            number += 1
            name = f"{base}.{number}"
    _write_local(terminal, name, body)
    if quiet:
        return Result("")
    log += [f"Length: {size} ({size}) [{final['type'].split(';')[0]}]", f"Saving to: ‘{name}’", "",
            f"{name:<20}100%[===================>] {size:>5}  --.-KB/s    in 0s", "",
            f"{WGET_NOW} (24.1 MB/s) - ‘{name}’ saved [{size}/{size}]"]
    return Result("\n".join(log))


# ---------------------------------------------------------------- ufw
SERVICES = {"ssh": "22/tcp", "http": "80/tcp", "https": "443/tcp", "OpenSSH": "OpenSSH"}


def ufw_state(terminal):
    network = terminal.progress.setdefault("network", {})
    return network.setdefault("ufw", {"active": False, "incoming": "deny", "rules": []})


@on_check
def check_network(scenario, terminal):
    expected = scenario.get("expected_ufw")
    if expected is not None:
        state = ufw_state(terminal)
        for key, value in expected.items():
            if key == "rules":
                equal = sorted(state["rules"]) == sorted(value)
            else:
                equal = state.get(key) == value
            if not equal:
                return False, "ファイアウォールの状態・既定方針・許可する相手とポートを確認しましょう。"
    return None


@on_prepare
def _prepare(terminal, step):
    config = step.get("ufw") or {}
    terminal.progress["network"] = {"ufw": {
        "active": bool(config.get("active", False)), "incoming": config.get("incoming", "deny"),
        "rules": [list(r) for r in config.get("rules", [])]}}


def _port_spec(text):
    if text in SERVICES:
        return SERVICES[text]
    match = re.fullmatch(r"(\d{1,5})(?:/(tcp|udp))?", text)
    if match and 1 <= int(match.group(1)) <= 65535:
        return text
    return None


def _rule_from(args):
    """allow/deny の後ろを (to, from) にする。書式が違えば None、不正なら文字列（エラー文）。"""
    if len(args) == 1:
        spec = _port_spec(args[0])
        if spec is None:
            if re.fullmatch(r"\d+(/\w+)?", args[0]):
                return f"ERROR: Bad port '{args[0].split('/')[0]}'"
            return f"ERROR: Could not find a profile matching '{args[0]}'"
        return spec, "Anywhere"
    if args and args[0] == "from" and len(args) >= 2:
        try:
            ipaddress.ip_network(args[1], strict=False)
        except ValueError:
            return f"ERROR: Bad source address"
        source = args[1]
        if len(args) == 2:
            return "Anywhere", source
        if len(args) >= 6 and args[2:5] == ["to", "any", "port"] and args[5].isdigit() and 1 <= int(args[5]) <= 65535:
            port = args[5]
            if len(args) == 8 and args[6] == "proto" and args[7] in ("tcp", "udp"):
                return f"{port}/{args[7]}", source
            if len(args) == 6:
                return port, source
    return None


def _ufw_status(state, mode):
    if not state["active"]:
        return "Status: inactive"
    rows = []
    for number, (to, action, source) in enumerate(state["rules"], 1):
        v6 = source == "Anywhere"
        rows.append((to, action, source))
        if v6:
            rows.append((f"{to} (v6)", action, "Anywhere (v6)"))
    if not rows and mode == "plain":
        return "Status: active"
    lines = ["Status: active"]
    if mode == "verbose":
        lines += ["Logging: on (low)", f"Default: {state['incoming']} (incoming), allow (outgoing), disabled (routed)",
                  "New profiles: skip"]
    lines.append("")
    if not rows:
        return "\n".join(lines).rstrip("\n")
    suffix = " IN" if mode in ("verbose", "numbered") else ""
    prefix = "     " if mode == "numbered" else ""
    lines.append(prefix + "To".ljust(27) + "Action".ljust(12) + "From")
    lines.append(prefix + "--".ljust(27) + "------".ljust(12) + "----")
    for index, (to, action, source) in enumerate(rows, 1):
        tag = f"[{index:>2}] " if mode == "numbered" else ""
        lines.append(tag + to.ljust(27) + (action + suffix).ljust(12) + source)
    return "\n".join(lines)


@command("ufw", sudo=True)
def ufw(terminal, rest, stdin=None, admin=False):
    if not rest:
        return None
    if not admin:
        return Result("ERROR: You need to be root to run this script", 1)
    state = ufw_state(terminal)
    action, args = rest[0], rest[1:]
    if action == "status":
        mode = "plain"
        if args == ["verbose"]:
            mode = "verbose"
        elif args == ["numbered"]:
            mode = "numbered"
        elif args:
            return None
        return Result(_ufw_status(state, mode))
    if action == "enable" and not args:
        state["active"] = True
        return Result("Firewall is active and enabled on system startup")
    if action == "disable" and not args:
        state["active"] = False
        return Result("Firewall stopped and disabled on system startup")
    if action == "default" and len(args) == 2 and args[0] in ("allow", "deny") and args[1] == "incoming":
        state["incoming"] = args[0]
        return Result(f"Default incoming policy changed to '{args[0]}'\n(be sure to update your rules accordingly)")
    if action in ("allow", "deny") and args:
        rule = _rule_from(args)
        if rule is None:
            return None
        if isinstance(rule, str):
            return Result(rule, 1)
        entry = [rule[0], action.upper(), rule[1]]
        v6 = rule[1] == "Anywhere"
        if entry in state["rules"]:
            message = "Skipping adding existing rule" + ("\nSkipping adding existing rule (v6)" if v6 else "")
        else:
            state["rules"].append(entry)
            if state["active"]:
                message = "Rule added" + ("\nRule added (v6)" if v6 else "")
            else:
                message = "Rules updated" + ("\nRules updated (v6)" if v6 else "")
        return Result(message)
    if action == "delete" and len(args) >= 2 and args[0] in ("allow", "deny"):
        rule = _rule_from(args[1:])
        if rule is None:
            return None
        if isinstance(rule, str):
            return Result(rule, 1)
        entry = [rule[0], args[0].upper(), rule[1]]
        v6 = rule[1] == "Anywhere"
        if entry in state["rules"]:
            state["rules"].remove(entry)
            return Result("Rule deleted" + ("\nRule deleted (v6)" if v6 else ""))
        return Result("Could not delete non-existent rule" + ("\nCould not delete non-existent rule (v6)" if v6 else ""), 0)
    return None
