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

# ---- 2. the session classifier ---------------------------------------------
cls = grab("is_live_menu_session")
if cls:
    cases = [
        ("/usr/bin/nucsub menu", True, "an open main menu"),
        ("/usr/bin/env bash /usr/bin/nucsub menu", True,
         "an open menu launched through the shebang"),
        ("bash /opt/nuc-sub/cli/nucsub", True, "a bare interactive menu"),
        ("bash /opt/nuc-sub/cli/nucsub menu", True, "an open menu via bash"),
        ("/usr/bin/nucsub apply gold", False, "a one-shot apply"),
        ("/usr/bin/nucsub webpanel start", False, "a one-shot webpanel start"),
        ("", False, "an empty cmdline"),
        ("vim /opt/nuc-sub/cli/nucsub", False, "an editor holding the file"),
        ("grep -r nucsub /opt", False, "a grep that merely mentions it"),
    ]
    script = ("set -euo pipefail\n"
              "is_live_menu_session() {\n" + cls + "}\n"
              'for c in "$@"; do\n'
              '  if is_live_menu_session "$c"; then echo "Y:$c"; else echo "N:$c"; fi\n'
              "done\n")
    with tempfile.TemporaryDirectory() as d2:
        p = pathlib.Path(d2) / "cls.sh"
        p.write_text(script, "utf-8")
        args = [c for c, _, _ in cases]
        r = subprocess.run([BASH, str(p), *args], capture_output=True, text=True,
                           timeout=45)
    got = {}
    for line in r.stdout.splitlines():
        if len(line) >= 2 and line[1] == ":" and line[0] in "YN":
            got[line[2:]] = line[0] == "Y"
    for cmdline, want, why in cases:
        if not got:
            failures.append(
                "the classifier script produced no output at all "
                f"(stderr: {(r.stderr or '').strip()[:200]!r})")
            break
        if cmdline not in got:
            failures.append(f"classifier never saw {cmdline!r}")
        elif got[cmdline] != want:
            failures.append(
                f"classifier says {'menu' if got[cmdline] else 'not a menu'} for "
                f"{why}: {cmdline!r}")

# ---- 3. wiring --------------------------------------------------------------
cu = grab("cmd_update")
if "update_warn_live_sessions" not in cu:
    failures.append("cmd_update never checks for a live menu session")
elif cu.index("update_warn_live_sessions") > cu.index("update_preflight"):
    failures.append("cmd_update checks for live sessions after its preflight")

for fn in ("cmd_menu", "web_panel_menu"):
    if "self_changed" not in grab(fn):
        failures.append(f"{fn} does not re-check whether the CLI was replaced")

if "self_changed" not in src.split("cmd_menu")[0]:
    failures.append("self_changed/self_restart_notice are not defined near the top")

print("checked: menu re-exec guard (executed), session classifier (9 cmdlines), "
      "update/menu wiring")
if failures:
    print(f"\nFAIL: {len(failures)} problem(s)")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("PASS  an update can no longer swap the CLI under a running menu")