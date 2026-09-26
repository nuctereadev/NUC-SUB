#!/usr/bin/env python3
"""Verify the post-JS status of every rendered theme state in headless Chrome.

Three different mechanisms are in play across the 33 themes, so all three are
read:
  * [data-i18n^="st_"]  - themes that tag the status label
  * the runtime's class/text fallback (cobalt hardcodes the Persian label)
  * volt renders the state server-side via Go conditionals

usage: t11_verify_browser.py <dir-with-renders>
"""
import concurrent.futures as cf
import glob
import html
import json
import os
import re
import subprocess
import sys
import tempfile

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

WORDS = {
    "فعال": "st_active", "غیرفعال": "st_disabled", "منقضی": "st_expired",
    "اتمام حجم": "st_exhausted", "Active": "st_active", "Disabled": "st_disabled",
    "Expired": "st_expired", "Data Exhausted": "st_exhausted",
}
EXPECT = {"expired": "st_expired", "disabled": "st_disabled",
          "exhausted": "st_exhausted", "normal": "st_active"}

PROBE = """
<script>
function nucVerify(){
  var out = {tagged: [], fallback: null, bar: null, errors: []};
  window.onerror = function(m){ out.errors.push(String(m)); };
  document.querySelectorAll('[data-i18n^="st_"]').forEach(function(el){
    out.tagged.push({key: el.getAttribute('data-i18n'),
                     text: (el.textContent||'').trim()});
  });
  var W = __WORDS__;
  var leaves = document.querySelectorAll('body *');
  for (var i = 0; i < leaves.length; i++) {
    var n = leaves[i];
    if (n.children.length) continue;
    var t = (n.textContent||'').trim();
    if (W[t]) { out.fallback = {key: W[t], text: t}; break; }
  }
  var f = document.querySelector('[data-nuc-width]');
  if (f) out.bar = f.style.width;
  var d = document.createElement('div');
  d.id = 'nuc-verify';
  d.textContent = JSON.stringify(out);
  document.body.appendChild(d);
}
if (document.readyState === 'complete') setTimeout(nucVerify, 1200);
else window.addEventListener('load', function(){ setTimeout(nucVerify, 1200); });
</script>
"""


def run(path):
    doc = open(path, encoding="utf-8", errors="replace").read()
    words = json.dumps(WORDS, ensure_ascii=False)
    tmp = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False,
                                     encoding="utf-8", errors="replace")
    tmp.write(doc.replace("</body>", PROBE.replace("__WORDS__", words) + "</body>"))
    tmp.close()
    try:
        with tempfile.TemporaryDirectory() as profile:
            r = subprocess.run(
                [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
                 "--hide-scrollbars", "--user-data-dir=" + profile,
                 "--virtual-time-budget=2500", "--window-size=1280,900",
                 "--dump-dom", "file:///" + tmp.name.replace("\\", "/").lstrip("/")],
                capture_output=True, text=True, errors="replace", timeout=180)
        m = re.search(r'<div id="nuc-verify">(.*?)</div>', r.stdout, re.S)
        if not m:
            return path, {"error": "probe missing"}
        return path, json.loads(html.unescape(m.group(1)))
    except Exception as e:                      # noqa: BLE001
        return path, {"error": str(e)}
    finally:
        os.unlink(tmp.name)


target = sys.argv[1]
paths = sorted(glob.glob(os.path.join(target, "*.html")))
rows, bad = [], 0
with cf.ThreadPoolExecutor(max_workers=4) as ex:
    for path, res in ex.map(run, paths):
        name = os.path.basename(path)[:-5]
        theme, state = name.rsplit("-", 1)
        want = EXPECT[state]
        if "error" in res:
            rows.append((theme, state, "FAIL", res["error"], ""))
            bad += 1
            continue
        keys = [s["key"] for s in res["tagged"]]
        if not keys and res["fallback"]:
            keys = [res["fallback"]["key"]]
        got = keys[0] if keys else None
        if not got:
            rows.append((theme, state, "FAIL", "no status element found", ""))
            bad += 1
        elif got != want:
            rows.append((theme, state, "FAIL", "got %s want %s" % (got, want),
                         ",".join(keys)))
            bad += 1
        elif res["errors"]:
            rows.append((theme, state, "FAIL", "JS error: %s" % res["errors"][:1], ""))
            bad += 1
        else:
            rows.append((theme, state, "ok", got, res["bar"] or "-"))

for theme, state, verdict, detail, bar in rows:
    print("%-4s %-9s %-10s %-28s bar=%s" % (verdict, theme, state, detail, bar))
print("\n%d/%d renders show the correct status in Chrome"
      % (len(rows) - bad, len(rows)))
sys.exit(1 if bad else 0)
