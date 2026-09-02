def build_symbol_message(symbol, tf_results, coingecko_map):
    """
    پیام واحد برای یک نماد — فرمت جدید:
      - خط اول: 🔴/🟢 #SHORT|#LONG   #SYMBOL
      - هر تایم‌فریم یه خط: ⏱ TF [✅/❌/بدون‌علامت]> HTF | RSI | ADX[⚠️] | 💰 قیمت
      - حجم/اردربوک/مارکت‌کپ به انگلیسی، خلاصه و کم‌حجم
      - لینک تریدینگ‌ویو
      - آخرین خط: تاریخ/ساعت UTC و تهران (+3:30)
    """
    from datetime import timedelta

    # جهت اصلی پیام: جهت اولین سیگنال تو لیست (معمولاً همه‌ی تایم‌فریم‌ها هم‌جهت‌ان)
    primary_signal = tf_results[0][1]["signal"]
    is_bullish_header = primary_signal == "bullish"
    header_emoji = "🟢" if is_bullish_header else "🔴"
    header_tag = "#LONG" if is_bullish_header else "#SHORT"

    tf_lines = []
    for tf, res in tf_results:
        # اگه جهت این تایم‌فریم با هدر فرق داشت، صریح مشخص کن
        own_dir_tag = ""
        if res["signal"] != primary_signal:
            own_dir_tag = " (LONG)" if res["signal"] == "bullish" else " (SHORT)"

        # تگ تایید هم‌جهتی با تایم فریم بالاتر
        htf_tf = res.get("htf_timeframe")
        if htf_tf:
            if res.get("htf_confirm") is True:
                htf_part = f"✅> {htf_tf}"
            elif res.get("htf_confirm") is False:
                htf_part = f"❌> {htf_tf}"
            else:
                htf_part = f"> {htf_tf}"
        else:
            htf_part = ""

        rsi_value = res["rsi_value"]
        is_hot = (
            (res["signal"] == "bullish" and rsi_value is not None and rsi_value > RSI_BULLISH_HOT)
            or (res["signal"] == "bearish" and rsi_value is not None and rsi_value < RSI_BEARISH_HOT)
        )
        rsi_str = "?" if rsi_value is None else f"{rsi_value:.1f}"
        if is_hot:
            rsi_str = f"⚠️{rsi_str}"

        adx_str = "?" if res["adx_value"] is None else f"{res['adx_value']:.1f}"
        if res["risky"]:
            adx_str += " ⚠️"

        no_volume_part = "  🟡NoVol" if res["no_volume"] else ""

        tf_lines.append(
            f"⏱ {tf} {htf_part}{own_dir_tag}   |   RSI {rsi_str}   |   ADX {adx_str}   |   💰 {res['close_price']}{no_volume_part}"
        )

    vol_1h, vol_24h, vol_7d = get_extra_volumes(symbol)
    volume_line = (
        f"📊 Vol: 1h {human_number(vol_1h)}   |   "
        f"24h {human_number(vol_24h)}   |   7d {human_number(vol_7d)}"
    )

    try:
        ob = get_order_book_summary(symbol)
    except Exception as e:
        print(f"[WARN] orderbook {symbol}: {e}")
        ob = None

    if ob:
        imbalance_str = (
            f"{ob['imbalance_pct']:+.1f}%" if ob["imbalance_pct"] is not None else "?"
        )
        orderbook_line = (
            f"📖 OrderBook: Buy {human_number(ob['total_bid_notional'])} / "
            f"Sell {human_number(ob['total_ask_notional'])} ({imbalance_str})"
        )
    else:
        orderbook_line = "📖 OrderBook: N/A"

    base_asset = symbol[:-len(QUOTE_ASSET)] if symbol.endswith(QUOTE_ASSET) else symbol
    mcap_info = coingecko_map.get(base_asset)
    if mcap_info:
        rank_str = f"#{mcap_info['rank']}" if mcap_info["rank"] else "?"
        mcap_line = f"🏆 MCap: {human_number(mcap_info['market_cap'])} | Rank {rank_str}"
    else:
        mcap_line = "🏆 MCap: N/A"

    tv_link = tradingview_link(symbol, tf_results[0][0])

    tf_block = "\n".join(tf_lines)

    now_utc = datetime.now(timezone.utc)
    now_tehran = now_utc + timedelta(hours=3, minutes=30)
    time_line = (
        f"🕒 {now_utc.strftime('%Y-%m-%d %H:%M')} UTC | "
        f"{now_tehran.strftime('%H:%M')} (+3:30)"
    )

    msg = (
        f"{header_emoji} {header_tag}   #{symbol}\n\n"
        f"{tf_block}\n\n"
        f"{volume_line}\n"
        f"{orderbook_line}\n"
        f"{mcap_line}\n\n"
        f"🔗 {tv_link}\n\n"
        f"{time_line}"
    )

    return msg
