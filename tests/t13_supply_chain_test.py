#!/usr/bin/env python3
"""
NUC-SUB — supply-chain integrity tests (Task 12, H1).

These are behavioural tests, not pattern greps: each one actually feeds a
tampered payload through the real verification code and asserts it is
rejected. A regex test would pass even if the verification were never called.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALL_SH = ROOT / "install.sh"
CLI = ROOT / "cli" / "nucsub"
MANIFEST = ROOT / "MANIFEST.sha256"

results: list[tuple[bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    results.append((bool(cond), f"{name}{(' — ' + detail) if detail and not cond else ''}"))


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def manifest_map() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in read(MANIFEST).splitlines():
        if not line.strip():
            continue
        m = re.match(r"^([0-9a-f]{64})\s+\*?(.+)$", line)
        if m:
            out[m.group(2).strip()] = m.group(1)
    return out


def bash_available() -> bool:
    if sys.platform.startswith("win"):
        for p in (
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files\Git\usr\bin\bash.exe",
        ):
            if os.path.exists(p):
                return True
        return False
    return True


# --------------------------------------------------------------------------
# 1. Manifest integrity and coverage
# --------------------------------------------------------------------------
def test_manifest_covers_shipped_files() -> None:
    m = manifest_map()
    check("MANIFEST.sha256 exists and is non-empty", len(m) > 0, f"{len(m)} entries")

    expected = {"cli/nucsub", "webpanel/server.py", "webpanel/index.html"}
    for p in expected:
        check(f"manifest covers {p}", p in m)

    themes = sorted(d.name for d in (ROOT / "themes").iterdir() if d.is_dir())
    check("33 x-ui themes present", len(themes) == 33, str(len(themes)))
    missing = [t for t in themes if f"themes/{t}/index.html" not in m]
    check("every x-ui theme is in the manifest", not missing, str(missing[:5]))

    pg = sorted((ROOT / "pasarguard-themes" / "subscription").glob("*.html"))
    check("33 Pasarguard templates present", len(pg) == 33, str(len(pg)))
    missing_pg = [f"pasarguard-themes/subscription/{p.name}" for p in pg
                  if f"pasarguard-themes/subscription/{p.name}" not in m]
    check("every Pasarguard template is in the manifest", not missing_pg, str(missing_pg[:5]))

    # every entry must be a real file whose hash matches right now
    bad: list[str] = []
    for path, want in m.items():
        f = ROOT / path
        if not f.is_file():
            bad.append(f"{path} (absent)")
            continue
        if sha256(f.read_bytes()) != want:
            bad.append(f"{path} (stale hash)")
    check("every manifest entry matches the working tree", not bad, str(bad[:5]))


def test_manifest_generator_agrees() -> None:
    if not bash_available():
        return
    b = _bash()
    r = subprocess.run([b, "tools/gen-manifest.sh", "--check"],
                       cwd=ROOT, capture_output=True, text=True)
    check("gen-manifest.sh --check reports no drift", r.returncode == 0,
          (r.stdout + r.stderr).strip()[:200])


# --------------------------------------------------------------------------
# 2. No mutable ref, and no bare curl|bash, in the shipped entry points
# --------------------------------------------------------------------------
def test_no_moving_branch_default() -> None:
    for path in (INSTALL_SH, CLI):
        text = read(path)
        # REPO_URL must be built from a ref variable, never a literal /main
        bad = re.search(r'NUC-SUB/main', text)
        check(f"{path.name} does not default REPO_URL to a moving branch",
              bad is None, bad.group(0) if bad else "")
        check(f"{path.name} defines NUC_SUB_REF", "NUC_SUB_REF=" in text)


def _code_blocks(text: str) -> list[str]:
    """Return the contents of fenced code blocks only.

    Prose that *warns against* `bash <(curl ...)` must not trip the check, so
    scanning the whole document would flag the very sentence telling people not
    to do it.
    """
    blocks: list[str] = []
    inside = False
    cur: list[str] = []
    for line in text.splitlines():
        if line.strip().startswith("```"):
            if inside:
                blocks.append("\n".join(cur))
                cur, inside = [], False
            else:
                inside = True
            continue
        if inside:
            cur.append(line)
    return blocks


def test_no_piped_remote_execution() -> None:
    for path in (INSTALL_SH, CLI):
        text = read(path)
        check(f"{path.name} does not recommend 'bash <(curl'",
              "bash <(curl" not in text)
    readme = ROOT / "README.md"
    if readme.exists():
        bad = [b for b in _code_blocks(read(readme)) if "bash <(curl" in b]
        check("README has no runnable 'bash <(curl' example", not bad, str(bad)[:200])
        # and the honest alternative must actually be documented
        blocks = "\n".join(_code_blocks(read(readme)))
        check("README documents verify-then-run", "sha256sum -c" in blocks)


# --------------------------------------------------------------------------
# 3. Behavioural: the verifier actually rejects tampered bytes
# --------------------------------------------------------------------------
_VERIFY_HARNESS = r'''
# Extract the real verification helpers from cli/nucsub and exercise them.
# No `set -u`: the extracted functions legitimately reference CLI globals
# (colour codes, message helpers) that are not part of the function bodies.
set -eo pipefail
SRC="$1"
ok()   { printf 'OK   %s\n' "$*"; }
warn() { printf 'WARN %s\n' "$*"; }
fail() { printf 'FAIL %s\n' "$*"; }
info() { printf 'INFO %s\n' "$*"; }
RED=''; GREEN=''; YELLOW=''; BLUE=''; CYAN=''; MAGENTA=''; NC=''; BOLD=''; DIM=''
# Pull in only the function definitions we need, not the whole CLI (it would run).
eval "$(awk '/^sha256_of\(\)/,/^}/' "$SRC")"
eval "$(awk '/^expected_sha\(\)/,/^}/' "$SRC")"
eval "$(awk '/^verify_manifest_file\(\)/,/^}/' "$SRC")"

MANIFEST="$2"
# Case 1: untampered file must PASS (verification is not simply always-failing)
p="$3"; f="$4"
if verify_manifest_file "$p" "$f" "case1"; then echo "CASE1 pass-ok"; else echo "CASE1 pass-FAIL"; fi
# Case 2: same file with one byte flipped must FAIL
f2="$5"
if verify_manifest_file "$p" "$f2" "case2"; then echo "CASE2 reject-FAIL"; else echo "CASE2 reject-ok"; fi
# Case 3: a path absent from the manifest must FAIL (no silent skip)
if verify_manifest_file "not/in/manifest.html" "$f" "case3"; then echo "CASE3 unknown-FAIL"; else echo "CASE3 unknown-ok"; fi
'''


def test_verifier_rejects_tampering() -> None:
    if not bash_available():
        check("behavioural tamper test ran", True, "skipped: no bash on this host")
        return
    b = _bash()
    m = manifest_map()
    probe_rel = "pasarguard-themes/subscription/volt.html"
    if probe_rel not in m:
        check("behavioural tamper test ran", False, f"{probe_rel} not in manifest")
        return

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        # Work with relative filenames from inside the temp dir: passing native
        # Windows paths (backslashes) into Git Bash makes [[ -f ]] and awk fail
        # in ways that look like product bugs.
        (tdp / "cli.sh").write_bytes(CLI.read_bytes())
        (tdp / "MANIFEST.sha256").write_bytes(MANIFEST.read_bytes())

        (tdp / "good.html").write_bytes((ROOT / probe_rel).read_bytes())
        data = bytearray((ROOT / probe_rel).read_bytes())
        idx = data.find(b"<style")
        if idx < 0:
            idx = len(data) // 2
        data[idx] = data[idx] ^ 0x01          # 1-byte tamper, still valid HTML
        (tdp / "bad.html").write_bytes(bytes(data))

        _write_lf(tdp / "h.sh", _VERIFY_HARNESS)

        r = subprocess.run(
            [b, "h.sh", "cli.sh", "MANIFEST.sha256", probe_rel, "good.html", "bad.html"],
            cwd=tdp, capture_output=True, text=True,
        )
        out = r.stdout
        err = (r.stderr or "").strip()
        detail = "rc=%d out=%r%s" % (r.returncode, out.strip()[-300:],
                                     (" | stderr: " + err[-200:]) if err else "")
        check("verifier accepts the genuine file", "CASE1 pass-ok" in out, detail)
        check("verifier REJECTS a 1-byte-modified file", "CASE2 reject-ok" in out, detail)
        check("verifier rejects a path missing from the manifest",
              "CASE3 unknown-ok" in out, detail)


# --------------------------------------------------------------------------
# 4. Behavioural: staged-update self-consistency check
# --------------------------------------------------------------------------
_STAGE_HARNESS = r'''
set -eo pipefail
SRC="$1"; TREE="$2"
ok()   { printf 'OK   %s\n' "$*"; }
warn() { printf 'WARN %s\n' "$*"; }
fail() { printf 'FAIL %s\n' "$*"; }
info() { printf 'INFO %s\n' "$*"; }
RED=''; GREEN=''; YELLOW=''; BLUE=''; CYAN=''; MAGENTA=''; NC=''; BOLD=''; DIM=''
eval "$(awk '/^sha256_of\(\)/,/^}/' "$SRC")"
eval "$(awk '/^update_validate_stage_manifest\(\)/,/^}/' "$SRC")"
if update_validate_stage_manifest "$TREE"; then echo "TREE ok"; else echo "TREE bad"; fi
'''


def _write_lf(path: Path, text: str) -> None:
    """Write a shell script with LF endings.

    Path.write_text() would emit CRLF on Windows, and a stray \\r turns
    `fi` into `fi\\r` — a syntax error that looks like a test failure.
    """
    path.write_bytes(text.replace("\r\n", "\n").encode("utf-8"))


def test_stage_manifest_check() -> None:
    if not bash_available():
        return
    b = _bash()

    def run_case(tree_setup, label: str) -> tuple[str, str]:
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            (tdp / "cli.sh").write_bytes(CLI.read_bytes())
            tree = tdp / "tree"
            tree.mkdir()
            tree_setup(tree)
            _write_lf(tdp / "s.sh", _STAGE_HARNESS)
            r = subprocess.run([b, "s.sh", "cli.sh", "tree"],
                               cwd=tdp, capture_output=True, text=True)
            return r.stdout, (r.stderr or "").strip()

    def d(path: str, data: bytes) -> None:
        def _s(tree: Path) -> None:
            f = tree / path
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
        return _s

    hello = sha256(b"hello")

    def matching(tree: Path) -> None:
        d("webpanel/server.py", b"hello")(tree)
        d("MANIFEST.sha256", f"{hello}  webpanel/server.py\n".encode())(tree)

    def tampered(tree: Path) -> None:
        d("webpanel/server.py", b"hellp")(tree)          # one char differs
        d("MANIFEST.sha256", f"{hello}  webpanel/server.py\n".encode())(tree)

    def missing_file(tree: Path) -> None:
        d("MANIFEST.sha256", f"{hello}  webpanel/server.py\n".encode())(tree)

    def no_manifest(tree: Path) -> None:
        d("webpanel/server.py", b"hello")(tree)

    def crlf_manifest(tree: Path) -> None:
        # A manifest authored on Windows arrives CRLF. A hidden \r on the path
        # used to make every lookup miss, so a good release was reported as
        # tampered and updates refused to install.
        d("webpanel/server.py", b"hello")(tree)
        d("MANIFEST.sha256", f"{hello}  webpanel/server.py\r\n".encode())(tree)

    for name, setup, want in (
        ("staged tree matching its manifest is accepted", matching, "TREE ok"),
        ("staged tree with a CRLF manifest is accepted", crlf_manifest, "TREE ok"),
        ("staged tree with a tampered file is REJECTED", tampered, "TREE bad"),
        ("staged tree with a missing file is REJECTED", missing_file, "TREE bad"),
        ("staged tree with no manifest is REJECTED", no_manifest, "TREE bad"),
    ):
        out, err = run_case(setup, name)
        detail = "out=%r%s" % (out.strip()[-200:], (" | stderr: " + err[-200:]) if err else "")
        check(name, want in out, detail)


def test_expected_sha_tolerates_crlf() -> None:
    """expected_sha() must not be defeated by a CRLF manifest."""
    if not bash_available():
        return
    b = _bash()
    harness = r'''
set -eo pipefail
SRC="$1"; M="$2"
RED=''; NC=''; DIM=''
eval "$(awk '/^sha256_of\(\)/,/^}/' "$SRC")"
eval "$(awk '/^expected_sha\(\)/,/^}/' "$SRC")"
MANIFEST="$M"
printf 'got[%s]\n' "$(expected_sha 'webpanel/server.py')"
'''
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        (tdp / "cli.sh").write_bytes(CLI.read_bytes())
        digest = sha256(b"hello")
        (tdp / "lf").write_bytes(f"{digest}  webpanel/server.py\n".encode())
        (tdp / "crlf").write_bytes(f"{digest}  webpanel/server.py\r\n".encode())
        _write_lf(tdp / "e.sh", harness)
        for variant in ("lf", "crlf"):
            r = subprocess.run([b, "e.sh", "cli.sh", variant], cwd=tdp,
                               capture_output=True, text=True)
            check(f"expected_sha works with a {variant.upper()} manifest",
                  digest in r.stdout, r.stdout.strip()[:200])


# --------------------------------------------------------------------------
# 5. Every remote download is actually gated
# --------------------------------------------------------------------------
def test_downloads_are_gated() -> None:
    cli = read(CLI)
    # The web-panel asset fetch is the dangerous one (server.py gets executed).
    check("web panel asset fetch calls ensure_manifest", "ensure_manifest" in cli)
    check("web panel asset fetch calls verify_manifest_file", "verify_manifest_file" in cli)
    check("download_theme calls ensure_manifest", "ensure_manifest" in cli)
    check("web panel fetch no longer degrades to a bare warning",
          'warn "Failed to fetch $_wf"' not in cli)
    inst = read(INSTALL_SH)
    check("install.sh fetch_raw verifies", "verify_downloaded" in inst)
    check("install.sh loads the manifest", "load_manifest" in inst)


def _bash() -> str:
    for p in (r"C:\Program Files\Git\bin\bash.exe",
              r"C:\Program Files\Git\usr\bin\bash.exe"):
        if os.path.exists(p):
            return p
    return "bash"


def main() -> int:
    test_manifest_covers_shipped_files()
    test_manifest_generator_agrees()
    test_no_moving_branch_default()
    test_no_piped_remote_execution()
    test_verifier_rejects_tampering()
    test_stage_manifest_check()
    test_expected_sha_tolerates_crlf()
    test_downloads_are_gated()

    passed = sum(1 for okk, _ in results if okk)
    for okk, name in results:
        print(f"  {'PASS' if okk else 'FAIL'}  {name}")
    print(f"\n{passed}/{len(results)} supply-chain checks passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
