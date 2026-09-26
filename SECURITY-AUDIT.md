# NUC-SUB — Security Audit (Task 12)

Date: 2026-09-26
Scope: `install.sh`, `cli/nucsub`, `webpanel/server.py`, `webpanel/index.html`,
deployment/service configuration, dependency & supply chain, plus a live
non-destructive check of the running panel.
Method: manual code review (3 independent passes), static greps, and a live
HTTP probe of the deployed panel. No exploitation, no data modification.

---

## Verdict

The panel's authentication core is **sound**: constant-time token comparison,
fail-closed when the token file is missing, realpath containment on static file
serves, strict theme-name validation, `shell=False` for every CLI call, and
server-side enforcement of every action the UI exposes. No path traversal, no
command injection, and no remotely exploitable XSS were found.

The real risk is **not** in the request handler. It is in the **trust chain
around the code**: the product installs and self-updates itself by fetching
unsigned files from a moving GitHub branch and running them as root, and the
admin panel is reachable from the public internet with no transport security.

**Production readiness: acceptable for a single-admin install now that the
panel is loopback-only and unprivileged, and every downloaded root-executed
file is checksum-verified against a pinned release (H1). The one structural gap
left is cryptographic signing of that manifest, which needs a release process
rather than a patch.**

---

## Findings, ranked

### H1 — HIGH · No integrity verification of downloaded, root-executed code
`install.sh:32,136,181,197` · `cli/nucsub:267-273` (+ update path ~1141, 2505-2522)

`REPO_URL` defaults to `https://raw.githubusercontent.com/.../main` and is
overridable via `XUI_SUB_REPO`. `install.sh` and the CLI's update routine fetch
the CLI, the web panel and themes with `curl -fsSL` and then execute/install
them as **root**. `validate_download` only checks that the file exists and does
not look like an HTML error page. There is no `sha256sum`, `sha512sum`, GPG or
minisign anywhere in the project.

*Impact:* compromise of the GitHub account, a force-push, or a MITM at any hop
yields instant root code execution on every machine that installs or updates.
`README.md:58` even recommends `bash <(curl -Ls ...)`, which removes the
user's ability to inspect what they run.

*Fix applied:* the download path is now pinned to an immutable release tag
(`NUC_SUB_REF`, default `v2.2.0`) instead of the moving `main` branch, and
`MANIFEST.sha256` (75 files: the CLI, all web panel assets, 33 themes, 33
Pasarguard templates) is fetched first and used to verify **every** payload
before it lands in a root-owned directory. Verification is fail-closed — a
mismatch, a file missing from the manifest, or an unparseable manifest aborts
the install and deletes the payload rather than warning. The web panel asset
fetch, which installs `server.py` for later execution, no longer degrades to a
`warn` on failure. The self-update path validates the staged tree against its own
manifest before rsyncing, and honours `NUC_SUB_EXPECT_SHA` as an out-of-band
commit pin. `README.md` now documents download → `sha256sum -c` → run.

*Residual risk, stated plainly:* the manifest and the code it describes come
from the same repository, so this defeats corruption, truncation, CDN mixups
and a tampered mirror — but **not** an attacker who can push to the repository.
Closing that last hop needs a manifest signed by a key whose fingerprint is
published somewhere other than the repo it protects (GPG or minisign). Until
that exists, the honest guidance is: pin with `NUC_SUB_EXPECT_SHA`, and treat
the release tag plus `MANIFEST.sha256` as "this is the release I reviewed",
not as "this cannot have been tampered with".

*Two bugs found by the new tests while implementing this:*
- `local root="$1" m="$root/MANIFEST.sha256"` silently produced
  `m=/MANIFEST.sha256`, because bash expands every word of a command *before*
  the builtin assigns. Every update would have been rejected.
- A CRLF manifest (Windows-authored, or any repo with `core.autocrlf` on) left
  a hidden `\r` on each path, so every lookup missed and good releases were
  reported as tampered. Both parsers now strip it.

### H2 — HIGH · Admin panel was publicly reachable over plain HTTP  *(FIXED)*
Live-confirmed before the fix: `http://<host>:8080/` returned `200` from the
public internet, and the token and every settings change travelled in cleartext.

*Fix applied:* the panel now binds **loopback by default** (`--host`, default
`127.0.0.1`, overridable with `NUC_SUB_WEB_HOST=0.0.0.0` for people who put TLS
and a firewall in front). Reach it over an SSH tunnel:
`ssh -L 8080:127.0.0.1:8080 <server>`. HSTS is now sent as well, which becomes
meaningful as soon as TLS terminates in front of it.

### M1 — MEDIUM · Token accepted in the URL query string  *(FIXED)*
`webpanel/server.py:256-259`

`?token=` put the admin token into browser history, proxy/CDN logs and, via the
`Referer` header, into `nuctereadev.github.io` — the page had external links.
The frontend never used the query form.
*Fix applied:* query-string token acceptance removed. Only the `Authorization`
header and the `token` cookie remain.

### M2 — MEDIUM · Missing security headers  *(FIXED)*
Live-confirmed absent: `Content-Security-Policy`, `Strict-Transport-Security`,
`Referrer-Policy`. Only `X-Content-Type-Options` and `X-Frame-Options` were sent.

*Fix applied:* a baseline header set is now emitted on every response. The CSP
omits `script-src` on purpose — the panel is one inline `<script>` plus ~20
inline `onclick=` handlers, so a `script-src` policy is not enforceable without
a refactor. The drop-in subset (`object-src 'none'`, `base-uri 'none'`,
`frame-ancestors 'none'`, `form-action 'self'`) still blocks plugin abuse,
`<base>` hijacking and framing.

### M3 — MEDIUM · `innerHTML` sink fed raw subprocess output  *(FIXED)*
`webpanel/index.html:1053` ← `:1196`

`showToast()` built HTML by concatenating a message; the `nucsub apply` failure
path passed raw `stdout`/`stderr` into it. Not exploitable today (both the
server and the CLI regex-validate theme names, so `<` cannot reach it), but a
`subprocess` output path with no output encoding is a latent stored-XSS that
would steal the `localStorage` token.
*Fix applied:* the icon is built as a DOM node and the message is inserted with
`textContent`. Also escaped the active-theme name in the status bar
(`index.html:1162`), a second latent sink.

### M4 — MEDIUM · CSRF-able state change + no content-type enforcement  *(FIXED)*
`webpanel/server.py` `GET /api/reset`, `_handle_settings_post`

`/api/reset` mutated state over `GET`, so any page could trigger it with an
`<img src=…>` if the browser held the token cookie — no preflight, no CSRF
token. The settings POST parsed the body regardless of `Content-Type`.
*Fix applied:* `/api/reset` is now POST-only (frontend updated); the settings
POST requires `Content-Type: application/json`, which alone forces a preflight
for any cross-origin caller.

### M5 — MEDIUM · Full server/Python version disclosure  *(FIXED)*
Live: `Server: nuc-sub-webpanel/2.2.0 Python/3.12.3`.
*Fix applied:* now `nuc-sub-webpanel`. The product version is kept because it is
useful in bug reports; the interpreter build is not.

### M6 — MEDIUM · Web panel ran as root  *(FIXED)*
The generated unit had `User=root`, so a token compromise was root code
execution, because the panel shells out to the CLI, which writes to `/etc/x-ui`
and restarts services.

*Fix applied:* the panel now runs as a dedicated shell-less system user
(`nucsub-web`, override with `NUC_SUB_WEB_USER=root`) and escalates only through
a fixed-argument sudoers policy that grants exactly `status`, `list`, `reset`,
`apply <name>` and `remove <name>` — with no bare `nucsub` grant, so least
privilege holds. The token stays `root:nucsub-web 0640`, so only root can mint a
new one while the panel can still read it. `sudo -n` is used throughout, so a
broken policy fails closed instead of prompting on a request.

One trade-off, stated plainly: `NoNewPrivileges=true` had to come off the unit,
because setuid escalation is impossible under it. `PrivateTmp=true` is kept.
Full `ProtectSystem=` sandboxing is likewise incompatible with sudo escalation
and is not used.

### L1 — LOW · Unpinned build dependency  *(not shipped)*
`demo/requirements.txt` pins `jinja2>=3.1` with no upper bound.
`demo/` and `tests/` are repo-resident dev tooling and never reach a production
install — `install.sh` copies only `themes/`, `pasarguard-themes/`, `cli/nucsub`
and `webpanel/`. The shipped panel is stdlib-only by design. Still worth
pinning plus a lockfile for reproducible builds; run `pip-audit` against the
resolved version.

### L2 — LOW · Unpinned system packages, failures silently swallowed
`install.sh:221-222` installs `sqlite3`/`sqlite` with `|| true`. If it fails,
`find_sqlite` leaves `_SQLITE=""` and every DB-backed panel setting silently
reads empty — a wrong-state bug that looks like data loss. Distro-signed
repositories, so no third-party-repo risk, but the error should surface.

### L3 — LOW · Token file path published to unauthenticated visitors
`index.html:75,825,934` tell anyone who can load the login page that the token
lives at `/opt/nuc-sub/.webpanel-token`. Static files are served without auth.
Only useful alongside a file-read primitive, so it is defence-in-depth only.
Left as-is deliberately: it is the documented admin workflow.

### L4 — LOW · Plaintext production credentials on disk, uncommitted
`username=…&password=…` in seven `probe_*.sh` files and `.env`. Verified **not**
committed (`.gitignore:11-12,44` covers them, and `git ls-files` returns nothing).
One `git add -f` from being published. **Rotate those credentials** and source
them from the already-ignored `.env`.

### L5 — LOW · Concurrent settings writes can lose updates
`SETTINGS` is a module-global mutated without a lock. Two concurrent saves can
interleave read-modify-write. Only reachable by the authenticated admin, and
`load_settings()` already re-reads from disk to reduce the window.

### L6 — LOW · SVG sanitisation is a blocklist
`server.py` and `index.html` both strip known-dangerous SVG constructs. The
frontend version is *stricter* than the server's. Blocklists are inherently
incomplete, though the logo is rendered through `<img>.src`, where SVG script
cannot execute — so this is defence-in-depth, not a live XSS.

### L7 — INFO · `HEAD` returned 501  *(FIXED)*
`BaseHTTPRequestHandler` had no `do_HEAD`, so health checks and reverse proxies
got `501 Unsupported method`. `do_HEAD` now returns real headers with no body.

### L8 — INFO · Undetermined-version vendored QR library ships in every theme
`demo/qrcode-lib.js` (Kazuhiko Arase QR Code Generator, MIT) is inlined into all
33 themes by `demo/localize.py:156`. The code is pure offline encoding with no
`eval` and no network access, and I am aware of no CVE for it — but the file
carries no version string, so the exact version is a guess. Record the upstream
URL and commit in a `THIRD_PARTY.md` so the next audit does not have to.

---

## Checked and found CLEAN

- **Command injection:** every CLI call uses `shell=False` with an argument list;
  theme names are validated against `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$` in both
  the server and the CLI.
- **Path traversal:** `_send_file` resolves with `realpath` and requires the
  result to stay under the base directory. Encoded traversal (`%2e%2e`) also
  rejected.
- **Token comparison:** `hmac.compare_digest` on every path; fails closed when the
  token file is missing or empty.
- **XSS:** no `eval`, `new Function`, `document.write`, `outerHTML`,
  `insertAdjacentHTML` or jQuery `.html()`. `esc()` covers `& < > " '`. Theme
  names are validated on the client *and* the server. `brand_logo` renders via
  `im.src`, where SVG script cannot run.
- **Client-side-only authorization:** none. Every action the UI exposes is
  independently enforced in `_api`.
- **Secrets in the repo:** no token, password or internal URL in `index.html`.
  Live panel identifiers were removed from the test scripts in `79f5a49`.
- **Brand/telegram/logo input validation:** quotes, backslashes and control
  characters rejected in `brand_name`; `telegram_channel` must match
  `^https://t\.me/[A-Za-z0-9_]{5,}$`; logo data URLs must have magic bytes
  matching the declared MIME type.
- **Live auth behaviour:** `/api/status` returns `401` with no token and `401`
  with a wrong token.

---

## Must fix before public exposure

1. ~~Put the panel behind TLS and restrict it to loopback~~ — **done** (H2).
2. ~~Stop running the web panel as root~~ — **done** (M6).
3. ~~Add integrity verification to the install/update path and pin to a release
   commit~~ (H1) — **done**: pinned release tag + `MANIFEST.sha256` verified
   fail-closed on every download, plus the `NUC_SUB_EXPECT_SHA` pin. Signing the
   manifest is the remaining part and needs a release process, not a code change.
4. Rotate the credentials sitting in `probe_*.sh` / `.env` (L4).

## Worth doing next

- Move inline `onclick=` handlers to `addEventListener` so a real `script-src`
  CSP can be enforced (this is the prerequisite for closing M2 properly).
- Shorten the panel token lifetime / add rotation UI; it currently lives in
  `localStorage` with no expiry, so any future XSS is a permanent token theft.
- Replace the SVG blocklist with an allowlist parser.
- Pin `jinja2`, add a lockfile, and record vendored-library provenance (L1, L8).
- Stop swallowing the `sqlite3` install failure (L2).

## Known-unknowns

- `qrcode-lib.js` exact upstream version (L8).
- Whether any Jinja2 ≥3.1 advisory applies to the version the dev preview
  resolves — no CVE number I am confident enough in to assert; run `pip-audit`.
- SSH hardening, the firewall ruleset, and on-disk permissions could not be
  inspected: the audit host had no SSH key or password available in this
  session, so the live checks were HTTP-only. `tests/t12_live_check.sh` is
  committed and will complete that picture in one run once SSH access is
  available.
