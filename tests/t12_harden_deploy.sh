#!/bin/bash
# Task 12 deployment: move the NUC-SUB web panel to loopback + a non-root user.
#
#   sudo bash t12_harden_deploy.sh            # apply (rolls back on failure)
#   sudo bash t12_harden_deploy.sh --check    # verify only, change nothing
#   sudo bash t12_harden_deploy.sh --rollback # put the old unit back
#
# Safe to re-run. Every step is verified before the next one starts, and any
# failure restores the backed-up unit automatically.
set -uo pipefail

UNIT="xui-sub-panel"
UNIT_PATH="/etc/systemd/system/${UNIT}.service"
INSTALL_DIR="/opt/nuc-sub"
# Must be under INSTALL_DIR, NOT /run: /run is a tmpfs that is wiped on
# reboot, and EnvironmentFile=- silently tolerates a missing file, which would
# leave the panel starting with no port and no paths after a reboot.
ENV_PATH="${INSTALL_DIR}/.webpanel-env"
SUDOERS="/etc/sudoers.d/nucsub-webpanel"
WEB_USER="${NUC_SUB_WEB_SYSTEM_USER:-nucsub-web}"
BACKUP="/root/.nuc-sub-webunit.bak"
MODE="${1:-apply}"

say()  { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
ok()   { printf '   \033[32mok\033[0m   %s\n' "$*"; }
bad()  { printf '   \033[31mFAIL\033[0m %s\n' "$*"; }

# die() must roll back, not just exit. `exit` does not raise the ERR trap, so
# the trap alone left the panel down after the first failed deploy.
ROLLBACK_ARMED=0
rollback() {
    [ "$ROLLBACK_ARMED" = "1" ] || return 0
    ROLLBACK_ARMED=0
    say "rolling back"
    cp -a "$BACKUP" "$UNIT_PATH" 2>/dev/null
    rm -f "$SUDOERS"
    systemctl daemon-reload 2>/dev/null
    if systemctl restart "$UNIT" 2>/dev/null && systemctl is-active --quiet "$UNIT"; then
        ok "previous unit restored and service is active"
    else
        bad "ROLLBACK FAILED - the panel is down. Restore it with:"
        printf '        cp -a %s %s && systemctl daemon-reload && systemctl restart %s\n' \
            "$BACKUP" "$UNIT_PATH" "$UNIT"
    fi
}
die() {
    printf '\n\033[31mABORT: %s\033[0m\n' "$*"
    rollback
    exit 1
}
trap rollback ERR

[ "$(id -u)" = "0" ] || die "must run as root (use sudo)"

# ---------------------------------------------------------------- check mode
if [ "$MODE" = "--check" ]; then
    say "current state"
    systemctl cat "$UNIT" 2>/dev/null | grep -E '^(User|ExecStart)=' || true
    echo
    echo "   bind:   $(ss -tlnp 2>/dev/null | grep -c "python3.*server.py") listener(s)"
    ss -tlnp 2>/dev/null | grep 'server.py' || true
    echo
    echo "   user:   $(id -u "$WEB_USER" 2>/dev/null || echo "$WEB_USER MISSING")"
    echo "   sudoers: $([ -f "$SUDOERS" ] && echo present || echo absent)"
    echo "   perms:"
    stat -c '     %a %U:%G %n' "$INSTALL_DIR/config.json" \
        "$INSTALL_DIR/.webpanel-token" "$INSTALL_DIR/.webport" 2>/dev/null
    exit 0
fi

# --------------------------------------------------------------- rollback mode
if [ "$MODE" = "--rollback" ]; then
    say "rolling back to the pre-hardening unit"
    [ -f "$BACKUP" ] || die "no backup at $BACKUP"
    cp -a "$BACKUP" "$UNIT_PATH"
    rm -f "$SUDOERS"
    systemctl daemon-reload
    systemctl restart "$UNIT" && ok "old unit restored" || die "restart failed"
    exit 0
fi

# ------------------------------------------------------------------ apply mode
say "1/6  backing up the current unit"
[ -f "$UNIT_PATH" ] || die "no unit at $UNIT_PATH"
[ -f "$BACKUP" ] || cp -a "$UNIT_PATH" "$BACKUP"
ok "backup at $BACKUP"

say "1b/6  checking the installed panel supports --host"
# The unit passes --host, so an older installed server.py would refuse to start
# and take the panel down. Catch that here, before touching anything.
SRV="$INSTALL_DIR/webpanel/server.py"
[ -f "$SRV" ] || die "no installed panel at $SRV"
if ! grep -q -- '--host' "$SRV"; then
    die "the installed $SRV predates --host support. Update the install first
    (nucsub update, or copy webpanel/server.py from a current checkout), then
    re-run this script. Nothing has been changed."
fi
python_ok=$(command -v python3 || true)
[ -n "$python_ok" ] || die "python3 not found"
"$python_ok" -c "import ast,sys; ast.parse(open(sys.argv[1],encoding='utf-8').read())" "$SRV" \
    || die "installed $SRV is not valid Python; refusing to continue"
ok "installed panel supports --host and parses cleanly"

rollback() {
    [ "$ROLLBACK_ARMED" = "1" ] || return 0
    ROLLBACK_ARMED=0
    say "rolling back"
    cp -a "$BACKUP" "$UNIT_PATH" 2>/dev/null
    rm -f "$SUDOERS"
    systemctl daemon-reload 2>/dev/null
    if systemctl restart "$UNIT" 2>/dev/null && systemctl is-active --quiet "$UNIT"; then
        ok "previous unit restored and service is active"
    else
        bad "ROLLBACK FAILED - restore manually with:"
        printf '        cp -a %s %s && systemctl daemon-reload && systemctl restart %s\n' \
            "$BACKUP" "$UNIT_PATH" "$UNIT"
    fi
}
trap rollback ERR

ROLLBACK_ARMED=1

say "2/6  creating the unprivileged system user"
if ! id -u "$WEB_USER" >/dev/null 2>&1; then
    useradd --system --no-create-home --home-dir "$INSTALL_DIR" \
            --shell /usr/sbin/nologin "$WEB_USER" \
        || die "useradd failed (is this a system without useradd? set NUC_SUB_WEB_USER=root)"
    ok "created $WEB_USER"
else
    ok "$WEB_USER already exists"
fi
id -u "$WEB_USER" >/dev/null 2>&1 || die "$WEB_USER still missing"

say "3/6  fixing file ownership"
# The token must stay root-owned so only root can mint a new one; the panel
# user gets group-read. config.json and .webport are written by the panel.
chown "root:$WEB_USER" "$INSTALL_DIR/.webpanel-token" || die "chown token failed"
chmod 640 "$INSTALL_DIR/.webpanel-token"                    || die "chmod token failed"
# config.json must exist and be panel-owned BEFORE the first save: the install
# directory stays root-owned (step below), so the panel can never create a new
# file in it -- a missing config.json means every "save settings" fails with
# EACCES and the panel reports an internal storage error.
CFG="$INSTALL_DIR/config.json"
if [ ! -f "$CFG" ]; then
    printf '{}\n' > "$CFG" || die "cannot create $CFG"
    ok "created $CFG (empty settings)"
fi
chown "$WEB_USER:$WEB_USER" "$CFG" || die "chown config.json failed"
chmod 600 "$CFG"                    || die "chmod config.json failed"
touch "$INSTALL_DIR/.webport"
chown "$WEB_USER:$WEB_USER" "$INSTALL_DIR/.webport"
chmod 644 "$INSTALL_DIR/.webport"
# The panel must be able to traverse into the install dir to read its own code
# and the CLI, but never write to the tree itself.
chmod o+x "$INSTALL_DIR" 2>/dev/null || true
# The panel must be able to read its own code, but never write it.
chown -R "root:$WEB_USER" "$INSTALL_DIR/webpanel"
chmod -R "g+rX,o-rwx" "$INSTALL_DIR/webpanel"
ok "ownership set"
stat -c '     %a %U:%G %n' "$CFG" \
    "$INSTALL_DIR/.webpanel-token" "$INSTALL_DIR/.webport"

say "4/6  installing the least-privilege sudoers policy"
{
    echo "# Managed by nucsub. Grants the web panel exactly the CLI"
    echo "# commands it needs. Regenerated on every service install."
    echo "$WEB_USER ALL=(root) NOPASSWD: $INSTALL_DIR/cli/nucsub status"
    echo "$WEB_USER ALL=(root) NOPASSWD: $INSTALL_DIR/cli/nucsub list"
    echo "$WEB_USER ALL=(root) NOPASSWD: $INSTALL_DIR/cli/nucsub reset"
    echo "$WEB_USER ALL=(root) NOPASSWD: $INSTALL_DIR/cli/nucsub apply [A-Za-z0-9_-]*"
    echo "$WEB_USER ALL=(root) NOPASSWD: $INSTALL_DIR/cli/nucsub remove [A-Za-z0-9_-]*"
    echo "$WEB_USER ALL=(root) NOPASSWD: $INSTALL_DIR/cli/nucsub refresh"
} > "$SUDOERS"
chmod 440 "$SUDOERS"
chown root:root "$SUDOERS"
# A malformed sudoers file locks root out of sudo, so validate before continuing.
visudo -c -f "$SUDOERS" >/dev/null 2>&1 || { rm -f "$SUDOERS"; die "sudoers policy is invalid, removed it"; }
ok "sudoers policy valid"

say "5/6  rewriting the unit: loopback bind + non-root user"
PORT="$(cat "$INSTALL_DIR/.webport" 2>/dev/null | tr -dc '0-9')"
[ -n "$PORT" ] || PORT=8080
DB_ARG=""
[ -e /etc/x-ui/x-ui.db ] && DB_ARG="--db /etc/x-ui/x-ui.db"
PY="$(command -v python3)"

cat > "$ENV_PATH" <<EOF
NP_PORT=$PORT
NP_HOST=127.0.0.1
NP_BASE=$INSTALL_DIR/webpanel
NP_CLI=$INSTALL_DIR/cli/nucsub
NP_THEMES=$INSTALL_DIR/themes
EOF
chmod 600 "$ENV_PATH"

cat > "$UNIT_PATH" <<EOF
[Unit]
Description=NUC-SUB web panel (subscription theme manager)
After=network.target

[Service]
Type=simple
User=$WEB_USER
EnvironmentFile=-$ENV_PATH
ExecStart=$PY $INSTALL_DIR/webpanel/server.py --host \${NP_HOST} --port \${NP_PORT} --base \${NP_BASE} --cli \${NP_CLI} --themes \${NP_THEMES} $DB_ARG
Restart=on-failure
RestartSec=3
PrivateTmp=true
# NoNewPrivileges is deliberately NOT set: the panel escalates through the
# sudoers policy above to run the CLI.

[Install]
WantedBy=multi-user.target
EOF
chmod 644 "$UNIT_PATH"
systemctl daemon-reload
ok "unit written (port $PORT, loopback only)"

say "6/6  restarting and verifying"
systemctl restart "$UNIT" || die "restart failed"
sleep 2
systemctl is-active --quiet "$UNIT" || die "service is not active"

# The panel must now answer on loopback and refuse a privileged identity.
if ! curl -fsS -m 5 "http://127.0.0.1:$PORT/" -o /dev/null; then
    die "panel not answering on 127.0.0.1:$PORT"
fi
ok "answers on 127.0.0.1:$PORT"

# ...and must NOT answer on the public interface any more.
PUBIP="$(hostname -I 2>/dev/null | awk '{print $1}')"
if [ -n "$PUBIP" ] && curl -fsS -m 4 "http://$PUBIP:$PORT/" -o /dev/null 2>/dev/null; then
    die "still reachable on $PUBIP:$PORT -- something else is binding it"
fi
ok "not reachable on $PUBIP:$PORT"

RUNAS="$(systemctl show -p User --value "$UNIT")"
[ "$RUNAS" = "$WEB_USER" ] || die "service is running as '$RUNAS', expected '$WEB_USER'"
ok "running as $RUNAS (not root)"

# The env file must live on disk, not in /run, or the panel breaks on reboot
# because EnvironmentFile=- silently tolerates a missing file.
[ -f "$ENV_PATH" ] || die "env file missing at $ENV_PATH"
case "$ENV_PATH" in
    /run|/tmp|/var/run|/dev/shm) die "env file $ENV_PATH is volatile and would be lost on reboot" ;;
esac
systemctl is-enabled --quiet "$UNIT" || die "service is not enabled; it would not return after a reboot"
ok "env file persists and service is enabled for boot"

# The escalation path must work, otherwise theme actions are broken.
if ! sudo -u "$WEB_USER" sudo -n "$INSTALL_DIR/cli/nucsub" status >/dev/null 2>&1; then
    die "sudoers escalation does not work -- theme actions would fail"
fi
ok "sudoers escalation works"
# `refresh` runs after every settings save. Without this grant the save succeeds
# but the brand/telegram/logo never reaches the subscription pages.
if ! sudo -u "$WEB_USER" sudo -n "$INSTALL_DIR/cli/nucsub" refresh >/dev/null 2>&1; then
    die "sudoers escalation for 'refresh' does not work -- saved settings would never reach the themes"
fi
ok "sudoers refresh escalation works"

# Saving settings must actually work, or the panel reports an internal storage
# error on every save. The install dir is deliberately root-owned (the panel
# must not rewrite the CLI it escalates with), so config.json has to be
# panel-owned and writable on its own.
if ! sudo -u "$WEB_USER" test -w "$INSTALL_DIR/config.json"; then
    die "$WEB_USER cannot write $INSTALL_DIR/config.json -- every settings save would fail"
fi
ok "panel can write its own settings file"
if sudo -u "$WEB_USER" test -w "$INSTALL_DIR"; then
    die "$WEB_USER can write the install tree -- privilege separation is gone"
fi
ok "install tree stays read-only for $WEB_USER"

trap - ERR
ROLLBACK_ARMED=0
say "done"
cat <<EOF

The panel now listens on 127.0.0.1:$PORT only, as $WEB_USER.

Reach it with an SSH tunnel from your machine:

    ssh -L $PORT:127.0.0.1:$PORT <server>

then open http://127.0.0.1:$PORT/

The admin token is unchanged and still in $INSTALL_DIR/.webpanel-token

To go back:
    sudo bash t12_harden_deploy.sh --rollback

To verify later:
    sudo bash t12_harden_deploy.sh --check
EOF
