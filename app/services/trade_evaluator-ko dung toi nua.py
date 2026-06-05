from datetime import datetime
from app.db.session import SessionLocal
from app.db.models import Signal, SignalFeature
from app.services.binance_service import get_klines


def evaluate_open_trades():

    db = SessionLocal()

    open_trades = db.query(Signal).filter(
        Signal.status == "OPEN"
    ).all()

    for trade in open_trades:

        df = get_klines(trade.symbol, limit=200)

        if df.empty:
            continue

        # Chỉ lấy các candle sau khi vào lệnh
        df = df[df["time"] > trade.candle_time]

        if df.empty:
            continue

        entry = float(trade.entry_price)
        sl = float(trade.stop_loss)
        tp = float(trade.take_profit)

        max_adverse = 0  # ✅ Maximum Adverse Excursion (MAE)

        for _, row in df.iterrows():

            high = float(row["high"])
            low = float(row["low"])

            if trade.direction == "LONG":

                # ✅ TÍNH DRAWNDOWN THỰC TẾ
                adverse_move = ((low - entry) / entry) * 100
                if adverse_move < max_adverse:
                    max_adverse = adverse_move

                # ✅ SL check
                if low <= sl:
                    trade.status = "LOSS"
                    trade.exit_price = sl
                    trade.exit_reason = "SL"
                    trade.result_percent = ((sl - entry) / entry) * 100
                    break

                # ✅ TP check
                if high >= tp:
                    trade.status = "WIN"
                    trade.exit_price = tp
                    trade.exit_reason = "TP"
                    trade.result_percent = ((tp - entry) / entry) * 100
                    break

            else:  # SHORT

                # ✅ TÍNH DRAWNDOWN THỰC TẾ
                adverse_move = ((entry - high) / entry) * 100
                if adverse_move < max_adverse:
                    max_adverse = adverse_move

                # ✅ SL check
                if high >= sl:
                    trade.status = "LOSS"
                    trade.exit_price = sl
                    trade.exit_reason = "SL"
                    trade.result_percent = ((entry - sl) / entry) * 100
                    break

                # ✅ TP check
                if low <= tp:
                    trade.status = "WIN"
                    trade.exit_price = tp
                    trade.exit_reason = "TP"
                    trade.result_percent = ((entry - tp) / entry) * 100
                    break

        # ✅ Nếu trade vừa đóng
        if trade.status in ["WIN", "LOSS"]:

            trade.exit_time = datetime.utcnow()

            # ✅ Update SignalFeature
            feature = db.query(SignalFeature).filter(
                SignalFeature.signal_id == trade.id
            ).first()

            if feature:

                feature.trade_return = trade.result_percent
                feature.label = 1 if trade.status == "WIN" else 0

                # ✅ Log Maximum Adverse Excursion
                feature.max_drawdown = max_adverse

                # ✅ Log thời gian giữ lệnh (phút)
                feature.time_to_exit = int(
                    (trade.exit_time - trade.created_at).total_seconds() / 60
                )

    db.commit()
    db.close()