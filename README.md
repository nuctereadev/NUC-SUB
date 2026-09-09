# NUC-SUB

**Subscription page theme engine for 3x-ui (Sanaei) and Pasarguard VPN panels.**

NUC-SUB installs modern, switchable subscription page themes onto your existing
panel. It ships a lightweight Bash CLI (`nucsub`), an optional web management
panel (3x-ui only), and a library of self-contained themes per panel. The
install preloads a single default theme; every other theme is fetched from
GitHub on demand the first time you apply it, keeping the installer fast and
small.

---

## Features

- Ready-made themes: 33 for Pasarguard (Jinja2) and 23 for 3x-ui (Go), from
  the classic `gradient` / `volt` / `arctic` designs to dozens of modern ones
  (`indigo`, `zenith`, `ocean`, `command`, ...).
- Two rendering engines: Go `html/template` for 3x-ui (via `subThemeDir`) and
  Jinja2 for Pasarguard (`SUBSCRIPTION_PAGE_TEMPLATE`).
- Lightweight web panel for 3x-ui — pure HTML/CSS/JS frontend with a small
  Python 3 standard-library HTTP server. No Node.js, no external CDNs.
- Single-command CLI with automatic panel detection.
- One-line installer that asks which panel to target and downloads only the
  files that panel needs.
- On-demand theme downloads at apply time; parallel asset fetching with
  timeouts so a slow network cannot stall the apply.
- Admin-token authentication for the web panel with constant-time comparison.
- Local fonts and icons (3x-ui) — no third-party CDN dependencies.
- Interactive setup menu opens automatically after installation.

---

## Supported panels

| Panel             | Mechanism                                       | Theme format      |
|-------------------|-------------------------------------------------|-------------------|
| 3x-ui (Sanaei)    | `subThemeDir` setting in the panel database     | Go `html/template`|
| Pasarguard        | `SUBSCRIPTION_PAGE_TEMPLATE` in the panel `.env`| Self-contained Jinja2 |

---

## Requirements

- Root access on the target server.
- Bash 4 or newer.
- `curl` (installed on virtually all distributions).
- `sqlite3` for 3x-ui (auto-installed by the installer when missing).
- Python 3 plus `curl` for Pasarguard API access.

---

## Quick start

Run the installer as root:

```bash
bash <(curl -Ls https://raw.githubusercontent.com/nuctereadev/NUC-SUB/main/install.sh)
```

You will be asked which panel to install for:

```
Select your VPN panel:
  1) 3x-ui (Sanaei)   — Go html/template themes (subThemeDir)
  2) Pasarguard       — self-contained Jinja2 templates
```

Only the selected panel's files are downloaded. A single default theme
(`gradient`) is preloaded so the subscription page has a theme immediately;
the remaining themes are downloaded the first time they are applied.

The installer then drops you into the interactive menu.

### Non-interactive install

For cloud-init, scripts, or automation:

```bash
NUC_SUB_PANEL=3xui XUI_SUB_NONINTERACTIVE=1 bash <(curl -Ls https://raw.githubusercontent.com/nuctereadev/NUC-SUB/main/install.sh)
```

`NUC_SUB_PANEL` accepts `3xui` or `pasarguard` and defaults to auto-detection
based on the panels installed on the server.

---

## Command-line usage

```
nucsub [command] [args...]
```

| Command                  | Description                                                    |
|--------------------------|----------------------------------------------------------------|
| `nucsub list`            | List themes with download and active status                    |
| `nucsub download <name>` | Download a theme without applying it                           |
| `nucsub apply <name>`    | Download (if needed) and activate a theme                      |
| `nucsub reset`           | Return to the panel's built-in subscription page               |
| `nucsub remove <name>`   | Remove a theme completely                                      |
| `nucsub status`          | Show panel, database, paths, and service information           |
| `nucsub webpanel ...`    | Control the web panel (`start`, `stop`, `restart`, `status`, `token`) |
| `nucsub telegram ...`    | View or set the Telegram channel shown inside themes           |
| `nucsub update`          | Pull the latest version from GitHub and reinstall              |
| `nucsub uninstall`       | Remove the CLI, themes, web panel, and database setting        |
| `nucsub menu`            | Open the interactive menu (default with no arguments)          |
| `nucsub version`         | Show the installed version                                     |

Example output of `nucsub list`:

```
Installed Themes
──────────────────────────────────────────────
     arctic            not downloaded
 ★  gradient          downloaded
     volt              not downloaded

✓ Active: gradient
  Running 'nucsub apply' downloads a theme automatically.
```

---

## Interactive menu

```
Main Menu

  1) Apply theme       — list all themes, pick one & activate
  2) Reset to default  — back to panel built-in page
  3) Remove theme      — delete a theme completely
  4) Web panel         — start/stop web UI (token auth)
  5) Update NUC-SUB    — pull latest from GitHub
  6) Uninstall         — remove everything
  7) Status & info     — panel DB, service, paths
  0) Exit
```

The menu opens automatically after installation and can be reopened anytime
with `nucsub menu`.

---

## Web panel (optional)

The web panel is **not** installed or started by default. Start it from menu
option 4 or with:

```bash
nucsub webpanel start
```

- Default port: `8080` (overridable via the `SUB_PANEL_PORT` environment variable).
- A bearer token is generated on first start and printed to the console. Retrieve
  it any time with `nucsub webpanel token`.
- The panel lets you list themes, activate a theme, return to the panel default,
  remove themes, and configure the Telegram channel shown inside themes.
- Served files and API responses are marked `Cache-Control: no-store`.

The web panel runs on the same port as before if you restart it; it is managed
as a systemd service (`xui-sub-panel`).

---

## Themes

3x-ui renders the subscription page with Go `html/template`. Every theme in this
project is self-contained — fonts and icons are served locally, with no external
CDN requests:

| Field             | Meaning                                        |
|-------------------|------------------------------------------------|
| `.sId`            | Subscription ID                                |
| `.enabled`        | Whether the subscription is active (boolean)   |
| `.download`/`.upload` | Formatted download/upload traffic          |
| `.total`/`.used`/`.remained` | Total, used, and remaining traffic   |
| `.expire`         | Expiry timestamp in seconds (`0` = unlimited)  |
| `.subTitle`/`.subSupportUrl`/`.announce` | Title, support link, announcement |
| `.links`/`.emails`| List of links and their matching emails        |

Theme sources live under `themes/<name>/` (3x-ui) and
`pasarguard-themes/subscription/<name>.html` (Pasarguard). You can add your own
theme by dropping a directory in the same layout under `themes/` and activating
it with `nucsub apply <name>`.

---

## Project structure

```
NUC-SUB/
├── install.sh                 # One-line installer
├── cli/nucsub                 # Bash CLI and interactive menu
├── webpanel/                  # Optional web management panel (3x-ui)
│   ├── server.py              # HTTP server (Python 3 standard library)
│   ├── index.html             # Web interface (plain HTML/JS/CSS)
│   ├── css/                   # Local font/icon stylesheets
│   ├── fonts/                 # IRANSansX font files
│   └── fa/                    # FontAwesome glyphs
├── themes/                    # 3x-ui themes (Go html/template), 8 themes
├── pasarguard-themes/
│   └── subscription/          # Pasarguard themes (Jinja2), 8 files
├── LICENSE                    # MIT
└── README.md
```

---

## How it works

**3x-ui:** `nucsub apply <name>` copies the theme from `themes/<name>` to
`/etc/x-ui/sub_templates/<name>/`, writes its path to the `subThemeDir` key in
the panel database, and restarts the panel so the new page is served
immediately.

**Pasarguard:** `nucsub apply <name>` copies the Jinja2 template to the panel's
templates directory, sets `SUBSCRIPTION_PAGE_TEMPLATE` in the panel `.env`, and
applies it (restarting the panel when needed). In both cases VPN clients keep
receiving normal subscription configs; only the human-facing page changes.

---

## Security

- The web panel token is stored in `/opt/nuc-sub/.webpanel-token` with mode
  `0600`; the systemd unit loads panel secrets from a `0600` environment file.
- Every API endpoint requires the `Authorization: Bearer <token>` header;
  tokens are compared with `hmac.compare_digest` to prevent timing attacks.
- Security headers are set on all responses: `X-Content-Type-Options: nosniff`,
  `Cache-Control: no-store`, and `X-Frame-Options`.
- Theme names are validated against a strict allowlist pattern before any
  filesystem or database operation.
- The systemd unit runs with `NoNewPrivileges=true` and `PrivateTmp=true`.
- The web panel binds to all interfaces by default; restrict it to trusted IPs
  in your firewall, or set the `SUB_PANEL_HOST` environment variable.

---

## Troubleshooting

| Symptom                                     | Likely cause / fix                                                        |
|---------------------------------------------|---------------------------------------------------------------------------|
| `nucsub list` shows `not downloaded`        | Expected after a fresh install — apply the theme once; it is fetched on demand. |
| Applying a theme fails with a fetch error   | The server cannot reach `raw.githubusercontent.com`; check outbound HTTPS. |
| Web panel is not reachable                  | Start it with `nucsub webpanel start` and open the printed Firewall port. |
| Subscription page shows the panel default   | Run `nucsub apply <name>` again; confirm the panel is running.            |
| `sqlite3: not found`                     | The installer should install it; otherwise install the `sqlite3` package. |

---

## License

MIT — see [LICENSE](LICENSE).

Copyright (c) NUCTEREA — [github.com/nuctereadev](https://github.com/nuctereadev)