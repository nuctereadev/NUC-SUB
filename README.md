<div dir="rtl">

# 🎨 NUC-SUB

**NUC-SUB یک موتور قالب مدرن برای صفحه سابسکریپشن پنل‌های 3x-ui است که توسط NUCTEREA توسعه داده شده است.**

قالب‌های زیبا و قابل‌تغییر برای صفحه سابسکریپشن پنل **3x-ui (سنایی)**، همراه با یک
**پنل وب سبک** و یک **مدیر خط فرمان (CLI)** برای انتخاب، اعمال، پیش‌نمایش و جابه‌جایی بین قالب‌ها.

> 🔥 کارها را بدون تغییر پورت، بدون ریورس‌پروکسی و بدون زبان وابستهٔ اضافه انجام می‌دهد —
> با استفاده از قابلیت بومی `subThemeDir` خود پنل 3x-ui.

## ✨ امکانات

- 🗂 **۵ قالب آماده**: `minimal`، `gradient`، `matrix`، `glass`، `neon`
- 🖥 **پنل وب فوق‌سبک** (HTML/JS/CSS خالص + Python3) — بدون Node.js، بدون فریم‌ورک
- ⌨️ **مدیر خط فرمان `nucsub`** — کار بدون وب‌پنل هم ممکن است
- 🚀 **نصب یک‌خطی** روی هر سرور دارای 3x-ui
- 🔄 **سوییچ زنده** بین قالب‌ها (تنها با restart پنل)
- 🔒 **توکن مدیریت** برای ورود به پنل وب
- 🧪 **پیش‌نمایش** قالب با دادهٔ واقعی سابسکریپشن (از `?format=info`)
- 🌐 **فونت و آیکون محلی** — بدون هیچ CDN خارجی

## 🚀 نصب سریع (یک‌خطی)

روی سرور (با دسترسی root و پنل 3x-ui نصب‌شده):

```bash
bash <(curl -Ls https://raw.githubusercontent.com/nuctereadev/NUC-SUB/main/install.sh)
```

پس از نصب، **ستاپ (منوی تعاملی) به‌صورت خودکار در ترمینال باز می‌شود** تا بتوانید همان‌جا قالب را انتخاب کنید.

وب‌پنل **به‌صورت پیش‌فرض نصب/اجرا نمی‌شود**. اگر بخواهید، از منو گزینهٔ `6) Web panel` را بزنید — بعد از اجرا یک **URL و یک توکن** برای ورود نمایش داده می‌شود.

> نصب بدون پرسش (برای cloud-init / خودکار):
> ```bash
> XUI_SUB_NONINTERACTIVE=1 bash <(curl -Ls https://raw.githubusercontent.com/nuctereadev/NUC-SUB/main/install.sh)
> ```

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
├── themes/
│   ├── minimal/          # قالب مینیمال
│   ├── gradient/         # قالب گرادیانت
│   ├── matrix/           # قالب ماتریکس
│   ├── glass/            # قالب شیشه‌ای
│   └── neon/             # قالب نئون
├── LICENSE               # MIT
└── README.md
```

## 🧠 چگونه کار می‌کند؟

1. `nucsub apply <name>` قالب را در `themes/<name>` کپی می‌کند به `/etc/x-ui/sub_templates/<name>/`.
2. آدرس این پوشه را در جدول `settings` دیتابیس 3x-ui به‌عنوان کلید `subThemeDir` می‌نویسد.
3. پنل را `restart` می‌کند — از این پس مرورگر با بازکردن لینک ساب، صفحهٔ سفارشی را می‌بیند،
   در حالی که کلاینت‌های VPN همچنان کانفیگ `base64` دریافت می‌کنند.

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
