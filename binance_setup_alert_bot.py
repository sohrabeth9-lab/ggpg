"""
Setup Candle + SMA Alert Bot (Binance -> Telegram) — Multi-Timeframe
=====================================================================
منطق سیگنال الان دقیقاً منطبق با آخرین نسخه‌ی اسکریپت Pine v6
(indicator "Setup Candle + SMA View") هست:
  - بدنه کوچک (small_body)
  - سایه غالب (lower/upper dominant) - نسبت سایه به بدنه جدا برای
    بولیش (SHADOW_RATIO_BULL) و بریش (SHADOW_RATIO_BEAR)
  - close بالای/پایین هر سه SMA (7, 25, 99) به‌طور هم‌زمان
  - چیدمان صحیح SMA ها نسبت به هم (sma7 > sma25 > sma99 برای بولیش،
    برعکسش برای بریش)
  - بدنه‌ی کندل نباید SMA7 رو قطع کرده باشه
  - فاصله‌ی close تا SMA7 نباید بیشتر از SMA7_MAX_DIST_MULT برابر
    رنج خود همون کندل (high-low) باشه — دیگه ATR/کندل‌های قبلی توش
    نقشی نداره، فقط خود کندل سیگنال حساب میشه
  - فیلتر روند با ADX/DMI: اگه ADX >= آستانه -> سیگنال عادی،
    اگه ADX < آستانه (بازار رنج) -> همون سیگنال ولی به‌عنوان "ریسکی"
    علامت‌گذاری میشه (دقیقاً مثل رنگ زرد/نارنجی تو اسکریپت Pine)
  - شرط حجم (حجم کندل فعلی کمتر از کندل قبلی) دیگه فیلتر نیست؛ فقط
    به‌عنوان یه تگ جدا روی سیگنال گذاشته میشه (دقیقاً مثل رنگ زرد
    "No-Volume-Condition" تو اسکریپت Pine) — یعنی سیگنالی که این
    شرط رو نداشته باشه هم فرستاده میشه، ولی با یه هشدار جدا مشخص میشه.
  - تایید هم‌جهتی با تایم‌فریم بالاتر (HTF Confirmation): دقیقاً مثل
    دایره‌ی سبز/قرمز تاییدیه‌ی اسکریپت Pine، این هم فیلتر نیست، فقط
    یه تگ جدا روی سیگنال میذاره که نشون میده چیدمان SMA (7/25/99)
    تو تایم فریم بالاتر هم‌جهت با سیگنال هست یا نه.

این نسخه روی چند تایم‌فریم هم‌زمان (پیش‌فرض: 15m, 1h, 4h) چک می‌کنه.
طراحی شده برای اجرا با cron یا GitHub Actions: هر بار که اجرا میشه،
فقط آخرین کندلِ "بسته‌شده"ی هر نماد در هر تایم‌فریم رو چک می‌کنه.

--- تغییرات این نسخه (هم‌سو با آخرین ویرایش اندیکاتور) ---
  - ترتیب ارسال پیام‌ها تغییر کرد: سیگنال‌های عادی (نه ریسکی، نه
    ناهم‌جهت با HTF) مثل قبل، همون لحظه که پیدا میشن فرستاده میشن.
    سیگنال‌هایی که ریسکی هستن (بازار رنج / risky=True) یا با تایم
    فریم بالاتر ناهم‌جهت هستن (htf_confirm=False) دیگه فوری فرستاده
    نمیشن؛ جمع میشن و همه‌شون یکجا، درست قبل از پیام «پایان اسکن»،
    فرستاده میشن (با یه پیام سرتیتر که تعداد نمادها رو نشون میده).
  - اضافه شدن تایید هم‌جهتی با تایم فریم بالاتر (HTF Confirmation):
      * USE_HTF_CONFIRM: فعال/غیرفعال کردن این بخش (پیش‌فرض: فعال)
      * AUTO_HTF: انتخاب خودکار تایم بالاتر (15m->1h, 1h->4h,
        4h->1d, 1d->1w) - معادل auto_htf تو Pine
      * MANUAL_HTF: تایم بالاتر دستی، وقتی AUTO_HTF خاموشه یا
        نگاشت خودکاری براش تعریف نشده
      * چیدمان SMA (7/25/99) روی تایم بالاتر محاسبه و با جهت
        سیگنال مقایسه میشه؛ نتیجه فقط به‌صورت تگ (🔵 هم‌جهت /
        ⚪ ناهم‌جهت) روی پیام گذاشته میشه، فیلتر نیست
  - SMA7_MAX_DIST_MULT پیش‌فرضش از 1.0 به 2.0 تغییر کرد تا با
    پیش‌فرض فعلی اسکریپت Pine (sma7_max_dist_mult) هم‌سو باشه
  - نسبت سایه به بدنه جدا شد: SHADOW_RATIO_BULL و SHADOW_RATIO_BEAR
  - چک چیدمان SMA (sma_stack_bull / sma_stack_bear) که قبلاً نبود اضافه شد
  - فاصله تا SMA7 دیگه بر مبنای ATR نیست؛ بر مبنای close و رنج خود
    کندل سیگنال حساب میشه (SMA7_MAX_DIST_MULT). ATR_LEN و
    SMA7_MAX_DIST_ATR حذف شدن.
  - فیلتر حجم از شرط ورود سیگنال حذف شد و به یه تگ/هشدار جدا تبدیل شد
    (no_volume=True یعنی این سیگنال شرط حجم رو نداشته)

نصب پیش‌نیازها:
    pip install requests

تنظیم قبل از اجرا (به‌صورت متغیر محیطی):
    export TELEGRAM_BOT_TOKEN="..."
    export TELEGRAM_CHAT_ID="..."

اجرای محلی با cron (مثال: هر ۱۵ دقیقه):
    */15 * * * * TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=yyy /usr/bin/python3 /path/to/binance_setup_alert_bot.py >> /path/to/bot.log 2>&1

نکته درباره‌ی داده‌ی مارکت‌کپ: بایننس مارکت‌کپ/رنک نمی‌ده، پس این
اسکریپت یک‌بار در ابتدای هر اجرا، چند صفحه از CoinGecko (API عمومی و
رایگان) رو فقط برای نمایش تو پیام می‌گیره. اگه این بخش با خطا یا
محدودیت مواجه بشه، اسکریپت متوقف نمیشه؛ فقط خط مارکت‌کپ تو پیام
"یافت نشد" نشون داده میشه.
"""

import json
import os
import time
from datetime import datetime, timezone

import requests

# ============================== تنظیمات ==============================

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

DEFAULT_TIMEFRAMES = ["15m", "1h", "4h"]
TIMEFRAMES = (
    [tf.strip() for tf in os.environ.get("TIMEFRAMES", "").split(",") if tf.strip()]
    or DEFAULT_TIMEFRAMES
)

QUOTE_ASSET = os.environ.get("QUOTE_ASSET", "USDT")
TOP_N = int(os.environ.get("TOP_N", "200"))   # ۲۰۰ کوین برتر بر اساس حجم معاملات بایننس

MAX_BODY_RATIO = float(os.environ.get("MAX_BODY_RATIO", "0.5"))

# نسبت سایه به بدنه - جدا برای بولیش (سایه پایین) و بریش (سایه بالا)
SHADOW_RATIO_BULL = float(os.environ.get("SHADOW_RATIO_BULL", "1.5"))
SHADOW_RATIO_BEAR = float(os.environ.get("SHADOW_RATIO_BEAR", "1.5"))

SMA_FAST_LEN = int(os.environ.get("SMA_FAST_LEN", "7"))
SMA_MID_LEN = int(os.environ.get("SMA_MID_LEN", "25"))
SMA_TREND_LEN = int(os.environ.get("SMA_TREND_LEN", "99"))

# فاصله‌ی close کندل ستاپ تا SMA7 - بر مبنای رنج خود همون کندل (نه ATR)
# پیش‌فرض هم‌سو با اسکریپت Pine فعلی (sma7_max_dist_mult = 2.0)
SMA7_MAX_DIST_MULT = float(os.environ.get("SMA7_MAX_DIST_MULT", "2.0"))

# فیلتر روند/رنج با ADX — دقیقاً مطابق اسکریپت Pine
ADX_LEN = int(os.environ.get("ADX_LEN", "14"))
ADX_SMOOTHING = int(os.environ.get("ADX_SMOOTHING", "14"))
ADX_THRESHOLD = float(os.environ.get("ADX_THRESHOLD", "20.0"))

RSI_LEN = int(os.environ.get("RSI_LEN", "21"))
RSI_BULLISH_HOT = 60   # اگه سیگنال لانگه و RSI بالای این عدد -> هایلایت
RSI_BEARISH_HOT = 30   # اگه سیگنال شورته و RSI زیر این عدد -> هایلایت

# --- تایید هم‌جهتی با تایم فریم بالاتر (HTF Confirmation) ---
# معادل use_htf_confirm / auto_htf / manual_htf تو اسکریپت Pine.
# این بخش فیلتر نیست، فقط یه تگ جدا روی سیگنال میذاره.
USE_HTF_CONFIRM = os.environ.get("USE_HTF_CONFIRM", "1") == "1"
AUTO_HTF = os.environ.get("AUTO_HTF", "1") == "1"
MANUAL_HTF = os.environ.get("MANUAL_HTF", "1h")  # فقط وقتی AUTO_HTF خاموشه یا نگاشتی نداره

# نگاشت خودکار تایم بالاتر (معادل auto_htf_value تو Pine):
# 15m -> 1h, 1h -> 4h, 4h -> 1d, 1d -> 1w
AUTO_HTF_MAP = {
    "15m": "1h",
    "1h": "4h",
    "4h": "1d",
    "1d": "1w",
}

# باید به اندازه‌ی کافی کندل داشته باشیم برای SMA99 + وارم‌آپ ADX
KLINES_LIMIT = max(SMA_TREND_LEN + 5, ADX_LEN + ADX_SMOOTHING + 20, 120)

# کندل کافی برای محاسبه‌ی چیدمان SMA روی تایم فریم بالاتر
HTF_KLINES_LIMIT = max(SMA_TREND_LEN + 5, 110)

# اردربوک
ORDERBOOK_LIMIT = int(os.environ.get("ORDERBOOK_LIMIT", "100"))
ORDERBOOK_WALL_TOP_N = int(os.environ.get("ORDERBOOK_WALL_TOP_N", "10"))

# CoinGecko (فقط برای نمایش مارکت‌کپ/رنک تو پیام؛ در انتخاب نماد نقشی نداره)
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
COINGECKO_ENABLED = os.environ.get("COINGECKO_ENABLED", "1") == "1"
COINGECKO_PAGES = int(os.environ.get("COINGECKO_PAGES", "5"))       # هر صفحه ۲۵۰ کوین
COINGECKO_SLEEP = float(os.environ.get("COINGECKO_SLEEP", "1.2"))

STATE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "alert_state.json"
)

# API عمومی دیتای Binance
BINANCE_BASE = "https://data-api.binance.vision"

# --- پشتیبانی چند صرافی (Multi-Exchange Fallback) ---
# اولویت پیش‌فرض: بایننس اول، اگه بایننس جواب نداد یا خطا داد (مثلاً
# ریت‌لیمیت یا مسدودی جغرافیایی)، میره سراغ MEXC و بعد KuCoin.
# این فقط برای گرفتن دیتای کندل/تیکر/اردربوک هست؛ به‌هیچ‌وجه منطق
# سیگنال یا شرط‌ها فرق نمی‌کنه، فقط منبع دیتا عوض میشه.
EXCHANGE_PRIORITY = (
    [ex.strip().lower() for ex in os.environ.get("EXCHANGE_PRIORITY", "binance,mexc,kucoin").split(",") if ex.strip()]
    or ["binance", "mexc", "kucoin"]
)

MEXC_BASE = "https://api.mexc.com"
KUCOIN_BASE = "https://api.kucoin.com"

# نگاشت اینتروال هر تایم‌فریم به فرمت مخصوص هر صرافی
MEXC_INTERVAL_MAP = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "60m", "4h": "4h", "1d": "1d", "1w": "1W",
}
KUCOIN_INTERVAL_MAP = {
    "1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min",
    "1h": "1hour", "4h": "4hour", "1d": "1day", "1w": "1week",
}

REQUEST_SLEEP = 0.08

# نگاشت تایم‌فریم بایننس به فرمت اینتروال TradingView
TV_INTERVAL_MAP = {
    "1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
    "1h": "60", "2h": "120", "4h": "240", "6h": "360", "8h": "480",
    "12h": "720", "1d": "D", "3d": "3D", "1w": "W", "1M": "M",
}

# =======================================================================


def to_kucoin_symbol(symbol: str, quote_asset: str) -> str:
    """تبدیل نماد سبک بایننس ('BTCUSDT') به فرمت کوکوین ('BTC-USDT')."""
    if symbol.endswith(quote_asset):
        base = symbol[: -len(quote_asset)]
        return f"{base}-{quote_asset}"

    return symbol


def _get_all_symbols_binance(quote_asset: str):
    url = f"{BINANCE_BASE}/api/v3/exchangeInfo"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    symbols = []
    for s in data.get("symbols", []):
        if (
            s.get("status") == "TRADING"
            and s.get("quoteAsset") == quote_asset
            and s.get("isSpotTradingAllowed", True)
        ):
            symbols.append(s["symbol"])

    return symbols


def _get_all_symbols_mexc(quote_asset: str):
    url = f"{MEXC_BASE}/api/v3/exchangeInfo"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    symbols = []
    for s in data.get("symbols", []):
        if (
            s.get("status") == "1" or s.get("status") == 1 or s.get("isSpotTradingAllowed", True)
        ) and s.get("quoteAsset") == quote_asset:
            symbols.append(s["symbol"])

    return symbols


def get_all_symbols(quote_asset: str):
    """
    همه‌ی نمادهای اسپات فعال با quote asset مشخص‌شده رو برمی‌گردونه.
    اولویت با بایننسه؛ اگه بایننس خطا داد (مثلاً مسدودی جغرافیایی/
    ریت‌لیمیت)، میره سراغ MEXC که فرمت نماد‌هاش دقیقاً مثل بایننسه
    (بدون خط تیره)، پس نیازی به تبدیل نداره.
    """
    errors = []

    for exchange in EXCHANGE_PRIORITY:
        try:
            if exchange == "binance":
                symbols = _get_all_symbols_binance(quote_asset)
            elif exchange == "mexc":
                symbols = _get_all_symbols_mexc(quote_asset)
            else:
                # کوکوین برای انتخاب یونیورس نماد استفاده نمیشه چون
                # فرمت نمادش با بقیه فرق داره؛ فقط برای دیتای کندل/
                # اردربوک به‌عنوان آخرین fallback به کار میره.
                continue

            if symbols:
                if exchange != "binance":
                    print(f"[INFO] لیست نمادها از {exchange} گرفته شد (fallback).")
                return symbols

        except Exception as e:
            errors.append(f"{exchange}: {e}")
            print(f"[WARN] get_all_symbols روی {exchange} شکست خورد: {e}")

    print(f"[ERROR] گرفتن لیست نمادها از همه‌ی صرافی‌ها شکست خورد: {errors}")
    return []


def _get_ticker_24hr_map_binance():
    url = f"{BINANCE_BASE}/api/v3/ticker/24hr"
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    return {row.get("symbol"): row for row in resp.json()}


def _get_ticker_24hr_map_mexc():
    url = f"{MEXC_BASE}/api/v3/ticker/24hr"
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    return {row.get("symbol"): row for row in resp.json()}


def get_top_symbols_by_volume(quote_asset: str, top_n: int):
    """
    نمادهای معتبر اسپات با quote asset مشخص‌شده رو می‌گیره و بر اساس
    حجم معاملات ۲۴ ساعته (quoteVolume) مرتب می‌کنه، و ۲۰۰ تای برتر
    (یا هر عددی که TOP_N باشه) رو برمی‌گردونه.
    اولویت با بایننسه؛ فقط اگه بایننس کلاً در دسترس نبود میره سراغ
    MEXC (چون یونیورس نماد هم از همون منبع باید بیاد تا سازگار بمونه).
    """
    valid_symbols = get_all_symbols(quote_asset)

    if not valid_symbols:
        return []

    valid_symbols_set = set(valid_symbols)

    ticker_fetchers = [
        ("binance", _get_ticker_24hr_map_binance),
        ("mexc", _get_ticker_24hr_map_mexc),
    ]

    # فقط صرافی‌هایی که تو EXCHANGE_PRIORITY هستن رو امتحان کن، به
    # همون ترتیب اولویت
    ordered_fetchers = [
        (name, fn) for name, fn in ticker_fetchers if name in EXCHANGE_PRIORITY
    ] or ticker_fetchers

    ticker_map = None
    used_exchange = None

    for name, fetcher in ordered_fetchers:
        try:
            candidate_map = fetcher()
            # فقط نمادهایی که تو یونیورس معتبرمون هستن رو نگه می‌داریم
            if any(sym in valid_symbols_set for sym in candidate_map):
                ticker_map = candidate_map
                used_exchange = name
                break
        except Exception as e:
            print(f"[WARN] ticker/24hr روی {name} شکست خورد: {e}")

    if ticker_map is None:
        print("[ERROR] گرفتن حجم ۲۴ ساعته از همه‌ی صرافی‌ها شکست خورد.")
        return valid_symbols[:top_n]

    if used_exchange and used_exchange != "binance":
        print(f"[INFO] حجم ۲۴ ساعته از {used_exchange} گرفته شد (fallback).")

    rows = []
    for symbol in valid_symbols:
        row = ticker_map.get(symbol)
        if not row:
            continue

        try:
            quote_volume = float(row.get("quoteVolume", 0))
        except (TypeError, ValueError):
            quote_volume = 0.0

        rows.append((symbol, quote_volume))

    rows.sort(key=lambda x: x[1], reverse=True)

    return [symbol for symbol, _ in rows[:top_n]]


def _get_klines_binance(symbol: str, interval: str, limit: int):
    """کندل‌های خام رو از بایننس می‌گیره."""
    url = f"{BINANCE_BASE}/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}

    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()

    return resp.json()


def _get_klines_mexc(symbol: str, interval: str, limit: int):
    """
    کندل‌های خام رو از MEXC می‌گیره. MEXC برای اسپات دقیقاً از همون
    فرمت نماد (بدون خط تیره) و همون شکل خروجی کندل بایننس استفاده
    می‌کنه، فقط اسم بعضی اینتروال‌ها فرق داره (مثلاً "1h" -> "60m").
    """
    mexc_interval = MEXC_INTERVAL_MAP.get(interval)
    if not mexc_interval:
        raise ValueError(f"اینتروال {interval} برای MEXC پشتیبانی نمیشه")

    url = f"{MEXC_BASE}/api/v3/klines"
    params = {"symbol": symbol, "interval": mexc_interval, "limit": limit}

    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()

    return resp.json()


def _get_klines_kucoin(symbol: str, interval: str, limit: int):
    """
    کندل‌های خام رو از کوکوین می‌گیره و به همون فرمت لیست-از-لیست
    بایننس تبدیل می‌کنه: [open_time_ms, open, high, low, close,
    volume, close_time_ms, quote_volume, ...]
    کوکوین کندل‌ها رو به‌ترتیب نزولی (جدیدترین اول) و با ترتیب فیلدهای
    [time, open, close, high, low, volume, turnover] برمی‌گردونه، پس
    باید هم ترتیب فیلدها هم ترتیب زمانی رو اصلاح کنیم.
    """
    kucoin_type = KUCOIN_INTERVAL_MAP.get(interval)
    if not kucoin_type:
        raise ValueError(f"اینتروال {interval} برای KuCoin پشتیبانی نمیشه")

    kucoin_symbol = to_kucoin_symbol(symbol, QUOTE_ASSET)
    interval_sec = interval_to_ms(interval) // 1000
    end_at = int(time.time())
    start_at = end_at - interval_sec * (limit + 2)

    url = f"{KUCOIN_BASE}/api/v1/market/candles"
    params = {
        "type": kucoin_type,
        "symbol": kucoin_symbol,
        "startAt": start_at,
        "endAt": end_at,
    }

    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    payload = resp.json()

    if payload.get("code") != "200000":
        raise RuntimeError(f"KuCoin error: {payload.get('code')} {payload.get('msg')}")

    raw = payload.get("data", [])

    # کوکوین جدیدترین رو اول میده؛ برعکسش می‌کنیم تا صعودی (قدیمی -> جدید) بشه
    raw = list(reversed(raw))

    normalized = []
    for row in raw:
        # row: [time, open, close, high, low, volume, turnover]
        open_time_ms = int(float(row[0])) * 1000
        o, cl, hi, lo, vol, turnover = (float(x) for x in row[1:7])
        close_time_ms = open_time_ms + interval_sec * 1000 - 1

        normalized.append([
            open_time_ms, o, hi, lo, cl, vol, close_time_ms, turnover
        ])

    return normalized[-limit:] if limit else normalized


_KLINES_FETCHERS = {
    "binance": _get_klines_binance,
    "mexc": _get_klines_mexc,
    "kucoin": _get_klines_kucoin,
}


def get_klines(symbol: str, interval: str, limit: int):
    """
    کندل‌ها رو به ترتیب اولویت EXCHANGE_PRIORITY می‌گیره (پیش‌فرض:
    بایننس -> MEXC -> KuCoin). اگه صرافی اول خطا بده یا دیتا برنگردونه
    (ریت‌لیمیت، قطعی، مسدودی جغرافیایی و ...)، خودکار میره سراغ صرافی
    بعدی. منطق سیگنال و شرط‌ها کاملاً مستقل از این بخشه و فرقی نمی‌کنه
    دیتا از کدوم صرافی اومده باشه.
    """
    errors = []

    for exchange in EXCHANGE_PRIORITY:
        fetcher = _KLINES_FETCHERS.get(exchange)
        if not fetcher:
            continue

        try:
            data = fetcher(symbol, interval, limit)

            if data:
                return data

        except Exception as e:
            errors.append(f"{exchange}: {e}")
            continue

    raise RuntimeError(
        f"گرفتن کندل {symbol}/{interval} از همه‌ی صرافی‌ها ({EXCHANGE_PRIORITY}) شکست خورد: {errors}"
    )


def sma(values, length):
    """SMA ساده."""
    result = [None] * len(values)

    for i in range(length - 1, len(values)):
        window = values[i - length + 1: i + 1]
        result[i] = sum(window) / length

    return result


def rsi(values, length=14):
    """
    RSI استاندارد (روش Wilder's smoothing).
    خروجی: لیستی هم‌طول values که ایندکس‌های قبل از آماده‌شدن None هستن.
    """
    n = len(values)
    result = [None] * n

    if n < length + 1:
        return result

    deltas = [values[i] - values[i - 1] for i in range(1, n)]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]

    avg_gain = sum(gains[:length]) / length
    avg_loss = sum(losses[:length]) / length

    result[length] = 100.0 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))

    for i in range(length, len(deltas)):
        gain = gains[i]
        loss = losses[i]

        avg_gain = (avg_gain * (length - 1) + gain) / length
        avg_loss = (avg_loss * (length - 1) + loss) / length

        idx_result = i + 1
        result[idx_result] = (
            100.0 if avg_loss == 0
            else 100 - (100 / (1 + avg_gain / avg_loss))
        )

    return result


def rma(values, length):
    """
    Wilder's smoothing (همون ta.rma تو Pine) — پایه‌ی ADX/DMI.
    مقادیر ابتدایی که None هستن (وارم‌آپ) نادیده گرفته میشن؛ اولین
    مقدار خروجی، میانگین ساده‌ی اولین `length` مقدار معتبره و بعدش
    هر مقدار جدید با فرمول Wilder روی مقدار قبلی اعمال میشه.
    """
    n = len(values)
    result = [None] * n

    start = None
    for i in range(n):
        if values[i] is not None:
            start = i
            break

    if start is None or (n - start) < length:
        return result

    seed = sum(values[start:start + length]) / length
    seed_idx = start + length - 1
    result[seed_idx] = seed

    for i in range(seed_idx + 1, n):
        result[i] = (result[i - 1] * (length - 1) + values[i]) / length

    return result


def true_range_series(highs, lows, closes):
    """True Range کلاسیک؛ برای کندل اول چون close قبلی نداریم، فقط high-low."""
    n = len(highs)
    tr = [None] * n

    for i in range(n):
        if i == 0:
            tr[i] = highs[i] - lows[i]
        else:
            tr[i] = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )

    return tr


def adx_series(highs, lows, closes, di_length, adx_smoothing):
    """
    پیاده‌سازی ta.dmi(di_length, adx_smoothing) از Pine — فقط سری ADX رو
    برمی‌گردونه (چون به +DI/-DI جداگانه نیازی نداریم، فقط برای فیلتر
    روند/رنج از خود ADX استفاده میشه).
    """
    n = len(highs)
    plus_dm = [0.0] * n
    minus_dm = [0.0] * n

    for i in range(1, n):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]

        plus_dm[i] = up_move if (up_move > down_move and up_move > 0) else 0.0
        minus_dm[i] = down_move if (down_move > up_move and down_move > 0) else 0.0

    tr = true_range_series(highs, lows, closes)

    tr_rma = rma(tr, di_length)
    plus_dm_rma = rma(plus_dm, di_length)
    minus_dm_rma = rma(minus_dm, di_length)

    dx = [None] * n
    for i in range(n):
        if (
            tr_rma[i] is not None
            and tr_rma[i] != 0
            and plus_dm_rma[i] is not None
            and minus_dm_rma[i] is not None
        ):
            plus_di = 100 * plus_dm_rma[i] / tr_rma[i]
            minus_di = 100 * minus_dm_rma[i] / tr_rma[i]
            denom = plus_di + minus_di
            dx[i] = 100 * abs(plus_di - minus_di) / denom if denom != 0 else 0.0

    return rma(dx, adx_smoothing)


def get_htf_timeframe(base_timeframe: str) -> str:
    """
    انتخاب تایم فریم بالاتر برای تایید هم‌جهتی SMA - معادل
    auto_htf_value تو اسکریپت Pine:
        15m -> 1h, 1h -> 4h, 4h -> 1d, 1d -> 1w
    اگه AUTO_HTF خاموش باشه، یا تایم فعلی تو نگاشت نباشه، از
    MANUAL_HTF استفاده میشه.
    """
    if AUTO_HTF and base_timeframe in AUTO_HTF_MAP:
        return AUTO_HTF_MAP[base_timeframe]

    return MANUAL_HTF


def get_htf_sma_stack(symbol: str, htf_timeframe: str):
    """
    چیدمان SMA (7/25/99) روی تایم فریم بالاتر رو حساب می‌کنه - معادل
    بخش request.security اسکریپت Pine (htf_sma7/25/99 و
    htf_stack_bull/bear). فقط برای تایید جهت استفاده میشه، نه محاسبه‌ی
    سیگنال مستقل روی تایم بالاتر.

    خروجی: (htf_stack_bull, htf_stack_bear) یا None اگه دیتای کافی
    نبود یا خطایی پیش اومد (در این حالت، تایید HTF نادیده گرفته میشه
    و سیگنال اصلی همچنان فرستاده میشه).
    """
    try:
        raw = get_klines(symbol, htf_timeframe, HTF_KLINES_LIMIT)
    except Exception as e:
        print(f"[WARN] HTF klines {symbol} {htf_timeframe}: {e}")
        return None

    if not raw or len(raw) < SMA_TREND_LEN + 1:
        return None

    closes = [float(k[4]) for k in raw]
    close_times = [int(k[6]) for k in raw]

    now_ms = int(time.time() * 1000)
    idx = len(raw) - 1

    # مثل تایم فعلی، اگه آخرین کندل HTF هنوز بسته نشده، قبلی رو بگیر
    if close_times[idx] > now_ms:
        idx -= 1

    if idx < SMA_TREND_LEN:
        return None

    htf_sma7 = sma(closes, SMA_FAST_LEN)[idx]
    htf_sma25 = sma(closes, SMA_MID_LEN)[idx]
    htf_sma99 = sma(closes, SMA_TREND_LEN)[idx]

    if htf_sma7 is None or htf_sma25 is None or htf_sma99 is None:
        return None

    htf_stack_bull = htf_sma7 > htf_sma25 and htf_sma25 > htf_sma99
    htf_stack_bear = htf_sma7 < htf_sma25 and htf_sma25 < htf_sma99

    return htf_stack_bull, htf_stack_bear


def interval_to_ms(interval: str) -> int:
    """تبدیل رشته‌ی تایم‌فریم بایننس (مثل '15m', '4h', '1d') به میلی‌ثانیه."""
    unit = interval[-1]
    value = int(interval[:-1])

    multipliers = {
        "m": 60_000,
        "h": 3_600_000,
        "d": 86_400_000,
        "w": 604_800_000,
    }

    return value * multipliers.get(unit, 60_000)


def tradingview_link(symbol: str, timeframe: str) -> str:
    """لینک مستقیم چارت TradingView برای نماد/تایم‌فریم."""
    tv_interval = TV_INTERVAL_MAP.get(timeframe, "")
    link = f"https://www.tradingview.com/chart/?symbol=BINANCE:{symbol}"

    if tv_interval:
        link += f"&interval={tv_interval}"

    return link


def human_number(n):
    """فرمت خوانا برای عددهای بزرگ (حجم، مارکت‌کپ و ...) با K/M/B."""
    if n is None:
        return "نامشخص"

    try:
        n = float(n)
    except (TypeError, ValueError):
        return "نامشخص"

    sign = "-" if n < 0 else ""
    n = abs(n)

    for unit, div in (("B", 1_000_000_000), ("M", 1_000_000), ("K", 1_000)):
        if n >= div:
            return f"{sign}{n / div:.2f}{unit}"

    return f"{sign}{n:.2f}"


def get_ticker_24hr_quote_volume(symbol: str):
    """
    حجم ۲۴ ساعته (بر حسب quote asset) یک نماد رو می‌گیره، با همون
    اولویت EXCHANGE_PRIORITY. KuCoin هم برای این بخش پشتیبانی میشه
    چون فقط برای نمایش تو پیامه، نه انتخاب نماد.
    """
    errors = []

    for exchange in EXCHANGE_PRIORITY:
        try:
            if exchange == "binance":
                url = f"{BINANCE_BASE}/api/v3/ticker/24hr"
                resp = requests.get(url, params={"symbol": symbol}, timeout=15)
                resp.raise_for_status()
                return float(resp.json().get("quoteVolume", 0))

            if exchange == "mexc":
                url = f"{MEXC_BASE}/api/v3/ticker/24hr"
                resp = requests.get(url, params={"symbol": symbol}, timeout=15)
                resp.raise_for_status()
                return float(resp.json().get("quoteVolume", 0))

            if exchange == "kucoin":
                kucoin_symbol = to_kucoin_symbol(symbol, QUOTE_ASSET)
                url = f"{KUCOIN_BASE}/api/v1/market/stats"
                resp = requests.get(url, params={"symbol": kucoin_symbol}, timeout=15)
                resp.raise_for_status()
                payload = resp.json()
                if payload.get("code") != "200000":
                    raise RuntimeError(f"KuCoin error: {payload.get('code')}")
                return float(payload.get("data", {}).get("volValue", 0))

        except Exception as e:
            errors.append(f"{exchange}: {e}")
            continue

    raise RuntimeError(f"گرفتن حجم ۲۴ ساعته {symbol} از همه‌ی صرافی‌ها شکست خورد: {errors}")


def get_extra_volumes(symbol: str):
    """
    حجم (quote volume، یعنی بر حسب USDT) در بازه‌های:
      - ۱ ساعت گذشته  -> مجموع ۶۰ کندل ۱ دقیقه‌ای
      - ۲۴ ساعت گذشته -> از endpoint رسمی ticker/24hr بایننس
      - ۷ روز گذشته   -> مجموع ۷ کندل روزانه (شامل کندل امروز که هنوز
                          کامل نشده، به‌صورت تقریبی)
    فقط زمانی صدا زده میشه که سیگنالی برای ارسال پیدا شده، نه برای
    همه‌ی نمادها، تا تعداد درخواست‌ها به بایننس زیاد نشه.
    """
    vol_1h = None
    vol_24h = None
    vol_7d = None

    try:
        k1m = get_klines(symbol, "1m", 60)
        vol_1h = sum(float(k[7]) for k in k1m)  # index 7 = quote asset volume
    except Exception as e:
        print(f"[WARN] volume 1h {symbol}: {e}")

    try:
        vol_24h = get_ticker_24hr_quote_volume(symbol)
    except Exception as e:
        print(f"[WARN] volume 24h {symbol}: {e}")

    try:
        k1d = get_klines(symbol, "1d", 7)
        vol_7d = sum(float(k[7]) for k in k1d)
    except Exception as e:
        print(f"[WARN] volume 7d {symbol}: {e}")

    return vol_1h, vol_24h, vol_7d


def _price_zone_stats(orders):
    """
    برای یک لیست سفارش [(price, qty), ...] این‌ها رو حساب می‌کنه:
      - میانگین قیمت وزن‌دار بر اساس حجم (weighted average price)
      - محدوده‌ی قیمتی (کمترین تا بیشترین قیمتی که این سفارش‌ها توش هستن)
    """
    if not orders:
        return None, None, None

    total_qty = sum(q for _, q in orders)
    if total_qty <= 0:
        return None, None, None

    weighted_avg_price = sum(p * q for p, q in orders) / total_qty
    prices = [p for p, _ in orders]

    return weighted_avg_price, min(prices), max(prices)


def _get_depth_binance(symbol: str, limit: int):
    url = f"{BINANCE_BASE}/api/v3/depth"
    resp = requests.get(url, params={"symbol": symbol, "limit": limit}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return data.get("bids", []), data.get("asks", [])


def _get_depth_mexc(symbol: str, limit: int):
    url = f"{MEXC_BASE}/api/v3/depth"
    # MEXC فقط از این مقادیر مشخص برای limit پشتیبانی می‌کنه
    allowed = [5, 10, 20, 50, 100, 500, 1000]
    mexc_limit = min(allowed, key=lambda x: abs(x - limit))
    resp = requests.get(url, params={"symbol": symbol, "limit": mexc_limit}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return data.get("bids", []), data.get("asks", [])


def _get_depth_kucoin(symbol: str, limit: int):
    kucoin_symbol = to_kucoin_symbol(symbol, QUOTE_ASSET)
    url = f"{KUCOIN_BASE}/api/v1/market/orderbook/level2_100"
    resp = requests.get(url, params={"symbol": kucoin_symbol}, timeout=15)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("code") != "200000":
        raise RuntimeError(f"KuCoin error: {payload.get('code')}")
    data = payload.get("data", {})
    return data.get("bids", []), data.get("asks", [])


_DEPTH_FETCHERS = {
    "binance": _get_depth_binance,
    "mexc": _get_depth_mexc,
    "kucoin": _get_depth_kucoin,
}


def get_order_book_summary(symbol: str, limit: int = ORDERBOOK_LIMIT, top_n: int = ORDERBOOK_WALL_TOP_N):
    """
    خلاصه‌ی اردربوک فعلی:
      - مجموع حجم تجمیعی سمت خرید (bids) و فروش (asks) در عمق مشخص‌شده
      - مجموع ارزش (notional) بزرگ‌ترین N سفارش هر سمت (دیوارهای احتمالی)
      - درصد عدم‌تعادل خرید/فروش (imbalance)
      - محدوده‌ی قیمتی و میانگین قیمت وزن‌دار بزرگ‌ترین سفارش‌های هر سمت
    فقط زمانی صدا زده میشه که سیگنالی برای ارسال پیدا شده. اردربوک هم
    مثل کندل‌ها به ترتیب EXCHANGE_PRIORITY از صرافی‌های مختلف گرفته میشه.
    """
    errors = []
    raw_bids, raw_asks = None, None

    for exchange in EXCHANGE_PRIORITY:
        fetcher = _DEPTH_FETCHERS.get(exchange)
        if not fetcher:
            continue

        try:
            raw_bids, raw_asks = fetcher(symbol, limit)
            if raw_bids or raw_asks:
                break
        except Exception as e:
            errors.append(f"{exchange}: {e}")
            raw_bids, raw_asks = None, None
            continue

    if not raw_bids and not raw_asks:
        raise RuntimeError(f"گرفتن اردربوک {symbol} از همه‌ی صرافی‌ها شکست خورد: {errors}")

    bids = [(float(p), float(q)) for p, q in raw_bids]
    asks = [(float(p), float(q)) for p, q in raw_asks]

    total_bid_qty = sum(q for _, q in bids)
    total_ask_qty = sum(q for _, q in asks)

    total_bid_notional = sum(p * q for p, q in bids)
    total_ask_notional = sum(p * q for p, q in asks)

    top_bids = sorted(bids, key=lambda x: x[1], reverse=True)[:top_n]
    top_asks = sorted(asks, key=lambda x: x[1], reverse=True)[:top_n]

    top_bids_notional = sum(p * q for p, q in top_bids)
    top_asks_notional = sum(p * q for p, q in top_asks)

    bid_wavg_price, bid_price_min, bid_price_max = _price_zone_stats(top_bids)
    ask_wavg_price, ask_price_min, ask_price_max = _price_zone_stats(top_asks)

    imbalance_pct = None
    denom = total_bid_qty + total_ask_qty
    if denom > 0:
        imbalance_pct = (total_bid_qty - total_ask_qty) / denom * 100

    return {
        "total_bid_notional": total_bid_notional,
        "total_ask_notional": total_ask_notional,
        "top_bids_notional": top_bids_notional,
        "top_asks_notional": top_asks_notional,
        "imbalance_pct": imbalance_pct,
        "bid_wavg_price": bid_wavg_price,
        "bid_price_min": bid_price_min,
        "bid_price_max": bid_price_max,
        "ask_wavg_price": ask_wavg_price,
        "ask_price_min": ask_price_min,
        "ask_price_max": ask_price_max,
    }


def load_coingecko_market_map(pages: int = COINGECKO_PAGES):
    """
    نگاشت symbol (مثلاً "BTC") -> {market_cap, rank, name} با گرفتن
    چند صفحه از coins/markets (مرتب‌شده بر اساس مارکت‌کپ نزولی).
    فقط یک‌بار در ابتدای هر اجرای اسکریپت ساخته میشه، و فقط برای
    نمایش مارکت‌کپ/رنک تو پیام استفاده میشه (نه انتخاب نماد).

    توجه: چون چند کوین ممکنه symbol یکسان داشته باشن، در صورت تکرار
    symbol، اونی که رنک بهتر (عدد کوچیک‌تر) داره نگه داشته میشه.
    """
    mapping = {}

    if not COINGECKO_ENABLED:
        return mapping

    for page in range(1, pages + 1):
        try:
            resp = requests.get(
                f"{COINGECKO_BASE}/coins/markets",
                params={
                    "vs_currency": "usd",
                    "order": "market_cap_desc",
                    "per_page": 250,
                    "page": page,
                    "sparkline": "false",
                },
                timeout=20,
            )
            resp.raise_for_status()
            rows = resp.json()

            if not rows:
                break

            for row in rows:
                symbol = (row.get("symbol") or "").upper()
                if not symbol:
                    continue

                rank = row.get("market_cap_rank")

                existing = mapping.get(symbol)
                if existing and existing["rank"] is not None:
                    if rank is None or rank >= existing["rank"]:
                        continue

                mapping[symbol] = {
                    "market_cap": row.get("market_cap"),
                    "rank": rank,
                    "name": row.get("name"),
                }

            time.sleep(COINGECKO_SLEEP)

        except Exception as e:
            print(f"[WARN] CoinGecko page {page}: {e}")
            break

    print(f"[INFO] CoinGecko market map: {len(mapping)} کوین بارگذاری شد.")

    return mapping


def evaluate_symbol(symbol: str, timeframe: str):
    """
    منطق سیگنال روی آخرین کندل بسته‌شده — دقیقاً مطابق آخرین نسخه‌ی
    اسکریپت Pine v6:
      - small_body + سایه‌ی غالب با نسبت جدا برای بولیش/بریش
      - close بالا/پایین هر سه SMA + چیدمان صحیح SMA ها نسبت به هم
      - بدنه نباید SMA7 رو قطع کرده باشه
      - فاصله‌ی close تا SMA7 <= SMA7_MAX_DIST_MULT * رنج خود کندل
      - فیلتر روند با ADX: ADX >= آستانه -> سیگنال عادی،
        ADX < آستانه -> همون سیگنال به‌صورت "ریسکی"
      - شرط حجم (حجم کندل فعلی کمتر از قبلی) فقط تگ می‌خوره، فیلتر نیست
      - تایید هم‌جهتی با تایم بالاتر (HTF Confirmation) فقط تگ می‌خوره،
        فیلتر نیست

    خروجی: dict یا None اگه سیگنالی نبود.
    """

    raw = get_klines(symbol, timeframe, KLINES_LIMIT)

    if not raw or len(raw) < SMA_TREND_LEN + 2:
        return None

    # Binance kline:
    # [open_time, open, high, low, close, volume, close_time, ...]

    opens = [float(k[1]) for k in raw]
    highs = [float(k[2]) for k in raw]
    lows = [float(k[3]) for k in raw]
    closes = [float(k[4]) for k in raw]
    volumes = [float(k[5]) for k in raw]

    open_times = [int(k[0]) for k in raw]
    close_times = [int(k[6]) for k in raw]

    # اگر آخرین کندل هنوز بسته نشده، قبلی را بررسی کن
    now_ms = int(time.time() * 1000)

    idx = len(raw) - 1

    if close_times[idx] > now_ms:
        idx -= 1

    if idx < SMA_TREND_LEN or idx < 1:
        return None

    sma7_series = sma(closes, SMA_FAST_LEN)
    sma25_series = sma(closes, SMA_MID_LEN)
    sma99_series = sma(closes, SMA_TREND_LEN)
    rsi_series = rsi(closes, RSI_LEN)
    adx_values = adx_series(highs, lows, closes, ADX_LEN, ADX_SMOOTHING)

    sma7 = sma7_series[idx]
    sma25 = sma25_series[idx]
    sma99 = sma99_series[idx]
    rsi_value = rsi_series[idx]
    adx_val = adx_values[idx]

    if sma7 is None or sma25 is None or sma99 is None:
        return None

    if adx_val is None:
        return None

    o = opens[idx]
    h = highs[idx]
    l = lows[idx]
    c = closes[idx]

    body = abs(c - o)

    upper_shadow = h - max(c, o)
    lower_shadow = min(c, o) - l

    candle_range = h - l

    if candle_range == 0:
        return None

    small_body = (
        body > 0
        and body <= candle_range * MAX_BODY_RATIO
    )

    upper_dominant = upper_shadow > lower_shadow
    lower_dominant = lower_shadow > upper_shadow

    above_all_sma = (
        c > sma7
        and c > sma25
        and c > sma99
    )

    below_all_sma = (
        c < sma7
        and c < sma25
        and c < sma99
    )

    # چیدمان صحیح SMA ها نسبت به هم (ترتیب صعودی/نزولی)
    sma_stack_bull = sma7 > sma25 and sma25 > sma99
    sma_stack_bear = sma7 < sma25 and sma25 < sma99

    body_high = max(o, c)
    body_low = min(o, c)

    body_crosses_sma7 = (
        sma7 >= body_low
        and sma7 <= body_high
    )

    # فاصله‌ی close همون کندل ستاپ تا SMA7 - فقط بر اساس خود همون کندل
    dist_to_sma7 = abs(c - sma7)
    near_sma7 = dist_to_sma7 <= candle_range * SMA7_MAX_DIST_MULT

    bullish_base = (
        small_body
        and lower_dominant
        and lower_shadow >= body * SHADOW_RATIO_BULL
        and above_all_sma
        and sma_stack_bull
        and not body_crosses_sma7
        and near_sma7
    )

    bearish_base = (
        small_body
        and upper_dominant
        and upper_shadow >= body * SHADOW_RATIO_BEAR
        and below_all_sma
        and sma_stack_bear
        and not body_crosses_sma7
        and near_sma7
    )

    trending = adx_val >= ADX_THRESHOLD

    if bullish_base:
        signal = "bullish"
        risky = not trending
    elif bearish_base:
        signal = "bearish"
        risky = not trending
    else:
        return None

    # شرط حجم - فقط تگ می‌خوره، سیگنال رو فیلتر نمی‌کنه
    vol_now = volumes[idx]
    vol_prev = volumes[idx - 1]
    no_volume = not (vol_now < vol_prev)

    # --- تایید هم‌جهتی با تایم فریم بالاتر (HTF Confirmation) ---
    # دقیقاً مثل دایره‌ی تاییدیه‌ی اسکریپت Pine: فیلتر نمی‌کنه، فقط
    # به‌عنوان یه تگ جدا روی سیگنال گذاشته میشه.
    htf_confirm = None
    htf_timeframe_used = None

    if USE_HTF_CONFIRM:
        htf_timeframe_used = get_htf_timeframe(timeframe)
        htf_stack = get_htf_sma_stack(symbol, htf_timeframe_used)

        if htf_stack is not None:
            htf_stack_bull, htf_stack_bear = htf_stack
            htf_confirm = htf_stack_bull if signal == "bullish" else htf_stack_bear

    interval_ms = interval_to_ms(timeframe)
    candles_ago = max(0, int((now_ms - close_times[idx]) // interval_ms))

    return {
        "signal": signal,
        "risky": risky,
        "no_volume": no_volume,
        "htf_confirm": htf_confirm,
        "htf_timeframe": htf_timeframe_used,
        "candle_open_ms": open_times[idx],
        "close_price": c,
        "rsi_value": rsi_value,
        "adx_value": adx_val,
        "candles_ago": candles_ago,
    }


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def send_telegram(text: str):

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(
            "[TELEGRAM SKIPPED] "
            "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID تنظیم نشدن."
        )
        return

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }

    try:
        resp = requests.post(
            url,
            data=payload,
            timeout=15
        )

        if resp.status_code != 200:
            print(
                f"[TELEGRAM ERROR] "
                f"{resp.status_code}: {resp.text}"
            )

    except Exception as e:
        print(f"[TELEGRAM EXCEPTION] {e}")


def build_symbol_message(symbol, tf_results, coingecko_map):
    """
    پیام واحد برای یک نماد که ممکنه شامل سیگنال چند تایم‌فریم باشه
    (مثلاً هم 15m هم 1h تو یه پیام). حجم/اردربوک/مارکت‌کپ فقط یک‌بار
    برای کل نماد گرفته و نمایش داده میشه.
    """

    lines_per_tf = []

    for tf, res in tf_results:
        is_bullish = res["signal"] == "bullish"
        direction_fa = "صعودی 🟢 #long" if is_bullish else "نزولی 🔴 #short"
        risky_tag = " ⚠️ ریسکی (رنج)" if res["risky"] else ""
        no_volume_tag = " 🟡 بدون شرط حجم" if res["no_volume"] else ""

        # تگ تایید هم‌جهتی با تایم فریم بالاتر (HTF Confirmation)
        htf_tag = ""
        if res.get("htf_confirm") is True:
            htf_tag = f" 🔵 هم‌جهت با {res.get('htf_timeframe')}"
        elif res.get("htf_confirm") is False:
            htf_tag = f" ⚪ ناهم‌جهت با {res.get('htf_timeframe')}"

        # همه‌ی شرایط رو داره: ریسکی نیست، شرط حجم رو داره، و اگه
        # تایید HTF فعاله، هم‌جهت هم تایید شده -> #pass
        is_full_pass = (
            not res["risky"]
            and not res["no_volume"]
            and res.get("htf_confirm") is True
        )
        pass_tag = " ✅ #pass" if is_full_pass else ""

        candle_time_str = datetime.fromtimestamp(
            res["candle_open_ms"] / 1000, tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M UTC")

        rsi_value = res["rsi_value"]
        is_hot = (
            (res["signal"] == "bullish" and rsi_value is not None and rsi_value > RSI_BULLISH_HOT)
            or (res["signal"] == "bearish" and rsi_value is not None and rsi_value < RSI_BEARISH_HOT)
        )
        rsi_str = "نامشخص" if rsi_value is None else f"{rsi_value:.1f}"
        if is_hot:
            rsi_str = f"⚠️{rsi_str}⚠️"

        candles_ago_str = "الان" if res["candles_ago"] == 0 else f"{res['candles_ago']} کندل پیش"

        adx_str = "؟" if res["adx_value"] is None else f"{res['adx_value']:.1f}"

        lines_per_tf.append(
            f"⏱ <b>{tf}</b>: {direction_fa}{risky_tag}{no_volume_tag}{htf_tag}{pass_tag}\n"
            f"   RSI {rsi_str} | ADX {adx_str} | 💰 {res['close_price']}\n"
            f"   🕒 {candle_time_str} ({candles_ago_str})"
        )

    vol_1h, vol_24h, vol_7d = get_extra_volumes(symbol)
    volume_line = (
        f"📈 حجم: 1h {human_number(vol_1h)} | "
        f"24h {human_number(vol_24h)} | 7d {human_number(vol_7d)}"
    )

    try:
        ob = get_order_book_summary(symbol)
    except Exception as e:
        print(f"[WARN] orderbook {symbol}: {e}")
        ob = None

    if ob:
        imbalance_str = (
            f"{ob['imbalance_pct']:+.1f}%" if ob["imbalance_pct"] is not None else "؟"
        )
        bid_str = f"~{ob['bid_wavg_price']:g}" if ob["bid_wavg_price"] is not None else "؟"
        ask_str = f"~{ob['ask_wavg_price']:g}" if ob["ask_wavg_price"] is not None else "؟"

        orderbook_line = (
            f"📖 اردربوک: خرید {human_number(ob['total_bid_notional'])} / "
            f"فروش {human_number(ob['total_ask_notional'])} "
            f"(عدم‌تعادل {imbalance_str})\n"
            f"   دیوار خرید {bid_str} | دیوار فروش {ask_str}"
        )
    else:
        orderbook_line = "📖 اردربوک: نامشخص"

    base_asset = symbol[:-len(QUOTE_ASSET)] if symbol.endswith(QUOTE_ASSET) else symbol
    mcap_info = coingecko_map.get(base_asset)
    if mcap_info:
        rank_str = f"#{mcap_info['rank']}" if mcap_info["rank"] else "؟"
        mcap_line = f"🏆 مارکت‌کپ: {human_number(mcap_info['market_cap'])} | رنک {rank_str}"
    else:
        mcap_line = "🏆 مارکت‌کپ/رنک: یافت نشد"

    # لینک چارت رو با تایم‌فریم اولین سیگنال (معمولاً کوچیک‌ترین) می‌سازیم
    tv_link = tradingview_link(symbol, tf_results[0][0])

    tf_block = "\n\n".join(lines_per_tf)

    msg = (
        f"<b>سیگنال‌های {symbol}</b>\n\n"
        f"{tf_block}\n\n"
        f"{volume_line}\n"
        f"{orderbook_line}\n"
        f"{mcap_line}\n\n"
        f"🔗 {tv_link}"
    )

    return msg


def main():

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(
            "[WARNING] TELEGRAM_BOT_TOKEN یا TELEGRAM_CHAT_ID "
            "ست نشده — پیام‌ها فقط توی لاگ چاپ میشن و تلگرام نمی‌فرسته."
        )

    state = load_state()

    # نگاشت مارکت‌کپ/رنک فقط برای نمایش تو پیام استفاده میشه
    coingecko_map = load_coingecko_market_map()

    symbols = get_top_symbols_by_volume(QUOTE_ASSET, TOP_N)

    print(
        f"[{datetime.now(timezone.utc).isoformat()}] "
        f"Checking top {len(symbols)} symbols "
        f"(by Binance 24h volume, TOP_N={TOP_N}) on timeframes {TIMEFRAMES}... "
        f"(HTF confirm: {'on' if USE_HTF_CONFIRM else 'off'}, "
        f"exchanges: {' -> '.join(EXCHANGE_PRIORITY)})"
    )

    bullish_count = 0
    bearish_count = 0
    pass_count = 0
    duplicate_skipped = 0
    messages_sent = 0

    # سیگنال‌های ریسکی (رنج) یا ناهم‌جهت با HTF اینجا جمع میشن و یکجا،
    # درست قبل از پیام پایان اسکن، فرستاده میشن. سیگنال‌های عادی (نه
    # ریسکی و نه ناهم‌جهت با HTF) همون لحظه فرستاده میشن.
    delayed_signals = []

    for symbol in symbols:

        tf_results = []

        for timeframe in TIMEFRAMES:

            try:
                result = evaluate_symbol(symbol, timeframe)

            except Exception as e:
                print(
                    f"[ERROR] {symbol} {timeframe}: {e}"
                )

                time.sleep(REQUEST_SLEEP)
                continue

            if result:

                key = f"{symbol}_{timeframe}"

                # --- جلوگیری از سیگنال تکراری ---
                if state.get(key) == result["candle_open_ms"]:
                    duplicate_skipped += 1
                    print(
                        f"[SKIP-DUP] {symbol} {timeframe}: "
                        f"سیگنال تکراریه (قبلاً روی همین کندل فرستاده شده)"
                    )
                    time.sleep(REQUEST_SLEEP)
                    continue

                tf_results.append((timeframe, result))

                if result["signal"] == "bullish":
                    bullish_count += 1
                else:
                    bearish_count += 1

                if (
                    not result["risky"]
                    and not result["no_volume"]
                    and result.get("htf_confirm") is True
                ):
                    pass_count += 1

                state[key] = result["candle_open_ms"]

                print(
                    f"[SIGNAL] {symbol} {timeframe}: {result['signal']} "
                    f"(risky={result['risky']}, no_volume={result['no_volume']}, "
                    f"htf_confirm={result['htf_confirm']} [{result['htf_timeframe']}], "
                    f"RSI={result['rsi_value']}, ADX={result['adx_value']})"
                )

            time.sleep(REQUEST_SLEEP)

        # --- جدا کردن سیگنال‌های عادی از سیگنال‌های تأخیری ---
        # عادی: همون لحظه، به شکل یه پیام واحد برای این نماد فرستاده میشه.
        # تأخیری (ریسکی یا ناهم‌جهت با HTF): فرستاده نمیشه، فقط جمع
        # میشه تا آخر اسکن یکجا بره.
        def _is_delayed(res):
            return res["risky"] or res.get("htf_confirm") is False

        normal_tf_results = [(tf, res) for tf, res in tf_results if not _is_delayed(res)]
        delayed_tf_results = [(tf, res) for tf, res in tf_results if _is_delayed(res)]

        if normal_tf_results:
            msg = build_symbol_message(symbol, normal_tf_results, coingecko_map)
            send_telegram(msg)
            messages_sent += 1

        if delayed_tf_results:
            delayed_signals.append((symbol, delayed_tf_results))

    save_state(state)

    # ---- ارسال یکجای سیگنال‌های تأخیری (ریسکی یا ناهم‌جهت با HTF) ----
    if delayed_signals:
        send_telegram(
            f"<b>⚠️ سیگنال‌های ریسکی / ناهم‌جهت با HTF این اسکن</b>\n"
            f"تعداد: {len(delayed_signals)} نماد"
        )

        for symbol, delayed_tf_results in delayed_signals:
            msg = build_symbol_message(symbol, delayed_tf_results, coingecko_map)
            send_telegram(msg)
            messages_sent += 1

    # ---- پیام پایان اسکن ----
    total_signals = bullish_count + bearish_count
    finish_time_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    summary_msg = (
        f"<b>✅ پایان اسکن</b>\n"
        f"🕒 {finish_time_str}\n"
        f"پیام‌های ارسال‌شده: <b>{messages_sent}</b>\n"
        f"مجموع سیگنال‌های جدید: <b>{total_signals}</b> "
        f"(🟢 {bullish_count} #long / 🔴 {bearish_count} #short)\n"
        f"✅ #pass (همه‌ی شرایط کامل): <b>{pass_count}</b>\n"
        f"تکراری نادیده‌گرفته‌شده: {duplicate_skipped}"
    )

    send_telegram(summary_msg)
    # --------------------------

    print("Done.")


if __name__ == "__main__":
    main()
