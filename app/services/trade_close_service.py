from datetime import datetime
from app.db.models import SignalFeature
from app.services.outcome_service import save_trade_outcome
from app.services.btc_context_cache import (get_or_build_hourly_snapshot,build_event_context,)
from app.services.binance_service import get_all_prices


def close_trade(db, trade, current_price, reason):

    if trade.status != "OPEN":
        return

    entry = float(trade.entry_price)
    current_price = float(current_price)

    # ============================================================
    # 1️⃣ GAP RECOVERY CHECK
    # ============================================================

    if reason in ["SL", "TP"]:

        theoretical_price = (
            float(trade.stop_loss) if reason == "SL"
            else float(trade.take_profit)
        )

        gap_pct = abs(
            (current_price - theoretical_price) / theoretical_price * 100
        )

        # ✅ Nếu vượt quá 1% so với SL/TP → coi là abnormal
        if gap_pct > 2.0:

            exit_price = current_price
            trade.exit_reason = "GAP"

        else:
            exit_price = theoretical_price
            trade.exit_reason = reason

    else:
        # Manual close
        exit_price = current_price
        trade.exit_reason = reason

    trade.exit_price = float(exit_price)

    # ============================================================
    # 2️⃣ TÍNH RESULT PERCENT (DỰA TRÊN exit_price)
    # ============================================================

    if trade.direction == "LONG":
        trade.result_percent = ((exit_price - entry) / entry) * 100
    else:
        trade.result_percent = ((entry - exit_price) / entry) * 100

    trade.status = "WIN" if trade.result_percent > 0 else "LOSS"

    trade.exit_time = datetime.utcnow()

   
    # ============================================================
    # 2️⃣ Thêm Market Context 
    # ============================================================

    price_map = get_all_prices()
    btc_price_now = price_map.get("BTCUSDT")

    btc_snapshot = get_or_build_hourly_snapshot()
    exit_context = build_event_context(btc_snapshot, btc_price_now)

    if trade.market_context:
        trade.market_context["exit"] = exit_context
    else:
        trade.market_context = {"exit": exit_context}

    feature = db.query(SignalFeature).filter(
        SignalFeature.signal_id == trade.id
    ).first()

    if not feature:
        return

    save_trade_outcome(db, trade, feature)