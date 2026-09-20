"""Read-only audit: NUC-SUB PasarGuard themes vs the REAL Pasarguard default
subscription template (github.com/PasarGuard/panel, app/templates/subscription/index.html).

For every theme under pasarguard-themes/subscription/*.html we check presence and
dynamic binding of every capability the real template offers, and flag any
remaining hardcoded literals in dynamic positions or unguarded server-side
division (which would 500 on unlimited accounts where data_limit == 0).

Run: py demo/audit_pg_capabilities.py   (output also written to audit_pg_matrix.txt)
"""
import os, re, sys, glob

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PG_DIR = os.path.join(ROOT, "pasarguard-themes", "subscription")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audit_pg_matrix.txt")

CHECKS = [
    # (key, label, regex, dynamic? )
    ("title_uname", "title username", r"<title>\s*\{\{\s*(?:user\.)?username(?:[^}]*|})"),
    ("uname", "username display", r"\{\{\s*(?:user\.)?username"),
    ("status", "status chip", r"user\.status"),
    ("unlimited", "unlimited-safe limit", r"∞"),
    ("used", "used traffic", r"user\.used_traffic"),
    ("limit", "total limit", r"user\.data_limit"),
    ("pct", "percent", r"user\.used_traffic\s*/\s*user\.data_limit"),
    ("reset", "reset strategy", r"data_limit_reset_strategy"),
    ("expire", "expire", r"user\.expire"),
    ("days", "days left", r"(?:user\.expire\s*-\s*now\(\)|remaining|days_left|daysleft|days-left|ROZ|BAGIM)"),
    ("onhold", "on_hold duration/timeout", r"on_hold_expire_duration|on_hold_timeout"),
    ("announce", "announce", r"if\s+announce"),
    ("announce_url", "announce_url", r"announce_url"),
    ("links", "links loop", r"for\s+(\w+)\s+in\s+links|for\s+link\s+in\s+links"),
    ("link_val", "link value bound", r"data-link|value=[\"']\{\{\s*link"),
    ("copy", "per-link copy", r"copy\(\s*link\)|copyLink\s*\(|nucCopy\s*\(|copy\(\s*text\)|config-copy|copyText\s*\(|doCopy\s*\(|cp\(\s*text\)|copyToClipboard|navigator\.clipboard"),
    ("qr", "QR (data-link + gen)", r"data-link"),
    ("copyall", "copy all", r"copyAll|copy_all|copy-all"),
    ("gate", "links gated by status", r"user\.status\s+in|data-nuc-gated|status!=='"),
    ("apps", "apps section", r"\bapps\b"),
    ("import", "import config", r"app\.import_url|importConfig|ImportConfig|Import Config"),
]

# hardcoded literals that must NOT appear in dynamic spots
LITERALS = [
    (r">\s*43\.75\s*<", "43.75"),
    (r">\s*56\.25\s*<", "56.25"),
    (r">\s*100(?:\.0)?\s*<", "100"),
    (r">\s*43(?:\.8)?\s*%<", "43.8%"),
    (r">\s*56\s*%<", "56%"),
    (r">\s*12\s*<span data-i18n=\"day", "12 day"),
    (r">\s*12(\s*روز\s*باقیمانده)", "12 remaining"),
    (r"2026-\d\d-\d\d", "2026 date"),
    (r"demo\.user", "demo.user"),
    (r">\s*3\s*<", "3 device"),
]

def audit(path):
    txt = open(path, encoding="utf-8").read()
    res = {}
    for key, label, pat, *_ in CHECKS:
        m = re.search(pat, txt, flags=re.I)
        res[key] = bool(m)
    # pct guard: if pct present, is it under an {% if user.data_limit %} guard?
    pct_unguarded = False
    if res["pct"]:
        pct_unguarded = not re.search(
            r"if\s+user\.data_limit[\s\S]{0,400}?user\.used_traffic\s*/\s*user\.data_limit", txt)
    res["pct_unguarded"] = pct_unguarded
    literals = []
    for pat, name in LITERALS:
        if re.search(pat, txt, flags=re.I):
            literals.append(name)
    # static "Active" label that a status chip could bind to
    static_active = bool(re.search(r"data-i18n=['\"]st_active|>[^a-zA-Z<]*Active[^a-zA-Z<]*<", txt))
    return res, literals, static_active

def main():
    theme_files = sorted(glob.glob(os.path.join(PG_DIR, "*.html")))
    lines = []
    lines.append("capability matrix (x = present, - = MISS):")
    header = ["theme".ljust(10)] + [c[0].ljust(12) for c in CHECKS] + ["pct_ung".ljust(7), "literal", "static_act"]
    lines.append("|".join(header))
    misses_total = {}
    for f in theme_files:
        name = os.path.basename(f)[:-5]
        res, lits, sact = audit(f)
        row = [name.ljust(10)]
        for key, *_ in CHECKS:
            row.append(("x" if res[key] else "-").ljust(12))
        row.append(("!!" if res["pct_unguarded"] else "ok").ljust(7))
        row.append((",".join(lits) if lits else "-").ljust(12))
        row.append("A" if sact else "-")
        lines.append("|".join(row))
        for key, *_ in CHECKS:
            if not res[key]:
                misses_total[key] = misses_total.get(key, 0) + 1
        if res["pct_unguarded"]:
            misses_total["pct_unguarded"] = misses_total.get("pct_unguarded", 0) + 1
    lines.append("")
    lines.append("MISSING-COUNT SUMMARY:")
    for key, cnt in sorted(misses_total.items()):
        lines.append(f"  {key:<20} missing in {cnt}/33")
    with open(OUT, "w", encoding="utf-8") as fp:
        fp.write("\n".join(lines) + "\n")
    print("\n".join(lines))

if __name__ == "__main__":
    main()