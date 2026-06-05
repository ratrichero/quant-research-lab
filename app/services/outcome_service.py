from app.services.binance_service import get_klines
from app.db.models import TradeOutcomeAnalytics


def save_trade_outcome(db, trade, feature):

    existing = db.query(TradeOutcomeAnalytics).filter(
        TradeOutcomeAnalytics.signal_id == trade.id
    ).first()

    if existing:
        return

    entry = float(trade.entry_price)
    stop_loss = float(trade.stop_loss)
    take_profit = float(trade.take_profit)
    result_percent = float(trade.result_percent)

    from datetime import timedelta

    # ✅ Tính duration (phút)
    duration_minutes = (
        (trade.exit_time - trade.created_at).total_seconds() / 60
    )

    # ✅ Hybrid interval
    if duration_minutes < 180:
        interval = "1m"
    elif duration_minutes < 2880:  # < 2 ngày
        interval = "5m"
    elif duration_minutes < 10080:  # < 7 ngày
        interval = "15m"
    else:
        interval = "1h"

    df = get_klines(
        symbol=trade.symbol,
        interval=interval,
        start_time=trade.created_at,
        end_time=trade.exit_time + timedelta(minutes=1),  # buffer nhẹ
        limit=1500
    )

    mae = None
    mfe = None

    if not df.empty:

        if trade.direction == "LONG":
            mae = min((row["low"] - entry) / entry * 100 for _, row in df.iterrows())
            mfe = max((row["high"] - entry) / entry * 100 for _, row in df.iterrows())
        else:
            mae = min((entry - row["high"]) / entry * 100 for _, row in df.iterrows())
            mfe = max((entry - row["low"]) / entry * 100 for _, row in df.iterrows())

    # ✅ RR planned
    rr_planned = None
    if entry != stop_loss:
        rr_planned = abs((take_profit - entry) / (entry - stop_loss))

    # ✅ RR realized
    rr_realized = None
    if rr_planned and rr_planned != 0:
        risk_percent = abs((stop_loss - entry) / entry * 100)
        if risk_percent != 0:
            rr_realized = result_percent / risk_percent

    time_to_exit = int(
        (trade.exit_time - trade.created_at).total_seconds() / 60
    )

    analytics = TradeOutcomeAnalytics(
        signal_id=trade.id,
        symbol=trade.symbol,
        timeframe=trade.timeframe,
        direction=trade.direction,
        regime=trade.regime,

        entry_price=entry,
        exit_price=float(trade.exit_price),
        stop_loss=stop_loss,
        take_profit=take_profit,

        rr_planned=rr_planned,
        rr_realized=rr_realized,

        trade_return=result_percent,
        label=1 if trade.status == "WIN" else 0,

        max_drawdown=mae,
        max_favorable=mfe,
        time_to_exit=time_to_exit,

        volatility_at_entry=float(feature.atr_ratio) if feature.atr_ratio else None,
        volume_ratio_at_entry=float(feature.volume_ratio) if feature.volume_ratio else None,
        total_score=float(feature.total_score),
        trend_score=float(feature.trend_score),
        mtf_score=float(feature.mtf_score),
        strict_penalty=float(feature.strict_penalty),

        exit_reason=trade.exit_reason
    )

    db.add(analytics)