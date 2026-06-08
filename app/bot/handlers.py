from telegram import Update
from telegram.ext import CallbackContext
from app.bot.menus import main_menu, coin_menu, timeframe_menu, result_navigation
from app.services.advanced_analysis_service import analyze_advanced


def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "🤖 Crypto Pattern Assistant\n\nChọn chức năng:",
        reply_markup=main_menu()
    )


def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data

    if data == "analyze":
        query.edit_message_text("📊 Chọn coin:", reply_markup=coin_menu())

    elif data.startswith("coin_"):
        symbol = data.split("_")[1]
        query.edit_message_text(
            f"📊 {symbol}\nChọn khung phân tích:",
            reply_markup=timeframe_menu(symbol)
        )

    elif data.startswith("tf_"):
        _, symbol, timeframe = data.split("_")

        result = analyze_advanced(symbol, timeframe)

        if "error" in result:
            query.edit_message_text(result["error"])
            return

        message = format_analysis(result)

        query.edit_message_text(
            message,
            parse_mode="HTML",
            reply_markup=result_navigation(symbol)
        )

    elif data == "back_main":
        query.edit_message_text(
            "Chọn chức năng:",
            reply_markup=main_menu()
        )


def format_analysis(result):

    long_score = result["long"]["score"]
    short_score = result["short"]["score"]

    if long_score > short_score:
        bias = "🟢 LONG"
    elif short_score > long_score:
        bias = "🔴 SHORT"
    else:
        bias = "⚪ NEUTRAL"

    return (
        f"<b>{result['symbol']} | {result['timeframe']}</b>\n\n"
        f"Regime: {result['regime']}\n"
        f"ATR%: {result['atr_pct']}%\n"
        f"EMA Dist: {result['ema_dist_pct']}%\n"
        f"Funding: {result['funding_rate']}\n\n"
        f"🟢 LONG Score: {long_score}\n"
        f"🔴 SHORT Score: {short_score}\n\n"
        f"Bias: {bias}"
    )