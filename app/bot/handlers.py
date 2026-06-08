from telegram import Update
from telegram.ext import CallbackContext
from app.services.advanced_analysis_service import analyze_quick
from app.bot.menus import overview_timeframe_menu

from app.bot.menus import (
    main_menu,
    coin_menu,
    timeframe_menu,
    result_navigation
)

from app.services.advanced_analysis_service import analyze_advanced, multi_tf_summary
from app.services.binance_service import get_top_symbols, get_klines_closed
from app.services.indicator_service import add_indicators_advanced
from app.services.llm_router import generate_analysis_advice
from app.bot.bot_state import VALID_SYMBOLS


# ============================================================
# START
# ============================================================

def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "🤖 Crypto Pattern Assistant\n\nChọn chức năng:",
        reply_markup=main_menu()
    )


# ============================================================
# TEXT INPUT HANDLER (Nhập coin tay)
# ============================================================

def text_handler(update: Update, context: CallbackContext):

    raw = update.message.text.strip().upper()

    if context.user_data.get("awaiting_coin_input"):

        symbol = raw if raw.endswith("USDT") else raw + "USDT"

        if symbol not in VALID_SYMBOLS:
            update.message.reply_text("❌ Coin không hợp lệ. Thử lại.")
            return

        context.user_data["awaiting_coin_input"] = False

        update.message.reply_text(
            f"📊 {symbol}\nChọn khung phân tích:",
            reply_markup=timeframe_menu(symbol)
        )


# ============================================================
# BUTTON HANDLER
# ============================================================

def button_handler(update: Update, context: CallbackContext):

    
    query = update.callback_query
    query.answer()

    data = query.data
    print("BUTTON DATA:", data)

    # ================= MENU =================

    if data == "analyze":
        query.edit_message_text("📊 Chọn coin:", reply_markup=coin_menu())

    elif data == "back_main":
        query.edit_message_text("Chọn chức năng:", reply_markup=main_menu())

    elif data == "input_coin":
        context.user_data["awaiting_coin_input"] = True
        query.edit_message_text("✏ Nhập mã coin (ví dụ: btc, eth, sol):")

    # ================= COIN SELECT =================

    elif data.startswith("coin_"):
        symbol = data.split("_")[1]
        query.edit_message_text(
            f"📊 {symbol}\nChọn khung phân tích:",
            reply_markup=timeframe_menu(symbol)
        )

    # ================= TIMEFRAME =================

    elif data.startswith("tf_"):

        _, symbol, timeframe = data.split("_")

        result = analyze_advanced(symbol, timeframe)

        if "error" in result:
            query.edit_message_text(result["error"])
            return

    

        message = format_summary(result)

        
        query.message.reply_text(
            message,
            parse_mode="HTML",
            reply_markup=result_navigation(symbol, timeframe)
        )

    # ================= DETAIL VIEW =================

    elif data.startswith("detail_"):

        _, symbol, timeframe = data.split("_")

        result = analyze_advanced(symbol, timeframe)

        if "error" in result:
            query.edit_message_text(result["error"])
            return

        message = format_detail(result)

        query.edit_message_text(
            message,
            parse_mode="HTML",
            reply_markup=result_navigation(symbol, timeframe)
        )

    # ================= AI ADVICE =================

    elif data.startswith("ai_"):

        _, symbol, timeframe = data.split("_")

        result = analyze_advanced(symbol, timeframe)

        if "error" in result:
            query.edit_message_text(result["error"])
            return

        advice = generate_analysis_advice({
            "symbol": symbol,
            "timeframe": timeframe,
            "regime": result["regime"],
            "atr_pct": result["atr_pct"],
            "ema_dist_pct": result["ema_dist_pct"],
            "funding_rate": result["funding_rate"],
            "long_score": result["long"]["score"],
            "short_score": result["short"]["score"],
            "long_htf_block": result["long"]["htf_block"],
            "short_htf_block": result["short"]["htf_block"],
            "long_funding_block": result["long"]["funding_block"],
            "short_funding_block": result["short"]["funding_block"],
        })

        query.edit_message_text(
            f"🤖 <b>AI Phân tích {symbol} ({timeframe})</b>\n\n{advice}",
            parse_mode="HTML",
            reply_markup=result_navigation(symbol, timeframe)
        )

    # ================= MARKET OVERVIEW =================

    elif data == "overview":
        query.edit_message_text(
            "📈 Chọn khung Market Overview:",
            reply_markup=overview_timeframe_menu()
        )

    elif data.startswith("overview_"):

        timeframe = data.split("_")[1]

        symbols = get_top_symbols(20)

        long_list = []
        short_list = []

        for sym in symbols:

            score_long, score_short = analyze_quick(sym, timeframe)

            if score_long is None:
                continue

            if score_long > score_short:
                long_list.append((sym, score_long))
            elif score_short > score_long:
                short_list.append((sym, score_short))

        total = len(long_list) + len(short_list)

        long_count = len(long_list)
        short_count = len(short_list)

        ratio = long_count / total if total > 0 else 0

        if ratio > 0.7:
            bias_label = "🟢 STRONGLY BULLISH"
        elif ratio > 0.55:
            bias_label = "🟢 BULLISH"
        elif ratio < 0.3:
            bias_label = "🔴 STRONGLY BEARISH"
        elif ratio < 0.45:
            bias_label = "🔴 BEARISH"
        else:
            bias_label = "⚪ NEUTRAL"

        # ✅ Sort top 5
        long_top = sorted(long_list, key=lambda x: x[1], reverse=True)[:5]
        short_top = sorted(short_list, key=lambda x: x[1], reverse=True)[:5]

        long_str = "\n".join([f"{sym} ({round(score,2)})" for sym, score in long_top]) or "None"
        short_str = "\n".join([f"{sym} ({round(score,2)})" for sym, score in short_top]) or "None"

        heatmap = ""
        for sym in symbols:
            score_long, score_short = analyze_quick(sym, timeframe)
            if score_long > score_short:
                heatmap += "🟢"
            elif score_short > score_long:
                heatmap += "🔴"
            else:
                heatmap += "⚪"

        message = (
            f"<b>📊 MARKET DASHBOARD PRO ({timeframe})</b>\n\n"

            f"🟢 LONG Bias: {long_count}/{total}\n"
            f"🔴 SHORT Bias: {short_count}/{total}\n"
            f"Overall Market Bias: <b>{bias_label}</b>\n\n"

            f"<b>🔥 Top 5 Strongest LONG</b>\n{long_str}\n\n"
            f"<b>❄ Top 5 Strongest SHORT</b>\n{short_str}\n\n"

            f"<b>📈 Heatmap (Top 20)</b>\n{heatmap}"
        )

        query.edit_message_text(
            message,
            parse_mode="HTML",
            reply_markup=overview_timeframe_menu()
        )


# ============================================================
# FORMAT FUNCTIONS
# ============================================================

def format_summary(result):

    long = result["long"]
    short = result["short"]

    bias = (
        "🟢 LONG" if long["score"] > short["score"]
        else "🔴 SHORT" if short["score"] > long["score"]
        else "⚪ NEUTRAL"
    )

    summary = multi_tf_summary(result["symbol"])
    tf_summary = " | ".join([f"{k}:{v}" for k, v in summary.items()])

    return (
        f"<b>{result['symbol']} | {result['timeframe']}</b>\n\n"
        f"Regime: {result['regime']}\n"
        f"ATR%: {result['atr_pct']}%\n"
        f"EMA Dist: {result['ema_dist_pct']}%\n\n"

        f"🟢 LONG Score: {long['score']}\n"
        f"🔴 SHORT Score: {short['score']}\n\n"

        f"📊 Multi-TF: {tf_summary}\n"
        f"🎯 Bias: <b>{bias}</b>"
    )


def format_detail(result):

    long = result["long"]
    short = result["short"]

    return (
        f"<b>{result['symbol']} | {result['timeframe']} - DETAIL</b>\n\n"

        f"Regime: {result['regime']}\n"
        f"ATR%: {result['atr_pct']}%\n"
        f"EMA Distance: {result['ema_dist_pct']}%\n\n"

        f"🟢 LONG\n"
        f"Score: {long['score']}\n"
        f"Derivative Bias: {long['derivative_bias']}\n"
        f"Entry: {long['entry']}\n"
        f"SL: {long['sl']}\n"
        f"TP: {long['tp']}\n"
        f"Confidence: {format_confidence(long['confidence'])}\n\n"

        f"🔴 SHORT\n"
        f"Score: {short['score']}\n"
        f"Derivative Bias: {short['derivative_bias']}\n"
        f"Entry: {short['entry']}\n"
        f"SL: {short['sl']}\n"
        f"TP: {short['tp']}\n"
        f"Confidence: {format_confidence(short['confidence'])}\n"
    )


def format_confidence(value: float):

    if value >= 0.75:
        return "HIGH 🔥"
    elif value >= 0.5:
        return "MEDIUM ⚖"
    else:
        return "LOW ❄"