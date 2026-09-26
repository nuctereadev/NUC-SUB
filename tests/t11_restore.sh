#!/usr/bin/env bash
# Restore the live panel to its production state after QA fixtures.
# Copying a DB file over a live sqlite3 does NOT work (x-ui rewrites it), so
# every change is reverted with explicit SQL and the service is restarted.
set -uo pipefail
DB=/etc/x-ui/x-ui.db
EMAIL=xzi3b440d4
SUBID=rgxaioe5mngxgxug
PORT=2096

sqlite3 "$DB" "update clients set total_gb=0, expiry_time=0, enable=1 where email='$EMAIL';"
sqlite3 "$DB" "update client_traffics set up=903, down=3547, total=0, expiry_time=0, enable=1, last_online=1790426360013, last_sub_fetch=1790438727975 where email='$EMAIL';"
sqlite3 "$DB" "update inbounds set settings=replace(settings,'\"enable\":false','\"enable\":true') where id=1;"
sqlite3 "$DB" "update settings set value='/etc/x-ui/sub_templates/volt' where key='subThemeDir';"

# drop every QA theme, keep only volt
for d in /etc/x-ui/sub_templates/*/; do
    name="$(basename "$d")"
    [ "$name" = "volt" ] || rm -rf "$d"
done

systemctl restart x-ui
sleep 5

SUBPATH="$(sqlite3 "$DB" "select value from settings where key='subPath';")"
URL="https://127.0.0.1:$PORT${SUBPATH}${SUBID}"

echo "subThemeDir : $(sqlite3 $DB "select value from settings where key='subThemeDir';")   (expect /etc/x-ui/sub_templates/volt)"
echo "clients     : $(sqlite3 $DB "select total_gb||'/'||expiry_time||'/'||enable from clients where email='$EMAIL';")   (expect 0/0/1)"
echo "traffic     : $(sqlite3 $DB "select total||'/'||expiry_time||'/'||up||'/'||down from client_traffics where email='$EMAIL';")   (expect 0/0/903/3547)"
echo "inbound json: $(sqlite3 $DB "select case when settings like '%\"enable\":false%' then 'false' else 'true' end from inbounds where id=1;")   (expect true)"
echo "themes dir  : $(ls /etc/x-ui/sub_templates | tr '\n' ' ')"
echo "x-ui        : $(systemctl is-active x-ui) / $(systemctl is-enabled x-ui)"
curl -sk -m 20 -o /tmp/volt_check.html -w 'volt render : http=%{http_code} ' -H 'Accept: text/html' "$URL"
echo "size=$(stat -c %s /tmp/volt_check.html) fallback=$(grep -c '__SUB_PAGE_DATA__' /tmp/volt_check.html)"
