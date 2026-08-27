"""
Setup Candle + SMA Alert Bot (Binance -> Telegram) — Multi-Timeframe
=====================================================================
منطق دقیقاً همون نسخه‌ی ساده‌ی اسکریپت Pine هست:
  - بدنه کوچک (small_body)
  - سایه غالب (lower/upper dominant) با نسبت shadow_ratio به بدنه
  - close بالای/پایین هر سه SMA (7, 25, 99) به‌طور هم‌زمان
  - بدنه‌ی کندل نباید SMA7 رو قطع کرده باشه

این نسخه روی چند تایم‌فریم هم‌زمان (پیش‌فرض: 15m, 1h, 4h) چک می‌کنه.
طراحی شده برای اجرا با cron یا GitHub Actions: هر بار که اجرا میشه،
فقط آخرین کندلِ "بسته‌شده"ی هر نماد در هر تایم‌فریم رو چک می‌کنه و اگه
شرط برقرار بود، یه پیام تلگرام میفرسته. برای جلوگیری از تکرار پیام
روی یه کندل، وضعیت هر (نماد، تایم‌فریم) تو یه فایل JSON محلی ذخیره میشه.

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
"""

import json
import os
import time
from datetime import datetime, timezone

import requests

# ============================== تنظیمات ==============================

# توکن و chat id هرگز نباید توی کد نوشته بشن — از env var خونده میشن.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# چند تایم‌فریم به‌صورت هم‌زمان چک میشن. هرکدوم رو می‌تونی جدا از طریق
# env var هم بازنویسی کنی: TIMEFRAMES="15m,1h,4h"
DEFAULT_TIMEFRAMES = ["15m", "1h", "4h"]
TIMEFRAMES = (
    [tf.strip() for tf in os.environ.get("TIMEFRAMES", "").split(",") if tf.strip()]
    or DEFAULT_TIMEFRAMES
)

QUOTE_ASSET = os.environ.get("QUOTE_ASSET", "USDT")  # فقط جفت‌ارزهایی که با این ارز quote میشن
TOP_N = int(os.environ.get("TOP_N", "200"))  # فقط N تا نماد برتر (بر اساس حجم معاملات ۲۴ ساعته)

SHADOW_RATIO = 1.5
MAX_BODY_RATIO = 0.5

SMA_FAST_LEN = 7
SMA_MID_LEN = 25
SMA_TREND_LEN = 99

KLINES_LIMIT = max(SMA_TREND_LEN + 5, 120)  # تعداد کندل کافی برای SMA99

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alert_state.json")

# فقط API عمومی دیتای Binance تغییر کرده
BINANCE_BASE = "https://data-api.binance.vision"

REQUEST_SLEEP = 0.08  # فاصله بین درخواست‌ها برای رعایت rate limit بایننس

# =======================================================================


def get_all_symbols(quote_asset: str):
    """همه‌ی نمادهای اسپات فعال با quote asset مشخص‌شده رو برمی‌گردونه (بدون فیلتر حجم)."""
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
    فقط N تا نماد برتر (بر اساس حجم معاملات ۲۴ ساعته - quoteVolume) رو برمی‌گردونه.
    این لیست مستقل از تایم‌فریمه، پس فقط یه بار در هر اجرا محاسبه میشه.
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
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def sma(values, length):
    """SMA ساده روی یه لیست عددی (خروجی: لیست هم‌طول با None برای نقاط ناکافی)."""
    result = [None] * len(values)
    for i in range(length - 1, len(values)):
        window = values[i - length + 1: i + 1]
        result[i] = sum(window) / length
    return result


def evaluate_symbol(symbol: str, timeframe: str):
    """
    منطق سیگنال رو روی آخرین کندلِ بسته‌شده‌ی این نماد در این تایم‌فریم چک می‌کنه.
    خروجی: ("bullish" | "bearish" | None, candle_open_time_ms, close_price)
    """
    raw = get_klines(symbol, timeframe, KLINES_LIMIT)
    if not raw or len(raw) < SMA_TREND_LEN + 2:
        return None, None, None

    # هر کندل بایننس: [open_time, open, high, low, close, volume, close_time, ...]
    opens = [float(k[1]) for k in raw]
    highs = [float(k[2]) for k in raw]
    lows = [float(k[3]) for k in raw]
    closes = [float(k[4]) for k in raw]
    open_times = [int(k[0]) for k in raw]
    close_times = [int(k[6]) for k in raw]

    # اگه آخرین کندل هنوز بسته نشده (close_time در آینده‌ست)، کندل قبلیش رو ملاک قرار بده
    now_ms = int(time.time() * 1000)
    idx = len(raw) - 1
    if close_times[idx] > now_ms:
        idx -= 1

    if idx < SMA_TREND_LEN:  # داده کافی برای SMA99 در این ایندکس نیست
        return None, None, None

    sma7_series = sma(closes, SMA_FAST_LEN)
    sma25_series = sma(closes, SMA_MID_LEN)
    sma99_series = sma(closes, SMA_TREND_LEN)

    sma7 = sma7_series[idx]
    sma25 = sma25_series[idx]
    sma99 = sma99_series[idx]
    if sma7 is None or sma25 is None or sma99 is None:
        return None, None, None

    o, h, l, c = opens[idx], highs[idx], lows[idx], closes[idx]

    body = abs(c - o)
    upper_shadow = h - max(c, o)
    lower_shadow = min(c, o) - l
    candle_range = h - l

    if candle_range == 0:
        return None, None, None

    small_body = body > 0 and body <= candle_range * MAX_BODY_RATIO
    upper_dominant = upper_shadow > lower_shadow
    lower_dominant = lower_shadow > upper_shadow

    above_all_sma = c > sma7 and c > sma25 and c > sma99
    below_all_sma = c < sma7 and c < sma25 and c < sma99

    body_high = max(o, c)
    body_low = min(o, c)
    body_crosses_sma7 = sma7 >= body_low and sma7 <= body_high

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

    signal = "bullish" if bullish else ("bearish" if bearish else None)
    return signal, open_times[idx], c


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
        print("[TELEGRAM SKIPPED] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID تنظیم نشدن.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        resp = requests.post(url, data=payload, timeout=15)
        if resp.status_code != 200:
            print(f"[TELEGRAM ERROR] {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[TELEGRAM EXCEPTION] {e}")


def main():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(
            "[WARNING] TELEGRAM_BOT_TOKEN یا TELEGRAM_CHAT_ID ست نشده — "
            "پیام‌ها فقط توی لاگ چاپ میشن و تلگرام نمی‌فرسته."
        )

    state = load_state()
    symbols = get_top_symbols(QUOTE_ASSET, TOP_N)
    print(
        f"[{datetime.now(timezone.utc).isoformat()}] "
        f"Checking top {len(symbols)} symbols (by 24h volume) on timeframes {TIMEFRAMES}..."
    )

    for symbol in symbols:
        for timeframe in TIMEFRAMES:
            try:
                signal, candle_open_ms, close_price = evaluate_symbol(symbol, timeframe)
            except Exception as e:
                print(f"[ERROR] {symbol} {timeframe}: {e}")
                time.sleep(REQUEST_SLEEP)
                continue

            if signal:
                key = f"{symbol}_{timeframe}"
                last_alerted = state.get(key)

                # فقط اگه قبلاً برای همین کندل آلارم نفرستاده باشیم
                if last_alerted != candle_open_ms:
                    direction_fa = "صعودی 🟢" if signal == "bullish" else "نزولی 🔴"
                    candle_time_str = datetime.fromtimestamp(
                        candle_open_ms / 1000, tz=timezone.utc
                    ).strftime("%Y-%m-%d %H:%M UTC")
                    msg = (
                        f"<b>سیگنال {direction_fa}</b>\n"
                        f"نماد: <b>{symbol}</b>\n"
                        f"تایم‌فریم: {timeframe}\n"
                        f"قیمت close: {close_price}\n"
                        f"زمان کندل: {candle_time_str}"
                    )
                    send_telegram(msg)
                    state[key] = candle_open_ms
                    print(f"[SIGNAL] {symbol} {timeframe}: {signal}")

            time.sleep(REQUEST_SLEEP)

    save_state(state)
    print("Done.")


if __name__ == "__main__":
    main()
