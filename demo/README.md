# NUC-SUB Live Preview

گالری زندهی ۱۶ قالب سابسکریپشن NUC-SUB (۸ قالب PasarGuard + ۸ قالب 3x-ui) روی **GitHub Pages**.

| | لینک |
|---|---|
| **پیشنمایش زنده** | `https://nuctereadev.github.io/NUC-SUB/` |
| مخزن | `https://github.com/nuctereadev/NUC-SUB` |

## چطور کار میکند؟

هر قالب با **دادهی ثابت و واقعینما** (یوزر `demo.user`، حجم ۱۰۰GB، مصرف ۴۳.۷۵GB، تا ۱۲ روز مهلت، ۶ لینک از ۶ پروتکل) آفلاین رندر میشود:

- **قالبهای PasarGuard** → با موتور **Jinja2** و فیلترهای واقعی پنل (`bytesformat`, `datetime`, `now`)
- **قالبهای 3x-ui** → با یک موتور کوچک **Go-template** (پشتیبانی `range`/`if`/`else`/متغیرها و کپی خودکار `css/fa/fonts`)

نتیجه یک سایت کاملاً استاتیک در `demo/site/` است (بدون نیاز به سرور و بدون هیچ خط API).

## ساخت مجدد (توسعهدهنده)

```bash
pip install jinja2
python demo/build.py
```

خروجی در `demo/site/` ساخته میشود. هر قالب جدید/تغییرافته را به `themes/` یا `pasarguard-themes/subscription/` اضافه کنید و اسکریپت را دوباره اجرا کنید.

## استقرار خودکار

با هر `push` به `main` (مسیرهای `themes/` یا `pasarguard-themes/` یا `demo/`) اکشن `demo/.github/workflows/demo.yml` اجرا میشود و سایت را روی GitHub Pages منتشر میکند.

### فعالسازی Pages (یک بار)

1. به **Settings → Pages** مخزن بروید.
2. در **Source** گزینهی **GitHub Actions** را انتخاب کنید.
3. تمام — اکشن بعد از هر push بهصورت خودکار رندر و منتشر میکند.

## ساختار

```
demo/
  build.py        # موتور رندر (Jinja2 + Go-template) و ساخت خروجی
  README.md
  site/           # سایت خروجی (رندر شده — به GitHub Pages میرود)
    index.html    # گالری انتخابگر با ۱۶ کارت
    pg/           # قالبهای PasarGuard
    xui/          # قالبهای 3x-ui (با asset های هر قالب)
```