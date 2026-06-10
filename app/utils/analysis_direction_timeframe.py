import sys
import os
import pandas as pd

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from app.db.session import SessionLocal
from app.db.models import TradeOutcomeAnalytics


TOP50_MARKETCAP = { ... }  # giữ nguyên list như trên


def load_data():
    with SessionLocal() as db:
        rows = db.query(
            TradeOutcomeAnalytics.symbol,
            TradeOutcomeAnalytics.timeframe,
            TradeOutcomeAnalytics.direction,
            TradeOutcomeAnalytics.trade_return
        ).all()

    df = pd.DataFrame(rows, columns=[
        "symbol","timeframe","direction","trade_return"
    ])
    df["trade_return"] = pd.to_numeric(df["trade_return"], errors="coerce")
    return df.dropna()


def run(df, name):

    print(f"\n===== {name} =====")

    grouped = df.groupby(["timeframe","direction"])

    for (tf, dir_), g in grouped:
        winrate = (g.trade_return > 0).mean()
        expectancy = g.trade_return.mean()
        print(f"{tf} - {dir_}: trades={len(g)}, winrate={winrate:.3f}, expectancy={expectancy:.4f}%")


def main():

    df = load_data()
    df_top50 = df[df.symbol.isin(TOP50_MARKETCAP)]

    run(df, "ALL")
    run(df_top50, "TOP50")


if __name__ == "__main__":
    main()