#!/usr/bin/env python3
"""Sweep every tracked file for values that must never be published.

Covers the two classes that have actually leaked in this repo's history: live
host/IP pairs and live panel identifiers, plus a few generic secret shapes.
"""
import re
import subprocess

PATTERNS = {
    "public IPv4": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "bearer/token literal": re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{12,}"),
    "uuid": re.compile(r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"),
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "sub-id shaped literal": re.compile(r"\b[a-z0-9]{12,20}\b"),
}

# values that are obviously not secrets and would only be noise
ALLOW = {
    "127.0.0.1", "0.0.0.0", "255.255.255.255", "1.1.1.1", "8.8.8.8",
    "255.255.255.0",
}
# demo/build.py ships a gallery of deliberately fake share links; their ids are
# part of the fixture, not leaked material.
DEMO_FILES = {"demo/build.py"}

files = subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                       check=True).stdout.split()
BIN = {".woff2", ".png", ".jpg", ".jpeg", ".gif", ".zip", ".ico", ".ttf"}

hits = 0
for path in files:
    if path.rsplit(".", 1)[-1].lower() in BIN or path in DEMO_FILES:
        continue
    try:
        doc = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        continue
    for label, pat in PATTERNS.items():
        if label == "sub-id shaped literal":
            continue
        for m in pat.finditer(doc):
            val = m.group(0)
            if val in ALLOW:
                continue
            line = doc[:m.start()].count("\n") + 1
            hits += 1
            print("%-46s %-22s line %-5d %s" % (path, label, line, val[:60]))
print("\n%d candidate leak(s)" % hits)
