#!/usr/bin/env python3
"""
Two Pasarguard-only bugs in cli/nucsub, both reachable by a user and both
invisible on the xui installs.

1. `SETTINGS_FILE: unbound variable` killed "Start web panel".

   The CLI runs under `set -euo pipefail`, and the privilege-separation block
   that hands the panel user ownership of the shared settings store said:

       chown "$webuser":"$webuser" "$SETTINGS_FILE"

   SETTINGS_FILE is the *Python* global in webpanel/server.py. It was never
   assigned in the shell, so under `set -u` the expansion aborted the entire
   subcommand before the panel was ever started. The store is config.json,
   which the CLI already exposes as $CONFIG_FILE.

   This only fired on Pasarguard: the block is guarded by
   `if [[ "$webuser" != "root" ]]`, and the xui installs run the panel as root
   and skip it entirely. That is why it was never seen before.

2. pg_restart_panel reported failure after a successful apply.

   It recreated the container with `docker compose up -d --force-recreate`,
   then unconditionally ran `docker restart` on the container it had just
   created. That second start-up was an independent failure point: when it
   failed, or when the container lookup raced the recreate, the function
   returned 1 and every apply printed "Panel restart failed" even though the
   panel had been recreated correctly on the new .env. The extra restart was
   also pure downtime, and while the panel was flapping the served template
   lagged behind SUBSCRIPTION_PAGE_TEMPLATE -- which is exactly what makes a
   theme switch look like it was never applied.

The restart half of this is tested by behaviour, not by grepping text: the real
function is extracted from cli/nucsub and executed against stubbed docker and
systemctl commands, so it has to genuinely return 0 on a successful recreate
and genuinely avoid the redundant restart.
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile


def find_bash() -> str | None:
    """Locate a real GNU bash.

    On Windows a bare `bash` on PATH is often the WSL launcher
    (C:\\Windows\\System32\\bash.exe), which prints "Windows Subsystem for Linux
    has no installed distributions" and exits instead of running the script.
    Probe the candidates and keep the first that actually reports GNU bash.
    """
    candidates = [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        "/usr/bin/bash",
        "/bin/bash",
        shutil.which("bash") or "",
    ]
    for c in candidates:
        if not c or not os.path.exists(c):
            continue
        try:
            r = subprocess.run([c, "--version"], capture_output=True, text=True,
                               timeout=20)
        except (OSError, subprocess.SubprocessError):
            continue
        if "GNU bash" in (r.stdout or ""):
            return c
    return None


BASH = find_bash()

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLI = ROOT / "cli" / "nucsub"
src = CLI.read_text("utf-8")

failures: list[str] = []


def strip_comments(text: str) -> str:
    out = []
    for line in text.splitlines():
        # only drop whole-line comments; the CLI has no inline `#` in strings
        # that matter here
        if line.lstrip().startswith("#"):
            continue
        out.append(line)
    return "\n".join(out)


code = strip_comments(src)

# ---- 1. the settings store ---------------------------------------------------
if "SETTINGS_FILE" in code:
    failures.append(
        "cli/nucsub still expands $SETTINGS_FILE in code; that is the Python "
        "global in webpanel/server.py and is unbound in the shell")

if not re.search(r'chown\s+"\$webuser":"\$webuser"\s+"\$CONFIG_FILE"', code):
    failures.append(
        "the panel user is not given ownership of $CONFIG_FILE, so the panel "
        "cannot persist telegram/brand settings")

# it must exist before it is chowned, or chown silently does nothing
if not re.search(r"CONFIG_FILE\"\s*\]\s*\|\||\[\[.*CONFIG_FILE", code):
    failures.append(
        "$CONFIG_FILE is never created before the chown; on a fresh install the "
        "chown would silently target nothing")

# ---- 2. pg_restart_panel, tested by running it -------------------------------
m = re.search(r"^pg_restart_panel\(\) \{\n(.*?)^\}", src, re.M | re.S)
if not m:
    failures.append("could not extract pg_restart_panel from cli/nucsub")
else:
    fn_body = m.group(1)

    # the function looks for docker-compose.yml in three fixed paths; point
    # them at the sandbox so the compose branch is actually exercised
    fn_body = (fn_body.replace("/opt/pasarguard", '"$STUB_PG1"')
                        .replace("/var/lib/pasarguard", '"$STUB_PG2"')
                        .replace("/root/pasarguard", '"$STUB_PG3"'))

    harness = """
set -euo pipefail
warn() { printf 'WARN %s\\n' "$*"; }
pg_app_container() { printf '%s' "$STUB_CONTAINER"; }
systemctl() { printf 'systemctl %s\\n' "$*" >> "$STUB_LOG"; return "$STUB_SYSTEMCTL_RC"; }

# stub docker: `docker compose ...` follows STUB_COMPOSE_RC, `docker restart`
# follows STUB_RESTART_RC, and every call is logged
docker() {
  printf 'docker %s\\n' "$*" >> "$STUB_LOG"
  if [ "${1:-}" = "compose" ]; then return "$STUB_COMPOSE_RC"; fi
  if [ "${1:-}" = "restart" ]; then return "$STUB_RESTART_RC"; fi
  return 0
}

__FN__

pg_restart_panel
printf 'RC=%s\\n' "$?"
"""
    # group(1) is the body only; put the signature back so `local` is legal
    harness = harness.replace("__FN__", "pg_restart_panel() {\n" + fn_body + "\n}")

    def run(compose_rc, restart_rc, systemctl_rc=0, container="pg-app"):
        with tempfile.TemporaryDirectory() as d:
            sandbox = pathlib.Path(d)
            for sub in ("pg1", "pg2", "pg3"):
                (sandbox / sub).mkdir()
            # only pg1 has a compose file, so the search stops there
            (sandbox / "pg1" / "docker-compose.yml").write_text("services: {}\n")
            log = sandbox / "calls.log"
            env = dict(os.environ)
            env.update({
                "STUB_LOG": str(log),
                "STUB_PG1": str(sandbox / "pg1"),
                "STUB_PG2": str(sandbox / "pg2"),
                "STUB_PG3": str(sandbox / "pg3"),
                "STUB_COMPOSE_RC": str(compose_rc),
                "STUB_RESTART_RC": str(restart_rc),
                "STUB_SYSTEMCTL_RC": str(systemctl_rc),
                "STUB_CONTAINER": container,
            })
            r = subprocess.run([BASH, "-c", harness], capture_output=True,
                               text=True, env=env, cwd=str(sandbox))
            r.log = log.read_text() if log.exists() else ""
            return r

    if BASH is None:
        print("SKIP  no GNU bash found; cannot exercise pg_restart_panel")
        sys.exit(0)

    # a) compose recreate works -> success, and no redundant docker restart
    r = run(compose_rc=0, restart_rc=1)
    calls = r.stdout + r.stderr
    if "RC=0" not in calls:
        failures.append(
            "pg_restart_panel does not report success after a successful "
            f"compose recreate (got {calls.strip()[:200]!r})")
    if "docker restart" in r.log:
        failures.append(
            "pg_restart_panel still runs `docker restart` after a successful "
            "recreate; that redundant restart is the false-failure source")

    # b) compose works and a restart would also have worked: still success,
    #    and the redundant restart must still not happen
    r = run(compose_rc=0, restart_rc=0)
    calls = r.stdout + r.stderr
    if "RC=0" not in calls:
        failures.append("pg_restart_panel regressed on the plain success path")
    if "docker restart" in r.log:
        failures.append("redundant `docker restart` reappeared")

    # c) compose genuinely fails -> must report failure and surface the error
    r = run(compose_rc=1, restart_rc=0)
    calls = r.stdout + r.stderr
    if "RC=0" in calls:
        failures.append(
            "pg_restart_panel reports success even though `docker compose up` "
            "failed; a broken panel .env would be swallowed again")
    if "docker compose up failed" not in calls:
        failures.append(
            "pg_restart_panel no longer surfaces the compose error message")

print(f"checked {CLI.relative_to(ROOT)}; ran pg_restart_panel against stubbed "
      f"docker/systemctl in 3 scenarios")

if failures:
    print(f"\nFAIL: {len(failures)} problem(s)")
    for f in failures:
        print("  -", f)
    sys.exit(1)

print("PASS  web panel can start under set -u; restart reports the truth")