from fastapi import APIRouter, Body
from app.db.session import SessionLocal
from app.db.models import Signal
from app.analytics.performance_engine import calculate_performance
from app.services.llm_router import ask_groq, ask_gemini

router = APIRouter()

@router.post("/assistant")
def assistant(question: str = Body(...)):

    db = SessionLocal()

    trades = db.query(Signal).filter(
        Signal.status.in_(["WIN", "LOSS"])
    ).order_by(Signal.candle_time.asc()).all()

    db.close()

    metrics = calculate_performance(trades)

    context = f"""
Dữ liệu hệ thống giao dịch hiện tại:

Tổng số lệnh: {metrics.get('total_trades')}
Winrate: {metrics.get('winrate_percent')}%
Sharpe: {metrics.get('sharpe_ratio')}
Max Drawdown: {metrics.get('max_drawdown_percent')}%
Profit Factor: {metrics.get('profit_factor')}
Expectancy: {metrics.get('expectancy_percent')}%
"""

    prompt = f"""
Bạn là trợ lý phân tích chiến lược giao dịch định lượng.

Dữ liệu hệ thống:
{context}

Câu hỏi của người dùng:
{question}

Hãy phân tích chi tiết, dễ hiểu, mang tính chuyên môn nhưng thân thiện.
"""

    result = ask_gemini(prompt)
    if result:
        return {"answer": result}
    
    result = ask_groq(prompt)
    if result:
        return {"answer": result}

    

    return {"answer": "Hiện tại hệ thống AI không khả dụng."}