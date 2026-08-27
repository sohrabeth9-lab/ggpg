# Binance Setup Candle + SMA Alert Bot (Multi-Timeframe)

ربات چک‌کننده‌ی الگوی کندل + SMA روی بایننس، حالا به‌صورت هم‌زمان روی
سه تایم‌فریم `15m` / `1h` / `4h`، با اجرا روی GitHub Actions.

## چی تغییر کرد نسبت به نسخه‌ی قبلی

1. **مولتی تایم‌فریم**: به‌جای یه `TIMEFRAME` ثابت، حالا لیست
   `TIMEFRAMES = ["15m", "1h", "4h"]` چک میشه (قابل override با env
   var `TIMEFRAMES="15m,1h,4h"`). وضعیت هر (نماد، تایم‌فریم) جدا تو
   `alert_state.json` نگه داشته میشه، پس پیام‌ها با هم قاطی نمی‌شن.
2. **حذف توکن hardcode‌شده**: `TELEGRAM_BOT_TOKEN` و
   `TELEGRAM_CHAT_ID` دیگه توی کد نوشته نمیشن، از environment variable
   خونده میشن. این برای اجرا روی گیت‌هاب (حتی ریپازیتوری private)
   ضروریه.
3. **ورک‌فلوی GitHub Actions** (`.github/workflows/alert.yml`) که هر
   ۱۵ دقیقه اجرا میشه و در پایان هر اجرا `alert_state.json` رو کامیت
   می‌کنه (چون ران‌رهای اکشن‌ها ephemeral هستن و فایل محلی بین اجراها
   نمی‌مونه مگر اینکه کامیتش کنیم).

## ⚠️ اقدام فوری لازم

توکن ربات تلگرامی که توی کد اصلی فرستادید (`TELEGRAM_BOT_TOKEN`) رو
از طریق [@BotFather](https://t.me/BotFather) با دستور `/revoke` باطل
کنید و یه توکن جدید بگیرید، چون توکن قبلی الان جایی بیرون از سیستم شما
دیده شده. توکن جدید رو فقط به‌عنوان GitHub Secret ذخیره کنید، هیچ‌وقت
توی کد ننویسیدش.

## راه‌اندازی روی GitHub

1. یه ریپازیتوری بسازید (می‌تونه private باشه) و این پوشه رو داخلش
   push کنید:
   ```bash
   cd binance-alert-bot
   git init
   git add .
   git commit -m "init: multi-timeframe alert bot"
   git branch -M main
   git remote add origin https://github.com/<username>/<repo>.git
   git push -u origin main
   ```

2. یه فایل خالی `alert_state.json` با محتوای `{}` بسازید و کامیت کنید
   (تا اولین ران بتونه بهش دسترسی داشته باشه):
   ```bash
   echo '{}' > alert_state.json
   git add alert_state.json
   git commit -m "chore: seed state file"
   git push
   ```

3. توی ریپازیتوری برید به **Settings → Secrets and variables →
   Actions → New repository secret** و این دو تا رو اضافه کنید:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`

4. تب **Actions** رو باز کنید — ورک‌فلوی `Binance Setup Alert Bot`
   خودکار هر ۱۵ دقیقه اجرا میشه. برای تست فوری، از همون تب روی
   **Run workflow** بزنید (چون `workflow_dispatch` هم فعاله).

## اجرای محلی (اختیاری، برای تست)

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
export TIMEFRAMES="15m,1h,4h"
python binance_setup_alert_bot.py
```

## تنظیمات قابل override با env var

| متغیر | پیش‌فرض | توضیح |
|---|---|---|
| `TIMEFRAMES` | `15m,1h,4h` | لیست تایم‌فریم‌ها، با کاما جدا |
| `QUOTE_ASSET` | `USDT` | ارز quote برای فیلتر نمادها |
| `TOP_N` | `200` | تعداد نماد برتر بر اساس حجم ۲۴ ساعته |

## نکات مهم درباره‌ی محدودیت‌های GitHub Actions

- **زمان‌بندی cron گیت‌هاب دقیق نیست**: گیت‌هاب تضمین نمی‌کنه که
  `*/15 * * * *` دقیقاً هر ۱۵ دقیقه اجرا بشه؛ ممکنه چند دقیقه تاخیر
  داشته باشه، مخصوصاً تو ساعات شلوغ. برای یه سیگنال‌گیر کندل این
  معمولاً مشکلی نیست (چون منطق بر اساس بسته‌شدن کندل چک میشه، نه زمان
  دقیقه‌ای)، ولی اگه تایمینگ خیلی حساسه، یه سرور کوچک با cron واقعی
  (نسخه‌ی قبلی) گزینه‌ی مطمئن‌تریه.
- **حجم درخواست**: با ۲۰۰ نماد × ۳ تایم‌فریم = ۶۰۰ درخواست به Klines
  در هر ران، با فاصله‌ی ۰.۰۸ ثانیه بین درخواست‌ها ≈ ۵۰ ثانیه اجرا؛
  کاملاً داخل محدودیت زمانی رایگان GitHub Actions هست.
- **permissions: contents: write** توی ورک‌فلو لازمه تا بتونه
  `alert_state.json` رو کامیت کنه. اگه ریپازیتوری تحت یه org با
  policyهای سخت‌گیرانه‌تره، ممکنه لازم باشه از تنظیمات
  Settings → Actions → General → Workflow permissions هم
  "Read and write permissions" رو فعال کنید.
