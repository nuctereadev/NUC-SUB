# NUC-SUB Live Preview

گالری زندهی ۱۶ قالب سابسکریپشن NUC-SUB (۸ قالب PasarGuard + ۸ قالب 3x-ui).

- **محلی:** با یک فرمان رندر و در مرورگر ببین
- **آنلاین:** روی **Vercel** دیپلوی کن و دامین خودت را وصل کن

## چطور کار میکند؟

هر قالب با **دادهی ثابت و واقعینما** (یوزر `demo.user`، حجم ۱۰۰GB، مصرف ۴۳.۷۵GB، تا ۱۲ روز مهلت، ۶ لینک از ۶ پروتکل) آفلاین رندر میشود:

- **قالبهای PasarGuard** → موتور **Jinja2** + فیلترهای واقعی پنل (`bytesformat`, `datetime`, `now`)
- **قالبهای 3x-ui** → یک موتور کوچک **Go-template** (`range`/`if`/`else`/متغیرها) + کپی خودکار `css/fa/fonts`

خروجی یک سایت کاملاً **استاتیک** در `demo/site/` است — بدون سرور، بدون API.

## اجرای محلی (روی سیستم خودت)

```bash
pip install jinja2
python demo/serve.py          # render + سرو روی http://127.0.0.1:8080 + باز کردن مرورگر
```

یا جداگانه:

```bash
python demo/build.py          # فقط رندر -> demo/site/
python -m http.server 8080 --directory demo/site
```

هر تغییر در `themes/` یا `pasarguard-themes/subscription/` را بعد از اجرای مجدد اسکریپت میبینی.

## استقرار روی Vercel

۱. مخزن `nuctereadev/NUC-SUB` را وارد Vercel کن (**New Project → Import Git Repository**).
۲. در تنظیمات پروژه:
   - **Root Directory**: `demo`
   - **Build Command**: `python3 -m pip install --quiet -r requirements.txt && python3 build.py`
   - **Output Directory**: `site`
3. **Deploy**.
۴. بعد از deploy، از تب **Domains** دامین خودت را اضافه کن.

پیکربندی فوق از قبل در `demo/vercel.json` قرار دارد — فقط باید Root Directory را روی `demo` بگذاری.

> نکته: بعد از هر `push` به `main`، Vercel بهصورت خودکار دوباره بیلد و منتشر میکند.

## ساختار

```
demo/
  build.py        # موتور رندر (Jinja2 + Go-template) -> demo/site/
  gallery.html    # ⭐ گالری (HTML خام — همین فایل را ویرایش کن؛ build از آن کپی میکند)
  serve.py        # اجرای محلی (render + سرور + مرورگر)
  vercel.json     # پیکربندی Vercel
  requirements.txt  # jinja2
  README.md
  site/           # خروجی رندر شده (gitignored — خودکار ساخته میشود)
    index.html    # گالری (کپی از gallery.html توسط build.py)
    pg/           # قالبهای PasarGuard
    xui/          # قالبهای 3x-ui (با asset های هر قالب)
```

> **مهم:** برای ویرایش گالری، **`demo/gallery.html`** را ویرایش کن، نه `demo/site/index.html`. هنگام اجرای `build.py` یا `serve.py`، فایل `gallery.html` بهصورت کلمهبهکلمه به `site/index.html` کپی میشود و ویرایشهای تو **از دست نمیروند**.