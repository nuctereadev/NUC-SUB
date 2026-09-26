#!/usr/bin/env bash
# Runs on the live server. The public host is passed in so the repo never carries
# a real address:  PUBLIC_HOST=<public ip> ./t10_accept_check.sh
set -uo pipefail
: "${PUBLIC_HOST:?set PUBLIC_HOST to the public address of this server}"
echo "=== POST-ACCEPTANCE STATE ==="
TOK="$(cat /opt/nuc-sub/.webpanel-token)"
echo "commit record        : $(cat /opt/nuc-sub/.nucsub-commit)"
echo "published HEAD       : $(git ls-remote https://github.com/nuctereadev/NUC-SUB.git main | cut -f1)"
echo "obsolete file gone   : $([[ -e /opt/nuc-sub/webpanel/legacy-obsolete.css ]] && echo NO || echo yes)"
echo "staging cleaned      : $([[ -e /opt/nuc-sub/.update-stage ]] && echo NO || echo yes)"
echo "backup cleaned       : $([[ -e /opt/nuc-sub/.update-backup ]] && echo NO || echo yes)"
echo "new updater          : $(grep -c web_panel_managed_here /opt/nuc-sub/cli/nucsub) refs"
echo "service              : $(systemctl is-active xui-sub-panel) / $(systemctl is-enabled xui-sub-panel)"
echo "unit install path    : $(grep -o '/opt/nuc-sub/webpanel/server.py' /etc/systemd/system/xui-sub-panel.service | head -1)"
echo "panel pid            : $(systemctl show -p MainPID --value xui-sub-panel)"
echo "api local            : $(curl -s -o /dev/null -w '%{http_code}' -m 10 -H "Authorization: Bearer $TOK" http://127.0.0.1:8080/api/status)"
echo "api public           : $(curl -s -o /dev/null -w '%{http_code}' -m 15 -H "Authorization: Bearer $TOK" "http://${PUBLIC_HOST}:8080/api/status")"
echo "perms cli/server/tok : $(stat -c %a /opt/nuc-sub/cli/nucsub)/$(stat -c %a /opt/nuc-sub/webpanel/server.py)/$(stat -c %a /opt/nuc-sub/.webpanel-token)"
echo "x-ui                 : $(systemctl is-active x-ui)"
echo "--- third run (must be a clean no-op) ---"
nucsub update 2>&1 | sed -e 's/\x1b\[[0-9;]*m//g'
echo "exit: ${PIPESTATUS[0]}"
echo "--- leftovers ---"
ls -d /root/t10* /tmp/t10* 2>/dev/null || echo none
