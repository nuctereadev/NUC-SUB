#!/bin/bash
echo "=== 1. web panel systemd unit (does it run as root?) ==="
systemctl cat xui-sub-panel 2>/dev/null | grep -vE '^\s*#' | grep -v '^$'
echo
echo "=== 2. who owns the process / listening sockets ==="
ss -tlnp 2>/dev/null | grep -E "8080|2096|LISTEN" | head -12
echo
echo "=== 3. firewall ==="
(ufw status 2>/dev/null || echo "ufw: not installed")
iptables -S 2>/dev/null | head -12 || echo "iptables: needs root/nft"
echo
echo "=== 4. permissions on secrets ==="
stat -c '%a %U:%G %n' /opt/nuc-sub /opt/nuc-sub/config.json /opt/nuc-sub/.webpanel-token \
  /opt/nuc-sub/webpanel.log /opt/nuc-sub/cli/nucsub /opt/nuc-sub/webpanel/server.py 2>/dev/null
echo
echo "=== 5. is 8080 reachable from the internet (not just localhost)? ==="
curl -s -o /dev/null -w 'public 8080 -> HTTP %{http_code}\n' -m 10 http://127.0.0.1:8080/ 2>/dev/null
echo
echo "=== 6. unauthenticated API access (must be 401) ==="
curl -s -o /dev/null -w 'no token      -> HTTP %{http_code}\n' -m 10 http://127.0.0.1:8080/api/status
curl -s -o /dev/null -w 'wrong token   -> HTTP %{http_code}\n' -m 10 -H 'Authorization: Bearer wrongwrongwrongwrong' http://127.0.0.1:8080/api/status
echo
echo "=== 7. security headers actually returned ==="
curl -sI -m 10 http://127.0.0.1:8080/ | grep -iE 'content-security|strict-transport|x-frame|x-content|referrer|server:'
echo
echo "=== 8. does the panel shell out as root? ==="
ps -o user,pid,cmd -p "$(systemctl show -p MainPID --value xui-sub-panel)" 2>/dev/null
echo
echo "=== 9. token file perms + length ==="
wc -c < /opt/nuc-sub/.webpanel-token
echo
echo "=== 10. ssh exposure ==="
grep -E '^(Port|PermitRootLogin|PasswordAuthentication|PubkeyAuthentication)' /etc/ssh/sshd_config 2>/dev/null
