#!/bin/bash
# Unlimited plan: a total of 0 must still render as the infinity sign.
# research/service.go defaults PageData.Total to "∞" and only overwrites it when
# the plan has a real byte limit, so this checks the templates do not defeat it.
#
# The client email / subscription id are live identifiers and must never be
# committed: pass them in, e.g.
#   NUC_EMAIL=... NUC_SUBID=... ./t11_unlimited.sh
set -uo pipefail
: "${NUC_EMAIL:?set NUC_EMAIL to the client email under test}"
: "${NUC_SUBID:?set NUC_SUBID to the subscription id under test}"
REPO=${NUC_REPO:-/root/t11/repo}
OUT=${NUC_OUT:-/root/t11/unlimited}
DB=${NUC_DB:-/etc/x-ui/x-ui.db}
EMAIL=$NUC_EMAIL
SUBID=$NUC_SUBID
PORT=${NUC_PORT:-2096}
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
