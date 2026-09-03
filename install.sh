#!/usr/bin/env bash
# =============================================================================
#  NUC-SUB — one-line installer (by NUCTEREA)
#
#  Installs beautiful, switchable subscription page themes for the 3x-ui
#  (Sanaei) panel, plus a command-line manager (nucsub) and an optional
#  ultra-light web panel (pure HTML/JS/CSS served by Python3).
#
#  Usage:
#    bash <(curl -Ls https://raw.githubusercontent.com/nuctereadev/NUC-SUB/main/install.sh)
#
#  Env for non-interactive installs:
#    XUI_SUB_PORT       port for the web panel (default 8080)
#    XUI_SUB_INSTALL_DIR  install dir (default /opt/nuc-sub)
# =============================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'

# ---- repository source (override for forked/local builds) -------------------
# When running from a git checkout, use local files; otherwise fetch from GitHub.
REPO_URL="${XUI_SUB_REPO:-https://raw.githubusercontent.com/nuctereadev/NUC-SUB/main}"
# Which files to fetch from the source
SRC_FILES=(
  "cli/nucsub"
  "webpanel/server.py"
  "webpanel/index.html"
  "webpanel/css/icons.css"
  "webpanel/css/fonts.css"
  "webpanel/fonts/IRANSansX-Bold.woff2"
  "webpanel/fonts/IRANSansX-Regular.woff2"
  "webpanel/fa/fa-solid-900.woff2"
)

INSTALL_DIR="${XUI_SUB_INSTALL_DIR:-/opt/nuc-sub}"
THEMES_DIR="$INSTALL_DIR/themes"
WEB_DIR="$INSTALL_DIR/webpanel"
CLI_DIR="$INSTALL_DIR/cli"
WEB_PORT="${XUI_SUB_PORT:-8080}"
XUI_SERVICE="x-ui"

# Detected source dir when running from a checkout
LOCAL_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

is_local() {
    [ -f "$LOCAL_SRC/install.sh" ] && [ -f "$LOCAL_SRC/cli/nucsub" ]
}

# ------------------------------------------------------------------- checks ---
[[ "$EUID" -eq 0 ]] || { echo -e "${RED}✗ Please run as root.${NC}"; exit 1; }

# Non-interactive: triggered by env or non-TTY stdin (curl | bash).
if [[ "${XUI_SUB_NONINTERACTIVE:-0}" == "1" ]] || [[ ! -t 0 ]]; then
    NONINTERACTIVE=1
else
    NONINTERACTIVE=0
fi

# Detect OS/distro
if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    DISTRO="$ID"
    VERSION_ID="${VERSION_ID:-}"
else
    DISTRO="unknown"
fi

banner() {
    echo -e "${CYAN}"
    echo "================================="
    echo "       NUC-SUB Installer"
    echo "       by NUCTEREA"
    echo "================================="
    echo -e "${NC}"
}

# ------------------------------------------------------------------ helpers ---
detect_ip() {
    local urls=(
      "https://api4.ipify.org"
      "https://ipv4.icanhazip.com"
      "https://v4.api.ipinfo.io/ip"
    )
    local ip=""
    for u in "${urls[@]}"; do
        ip="$(curl -s --max-time 4 "$u" 2>/dev/null | tr -d '[:space:]')"
        if [[ "$ip" =~ ^[0-9]+(\.[0-9]+){3}$ ]]; then
            echo "$ip"; return 0
        fi
    done
    echo ""
}

gen_token() {
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -hex 24
    else
        head -c 32 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 48
    fi
}

prompt() {  # prompt VAR DEFAULT
    local __var="$1" __default="$2"
    if [[ "$NONINTERACTIVE" == "1" ]]; then
        printf -v "$__var" '%s' "$__default"
    else
        read -rp "» " "$__var"
        [[ -z "${!__var}" ]] && printf -v "$__var" '%s' "$__default"
    fi
}

# ------------------------------------------------------------------ install ---
install_python() {
    # python3 is only needed for the web panel; if absent, warn & skip serve.
    if command -v python3 >/dev/null 2>&1; then
        return 0
    fi
    case "$DISTRO" in
        ubuntu|debian|armbian)
            apt-get update -qq >/dev/null 2>&1
            apt-get install -y -qq python3 >/dev/null 2>&1 || true
            ;;
        fedora|rhel|almalinux|rocky|ol|amzn)
            dnf install -y -q python3 >/dev/null 2>&1 || true
            ;;
        arch|manjaro|parch)
            pacman -Sy --noconfirm python >/dev/null 2>&1 || true
            ;;
    esac
}

copy_from_local() {
    mkdir -p "$CLI_DIR" "$WEB_DIR" "$THEMES_DIR"
    install -m 755 "$LOCAL_SRC/cli/nucsub" "$CLI_DIR/nucsub"
    cp "$LOCAL_SRC/webpanel/server.py" "$LOCAL_SRC/webpanel/index.html" "$WEB_DIR/"
    # web panel static assets (self-hosted fonts + icons)
    cp -r "$LOCAL_SRC/webpanel/css" "$LOCAL_SRC/webpanel/fonts" "$LOCAL_SRC/webpanel/fa" "$WEB_DIR/"
    # themes
    if [[ -d "$LOCAL_SRC/themes" ]]; then
        for d in "$LOCAL_SRC"/themes/*; do
            [[ -d "$d" ]] || continue
            cp -r "$d" "$THEMES_DIR/"
        done
    fi
}

fetch_from_github() {
    mkdir -p "$CLI_DIR" "$WEB_DIR" "$THEMES_DIR"
    local f name
    for f in "${SRC_FILES[@]}"; do
        mkdir -p "$INSTALL_DIR/$(dirname "$f")"
        curl -fsSL "$REPO_URL/$f" -o "$INSTALL_DIR/$f" || { echo -e "${RED}✗ Failed to fetch $f${NC}"; exit 1; }
    done
    chmod 755 "$CLI_DIR/nucsub"
    # fetch themes, each with its self-hosted css / fonts / fa assets
    for theme in minimal gradient matrix glass neon; do
        local td="$THEMES_DIR/$theme"
        mkdir -p "$td/css" "$td/fonts" "$td/fa"
        curl -fsSL "$REPO_URL/themes/$theme/index.html" -o "$td/index.html" \
            || { echo -e "${RED}✗ Failed to fetch theme $theme${NC}"; }
        curl -fsSL "$REPO_URL/themes/$theme/css/icons.css" -o "$td/css/icons.css" \
            || { echo -e "${RED}✗ Failed to fetch theme $theme css/icons.css${NC}"; }
        curl -fsSL "$REPO_URL/themes/$theme/css/fonts.css" -o "$td/css/fonts.css" \
            || { echo -e "${RED}✗ Failed to fetch theme $theme css/fonts.css${NC}"; }
        curl -fsSL "$REPO_URL/themes/$theme/fonts/IRANSansX-Bold.woff2" -o "$td/fonts/IRANSansX-Bold.woff2" \
            || { echo -e "${RED}✗ Failed to fetch theme $theme font${NC}"; }
        curl -fsSL "$REPO_URL/themes/$theme/fonts/IRANSansX-Regular.woff2" -o "$td/fonts/IRANSansX-Regular.woff2" \
            || { echo -e "${RED}✗ Failed to fetch theme $theme regular font${NC}"; }
        curl -fsSL "$REPO_URL/themes/$theme/fa/fa-solid-900.woff2" -o "$td/fa/fa-solid-900.woff2" \
            || { echo -e "${RED}✗ Failed to fetch theme $theme icons${NC}"; }
    done
}

banner
echo -e "${BLUE}→ 1/5 Install dir: ${NC}$INSTALL_DIR"

mkdir -p "$INSTALL_DIR"
if is_local; then
    echo -e "${GREEN}✓ Using local source from this checkout${NC}"
    copy_from_local
else
    echo -e "${BLUE}→ Fetching source from GitHub...${NC}"
    fetch_from_github
fi

echo -e "${BLUE}→ 2/5 Ensuring prerequisites...${NC}"
install_python
if ! command -v sqlite3 >/dev/null 2>&1; then
    case "$DISTRO" in
        ubuntu|debian|armbian) apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq sqlite3 >/dev/null 2>&1 || true ;;
        fedora|rhel|almalinux|rocky|ol|amzn) dnf install -y -q sqlite >/dev/null 2>&1 || true ;;
        arch|manjaro|parch) pacman -Sy --noconfirm sqlite >/dev/null 2>&1 || true ;;
    esac
fi

echo -e "${BLUE}→ 3/5 Detecting panel...${NC}"
XUI_DB=""
for p in /etc/x-ui/x-ui.db /etc/3x-ui/db/x-ui.db; do
    if [[ -f "$p" ]]; then XUI_DB="$p"; break; fi
done
if [[ -z "$XUI_DB" ]]; then
    echo -e "${YELLOW}⚠ No 3x-ui database found. Themes are installed, but 'nucsub apply' needs"
    echo -e "   an existing 3x-ui (Sanaei) panel to write subThemeDir.${NC}"
else
    echo -e "${GREEN}✓ Found panel DB: $XUI_DB${NC}"
fi

echo -e "${BLUE}→ 4/5 Configuring web panel...${NC}"
token="$(gen_token)"
cat > "$INSTALL_DIR/.webpanel-token" <<< "$token"
chmod 600 "$INSTALL_DIR/.webpanel-token"

# write a small config used by nucsub / server
cat > "$INSTALL_DIR/config.env" <<EOF
SUB_TEMPLATES_DIR=$INSTALL_DIR
SUB_PANEL_PORT=$WEB_PORT
SUB_PANEL_HOST=0.0.0.0
SUB_PANEL_TOKEN=$token
XUI_DB=$XUI_DB
EOF
chmod 600 "$INSTALL_DIR/config.env"

echo -e "${BLUE}→ 5/5 Registering web-panel service...${NC}"
cat > /etc/systemd/system/xui-sub-panel.service <<SERVICE
[Unit]
Description=NUC-SUB web panel (by NUCTEREA)
After=network.target
[Service]
Type=simple
User=root
WorkingDirectory=$WEB_DIR
EnvironmentFile=$INSTALL_DIR/config.env
ExecStart=/usr/bin/env python3 $WEB_DIR/server.py --port "$WEB_PORT" --token "$token" --base $WEB_DIR --cli $CLI_DIR/nucsub --themes $THEMES_DIR --db "$XUI_DB"
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload >/dev/null 2>&1 || true
systemctl unmask xui-sub-panel >/dev/null 2>&1 || true
systemctl enable xui-sub-panel >/dev/null 2>&1 || true
systemctl restart xui-sub-panel >/dev/null 2>&1 || true

IP="$(detect_ip)"
cat > "$INSTALL_DIR/install-result.txt" <<EOF
URL   : http://${IP:-YOUR_IP}:$WEB_PORT/
TOKEN : $token
CLI   : $CLI_DIR/nucsub
EOF
chmod 600 "$INSTALL_DIR/install-result.txt"

echo ""
echo -e "${GREEN}NUC-SUB installed successfully.${NC}"
echo ""
echo -e "${CYAN}Web panel:${NC}"
echo -e "   URL   : ${BLUE}http://${IP:-YOUR_IP}:$WEB_PORT/${NC}"
echo -e "   Token : ${YELLOW}$token${NC}"
echo ""
echo -e "${CYAN}Quick commands:${NC}"
echo -e "   nucsub menu           ${DIM}# interactive menu (recommended)${NC}"
echo -e "   nucsub --help         ${DIM}# show help${NC}"
echo -e "   nucsub list           ${DIM}# show installed themes${NC}"
echo -e "   nucsub apply gradient ${DIM}# activate a theme${NC}"
echo -e "   nucsub status         ${DIM}# full system info${NC}"
echo ""
echo -e "${CYAN}Installation details:${NC} $INSTALL_DIR/install-result.txt"
echo ""

# Symlink for global access
ln -sf "$CLI_DIR/nucsub" /usr/bin/nucsub 2>/dev/null || \
    cp -f "$CLI_DIR/nucsub" /usr/bin/nucsub && chmod +x /usr/bin/nucsub

# Drop into interactive menu (only if TTY)
if [[ -t 0 && "${SKIP_MENU:-0}" != "1" ]]; then
    echo -e "${YELLOW}Press Enter to open the interactive menu, or Ctrl+C to exit...${NC}"
    read -r _
    exec /usr/bin/nucsub
fi
