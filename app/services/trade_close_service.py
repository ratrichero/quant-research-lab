from datetime import datetime
from app.db.models import SignalFeature
from app.services.outcome_service import save_trade_outcome

def close_trade(db, trade, current_price, reason):

    if trade.status != "OPEN":
        return

    entry = float(trade.entry_price)
    current_price = float(current_price)

    if trade.direction == "LONG":
        trade.result_percent = ((current_price - entry) / entry) * 100
    else:
        trade.result_percent = ((entry - current_price) / entry) * 100

    if reason == "TP":
        trade.status = "WIN"
    elif reason == "SL":
        trade.status = "LOSS"
    else:
        trade.status = "WIN" if trade.result_percent > 0 else "LOSS"

    trade.exit_price = float(current_price)
    trade.exit_reason = reason
    trade.exit_time = datetime.utcnow()

    feature = db.query(SignalFeature).filter(
        SignalFeature.signal_id == trade.id
    ).first()

    if not feature:
        return

    save_trade_outcome(db, trade, feature)