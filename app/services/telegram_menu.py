import requests
import os

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_main_menu():

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    keyboard = {
        "inline_keyboard": [
            [{"text": "📊 Báo cáo tuần gần nhất", "callback_data": "weekly"}],
            [{"text": "📈 Báo cáo tháng gần nhất", "callback_data": "monthly"}],
            [{"text": "📉 Trích lục performance", "callback_data": "performance"}]
            [{"text": "📂 Xem báo cáo cũ", "callback_data": "reports_page_1"}],
            [{"text": "🤖 Hỏi AI", "callback_data": "ask_ai"}],
        ]
    }

    requests.post(url, json={
        "chat_id": CHAT_ID,
        "text": "Chọn báo cáo bạn muốn xem:",
        "reply_markup": keyboard
    })