from telegram import BotCommand
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters
from app.bot.handlers import start, button_handler, text_handler


def run_bot(token: str):

    updater = Updater(token, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(button_handler))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, text_handler))

    commands = [
        BotCommand("start", "Mở menu chính"),
        BotCommand("analyze", "Phân tích coin"),
        BotCommand("bias", "Market bias"),
        BotCommand("help", "Hướng dẫn sử dụng"),
    ]

    updater.bot.set_my_commands(commands)

    print("🤖 Telegram Bot started (Polling)...")
    updater.start_polling()

    return updater