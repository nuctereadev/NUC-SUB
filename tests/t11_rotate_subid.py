#!/usr/bin/env python3
"""Rotate the subscription id of one client on a live 3x-ui panel.

The old value was published in a public repository, so it is treated as
disclosed.

Two places hold the id and both have to move together: the authoritative
`clients.sub_id` column (which is what the subscription endpoint actually
resolves, and is indexed as idx_clients_sub_id) and the copy embedded in the
inbound's settings JSON. Rotating only the JSON leaves the leaked id working,
because the panel serves the page from the column.

  NUC_EMAIL=... python3 rotate_subid.py [--apply] [--old <current id>]
"""
import json
import os
import secrets
import sqlite3
import subprocess
import sys

DB = os.environ.get("NUC_DB", "/etc/x-ui/x-ui.db")
EMAIL = os.environ["NUC_EMAIL"]
APPLY = "--apply" in sys.argv
OLD = None
if "--old" in sys.argv:
    OLD = sys.argv[sys.argv.index("--old") + 1]


def sub_path(con):
    return con.execute("select value from settings where key='subPath'").fetchone()[0]


def mirror_inbound(con, inbid, new):
    """Keep the inbound's client copy pointing at the same id."""
    row = con.execute("select settings from inbounds where id=?", (inbid,)).fetchone()
    if not row:
        return False
    doc = json.loads(row[0])
    touched = False
    for c in doc.get("clients", []):
        if c.get("email") == EMAIL:
            c["subId"] = new
            touched = True
    if touched:
        con.execute("update inbounds set settings=? where id=?",
                    (json.dumps(doc, indent=2), inbid))
    return touched


def main():
    new = secrets.token_urlsafe(12)
    con = sqlite3.connect(DB)
    row = con.execute("select sub_id from clients where email=?", (EMAIL,)).fetchone()
    if not row:
        print("no client row for %s" % EMAIL)
        return 1
    current = row[0]
    if OLD and current != OLD:
        print("clients.sub_id is %r, not the expected %r - refusing" % (current, OLD))
        return 1
    print("rotating %s: %r -> %s" % (EMAIL, current, new))
    if not APPLY:
        print("dry run; pass --apply to write")
        return 0

    con.execute("update clients set sub_id=? where email=?", (new, EMAIL))
    con.commit()
    inbid = con.execute("select inbound_id from client_traffics where email=?",
                        (EMAIL,)).fetchone()
    if inbid and inbid[0]:
        mirror_inbound(con, inbid[0], new)
        con.commit()

    subprocess.run(["systemctl", "restart", "x-ui"], check=True)
    subprocess.run(["sleep", "6"], check=True)

    base = "https://127.0.0.1:2096" + sub_path(con)

    def probe(sid):
        r = subprocess.run(
            ["curl", "-sk", "-m", "15", "-o", "/tmp/probe.html", "-w", "%{http_code}",
             "-H", "Accept: text/html", base + sid],
            capture_output=True, text=True)
        size = os.path.getsize("/tmp/probe.html") if os.path.exists("/tmp/probe.html") else 0
        os.path.exists("/tmp/probe.html") and os.unlink("/tmp/probe.html")
        return r.stdout.strip(), size

    old_code, old_size = probe(current)
    new_code, new_size = probe(new)
    print("  old id -> HTTP %s (%d bytes)" % (old_code, old_size))
    print("  new id -> HTTP %s (%d bytes)" % (new_code, new_size))
    ok = old_code != "200" and new_code == "200" and new_size > 2000
    print("  verified" if ok else "  VERIFICATION FAILED")
    print("\nnew sub id: %s" % new)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
