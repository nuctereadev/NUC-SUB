#!/usr/bin/env python3
"""Inject a layout/console probe into each rendered subscription page, run it in
real headless Chrome, and read the measurements back out of the dumped DOM.

This replaces eyeballing screenshots: it reports horizontal overflow, elements
that stick out of the viewport, computed fonts, and any JS errors."""
import os
import re
import subprocess
import sys
import tempfile

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

PROBE = r"""
<script>
// Headless virtual time does not advance CSS transitions/animations, so a bar
// that is correctly set to 43.75% still measures 0. Neutralise animation so the
// probe measures real layout instead of the transition's start value.
(function(){
  var s = document.createElement('style');
  s.textContent = '*,*::before,*::after{transition:none !important;animation:none !important}';
  (document.head || document.documentElement).appendChild(s);
})();
window.__errs = [];
window.addEventListener('error', function(e){ window.__errs.push(String(e.message)); });
function nucProbe(){
  var errs = window.__errs;
  var de = document.documentElement;
  var vw = de.clientWidth;
  var over = [];
  var all = document.querySelectorAll('body *');
  for (var i = 0; i < all.length; i++) {
    var el = all[i], r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    if (r.right > vw + 1.5 || r.left < -1.5) {
      var cs = getComputedStyle(el);
      if (cs.position === 'fixed') continue;
      over.push(el.tagName.toLowerCase()
        + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).join('.') : '')
        + ' [' + Math.round(r.left) + '..' + Math.round(r.right) + ']');
    }
  }
  var bars = [];
  document.querySelectorAll('[data-nuc-width]').forEach(function(b){
    var r = b.getBoundingClientRect();
    bars.push(Math.round(r.width) + 'px/' + (b.getAttribute('data-width')||'-')
              + ' parent=' + Math.round(b.parentElement.getBoundingClientRect().width) + 'px');
  });
  var d = document.createElement('div');
  d.id = 'nuc-probe';
  d.textContent = JSON.stringify({
    vw: vw, sw: de.scrollWidth, bw: document.body.scrollWidth,
    hOverflow: de.scrollWidth > vw + 1,
    overCount: over.length, over: over.slice(0, 6),
    barPx: bars, errs: errs.slice(0, 5),
    dir: getComputedStyle(de).direction,
    bodyFont: getComputedStyle(document.body).fontFamily.slice(0, 40)
  });
  document.body.appendChild(d);
}
// themes animate width with a 1.6s CSS transition, so measure well after load
if (document.readyState === 'complete') setTimeout(nucProbe, 2400);
else window.addEventListener('load', function(){ setTimeout(nucProbe, 2400); });
</script>
"""


def probe(path, width, height):
    doc = open(path, encoding="utf-8", errors="replace").read()
    tmp = tempfile.NamedTemporaryFile(
        "w", suffix=".html", delete=False, encoding="utf-8", errors="replace"
    )
    tmp.write(doc.replace("</body>", PROBE + "</body>"))
    tmp.close()
    with tempfile.TemporaryDirectory() as profile:
        r = subprocess.run(
            [
                CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
                "--hide-scrollbars", "--user-data-dir=" + profile,
                "--virtual-time-budget=4000", "--window-size=%d,%d" % (width, height),
                "--dump-dom", "file:///" + tmp.name.replace("\\", "/").lstrip("/"),
            ],
            capture_output=True, text=True, errors="replace", timeout=120,
        )
    os.unlink(tmp.name)
    m = re.search(r'<div id="nuc-probe">(.*?)</div>', r.stdout, re.S)
    if not m:
        return {"error": "probe not found"}
    import html
    import json
    return json.loads(html.unescape(m.group(1)))


if __name__ == "__main__":
    import glob as _glob
    files = []
    for f in sys.argv[1:]:
        files.extend(sorted(_glob.glob(f)) or [f])
    for f in files:
        base = os.path.basename(f)
        for label, w, h in (("desktop", 1280, 900), ("mobile", 390, 844)):
            d = probe(f, w, h)
            flag = "H-OVERFLOW" if d.get("hOverflow") else "ok"
            print(
                "%-26s %-8s vw=%-5s scrollW=%-5s %-11s bars=%-8s dir=%-4s errs=%s"
                % (
                    base, label, d.get("vw"), d.get("sw"), flag,
                    d.get("barPx"), d.get("dir"), d.get("errs") or "none",
                )
            )
            for o in d.get("over", [])[:4]:
                print("      overflow: %s" % o)
            if d.get("error"):
                print("      %s" % d["error"])
