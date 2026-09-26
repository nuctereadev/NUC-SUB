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

- Ready-made themes: 33 for Pasarguard (Jinja2) and 31 for 3x-ui (Go), from
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

Download the installer, check it, then run it as root:

```bash
curl -fsSLO https://raw.githubusercontent.com/nuctereadev/NUC-SUB/v2.2.1/install.sh
curl -fsSLO https://raw.githubusercontent.com/nuctereadev/NUC-SUB/v2.2.1/install.sh.sha256
sha256sum -c install.sh.sha256 && bash install.sh
```

> **Do not pipe the installer into `bash`.** It runs as root, and
> `bash <(curl ...)` executes whatever the network delivered at that instant
> with no way to inspect it first. `install.sh` is pinned to an immutable
> release tag and verifies every file it downloads against `MANIFEST.sha256`,
> so a corrupted or altered payload aborts the install.
>
> Being straight about the limits: `install.sh.sha256` is served from the same
> host as `install.sh`, so it catches truncation and CDN mixups but *not* an
> attacker who can rewrite both. Checksums stop a bad transfer; they do not
> stop a compromised repository. For a real trust anchor, compare the digest
> against one you obtained out-of-band, and pin updates with
> `NUC_SUB_EXPECT_SHA=<commit>`.

### Supply chain

Three layers, each covering what the one above it cannot:

| Layer | Stops | Does not stop |
| --- | --- | --- |
| Pinned ref (`v2.2.1`, never `main`) | Silent branch-tip swaps, CDN mixups | A rewritten tag |
| `MANIFEST.sha256` per-file check | Corrupt or altered payload bytes | A self-consistent forged manifest |
| minisign signature + pinned key id | Forged manifests, swapped signing keys | A host serving both a new key *and* a new fingerprint |

Every release is pinned to a tag and every downloaded byte is checksummed
before it is written into the root-owned install directory. Releases also carry
a detached minisign signature over `MANIFEST.sha256`; the installer verifies it
before downloading any payload, and refuses outright if the key id does not
match the one compiled into the installer.

**The signature is only as good as your comparison.** `MINISIGN_PUBKEY` is
served from the same repository as the manifest, so an attacker who can rewrite
one can rewrite the other. The trust anchor is the key id printed by the
installer, compared against the fingerprint published in
[`README.md`](#release-signing-key) over a channel you already trust. If you
cannot get that fingerprint anywhere but the same host that served the
installer, you have checksums, not authentication — and that is a property of
GitHub, not of this project.

Set `NUC_SUB_REQUIRE_SIG=1` to make an unverifiable release a hard failure
instead of a warning.

You will be asked which panel to install for:

```
Select your VPN panel:
  1) 3x-ui (Sanaei)   — Go html/template themes (subThemeDir)
  2) Pasarguard       — self-contained Jinja2 templates
```

Only the selected panel's files are downloaded. A single default theme
(`volt`) is preloaded so the subscription page has a theme immediately;
the remaining themes are downloaded the first time they are applied.

The installer then drops you into the interactive menu.

### Non-interactive install

For cloud-init, scripts, or automation:

```bash
NUC_SUB_PANEL=3xui XUI_SUB_NONINTERACTIVE=1 bash install.sh
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
 ★  volt              downloaded

✓ Active: volt
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
├── themes/                    # 3x-ui themes (Go html/template), 31 themes
├── pasarguard-themes/
│   └── subscription/          # Pasarguard themes (Jinja2), 33 files
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

- Installs and payload fetches are pinned to an immutable release tag and every
  downloaded file is verified against `MANIFEST.sha256`; a mismatch is deleted
  and the install aborts rather than continuing with unverified code.
- Releases carry a detached minisign signature over the manifest, verified
  before any payload is written, with the key id pinned in the installer. See
  [Supply chain](#supply-chain).
- The web panel binds to `127.0.0.1` only and runs as the unprivileged
  `nucsub-web` user. It is reachable exclusively through an SSH tunnel:
  `ssh -L 8080:127.0.0.1:8080 <server>`.
- The panel escalates to root through a single sudoers policy limited to
  `nucsub status|list|reset|apply|remove`. A shell, a `bash -c`, or any extra
  argument is refused, and the panel cannot write its own code.
- The web panel token lives in `/opt/nuc-sub/.webpanel-token`, root-owned and
  group-readable only by `nucsub-web`; the panel re-reads it when it changes, so
  rotating it with the CLI takes effect immediately.
- Every API endpoint requires the `Authorization: Bearer <token>` header; the
  token is compared with `hmac.compare_digest` to prevent timing attacks, and it
  is never accepted as a URL query parameter.
- Security headers on all responses: `Content-Security-Policy`,
  `Referrer-Policy: no-referrer`, `Strict-Transport-Security`,
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Cache-Control:
  no-store`, and a `Server` header that does not advertise the Python build.
- Theme names are validated against a strict allowlist before any filesystem or
  database operation, and settings are written through `textContent` so stored
  values cannot become markup.
- `PrivateTmp=true` is set on the unit. `NoNewPrivileges` is deliberately
  **not** set: the panel needs to escalate through the sudoers policy above, and
  that escalation cannot work under `NoNewPrivileges`. Least privilege comes
  from the non-root user plus the narrow sudoers rule, not from that flag.
- `SUB_PANEL_HOST` is not a supported variable. The bind address is `NP_HOST` in
  the unit's environment file, defaulting to `127.0.0.1`; the CLI passes
  `--host "${NP_HOST}"` to the server.

---

## Release signing key

Releases are signed with a minisign key whose secret never lives in this
repository. The public key id published here is the value to compare against
what the installer prints:

```
# Not yet published.
#
# When a key is added this section reads:
#
#   minisign public key id:
#     RWQf6LRCGA9i53mlYecO4IzT51QuEHiY9MS7NyDWK2Y
#
#   Verify the key itself once, over a channel you already trust:
#     curl -fsSLO https://raw.githubusercontent.com/nuctereadev/NUC-SUB/v2.2.1/MINISIGN_PUBKEY
#     minisign -P -p MINISIGN_PUBKEY
#
# The installer prints the same id. If they differ, stop.
```

Until a key is published, releases are checksum-only: `install.sh` warns once
and continues, because a key id cannot be pinned to a key that does not exist
yet. `NUC_SUB_REQUIRE_SIG=1` turns that warning into a failure.

To publish a key:

1. Generate it on a machine that cannot push to this repository:
   `minisign -G -p MINISIGN_PUBKEY -s /secure/path/minisign.key`
2. `bash tools/sign-manifest.sh` — regenerates the manifest, signs it, writes
   the public key, and prints the key id.
3. Set `NUC_SUB_EXPECT_KEY_ID` in both `install.sh` and `cli/nucsub` to that id,
   and paste it into the block above.
4. Commit `MANIFEST.sha256`, `MANIFEST.sha256.minisig` and `MINISIGN_PUBKEY`,
   then tag. `tools/sign-manifest.sh` refuses to sign if the private key is
   inside the working tree.

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