from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu():
    keyboard = [
        [InlineKeyboardButton("📊 Phân tích Coin", callback_data="analyze")],
        [InlineKeyboardButton("📈 Market Bias", callback_data="bias")],
    ]
    return InlineKeyboardMarkup(keyboard)


def coin_menu():
    keyboard = [
        [
            InlineKeyboardButton("BTCUSDT", callback_data="coin_BTCUSDT"),
            InlineKeyboardButton("ETHUSDT", callback_data="coin_ETHUSDT"),
        ],
        [
            InlineKeyboardButton("SOLUSDT", callback_data="coin_SOLUSDT"),
            InlineKeyboardButton("BNBUSDT", callback_data="coin_BNBUSDT"),
        ],
        [InlineKeyboardButton("⬅ Menu chính", callback_data="back_main")],
    ]
    return InlineKeyboardMarkup(keyboard)


def timeframe_menu(symbol):
    keyboard = [
        [
            InlineKeyboardButton("15m", callback_data=f"tf_{symbol}_15m"),
            InlineKeyboardButton("1h", callback_data=f"tf_{symbol}_1h"),
            InlineKeyboardButton("4h", callback_data=f"tf_{symbol}_4h"),
        ],
        [InlineKeyboardButton("⬅ Đổi Coin", callback_data="analyze")],
    ]
    return InlineKeyboardMarkup(keyboard)


def result_navigation(symbol):
    keyboard = [
        [
            InlineKeyboardButton("🔄 Đổi khung", callback_data=f"coin_{symbol}"),
            InlineKeyboardButton("🔁 Đổi coin", callback_data="analyze"),
        ],
        [InlineKeyboardButton("⬅ Menu chính", callback_data="back_main")],
    ]
    return InlineKeyboardMarkup(keyboard)