from telegram.ext import Updater, CommandHandler, CallbackQueryHandler
from app.bot.handlers import start, button_handler


def run_bot(token: str):
    updater = Updater(token, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Telegram Bot started (Polling)...")
    updater.start_polling()
    return updater