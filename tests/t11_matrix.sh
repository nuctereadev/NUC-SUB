#!/usr/bin/env bash
# Render every Sanaei theme through the REAL 3x-ui in each client state.
#
# 3x-ui switches a client's enable bit off by itself both when its expiry passes
# and when its quota runs out, so `enabled=false` on its own cannot identify the
# cause. The expired fixture is given time to settle and the expired pass runs
# LAST so it is a stable state rather than a race, and every pass pins the
# traffic figures it needs so no state can inherit the previous one's quota.
set -uo pipefail

# The client email / subscription id are live identifiers and must never be
# committed: pass them in, e.g.
#   NUC_EMAIL=... NUC_SUBID=... ./t11_matrix.sh
: "${NUC_EMAIL:?set NUC_EMAIL to the client email under test}"
: "${NUC_SUBID:?set NUC_SUBID to the subscription id under test}"
REPO=${NUC_REPO:-/root/t11/repo}
OUT=${NUC_OUT:-/root/t11/out}
DB=${NUC_DB:-/etc/x-ui/x-ui.db}
EMAIL=$NUC_EMAIL
SUBID=$NUC_SUBID
PORT=${NUC_PORT:-2096}
GiB=1073741824
mkdir -p "$OUT"

SUBPATH="$(sqlite3 "$DB" "select value from settings where key='subPath';")"
URL="https://127.0.0.1:$PORT${SUBPATH}${SUBID}"
days_ms(){ echo $(( $(date +%s) + $1 * 86400 ))000; }
THEMES=$(ls "$REPO/themes")

set_traffic() {   # total expiry up down
    sqlite3 "$DB" "update client_traffics set total=$1, expiry_time=$2, up=$3, down=$4, enable=1 where email='$EMAIL';"
    sqlite3 "$DB" "update clients set total_gb=$1, expiry_time=$2, enable=1 where email='$EMAIL';"
}

set_enable() {    # 0 | 1
    sqlite3 "$DB" "update clients set enable=$1 where email='$EMAIL';"
    sqlite3 "$DB" "update client_traffics set enable=$1 where email='$EMAIL';"
}

render() {        # $1 theme $2 state
    local file="$OUT/$1-$2.html"
    local tpl="/etc/x-ui/sub_templates/$1"
    mkdir -p "$tpl"
    cp "$REPO/themes/$1/index.html" "$tpl/index.html"
    chmod 644 "$tpl/index.html"
    sqlite3 "$DB" "update settings set value='$tpl' where key='subThemeDir';"
    local code size fb toks
    code="$(curl -sk -m 25 -o "$file" -w '%{http_code}' -H 'Accept: text/html' "$URL")"
    size="$(stat -c %s "$file" 2>/dev/null || echo 0)"
    fb="$(grep -c '__SUB_PAGE_DATA__' "$file")"
    toks="$(grep -o '{{[^}]*}}' "$file" | wc -l)"
    local en
    en="$(grep -o '<i data-nuc-enabled[^>]*>[^<]*</i>' "$file" | sed -e 's/.*>\([^<]*\)<.*/\1/')"
    local exp
    exp="$(grep -o '<i data-nuc-expire-ts[^>]*>[^<]*</i>' "$file" | sed -e 's/.*>\([^<]*\)<.*/\1/')"
    if [[ "$code" == "200" && "$fb" == "0" && "$size" -gt 2000 && "$toks" == "0" ]]; then
        printf 'ok    %-9s %-10s size=%-7s enabled=%-5s expire=%s\n' "$1" "$2" "$size" "$en" "$exp"
    else
        printf 'FAIL  %-9s %-10s http=%s size=%s fallback=%s unrendered=%s\n' \
            "$1" "$2" "$code" "$size" "$fb" "$toks"
    fi
}

echo "########## normal ##########"
set_traffic $((100*GiB)) "$(days_ms 12)" $((3*GiB)) $((40*GiB))
systemctl restart x-ui; sleep 4
for t in $THEMES; do render "$t" normal; done
echo

echo "########## exhausted ##########"
# 3x-ui also switches a client off the moment its quota runs out, so the render
# will legitimately carry enabled=false. The theme still has to report the more
# specific "data exhausted" rather than the generic "disabled" x-ui turned it into.
set_traffic $((100*GiB)) "$(days_ms 12)" $((2*GiB)) $((110*GiB))
systemctl restart x-ui; sleep 4
for t in $THEMES; do render "$t" exhausted; done
echo

echo "########## disabled (admin off, time and quota still running) ##########"
# traffic is reset first: leaving the exhausted figures in place would make this
# a second exhausted fixture instead of a hand-disabled client.
set_traffic $((100*GiB)) "$(days_ms 12)" $((3*GiB)) $((40*GiB))
set_enable 0
systemctl restart x-ui; sleep 5
for t in $THEMES; do render "$t" disabled; done
set_enable 1
systemctl restart x-ui; sleep 5
echo

echo "########## expired (settled: 3x-ui will have auto-disabled it) ##########"
set_traffic $((100*GiB)) "$(days_ms -3)" $((3*GiB)) $((40*GiB))
echo "waiting 45s for the panel to auto-disable the lapsed client..."
sleep 45
echo "clients.enable=$(sqlite3 $DB "select enable from clients where email='$EMAIL';")"
for t in $THEMES; do render "$t" expired; done
echo
echo "rendered files : $(ls $OUT/*.html | wc -l)"
