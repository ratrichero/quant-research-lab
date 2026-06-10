import sys
import os
import pandas as pd

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
            TradeOutcomeAnalytics.timeframe,
            TradeOutcomeAnalytics.regime,
            TradeOutcomeAnalytics.trade_return
        ).all()

    df = pd.DataFrame(rows, columns=[
        "symbol","timeframe","regime","trade_return"
    ])

    df["trade_return"] = pd.to_numeric(df["trade_return"], errors="coerce")
    df = df.dropna(subset=["trade_return"])
    return df


def run(df, name):

    print(f"\n===== {name} =====")

    grouped = df.groupby(["timeframe","regime"], observed=True)

    for (tf, reg), g in grouped:
        winrate = (g.trade_return > 0).mean()
        expectancy = g.trade_return.mean()
        print(f"{tf} - {reg}: trades={len(g)}, winrate={winrate:.3f}, expectancy={expectancy:.4f}%")


def main():

    df = load_data()
    df_top50 = df[df.symbol.isin(TOP50_MARKETCAP)]

    run(df, "ALL")
    run(df_top50, "TOP50")


if __name__ == "__main__":
    main()