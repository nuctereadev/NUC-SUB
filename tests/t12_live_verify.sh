#!/bin/bash
# Post-deploy verification for the Task 12 hardening.
pass=0; fail=0
ck() { if [ "$2" = "0" ]; then printf '  \033[32mPASS\033[0m %s\n' "$1"; pass=$((pass+1));
       else printf '  \033[31mFAIL\033[0m %s\n' "$1"; fail=$((fail+1)); fi; }

PORT=$(cat /opt/nuc-sub/.webport 2>/dev/null | tr -dc '0-9'); [ -n "$PORT" ] || PORT=8080
PUBIP=$(hostname -I | awk '{print $1}')

echo "== service =="
[ "$(systemctl is-active xui-sub-panel)" = "active" ]; ck "service active" $?
[ "$(systemctl is-active x-ui)" = "active" ];            ck "x-ui still active" $?
[ "$(systemctl is-enabled xui-sub-panel)" = "enabled" ]; ck "service enabled for boot" $?

echo "== identity =="
RUNAS=$(systemctl show -p User --value xui-sub-panel)
[ "$RUNAS" = "nucsub-web" ]; ck "runs as nucsub-web (not root)" $?
[ "$RUNAS" = "root" ] && { printf '  \033[31mFAIL\033[0m still root\n'; fail=$((fail+1)); }
PID=$(systemctl show -p MainPID --value xui-sub-panel)
UID_PROC=$(awk '/^Uid:/{print $2}' /proc/$PID/status 2>/dev/null)
[ "$UID_PROC" != "0" ]; ck "process uid is non-zero ($UID_PROC)" $?

echo "== binding =="
ss -tlnp 2>/dev/null | grep -q "127.0.0.1:$PORT"; ck "listening on 127.0.0.1:$PORT" $?
ss -tlnp 2>/dev/null | grep -qE "0\.0\.0\.0:$PORT|\*:$PORT"; \
  [ $? -ne 0 ]; ck "NOT listening on 0.0.0.0:$PORT" $?
curl -fsS -m 5 "http://127.0.0.1:$PORT/" -o /dev/null 2>/dev/null; ck "answers on loopback" $?
curl -fsS -m 4 "http://$PUBIP:$PORT/" -o /dev/null 2>/dev/null; \
  [ $? -ne 0 ]; ck "refuses the public IP $PUBIP:$PORT" $?

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
sudo -u nucsub-web sudo -n /bin/bash >/dev/null 2>&1; [ $? -ne 0 ]; ck "/bin/bash via sudo is REFUSED" $?
sudo -u nucsub-web sudo -n /opt/nuc-sub/cli/nucsub reset --force >/dev/null 2>&1; [ $? -ne 0 ]; ck "extra args are REFUSED" $?
sudo -u nucsub-web test -w /opt/nuc-sub/webpanel/server.py; [ $? -ne 0 ]; ck "cannot write its own code" $?
sudo -u nucsub-web test -r /opt/nuc-sub/.webpanel-token; ck "can read the admin token" $?
stat -c '%U' /opt/nuc-sub/.webpanel-token | grep -q '^root$'; ck "token stays root-owned" $?

echo "== persistence =="
[ -f /opt/nuc-sub/.webpanel-env ]; ck "env file exists (not in tmpfs)" $?
grep -q 'NP_HOST=127.0.0.1' /opt/nuc-sub/.webpanel-env; ck "NP_HOST=127.0.0.1 persisted" $?

echo "== leftovers =="
ls /root/up_server.py /root/up_index.html >/dev/null 2>&1 && { printf '  \033[33mnote\033[0m staging files still in /root\n'; }

printf '\n  %d passed, %d failed\n' "$pass" "$fail"
[ "$fail" = "0" ] || exit 1
