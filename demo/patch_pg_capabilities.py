"""Apply the REAL-Pasarguard dynamic-capability patch to every NUC-SUB theme in
pasarguard-themes/subscription/*.html.

Reference: github.com/PasarGuard/panel  app/templates/subscription/index.html
(context keys: user, links, announce, announce_url, apps; filters: datetime,
bytesformat, int, replace; global: now()).

What the patch adds/fixes per theme (idempotent, guarded by -- data-nuc-pgcap --):
  1. unlimited-safe progress percentage (server-side division would 500 when
     user.data_limit == 0)
  2. unlimited-safe remaining/total displays (show 'infinity' when unlimited)
  3. expire/None-safe rendering + days-remaining display (datetime filter
     crashes on None)
  4. dynamic status badge bound to user.status.value
  5. status-gated config area (hide links/actions when not active/on_hold)
  6. data_limit_reset_strategy note displayed when != no_reset
  7. on-hold duration/timeout display when status == on_hold
  8. announce_url "More info" link (and a new minimal announce box for themes
     that never had one)
  9. recommended-applications section (apps) with download links + import
 10. dynamic config-count (amber/lime "6 item" literal -> links|length)

Run: py demo/patch_pg_capabilities.py
"""
import os, re, sys, glob

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PG_DIR = os.path.join(ROOT, "pasarguard-themes", "subscription")

MARK = "<!-- data-nuc-pgcap -->"
NO_ANNOUNCE = {"abyss", "coal", "dusk", "gold", "graphite", "marine", "onyx", "steel", "tide", "zenith"}
DAYS_ALREADY = {"abyss", "dusk", "ocean"}  # already carry a days-remaining formula
COUNT6 = {"amber", "lime"}

PCT_OLD = r"\{\{\s*\(user\.used_traffic\s*/\s*user\.data_limit\s*\*\s*100\)\s*\|\s*round\(1\)\s*\}\}"
PCT_NEW = "{% if user.data_limit %}{{ (user.used_traffic / user.data_limit * 100) | round(1) }}{% else %}0{% endif %}"

REMAIN_OLD = r"\{\{\s*\(user\.data_limit\s*-\s*user\.used_traffic\)\s*\|\s*bytesformat\s*\}\}"
REMAIN_NEW = "{% if user.data_limit %}{{ (user.data_limit - user.used_traffic) | bytesformat }}{% else %}∞{% endif %}"

REMAIN_GB_OLD = r"\{\{\s*\(\(user\.data_limit\s*-\s*user\.used_traffic\)\s*/\s*1024\s*\*\*\s*3\)\s*\|\s*round\(2\)\s*\}\}"
REMAIN_GB_NEW = "{% if user.data_limit %}{{ ((user.data_limit - user.used_traffic) / 1024 ** 3) | round(2) }}{% else %}∞{% endif %}"

LIMIT_OLD = r"\{\{\s*user\.data_limit\s*\|\s*bytesformat\s*\}\}"
LIMIT_NEW = "{% if user.data_limit %}{{ user.data_limit | bytesformat }}{% else %}∞{% endif %}"

EXP_DT_OLD = r"\{\{\s*user\.expire\s*\|\s*datetime\s*\}\}"
EXP_DT_GUARD = "{% if user.expire %}{{ user.expire | datetime }}{% else %}∞{% endif %}"
EXP_DT_WITH_DAYS = (
    "{% if user.expire %}{{ user.expire | datetime }}"
    " ({{ ((user.expire - now()) / 86400) | round(0, 'ceil') | int if (user.expire - now()) > 0 else 0 }}"
    " روز باقیمانده){% else %}∞{% endif %}"
)

VOLT_REMAIN_OLD = r"\{\{\s*remaining\s*\|\s*bytesformat\s*\}\}"
VOLT_REMAIN_NEW = REMAIN_NEW

ANNOUNCE_OLD = r"\{\%\s*if\s+announce\s*\%\}\{\{\s*announce\s*\}\}\{%\s*endif\s*%\}"
ANNOUNCE_NEW = ("{% if announce %}{{ announce }}"
                "{% if announce_url %}<a href=\"{{ announce_url }}\" target=\"_blank\" style=\"font-weight:600\">"
                " | اطلاعات بیشتر</a>{% endif %}{% endif %}")

DAYS_OLD = r"\{\{\s*\(\(user\.expire\s*-\s*now\(\)\)\s*/\s*86400\)\s*\|\s*round\(0,\s*'ceil'\)\s*\|\s*int\s+if\s+\(user\.expire\s*-\s*now\(\)\)\s*>\s*0\s+else\s*0\s*\}\}"
DAYS_NEW = ("{% if user.expire %}{{ ((user.expire - now()) / 86400) | round(0, 'ceil') | int "
            "if (user.expire - now()) > 0 else 0 }}{% else %}0{% endif %}")


def _guarded_expire_window(txt, pos):
    pre = txt[max(0, pos - 160):pos]
    return "{% if user.expire %}" in pre and pre.count("{% if user.expire %}") > pre.count("{% endif %}")


def _guarded_window(txt, pos):
    """True if an open {% if user.data_limit %} / {% if not user.data_limit %}
    guard exists within the 160 chars before pos and is not yet closed."""
    pre = txt[max(0, pos - 160):pos]
    if "{% if not user.data_limit %}" in pre or "{% if user.data_limit %}" in pre:
        opens = pre.count("{% if user.data_limit %}") + pre.count("{% if not user.data_limit %}")
        closes = pre.count("{% endif %}")
        return opens > closes
    return False


def _guard_all(txt, old, new, skip_guarded=True):
    out, pos = [], 0
    for m in re.finditer(old, txt, flags=re.I):
        out.append(txt[pos:m.start()])
        if skip_guarded and _guarded_window(txt, m.start()):
            out.append(m.group(0))
        else:
            out.append(new)
        pos = m.end()
    out.append(txt[pos:])
    return "".join(out)


PGCAP_HIDDEN = """<i data-nuc-status style="display:none">{{ user.status.value }}</i>
<i data-nuc-reset style="display:none">{{ user.data_limit_reset_strategy.value }}</i>
<i data-nuc-expire style="display:none">{% if user.expire %}{{ user.expire | datetime }}{% endif %}</i>
<i data-nuc-onhold-dur style="display:none">{% if user.on_hold_expire_duration %}{{ user.on_hold_expire_duration }}{% endif %}</i>
<i data-nuc-onhold-until style="display:none">{% if user.on_hold_timeout %}{{ user.on_hold_timeout | datetime }}{% endif %}</i>
"""

PGS_ANNOUNCE_BOX = """{% if announce %}<div id="nucCapAnnounce" dir="rtl">{{ announce }}{% if announce_url %}<br><a href="{{ announce_url }}" target="_blank">اطلاعات بیشتر</a>{% endif %}</div>{% endif %}
"""

PGS_SUPP = """<div id="nucCapSupp" dir="rtl" style="display:none">
  <span data-nuc="cap-reset"></span>
  <span data-nuc="cap-onhold-dur"></span>
  <span data-nuc="cap-onhold-until"></span>
</div>
"""

PGS_APPS = """{% if apps %}
<section data-nuc="pgcap-apps" dir="rtl" style="margin:14px auto;max-width:760px">
  <h2 style="margin:0 0 10px;font-size:1.05rem;font-weight:700">اپلیکیشن‌های پیشنهادی</h2>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px">
  {% for app in apps %}
    <div style="border:1px solid rgba(127,127,127,.3);border-radius:12px;padding:12px;display:flex;flex-direction:column;gap:6px">
      <div style="display:flex;align-items:center;gap:10px">
        {% if app.icon_url %}<img src="{{ app.icon_url }}" alt="{{ app.name }}" style="width:36px;height:36px;border-radius:8px;object-fit:cover;flex:none" loading="lazy">{% endif %}
        <div style="min-width:0">
          <h3 style="margin:0;font-size:.95rem;font-weight:700">{{ app.name }}{% if app.recommended %} <span style="font-weight:400;font-size:.7rem;opacity:.75">(توصیه‌شده)</span>{% endif %}</h3>
          {% if app.platform %}<span style="font-size:.7rem;opacity:.75">{{ app.platform.value }}</span>{% endif %}
        </div>
      </div>
      {% if app.description and app.description["en"] %}<p style="margin:0;font-size:.8rem;opacity:.85">{{ app.description["en"] }}</p>{% endif %}
      {% if app.download_links %}
      <div style="font-size:.78rem;opacity:.9">
        {% for link in app.download_links %}{% if link.language.value == 'en' %}<a href="{{ link.url }}" target="_blank" style="display:inline-block;margin-right:8px;text-decoration:underline">{{ link.name }}</a>{% endif %}{% endfor %}
      </div>
      {% endif %}
      {% if app.import_url %}<button type="button" onclick="window.open('{{ app.import_url }}','_blank')" style="align-self:flex-start;border:none;background:rgba(127,127,127,.25);color:inherit;padding:6px 14px;border-radius:8px;font-size:.8rem;cursor:pointer">Import Config</button>{% endif %}
    </div>
  {% endfor %}
  </div>
</section>
{% endif %}"""

PGS_STYLE = """<style data-nuc="pgcap">
#nucCapAnnounce{margin:10px auto;padding:10px 14px;border:1px solid rgba(127,127,127,.3);border-radius:12px;background:rgba(127,127,127,.08);font-size:.85rem;max-width:760px}
#nucCapAnnounce a{font-weight:600}
#nucCapSupp{margin:10px auto;border:1px solid rgba(127,127,127,.25);border-radius:10px;padding:8px 12px;font-size:.8rem;line-height:1.9;max-width:760px}
#nucCapSupp a{font-weight:600}
[data-nuc-gated]{display:none!important}
</style>
"""

PGS_BRIDGE = """<script data-nuc="pgcap">
(function(){
  function t(sel){var el=document.querySelector(sel);return el?el.textContent.replace(/\\s+/g,' ').trim():'';}
  var status=t('[data-nuc-status]')||'active';
  var reset=t('[data-nuc-reset]')||'no_reset';
  var onholdDur=t('[data-nuc-onhold-dur]');
  var onholdUntil=t('[data-nuc-onhold-until]');
  var badge=document.querySelector('[data-i18n="st_active"]');
  if(badge){
    badge.textContent=status;
    badge.removeAttribute('data-i18n');
    var map={active:'#16a34a',limited:'#dc2626',on_hold:'#8b5cf6',expired:'#f59e0b',disabled:'#6b7280'};
    var c=map[status]||'#16a34a';
    try{badge.style.color='#fff';badge.style.background=c;badge.style.borderColor=c;}catch(e){}
  }
  if(status!=='active' && status!=='on_hold'){
    document.querySelectorAll('[data-link]').forEach(function(el){el.setAttribute('data-nuc-gated','');});
    ['#copyAllBtn','#qrBtn'].forEach(function(s){var el=document.querySelector(s);if(el)el.setAttribute('data-nuc-gated','');});
    document.querySelectorAll('.actions').forEach(function(el){el.setAttribute('data-nuc-gated','');});
  }
  var us=parseFloat(t('[data-nuc-used]')), lm=parseFloat(t('[data-nuc-limit]'));
  var pct = (isFinite(us)&&isFinite(lm)&&lm>0) ? Math.min(100,us/lm*100) : 0;
  document.querySelectorAll('[data-nuc-bar-rem]').forEach(function(el){var p=100-pct;el.style.width=p+'%';el.setAttribute('data-width',String(p));});
  var items=[];
  if(reset && reset!=='no_reset') items.push('<div>ریست دوره‌ای حجم: '+reset+'</div>');
  if(status==='on_hold'){
    if(onholdDur){var days=Math.round(parseFloat(onholdDur)/86400);items.push('<div>نگهداری: '+days+' روز</div>');}
    if(onholdUntil) items.push('<div>نگهداری تا: '+onholdUntil+'</div>');
  }
  var supp=document.getElementById('nucCapSupp');
  if(supp&&items.length){supp.innerHTML=items.join('');supp.style.display='block';}
})();
</script>
</div>"""


def _patch_announce_blocks(txt):
    out, pos, n = [], 0, 0
    for m in re.finditer(ANNOUNCE_OLD, txt, flags=re.I):
        out.append(txt[pos:m.start()])
        out.append(ANNOUNCE_NEW)
        pos = m.end()
        n += 1
    out.append(txt[pos:])
    return "".join(out), n


def patch(name):
    path = os.path.join(PG_DIR, f"{name}.html")
    txt = open(path, encoding="utf-8").read()
    already = MARK in txt

    # always-run guard for pre-existing days-remaining formula (idempotent)
    out, pos = [], 0
    for m in re.finditer(DAYS_OLD, txt, flags=re.I):
        out.append(txt[pos:m.start()])
        if _guarded_expire_window(txt, m.start()):
            out.append(m.group(0))
        else:
            out.append(DAYS_NEW)
        pos = m.end()
    if out:
        out.append(txt[pos:])
        txt = "".join(out)

    if already:
        open(path, "w", encoding="utf-8").write(txt)
        return f"{name}: already patched, skip"
    edits = []

    n0 = len(re.findall(PCT_OLD, txt, flags=re.I))
    txt = re.sub(PCT_OLD, PCT_NEW, txt, flags=re.I)
    edits.append(f"pct-guard x{n0}")

    n1 = len(re.findall(REMAIN_OLD, txt, flags=re.I))
    txt = _guard_all(txt, REMAIN_OLD, REMAIN_NEW)
    edits.append(f"remain-guard x{n1}")
    n1b = len(re.findall(REMAIN_GB_OLD, txt, flags=re.I))
    txt = _guard_all(txt, REMAIN_GB_OLD, REMAIN_GB_NEW)
    edits.append(f"remain-gb-guard x{n1b}")

    n2 = len(re.findall(VOLT_REMAIN_OLD, txt, flags=re.I))
    txt = re.sub(VOLT_REMAIN_OLD, VOLT_REMAIN_NEW, txt, flags=re.I)
    edits.append(f"volt-remaining x{n2}")

    n3 = len(re.findall(LIMIT_OLD, txt, flags=re.I))
    txt = _guard_all(txt, LIMIT_OLD, LIMIT_NEW)
    edits.append(f"limit-guard x{n3}")

    exp_list = list(re.finditer(EXP_DT_OLD, txt, flags=re.I))
    if exp_list:
        out, pos = [], 0
        for m in exp_list:
            out.append(txt[pos:m.start()])
            out.append(EXP_DT_GUARD if name in DAYS_ALREADY else EXP_DT_WITH_DAYS)
            pos = m.end()
        out.append(txt[pos:])
        txt = "".join(out)
        edits.append(f"expire-guard+days x{len(exp_list)}")

    txt, nan = _patch_announce_blocks(txt)
    edits.append(f"announce+url x{nan}")

    if name in COUNT6:
        n5 = len(re.findall(r"</h2>\s*<span>\s*6\s*مورد\s*</span>", txt))
        txt = re.sub(r"</h2>\s*<span>\s*6\s*مورد\s*</span>",
                     "</h2><span>{{ links | length }} مورد</span>", txt)
        edits.append(f"config-count x{n5}")

    block = MARK + "\n" + PGCAP_HIDDEN + PGS_STYLE
    if name in NO_ANNOUNCE:
        block += PGS_ANNOUNCE_BOX
    block += PGS_SUPP + PGS_APPS + PGS_BRIDGE
    txt = txt.replace("</body>", block + "\n</body>", 1)

    open(path, "w", encoding="utf-8").write(txt)
    return f"{name}: {' | '.join(edits)}  (len {txt.__len__()})"


def main():
    names = [os.path.basename(p)[:-5] for p in sorted(glob.glob(os.path.join(PG_DIR, "*.html")))]
    for name in names:
        print(patch(name))


if __name__ == "__main__":
    main()