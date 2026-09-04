<div dir="rtl">

# 🎨 NUC-SUB

**NUC-SUB یک موتور قالب مدرن برای صفحه سابسکریپشن پنل‌های VPN است که توسط NUCTEREA توسعه داده شده است.**

پشتیبانی از دو پنل: **3x-ui (سنایی)** و **Pasarguard**. قالب‌های زیبا و قابل‌تغییر
برای صفحه سابسکریپشن، همراه با یک **پنل وب سبک** (فقط 3x-ui) و یک
**مدیر خط فرمان (CLI)** برای انتخاب، اعمال، پیش‌نمایش و جابه‌جایی بین قالب‌ها.

> 🔥 نصب‌کننده ابتدا کادر انتخاب پنل را نشان می‌دهد و **فقط فایل‌های همان پنل** را دانلود می‌کند.

## ✨ امکانات

- 🗂 **۸ قالب آماده** برای هر پنل: `gradient`، `minimal`، `glass`، `matrix`، `neon`، `sunset`، `arctic`، `cyberpunk`
- 🧩 دو موتور رندر: Go `html/template` برای **3x-ui** (با `subThemeDir`) و **Jinja2** برای **Pasarguard**
- 🖥 **پنل وب فوق‌سبک** (۳x-ui؛ HTML خالص + Python3) — بدون Node.js
- ⌨️ **مدیر خط فرمان `nucsub`** — تشخیص خودکار پنل و کار روی هر دو
- 🚀 **نصب یک‌خطی** که پنل را می‌پرسد
- 🔄 **سوییچ زنده** بین قالب‌ها (تنها با restart پنل)
- 🔒 **توکن مدیریت** برای ورود به پنل وب
- 🌐 **فونت و آیکون محلی (۳x-ui)** — بدون هیچ CDN خارجی

## 🚀 نصب سریع (یک‌خطی)

روی سرور (با دسترسی root):

```bash
bash <(curl -Ls https://raw.githubusercontent.com/nuctereadev/NUC-SUB/main/install.sh)
```

ابتدا **کادر انتخاب پنل** نمایش داده می‌شود:

```
Select your VPN panel:
  1) 3x-ui (Sanaei)   — Go html/template themes (subThemeDir)
  2) Pasarguard       — self-contained Jinja2 templates
```

بسته به انتخاب، **فقط فایل‌های همان پنل** دانلود و نصب می‌شود (بدون فایل اضافه).
سپس ستاپ (منوی تعاملی) به‌صورت خودکار باز می‌شود تا قالب را انتخاب کنید.

> نصب بدون پرسش (برای cloud-init / خودکار):
> ```bash
> NUC_SUB_PANEL=pasarguard XUI_SUB_NONINTERACTIVE=1 bash <(curl -Ls https://raw.githubusercontent.com/nuctereadev/NUC-SUB/main/install.sh)
> ```
> مقدار مجاز `NUC_SUB_PANEL`: `3xui` یا `pasarguard` (پیش‌فرض: تشخیص خودکار از روی پنل نصب‌شده).

### نصب بر روی Pasarguard

- تم‌ها به `/var/lib/pasarguard/templates/subscription/<name>.html` کپی می‌شوند.
- `nucsub apply gradient` به‌صورت خودکار خطوط `CUSTOM_TEMPLATES_DIRECTORY` و
  `SUBSCRIPTION_PAGE_TEMPLATE` را در `.env` پنل تنظیم و افکت می‌کند (و پنل را restart می‌کند).
- اگر پنل هنوز نصب نباشد، تم‌ها در `/opt/nuc-sub/pasarguard-themes/subscription/` می‌مانند
  و بعد از نصب پنل با `nucsub apply gradient` فعال می‌شوند.

## ⌨️ استفاده از خط فرمان (nucsub)

```bash
nucsub list                     # لیست قالب‌ها + قالب فعلی
nucsub apply gradient           # فعال‌سازی قالب گرادیانت
nucsub preview matrix           # پیش‌نمایش قالب با دادهٔ واقعی
nucsub reset                    # بازگشت به صفحهٔ پیش‌فرض پنل
nucsub remove neon              # حذف یک قالب
nucsub status                   # وضعیت پنل و قالب‌ها
nucsub webpanel status          # وضعیت وب‌پنل
nucsub --help                   # راهنمای کامل
nucsub menu                     # منوی تعاملی
```

مثالی از خروجی `nucsub list`:

```
Theme folder: /opt/nuc-sub/themes
──────────────────────────────────────────────
   glass         ✓ runnable
 ★ gradient      ✓ runnable     ← قالب فعال
   matrix        ✓ runnable
   minimal       ✓ runnable
   neon          ✓ runnable
```

## 🖥 پنل وب (اختیاری)

وب‌پنل به‌صورت خودکار نصب نمی‌شود. برای راه‌اندازی آن از منو گزینهٔ `6) Web panel` را انتخاب کنید (یا `nucsub webpanel start`).

- پورت پیش‌فرض: `8080`
- توکن هنگام اجرای پنل ساخته و همان‌جا نمایش داده می‌شود (با `nucsub webpanel token` هم قابل مشاهده است)
- امکانات: مشاهدهٔ قالب‌ها، فعال‌سازی، حذف، بازگشت به پیش‌فرض
- برند: **NUC-SUB · Subscription Theme Engine**
- فوتر: **Created by [NUCTEREA](https://github.com/nuctereadev)**
- فایل‌های وب‌پنل در `webpanel/` نگهداری می‌شود

## 🧩 قالب‌ها (Go html/template)

پنل 3x-ui صفحهٔ ساب را با استاندارد **Go `html/template`** رندر می‌کند. قالب‌های این پروژه از
این الگو پیروی می‌کنند و از **فیلدهای مستند رسمی** استفاده می‌کنند:

| فیلد | معنی |
|------|------|
| `.sId` | آیدی سابسکریپشن |
| `.enabled` | فعال/غیرفعال بودن (boolean) |
| `.download` / `.upload` | ترافیک دانلود/آپلود (فرمت‌شده) |
| `.total` / `.used` / `.remained` | حجم کل / مصرفی / باقیمانده |
| `.expire` | timestamp انقضا (ثانیه؛ ۰ = نامحدود) |
| `.subTitle` / `.subSupportUrl` / `.announce` | عنوان / لینک پشتیبانی / اطلاعیه |
| `.links` / `.emails` | لیست لینک‌ها و ایمیل‌های متناظر |

هر قالب **کاملاً خودمتن** است (فونت + آیکون محلی، بدون CDN). قالب‌ها در
`themes/<name>/index.html` قرار دارند. می‌توانید قالبی جدید با همین ساختار بسازید
و آن را در `themes/` قرار دهید — با `nucsub apply <name>` فعال می‌شود.

## 🏗 ساختار پروژه

```
NUC-SUB/
├── install.sh            # نصب‌کنندهٔ یک‌خطی
├── cli/nucsub            # مدیر خط فرمان (bash)
├── webpanel/
│   ├── server.py         # وب‌سرور فوق‌سبک (Python3 stdlib)
│   ├── index.html        # رابط وب (HTML/JS/CSS خالص)
│   ├── css/              # فونت و آیکون (محلی)
│   ├── fonts/            # فونت ایران‌سنس (IRANSansX)
│   └── fa/               # آیکون‌های FontAwesome
├── themes/                  # قالب‌های 3x-ui (Go html/template)، ۸ قالب
│   ├── gradient/
│   ├── minimal/
│   ├── ...
├── pasarguard-themes/
│   └── subscription/        # قالب‌های Pasarguard (Jinja2 خودمتن)، ۸ فایل
├── LICENSE               # MIT
└── README.md
```

## 🧠 چگونه کار می‌کند؟

**۳x-ui:** `nucsub apply <name>` قالب را از `themes/<name>` به `/etc/x-ui/sub_templates/<name>/` کپی می‌کند، آدرس آن را با کلید `subThemeDir` در دیتابیس می‌نویسد و پنل را restart می‌کند.

**Pasarguard:** `nucsub apply <name>` قالب Jinja2 را به `/var/lib/pasarguard/templates/subscription/<name>.html` کپی می‌کند، `SUBSCRIPTION_PAGE_TEMPLATE=subscription/<name>.html` را در `.env` پنل تنظیم می‌کند و پنل را restart می‌کند. درکدام‌حالت، کلاینت‌های VPN همچنان کانفیگ `base64` دریافت می‌کنند و فقط مرورگر صفحهٔ سفارشی را می‌بیند.

## 🔒 امنیت

- توکن مدیریت در `/opt/nuc-sub/.webpanel-token` (mode 600) ذخیره می‌شود
- تمام API ها نیاز به `Authorization: Bearer <token>` دارند
- مقایسهٔ توکن با `hmac.compare_digest` (مقاوم در برابر timing attack)
- هدرهای امنیتی: `nosniff`، `no-store`، `X-Frame-Options`
- جلوگیری از SQL injection و XSS
- پورت وب‌پنل را در فایروال فقط به IP های مجاز باز کنید

## 🌱 نقشهٔ راه

- [x] مدیریت ۵ قالب با CLI
- [x] پنل وب سبک با توکن
- [x] پیش‌نمایش با دادهٔ واقعی
- [ ] آپلود/ایمپورت قالب سفارشی (CSS) — **به‌زودی**
- [ ] ویرایشگر بصری قالب
- [ ] پشتیبانی چند سرور / چند پنل

## ✍️ توسعه‌دهنده

**NUCTEREA** — [github.com/nuctereadev](https://github.com/nuctereadev)

## 📄 لایسنس

MIT

</div>
