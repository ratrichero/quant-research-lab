from datetime import datetime
from app.db.models import SignalFeature
from app.services.outcome_service import save_trade_outcome

def close_trade(db, trade, current_price, reason):

    if trade.status != "OPEN":
        return

    entry = float(trade.entry_price)

    # ✅ Xác định exit_price theo lý thuyết
    if reason == "SL":
        exit_price = float(trade.stop_loss)
        trade.status = "LOSS"
    elif reason == "TP":
        exit_price = float(trade.take_profit)
        trade.status = "WIN"
    else:
        exit_price = float(current_price)
        trade.status = "WIN" if (
            (exit_price - entry > 0 and trade.direction == "LONG") or
            (entry - exit_price > 0 and trade.direction == "SHORT")
        ) else "LOSS"

    trade.exit_price = exit_price

    # ✅ Tính return dựa trên exit_price đã chuẩn hóa
    if trade.direction == "LONG":
        trade.result_percent = ((exit_price - entry) / entry) * 100
    else:
        trade.result_percent = ((entry - exit_price) / entry) * 100

    trade.exit_reason = reason
    trade.exit_time = datetime.utcnow()

    feature = db.query(SignalFeature).filter(
        SignalFeature.signal_id == trade.id
    ).first()

    if not feature:
        return

    save_trade_outcome(db, trade, feature)