"""
Setup Candle + SMA Alert Bot (Binance -> Telegram) — Multi-Timeframe
=====================================================================
منطق اصلی سیگنال دقیقاً همون نسخه‌ی ساده‌ی اسکریپت Pine هست:
  - بدنه کوچک (small_body)
  - سایه غالب (lower/upper dominant) با نسبت shadow_ratio به بدنه
  - close بالای/پایین هر سه SMA (7, 25, 99) به‌طور هم‌زمان
  - بدنه‌ی کندل نباید SMA7 رو قطع کرده باشه

این نسخه روی چند تایم‌فریم هم‌زمان (پیش‌فرض: 15m, 1h, 4h) چک می‌کنه.
طراحی شده برای اجرا با cron یا GitHub Actions: هر بار که اجرا میشه،
فقط آخرین کندلِ "بسته‌شده"ی هر نماد در هر تایم‌فریم رو چک می‌کنه و اگه
شرط برقرار بود، یه پیام تلگرام میفرسته.

--- تغییرات نسخه‌ی قبلی (بدون تغییر منطق سیگنال‌دهی) ---
  - محاسبه‌ی RSI (Wilder, پیش‌فرض 14 کندل) و نمایشش کنار هر پیام
  - نمایش تعداد کندل گذشته از بسته‌شدن کندل سیگنال تا لحظه‌ی ارسال پیام
  - افزودن لینک مستقیم چارت TradingView برای نماد/تایم‌فریم مربوطه

--- تغییرات این نسخه ---
  - حجم معاملات (quote volume) در ۱ ساعت، ۲۴ ساعت و ۷ روز گذشته
  - خلاصه‌ی اردربوک: مجموع حجم تجمیعی خرید/فروش + بزرگ‌ترین سفارش‌ها
    (دیوارهای احتمالی نهنگ‌ها) به‌صورت تجمیعی + درصد عدم‌تعادل خرید/فروش
  - مارکت‌کپ و رنک توکن (از CoinGecko، چون بایننس این داده رو نمی‌ده)
  - جلوگیری از ارسال سیگنال تکراری: تا وقتی کندلِ سیگنال‌دهنده عوض
    نشده (یعنی سیگنال جدیدی روی کندل بسته‌شده‌ی بعدی نیومده)، دوباره
    پیام فرستاده نمی‌شه. این وضعیت در alert_state.json نگه‌داری میشه.

نصب پیش‌نیازها:
    pip install requests

تنظیم قبل از اجرا (به‌صورت متغیر محیطی — دیگه هیچ‌چیز hardcode نیست):
    export TELEGRAM_BOT_TOKEN="..."
    export TELEGRAM_CHAT_ID="..."

اجرای محلی با cron (مثال: هر 15 دقیقه):
    */15 * * * * TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=yyy /usr/bin/python3 /path/to/binance_setup_alert_bot.py >> /path/to/bot.log 2>&1

برای اجرا روی GitHub Actions به README.md و
.github/workflows/alert.yml نگاه کن — توکن‌ها به‌صورت GitHub Secrets
ست میشن، نه توی کد.

نکته درباره‌ی داده‌ی مارکت‌کپ: بایننس مارکت‌کپ/رنک نمی‌ده، پس این
اسکریپت یک‌بار در ابتدای هر اجرا، چند صفحه از CoinGecko (API عمومی و
رایگان) رو می‌گیره و توی حافظه نگه می‌داره. API رایگان CoinGecko
محدودیت نرخ داره (~۵ تا ۳۰ درخواست در دقیقه بسته به شرایط)، برای
همین بین هر صفحه یک وقفه‌ی کوتاه گذاشته شده. اگه این بخش با خطا یا
محدودیت مواجه بشه، اسکریپت متوقف نمیشه؛ فقط اون قسمت از پیام
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
TOP_N = int(os.environ.get("TOP_N", "200"))

SHADOW_RATIO = 1.5
MAX_BODY_RATIO = 0.5

SMA_FAST_LEN = 7
SMA_MID_LEN = 25
SMA_TREND_LEN = 99

RSI_LEN = int(os.environ.get("RSI_LEN", "14"))
RSI_BULLISH_HOT = 60   # اگه سیگنال لانگه و RSI بالای این عدد -> هایلایت
RSI_BEARISH_HOT = 30   # اگه سیگنال شورته و RSI زیر این عدد -> هایلایت

KLINES_LIMIT = max(SMA_TREND_LEN + 5, 120)

# اردربوک
ORDERBOOK_LIMIT = int(os.environ.get("ORDERBOOK_LIMIT", "100"))       # عمق اردربوک
ORDERBOOK_WALL_TOP_N = int(os.environ.get("ORDERBOOK_WALL_TOP_N", "5"))  # چند تا سفارش بزرگ‌تر

# CoinGecko (مارکت‌کپ/رنک)
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

REQUEST_SLEEP = 0.08

# نگاشت تایم‌فریم بایننس به فرمت اینتروال TradingView
TV_INTERVAL_MAP = {
    "1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
    "1h": "60", "2h": "120", "4h": "240", "6h": "360", "8h": "480",
    "12h": "720", "1d": "D", "3d": "3D", "1w": "W", "1M": "M",
}

# =======================================================================


def get_all_symbols(quote_asset: str):
    """همه‌ی نمادهای اسپات فعال با quote asset مشخص‌شده رو برمی‌گردونه."""
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


def get_top_symbols(quote_asset: str, top_n: int):
    """
    فقط N تا نماد برتر بر اساس حجم معاملات ۲۴ ساعته.
    """
    valid_symbols = set(get_all_symbols(quote_asset))

    url = f"{BINANCE_BASE}/api/v3/ticker/24hr"
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    tickers = resp.json()

    ranked = []

    for t in tickers:
        symbol = t.get("symbol", "")

        if symbol in valid_symbols:
            try:
                volume = float(t.get("quoteVolume", 0))
            except (TypeError, ValueError):
                volume = 0.0

            ranked.append((symbol, volume))

    ranked.sort(key=lambda x: x[1], reverse=True)

    return [symbol for symbol, _ in ranked[:top_n]]


def get_klines(symbol: str, interval: str, limit: int):
    """کندل‌های خام رو از بایننس می‌گیره."""
    url = f"{BINANCE_BASE}/api/v3/klines"

    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }

    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()

    return resp.json()


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
        url = f"{BINANCE_BASE}/api/v3/ticker/24hr"
        resp = requests.get(url, params={"symbol": symbol}, timeout=15)
        resp.raise_for_status()
        vol_24h = float(resp.json().get("quoteVolume", 0))
    except Exception as e:
        print(f"[WARN] volume 24h {symbol}: {e}")

    try:
        k1d = get_klines(symbol, "1d", 7)
        vol_7d = sum(float(k[7]) for k in k1d)
    except Exception as e:
        print(f"[WARN] volume 7d {symbol}: {e}")

    return vol_1h, vol_24h, vol_7d


def get_order_book_summary(symbol: str, limit: int = ORDERBOOK_LIMIT, top_n: int = ORDERBOOK_WALL_TOP_N):
    """
    خلاصه‌ی اردربوک فعلی:
      - مجموع حجم تجمیعی سمت خرید (bids) و فروش (asks) در عمق مشخص‌شده
      - مجموع ارزش (notional) بزرگ‌ترین N سفارش هر سمت (دیوارهای احتمالی)
      - درصد عدم‌تعادل خرید/فروش (imbalance)
    فقط زمانی صدا زده میشه که سیگنالی برای ارسال پیدا شده.
    """
    url = f"{BINANCE_BASE}/api/v3/depth"
    resp = requests.get(url, params={"symbol": symbol, "limit": limit}, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    bids = [(float(p), float(q)) for p, q in data.get("bids", [])]
    asks = [(float(p), float(q)) for p, q in data.get("asks", [])]

    total_bid_qty = sum(q for _, q in bids)
    total_ask_qty = sum(q for _, q in asks)

    total_bid_notional = sum(p * q for p, q in bids)
    total_ask_notional = sum(p * q for p, q in asks)

    top_bids = sorted(bids, key=lambda x: x[1], reverse=True)[:top_n]
    top_asks = sorted(asks, key=lambda x: x[1], reverse=True)[:top_n]

    top_bids_notional = sum(p * q for p, q in top_bids)
    top_asks_notional = sum(p * q for p, q in top_asks)

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
    }


def load_coingecko_market_map(pages: int = COINGECKO_PAGES):
    """
    نگاشت symbol (مثلاً "BTC") -> {market_cap, rank, name} با گرفتن
    چند صفحه از coins/markets (مرتب‌شده بر اساس مارکت‌کپ نزولی).
    فقط یک‌بار در ابتدای هر اجرای اسکریپت ساخته میشه، نه به‌ازای هر نماد.

    توجه: چون چند کوین ممکنه symbol یکسان داشته باشن (مثلاً توکن‌های
    fork‌شده یا اسکم)، در صورت تکرار symbol، اونی که رنک بهتر (عدد
    کوچیک‌تر) داره نگه داشته میشه.
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
    منطق سیگنال روی آخرین کندل بسته‌شده.
    خروجی:
    (signal, candle_open_time_ms, close_price, rsi_value, candles_ago)
    """

    raw = get_klines(symbol, timeframe, KLINES_LIMIT)

    if not raw or len(raw) < SMA_TREND_LEN + 2:
        return None, None, None, None, None

    # Binance kline:
    # [open_time, open, high, low, close, volume, close_time, ...]

    opens = [float(k[1]) for k in raw]
    highs = [float(k[2]) for k in raw]
    lows = [float(k[3]) for k in raw]
    closes = [float(k[4]) for k in raw]

    open_times = [int(k[0]) for k in raw]
    close_times = [int(k[6]) for k in raw]

    # اگر آخرین کندل هنوز بسته نشده، قبلی را بررسی کن
    now_ms = int(time.time() * 1000)

    idx = len(raw) - 1

    if close_times[idx] > now_ms:
        idx -= 1

    if idx < SMA_TREND_LEN:
        return None, None, None, None, None

    sma7_series = sma(closes, SMA_FAST_LEN)
    sma25_series = sma(closes, SMA_MID_LEN)
    sma99_series = sma(closes, SMA_TREND_LEN)
    rsi_series = rsi(closes, RSI_LEN)

    sma7 = sma7_series[idx]
    sma25 = sma25_series[idx]
    sma99 = sma99_series[idx]
    rsi_value = rsi_series[idx]

    if sma7 is None or sma25 is None or sma99 is None:
        return None, None, None, None, None

    o = opens[idx]
    h = highs[idx]
    l = lows[idx]
    c = closes[idx]

    body = abs(c - o)

    upper_shadow = h - max(c, o)
    lower_shadow = min(c, o) - l

    candle_range = h - l

    if candle_range == 0:
        return None, None, None, None, None

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

    body_high = max(o, c)
    body_low = min(o, c)

    body_crosses_sma7 = (
        sma7 >= body_low
        and sma7 <= body_high
    )

    bullish = (
        small_body
        and lower_dominant
        and lower_shadow >= body * SHADOW_RATIO
        and above_all_sma
        and not body_crosses_sma7
    )

    bearish = (
        small_body
        and upper_dominant
        and upper_shadow >= body * SHADOW_RATIO
        and below_all_sma
        and not body_crosses_sma7
    )

    signal = (
        "bullish"
        if bullish
        else ("bearish" if bearish else None)
    )

    if signal is None:
        return None, None, None, None, None

    interval_ms = interval_to_ms(timeframe)
    candles_ago = max(0, int((now_ms - close_times[idx]) // interval_ms))

    return signal, open_times[idx], c, rsi_value, candles_ago


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


def build_signal_message(symbol, timeframe, signal, candle_open_ms, close_price,
                          rsi_value, candles_ago, coingecko_map):
    """پیام کامل سیگنال شامل RSI، حجم‌ها، اردربوک و مارکت‌کپ/رنک رو می‌سازه."""

    direction_fa = "صعودی 🟢" if signal == "bullish" else "نزولی 🔴"

    candle_time_str = datetime.fromtimestamp(
        candle_open_ms / 1000,
        tz=timezone.utc
    ).strftime("%Y-%m-%d %H:%M UTC")

    # --- خط RSI با هایلایت شرطی ---
    is_hot = (
        (signal == "bullish" and rsi_value is not None and rsi_value > RSI_BULLISH_HOT)
        or (signal == "bearish" and rsi_value is not None and rsi_value < RSI_BEARISH_HOT)
    )

    if rsi_value is None:
        rsi_line = "RSI: نامشخص"
    elif is_hot:
        rsi_line = f"⚠️ <b>RSI: {rsi_value:.1f}</b> ⚠️"
    else:
        rsi_line = f"RSI: {rsi_value:.1f}"

    # --- خط فاصله از سیگنال ---
    candles_ago_str = "همین الان بسته شده" if candles_ago == 0 else f"{candles_ago} کندل پیش"

    # --- حجم‌ها ---
    vol_1h, vol_24h, vol_7d = get_extra_volumes(symbol)
    volume_lines = (
        f"حجم ۱ ساعت: {human_number(vol_1h)}\n"
        f"حجم ۲۴ ساعت: {human_number(vol_24h)}\n"
        f"حجم ۷ روز: {human_number(vol_7d)}"
    )

    # --- اردربوک ---
    try:
        ob = get_order_book_summary(symbol)
    except Exception as e:
        print(f"[WARN] orderbook {symbol}: {e}")
        ob = None

    if ob:
        imbalance_str = (
            f"{ob['imbalance_pct']:+.1f}%"
            if ob["imbalance_pct"] is not None
            else "نامشخص"
        )
        orderbook_lines = (
            f"اردربوک (تجمیعی، عمق {ORDERBOOK_LIMIT} سطح):\n"
            f"  خرید: {human_number(ob['total_bid_notional'])} | "
            f"فروش: {human_number(ob['total_ask_notional'])}\n"
            f"  بزرگ‌ترین سفارش‌ها (Top {ORDERBOOK_WALL_TOP_N}) خرید: "
            f"{human_number(ob['top_bids_notional'])} | فروش: "
            f"{human_number(ob['top_asks_notional'])}\n"
            f"  عدم‌تعادل خرید/فروش: {imbalance_str}"
        )
    else:
        orderbook_lines = "اردربوک: نامشخص"

    # --- مارکت‌کپ و رنک ---
    base_asset = symbol[:-len(QUOTE_ASSET)] if symbol.endswith(QUOTE_ASSET) else symbol
    mcap_info = coingecko_map.get(base_asset)

    if mcap_info:
        rank_str = f"#{mcap_info['rank']}" if mcap_info["rank"] else "نامشخص"
        mcap_line = f"مارکت‌کپ: {human_number(mcap_info['market_cap'])} | رنک: {rank_str}"
    else:
        mcap_line = "مارکت‌کپ/رنک: یافت نشد"

    tv_link = tradingview_link(symbol, timeframe)

    msg = (
        f"<b>سیگنال {direction_fa}</b>\n"
        f"نماد: <b>{symbol}</b>\n"
        f"تایم‌فریم: {timeframe}\n"
        f"قیمت close: {close_price}\n"
        f"زمان کندل: {candle_time_str}\n"
        f"{rsi_line}\n"
        f"فاصله از سیگنال: {candles_ago_str}\n"
        f"{volume_lines}\n"
        f"{orderbook_lines}\n"
        f"{mcap_line}\n"
        f"چارت: {tv_link}"
    )

    return msg


def main():

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(
            "[WARNING] TELEGRAM_BOT_TOKEN یا TELEGRAM_CHAT_ID "
            "ست نشده — پیام‌ها فقط توی لاگ چاپ میشن و تلگرام نمی‌فرسته."
        )

    state = load_state()

    symbols = get_top_symbols(
        QUOTE_ASSET,
        TOP_N
    )

    # نگاشت مارکت‌کپ/رنک فقط یک‌بار در ابتدای اجرا ساخته میشه
    coingecko_map = load_coingecko_market_map()

    print(
        f"[{datetime.now(timezone.utc).isoformat()}] "
        f"Checking top {len(symbols)} symbols "
        f"(by 24h volume) on timeframes {TIMEFRAMES}..."
    )

    bullish_count = 0
    bearish_count = 0
    duplicate_skipped = 0

    for symbol in symbols:

        for timeframe in TIMEFRAMES:

            try:
                signal, candle_open_ms, close_price, rsi_value, candles_ago = evaluate_symbol(
                    symbol,
                    timeframe
                )

            except Exception as e:
                print(
                    f"[ERROR] {symbol} {timeframe}: {e}"
                )

                time.sleep(REQUEST_SLEEP)
                continue

            if signal:

                key = f"{symbol}_{timeframe}"

                # --- جلوگیری از سیگنال تکراری ---
                # اگر همین کندل (با همین candle_open_ms) قبلاً برای این
                # نماد/تایم‌فریم سیگنال داده و ارسال شده، دوباره نفرست.
                # فقط وقتی کندل سیگنال‌دهنده عوض بشه (یعنی سیگنال جدیدی
                # روی یک کندل بسته‌شده‌ی دیگه بیاد) پیام دوباره میره.
                if state.get(key) == candle_open_ms:
                    duplicate_skipped += 1
                    print(
                        f"[SKIP-DUP] {symbol} {timeframe}: "
                        f"سیگنال تکراریه (قبلاً روی همین کندل فرستاده شده)"
                    )
                    time.sleep(REQUEST_SLEEP)
                    continue

                msg = build_signal_message(
                    symbol, timeframe, signal, candle_open_ms, close_price,
                    rsi_value, candles_ago, coingecko_map
                )

                send_telegram(msg)

                if signal == "bullish":
                    bullish_count += 1
                else:
                    bearish_count += 1

                state[key] = candle_open_ms

                print(
                    f"[SIGNAL] {symbol} {timeframe}: {signal} "
                    f"(RSI={rsi_value})"
                )

            time.sleep(REQUEST_SLEEP)

    save_state(state)

    # ---- پیام پایان اسکن ----
    total_signals = bullish_count + bearish_count
    finish_time_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    summary_msg = (
        f"<b>✅ پایان اسکن</b>\n"
        f"تاریخ و ساعت: {finish_time_str}\n"
        f"تعداد کل سیگنال‌های جدید: <b>{total_signals}</b>\n"
        f"لانگ 🟢: {bullish_count}\n"
        f"شورت 🔴: {bearish_count}\n"
        f"تکراری (نادیده گرفته شد): {duplicate_skipped}"
    )

    send_telegram(summary_msg)
    # --------------------------

    print("Done.")


if __name__ == "__main__":
    main()
