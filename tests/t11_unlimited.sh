#!/bin/bash
# Unlimited plan: 3x-ui leaves PageData.Total empty when total==0.
# Every theme that prints "of <total> total" therefore has to cope with that.
REPO=/root/t11/repo
OUT=/root/t11/unlimited
DB=/etc/x-ui/x-ui.db
EMAIL=xzi3b440d4
SUBID=rgxaioe5mngxgxug
PORT=2096
GiB=1073741824
rm -rf "$OUT"; mkdir -p "$OUT"
SUBPATH="$(sqlite3 "$DB" "select value from settings where key='subPath';")"
URL="https://127.0.0.1:$PORT${SUBPATH}${SUBID}"
now=$(date +%s); fut=$((now + 12*86400))

# total = 0  ->  unlimited
sqlite3 "$DB" "update client_traffics set total=0, expiry_time=$fut, up=$((3*GiB)), down=$((40*GiB)), enable=1, reset=0 where email='$EMAIL';"
sqlite3 "$DB" "update clients set total_gb=0, expiry_time=$fut, enable=1 where email='$EMAIL';"
systemctl restart x-ui; sleep 4
echo "total in db = $(sqlite3 "$DB" "select total from client_traffics where email='$EMAIL';")"

for t in $(ls "$REPO/themes"); do
  mkdir -p "/etc/x-ui/sub_templates/$t"
  cp "$REPO/themes/$t/index.html" "/etc/x-ui/sub_templates/$t/index.html"
  chmod 644 "/etc/x-ui/sub_templates/$t/index.html"
  sqlite3 "$DB" "update settings set value='/etc/x-ui/sub_templates/$t' where key='subThemeDir';"
  curl -sk -m 25 -o "$OUT/$t.html" -H 'Accept: text/html' "$URL"
done
echo "rendered: $(ls $OUT/*.html | wc -l)"
