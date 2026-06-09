from datetime import datetime, timedelta
from sqlalchemy.dialects.postgresql import insert
from app.db.session import SessionLocal
from app.db.models import MarketData
from app.services.binance_service import get_klines


SYMBOLS = ["BTCUSDT", "ETHUSDT"]
TIMEFRAME = "5m"
BINANCE_LIMIT = 1500  # max mỗi request


def round_to_closed_5m():
    now = datetime.utcnow()
    rounded_minute = (now.minute // 5) * 5
    return now.replace(minute=rounded_minute, second=0, microsecond=0)


def backfill_5m_days(days=10):

    end_time = round_to_closed_5m()
    start_time = end_time - timedelta(days=days)

    print(f"Backfilling from {start_time} to {end_time}")

    with SessionLocal() as db:

        for symbol in SYMBOLS:

            current_start = start_time

            while current_start < end_time:

                df = get_klines(
                    symbol=symbol,
                    interval=TIMEFRAME,
                    start_time=current_start,
                    limit=BINANCE_LIMIT
                )

                if df is None or df.empty:
                    break

                for _, row in df.iterrows():

                    if row["time"] >= end_time:
                        break

                    stmt = insert(MarketData).values(
                        symbol=symbol,
                        timeframe=TIMEFRAME,
                        time=row["time"],
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row["volume"]),
                    ).on_conflict_do_nothing(
                        index_elements=["symbol", "timeframe", "time"]
                    )

                    db.execute(stmt)

                db.commit()

                last_time = df.iloc[-1]["time"]

                # Nếu Binance trả ít hơn limit → đã tới cuối
                if len(df) < BINANCE_LIMIT:
                    break

                current_start = last_time + timedelta(minutes=5)

            print(f"✅ Done backfill for {symbol}")

    print("🎉 Backfill completed.")


if __name__ == "__main__":
    backfill_5m_days(2)