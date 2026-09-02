"""
Setup Candle + SMA Alert Bot (Binance FUTURES -> Telegram) — Multi-Timeframe
=============================================================================
منطق سیگنال دقیقاً منطبق با آخرین نسخه‌ی اسکریپت Pine v6
(indicator "Setup Candle + SMA View") هست:
  - بدنه کوچک (small_body)
  - سایه غالب (lower/upper dominant) - نسبت سایه به بدنه جدا برای
    بولیش (SHADOW_RATIO_BULL) و بریش (SHADOW_RATIO_BEAR)
  - close بالای/پایین هر سه SMA (7, 25, 99) به‌طور هم‌زمان
  - چیدمان صحیح SMA ها نسبت به هم (sma7 > sma25 > sma99 برای بولیش،
    برعکسش برای بریش)
  - بدنه‌ی کندل نباید SMA7 رو قطع کرده باشه
  - فاصله‌ی close تا SMA7 نباید بیشتر از SMA7_MAX_DIST_MULT برابر
    رنج خود همون کندل (high-low) باشه
  - فیلتر روند با ADX/DMI: اگه ADX >= آستانه -> سیگنال عادی،
    اگه ADX < آستانه (بازار رنج) -> همون سیگنال ولی "ریسکی" میشه
  - شرط حجم فیلتر نیست؛ فقط تگ جدا (No-Volume-Condition)
  - تایید هم‌جهتی با تایم‌فریم بالاتر (HTF Confirmation) - فقط تگ،
    نه فیلتر

--- تغییر این نسخه ---
داده دیگه از بایننس اسپات گرفته نمیشه؛ همه‌چیز از بایننس FUTURES
(USDT-M Perpetual, fapi.binance.com) میاد. پشتیبانی MEXC و KuCoin
(هم برای لیست نمادها، هم کندل‌ها، هم اردربوک) کاملاً حذف شده و
اسکریپت فقط به یک صرافی (بایننس فیوچرز) وصل میشه. اگه درخواستی به
بایننس فیوچرز شکست بخوره، دیگه fallback ای وجود نداره و همون خطا
لاگ میشه.

نصب پیش‌نیازها:
    pip install requests

تنظیم قبل از اجرا (به‌صورت متغیر محیطی):
    export TELEGRAM_BOT_TOKEN="..."
    export TELEGRAM_CHAT_ID="..."

اجرای محلی با cron (مثال: هر ۱۵ دقیقه):
    */15 * * * * TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=yyy /usr/bin/python3 /path/to/binance_futures_setup_alert_bot.py >> /path/to/bot.log 2>&1

نکته درباره‌ی داده‌ی مارکت‌کپ: بایننس مارکت‌کپ/رنک نمی‌ده، پس این
اسکریپت یک‌بار در ابتدای هر اجرا، چند صفحه از CoinGecko (API عمومی و
رایگان) رو فقط برای نمایش تو پیام می‌گیره. اگه این بخش با خطا یا
محدودیت مواجه بشه، اسکریپت متوقف نمیشه؛ فقط خط مارکت‌کپ تو پیام
"یافت نشد" نشون داده میشه.
"""

import json
import os
import time
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
TOP_N = int(os.environ.get("TOP_N", "200"))   # ۲۰۰ قرارداد برتر بر اساس حجم معاملات فیوچرز

# فقط قراردادهای Perpetual (نه Delivery/Quarterly) در نظر گرفته میشن
FUTURES_ONLY_PERPETUAL = os.environ.get("FUTURES_ONLY_PERPETUAL", "1") == "1"

MAX_BODY_RATIO = float(os.environ.get("MAX_BODY_RATIO", "0.5"))

# نسبت سایه به بدنه - جدا برای بولیش (سایه پایین) و بریش (سایه بالا)
SHADOW_RATIO_BULL = float(os.environ.get("SHADOW_RATIO_BULL", "1.5"))
SHADOW_RATIO_BEAR = float(os.environ.get("SHADOW_RATIO_BEAR", "1.5"))

# حداکثر سایه‌ی مقابل (غیرغالب) به صورت درصدی از سایه‌ی غالب همون کندل
SHADOW_MAX_BULL_OPPOSITE_PCT = float(os.environ.get("SHADOW_MAX_BULL_OPPOSITE_PCT", "50.0"))
SHADOW_MAX_BEAR_OPPOSITE_PCT = float(os.environ.get("SHADOW_MAX_BEAR_OPPOSITE_PCT", "50.0"))

# درصد تلورانس (انعطاف) برای همه‌ی نسبت‌های سایه بالا
SHADOW_TOLERANCE_PERCENT = float(os.environ.get("SHADOW_TOLERANCE_PERCENT", "10.0"))

SMA_FAST_LEN = int(os.environ.get("SMA_FAST_LEN", "7"))
SMA_MID_LEN = int(os.environ.get("SMA_MID_LEN", "25"))
SMA_TREND_LEN = int(os.environ.get("SMA_TREND_LEN", "99"))

# فاصله‌ی close کندل ستاپ تا SMA7 - بر مبنای رنج خود همون کندل (نه ATR)
SMA7_MAX_DIST_MULT = float(os.environ.get("SMA7_MAX_DIST_MULT", "1.0"))

# فیلتر روند/رنج با ADX
ADX_LEN = int(os.environ.get("ADX_LEN", "14"))
ADX_SMOOTHING = int(os.environ.get("ADX_SMOOTHING", "14"))
ADX_THRESHOLD = float(os.environ.get("ADX_THRESHOLD", "20.0"))

RSI_LEN = int(os.environ.get("RSI_LEN", "21"))
RSI_BULLISH_HOT = 60   # اگه سیگنال لانگه و RSI بالای این عدد -> هایلایت
RSI_BEARISH_HOT = 30   # اگه سیگنال شورته و RSI زیر این عدد -> هایلایت

# --- تایید هم‌جهتی با تایم فریم بالاتر (HTF Confirmation) ---
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

# API بایننس فیوچرز (USDT-M). فقط همین صرافی استفاده میشه، بدون fallback.
BINANCE_FUTURES_BASE = "https://fapi.binance.com"

REQUEST_SLEEP = 0.08

# نگاشت تایم‌فریم بایننس به فرمت اینتروال TradingView
TV_INTERVAL_MAP = {
    "1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
    "1h": "60", "2h": "120", "4h": "240", "6h": "360", "8h": "480",
    "12h": "720", "1d": "D", "3d": "3D", "1w": "W", "1M": "M",
}

# وقت تهران (Iran Standard Time) = UTC + 3:30
TEHRAN_OFFSET = timedelta(hours=3, minutes=30)

# =======================================================================


def get_all_symbols(quote_asset: str):
    """
    همه‌ی نمادهای فیوچرز فعال (Perpetual) با quote asset مشخص‌شده رو
    از بایننس فیوچرز برمی‌گردونه.
    """
    url = f"{BINANCE_FUTURES_BASE}/fapi/v1/exchangeInfo"

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[ERROR] گرفتن لیست نمادهای فیوچرز شکست خورد: {e}")
        return []

    symbols = []
    for s in data.get("symbols", []):
        if s.get("status") != "TRADING":
            continue

        if s.get("quoteAsset") != quote_asset:
            continue

        if FUTURES_ONLY_PERPETUAL and s.get("contractType") != "PERPETUAL":
            continue

        symbols.append(s["symbol"])

    return symbols


def get_top_symbols_by_volume(quote_asset: str, top_n: int):
    """
    نمادهای فیوچرز معتبر با quote asset مشخص‌شده رو می‌گیره و بر اساس
    حجم معاملات ۲۴ ساعته (quoteVolume) مرتب می‌کنه.
    """
    valid_symbols = get_all_symbols(quote_asset)

    if not valid_symbols:
        return []

    valid_symbols_set = set(valid_symbols)

    url = f"{BINANCE_FUTURES_BASE}/fapi/v1/ticker/24hr"

    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        ticker_map = {row.get("symbol"): row for row in resp.json()}
    except Exception as e:
        print(f"[ERROR] گرفتن حجم ۲۴ ساعته فیوچرز شکست خورد: {e}")
        return valid_symbols[:top_n]

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


def get_klines(symbol: str, interval: str, limit: int):
    url = f"{BINANCE_FUTURES_BASE}/fapi/v1/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}

    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()

    return resp.json()


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


def adx_series(highs, lows, closes, di_length, adx_smoothing):
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
    if AUTO_HTF and base_timeframe in AUTO_HTF_MAP:
        return AUTO_HTF_MAP[base_timeframe]

    return MANUAL_HTF


def get_htf_sma_stack(symbol: str, htf_timeframe: str):
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
    tv_interval = TV_INTERVAL_MAP.get(timeframe, "")
    # ".P" یعنی چارت پرپچوال فیوچرز تو TradingView
    link = f"https://www.tradingview.com/chart/?symbol=BINANCE:{symbol}.P"

    if tv_interval:
        link += f"&interval={tv_interval}"

    return link


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


def get_ticker_24hr_quote_volume(symbol: str):
    url = f"{BINANCE_FUTURES_BASE}/fapi/v1/ticker/24hr"
    resp = requests.get(url, params={"symbol": symbol}, timeout=15)
    resp.raise_for_status()
    return float(resp.json().get("quoteVolume", 0))


def get_extra_volumes(symbol: str):
    vol_1h = None
    vol_24h = None
    vol_7d = None

    try:
        k1m = get_klines(symbol, "1m", 60)
        vol_1h = sum(float(k[7]) for k in k1m)
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
    if not orders:
        return None, None, None

    total_qty = sum(q for _, q in orders)
    if total_qty <= 0:
        return None, None, None

    weighted_avg_price = sum(p * q for p, q in orders) / total_qty
    prices = [p for p, _ in orders]

    return weighted_avg_price, min(prices), max(prices)


def get_order_book_summary(symbol: str, limit: int = ORDERBOOK_LIMIT, top_n: int = ORDERBOOK_WALL_TOP_N):
    url = f"{BINANCE_FUTURES_BASE}/fapi/v1/depth"
    resp = requests.get(url, params={"symbol": symbol, "limit": limit}, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    raw_bids, raw_asks = data.get("bids", []), data.get("asks", [])

    if not raw_bids and not raw_asks:
        raise RuntimeError(f"گرفتن اردربوک فیوچرز {symbol} شکست خورد (پاسخ خالی)")

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
    اسکریپت Pine v6 (شامل تلورانس درصدی و سقف سایه‌ی مقابل).
    داده‌ها از بایننس فیوچرز (USDT-M Perpetual) گرفته میشن.
    """

    raw = get_klines(symbol, timeframe, KLINES_LIMIT)

    if not raw or len(raw) < SMA_TREND_LEN + 2:
        return None

    opens = [float(k[1]) for k in raw]
    highs = [float(k[2]) for k in raw]
    lows = [float(k[3]) for k in raw]
    closes = [float(k[4]) for k in raw]
    volumes = [float(k[5]) for k in raw]

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

    sma_stack_bull = sma7 > sma25 and sma25 > sma99
    sma_stack_bear = sma7 < sma25 and sma25 < sma99

    body_high = max(o, c)
    body_low = min(o, c)

    body_crosses_sma7 = (
        sma7 >= body_low
        and sma7 <= body_high
    )

    dist_to_sma7 = abs(c - sma7)
    near_sma7 = dist_to_sma7 <= candle_range * SMA7_MAX_DIST_MULT

    # --- تلورانس درصدی (معادل tol_factor_min / tol_factor_max تو Pine) ---
    tol_factor_min = 1 - (SHADOW_TOLERANCE_PERCENT / 100)
    tol_factor_max = 1 + (SHADOW_TOLERANCE_PERCENT / 100)

    shadow_ratio_bull_eff = SHADOW_RATIO_BULL * tol_factor_min
    shadow_ratio_bear_eff = SHADOW_RATIO_BEAR * tol_factor_min

    # سقف سایه‌ی مقابل: نسبی به سایه‌ی غالب همون کندل + تلورانس
    shadow_max_bull_opposite_eff = lower_shadow * (SHADOW_MAX_BULL_OPPOSITE_PCT / 100) * tol_factor_max
    shadow_max_bear_opposite_eff = upper_shadow * (SHADOW_MAX_BEAR_OPPOSITE_PCT / 100) * tol_factor_max

    cond_lower_ratio_ok = lower_shadow >= body * shadow_ratio_bull_eff
    cond_upper_opposite_ok = upper_shadow <= shadow_max_bull_opposite_eff

    cond_upper_ratio_ok = upper_shadow >= body * shadow_ratio_bear_eff
    cond_lower_opposite_ok = lower_shadow <= shadow_max_bear_opposite_eff

    bullish_base = (
        small_body
        and lower_dominant
        and cond_lower_ratio_ok
        and cond_upper_opposite_ok
        and above_all_sma
        and sma_stack_bull
        and not body_crosses_sma7
        and near_sma7
    )

    bearish_base = (
        small_body
        and upper_dominant
        and cond_upper_ratio_ok
        and cond_lower_opposite_ok
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

    vol_now = volumes[idx]
    vol_prev = volumes[idx - 1]
    no_volume = not (vol_now < vol_prev)

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
    پیام واحد برای یک نماد که ممکنه شامل سیگنال چند تایم‌فریم باشه.

    فرمت:
      🟢 #LONG #SYMBOL   (یا 🔴 #SHORT #SYMBOL)

      ⏱️ 15m ✅> 1h | RSI 40.4 | ADX 27.3 ⚠️ | 💰 42.11 | 🟡NoVol
      ⏱️ 1h ❌> 4h | RSI ...

      📊 Vol: 1h 163K | 24h 13.3M | 7d 81M
      📖 OrderBook: Buy 187K / Sell 247K (-12.6%)
      🏆 MCap: 540M | Rank #101

      🔗 <tradingview link>

      🕒 2026-09-02 07:30 UTC | 11:00 (+3:30)
    """

    first_signal = tf_results[0][1]["signal"]
    is_bullish = first_signal == "bullish"
    direction_emoji = "🟢" if is_bullish else "🔴"
    direction_hashtag = "#LONG" if is_bullish else "#SHORT"

    header_line = f"{direction_emoji} {direction_hashtag} #{symbol}"

    lines_per_tf = []

    for tf, res in tf_results:
        htf_arrow = ""
        if res.get("htf_confirm") is True:
            htf_arrow = f" ✅> {res.get('htf_timeframe')}"
        elif res.get("htf_confirm") is False:
            htf_arrow = f" ❌> {res.get('htf_timeframe')}"

        rsi_value = res["rsi_value"]
        rsi_str = "?" if rsi_value is None else f"{rsi_value:.1f}"

        adx_str = "?" if res["adx_value"] is None else f"{res['adx_value']:.1f}"
        risky_suffix = " ⚠️" if res["risky"] else ""

        no_volume_suffix = " | 🟡NoVol" if res["no_volume"] else ""

        lines_per_tf.append(
            f"⏱️ {tf}{htf_arrow} | RSI {rsi_str} | ADX {adx_str}{risky_suffix} | "
            f"💰 {res['close_price']}{no_volume_suffix}"
        )

    vol_1h, vol_24h, vol_7d = get_extra_volumes(symbol)
    volume_line = (
        f"📊 Vol: 1h {human_number(vol_1h)} | "
        f"24h {human_number(vol_24h)} | 7d {human_number(vol_7d)}"
    )

    try:
        ob = get_order_book_summary(symbol)
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

    base_asset = symbol[:-len(QUOTE_ASSET)] if symbol.endswith(QUOTE_ASSET) else symbol
    mcap_info = coingecko_map.get(base_asset)
    if mcap_info:
        rank_str = f"#{mcap_info['rank']}" if mcap_info["rank"] else "N/A"
        mcap_line = f"🏆 MCap: {human_number(mcap_info['market_cap'])} | Rank {rank_str}"
    else:
        mcap_line = "🏆 MCap: N/A"

    tv_link = tradingview_link(symbol, tf_results[0][0])

    tf_block = "\n".join(lines_per_tf)

    now_utc = datetime.now(timezone.utc)
    now_tehran = now_utc + TEHRAN_OFFSET
    time_line = (
        f"🕒 {now_utc.strftime('%Y-%m-%d %H:%M')} UTC | "
        f"{now_tehran.strftime('%H:%M')} (+3:30)"
    )

    msg = (
        f"{header_line}\n\n"
        f"{tf_block}\n\n"
        f"{volume_line}\n"
        f"{orderbook_line}\n"
        f"{mcap_line}\n\n"
        f"🔗 {tv_link}\n\n"
        f"{time_line}"
    )

    return msg


def main():

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(
            "[WARNING] TELEGRAM_BOT_TOKEN یا TELEGRAM_CHAT_ID "
            "ست نشده — پیام‌ها فقط توی لاگ چاپ میشن و تلگرام نمی‌فرسته."
        )

    state = load_state()

    coingecko_map = load_coingecko_market_map()

    symbols = get_top_symbols_by_volume(QUOTE_ASSET, TOP_N)

    print(
        f"[{datetime.now(timezone.utc).isoformat()}] "
        f"Checking top {len(symbols)} FUTURES symbols "
        f"(by Binance Futures 24h volume, TOP_N={TOP_N}) on timeframes {TIMEFRAMES}... "
        f"(HTF confirm: {'on' if USE_HTF_CONFIRM else 'off'}, exchange: binance-futures)"
    )

    bullish_count = 0
    bearish_count = 0
    pass_count = 0
    duplicate_skipped = 0
    messages_sent = 0

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

    if delayed_signals:
        send_telegram(
            f"<b>⚠️ سیگنال‌های ریسکی / ناهم‌جهت با HTF این اسکن</b>\n"
            f"تعداد: {len(delayed_signals)} نماد"
        )

        for symbol, delayed_tf_results in delayed_signals:
            msg = build_symbol_message(symbol, delayed_tf_results, coingecko_map)
            send_telegram(msg)
            messages_sent += 1

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

    print("Done.")


if __name__ == "__main__":
    main()
