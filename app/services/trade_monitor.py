from app.db.session import SessionLocal
from app.db.models import Signal
from app.services.trade_close_service import close_trade
from app.services.binance_service import get_all_prices


def monitor_open_trades():

    db = SessionLocal()

    open_trades = db.query(Signal).filter(
        Signal.status == "OPEN"
    ).all()

    if not open_trades:
        db.close()
        return

    price_map = get_all_prices()
    if not price_map:
        db.close()
        return

    for trade in open_trades:

        current_price = price_map.get(trade.symbol)
        if current_price is None:
            continue

        sl = float(trade.stop_loss)
        tp = float(trade.take_profit)

        # ✅ LONG
        if trade.direction == "LONG":

            if current_price <= sl:
                close_trade(db, trade, sl, "SL")
                print(f"[CLOSED] {trade.symbol} SL")

            elif current_price >= tp:
                close_trade(db, trade, tp, "TP")
                print(f"[CLOSED] {trade.symbol} TP")

        # ✅ SHORT
        else:

            if current_price >= sl:
                close_trade(db, trade, sl, "SL")
                print(f"[CLOSED] {trade.symbol} SL")

            elif current_price <= tp:
                close_trade(db, trade, tp, "TP")
                print(f"[CLOSED] {trade.symbol} TP")

    db.commit()
    db.close()