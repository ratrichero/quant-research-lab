from datetime import datetime, timedelta
from app.db.session import SessionLocal
from app.db.models import Signal
from sqlalchemy import text
from app.analytics.performance_engine import calculate_performance
from app.services.llm_router import ask_groq, ask_gemini
from app.services.telegram_service import send_telegram


def generate_report(period_days, report_type):

    db = SessionLocal()

    start_date = datetime.utcnow() - timedelta(days=period_days)

    trades = db.query(Signal).filter(
        Signal.status.in_(["WIN", "LOSS"]),
        Signal.candle_time >= start_date
    ).order_by(Signal.candle_time.asc()).all()

    if not trades:
        db.close()
        return None

    metrics = calculate_performance(trades)

    summary = f"""
📊 <b>BÁO CÁO {report_type.upper()}</b>

Tổng lệnh: {metrics['total_trades']}
Winrate: {metrics['winrate_percent']}%
Sharpe: {metrics['sharpe_ratio']}
Max DD: {metrics['max_drawdown_percent']}%
Profit Factor: {metrics['profit_factor']}
Expectancy: {metrics['expectancy_percent']}%
Equity cuối kỳ: ${metrics['final_equity']}
"""

    prompt = f"""
Bạn là chuyên gia phân tích chiến lược giao dịch định lượng.

Hiệu suất {report_type}:
{summary}

Hãy phân tích chi tiết, điểm mạnh, điểm yếu và đề xuất cải thiện.
"""

    analysis = ask_groq(prompt) or ask_gemini(prompt)

    if analysis:
        summary += f"\n🧠 Phân tích AI:\n{analysis}"

    # Lưu vào DB
    db.execute(text("""
        INSERT INTO reports (report_type, period_start, period_end, content)
        VALUES (:type, :start, :end, :content)
    """), {
        "type": report_type,
        "start": start_date,
        "end": datetime.utcnow(),
        "content": summary
    })

    db.commit()
    db.close()

    return summary


def send_weekly():
    report = generate_report(7, "weekly")
    if report:
        send_telegram(report)


def send_monthly():
    report = generate_report(30, "monthly")
    if report:
        send_telegram(report)