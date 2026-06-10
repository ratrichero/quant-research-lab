import sys
import os
import pandas as pd
import numpy as np

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from app.db.session import SessionLocal
from app.db.models import TradeOutcomeAnalytics


TOP50_MARKETCAP = {
    "BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","TRXUSDT",
    "AVAXUSDT","TONUSDT","DOTUSDT","MATICUSDT","LINKUSDT","LTCUSDT","BCHUSDT",
    "NEARUSDT","ICPUSDT","APTUSDT","ETCUSDT","ATOMUSDT","FILUSDT","HBARUSDT",
    "OPUSDT","ARBUSDT","INJUSDT","RNDRUSDT","GRTUSDT","AAVEUSDT","SANDUSDT",
    "MANAUSDT","FLOWUSDT","FTMUSDT","EGLDUSDT","KASUSDT","TIAUSDT","STXUSDT",
    "THETAUSDT","XTZUSDT","EOSUSDT","DYDXUSDT","PEPEUSDT","SHIBUSDT","UNIUSDT",
    "SUIUSDT","BLURUSDT","IMXUSDT","LDOUSDT","WLDUSDT","SEIUSDT"
}


def load_data():
    with SessionLocal() as db:
        rows = db.query(
            TradeOutcomeAnalytics.symbol,
            TradeOutcomeAnalytics.created_at,
            TradeOutcomeAnalytics.trade_return
        ).all()

    df = pd.DataFrame(rows, columns=[
        "symbol","created_at","trade_return"
    ])

    df["trade_return"] = pd.to_numeric(df["trade_return"], errors="coerce")
    df = df.dropna(subset=["trade_return"])
    df = df.sort_values("created_at")
    return df


def analyze(df, name):

    print(f"\n===== {name} =====")

    midpoint = len(df) // 2

    early = df.iloc[:midpoint]
    late = df.iloc[midpoint:]

    for label, subset in [("EARLY", early), ("LATE", late)]:
        winrate = (subset.trade_return > 0).mean()
        expectancy = subset.trade_return.mean()
        print(f"{label}: trades={len(subset)}, winrate={winrate:.3f}, expectancy={expectancy:.4f}%")


def main():

    df = load_data()
    df_top50 = df[df.symbol.isin(TOP50_MARKETCAP)]

    analyze(df, "ALL")
    analyze(df_top50, "TOP50")


if __name__ == "__main__":
    main()