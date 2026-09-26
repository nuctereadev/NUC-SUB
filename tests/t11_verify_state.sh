#!/bin/bash
rm -f /root/t11_rotate_subid.py /root/t11_diag.sh /root/t11_client_probe.sh
echo "leftovers : $(ls -d /root/t11* 2>/dev/null || echo none)"
echo "x-ui      : $(systemctl is-active x-ui)"
echo "sub-panel : $(systemctl is-active xui-sub-panel)"
DB=/etc/x-ui/x-ui.db
echo "theme dir : $(sqlite3 "$DB" "select value from settings where key='subThemeDir';")"
echo "theme dirs: $(ls /etc/x-ui/sub_templates | tr '\n' ' ')"
sqlite3 -header -column "$DB" "select email, enable, total_gb, expiry_time from clients;"
sqlite3 -header -column "$DB" "select enable, total, expiry_time, up, down from client_traffics;"
