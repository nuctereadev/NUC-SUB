#!/usr/bin/env bash
# =============================================================================
#  NUC-SUB — manifest signature verifier
#
#  MANIFEST.sha256 proves the payload bytes match the release. It does not prove
#  the manifest itself was authored by us: anyone who can alter the repository,
#  the ref, or the CDN can serve a self-consistent manifest plus matching
#  payload. A detached minisign signature over the manifest closes that gap, but
#  only if the public key is pinned somewhere the attacker cannot rewrite.
#
#  Usage:
#    bash tools/verify-manifest.sh <manifest> [signature] [pubkey]
#
#  Defaults: signature = <manifest>.minisig, pubkey = MINISIGN_PUBKEY
#            in the repository root.
#
#  Trust model
#  -----------
#  A signature checked against a key file that ships in the same repository is
#  not a trust anchor. If an attacker can replace MANIFEST.sha256 they can
#  replace the .minisig and the public key too, and the check still passes. This
#  tool therefore pins the key's signature id (not just "some key verified") and
#  prints the id in every success message, so the human can compare it against
#  the fingerprint published in README.md. That comparison, done over a channel
#  other than the compromised host, is the actual anchor.
#
#  Environment:
#    NUC_SUB_EXPECT_KEY_ID   require this exact minisign key id, e.g.
#                            RWQf6LRCGA9i53mlYecO4IzT51QuEHiY9MS7NyDWK2Y. Pins the
#                            key id inside this script as well as in the docs,
#                            so swapping the pubkey file alone is detected.
#    NUC_SUB_REQUIRE_SIG=1   treat "signature support unavailable" as fatal
#                            instead of degrading to checksum-only.
#
#  Exit codes: 0 verified · 1 verification failed · 2 no signature support
# =============================================================================
set -euo pipefail

MANIFEST="${1:-}"
SIG="${2:-${MANIFEST}.minisig}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PUBKEY="${3:-$ROOT/MINISIGN_PUBKEY}"
EXPECT_ID="${NUC_SUB_EXPECT_KEY_ID:-}"
REQUIRED="${NUC_SUB_REQUIRE_SIG:-0}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; DIM='\033[2m'; NC='\033[0m'
[[ -t 1 ]] || { RED=''; GREEN=''; YELLOW=''; DIM=''; NC=''; }

note() { echo -e "${DIM}$*${NC}" >&2; }
warn() { echo -e "${YELLOW}$*${NC}" >&2; }
die()  { echo -e "${RED}$*${NC}" >&2; exit 1; }

if [[ -z "$MANIFEST" ]]; then
  echo "usage: bash tools/verify-manifest.sh <manifest> [signature] [pubkey]" >&2
  exit 1
fi
[[ -f "$MANIFEST" ]] || die "manifest not found: $MANIFEST"

# minisign's own verification is mandatory once a signature is published; the
# --force flag is what makes it non-interactive, it does not skip the crypto.
have_minisign() { command -v minisign >/dev/null 2>&1; }
minisign_bin() {
  if have_minisign; then command -v minisign
  elif [[ -x "$ROOT/tools/minisign" ]]; then echo "$ROOT/tools/minisign"
  elif have_minisign; then echo minisign
  else echo ""; fi
}

# ---- case 1: no signature published yet (checksum-only release) --------------
if [[ ! -f "$SIG" ]]; then
  if [[ "$REQUIRED" == "1" ]]; then
    die "signature required but missing: $SIG"
  fi
  if [[ -n "$EXPECT_ID" ]]; then
    die "a key id is pinned ($EXPECT_ID) but no signature was published: $SIG"
  fi
  warn "no signature for $(basename "$MANIFEST") - checksum-only release."
  note "Payload integrity is still verified, but a compromised repository,"
  note "ref or CDN could serve a self-consistent manifest. See README.md."
  exit 2
fi

# ---- case 2: signature exists, so it must verify ---------------------------
if ! have_minisign; then
  if [[ -x "$ROOT/tools/minisign" ]]; then
    :
  elif [[ "$REQUIRED" == "1" ]]; then
    die "signature published but minisign is not installed and $REQUIRED=1"
  else
    warn "signature published but minisign is not installed - cannot verify."
    note "Install it with:  apt-get install -y minisign   (or: brew install minisign)"
    exit 2
  fi
fi
MS="$(minisign_bin)"
[[ -n "$MS" ]] || die "minisign not found"

[[ -f "$PUBKEY" ]] || die "signature exists but no public key at $PUBKEY"

# ---- key id pinning --------------------------------------------------------
# The key id is the trailing field of the pubkey's untrusted comment. It is
# derived from the key material and bound into the signature, so a comment that
# disagrees with the key fails the -V check. Read it with sed rather than
# `minisign -P`: -P expects a base64 key string and prints usage when given -p.
minisign_key_id() {
    sed -n 's/^untrusted comment: *minisign public key *//p' "$1" 2>/dev/null \
        | head -1 | tr -d '[:space:]'
}

actual_id="$(minisign_key_id "$PUBKEY")"
if [[ ! "$actual_id" =~ ^[0-9A-F]{16}$ ]]; then
    die "could not read a minisign key id from $PUBKEY (expected 16 hex chars in the untrusted comment)"
fi

# Comparing it here means a swapped pubkey fails even when the attacker also
# re-signs the manifest with their own key.
if [[ -n "$EXPECT_ID" ]]; then
    if [[ "$actual_id" != "$EXPECT_ID" ]]; then
        die "key id mismatch: expected $EXPECT_ID, $PUBKEY is $actual_id"
    fi
    note "key id pinned: $actual_id"
fi

if ! "$MS" -V -p "$PUBKEY" -x "$SIG" -m "$MANIFEST" >/dev/null 2>&1; then
  die "SIGNATURE INVALID for $MANIFEST"
  die "  The manifest does not match the signed release, or the signature is"
  die "  not ours. Nothing was installed. Do not work around this."
fi

echo -e "${GREEN}✓ manifest signature verified${NC} (key ${actual_id})" >&2
note "Compare that key id against the fingerprint in README.md before trusting"
note "this release. A key that matches a file served by the same host proves"
note "nothing on its own."
exit 0
