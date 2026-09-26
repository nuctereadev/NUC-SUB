#!/usr/bin/env bash
# Final acceptance: the live server updates itself from the real published
# commit using the Task 10 updater it just installed.
set -uo pipefail
W=/root/t10accept
rm -rf "$W"; mkdir -p "$W"
TOK="$(cat /opt/nuc-sub/.webpanel-token)"
CFG="$(sha256sum /opt/nuc-sub/config.json | cut -d' ' -f1)"
THEME="$(cat /etc/x-ui/sub_templates/volt/index.html 2>/dev/null | sha256sum | cut -d' ' -f1)"
PID_BEFORE="$(systemctl show -p MainPID --value xui-sub-panel)"

echo "before: commit=$(cut -c1-7 /opt/nuc-sub/.nucsub-commit) updater=$(grep -c web_panel_managed_here /opt/nuc-sub/cli/nucsub) pid=$PID_BEFORE"

# plant an obsolete file so we can prove the real sync deletes it
echo obsolete > /opt/nuc-sub/webpanel/legacy-obsolete.css

echo "=== running the real update ==="
nucsub update 2>&1 | sed -e 's/\x1b\[[0-9;]*m//g'
RC=${PIPESTATUS[0]}

echo
echo "=== results ==="
echo "exit code            : $RC"
echo "commit record        : $(cat /opt/nuc-sub/.nucsub-commit)"
echo "published HEAD       : $(git ls-remote https://github.com/nuctereadev/NUC-SUB.git main | cut -f1)"
echo "new updater installed: $(grep -c web_panel_managed_here /opt/nuc-sub/cli/nucsub) (expect 3)"
echo "obsolete file gone   : $([[ -e /opt/nuc-sub/webpanel/legacy-obsolete.css ]] && echo NO || echo yes)"
echo "config preserved     : $([[ "$(sha256sum /opt/nuc-sub/config.json | cut -d' ' -f1)" == "$CFG" ]] && echo yes || echo NO)"
echo "theme preserved      : $([[ "$(cat /etc/x-ui/sub_templates/volt/index.html | sha256sum | cut -d' ' -f1)" == "$THEME" ]] && echo yes || echo NO)"
echo "service active       : $(systemctl is-active xui-sub-panel)"
echo "unit install path    : $(grep -o '/opt/nuc-sub/webpanel/server.py' /etc/systemd/system/xui-sub-panel.service | head -1)"
echo "panel restarted      : $([[ "$(systemctl show -p MainPID --value xui-sub-panel)" != "$PID_BEFORE" ]] && echo yes || echo NO)"
echo "api status           : $(curl -s -o /dev/null -w '%{http_code}' -m 10 -H "Authorization: Bearer $TOK" http://127.0.0.1:8080/api/status)"
echo "cli perms            : $(stat -c %a /opt/nuc-sub/cli/nucsub)"
echo "x-ui                 : $(systemctl is-active x-ui)"

echo
echo "=== second run must be a no-op ==="
nucsub update 2>&1 | sed -e 's/\x1b\[[0-9;]*m//g'
echo "exit code: ${PIPESTATUS[0]}"
rm -rf "$W"
