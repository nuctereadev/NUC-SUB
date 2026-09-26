#!/usr/bin/env bash
# =============================================================================
#  NUC-SUB — manifest signer (maintainer tool)
#
#  Produces MANIFEST.sha256.minisig, the detached signature that
#  tools/verify-manifest.sh (and install.sh) check before installing anything.
#
#  Run order for a release:
#     bash tools/gen-manifest.sh              # refresh MANIFEST.sha256
#     bash tools/sign-manifest.sh             # sign it, print the fingerprint
#     git add MANIFEST.sha256 MANIFEST.sha256.minisig MINISIGN_PUBKEY
#     git commit && git tag -a vX.Y.Z -m "..."
#
#  KEY HANDLING
#  ------------
#  The private key must never live in this repository or on a machine that can
#  push to it. This script looks for it in, in order:
#     $NUC_SUB_MINISIGN_SECRET   explicit path
#     ~/.config/nuc-sub/minisign.key
#     ~/.minisign/minisign.key
#  and writes the public key to MINISIGN_PUBKEY in the repo root. Publishing the
#  public key is fine; publishing the secret key voids the whole point.
#
#  Trust: the public key is a same-host artifact, so it is not an anchor on its
#  own. Publish MINISIGN_PUBKEY's id in README.md and let readers compare it
#  over an independent channel. tools/verify-manifest.sh additionally pins the
#  id so a swapped key file is caught even if re-signed.
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BOLD='\033[1m'; NC='\033[0m'
[[ -t 1 ]] || { RED=''; GREEN=''; YELLOW=''; BOLD=''; NC=''; }
die() { echo -e "${RED}$*${NC}" >&2; exit 1; }

command -v minisign >/dev/null 2>&1 || die "minisign is not installed (apt-get install -y minisign)"

find_secret() {
  local c
  for c in "${NUC_SUB_MINISIGN_SECRET:-}" \
           "$HOME/.config/nuc-sub/minisign.key" \
           "$HOME/.minisign/minisign.key"; do
    [[ -n "$c" && -f "$c" ]] && { echo "$c"; return 0; }
  done
  return 1
}

SECRET="$(find_secret || true)"
if [[ -z "$SECRET" ]]; then
  die "no minisign secret key found.
  Generate one on a machine that is NOT this repo's build host:
      minisign -G -p MINISIGN_PUBKEY -s /secure/path/minisign.key
  Then point this script at it:
      NUC_SUB_MINISIGN_SECRET=/secure/path/minisign.key bash tools/sign-manifest.sh"
fi
if [[ "$SECRET" == "$ROOT/"* ]]; then
  die "refusing to sign: the secret key is inside the repository ($SECRET).
  A private key in the repo is a public private key. Move it out first."
fi
chmod 600 "$SECRET" 2>/dev/null || true

# Always sign the current tree state, so the signature cannot describe bytes
# that differ from what ships.
if ! bash tools/gen-manifest.sh; then
  die "gen-manifest.sh failed; refusing to sign a manifest that does not match the tree"
fi

minisign -S -s "$SECRET" -m MANIFEST.sha256 -x MANIFEST.sha256.minisig \
  || die "minisign failed"
minisign -P -p "$SECRET" > MINISIGN_PUBKEY 2>/dev/null \
  || die "could not derive the public key"

KEY_ID="$(minisign -P -p MINISIGN_PUBKEY | tr -d '[:space:]')"

echo
echo -e "${GREEN}✓ wrote MANIFEST.sha256.minisig${NC}"
echo -e "${GREEN}✓ wrote MINISIGN_PUBKEY${NC}"
echo
echo -e "${BOLD}Public key id:${NC} $KEY_ID"
echo
echo -e "${BOLD}Next steps${NC}"
echo "  1. Add the pubkey to git:"
echo "       git add MANIFEST.sha256 MANIFEST.sha256.minisig MINISIGN_PUBKEY"
echo "  2. Pin the id so verification cannot be satisfied by a swapped key."
echo "     Set NUC_SUB_EXPECT_KEY_ID in install.sh and cli/nucsub to:"
echo "       $KEY_ID"
echo "  3. Publish that same id in README.md so readers can compare it over a"
echo "     channel other than this repository."
echo "  4. Confirm the secret key is NOT in the working tree:"
echo "       git status --porcelain | grep -i minisign || echo clean"
echo
echo -e "${YELLOW}Note${NC} $SECRET still holds the private key. Keep it offline;"
echo "if this machine is the build host, remove the copy once the signature is"
echo "pushed and sign future releases from a clean machine."
