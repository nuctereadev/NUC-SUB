#!/usr/bin/env bash
# =============================================================================
#  NUC-SUB — MANIFEST.sha256 generator (maintainer tool)
#
#  Emits SHA-256 checksums for every file the installer and the CLI download
#  from the repository. install.sh and cli/nucsub verify each download against
#  this manifest and abort on mismatch, so a tampered or corrupted payload can
#  never be written into a root-owned install directory.
#
#  Run this after ANY change to a shipped file, then commit MANIFEST.sha256
#  together with that change. The self-update path re-verifies the manifest, so
#  a stale manifest is a hard failure, not a silent downgrade.
#
#  Usage:  bash tools/gen-manifest.sh [--check]
#    (no flag)  rewrite MANIFEST.sha256
#    --check)   verify the committed manifest matches the tree, exit 1 on drift
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MANIFEST="MANIFEST.sha256"

# Every path reachable from REPO_URL at install/apply/update time.
collect_paths() {
  printf '%s\n' cli/nucsub
  printf '%s\n' webpanel/server.py webpanel/index.html
  printf '%s\n' webpanel/css/icons.css webpanel/css/fonts.css webpanel/css/panel.css
  printf '%s\n' webpanel/fonts/IRANSansX-Bold.woff2 webpanel/fonts/IRANSansX-Regular.woff2
  printf '%s\n' webpanel/fa/fa-solid-900.woff2
  local d
  for d in themes/*/; do
    printf '%s/index.html\n' "${d%/}"
  done
  for d in pasarguard-themes/subscription/*.html; do
    printf '%s\n' "$d"
  done
}

if command -v sha256sum >/dev/null 2>&1; then
  hash_of() { sha256sum -- "$1" | cut -d' ' -f1; }
else
  # BSD/macOS
  hash_of() { shasum -a 256 -- "$1" | cut -d' ' -f1; }
fi

# Fail loudly on a missing file: a silently-skipped path is an unverified path.
paths="$(collect_paths)"
count=0
missing=0
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

while IFS= read -r p; do
  [[ -n "$p" ]] || continue
  if [[ ! -f "$p" ]]; then
    echo "MISSING: $p" >&2
    missing=$((missing + 1))
    continue
  fi
  printf '%s  %s\n' "$(hash_of "$p")" "$p" >>"$tmp"
  count=$((count + 1))
done <<<"$paths"

if [[ "$missing" -gt 0 ]]; then
  echo "error: $missing path(s) listed as shipped but absent from the tree." >&2
  exit 1
fi

if [[ "${1:-}" == "--check" ]]; then
  if [[ ! -f "$MANIFEST" ]]; then
    echo "error: $MANIFEST not found; run 'bash tools/gen-manifest.sh'." >&2
    exit 1
  fi
  if diff -u "$MANIFEST" "$tmp" >/dev/null 2>&1; then
    echo "manifest OK ($count files, no drift)"
    exit 0
  fi
  echo "error: $MANIFEST is stale — a shipped file changed without regenerating it." >&2
  diff -u "$MANIFEST" "$tmp" | head -40 >&2 || true
  exit 1
fi

mv -f "$tmp" "$MANIFEST"
trap - EXIT
echo "wrote $MANIFEST ($count files)"

# Convenience digest for the installer itself, so the documented
# `sha256sum -c install.sh.sha256` step has something to check. Note this file
# is served from the same host as install.sh, so it is a corruption/CDN check,
# not an independent trust anchor: whoever can alter install.sh can alter this
# too. A real anchor means verifying the digest somewhere else.
if [[ -f install.sh ]]; then
    printf '%s  %s\n' "$(hash_of install.sh)" "install.sh" > install.sh.sha256
    echo "wrote install.sh.sha256"
fi
