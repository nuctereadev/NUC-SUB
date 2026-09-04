#!/usr/bin/env bash
# =============================================================================
#  NUC-SUB — one-line installer (by NUCTEREA)
#
#  Installs beautiful, switchable subscription page themes for your VPN panel.
#  Supports two panels — you pick one and ONLY that panel's files are
#  downloaded (lightweight install, no extra files):
#
#    1) 3x-ui (Sanaei)   — Go html/template themes via the panel's subThemeDir
#    2) Pasarguard       — self-contained Jinja2 templates in the panel's
#                          CUSTOM_TEMPLATES_DIRECTORY / SUBSCRIPTION_PAGE_TEMPLATE
#
#  The web panel (3x-ui only) is OPTIONAL and is NOT installed by default.
#  After install, the interactive setup menu opens so you can pick a theme right
#  away and, if you want, enable the web panel for 3x-ui from option 6.
#
#  Usage:
#    bash <(curl -Ls https://raw.githubusercontent.com/nuctereadev/NUC-SUB/main/install.sh)
#
#  Env for non-interactive installs:
#    NUC_SUB_PANEL=3xui|pasarguard   panel to install (default: auto-detect)
#    XUI_SUB_INSTALL_DIR             install dir (default /opt/nuc-sub)
#    XUI_SUB_NONINTERACTIVE=1        skip the panel prompt and the menu at the end
# =============================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'
BOLD='\033[1m'; DIM='\033[2m'

# ---- repository source (override for forked/local builds) -------------------
# When running from a git checkout, use local files; otherwise fetch from GitHub.
REPO_URL="${XUI_SUB_REPO:-https://raw.githubusercontent.com/nuctereadev/NUC-SUB/main}"

# Files that are shared by both panels
SRC_COMMON=(
  "cli/nucsub"
)

# Web panel (3x-ui only) — self-hosted fonts + icons
SRC_WEB=(
  "webpanel/server.py"
  "webpanel/index.html"
  "webpanel/css/icons.css"
  "webpanel/css/fonts.css"
  "webpanel/fonts/IRANSansX-Bold.woff2"
  "webpanel/fonts/IRANSansX-Regular.woff2"
  "webpanel/fa/fa-solid-900.woff2"
)

# 3x-ui themes, each with its self-hosted css / fonts / fa assets
XUI_THEMES=(minimal gradient matrix glass neon sunset arctic cyberpunk)

# Pasarguard themes (self-contained Jinja2, one file each, no external assets)
PG_THEMES=(gradient minimal glass sunset matrix neon arctic cyberpunk)

INSTALL_DIR="${XUI_SUB_INSTALL_DIR:-/opt/nuc-sub}"
THEMES_DIR="$INSTALL_DIR/themes"
WEB_DIR="$INSTALL_DIR/webpanel"
CLI_DIR="$INSTALL_DIR/cli"
PG_SRC_DIR="$INSTALL_DIR/pasarguard-themes/subscription"
PANEL_CONF="$INSTALL_DIR/panel.conf"
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
# Panel selection — interactive box or env/auto-detect for non-interactive runs.
PANEL=""
select_panel() {
    if [[ "$NONINTERACTIVE" == "1" ]]; then
        PANEL="${NUC_SUB_PANEL:-${XUI_SUB_PANEL:-}}"
        if [[ -z "$PANEL" ]]; then
            for p in /etc/x-ui/x-ui.db /etc/3x-ui/db/x-ui.db; do
                [[ -f "$p" ]] && { PANEL="3xui"; break; }
            done
            if [[ -z "$PANEL" ]] && { [[ -d /var/lib/pasarguard ]] || [[ -d /opt/pasarguard ]]; }; then
                PANEL="pasarguard"
            fi
            [[ -z "$PANEL" ]] && PANEL="3xui"
        fi
        return 0
    fi
    echo ""
    echo -e "  ${BOLD}Select your VPN panel:${NC}"
    echo -e "  ${GREEN}1)${NC} 3x-ui (Sanaei)   ${DIM}— Go html/template themes (subThemeDir)${NC}"
    echo -e "  ${GREEN}2)${NC} Pasarguard       ${DIM}— self-contained Jinja2 templates${NC}"
    sep
    while true; do
        echo -ne "  ${BOLD}Select option [1-2]: ${NC}"
        read -r choice
        case "$choice" in
            1) PANEL="3xui"; return 0 ;;
            2) PANEL="pasarguard"; return 0 ;;
            *) echo -e "${RED}  Invalid option: $choice${NC}" ;;
        esac
    done
}

fetch_raw() {  # fetch_raw <repo-path> <dest>  — mirrors a raw GitHub file locally
    local f="$1" out="$2"
    mkdir -p "$(dirname "$out")"
    curl -fsSL "$REPO_URL/$f" -o "$out" || { echo -e "${RED}✗ Failed to fetch $f${NC}"; exit 1; }
}

copy_from_local() {  # copy_from_local <src-root> <dest-root> <path...>
    local src="$1" dst="$2"; shift 2
    local p
    for p in "$@"; do
        mkdir -p "$dst/$(dirname "$p")"
        cp -f "$src/$p" "$dst/$p"
    done
}

sep() { echo -e "${DIM}──────────────────────────────────────────────${NC}"; }

banner
select_panel
echo -e "${BLUE}→ 1/4 Panel: ${NC}${BOLD}$PANEL${NC}   ${DIM}Install dir: ${NC}$INSTALL_DIR"

mkdir -p "$INSTALL_DIR" "$CLI_DIR"

# ------------------------------- common (cli/nucsub) --------------------------
if is_local; then
    echo -e "${GREEN}✓ Using local source from this checkout${NC}"
    copy_from_local "$LOCAL_SRC" "$INSTALL_DIR" "${SRC_COMMON[@]}"
    chmod 755 "$CLI_DIR/nucsub"
else
    echo -e "${BLUE}→ Fetching source from GitHub...${NC}"
    for f in "${SRC_COMMON[@]}"; do fetch_raw "$f" "$INSTALL_DIR/$f"; done
    chmod 755 "$CLI_DIR/nucsub"
fi

# ---------------------------- per-panel download ------------------------------
if [[ "$PANEL" == "3xui" ]]; then
    echo -e "${BLUE}→ 2/4 Downloading 3x-ui themes + assets...${NC}"
    if is_local; then
        copy_from_local "$LOCAL_SRC" "$INSTALL_DIR" "${SRC_WEB[@]}"
        mkdir -p "$THEMES_DIR"
        for d in "$LOCAL_SRC"/themes/*; do
            [[ -d "$d" ]] || continue
            cp -r "$d" "$THEMES_DIR/"
        done
    else
        for f in "${SRC_WEB[@]}"; do fetch_raw "$f" "$INSTALL_DIR/$f"; done
        for name in "${XUI_THEMES[@]}"; do
            td="$THEMES_DIR/$name"
            mkdir -p "$td/css" "$td/fonts" "$td/fa"
            curl -fsSL "$REPO_URL/themes/$name/index.html" -o "$td/index.html" \
                || { echo -e "${RED}✗ Failed to fetch theme $name${NC}"; }
            curl -fsSL "$REPO_URL/themes/$name/css/icons.css" -o "$td/css/icons.css" \
                || { echo -e "${RED}✗ Failed to fetch theme $name css/icons.css${NC}"; }
            curl -fsSL "$REPO_URL/themes/$name/css/fonts.css" -o "$td/css/fonts.css" \
                || { echo -e "${RED}✗ Failed to fetch theme $name css/fonts.css${NC}"; }
            curl -fsSL "$REPO_URL/themes/$name/fonts/IRANSansX-Bold.woff2" -o "$td/fonts/IRANSansX-Bold.woff2" \
                || { echo -e "${RED}✗ Failed to fetch theme $name font${NC}"; }
            curl -fsSL "$REPO_URL/themes/$name/fonts/IRANSansX-Regular.woff2" -o "$td/fonts/IRANSansX-Regular.woff2" \
                || { echo -e "${RED}✗ Failed to fetch theme $name regular font${NC}"; }
            curl -fsSL "$REPO_URL/themes/$name/fa/fa-solid-900.woff2" -o "$td/fa/fa-solid-900.woff2" \
                || { echo -e "${RED}✗ Failed to fetch theme $name icons${NC}"; }
        done
    fi
else  # pasarguard
    echo -e "${BLUE}→ 2/4 Downloading Pasarguard Jinja2 templates...${NC}"
    mkdir -p "$PG_SRC_DIR"
    if is_local; then
        cp -f "$LOCAL_SRC"/pasarguard-themes/subscription/*.html "$PG_SRC_DIR/"
    else
        for name in "${PG_THEMES[@]}"; do
            curl -fsSL "$REPO_URL/pasarguard-themes/subscription/$name.html" -o "$PG_SRC_DIR/$name.html" \
                || { echo -e "${RED}✗ Failed to fetch theme $name${NC}"; }
        done
    fi
fi

# Remember the selected panel so `nucsub` knows how to behave
echo "$PANEL" > "$PANEL_CONF"

# Symlink for global access
ln -sf "$CLI_DIR/nucsub" /usr/bin/nucsub 2>/dev/null || \
    cp -f "$CLI_DIR/nucsub" /usr/bin/nucsub && chmod +x /usr/bin/nucsub

# ------------------------------ panel-specific setup --------------------------
if [[ "$PANEL" == "3xui" ]]; then
    # The web panel is OPTIONAL and is never installed here.
    # It is turned on later from the interactive menu (option 6) — nothing is run now.
    echo -e "${BLUE}→ 3/4 Ensuring prerequisites...${NC}"
    if ! command -v sqlite3 >/dev/null 2>&1; then
        case "$DISTRO" in
            ubuntu|debian|armbian) apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq sqlite3 >/dev/null 2>&1 || true ;;
            fedora|rhel|almalinux|rocky|ol|amzn) dnf install -y -q sqlite >/dev/null 2>&1 || true ;;
            arch|manjaro|parch) pacman -Sy --noconfirm sqlite >/dev/null 2>&1 || true ;;
        esac
    fi

    echo -e "${BLUE}→ 4/4 Detecting panel...${NC}"
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
else  # pasarguard
    echo -e "${BLUE}→ 3/4 Detecting Pasarguard panel...${NC}"
    PANEL_DIR=""
    for d in /opt/pasarguard /var/lib/pasarguard; do [[ -d "$d" ]] && { PANEL_DIR="$d"; break; }; done

    if [[ -n "$PANEL_DIR" ]]; then
        echo -e "${GREEN}✓ Found Pasarguard install at $PANEL_DIR${NC}"
        echo -e "${BLUE}→ 4/4 Deploying templates and activating default theme (gradient)...${NC}"
        /usr/bin/nucsub apply gradient 2>&1 | tail -n 5 || \
            echo -e "${YELLOW}⚠ Could not auto-activate. Run 'nucsub apply gradient' after fixing the panel.${NC}"
    else
        echo -e "${YELLOW}⚠ Pasarguard panel not found on this server. Templates were installed to:${NC}"
        echo -e "     $PG_SRC_DIR"
        echo -e "   After installing Pasarguard, deploy them with: ${BOLD}nucsub apply gradient${NC}"
    fi
fi

echo ""
echo -e "${GREEN}NUC-SUB installed successfully.${NC}"
echo ""
if [[ "$PANEL" == "3xui" ]]; then
    echo -e "${CYAN}The web panel is NOT installed by default.${NC}"
    echo -e "  You can choose themes from the terminal now, and enable the"
    echo -e "  web panel later from the menu (${BOLD}option ${GREEN}6${NC}${CYAN}) — it will"
    echo -e "  print a URL and an access token for you to log in.${NC}"
fi
echo ""
echo -e "${CYAN}Quick commands:${NC}"
echo -e "   nucsub apply gradient ${DIM}# activate a theme${NC}"
echo -e "   nucsub list           ${DIM}# show installed themes${NC}"
echo -e "   nucsub menu           ${DIM}# interactive menu${NC}"
echo -e "   nucsub status         ${DIM}# full system info (panel = $PANEL)${NC}"
echo ""

# Drop into the interactive setup/menu so the user can pick a theme.
if [[ -t 0 && "${SKIP_MENU:-0}" != "1" ]]; then
    echo -e "${YELLOW}Opening NUC-SUB setup menu... (Ctrl+C to exit)${NC}"
    sleep 1
    exec /usr/bin/nucsub menu
fi