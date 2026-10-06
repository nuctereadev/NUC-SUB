#!/usr/bin/env python3
"""
Verify MANIFEST.sha256 against the bytes that git actually stores.

`nucsub update` downloads a tarball of the committed tree and refuses to install
if any file disagrees with its manifest entry. That check runs on the server,
against git blobs -- but everything we test locally runs against the working
tree. On Windows those two differ: Path.write_text() and friends leave CRLF in
the checkout, MANIFEST.sha256 is generated over those CRLF bytes, and git stores
LF because .gitattributes says `*.html text eol=lf`. The result is a release
that passes every local test and then fails on every user with:

    Update tree does not match its own MANIFEST.sha256 (33 of 75 file(s))

which is exactly how v2.2.2 shipped. This test compares each manifest entry to
`git show HEAD:<path>` so the mismatch is caught before a tag is pushed.

Skips entries for files that are not committed yet (a brand-new file), by
falling back to the working tree.
"""
import hashlib
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "MANIFEST.sha256"

if not MANIFEST.exists():
    print("SKIP: no MANIFEST.sha256")
    sys.exit(0)


def committed_bytes(path: str) -> tuple[bytes | None, str]:
    r = subprocess.run(["git", "show", f"HEAD:{path}"], cwd=ROOT, capture_output=True)
    if r.returncode == 0:
        return r.stdout, "git blob"
    return None, "uncommitted"


def is_binary(rel: str) -> bool:
    """Honour .gitattributes: binary files legitimately contain arbitrary bytes."""
    try:
        out = subprocess.run(["git", "check-attr", "binary", "--", rel],
                             cwd=ROOT, capture_output=True, text=True).stdout
    except OSError:
        return False
    return ": binary" in out


def main() -> int:
    entries = []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        want, path = line.split(None, 1)
        entries.append((want, path.lstrip("*").strip()))
    if not entries:
        print("FAIL: MANIFEST.sha256 is empty")
        return 1

    mismatches: list[tuple[str, str, str, str]] = []
    crlf: list[str] = []
    blobs = tree = 0

    for want, path in entries:
        f = ROOT / path
        if not f.exists():
            mismatches.append((path, "absent", want, "<file not found>"))
            continue
        raw = f.read_bytes()
        # Only text files can suffer the CRLF problem; a .woff2 legitimately
        # carries 0x0d 0x0a inside compressed data.
        if b"\r\n" in raw and not is_binary(path):
            crlf.append(path)

        data, source = committed_bytes(path)
        if data is None:
            data, source = raw, "working tree"
            tree += 1
        else:
            blobs += 1

        got = hashlib.sha256(data).hexdigest()
        if got != want:
            mismatches.append((path, source, want, got))

        # The second half of the bug: gen-manifest.sh hashes the working tree,
        # so if the checkout is CRLF the manifest itself was generated over CRLF
        # bytes and disagrees with what ships. Comparing only against the git
        # blob would miss that, so the working tree must match the manifest too.
        wt = hashlib.sha256(raw).hexdigest()
        if wt != want:
            mismatches.append((path, "working tree vs manifest", want, wt))

    print(f"compared {len(entries)} manifest entries: "
          f"{blobs} against git blobs, {tree} against the working tree")

    if crlf:
        print(f"\nFAIL: {len(crlf)} tracked file(s) contain CRLF. The manifest is")
        print("generated over these bytes while git stores LF, so the published")
        print("release will not match its own manifest. Normalise to LF:")
        for p in crlf[:10]:
            print(f"  - {p}")
        if len(crlf) > 10:
            print(f"  ... and {len(crlf) - 10} more")

    if mismatches:
        print(f"\nFAIL: {len(mismatches)} manifest entr(ies) do not match what ships:")
        for path, source, want, got in mismatches[:8]:
            print(f"  - {path}  [{source}]")
            print(f"      manifest: {want}")
            print(f"      ships as: {got}")
        if len(mismatches) > 8:
            print(f"  ... and {len(mismatches) - 8} more")

    if crlf or mismatches:
        return 1

    print("PASS  manifest matches the bytes that git actually stores")
    return 0


if __name__ == "__main__":
    sys.exit(main())