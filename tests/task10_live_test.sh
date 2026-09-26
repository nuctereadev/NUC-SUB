#!/usr/bin/env bash
# Task 10 — live test: drive `nucsub update` against the REAL /opt/nuc-sub
# install, with the real systemd unit, the real web panel and real user data.
# The "remote" is a local bare repo holding A (what is deployed now) and B (the
# same tree with the new CLI), so nothing on GitHub is touched.
set -uo pipefail

PASS=0; FAIL=0; FAILED=()
ok(){ PASS=$((PASS+1)); printf '  \033[0;32m✓\033[0m %s\n' "$1"; }
bad(){ FAIL=$((FAIL+1)); FAILED+=("$1"); printf '  \033[0;31m✗ %s\033[0m  %s\n' "$1" "${2:-}"; }
chk(){ if [[ "$2" == "$3" ]]; then ok "$1"; else bad "$1" "expected [$3] got [$2]"; fi; }
# Matching is done with bash pattern matching, not `sed | grep -q`: under
# `set -o pipefail` a successful grep -q closes the pipe early, sed dies of
# SIGPIPE and the pipeline reports failure for a match that actually happened.
has(){ local t; t="$(sed -e 's/\x1b\[[0-9;]*m//g' "$2" 2>/dev/null)"; if [[ "$t" == *"$3"* ]]; then ok "$1"; else bad "$1" "missing [$3] in $2"; fi; }
hasnt(){ local t; t="$(sed -e 's/\x1b\[[0-9;]*m//g' "$2" 2>/dev/null)"; if [[ "$t" == *"$3"* ]]; then bad "$1" "unexpected [$3] in $2"; else ok "$1"; fi; }
exist(){ [[ -e "$2" ]] && ok "$1" || bad "$1" "missing $2"; }
noexist(){ [[ -e "$2" ]] && bad "$1" "should be gone: $2" || ok "$1"; }
sec(){ printf '\n\033[1;36m── %s\033[0m\n' "$1"; }

W=/root/t10live
SRC=/opt/nuc-sub
BARE=$W/origin.git
TARBALLS=$W/tarballs            # served root; files live in $TARBALLS/tar.gz/<sha>
                                  # (codeload layout the CLI requests)
PORTF=$W/PORT
NEWCLI=/root/t10suite/cli/nucsub          # the Task 10 build under test

rm -rf "$W"; mkdir -p "$W/tree" "$TARBALLS"

# ---------------------------------------------------------------- version A ---
# A is exactly what the server runs right now.
mkdir -p "$W/tree/cli" "$W/tree/webpanel" "$W/tree/themes/volt" "$W/tree/pasarguard-themes/subscription"
cp -a "$SRC/cli/nucsub"           "$W/tree/cli/nucsub"
cp -a "$SRC/webpanel/."            "$W/tree/webpanel/"
rm -rf "$W/tree/webpanel/__pycache__"
cp -a "$SRC/themes/volt/."         "$W/tree/themes/volt/" 2>/dev/null || true
echo "installer" > "$W/tree/install.sh"
echo "# NUC-SUB" > "$W/tree/README.md"
( cd "$W/tree" && git init -q -b main && git add -A && \
  git -c user.email=t@t -c user.name=t commit -q -m "A: current deployment" ) >/dev/null
git init -q --bare "$BARE" >/dev/null 2>&1
publish(){
    mkdir -p "$TARBALLS/tar.gz"
    ( cd "$W/tree" && git archive --format=tar.gz --prefix=NUC-SUB/ -o "$TARBALLS/tar.gz/$1" HEAD ) >/dev/null
    ( cd "$BARE" && git fetch -q "$W/tree" "HEAD:refs/heads/main" ) >/dev/null 2>&1
}
SHA_A="$(cd "$W/tree" && git rev-parse HEAD)"
publish "$SHA_A"

# ---------------------------------------------------------------- version B ---
# B is the same tree with the new CLI and a changed web panel + new asset.
install -m 755 "$NEWCLI" "$W/tree/cli/nucsub"
echo "# patched by live test" >> "$W/tree/webpanel/server.py"
echo "/* new asset */" > "$W/tree/webpanel/newasset.css"
( cd "$W/tree" && git add -A && git -c user.email=t@t -c user.name=t commit -q -m "B: task 10 build" ) >/dev/null
SHA_B="$(cd "$W/tree" && git rev-parse HEAD)"
publish "$SHA_B"
echo "A = $SHA_A"
echo "B = $SHA_B"

# ------------------------------------------------------- seed the real user ---
cp -a "$SRC/config.json" "$W/config.json.bak"
cp -a "$SRC/.webpanel-token" "$W/token.bak"
TOKEN_BEFORE="$(cat "$SRC/.webpanel-token")"
CFG_BEFORE="$(sha256sum "$SRC/config.json" | awk '{print $1}')"

# real user data that must survive (same keys the CLI/web panel write)
cfg_set(){ python3 - "$SRC/config.json" "$1" "$2" <<'PY'
import json, sys
p, k, v = sys.argv[1], sys.argv[2], sys.argv[3]
d = json.load(open(p, encoding='utf-8')) if __import__('os').path.exists(p) else {}
d[k] = json.loads(v)
json.dump(d, open(p, 'w', encoding='utf-8'), indent=2, ensure_ascii=False)
PY
}
cfg_get(){ python3 -c "import json,sys;print(json.load(open(sys.argv[1],encoding='utf-8')).get(sys.argv[2],''))" "$SRC/config.json" "$1" 2>/dev/null; }

cfg_set brand_name '"LiveTestBrand"'
cfg_set telegram_channel '"@livetest"'
cfg_set telegram_enabled 'true'
cfg_set brand_logo '"/opt/nuc-sub/branding/logos/livetest.png"'
mkdir -p "$SRC/branding/logos"
printf '\x89PNG\r\n\x1a\nLIVELOGO' > "$SRC/branding/logos/livetest.png"
BRAND_BEFORE="$(cfg_get brand_name)"
echo "brand before: $BRAND_BEFORE"

# an obsolete file from a "previous release" plus a stale asset and bytecode
echo "obsolete" > "$SRC/webpanel/legacy-obsolete.css"
echo "obsolete" > "$SRC/cli/legacy-helper.sh"
mkdir -p "$SRC/webpanel/__pycache__"; echo x > "$SRC/webpanel/__pycache__/server.cpython-312.pyc"

# record the currently installed commit as A, and deploy the new CLI
install -m 755 "$NEWCLI" "$SRC/cli/nucsub" || { echo "FATAL: could not deploy CLI"; exit 1; }
if ! grep -q web_panel_managed_here "$SRC/cli/nucsub"; then
    echo "FATAL: deployed CLI is not the Task 10 build"; exit 1
fi
printf '%s' "$SHA_A" > "$SRC/.nucsub-commit"
PID_BEFORE="$(systemctl show -p MainPID --value xui-sub-panel 2>/dev/null || echo 0)"
echo "panel pid before: $PID_BEFORE"

# ------------------------------------------------------------------- update ---
sec "live: update the real /opt/nuc-sub install from A to B"
rm -f "$PORTF"
python3 /root/t10suite/tarball_server.py "$W/tarballs" "$PORTF" >/dev/null 2>&1 &
SRV=$!
TP=""
for _ in $(seq 1 40); do
    if [[ -s "$PORTF" ]]; then
        cand="$(tr -d '[:space:]' < "$PORTF")"
        if curl -fsS -m 3 -o /dev/null "http://127.0.0.1:$cand/tar.gz/$SHA_B" 2>/dev/null; then TP="$cand"; break; fi
    fi
    sleep 0.25
done
if [[ -z "$TP" ]]; then echo "FATAL: tarball server never served tar.gz/$SHA_B"; kill $SRV 2>/dev/null; exit 1; fi

NUC_SUB_REPO_GIT="$BARE" NUC_SUB_TARBALL_BASE="http://127.0.0.1:$TP" \
  nucsub update > "$W/out.txt" 2>&1
RC=$?
kill $SRV 2>/dev/null
sed 's/^/  | /' "$W/out.txt"

chk "update succeeded" "$RC" "0"
has "new CLI is live" "$SRC/cli/nucsub" "web_panel_managed_here"
has "new web panel is live" "$SRC/webpanel/server.py" "patched by live test"
exist "new asset installed" "$SRC/webpanel/newasset.css"
chk "commit record is B" "$(cat "$SRC/.nucsub-commit")" "$SHA_B"

sec "live: obsolete files removed, no stale bytecode"
noexist "obsolete webpanel file removed" "$SRC/webpanel/legacy-obsolete.css"
noexist "obsolete helper removed" "$SRC/cli/legacy-helper.sh"
noexist "stale bytecode removed" "$SRC/webpanel/__pycache__"
noexist "staging dir cleaned" "$SRC/.update-stage"
noexist "backup dir cleaned" "$SRC/.update-backup"

sec "live: user data preserved"
chk "token unchanged" "$(cat "$SRC/.webpanel-token")" "$TOKEN_BEFORE"
chk "token still mode 600" "$(stat -c %a "$SRC/.webpanel-token")" "600"
chk "brand name preserved" "$(cfg_get brand_name)" "$BRAND_BEFORE"
chk "brand logo setting preserved" "$(cfg_get brand_logo)" "/opt/nuc-sub/branding/logos/livetest.png"
has "telegram channel preserved" "$SRC/config.json" "@livetest"
exist "brand logo preserved" "$SRC/branding/logos/livetest.png"
chk "webport preserved" "$(cat "$SRC/.webport")" "8080"
chk "panel.conf preserved" "$(cat "$SRC/panel.conf")" "3xui"
chk "env file still has no token" "$(grep -c NP_TOKEN "$SRC/.webpanel-env" || true)" "0"

sec "live: permissions"
chk "CLI executable" "$(stat -c %a "$SRC/cli/nucsub")" "755"
chk "server.py 644" "$(stat -c %a "$SRC/webpanel/server.py")" "644"
chk "new asset 644" "$(stat -c %a "$SRC/webpanel/newasset.css")" "644"

sec "live: services healthy, unit correct, panel really serving new code"
chk "service active" "$(systemctl is-active xui-sub-panel)" "active"
chk "service enabled" "$(systemctl is-enabled xui-sub-panel)" "enabled"
has "unit points at the real install" /etc/systemd/system/xui-sub-panel.service "$SRC"
has "unit env file is the real one" /etc/systemd/system/xui-sub-panel.service "$SRC/.webpanel-env"
PID_AFTER="$(systemctl show -p MainPID --value xui-sub-panel 2>/dev/null || echo 0)"
if [[ "$PID_AFTER" != "$PID_BEFORE" && "$PID_AFTER" != "0" ]]; then
    ok "panel process was restarted (pid $PID_BEFORE -> $PID_AFTER)"
else
    bad "panel process was restarted" "pid $PID_BEFORE -> $PID_AFTER"
fi
CODE="$(curl -s -o /dev/null -w '%{http_code}' -m 10 -H "Authorization: Bearer $TOKEN_BEFORE" http://127.0.0.1:8080/api/status)"
chk "panel API answers 200" "$CODE" "200"
if grep -q web_panel_managed_here /usr/bin/nucsub; then
    ok "nucsub on PATH is the new build"
else
    bad "nucsub on PATH is the new build" "marker missing"
fi

sec "live: idempotence and rollback of user settings"
NUC_SUB_REPO_GIT="$BARE" NUC_SUB_TARBALL_BASE="http://127.0.0.1:$TP" nucsub update > "$W/out2.txt" 2>&1
chk "second update succeeds" "$?" "0"
has "says already up to date" "$W/out2.txt" "already up to date"
hasnt "does not claim a fresh update" "$W/out2.txt" "New version detected"
chk "commit record still B" "$(cat "$SRC/.nucsub-commit")" "$SHA_B"

sec "live: rollback path (unreachable remote leaves the install intact)"
BEFORE_STATE="$(sha256sum "$SRC/cli/nucsub" | awk '{print $1}')"
NUC_SUB_REPO_GIT="$BARE" NUC_SUB_TARBALL_BASE="http://127.0.0.1:1" nucsub update -f > "$W/out3.txt" 2>&1
RC3=$?
if [[ "$RC3" -ne 0 ]]; then ok "unreachable remote returns non-zero"; else bad "unreachable remote returns non-zero" "got 0"; fi
hasnt "never claims success" "$W/out3.txt" "updated successfully"
chk "CLI untouched after failure" "$(sha256sum "$SRC/cli/nucsub" | awk '{print $1}')" "$BEFORE_STATE"
chk "service still active" "$(systemctl is-active xui-sub-panel)" "active"

# ------------------------------------------------------------------- restore ---
# Put the server back on the real published release: the test installed a
# synthetic tree (patched server.py, newasset.css) that must not survive.
cfg_set brand_name '""'
cfg_set telegram_channel '""'
cfg_set telegram_enabled 'false'
cfg_set brand_logo '""'
cp -a "$W/config.json.bak" "$SRC/config.json"
rm -f "$SRC/branding/logos/livetest.png"
nucsub update > "$W/restore.txt" 2>&1
RC_R=$?
REAL_HEAD="$(git ls-remote https://github.com/nuctereadev/NUC-SUB.git main 2>/dev/null | awk '{print $1}')"
[[ -n "$REAL_HEAD" ]] || REAL_HEAD="unknown"

sec "live: server left clean on the real published release"
chk "restore update succeeded" "$RC_R" "0"
noexist "synthetic webpanel asset gone" "$SRC/webpanel/newasset.css"
hasnt "synthetic patch gone" "$SRC/webpanel/server.py" "patched by live test"
noexist "test brand logo gone" "$SRC/branding/logos/livetest.png"
hasnt "test brand setting gone" "$SRC/config.json" "LiveTestBrand"
hasnt "test telegram setting gone" "$SRC/config.json" "@livetest"
if [[ "$REAL_HEAD" != "unknown" ]]; then
    chk "commit record is the published HEAD" "$(cat "$SRC/.nucsub-commit")" "$REAL_HEAD"
else
    printf '  \033[0;33m~\033[0m published HEAD (skipped: no network)\n'
fi
chk "service still active" "$(systemctl is-active xui-sub-panel)" "active"
chk "service still enabled" "$(systemctl is-enabled xui-sub-panel)" "enabled"
CODE="$(curl -s -o /dev/null -w '%{http_code}' -m 10 -H "Authorization: Bearer $(cat "$SRC/.webpanel-token")" http://127.0.0.1:8080/api/status)"
chk "panel API still answers 200" "$CODE" "200"
nucsub webpanel status > "$W/wp.txt" 2>&1
has "webpanel status reports Running" "$W/wp.txt" "Running on port"

printf '\n\033[1m═══ live: %d passed, %d failed ═══\033[0m\n' "$PASS" "$FAIL"
[[ $FAIL -gt 0 ]] && { printf 'Failed:\n'; for n in "${FAILED[@]}"; do printf '  - %s\n' "$n"; done; exit 1; }
exit 0
