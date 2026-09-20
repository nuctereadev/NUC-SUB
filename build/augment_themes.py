#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
augment_themes.py — NUC-SUB theme augmentation pass (idempotent).

Adds, to EVERY subscription theme (3x-ui themes/ + pasarguard-themes/subscription),
the shared NUC-SUB branding/telegram "slot" system:
  * a Telegram button (id="tgBtn") styled with the theme's own copyAll classes
  * nuc_telegram i18n keys (fa/en) for themes that ship an i18n dict
  * a guarded feature script (<!-- nuc-bs -->) that dynamically injects
    @@TG_CHANNEL@@ / @@BRAND_NAME@@ / @@BRAND_LOGO@@ at runtime
  * for legacy volt (xui) templates: {{ .subSupportUrl }} -> @@TG_CHANNEL@@

Run from the repo root:  python3 build/augment_themes.py
"""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGETS = {
    "xui": os.path.join(ROOT, "themes", "*", "index.html"),
    "xui-build": os.path.join(ROOT, "build", "xui-33", "*", "index.html"),
    "pg": os.path.join(ROOT, "pasarguard-themes", "subscription", "*.html"),
}

TG_BTN_TMPL = (
    '<a id="tgBtn" class="{cls}" href="@@TG_CHANNEL@@" target="_blank" rel="noopener" '
    'style="display:none;grid-column:1/-1" aria-label="Telegram">'
    '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M21.9 4.6c.3-1.2-.9-2.2-2-1.7L2.7 9.7'
    'c-1.2.5-1.1 2.2.1 2.5l4.8 1.3 1.8 5.7c.3 1 1.6 1.3 2.3.5l2.5-2.7 4.6 3.4c.9.6 2.2.2 2.4-.9'
    'l2.7-14.9z"/></svg>'
    '<span data-i18n="nuc_telegram">کانال تلگرام</span></a>\n'
)

FEATURE_SCRIPT = """<!-- nuc-bs -->
<script>
(function(){
  var T='@@TG_CHANNEL@@',N='@@BRAND_NAME@@',L='@@BRAND_LOGO@@';
  function ok(v){return !!v&&v.indexOf('@@')===-1;}
  var lang=(document.documentElement.lang||'fa').toLowerCase();
  var en=lang==='en';
  var lbl=en?'Telegram':'کانال تلگرام';
  var tBtn=document.getElementById('tgBtn');
  if(tBtn&&ok(T)){
    try{tBtn.href=T}catch(e){}
    tBtn.removeAttribute('hidden');tBtn.classList.remove('hidden');
    tBtn.style.display='';
    var s=tBtn.querySelector('span');if(s&&!s.getAttribute('data-dyn'))s.textContent=lbl;
  }
  var nameEl=document.querySelector('.brand-name,.subscription-brand,.brand-title,.site-name');
  var nameOk=ok(N);
  if(nameEl&&nameOk)nameEl.textContent=N;
  var mk=document.querySelector('.brand-mark,.brand-logo,.app-logo,.top-logo,.logo-img,.brand-icon');
  if(mk&&ok(L)&&!mk.firstElementChild){
    mk.innerHTML='';
    var im=document.createElement('img');
    im.src=L;im.alt=nameOk?N:'logo';
    im.style.cssText='width:100%;height:100%;object-fit:contain;display:block';
    mk.appendChild(im);
  }
  var needChip=(!mk&&ok(L))||(!nameEl&&nameOk);
  if(needChip){
    var chip=document.getElementById('nuc-brand-chip');
    if(!chip){
      chip=document.createElement('div');chip.id='nuc-brand-chip';
      if(ok(L)){
        var cim=document.createElement('img');cim.src=L;cim.alt='logo';
        cim.style.cssText='width:auto;height:100%;max-height:36px;display:inline-block;vertical-align:middle';
        chip.appendChild(cim);
      }
      if(nameOk){
        var csp=document.createElement('span');csp.textContent=N;
        csp.style.cssText='vertical-align:middle;font-weight:800;font-size:13px;line-height:36px';
        chip.appendChild(csp);
      }
      chip.style.cssText='display:inline-flex;align-items:center;gap:8px;padding:2px 12px;border-radius:10px;border:1px solid var(--line,#2a2a2a);background:var(--panel,#141414);color:var(--text,#eee);box-shadow:0 4px 14px rgba(0,0,0,.18)';
      var chd=document.querySelector('.controls,.top-actions,.header-actions,.top-buttons,.toolbar,.navbar');
      if(chd){chd.insertBefore(chip,chd.firstChild)}
      else{document.body.appendChild(chip);chip.style.position='fixed';chip.style.top='12px';chip.style.zIndex='9000';chip.style[document.documentElement.dir==='rtl'?'right':'left']='12px'}
    }
  }
})();
</script>
"""

I18N_FA = "nuc_telegram:'کانال تلگرام'"
I18N_EN = "nuc_telegram:'Telegram'"


def find_copyall_class(text):
    m = re.search(r'<[a-zA-Z][^>]*\bid="copyAllBtn"[^>]*>', text)
    if not m:
        return None, None
    tag = m.group(0)
    cm = re.search(r'\bclass="([^"]*)"', tag)
    cls = cm.group(1) if cm else ""
    return m.start(), cls


def add_i18n_keys(text):
    """Insert nuc_telegram after copy_all entries (1st fa, 2nd en) if missing."""
    if re.search(r"nuc_telegram\s*:", text):
        return text, 0
    state = [0]
    pat = re.compile(r"copy_all\s*:\s*('(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")")
    def _rep(m):
        state[0] += 1
        return f"{m.group(0)}, {I18N_FA if state[0] == 1 else I18N_EN}"
    out, n = pat.subn(_rep, text)
    return out, state[0] if n else 0


def augment_file(path):
    orig = open(path, encoding="utf-8").read()
    text = orig

    # 1) legacy volt template: swap go-template var for the NUC-SUB token
    if 'id="tgBtn"' in text and "{{ .subSupportUrl }}" in text:
        text = text.replace("{{ .subSupportUrl }}", "@@TG_CHANNEL@@")

    used_tg = 0

    # 2) generic tgBtn (skip themes that already have one)
    if 'id="tgBtn"' not in text:
        pos, cls = find_copyall_class(text)
        if pos is None:
            print(f"  !! {os.path.basename(path)} has no copyAllBtn — telegram button skipped")
        else:
            text = text[:pos] + TG_BTN_TMPL.format(cls=cls) + text[pos:]
            used_tg = 1

    # 3) nuc_telegram i18n keys when the theme ships an i18n dict
    text, n = add_i18n_keys(text)
    if n:
        used_tg = max(used_tg, 1)

    # 4) feature script (idempotent via marker)
    if "<!-- nuc-bs -->" not in text:
        marker = "<!-- nuc-bs -->"
        idx = text.rfind("</body>")
        if idx == -1:
            print(f"  !! {os.path.basename(path)} has no </body> — script skipped")
        else:
            text = text[:idx] + FEATURE_SCRIPT + "\n" + text[idx:]

    if text != orig:
        open(path, "w", encoding="utf-8", newline="\n").write(text)
        print(f"  updated  {os.path.basename(os.path.dirname(path))}/{os.path.basename(path)}")
    return used_tg


def main():
    for label, pattern in TARGETS.items():
        print(f"[{label}] {pattern}")
        files = sorted(glob.glob(pattern))
        for path in files:
            augment_file(path)
    print("done")


if __name__ == "__main__":
    main()