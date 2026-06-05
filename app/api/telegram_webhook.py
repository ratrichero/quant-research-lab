from fastapi import APIRouter, Request
from app.db.session import SessionLocal
from sqlalchemy import text
from app.analytics.performance_engine import calculate_performance
from app.db.models import Signal
from app.services.llm_router import ask_groq, ask_gemini
import requests
import os

router = APIRouter()

TOKEN = os.getenv("TELEGRAM_TOKEN")

# Lưu trạng thái AI mode cho từng chat
user_ai_mode = {}


@router.post("/telegram-webhook")
async def telegram_webhook(request: Request):

    try:
        data = await request.json()
    except Exception:
        return {"status": "ok"}

    print("Incoming Telegram data:", data)

    # =============================
    # CALLBACK QUERY (BUTTON CLICK)
    # =============================
    if "callback_query" in data:

        callback = data["callback_query"]
        action = callback["data"]
        chat_id = callback["message"]["chat"]["id"]
        callback_id = callback["id"]

        answer_callback(callback_id)

        if action == "menu":
            send_main_menu(chat_id)
            return {"status": "ok"}

        if action == "ask_ai":
            user_ai_mode[chat_id] = True
            send_message_with_keyboard(
                chat_id,
                "🤖 Bạn đang ở chế độ hỏi AI.\nHãy gửi câu hỏi của bạn.",
                [[{"text": "⬅ Quay lại", "callback_data": "menu"}]]
            )
            return {"status": "ok"}

        if action in ["weekly", "monthly"]:

            db = SessionLocal()
            result = db.execute(text("""
                SELECT content
                FROM reports
                WHERE report_type = :type
                ORDER BY created_at DESC
                LIMIT 1
            """), {"type": action}).fetchone()
            db.close()

            if result:
                send_message(chat_id, result[0])
            else:
                send_message(chat_id, "Chưa có báo cáo.")

            return {"status": "ok"}

        if action == "performance":

            db = SessionLocal()
            trades = db.query(Signal).filter(
                Signal.status.in_(["WIN", "LOSS"])
            ).all()
            db.close()

            if not trades:
                send_message(chat_id, "Chưa có dữ liệu performance.")
            else:
                metrics = calculate_performance(trades)

                perf_text = f"""
📉 TRÍCH LỤC PERFORMANCE

Tổng lệnh: {metrics['total_trades']}
Winrate: {metrics['winrate_percent']}%
Sharpe: {metrics['sharpe_ratio']}
Max DD: {metrics['max_drawdown_percent']}%
Profit Factor: {metrics['profit_factor']}
Expectancy: {metrics['expectancy_percent']}%
Equity hiện tại: ${metrics['final_equity']}
"""
                send_message(chat_id, perf_text)

            return {"status": "ok"}

    # =============================
    # NORMAL MESSAGE
    # =============================
    if "message" in data:

        chat_id = data["message"]["chat"]["id"]
        text_message = data["message"].get("text", "")

        # gửi menu nếu user gõ /start hoặc /menu
        if text_message in ["/start", "/menu"]:
            send_main_menu(chat_id)
            return {"status": "ok"}

        # nếu đang ở AI mode
        if user_ai_mode.get(chat_id):

            prompt = f"""
Bạn là trợ lý phân tích chiến lược giao dịch định lượng.
Hãy trả lời câu hỏi sau một cách rõ ràng:

{text_message}
"""

            answer = ask_groq(prompt) or ask_gemini(prompt)
            send_message(chat_id, answer or "AI hiện không khả dụng.")
            return {"status": "ok"}

    return {"status": "ok"}


# =============================
# HELPER FUNCTIONS
# =============================

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": chat_id,
        "text": text
    })


def send_message_with_keyboard(chat_id, text, keyboard):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": chat_id,
        "text": text,
        "reply_markup": {
            "inline_keyboard": keyboard
        }
    })


def send_main_menu(chat_id):
    keyboard = [
        [{"text": "📊 Báo cáo tuần", "callback_data": "weekly"}],
        [{"text": "📈 Báo cáo tháng", "callback_data": "monthly"}],
        [{"text": "📉 Trích lục performance", "callback_data": "performance"}],
        [{"text": "🤖 Hỏi AI", "callback_data": "ask_ai"}]
    ]
    send_message_with_keyboard(chat_id, "Chọn chức năng:", keyboard)

def answer_callback(callback_id):
    url = f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery"
    requests.post(url, json={
        "callback_query_id": callback_id
    })