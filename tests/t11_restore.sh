#!/usr/bin/env bash
# Restore the live panel to its production state after QA fixtures.
# Copying a DB file over a live sqlite3 does NOT work (x-ui rewrites it), so
# every change is reverted with explicit SQL and the service is restarted.
#
# The client email / subscription id are live identifiers and must never be
# committed: pass them in, e.g.
#   NUC_EMAIL=... NUC_SUBID=... ./t11_restore.sh
set -uo pipefail
: "${NUC_EMAIL:?set NUC_EMAIL to the client email under test}"
: "${NUC_SUBID:?set NUC_SUBID to the subscription id under test}"
DB=${NUC_DB:-/etc/x-ui/x-ui.db}
EMAIL=$NUC_EMAIL
SUBID=$NUC_SUBID
PORT=${NUC_PORT:-2096}

sqlite3 "$DB" "update clients set total_gb=0, expiry_time=0, enable=1 where email='$EMAIL';"
sqlite3 "$DB" "update client_traffics set up=903, down=3547, total=0, expiry_time=0, enable=1, last_online=1790426360013, last_sub_fetch=1790438727975 where email='$EMAIL';"
sqlite3 "$DB" "update inbounds set settings=replace(settings,'\"enable\":false','\"enable\":true') where id=1;"
sqlite3 "$DB" "update settings set value='/etc/x-ui/sub_templates/volt' where key='subThemeDir';"
