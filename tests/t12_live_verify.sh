#!/bin/bash
# Post-deploy verification for the Task 12 hardening.
pass=0; fail=0
ck() { if [ "$2" = "0" ]; then printf '  \033[32mPASS\033[0m %s\n' "$1"; pass=$((pass+1));
       else printf '  \033[31mFAIL\033[0m %s\n' "$1"; fail=$((fail+1)); fi; }

PORT=$(cat /opt/nuc-sub/.webport 2>/dev/null | tr -dc '0-9'); [ -n "$PORT" ] || PORT=8080
PUBIP=$(hostname -I | awk '{print $1}')

echo "== service =="
[ "$(systemctl is-active xui-sub-panel)" = "active" ]; ck "service active" $?
# The subscription backend: a systemd x-ui install, or the PasarGuard container.
# Checking for x-ui alone always fails on a PasarGuard box, where the panel is
# a Docker container and there is no x-ui unit at all.
if systemctl cat x-ui >/dev/null 2>&1; then
    [ "$(systemctl is-active x-ui)" = "active" ]; ck "x-ui still active" $?
elif command -v docker >/dev/null 2>&1; then
    docker ps --format '{{.Names}}' 2>/dev/null | grep -qi pasarguard
    ck "pasarguard panel container still running" $?
else
    printf '  \033[33mnote\033[0m no x-ui unit and no docker, backend check skipped\n'
fi
[ "$(systemctl is-enabled xui-sub-panel)" = "enabled" ]; ck "service enabled for boot" $?

echo "== identity =="
RUNAS=$(systemctl show -p User --value xui-sub-panel)
[ "$RUNAS" = "nucsub-web" ]; ck "runs as nucsub-web (not root)" $?
[ "$RUNAS" = "root" ] && { printf '  \033[31mFAIL\033[0m still root\n'; fail=$((fail+1)); }
PID=$(systemctl show -p MainPID --value xui-sub-panel)
UID_PROC=$(awk '/^Uid:/{print $2}' /proc/$PID/status 2>/dev/null)
[ "$UID_PROC" != "0" ]; ck "process uid is non-zero ($UID_PROC)" $?

echo "== binding =="
# The bind address is a deployment choice (loopback behind a tunnel, or public
# behind the token gate), so assert against what this install declares instead
# of a hardcoded assumption.
NP_HOST=$(sed -n 's/^NP_HOST=//p' /opt/nuc-sub/.webpanel-env 2>/dev/null | tr -d '"')
[ -n "$NP_HOST" ] || NP_HOST=127.0.0.1
curl -fsS -m 5 "http://127.0.0.1:$PORT/" -o /dev/null 2>/dev/null; ck "answers on loopback (NP_HOST=$NP_HOST)" $?
if [ "$NP_HOST" = "0.0.0.0" ]; then
  curl -fsS -m 4 "http://$PUBIP:$PORT/" -o /dev/null 2>/dev/null; ck "public bind: answers on $PUBIP:$PORT" $?
else
  curl -fsS -m 4 "http://$PUBIP:$PORT/" -o /dev/null 2>/dev/null; \
    [ $? -ne 0 ]; ck "loopback bind: refuses the public IP $PUBIP:$PORT" $?
  ss -tlnp 2>/dev/null | grep -qE "0\.0\.0\.0:$PORT|\*:$PORT"; \
    [ $? -ne 0 ]; ck "NOT listening on 0.0.0.0:$PORT" $?
fi

echo "== security headers (live) =="
H=$(curl -sI -m 5 "http://127.0.0.1:$PORT/" 2>/dev/null)
echo "$H" | grep -qi "content-security-policy"; ck "CSP present" $?
echo "$H" | grep -qi "referrer-policy: *no-referrer"; ck "Referrer-Policy: no-referrer" $?
echo "$H" | grep -qi "strict-transport-security"; ck "HSTS present" $?
echo "$H" | grep -qi "x-frame-options: *DENY"; ck "X-Frame-Options: DENY" $?
echo "$H" | grep -qi "x-content-type-options: *nosniff"; ck "nosniff present" $?
echo "$H" | grep -qi "^Server:.*Python"; [ $? -ne 0 ]; ck "Server header hides the Python build" $?

echo "== auth =="
c=$(curl -s -o /dev/null -w '%{http_code}' -m 5 "http://127.0.0.1:$PORT/api/status"); [ "$c" = "401" ]; ck "no token -> 401" $?
c=$(curl -s -o /dev/null -w '%{http_code}' -m 5 -H "Authorization: Bearer wrongwrongwrongwrong" "http://127.0.0.1:$PORT/api/status"); [ "$c" = "401" ]; ck "bad token -> 401" $?
c=$(curl -s -o /dev/null -w '%{http_code}' -m 5 "http://127.0.0.1:$PORT/api/status?token=x"); [ "$c" = "401" ]; ck "token in query string -> 401" $?

echo "== privilege separation =="
sudo -u nucsub-web sudo -n /opt/nuc-sub/cli/nucsub status >/dev/null 2>&1; ck "sudoers escalation works" $?
sudo -u nucsub-web sudo -n /opt/nuc-sub/cli/nucsub refresh >/dev/null 2>&1; ck "sudoers refresh escalation works" $?
sudo -u nucsub-web sudo -n /bin/bash >/dev/null 2>&1; [ $? -ne 0 ]; ck "/bin/bash via sudo is REFUSED" $?
sudo -u nucsub-web sudo -n /opt/nuc-sub/cli/nucsub reset --force >/dev/null 2>&1; [ $? -ne 0 ]; ck "extra args are REFUSED" $?
sudo -u nucsub-web test -w /opt/nuc-sub/webpanel/server.py; [ $? -ne 0 ]; ck "cannot write its own code" $?
sudo -u nucsub-web test -r /opt/nuc-sub/.webpanel-token; ck "can read the admin token" $?
stat -c '%U' /opt/nuc-sub/.webpanel-token | grep -q '^root$'; ck "token stays root-owned" $?
sudo -u nucsub-web test -w /opt/nuc-sub/config.json; ck "can write config.json (saves work)" $?
sudo -u nucsub-web test -w /opt/nuc-sub; [ $? -ne 0 ]; ck "install tree stays read-only" $?

echo "== settings save =="
# The reported bug: every save came back as an internal storage error because
# the panel could not write the install dir. Save the current settings straight
# back -- idempotent, and it exercises that exact write path.
TOKEN=$(cat /opt/nuc-sub/.webpanel-token 2>/dev/null)
G=$(curl -s -m 5 -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:$PORT/api/settings")
echo "$G" | grep -q '"settings"'; ck "authenticated GET /api/settings" $?
BODY=$(echo "$G" | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin).get("settings", {})))' 2>/dev/null)
[ -n "$BODY" ]; ck "settings payload is readable" $?
CODE=$(curl -s -o /tmp/t21-save.json -w '%{http_code}' -m 15 -X POST \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  --data "$BODY" "http://127.0.0.1:$PORT/api/settings")
[ "$CODE" = "200" ]; ck "settings save returns 200 (got ${CODE:-none})" $?
grep -q '"ok": *true' /tmp/t21-save.json; ck "save reports ok" $?
# A save that cannot re-apply into the themes reports warn=theme_refresh_failed
# and the new logo/brand never reaches the subscription pages.
grep -q 'theme_refresh_failed' /tmp/t21-save.json; [ $? -ne 0 ]; ck "save re-applies into the themes (no refresh warning)" $?
journalctl -u xui-sub-panel --since '-3 min' --no-pager 2>/dev/null \
  | grep -q 'settings POST save failed'; [ $? -ne 0 ]; ck "no save failure in the journal" $?

echo "== persistence =="
[ -f /opt/nuc-sub/.webpanel-env ]; ck "env file exists (not in tmpfs)" $?
grep -qE '^NP_HOST=(127\.0\.0\.1|0\.0\.0\.0)$' /opt/nuc-sub/.webpanel-env; ck "NP_HOST persisted and sane ($NP_HOST)" $?
systemctl cat xui-sub-panel 2>/dev/null | grep -q 'EnvironmentFile=-/opt/nuc-sub/.webpanel-env'; ck "unit still reads the env file" $?

echo "== leftovers =="
ls /root/up_server.py /root/up_index.html >/dev/null 2>&1 && { printf '  \033[33mnote\033[0m staging files still in /root\n'; }

printf '\n  %d passed, %d failed\n' "$pass" "$fail"
[ "$fail" = "0" ] || exit 1
