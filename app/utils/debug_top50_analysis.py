import sys
import os
import pandas as pd
import numpy as np

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from app.db.session import SessionLocal
from app.db.models import TradeOutcomeAnalytics


# ✅ Hardcode Top 50 Market Cap (stable list for research)
TOP50_MARKETCAP = {
    "BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","TRXUSDT",
    "AVAXUSDT","TONUSDT","DOTUSDT","MATICUSDT","LINKUSDT","LTCUSDT","BCHUSDT",
    "NEARUSDT","ICPUSDT","APTUSDT","ETCUSDT","ATOMUSDT","FILUSDT","HBARUSDT",
    "OPUSDT","ARBUSDT","INJUSDT","RNDRUSDT","GRTUSDT","AAVEUSDT","SANDUSDT",
    "MANAUSDT","FLOWUSDT","FTMUSDT","EGLDUSDT","KASUSDT","TIAUSDT","STXUSDT",
    "THETAUSDT","XTZUSDT","EOSUSDT","DYDXUSDT","PEPEUSDT","SHIBUSDT","UNIUSDT",
    "SUIUSDT","BLURUSDT","IMXUSDT","LDOUSDT","WLDUSDT","SEIUSDT"
}


# ─────────────────────────────────────────────
# Load Data
# ─────────────────────────────────────────────

def load_data():
    with SessionLocal() as db:
        rows = db.query(
            TradeOutcomeAnalytics.symbol,
            TradeOutcomeAnalytics.trade_return,
            TradeOutcomeAnalytics.direction,
            TradeOutcomeAnalytics.regime,
            TradeOutcomeAnalytics.mtf_score,
        ).all()

    df = pd.DataFrame(rows, columns=[
        "symbol",
        "trade_return",
        "direction",
        "regime",
        "mtf_score",
    ])

    df["trade_return"] = pd.to_numeric(df["trade_return"], errors="coerce")
    df["mtf_score"] = pd.to_numeric(df["mtf_score"], errors="coerce")

    df = df.dropna(subset=["trade_return"])
    return df


# ─────────────────────────────────────────────
# NAV Simulation (Fixed $1000)
# ─────────────────────────────────────────────

def simulate_nav(df, initial_capital=10000, fixed_trade=1000):

    capital = initial_capital
    peak = initial_capital
    max_dd = 0

    for _, row in df.iterrows():
        r = row.trade_return / 100
        capital += fixed_trade * r

        if capital > peak:
            peak = capital

        dd = (capital - peak) / peak
        if dd < max_dd:
            max_dd = dd

    total_return = (capital - initial_capital) / initial_capital * 100
    return capital, total_return, max_dd * 100


# ─────────────────────────────────────────────
# Scenario Runner
# ─────────────────────────────────────────────

def run_scenario(df, name):

    if len(df) == 0:
        print(f"\n=== {name} ===")
        print("No trades.")
        return

    winrate = (df.trade_return > 0).mean()
    expectancy = df.trade_return.mean()

    final_nav, ret, dd = simulate_nav(df)

    print(f"\n=== {name} ===")
    print(f"Trades: {len(df)}")
    print(f"Winrate: {winrate:.3f}")
    print(f"Expectancy: {expectancy:.4f}%")
    print(f"Final NAV (Fixed $1000): {final_nav:.2f}")
    print(f"Return: {ret:.2f}%")
    print(f"Max DD: {dd:.2f}%")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():

    df = load_data()

    df_top50 = df[df.symbol.isin(TOP50_MARKETCAP)]

    print("Total trades (ALL):", len(df))
    print("Total trades (TOP50):", len(df_top50))

    # BASE
    run_scenario(df, "BASE (ALL SYMBOLS)")

    # TOP50 ONLY
    run_scenario(df_top50, "TOP 50 ONLY")

    # SHORT only (TOP50)
    run_scenario(
        df_top50[df_top50.direction == "SHORT"],
        "TOP 50 SHORT ONLY"
    )

    # MTF HIGH (TOP50)
    if len(df_top50) > 0:
        threshold = df_top50["mtf_score"].quantile(0.66)

        run_scenario(
            df_top50[df_top50.mtf_score >= threshold],
            "TOP 50 MTF HIGH"
        )

        run_scenario(
            df_top50[
                (df_top50.direction == "SHORT") &
                (df_top50.mtf_score >= threshold)
            ],
            "TOP 50 SHORT + MTF HIGH"
        )


if __name__ == "__main__":
    main()