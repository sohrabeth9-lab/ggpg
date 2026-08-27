def get_top_symbols(quote_asset: str, top_n: int):
    """
    گرفتن Top N نماد بر اساس حجم 24h.
    بدون استفاده از /exchangeInfo تا روی GitHub Actions
    به خطای 451 وابسته نباشیم.
    """
    url = f"{BINANCE_BASE}/api/v3/ticker/24hr"

    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    tickers = resp.json()

    ranked = []

    for t in tickers:
        symbol = t.get("symbol", "")

        # فقط جفت‌های USDT
        if not symbol.endswith(quote_asset):
            continue

        # حذف بعضی نمادهای غیرقابل استفاده
        if not t.get("symbol"):
            continue

        try:
            volume = float(t.get("quoteVolume", 0))
        except (TypeError, ValueError):
            volume = 0.0

        if volume > 0:
            ranked.append((symbol, volume))

    ranked.sort(key=lambda x: x[1], reverse=True)

    return [symbol for symbol, _ in ranked[:top_n]]
