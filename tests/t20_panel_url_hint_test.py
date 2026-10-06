#!/usr/bin/env python3
"""
The web panel binds loopback by default, so the only way in is an SSH tunnel.
The tool used to print a literal `<this-server>` placeholder in that command,
which is useless to copy and reads as a broken URL.

Checked here:

  * web_panel_ssh_target resolves a real user@host for every input shape:
    an SSH session, a console login, a NAT box with an internal interface
    address, an IPv6-only host, and a host with no hostname at all;
  * it must never print a loopback address, and never `<this-server>`;
  * the loopback and 0.0.0.0 print branches must both be coherent, and the
    loopback branch must hand the operator a command that actually works.
"""
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLI = ROOT / "cli" / "nucsub"
src = CLI.read_text("utf-8")

failures: list[str] = []


def grab(name: str) -> str:
    m = re.search(rf"^{name}\(\) \{{\n(.*?)^\}}", src, re.M | re.S)
    if not m:
        failures.append(f"could not extract {name} from cli/nucsub")
        return ""
    return m.group(1)


def find_bash() -> str | None:
    import shutil
    for c in (r"C:\Program Files\Git\bin\bash.exe",
              r"C:\Program Files\Git\usr\bin\bash.exe",
              "/usr/bin/bash", "/bin/bash", shutil.which("bash") or ""):
        if c and os.path.exists(c):
            try:
                r = subprocess.run([c, "--version"], capture_output=True,
                                   text=True, timeout=20)
            except (OSError, subprocess.SubprocessError):
                continue
            if "GNU bash" in (r.stdout or ""):
                return c
    return None


BASH = find_bash()
if BASH is None:
    print("SKIP  no GNU bash found")
    sys.exit(0)

body = grab("web_panel_ssh_target")

# ---- 1. resolution per input shape -----------------------------------------
# stub the probes so the test does not depend on this machine's network
stub = r'''
set -euo pipefail
curl() { [[ "${STUB_CURL:-}" == "ok" ]] && { cat /dev/null; printf '%s' "${STUB_IP:-}"; return 0; } || return 1; }
hostname() { if [[ "${1:-}" == "-I" ]]; then printf '%s' "${STUB_IFADDRS:-}"; else printf '%s' "${STUB_HOSTNAME:-no-name-host}"; fi; }
'''
cases = [
    # name, env, expected
    ("an SSH session uses the address they connected to",
     {"SSH_CONNECTION": "5.114.116.150 29803 169.40.32.93 22", "USER": "root"},
     "root@169.40.32.93"),
    ("a sudo'd session keeps the operator's own user",
     {"SSH_CONNECTION": "5.114.116.150 1 10.0.0.5 22", "SUDO_USER": "operator",
      "USER": "root"},
     "operator@10.0.0.5"),
    ("a console login falls back to the public IP",
     {"STUB_CURL": "ok", "STUB_IP": "203.0.113.9", "USER": "ubuntu"},
     "ubuntu@203.0.113.9"),
    ("a NAT box does not advertise its internal address",
     {"STUB_CURL": "fail", "STUB_IFADDRS": "127.0.0.1 10.0.0.7 172.17.0.1 ",
      "USER": "root"},
     "root@10.0.0.7"),
    ("stray whitespace cannot hide an address",
     {"STUB_CURL": "fail", "STUB_IFADDRS": "127.0.0.1 \n  10.0.0.9 \n",
      "USER": "root"},
     "root@10.0.0.9"),
    ("IPv6-only interfaces are skipped, not printed as the target",
     {"STUB_CURL": "fail", "STUB_IFADDRS": "127.0.0.1 fe80::1 ",
      "USER": "root"},
     "root@no-name-host"),
    ("a public-IP probe answering with loopback is discarded, not printed",
     {"STUB_CURL": "ok", "STUB_IP": "127.0.0.1", "STUB_IFADDRS": "10.0.0.5 ",
      "USER": "root"},
     "root@10.0.0.5"),
    ("a host with no reachable address still yields something usable",
     {"STUB_CURL": "fail", "STUB_IFADDRS": "", "STUB_HOSTNAME": "mybox",
      "USER": "root"},
     "root@mybox"),
]

with tempfile.TemporaryDirectory() as d:
    p = pathlib.Path(d) / "t.sh"
    script = (stub + "\nweb_panel_ssh_target() {\n" + body + "}\n"
              'printf "%s" "$(web_panel_ssh_target)"\n')
    p.write_text(script, "utf-8")

    for why, env, want in cases:
        e = {"PATH": os.environ.get("PATH", ""), "USER": "root"}
        e.update(env)
        if e.get("STUB_IFADDRS", "") == "":
            e.pop("STUB_IFADDRS", None)
        r = subprocess.run([BASH, str(p)], capture_output=True, text=True,
                           timeout=45, env=e)
        got = r.stdout.strip()
        if got != want:
            failures.append(
                f"{why}: got {got!r}, want {want!r}"
                + (f" (stderr {(r.stderr or '').strip()[:100]!r})" if r.stderr else ""))

    # never print a loopback address or a placeholder
    e = {"PATH": os.environ.get("PATH", ""), "USER": "root",
         "STUB_CURL": "ok", "STUB_IP": "127.0.0.1"}
    r = subprocess.run([BASH, str(p)], capture_output=True, text=True,
                       timeout=45, env=e)
    got = r.stdout.strip()
    if "127.0.0.1" in got:
        failures.append(f"offered a loopback address as the ssh target: {got!r}")
    printed = "\n".join(
        ln for ln in src.splitlines() if "<this-server>" not in ln
        or not ln.lstrip().startswith("#"))
    if "<this-server>" in printed:
        failures.append("cli/nucsub still prints the <this-server> placeholder")

# ---- 2. the printed command must be well formed ----------------------------
m = re.search(r'ssh -N -L \$port:127\.0\.0\.1:\$port \$target', src)
if not m:
    failures.append("the loopback branch does not print a filled-in tunnel command")
if "-N" not in src:
    failures.append("the tunnel command does not use -N, so it blocks the terminal")

# both bind branches must be handled
if 'NUC_SUB_WEB_HOST:-127.0.0.1}" == "0.0.0.0"' not in src:
    failures.append("the public-bind branch is gone; 0.0.0.0 would print a loopback URL")

# ---- 3. the command the tool prints must actually work ---------------------
# `ssh -G` parses the arguments and dumps the effective config without
# connecting, so this validates the -L form without needing a live sshd.
probe = ('ssh -G -N -L 18443:127.0.0.1:8080 root@example.invalid '
         '2>/dev/null | grep -i "^localforward" || true')
r = subprocess.run([BASH, "-c", probe], capture_output=True, text=True, timeout=45)
fwd = r.stdout.strip().lower()
if "18443" not in fwd or "8080" not in fwd:
    failures.append(
        f"the printed tunnel form is not a valid ssh -L forward: {fwd[:160]!r}")

# ---- 4. re-running start must still show the access info --------------------
# Menu option 1 is "install + run + show URL/token", so running it when the
# panel is already up is how an operator asks for that info again. It used to
# print only "Already running." and return.
access = grab("web_panel_print_access")
cu = grab("cmd_webpanel")

already = cu.split("Already running.", 1)
if len(already) < 2:
    failures.append("the already-running branch is gone")
else:
    # bound the branch to the closing `fi` of that one-line if, not to the next
    # `;;` -- the rest of the start path also prints the access block, so a
    # looser boundary would make this assertion unfalsifiable
    branch = already[1].split("\n            fi", 1)[0]
    if "web_panel_print_access" not in branch:
        failures.append(
            "re-running `webpanel start` on a live panel does not show the "
            "URL/token/tunnel any more")
    if not re.search(r"\breturn\b", branch):
        failures.append("the already-running branch no longer returns early")

if access:
    with tempfile.TemporaryDirectory() as d2:
        (pathlib.Path(d2) / ".webport").write_text("9191\n", "utf-8")
        (pathlib.Path(d2) / ".token").write_text("s3cr3tpanelTOKEN123\n", "utf-8")
        script = (
            "set -euo pipefail\n"
            "CYAN=''; DIM=''; BOLD=''; YELLOW=''; NC=''\n"
            "WEB_PORT_FILE='DIR/.webport'\n"
            "WEB_TOKEN_FILE='DIR/.token'\n"
            "web_panel_ssh_target() { printf 'root@198.51.100.4'; }\n"
            "web_panel_host() { printf '198.51.100.4'; }\n"
            "web_panel_print_access() {\n" + access + "}\n"
            'web_panel_print_access\n').replace("DIR", d2)
        p2 = pathlib.Path(d2) / "acc.sh"
        p2.write_text(script, "utf-8")
        env = {"PATH": os.environ.get("PATH", ""), "USER": "root",
               "SSH_CONNECTION": "5.114.116.150 1 198.51.100.4 22"}
        r2 = subprocess.run([BASH, str(p2)], capture_output=True, text=True,
                            timeout=45, env=env)
        out2 = r2.stdout
        if "9191" not in out2:
            failures.append(
                f"the printed access block ignores the real port file: {out2[:200]!r}")
        if "s3cr3tpanelTOKEN123" not in out2:
            failures.append("the printed access block does not show the token")
        if "-L 9191:127.0.0.1:9191 root@198.51.100.4" not in out2:
            failures.append(
                "the printed access block does not show a usable tunnel for the "
                f"actual port: {out2[:200]!r}")

print(f"checked: {len(cases)} ssh-target shapes, placeholder removed, "
      "tunnel command accepted by ssh, re-running start still shows access")
if failures:
    print(f"\nFAIL: {len(failures)} problem(s)")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("PASS  the operator gets a copy-pasteable tunnel to the real address")