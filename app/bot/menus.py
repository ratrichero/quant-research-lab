from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from app.services.binance_service import get_top_symbols


# ============================================================
# MAIN MENU
# ============================================================

def main_menu():
    keyboard = [
        [InlineKeyboardButton("📊 Phân tích Coin", callback_data="analyze")],
        [InlineKeyboardButton("📈 Market Bias", callback_data="overview")],
        [InlineKeyboardButton("❓ Hướng dẫn", callback_data="help")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ============================================================
# COIN MENU (Top 20 + Nhập tay)
# ============================================================

def coin_menu():

    try:
        symbols = get_top_symbols(20)
    except Exception:
        symbols = []

    keyboard = []
    row = []

    for i, sym in enumerate(symbols):
        label = sym.replace("USDT", "")
        row.append(InlineKeyboardButton(label, callback_data=f"coin_{sym}"))

        if len(row) == 4:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    keyboard.append(
        [InlineKeyboardButton("✏️ Nhập coin khác", callback_data="input_coin")]
    )

    keyboard.append(
        [InlineKeyboardButton("⬅️ Menu chính", callback_data="back_main")]
    )

    return InlineKeyboardMarkup(keyboard)


# ============================================================
# TIMEFRAME MENU
# ============================================================

def timeframe_menu(symbol):
    keyboard = [
        [
            InlineKeyboardButton("⚡ 15m", callback_data=f"tf_{symbol}_15m"),
            InlineKeyboardButton("🕐 1h", callback_data=f"tf_{symbol}_1h"),
            InlineKeyboardButton("🕓 4h", callback_data=f"tf_{symbol}_4h"),
        ],
        [InlineKeyboardButton("⬅️ Đổi Coin", callback_data="analyze")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ============================================================
# RESULT NAVIGATION
# ============================================================

def result_navigation(symbol, timeframe):
    keyboard = [
        [InlineKeyboardButton("📊 Chi tiết số liệu", callback_data=f"detail_{symbol}_{timeframe}")],
        [InlineKeyboardButton("🤖 AI Tư vấn", callback_data=f"ai_{symbol}_{timeframe}")],
        [
            InlineKeyboardButton("🔄 Đổi khung", callback_data=f"coin_{symbol}"),
            InlineKeyboardButton("🔁 Đổi coin", callback_data="analyze"),
        ],
        [InlineKeyboardButton("⬅️ Menu chính", callback_data="back_main")],
    ]
    return InlineKeyboardMarkup(keyboard)

def main_menu():
    keyboard = [
        [InlineKeyboardButton("📊 Phân tích Coin", callback_data="analyze")],
        [InlineKeyboardButton("📈 Market Overview", callback_data="overview")],
    ]
    return InlineKeyboardMarkup(keyboard)

def overview_timeframe_menu():
    keyboard = [
        [
            InlineKeyboardButton("⚡ 15m", callback_data="overview_15m"),
            InlineKeyboardButton("🕐 1h", callback_data="overview_1h"),
            InlineKeyboardButton("🕓 4h", callback_data="overview_4h"),
        ],
        [InlineKeyboardButton("⬅️ Menu chính", callback_data="back_main")],
    ]
    return InlineKeyboardMarkup(keyboard)
