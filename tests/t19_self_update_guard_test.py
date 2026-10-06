#!/usr/bin/env python3
"""
Guard against `nucsub update` replacing the CLI underneath a running menu.

bash reads a script lazily, by byte offset. A shell that started against the old
cli/nucsub keeps reading at the OLD offsets out of the NEW file, so it executes a
mix of the two versions and fails on lines that no longer say what they used to.
This is not hypothetical: after the SETTINGS_FILE fix shipped in v2.2.6, a menu
that had been open across the update kept reporting

    line 1331: SETTINGS_FILE: unbound variable

even though line 1331 of the new file is a `useradd` call and SETTINGS_FILE
appears only inside comments. v2.2.5 line 1331 was exactly the buggy chown.

Two defences, both checked here:

  * the menu re-fingerprints its own script on every pass and re-execs when it
    changed, so an already-open session recovers instead of limping on;
  * `nucsub update` refuses to run while another menu session is live, so the
    file is never swapped in the first place.

The menu half is exercised for real: a script appends to itself mid-run to
simulate the update landing, and must be re-executed. The session-classifier
half is exercised against real cmdlines.
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
    # tolerate a trailing comment on the signature line
    m = re.search(rf"^{name}\(\) \{{\s*(?:#[^\n]*)?\n(.*?)^\}}", src, re.M | re.S)
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

# ---- 1. the menu self-restart guard, for real -------------------------------
if BASH is None:
    print("SKIP  no GNU bash found")
    sys.exit(0)

BODY = r'''
set -euo pipefail
NUC_SUB_SELF_SHA="$(sha256sum "$0" | cut -d" " -f1)"
self_changed() {
  local f="$0" now
  [[ -z "$NUC_SUB_SELF_SHA" || ! -f "$f" ]] && return 1
  now="$(sha256sum "$f" | cut -d" " -f1)"
  [[ -n "$now" && "$now" != "$NUC_SUB_SELF_SHA" ]]
}
self_restart_notice() { echo GUARD_RESTART; exec "$0" "$@"; }
# simulate `nucsub update` landing mid-session, exactly once -- otherwise the
# re-exec would keep changing the file and loop forever
if [[ ! -f "$0.updated" ]]; then
  printf 'SIMULATED_UPDATE' >> "$0"
  : > "$0.updated"
fi
n=0
while true; do
  n=$((n+1))
  self_changed && self_restart_notice
  [[ $n -ge 2 ]] && { echo "RESTARTED_RUN_IS_CURRENT"; break; }
done
'''

with tempfile.TemporaryDirectory() as d:
    f = pathlib.Path(d) / "nucsub"
    f.write_text(BODY, "utf-8")
    try:
        r = subprocess.run([BASH, str(f)], capture_output=True, text=True,
                           timeout=45)
        out = r.stdout
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode("utf-8", "replace") if isinstance(
            e.stdout, bytes) else (e.stdout or "")
        failures.append(
            "the menu guard did not re-exec after the CLI changed underneath it "
            f"(it hung instead; output: {out.strip()[:120]!r})")
        out = ""
    if "GUARD_RESTART" not in out:
        failures.append(
            "the menu guard did not re-exec after the CLI changed underneath it "
            f"(output: {out.strip()[:120]!r})")
    if "RESTARTED_RUN_IS_CURRENT" not in out:
        failures.append(
            "after re-exec the menu still does not consider itself current "
            f"(output: {out.strip()[:120]!r})")

# ---- 2. the session registry, for real ---------------------------------------
# The live-session check must be a fact, not a guess. It used to be a pgrep +
# /proc/cmdline classifier, and that was wrong in both directions: it let an
# update through while a menu was open, and it blocked updates when no menu was
# open at all -- silently, with nothing but exit status 1. So the test below
# runs the registry for real, against real pids, including a pid that is alive
# but whose recorded starttime does not match, and an entry for a pid that does
# not exist at all.
#
# This needs a working /proc/<pid>/stat. Git Bash emulates /proc for its own
# processes only, so field 22 is not readable for an unrelated pid and every
# negative case here would pass for the wrong reason. Rather than report a
# green that means nothing, the section says it was skipped.
FUNCS = {n: grab(n) for n in ("proc_starttime", "menu_session_register",
                              "menu_session_unregister", "menu_live_session_pids")}
REGISTERED = False
if not all(FUNCS.values()):
    failures.append(
        "could not extract the session-registry functions from cli/nucsub")
else:
    probe = ("set -euo pipefail\n"
             + "proc_starttime() {\n" + FUNCS["proc_starttime"] + "\n}\n"
             + 'st="$(proc_starttime $PPID 2>/dev/null || true)"\n'
             + '[[ "$st" =~ ^[0-9]+$ ]] && echo "USABLE:$st"\n')
    with tempfile.TemporaryDirectory() as d0:
        p0 = pathlib.Path(d0) / "probe.sh"
        p0.write_text(probe, "utf-8")
        r0 = subprocess.run([BASH, str(p0)], capture_output=True, text=True,
                            timeout=45)
    if "USABLE:" not in r0.stdout:
        print("SKIP  session-registry checks: /proc/<other-pid>/stat is not "
              "readable here, so the pid-reuse cases cannot be observed")
        print("      (Git Bash exposes /proc for its own process only)")
        REGISTERED = False
    else:
        REGISTERED = True

if REGISTERED:
    REG = ("set -euo pipefail\n"
           "MENU_SESSION_DIR=\"$1\"\n"
           "CYAN=''; DIM=''; NC=''\n"
           "warn() { echo WARN; }\n"
           + "".join(f"{n}() {{\n{b}\n}}\n" for n, b in FUNCS.items())
           + 'echo "self: $$"\n'
             'echo "registered: [$(menu_live_session_pids)]"\n')
    with tempfile.TemporaryDirectory() as d2:
        sleeper = pathlib.Path(d2) / "sleeper.sh"
        sleeper.write_text("sleep 30\n", "utf-8")
        holder = subprocess.Popen([BASH, str(sleeper)],
                                  stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL)
        sessions = pathlib.Path(d2) / "sessions"

        def run(script: str) -> tuple[int, str, str]:
            p = pathlib.Path(d2) / "reg.sh"
            p.write_text(script, "utf-8")
            r = subprocess.run([BASH, str(p), str(sessions)],
                               capture_output=True, text=True, timeout=45)
            return r.returncode, r.stdout, r.stderr

        def field(out: str, name: str) -> str | None:
            for line in out.splitlines():
                if line.startswith(name + ":"):
                    return line.split(":", 1)[1].strip()
            return None

        try:
            # 2a. nothing registered -> no live sessions, update may proceed
            rc, out, err = run(REG)
            if field(out, "registered") != "[]":
                failures.append(
                    "an empty registry is not reported as empty: "
                    f"{out.strip()[:160]!r} (stderr {err.strip()[:120]!r})")

            # 2b. a real registration -> that exact pid comes back
            rc, out, err = run(REG + "menu_session_register\n"
                                     'echo "after: [$(menu_live_session_pids)]"\n')
            me = field(out, "self")
            if field(out, "after") != f"[{me}]":
                failures.append(
                    "a menu session that registered itself is not reported as "
                    f"live: {out.strip()[:200]!r}")

            # 2c. alive, but the recorded starttime is not this process's --
            #     exactly the recycled-pid case, and exactly what the old
            #     pgrep classifier could not tell apart
            sessions.mkdir(parents=True, exist_ok=True)
            (sessions / str(holder.pid)).write_text(
                f"{holder.pid} 123456\n", "utf-8")
            rc, out, err = run(REG)
            if field(out, "registered") != "[]":
                failures.append(
                    "a registry entry whose starttime does not match was "
                    f"accepted as a live menu: {out.strip()[:200]!r}")
            if (sessions / str(holder.pid)).exists():
                failures.append(
                    "a stale registry entry is not cleaned up, so it can only "
                    "accumulate")

            # 2d. an entry for a pid that does not exist at all
            (sessions / "999999").write_text("999999 424242\n", "utf-8")
            rc, out, err = run(REG)
            if field(out, "registered") != "[]":
                failures.append(
                    "a registry entry for a dead pid is reported as live: "
                    f"{out.strip()[:200]!r}")
            if (sessions / "999999").exists():
                failures.append("an entry for a dead pid is not cleaned up")

            # 2e. unregister really removes the entry
            rc, out, err = run(REG + "menu_session_register\n"
                                     "menu_session_unregister\n"
                                     'echo "after: [$(menu_live_session_pids)]"\n')
            if field(out, "after") != "[]":
                failures.append(
                    "menu_session_unregister does not remove the session: "
                    f"{out.strip()[:200]!r}")
        finally:
            holder.kill()
            holder.wait(timeout=20)

# ---- 3. wiring --------------------------------------------------------------
cu = grab("cmd_update")
if "update_warn_live_sessions" not in cu:
    failures.append("cmd_update never checks for a live menu session")
elif cu.index("update_warn_live_sessions") > cu.index("update_preflight"):
    failures.append("cmd_update checks for live sessions after its preflight")
elif "&& return 1" in cu.split("update_warn_live_sessions")[1].split("\n")[0]:
    # `guard && return 1` aborted the update on the server with a bare exit
    # status 1 and no message, on runs where the guard had reported no live
    # session. The condition may be written any number of ways; this one is not
    # one of them.
    failures.append(
        "cmd_update aborts with the short-circuit && form, which is the form "
        "that failed silently on the server")

for fn in ("cmd_menu", "web_panel_menu"):
    if "self_changed" not in grab(fn):
        failures.append(f"{fn} does not re-check whether the CLI was replaced")

# a session that never registers itself cannot be protected by anything
cm = grab("cmd_menu")
if "menu_session_register" not in cm:
    failures.append(
        "cmd_menu never registers the session, so `nucsub update` cannot know "
        "it is open")
elif "menu_session_unregister" not in cm:
    failures.append(
        "cmd_menu registers a session but never unregisters it, so the "
        "registry only ever grows")
elif "EXIT" not in cm:
    failures.append(
        "cmd_menu unregisters without an EXIT trap, so quitting the menu with "
        "q still leaves the session registered")
elif cm.index("menu_session_register") > cm.index("self_changed"):
    failures.append(
        "cmd_menu registers its session only after the self-change check, so "
        "the re-exec path re-registers as a new process (fine) but the very "
        "first entry is not announced until later than it should be")

if "self_changed" not in src.split("cmd_menu")[0]:
    failures.append("self_changed/self_restart_notice are not defined near the top")

for fn in ("proc_starttime", "menu_session_register", "menu_session_unregister",
           "menu_live_session_pids"):
    if f"{fn}() {{" not in src:
        failures.append(f"{fn} is referenced but never defined")

print("checked: menu re-exec guard (executed), session registry "
      f"({'real pids' if REGISTERED else 'skipped, no /proc starttime here'}), "
      "update/menu wiring")
if failures:
    print(f"\nFAIL: {len(failures)} problem(s)")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("PASS  an update can no longer swap the CLI under a running menu")