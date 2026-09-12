"""
Setup Candle + SMA Alert Bot (Binance SPOT + MEXC FUTURES fallback -> Telegram)
Multi-Timeframe
============================================================================
منطق سیگنال دقیقاً منطبق با آخرین نسخه‌ی اسکریپت Pine v6
(indicator "Setup Candle - Step 10 (+ SMA Entanglement)") هست:
  - بدنه کوچک، بر اساس ATR (نه رنج خود کندل): body <= ATR * MAX_BODY_ATR_MULT
  - موقعیت بدنه در رنج کندل (Body Position): برای بولیش بدنه باید تو
    پایین رنج باشه (hammer)، برای بریش تو بالای رنج (shooting star)
  - سایه‌ی غالب حداقل به اندازه‌ی ATR * MIN_DOMINANT_SHADOW_ATR_MULT
  - سایه‌ی مقابل (غیرغالب) حداکثر MAX_OPPOSITE_SHADOW_PCT درصد از کل
    رنج کندل
  - close بالای/پایین هر سه SMA (7, 25, 99) به‌طور هم‌زمان + چیدمان
    صحیح SMA ها نسبت به هم
  - بدنه‌ی کندل نباید SMA7 رو قطع کرده باشه + فاصله‌ی close تا SMA7
    نباید بیشتر از SMA7_MAX_DIST_MULT برابر ATR باشه
  - فیلتر Cross Count: فقط تقاطع SMA7×SMA25 (نه هر سه‌تایی) تو
    CROSS_LOOKBACK کندل اخیر نباید از MAX_CROSS_COUNT بیشتر باشه
  - فیلتر درگیری/فشردگی SMA (Entanglement): پهنای بین بالاترین و
    پایین‌ترین SMA باید حداقل SMA_ENTANGLEMENT_ATR_MULT برابر ATR باشه
  - فیلتر Choppiness Index: باید زیر CHOP_THRESHOLD باشه (یعنی بازار
    ترنده، نه رنج)
  - فیلتر ساختار Higher-High/Higher-Low ساده روی SWING_LOOKBACK کندل
  - فیلتر اختلاف DI+/DI- (نه ADX خام): |DI+ - DI-| باید از
    DI_DIFF_THRESHOLD بیشتر باشه و در جهت سیگنال
  - همه‌ی فیلترهای بالا (Chop + Structure + DI-Diff + Cross + عدم‌درگیری)
    الان بخشی جدایی‌ناپذیر از خود شرط سیگنال هستن، نه یه تگ "ریسکی"
    جدا؛ یعنی اگه بازار رنج/درگیر باشه، اصلاً سیگنالی تولید نمیشه.
    به همین خاطر مفهوم "ریسکی" و پیام جدا برای سیگنال‌های ریسکی از این
    نسخه کاملاً حذف شده.
  - شرط حجم فیلتر نیست؛ فقط تگ جدا (No-Volume-Condition)
  - تایید هم‌جهتی با تایم‌فریم بالاتر (HTF Confirmation) - این نسخه:
    این بند حالا یک فیلتر واقعی و اجباریه (نه فقط یه تگ روی پیام).
    اگه سیگنال با تایم‌فریم بالاتر هم‌جهت نباشه (یعنی همون سیگنال
    "زرد/⚠️" تو اندیکاتور پاین) یا اصلاً نشه هم‌جهتی رو تشخیص داد
    (داده‌ی کافی نبود)، سیگنال کاملاً کنار گذاشته میشه و هیچ پیامی
    براش فرستاده نمیشه.

--- منبع داده (این نسخه) ---
اولویت اول: بایننس SPOT (نه فیوچرز، چون فیوچرز بایننس رو خیلی از
سرورها با خطای 451 بلاک می‌کنه).
اولویت دوم: MEXC فیوچرز (USDT-M Perpetual) - فقط برای نمادهایی که
اصلاً تو بایننس اسپات موجود نیستن.

نصب پیش‌نیازها:
    pip install requests

تنظیم قبل از اجرا (به‌صورت متغیر محیطی):
    export TELEGRAM_BOT_TOKEN="..."
    export TELEGRAM_CHAT_ID="..."

اجرای محلی با cron (مثال: هر ۱۵ دقیقه):
    */15 * * * * TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=yyy /usr/bin/python3 /path/to/setup_alert_bot.py >> /path/to/bot.log 2>&1
"""

import json
import math
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

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
TOP_N = int(os.environ.get("TOP_N", "400"))   # نمادهای برتر بر اساس حجم معاملات (ترکیبی بایننس+مکسی)

# فقط قراردادهای Perpetual مکسی (نه Delivery) در نظر گرفته میشن
FUTURES_ONLY_PERPETUAL = os.environ.get("FUTURES_ONLY_PERPETUAL", "1") == "1"

# --- بدنه و سایه (بر مبنای ATR - دقیقاً مطابق اندیکاتور جدید) ---
MAX_BODY_ATR_MULT = float(os.environ.get("MAX_BODY_ATR_MULT", "0.4"))
MIN_DOMINANT_SHADOW_ATR_MULT = float(os.environ.get("MIN_DOMINANT_SHADOW_ATR_MULT", "0.2"))
MAX_OPPOSITE_SHADOW_PCT = float(os.environ.get("MAX_OPPOSITE_SHADOW_PCT", "25.0"))
BODY_POSITION_THRESHOLD = float(os.environ.get("BODY_POSITION_THRESHOLD", "0.5"))

SMA_FAST_LEN = int(os.environ.get("SMA_FAST_LEN", "7"))
SMA_MID_LEN = int(os.environ.get("SMA_MID_LEN", "25"))
SMA_TREND_LEN = int(os.environ.get("SMA_TREND_LEN", "99"))

# فاصله‌ی close کندل ستاپ تا SMA7 - بر مبنای ATR
SMA7_MAX_DIST_MULT = float(os.environ.get("SMA7_MAX_DIST_MULT", "1.0"))

# فیلتر Cross Count: فقط تقاطع SMA7×SMA25 تو این تعداد کندل اخیر
# نباید از MAX_CROSS_COUNT بیشتر باشه (بیشتر از این یعنی بازار رنجه)
CROSS_LOOKBACK = int(os.environ.get("CROSS_LOOKBACK", "20"))
MAX_CROSS_COUNT = int(os.environ.get("MAX_CROSS_COUNT", "1"))

# فیلتر درگیری/فشردگی هر سه SMA با هم: پهنای بین بالاترین و
# پایین‌ترین SMA باید حداقل این‌قدر برابر ATR باشه، وگرنه "درگیر"
# (entangled) حساب میشه و سیگنال حذف میشه
SMA_ENTANGLEMENT_ATR_MULT = float(os.environ.get("SMA_ENTANGLEMENT_ATR_MULT", "2.0"))

# --- Choppiness Index (رنج/ترند) ---
CHOP_LEN = int(os.environ.get("CHOP_LEN", "14"))
CHOP_THRESHOLD = float(os.environ.get("CHOP_THRESHOLD", "61.8"))

# --- ساختار Higher-High/Higher-Low ---
SWING_LOOKBACK = int(os.environ.get("SWING_LOOKBACK", "10"))

# --- اختلاف DI+/DI- (نه ADX خام) ---
DMI_LEN = int(os.environ.get("DMI_LEN", "14"))
DMI_SMOOTHING = int(os.environ.get("DMI_SMOOTHING", "14"))
DI_DIFF_THRESHOLD = float(os.environ.get("DI_DIFF_THRESHOLD", "5.0"))

# ATR مشترک برای بدنه/سایه، near_sma7 و فیلتر entanglement
ATR_LEN = int(os.environ.get("ATR_LEN", "14"))

RSI_LEN = int(os.environ.get("RSI_LEN", "21"))

# --- تایید هم‌جهتی با تایم فریم بالاتر (HTF Confirmation) ---
# این نسخه: این پرچم الان یک فیلتر واقعیه. اگه True باشه، فقط سیگنال‌هایی
# که با SMA-Stack تایم‌فریم بالاتر هم‌جهت باشن (htf_confirm == True)
# فرستاده میشن؛ سیگنال‌های ناهم‌جهت (زرد/⚠️) و سیگنال‌هایی که هم‌جهتی‌شون
# قابل تشخیص نبوده (داده‌ی HTF ناکافی) کلاً حذف میشن.
USE_HTF_CONFIRM = os.environ.get("USE_HTF_CONFIRM", "1") == "1"
AUTO_HTF = os.environ.get("AUTO_HTF", "1") == "1"
MANUAL_HTF = os.environ.get("MANUAL_HTF", "1h")  # فقط وقتی AUTO_HTF خاموشه یا نگاشتی نداره

# نگاشت خودکار تایم بالاتر: 15m -> 1h, 1h -> 4h, 4h -> 1d, 1d -> 1w
AUTO_HTF_MAP = {
    "15m": "1h",
    "1h": "4h",
    "4h": "1d",
    "1d": "1w",
}

# باید به اندازه‌ی کافی کندل داشته باشیم برای:
#   - SMA99 + وارم‌آپ Cross Count
#   - وارم‌آپ DMI/ADX
#   - وارم‌آپ ATR
#   - وارم‌آپ Choppiness (highest/lowest/sum روی CHOP_LEN)
#   - وارم‌آپ ساختار HH/HL روی SWING_LOOKBACK
KLINES_LIMIT = max(
    SMA_TREND_LEN + CROSS_LOOKBACK + 10,
    DMI_LEN + DMI_SMOOTHING + 20,
    ATR_LEN + 20,
    CHOP_LEN + 20,
    SWING_LOOKBACK + 20,
    150,
)

# کندل کافی برای محاسبه‌ی چیدمان SMA روی تایم فریم بالاتر
HTF_KLINES_LIMIT = max(SMA_TREND_LEN + 5, 110)

# اردربوک
ORDERBOOK_LIMIT = int(os.environ.get("ORDERBOOK_LIMIT", "100"))
ORDERBOOK_WALL_TOP_N = int(os.environ.get("ORDERBOOK_WALL_TOP_N", "10"))

STATE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "alert_state.json"
)

# --- بایننس اسپات (اولویت اول) ---
BINANCE_SPOT_BASE = os.environ.get("BINANCE_SPOT_BASE", "https://data-api.binance.vision")
BINANCE_DEPTH_VALID_LIMITS = [5, 10, 20, 50, 100, 500, 1000, 5000]

# --- MEXC فیوچرز (اولویت دوم / fallback) ---
MEXC_FUTURES_BASE = "https://contract.mexc.com"

# نگاشت تایم‌فریم داخلی (سبک بایننس) به اینتروال MEXC فیوچرز
MEXC_INTERVAL_MAP = {
    "1m": "Min1",
    "5m": "Min5",
    "15m": "Min15",
    "30m": "Min30",
    "1h": "Min60",
    "4h": "Hour4",
    "8h": "Hour8",
    "1d": "Day1",
    "1w": "Week1",
    "1M": "Month1",
}

# نگاشت تایم‌فریم به فرمت اینتروال TradingView
TV_INTERVAL_MAP = {
    "1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
    "1h": "60", "2h": "120", "4h": "240", "6h": "360", "8h": "480",
    "12h": "720", "1d": "D", "3d": "3D", "1w": "W", "1M": "M",
}

# وقت تهران (Iran Standard Time) = UTC + 3:30
TEHRAN_OFFSET = timedelta(hours=3, minutes=30)

# --- موازی‌سازی و محافظ ریت‌لیمیت ---
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "20"))
MAX_HTTP_RETRIES = int(os.environ.get("MAX_HTTP_RETRIES", "4"))

# =======================================================================


def http_get_with_retry(url, params=None, timeout=15, max_retries=MAX_HTTP_RETRIES):
    last_exc = None

    for attempt in range(max_retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
        except requests.exceptions.RequestException as e:
            last_exc = e
            wait = min(2 ** attempt, 20) + random.uniform(0, 0.5)
            time.sleep(wait)
            continue

        if resp.status_code in (429, 418):
            retry_after = resp.headers.get("Retry-After")
            try:
                wait = float(retry_after) if retry_after else min(2 ** attempt, 30)
            except ValueError:
                wait = min(2 ** attempt, 30)

            wait += random.uniform(0, 0.5)
            print(
                f"[RATE-LIMIT] {resp.status_code} از {url} — "
                f"{wait:.1f} ثانیه صبر و تلاش دوباره (تلاش {attempt + 1}/{max_retries + 1})..."
            )
            time.sleep(wait)
            last_exc = RuntimeError(f"HTTP {resp.status_code} rate-limited: {url}")
            continue

        if 500 <= resp.status_code < 600:
            last_exc = RuntimeError(f"HTTP {resp.status_code} server error: {url}")
            wait = min(2 ** attempt, 15) + random.uniform(0, 0.5)
            time.sleep(wait)
            continue

        resp.raise_for_status()
        return resp

    raise last_exc if last_exc else RuntimeError(f"گرفتن {url} شکست خورد")


def to_mexc_symbol(symbol: str, quote_asset: str) -> str:
    if symbol.endswith(quote_asset):
        base = symbol[: -len(quote_asset)]
        return f"{base}_{quote_asset}"

    return symbol


def from_mexc_symbol(mexc_symbol: str) -> str:
    return mexc_symbol.replace("_", "")


def interval_to_ms(interval: str) -> int:
    unit = interval[-1]
    value = int(interval[:-1])

    multipliers = {
        "m": 60_000,
        "h": 3_600_000,
        "d": 86_400_000,
        "w": 604_800_000,
    }

    return value * multipliers.get(unit, 60_000)


# --------------------------- بایننس اسپات ---------------------------

def get_binance_all_symbols(quote_asset: str):
    url = f"{BINANCE_SPOT_BASE}/api/v3/exchangeInfo"

    try:
        resp = http_get_with_retry(url, timeout=15)
        payload = resp.json()
    except Exception as e:
        print(f"[ERROR] گرفتن لیست نمادهای بایننس اسپات شکست خورد: {e}")
        return []

    symbols = []
    for s in payload.get("symbols", []):
        if s.get("status") != "TRADING":
            continue
        if s.get("quoteAsset") != quote_asset:
            continue
        if not s.get("isSpotTradingAllowed", True):
            continue

        sym = s.get("symbol")
        if sym:
            symbols.append(sym)

    return symbols


def get_binance_top_symbols_by_volume(quote_asset: str):
    valid_symbols = get_binance_all_symbols(quote_asset)
    if not valid_symbols:
        return []

    valid_set = set(valid_symbols)
    url = f"{BINANCE_SPOT_BASE}/api/v3/ticker/24hr"

    try:
        resp = http_get_with_retry(url, timeout=20)
        data = resp.json()
    except Exception as e:
        print(f"[ERROR] گرفتن حجم ۲۴ ساعته بایننس شکست خورد: {e}")
        return [(s, 0.0) for s in valid_symbols]

    rows = []
    for row in data:
        sym = row.get("symbol")
        if sym not in valid_set:
            continue

        try:
            qv = float(row.get("quoteVolume", 0))
        except (TypeError, ValueError):
            qv = 0.0

        rows.append((sym, qv))

    rows.sort(key=lambda x: x[1], reverse=True)

    return rows


def get_binance_klines(symbol: str, interval: str, limit: int):
    url = f"{BINANCE_SPOT_BASE}/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}

    resp = http_get_with_retry(url, params=params, timeout=15)
    data = resp.json()

    rows = []
    for k in data:
        rows.append([
            int(k[0]),
            float(k[1]),
            float(k[2]),
            float(k[3]),
            float(k[4]),
            float(k[5]),
            int(k[6]),
            float(k[7]),
        ])

    return rows


def get_binance_ticker_24hr_quote_volume(symbol: str):
    url = f"{BINANCE_SPOT_BASE}/api/v3/ticker/24hr"
    resp = http_get_with_retry(url, params={"symbol": symbol}, timeout=15)
    data = resp.json()

    return float(data.get("quoteVolume", 0))


def get_binance_depth(symbol: str, limit: int):
    url = f"{BINANCE_SPOT_BASE}/api/v3/depth"
    lim = min(BINANCE_DEPTH_VALID_LIMITS, key=lambda x: abs(x - limit))

    resp = http_get_with_retry(url, params={"symbol": symbol, "limit": lim}, timeout=15)
    data = resp.json()

    bids = [(float(p), float(q)) for p, q in data.get("bids", [])]
    asks = [(float(p), float(q)) for p, q in data.get("asks", [])]

    return bids, asks


# --------------------------- MEXC فیوچرز ---------------------------

def get_mexc_all_symbols(quote_asset: str):
    url = f"{MEXC_FUTURES_BASE}/api/v1/contract/detail"

    try:
        resp = http_get_with_retry(url, timeout=15)
        payload = resp.json()
    except Exception as e:
        print(f"[ERROR] گرفتن لیست قراردادهای فیوچرز MEXC شکست خورد: {e}")
        return []

    if not payload.get("success", True):
        print(f"[ERROR] MEXC contract/detail error: {payload}")
        return []

    data = payload.get("data", [])
    if isinstance(data, dict):
        data = [data]

    symbols = []
    for s in data:
        if s.get("state") != 0:
            continue

        if s.get("quoteCoin") != quote_asset:
            continue

        if FUTURES_ONLY_PERPETUAL and s.get("futureType") != 1:
            continue

        mexc_symbol = s.get("symbol")
        if not mexc_symbol:
            continue

        symbols.append(from_mexc_symbol(mexc_symbol))

    return symbols


def get_mexc_top_symbols_by_volume(quote_asset: str):
    valid_symbols = get_mexc_all_symbols(quote_asset)
    if not valid_symbols:
        return []

    url = f"{MEXC_FUTURES_BASE}/api/v1/contract/ticker"

    try:
        resp = http_get_with_retry(url, timeout=20)
        payload = resp.json()
    except Exception as e:
        print(f"[ERROR] گرفتن حجم ۲۴ ساعته فیوچرز MEXC شکست خورد: {e}")
        return [(s, 0.0) for s in valid_symbols]

    data = payload.get("data", [])
    if isinstance(data, dict):
        data = [data]

    ticker_map = {}
    for row in data:
        mexc_symbol = row.get("symbol")
        if not mexc_symbol:
            continue
        ticker_map[from_mexc_symbol(mexc_symbol)] = row

    rows = []
    for symbol in valid_symbols:
        row = ticker_map.get(symbol)
        if not row:
            continue

        try:
            quote_volume = float(row.get("amount24", 0))
        except (TypeError, ValueError):
            quote_volume = 0.0

        rows.append((symbol, quote_volume))

    rows.sort(key=lambda x: x[1], reverse=True)

    return rows


def get_mexc_klines(symbol: str, interval: str, limit: int):
    mexc_interval = MEXC_INTERVAL_MAP.get(interval)
    if not mexc_interval:
        raise ValueError(f"اینتروال {interval} برای MEXC فیوچرز پشتیبانی نمیشه")

    mexc_symbol = to_mexc_symbol(symbol, QUOTE_ASSET)
    interval_sec = interval_to_ms(interval) // 1000

    end = int(time.time())
    start = end - interval_sec * (limit + 5)

    url = f"{MEXC_FUTURES_BASE}/api/v1/contract/kline/{mexc_symbol}"
    params = {"interval": mexc_interval, "start": start, "end": end}

    resp = http_get_with_retry(url, params=params, timeout=15)
    payload = resp.json()

    if not payload.get("success", True):
        raise RuntimeError(f"MEXC futures kline error: {payload}")

    data = payload.get("data") or {}

    times = data.get("time") or []
    opens = data.get("open") or []
    highs = data.get("high") or []
    lows = data.get("low") or []
    closes = data.get("close") or []
    vols = data.get("vol") or []
    amounts = data.get("amount") or []

    rows = []
    for i in range(len(times)):
        open_time_ms = int(times[i]) * 1000
        close_time_ms = open_time_ms + interval_sec * 1000 - 1

        rows.append([
            open_time_ms,
            opens[i],
            highs[i],
            lows[i],
            closes[i],
            vols[i],
            close_time_ms,
            amounts[i] if i < len(amounts) else 0,
        ])

    return rows[-limit:] if limit else rows


def get_mexc_ticker_24hr_quote_volume(symbol: str):
    mexc_symbol = to_mexc_symbol(symbol, QUOTE_ASSET)
    url = f"{MEXC_FUTURES_BASE}/api/v1/contract/ticker"
    resp = http_get_with_retry(url, params={"symbol": mexc_symbol}, timeout=15)
    payload = resp.json()

    if not payload.get("success", True):
        raise RuntimeError(f"MEXC futures ticker error: {payload}")

    data = payload.get("data") or {}
    if isinstance(data, list):
        data = data[0] if data else {}

    return float(data.get("amount24", 0))


def get_mexc_depth(symbol: str, limit: int):
    mexc_symbol = to_mexc_symbol(symbol, QUOTE_ASSET)
    url = f"{MEXC_FUTURES_BASE}/api/v1/contract/depth/{mexc_symbol}"

    resp = http_get_with_retry(url, params={"limit": limit}, timeout=15)
    payload = resp.json()

    if not payload.get("success", True):
        raise RuntimeError(f"MEXC futures depth error: {payload}")

    data = payload.get("data") or {}
    raw_bids = data.get("bids", [])
    raw_asks = data.get("asks", [])

    bids = [(float(row[0]), float(row[1])) for row in raw_bids]
    asks = [(float(row[0]), float(row[1])) for row in raw_asks]

    return bids, asks


# ------------------------- دیسپچر چند-صرافی -------------------------

def get_top_symbols_combined(quote_asset: str, top_n: int):
    binance_rows = get_binance_top_symbols_by_volume(quote_asset)
    binance_symbol_set = {s for s, _ in binance_rows}

    if not binance_rows:
        print(
            "[WARNING] لیست بایننس خالی برگشت (خطای شبکه/API) — این اجرا "
            "همه‌ی نمادها موقتاً از مکسی فیوچرز حساب میشن، حتی اونایی که "
            "واقعاً تو بایننس هم هستن. اگه این هشدار مکرر دیدی، دسترسی به "
            "api.binance.com رو چک کن."
        )

    mexc_rows_all = get_mexc_top_symbols_by_volume(quote_asset)
    mexc_only_rows = [(s, v) for s, v in mexc_rows_all if s not in binance_symbol_set]

    combined = (
        [(s, v, "binance") for s, v in binance_rows]
        + [(s, v, "mexc") for s, v in mexc_only_rows]
    )
    combined.sort(key=lambda x: x[1], reverse=True)

    top = combined[:top_n]

    symbols = [s for s, _, _ in top]
    source_map = {s: src for s, _, src in top}

    binance_count = sum(1 for _, _, src in top if src == "binance")
    mexc_count = len(top) - binance_count

    print(
        f"[INFO] نمادهای انتخابی: {binance_count} از بایننس (اسپات)، "
        f"{mexc_count} از مکسی فیوچرز (از بین {len(top)} نماد)"
    )

    return symbols, source_map


def get_klines(symbol: str, interval: str, limit: int, source: str):
    if source == "binance":
        return get_binance_klines(symbol, interval, limit)
    return get_mexc_klines(symbol, interval, limit)


def get_extra_volumes(symbol: str, source: str):
    vol_1h = None
    vol_24h = None
    vol_7d = None

    try:
        k1m = get_klines(symbol, "1m", 60, source)
        vol_1h = sum(float(k[7]) for k in k1m)
    except Exception as e:
        print(f"[WARN] volume 1h {symbol}: {e}")

    try:
        if source == "binance":
            vol_24h = get_binance_ticker_24hr_quote_volume(symbol)
        else:
            vol_24h = get_mexc_ticker_24hr_quote_volume(symbol)
    except Exception as e:
        print(f"[WARN] volume 24h {symbol}: {e}")

    try:
        k1d = get_klines(symbol, "1d", 7, source)
        vol_7d = sum(float(k[7]) for k in k1d)
    except Exception as e:
        print(f"[WARN] volume 7d {symbol}: {e}")

    return vol_1h, vol_24h, vol_7d


def _price_zone_stats(orders):
    if not orders:
        return None, None, None

    total_qty = sum(q for _, q in orders)
    if total_qty <= 0:
        return None, None, None

    weighted_avg_price = sum(p * q for p, q in orders) / total_qty
    prices = [p for p, _ in orders]

    return weighted_avg_price, min(prices), max(prices)


def get_order_book_summary(symbol: str, source: str, limit: int = ORDERBOOK_LIMIT, top_n: int = ORDERBOOK_WALL_TOP_N):
    if source == "binance":
        bids, asks = get_binance_depth(symbol, limit)
    else:
        bids, asks = get_mexc_depth(symbol, limit)

    if not bids and not asks:
        raise RuntimeError(f"گرفتن اردربوک {symbol} شکست خورد (پاسخ خالی)")

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


def market_search_links(symbol: str, quote_asset: str):
    base_asset = symbol[:-len(quote_asset)] if symbol.endswith(quote_asset) else symbol

    coingecko_link = f"https://www.coingecko.com/en/search?query={base_asset}"
    cmc_link = f"https://coinmarketcap.com/search/?q={base_asset}"

    return coingecko_link, cmc_link


def tradingview_link(symbol: str, timeframe: str, source: str) -> str:
    tv_interval = TV_INTERVAL_MAP.get(timeframe, "")

    if source == "binance":
        link = f"https://www.tradingview.com/chart/?symbol=BINANCE:{symbol}"
    else:
        link = f"https://www.tradingview.com/chart/?symbol=MEXC:{symbol}.P"

    if tv_interval:
        link += f"&interval={tv_interval}"

    return link


# --------------------------- اندیکاتورها ---------------------------

def sma(values, length):
    result = [None] * len(values)

    for i in range(length - 1, len(values)):
        window = values[i - length + 1: i + 1]
        result[i] = sum(window) / length

    return result


def rsi(values, length=14):
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


def atr_series(highs, lows, closes, length):
    tr = true_range_series(highs, lows, closes)
    return rma(tr, length)


def dmi_series(highs, lows, closes, di_length, adx_smoothing):
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

    plus_di = [None] * n
    minus_di = [None] * n
    dx = [None] * n

    for i in range(n):
        if (
            tr_rma[i] is not None
            and tr_rma[i] != 0
            and plus_dm_rma[i] is not None
            and minus_dm_rma[i] is not None
        ):
            pdi = 100 * plus_dm_rma[i] / tr_rma[i]
            mdi = 100 * minus_dm_rma[i] / tr_rma[i]
            plus_di[i] = pdi
            minus_di[i] = mdi

            denom = pdi + mdi
            dx[i] = 100 * abs(pdi - mdi) / denom if denom != 0 else 0.0

    adx = rma(dx, adx_smoothing)

    return plus_di, minus_di, adx


def cross_events(series_a, series_b):
    n = len(series_a)
    result = [False] * n

    for i in range(1, n):
        a0, b0 = series_a[i], series_b[i]
        a1, b1 = series_a[i - 1], series_b[i - 1]

        if a0 is None or b0 is None or a1 is None or b1 is None:
            continue

        diff0 = a0 - b0
        diff1 = a1 - b1

        if diff1 * diff0 < 0:
            result[i] = True

    return result


def rolling_bool_sum(bool_series, idx, lookback):
    if idx - lookback + 1 < 0:
        return None

    window = bool_series[idx - lookback + 1: idx + 1]
    return sum(1 for v in window if v)


def choppiness_index_at(highs, lows, tr_series, idx, length):
    if idx - length + 1 < 0:
        return None

    tr_window = tr_series[idx - length + 1: idx + 1]
    if any(v is None for v in tr_window):
        return None

    chop_sum_tr = sum(tr_window)

    high_window = highs[idx - length + 1: idx + 1]
    low_window = lows[idx - length + 1: idx + 1]
    chop_range = max(high_window) - min(low_window)

    if chop_range <= 0:
        return 0.0

    return 100 * math.log10(chop_sum_tr / chop_range) / math.log10(length)


def structure_flags_at(highs, lows, idx, swing_lookback):
    if idx - swing_lookback < 0:
        return None, None

    prev_lows = lows[idx - swing_lookback: idx]
    prev_highs = highs[idx - swing_lookback: idx]

    structure_uptrend = lows[idx] > min(prev_lows)
    structure_downtrend = highs[idx] < max(prev_highs)

    return structure_uptrend, structure_downtrend


def get_htf_timeframe(base_timeframe: str) -> str:
    if AUTO_HTF and base_timeframe in AUTO_HTF_MAP:
        return AUTO_HTF_MAP[base_timeframe]

    return MANUAL_HTF


def get_htf_sma_stack(symbol: str, htf_timeframe: str, source: str):
    try:
        raw = get_klines(symbol, htf_timeframe, HTF_KLINES_LIMIT, source)
    except Exception as e:
        print(f"[WARN] HTF klines {symbol} {htf_timeframe}: {e}")
        return None

    if not raw or len(raw) < SMA_TREND_LEN + 1:
        return None

    closes = [float(k[4]) for k in raw]
    close_times = [int(k[6]) for k in raw]

    now_ms = int(time.time() * 1000)
    idx = len(raw) - 1

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


def human_number(n):
    if n is None:
        return "N/A"

    try:
        n = float(n)
    except (TypeError, ValueError):
        return "N/A"

    sign = "-" if n < 0 else ""
    n = abs(n)

    for unit, div in (("B", 1_000_000_000), ("M", 1_000_000), ("K", 1_000)):
        if n >= div:
            return f"{sign}{n / div:.2f}{unit}"

    return f"{sign}{n:.2f}"


def evaluate_symbol(symbol: str, timeframe: str, source: str):
    """
    منطق سیگنال روی آخرین کندل بسته‌شده — دقیقاً مطابق آخرین نسخه‌ی
    اسکریپت Pine v6 "Setup Candle - Step 10 (+ SMA Entanglement)".
    داده‌ها بسته به source از بایننس اسپات یا مکسی فیوچرز گرفته میشن.

    توجه (این نسخه): تایید هم‌جهتی با تایم‌فریم بالاتر (HTF Confirmation)
    الان یه فیلتر واقعیه، نه فقط یه تگ. اگه USE_HTF_CONFIRM روشن باشه و
    سیگنال با تایم‌فریم بالاتر هم‌جهت نباشه (سیگنال "زرد/⚠️" اندیکاتور
    پاین) یا اصلاً نشه هم‌جهتی رو تشخیص داد (داده‌ی HTF ناکافی)، این
    تابع None برمی‌گردونه؛ یعنی هیچ پیامی براش فرستاده نمیشه.
    """

    raw = get_klines(symbol, timeframe, KLINES_LIMIT, source)

    if not raw or len(raw) < SMA_TREND_LEN + 2:
        return None

    opens = [float(k[1]) for k in raw]
    highs = [float(k[2]) for k in raw]
    lows = [float(k[3]) for k in raw]
    closes = [float(k[4]) for k in raw]

    open_times = [int(k[0]) for k in raw]
    close_times = [int(k[6]) for k in raw]

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
    atr_values = atr_series(highs, lows, closes, ATR_LEN)
    tr_series = true_range_series(highs, lows, closes)
    plus_di_series, minus_di_series, adx_series_vals = dmi_series(
        highs, lows, closes, DMI_LEN, DMI_SMOOTHING
    )

    sma7 = sma7_series[idx]
    sma25 = sma25_series[idx]
    sma99 = sma99_series[idx]
    rsi_value = rsi_series[idx]
    atr_val = atr_values[idx]
    plus_di = plus_di_series[idx]
    minus_di = minus_di_series[idx]
    adx_val = adx_series_vals[idx]

    if sma7 is None or sma25 is None or sma99 is None:
        return None

    if atr_val is None or atr_val == 0:
        return None

    if plus_di is None or minus_di is None:
        return None

    o = opens[idx]
    h = highs[idx]
    l = lows[idx]
    c = closes[idx]

    body = abs(c - o)
    upper_shadow = h - max(c, o)
    lower_shadow = min(c, o) - l
    candle_range = h - l

    if candle_range <= 0:
        return None

    # --- بدنه و سایه (بر مبنای ATR) ---
    small_body = body <= atr_val * MAX_BODY_ATR_MULT

    body_low_position = (min(o, c) - l) / candle_range
    body_high_position = (max(o, c) - l) / candle_range

    is_hammer_position = body_low_position >= BODY_POSITION_THRESHOLD
    is_shooting_star_position = body_high_position <= (1 - BODY_POSITION_THRESHOLD)

    lower_shadow_big_enough = lower_shadow >= atr_val * MIN_DOMINANT_SHADOW_ATR_MULT
    upper_shadow_big_enough = upper_shadow >= atr_val * MIN_DOMINANT_SHADOW_ATR_MULT

    upper_shadow_tiny = upper_shadow <= candle_range * (MAX_OPPOSITE_SHADOW_PCT / 100)
    lower_shadow_tiny = lower_shadow <= candle_range * (MAX_OPPOSITE_SHADOW_PCT / 100)

    bullish_shape = (
        small_body and is_hammer_position
        and lower_shadow_big_enough and upper_shadow_tiny
    )
    bearish_shape = (
        small_body and is_shooting_star_position
        and upper_shadow_big_enough and lower_shadow_tiny
    )

    if not bullish_shape and not bearish_shape:
        return None

    # --- SMA: چیدمان، موقعیت close، فاصله تا SMA7 ---
    sma_stack_bull = sma7 > sma25 and sma25 > sma99
    sma_stack_bear = sma7 < sma25 and sma25 < sma99

    above_all_sma = c > sma7 and c > sma25 and c > sma99
    below_all_sma = c < sma7 and c < sma25 and c < sma99

    dist_to_sma7 = abs(c - sma7)
    near_sma7 = dist_to_sma7 <= atr_val * SMA7_MAX_DIST_MULT

    body_high = max(o, c)
    body_low = min(o, c)
    body_crosses_sma7 = sma7 >= body_low and sma7 <= body_high

    # --- Cross Count: فقط SMA7×SMA25 ---
    cross_7_25 = cross_events(sma7_series, sma25_series)
    cross_count = rolling_bool_sum(cross_7_25, idx, CROSS_LOOKBACK)
    if cross_count is None:
        return None
    cross_trending = cross_count <= MAX_CROSS_COUNT

    # --- درگیری/فشردگی هر سه SMA ---
    sma_max = max(sma7, sma25, sma99)
    sma_min = min(sma7, sma25, sma99)
    sma_entanglement_range = sma_max - sma_min
    not_entangled = sma_entanglement_range >= atr_val * SMA_ENTANGLEMENT_ATR_MULT

    # --- Choppiness Index ---
    choppiness = choppiness_index_at(highs, lows, tr_series, idx, CHOP_LEN)
    if choppiness is None:
        return None
    is_trending_chop = choppiness < CHOP_THRESHOLD

    # --- ساختار Higher-High/Higher-Low ---
    structure_uptrend, structure_downtrend = structure_flags_at(highs, lows, idx, SWING_LOOKBACK)
    if structure_uptrend is None:
        return None

    # --- اختلاف DI+/DI- ---
    di_diff = plus_di - minus_di
    direction_bull_clear = di_diff > DI_DIFF_THRESHOLD
    direction_bear_clear = (-di_diff) > DI_DIFF_THRESHOLD

    # --- ترکیب نهایی فیلتر رنج/ترند (بخشی اجباری از خود سیگنال) ---
    is_trending_bull = (
        is_trending_chop and structure_uptrend
        and direction_bull_clear and cross_trending and not_entangled
    )
    is_trending_bear = (
        is_trending_chop and structure_downtrend
        and direction_bear_clear and cross_trending and not_entangled
    )

    bullish_condition = (
        bullish_shape and sma_stack_bull and above_all_sma
        and near_sma7 and not body_crosses_sma7 and is_trending_bull
    )
    bearish_condition = (
        bearish_shape and sma_stack_bear and below_all_sma
        and near_sma7 and not body_crosses_sma7 and is_trending_bear
    )

    if bullish_condition:
        signal = "bullish"
    elif bearish_condition:
        signal = "bearish"
    else:
        return None

    htf_confirm = None
    htf_timeframe_used = None

    if USE_HTF_CONFIRM:
        htf_timeframe_used = get_htf_timeframe(timeframe)
        htf_stack = get_htf_sma_stack(symbol, htf_timeframe_used, source)

        if htf_stack is not None:
            htf_stack_bull, htf_stack_bear = htf_stack
            htf_confirm = htf_stack_bull if signal == "bullish" else htf_stack_bear

        # === تغییر درخواستی: سیگنال‌های "زرد" (ناهم‌جهت با HTF) و
        # سیگنال‌هایی که هم‌جهتی‌شون قابل تشخیص نبوده (htf_confirm=None،
        # یعنی داده‌ی HTF ناکافی) کلاً حذف میشن و اصلاً فرستاده نمیشن. ===
        if htf_confirm is not True:
            return None

    interval_ms = interval_to_ms(timeframe)
    candles_ago = max(0, int((now_ms - close_times[idx]) // interval_ms))

    return {
        "signal": signal,
        "htf_confirm": htf_confirm,
        "htf_timeframe": htf_timeframe_used,
        "candle_open_ms": open_times[idx],
        "candle_close_ms": close_times[idx],
        "close_price": c,
        "rsi_value": rsi_value,
        "adx_value": adx_val,
        "di_diff": di_diff,
        "choppiness": choppiness,
        "candles_ago": candles_ago,
        "source": source,
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

    for attempt in range(4):
        try:
            resp = requests.post(
                url,
                data=payload,
                timeout=15
            )

            if resp.status_code == 429:
                try:
                    retry_after = resp.json().get("parameters", {}).get("retry_after", 2 ** attempt)
                except Exception:
                    retry_after = 2 ** attempt

                print(f"[TELEGRAM RATE-LIMIT] {retry_after}s صبر و تلاش دوباره...")
                time.sleep(float(retry_after) + 0.5)
                continue

            if resp.status_code != 200:
                print(
                    f"[TELEGRAM ERROR] "
                    f"{resp.status_code}: {resp.text}"
                )

            return

        except Exception as e:
            print(f"[TELEGRAM EXCEPTION] {e}")
            time.sleep(min(2 ** attempt, 10))

    print("[TELEGRAM ERROR] ارسال پیام بعد از چند تلاش شکست خورد.")


def build_symbol_message(symbol, tf_results, source):
    """
    پیام واحد برای یک نماد که ممکنه شامل سیگنال چند تایم‌فریم باشه.
    چون فیلتر ترند/رنج و فیلتر HTF Confirmation الان جزو خود شرط
    سیگناله، همه‌ی سیگنال‌های این پیام از قبل "تمیز" و "هم‌جهت با
    تایم بالاتر" هستن؛ دیگه هیچ حالت ⚠️/زرد یا ❌ اینجا نمایش داده
    نمیشه (چون اصلاً به این تابع نمی‌رسه).
    """

    first_signal = tf_results[0][1]["signal"]
    is_bullish = first_signal == "bullish"
    direction_emoji = "🟢" if is_bullish else "🔴"
    direction_hashtag = "#LONG" if is_bullish else "#SHORT"

    header_line = f"{direction_emoji} {direction_hashtag} #{symbol}"

    lines_per_tf = []

    for tf, res in tf_results:
        # htf_confirm همیشه True هست (وگرنه سیگنال از evaluate_symbol
        # اصلاً برنمی‌گشت)، پس همیشه علامت ✅ نشون داده میشه.
        htf_arrow = f" ✅> {res.get('htf_timeframe')}" if res.get("htf_timeframe") else ""

        rsi_value = res["rsi_value"]
        rsi_str = "?" if rsi_value is None else f"{rsi_value:.1f}"

        adx_str = "?" if res["adx_value"] is None else f"{res['adx_value']:.1f}"

        lines_per_tf.append(
            f"⏱️ {tf}{htf_arrow} | RSI {rsi_str} | ADX {adx_str} | "
            f"💰 {res['close_price']}"
        )

    vol_1h, vol_24h, vol_7d = get_extra_volumes(symbol, source)
    volume_line = (
        f"📊 Vol: 1h {human_number(vol_1h)} | "
        f"24h {human_number(vol_24h)} | 7d {human_number(vol_7d)}"
    )

    try:
        ob = get_order_book_summary(symbol, source)
    except Exception as e:
        print(f"[WARN] orderbook {symbol}: {e}")
        ob = None

    if ob:
        imbalance_str = (
            f"{ob['imbalance_pct']:+.1f}%" if ob["imbalance_pct"] is not None else "N/A"
        )

        orderbook_line = (
            f"📖 OrderBook: Buy {human_number(ob['total_bid_notional'])} / "
            f"Sell {human_number(ob['total_ask_notional'])} "
            f"({imbalance_str})"
        )
    else:
        orderbook_line = "📖 OrderBook: N/A"

    tv_link = tradingview_link(symbol, tf_results[0][0], source)
    coingecko_link, cmc_link = market_search_links(symbol, QUOTE_ASSET)

    tf_block = "\n".join(lines_per_tf)

    latest_close_ms = max(res["candle_close_ms"] for _, res in tf_results)
    close_utc = datetime.fromtimestamp(latest_close_ms / 1000, tz=timezone.utc)
    close_tehran = close_utc + TEHRAN_OFFSET
    time_line = (
        f"🕒 {close_utc.strftime('%Y-%m-%d %H:%M')} UTC | "
        f"{close_tehran.strftime('%H:%M')} (+3:30)"
    )

    msg = (
        f"{header_line}\n\n"
        f"{tf_block}\n\n"
        f"{volume_line}\n"
        f"{orderbook_line}\n\n"
        f"🔗 {tv_link}\n"
        f"🦎 {coingecko_link}\n"
        f"💹 {cmc_link}\n\n"
        f"{time_line}"
    )

    return msg


def _evaluate_task(symbol, timeframe, source):
    try:
        result = evaluate_symbol(symbol, timeframe, source)
        return symbol, timeframe, source, result, None
    except Exception as e:
        return symbol, timeframe, source, None, e


def main():

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(
            "[WARNING] TELEGRAM_BOT_TOKEN یا TELEGRAM_CHAT_ID "
            "ست نشده — پیام‌ها فقط توی لاگ چاپ میشن و تلگرام نمی‌فرسته."
        )

    state = load_state()

    symbols, source_map = get_top_symbols_combined(QUOTE_ASSET, TOP_N)

    print(
        f"[{datetime.now(timezone.utc).isoformat()}] "
        f"Checking top {len(symbols)} symbols "
        f"(priority: Binance Spot, fallback: MEXC Futures, TOP_N={TOP_N}) "
        f"on timeframes {TIMEFRAMES}... "
        f"(HTF confirm: {'on (filter, non-aligned/unconfirmed dropped)' if USE_HTF_CONFIRM else 'off'}, "
        f"workers: {MAX_WORKERS})"
    )

    tasks = [
        (symbol, timeframe, source_map[symbol])
        for symbol in symbols
        for timeframe in TIMEFRAMES
    ]

    raw_results = {}
    error_count = 0

    scan_started_at = time.monotonic()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(_evaluate_task, symbol, timeframe, source)
            for symbol, timeframe, source in tasks
        ]

        for future in as_completed(futures):
            symbol, timeframe, source, result, error = future.result()

            if error is not None:
                error_count += 1
                print(f"[ERROR] {symbol} ({source}) {timeframe}: {error}")
                continue

            if result:
                raw_results[(symbol, timeframe)] = result

    scan_elapsed = time.monotonic() - scan_started_at

    print(
        f"[INFO] فاز موازی تموم شد: {len(tasks)} ترکیب نماد/تایم‌فریم "
        f"در {scan_elapsed:.1f} ثانیه ({error_count} خطا، "
        f"{len(raw_results)} نتیجه‌ی معتبر و تأییدشده با HTF)."
    )

    bullish_count = 0
    bearish_count = 0
    duplicate_skipped = 0
    messages_sent = 0

    for symbol in symbols:

        source = source_map[symbol]
        tf_results = []

        for timeframe in TIMEFRAMES:

            result = raw_results.get((symbol, timeframe))
            if not result:
                continue

            key = f"{symbol}_{timeframe}"

            if state.get(key) == result["candle_open_ms"]:
                duplicate_skipped += 1
                print(
                    f"[SKIP-DUP] {symbol} {timeframe}: "
                    f"سیگنال تکراریه (قبلاً روی همین کندل فرستاده شده)"
                )
                continue

            tf_results.append((timeframe, result))

            if result["signal"] == "bullish":
                bullish_count += 1
            else:
                bearish_count += 1

            state[key] = result["candle_open_ms"]

            print(
                f"[SIGNAL] {symbol} ({source}) {timeframe}: {result['signal']} "
                f"(htf_confirm={result['htf_confirm']} [{result['htf_timeframe']}], "
                f"RSI={result['rsi_value']}, ADX={result['adx_value']}, "
                f"DI-diff={result['di_diff']:.2f}, Chop={result['choppiness']:.1f})"
            )

        if tf_results:
            msg = build_symbol_message(symbol, tf_results, source)
            send_telegram(msg)
            messages_sent += 1

    save_state(state)

    total_signals = bullish_count + bearish_count
    finish_time_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    summary_msg = (
        f"<b>✅ پایان اسکن</b>\n"
        f"🕒 {finish_time_str}\n"
        f"⏱ زمان اسکن: {scan_elapsed:.1f} ثانیه\n"
        f"پیام‌های ارسال‌شده: <b>{messages_sent}</b>\n"
        f"مجموع سیگنال‌های جدید (فقط هم‌جهت با HTF): <b>{total_signals}</b> "
        f"(🟢 {bullish_count} #long / 🔴 {bearish_count} #short)\n"
        f"تکراری نادیده‌گرفته‌شده: {duplicate_skipped}"
    )

    send_telegram(summary_msg)

    print("Done.")


if __name__ == "__main__":
    main()
