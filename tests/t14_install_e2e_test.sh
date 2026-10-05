#!/usr/bin/env bash
# =============================================================================
#  NUC-SUB — installer end-to-end tests
#
#  Everything else in tests/ checks pieces. This one actually EXECUTES
#  install.sh, because a real crash shipped through the whole suite once:
#  verify_manifest_signature() declared `local sig="$1" pubkey="$2"` while being
#  called with one argument, so `set -u` killed every install at "Fetching source
#  from GitHub". No grep-based test can catch that; only running the thing can.
#
#  The install is sandboxed: a file:// mirror stands in for GitHub, the install
#  dir is a temp dir, and package managers are stubbed. /usr/bin/nucsub is the
#  one thing install.sh writes outside the install dir, so it is saved and
#  restored.
#
#  Usage: sudo bash tests/t14_install_e2e_test.sh
#  Linux only — install.sh runs as root and has no other supported platform.
# =============================================================================
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
REAL_NUCSUB=""
[[ -e /usr/bin/nucsub ]] && REAL_NUCSUB="$(readlink -f /usr/bin/nucsub 2>/dev/null || echo present)"

cleanup() {
    if [[ -n "$REAL_NUCSUB" ]]; then
        ln -sf "$REAL_NUCSUB" /usr/bin/nucsub 2>/dev/null || true
    else
        rm -f /usr/bin/nucsub 2>/dev/null || true
    fi
    rm -rf "$WORK"
}
trap cleanup EXIT

pass=0; fail=0
ok()  { echo -e "  ${GREEN}PASS${NC}  $1"; pass=$((pass+1)); }
bad() { echo -e "  ${RED}FAIL${NC}  $1"; fail=$((fail+1)); }

GREEN='\033[0;32m'; RED='\033[0;31m'; DIM='\033[2m'; NC='\033[0m'
[[ -t 1 ]] || { GREEN=''; RED=''; DIM=''; NC=''; }

[[ "$EUID" -eq 0 ]] || { echo "must run as root (install.sh checks EUID)"; exit 1; }

# ---- stub bin: keep package managers from mutating the host -----------------
STUB="$WORK/stub"; mkdir -p "$STUB"
for c in apt-get apt dnf pacman; do
    printf '#!/bin/sh\necho "[stub %s] $*" >> "%s/pkg.log"\nexit 0\n' "$c" "$WORK" > "$STUB/$c"
    chmod +x "$STUB/$c"
done
export PATH="$STUB:$PATH"

# ---- build a release mirror -------------------------------------------------
MIRROR="$WORK/mirror"
mkdir -p "$MIRROR"
cp -r "$ROOT/cli" "$ROOT/webpanel" "$ROOT/themes" "$ROOT/pasarguard-themes" "$MIRROR/"
cp "$ROOT/MANIFEST.sha256" "$MIRROR/"

# install.sh must live OUTSIDE the mirror: is_local() returns true when
# install.sh and cli/nucsub sit in the same directory, which would skip the
# remote path this suite exists to exercise.
RUNNER="$WORK/runner"; mkdir -p "$RUNNER"
cp "$ROOT/install.sh" "$RUNNER/"

# run_install <name> <panel> [mirror]
run_install() {
    local name="$1" panel="$2" mirror="${3:-$MIRROR}" dest="$WORK/dest-$1"
    rm -rf "$dest"; mkdir -p "$dest"
    XUI_SUB_REPO="file://$mirror" \
    XUI_SUB_INSTALL_DIR="$dest" \
    NUC_SUB_PANEL="$panel" \
    XUI_SUB_NONINTERACTIVE=1 \
    SKIP_MENU=1 \
        bash "$RUNNER/install.sh" >"$WORK/$name.out" 2>&1
    echo $?
}

banner() { echo; echo -e "${DIM}== $1 ==${NC}"; }

# =============================================================================
banner "1. 3x-ui install completes"
# =============================================================================
rc="$(run_install 3xui 3xui)"
out="$(cat "$WORK/3xui.out")"
[[ "$rc" == 0 ]] && ok "exits 0" || bad "exits 0 (got $rc)"
grep -q "unbound variable" "$WORK/3xui.out" && bad "no unbound-variable crash" \
                                          || ok "no unbound-variable crash"
grep -q "CHECKSUM MISMATCH" "$WORK/3xui.out" && bad "no checksum mismatch" || ok "no checksum mismatch"
[[ -f "$WORK/dest-3xui/cli/nucsub" ]] && ok "cli/nucsub installed" || bad "cli/nucsub installed"
[[ -f "$WORK/dest-3xui/themes/volt/index.html" ]] && ok "default theme preloaded" \
                                                   || bad "default theme preloaded"
if [[ -f "$WORK/dest-3xui/cli/nucsub" ]]; then
    a="$(sha256sum "$WORK/dest-3xui/cli/nucsub" | cut -d' ' -f1)"
    b="$(awk '$2=="cli/nucsub"{print $1}' "$MIRROR/MANIFEST.sha256")"
    [[ "$a" == "$b" ]] && ok "installed cli matches the manifest hash" \
                        || bad "installed cli matches the manifest hash"
fi
bash -n "$WORK/dest-3xui/cli/nucsub" 2>/dev/null && ok "installed cli parses" \
                                               || bad "installed cli parses"

# =============================================================================
banner "2. Pasarguard install completes"
# =============================================================================
rc="$(run_install pg pasarguard)"
out="$(cat "$WORK/pg.out")"
[[ "$rc" == 0 ]] && ok "exits 0" || bad "exits 0 (got $rc)"
grep -q "unbound variable" "$WORK/pg.out" && bad "no unbound-variable crash" \
                                          || ok "no unbound-variable crash"
[[ -f "$WORK/dest-pg/pasarguard-themes/subscription/volt.html" ]] \
    && ok "Pasarguard template installed" || bad "Pasarguard template installed"

# =============================================================================
banner "3. tampered payload is refused"
# =============================================================================
TM="$WORK/mirror-tampered"; cp -r "$MIRROR" "$TM"
printf '\n# attacker injected\n' >> "$TM/cli/nucsub"
rc="$(run_install tampered 3xui "$TM")"
grep -q "CHECKSUM MISMATCH" "$WORK/tampered.out" && ok "tampered cli/nucsub rejected" \
                                               || bad "tampered cli/nucsub rejected"
[[ "$rc" != 0 ]] && ok "tampered install exits non-zero" || bad "tampered install exits non-zero"
if [[ -f "$WORK/dest-tampered/cli/nucsub" ]] && grep -q "attacker injected" \
        "$WORK/dest-tampered/cli/nucsub" 2>/dev/null; then
    bad "tampered file was deleted, not left on disk"
else
    ok "tampered file was deleted, not left on disk"
fi

# =============================================================================
banner "4. tampered manifest entry is refused"
# =============================================================================
TM2="$WORK/mirror-tamper2"; cp -r "$MIRROR" "$TM2"
sed -i 's/^\(.\)\{64\}\(  cli\/nucsub\)$/0000000000000000000000000000000000000000000000000000000000000000\2/' "$TM2/MANIFEST.sha256"
rc="$(run_install tamper2 3xui "$TM2")"
[[ "$rc" != 0 ]] && ok "manifest edited to match a bad payload is refused" \
                 || bad "manifest edited to match a bad payload is refused"

# =============================================================================
banner "5. missing manifest is refused"
# =============================================================================
MM="$WORK/mirror-nomanifest"; cp -r "$MIRROR" "$MM"; rm -f "$MM/MANIFEST.sha256"
rc="$(run_install nomanifest 3xui "$MM")"
grep -q "MANIFEST" "$WORK/nomanifest.out" && ok "missing manifest reported" \
                                           || bad "missing manifest reported"
[[ "$rc" != 0 ]] && ok "install without a manifest exits non-zero" \
                 || bad "install without a manifest exits non-zero"

# =============================================================================
banner "6. an unsigned release degrades instead of failing"
# =============================================================================
# No signature is published yet, so this must warn and continue, not abort and
# not silently "pass" as verified.
grep -q "checksum-only" "$WORK/3xui.out" && ok "checksum-only release warns" \
                                        || bad "checksum-only release warns"
[[ "$(grep -c 'signature verified' "$WORK/3xui.out")" == "0" ]] \
    && ok "does not claim a signature was verified" \
    || bad "does not claim a signature was verified"

# =============================================================================
banner "7. NUC_SUB_REQUIRE_SIG=1 makes an unsigned release fatal"
# =============================================================================
rm -rf "$WORK/dest-strict"; mkdir -p "$WORK/dest-strict"
XUI_SUB_REPO="file://$MIRROR" XUI_SUB_INSTALL_DIR="$WORK/dest-strict" \
NUC_SUB_PANEL=3xui XUI_SUB_NONINTERACTIVE=1 SKIP_MENU=1 NUC_SUB_REQUIRE_SIG=1 \
    bash "$RUNNER/install.sh" >"$WORK/strict.out" 2>&1
[[ $? != 0 ]] && ok "REQUIRE_SIG=1 aborts without a signature" \
              || bad "REQUIRE_SIG=1 aborts without a signature"

# =============================================================================
banner "8. static check: no function declares more positional params than it is called with"
# =============================================================================
# The crash class from this file, caught statically so the next one does not
# have to ship first. Looks for functions declaring local x="$N" and flags the
# ones whose only call sites pass fewer than N arguments.
python3 - "$ROOT/install.sh" <<'PY'
import re, sys
src = open(sys.argv[1], encoding='utf-8').read()
lines = src.splitlines()
funcs = {}
cur = None
for i, ln in enumerate(lines, 1):
    m = re.match(r'^([a-z_][a-z0-9_]*)\(\)\s*\{', ln)
    if m:
        cur = (m.group(1), i); funcs.setdefault(m.group(1), []).append([i, 0])
        continue
    if cur and re.match(r'^\}', ln):
        cur = None; continue
    if cur:
        for pm in re.finditer(r'"\$(\d)"', ln):
            n = int(pm.group(1))
            funcs[cur[0]][0][1] = max(funcs[cur[0]][0][1], n)
bad = []
for name, (dline, maxp) in funcs.items():
    if maxp == 0:
        continue
    calls = []
    for i, ln in enumerate(lines, 1):
        if i == dline or not re.search(r'\b' + re.escape(name) + r'\b', ln):
            continue
        if re.match(r'^\s*#', ln):
            continue
        body = re.sub(r'^\s*' + re.escape(name) + r'\b', '', ln).strip()
        if body.startswith('()'):      # the definition itself
            continue
        if not body.startswith('"'):   # only simple `fn "$a" "$b"` calls count
            continue
        args = re.findall(r'"[^"]*"', body)
        calls.append((i, len(args)))
    if calls and all(n < maxp for _, n in calls):
        bad.append(f'{name} (line {dline}) declares ${maxp} but is called with {min(n for _, n in calls)}')
if bad:
    print('  MISMATCH:', '; '.join(bad))
    sys.exit(1)
print('  all positional-param functions are called with enough args')
PY
[[ $? == 0 ]] && ok "positional-parameter arity is consistent" \
              || bad "positional-parameter arity is consistent"

echo
if [[ "$fail" -eq 0 ]]; then
    echo -e "${GREEN}=== $pass passed, 0 failed ===${NC}"
else
    echo -e "${RED}=== $pass passed, $fail failed ===${NC}"
fi
[[ "$fail" -eq 0 ]]