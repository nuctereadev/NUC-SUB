#!/bin/bash
# Remove everything Task 11 staged on the server, then re-assert the production
# baseline so a failed/partial cleanup can never be mistaken for a clean finish.
set -uo pipefail
rm -rf /root/t11
rm -f /root/t11_*.tgz /tmp/t11_* 2>/dev/null
# every theme except the configured one has to be gone from the panel
CUR=$(sqlite3 /etc/x-ui/x-ui.db "select value from settings where key='subThemeDir';")
echo "subThemeDir : $CUR"
echo "theme dirs  : $(ls /etc/x-ui/sub_templates 2>/dev/null | tr '\n' ' ')"
echo "t11 leftovers: $(ls -d /root/t11 2>/dev/null || echo none)"
systemctl is-active x-ui
