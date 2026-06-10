import sys
import os
import pandas as pd
import numpy as np

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from app.db.session import SessionLocal
from app.db.models import TradeOutcomeAnalytics


# ─────────────────────────────────────────────
# Load data
# ─────────────────────────────────────────────

def load_data():
    with SessionLocal() as db:
        rows = db.query(
            TradeOutcomeAnalytics.trade_return,
            TradeOutcomeAnalytics.direction,
            TradeOutcomeAnalytics.regime,
            TradeOutcomeAnalytics.mtf_score,
            TradeOutcomeAnalytics.total_score,
        ).all()

    df = pd.DataFrame(rows, columns=[
        "trade_return",
        "direction",
        "regime",
        "mtf_score",
        "total_score",
    ])

    df["trade_return"] = pd.to_numeric(df["trade_return"], errors="coerce")
    df["mtf_score"] = pd.to_numeric(df["mtf_score"], errors="coerce")
    df["total_score"] = pd.to_numeric(df["total_score"], errors="coerce")

    df = df.dropna(subset=["trade_return"])
    return df


# ─────────────────────────────────────────────
# NAV Simulation
# ─────────────────────────────────────────────

def simulate_nav(df, initial_capital=10000, fixed_trade=None):

    capital = initial_capital
    nav_curve = []

    for _, row in df.iterrows():

        r = row.trade_return / 100.0

        if fixed_trade:
            capital += fixed_trade * r
        else:
            capital *= (1 + r)

        nav_curve.append(capital)

    final = capital
    total_return = (final - initial_capital) / initial_capital * 100

    dd = 0
    peak = initial_capital

    for value in nav_curve:
        if value > peak:
            peak = value
        drawdown = (value - peak) / peak
        if drawdown < dd:
            dd = drawdown

    return final, total_return, dd * 100


# ─────────────────────────────────────────────
# Run Scenario
# ─────────────────────────────────────────────

def run_scenario(df, name, initial_capital=10000):

    winrate = (df.trade_return > 0).mean()
    expectancy = df.trade_return.mean()

    final_c, ret_c, dd_c = simulate_nav(df, initial_capital)
    final_f, ret_f, dd_f = simulate_nav(df, initial_capital, fixed_trade=1000)

    print(f"\n=== SCENARIO: {name} ===")
    print(f"Trades: {len(df)}")
    print(f"Winrate: {winrate:.3f}")
    print(f"Expectancy: {expectancy:.4f}%")

    print(f"\nCompounded:")
    print(f"Final NAV: {final_c:.2f}")
    print(f"Return: {ret_c:.2f}%")
    print(f"Max DD: {dd_c:.2f}%")

    print(f"\nFixed $1000:")
    print(f"Final NAV: {final_f:.2f}")
    print(f"Return: {ret_f:.2f}%")
    print(f"Max DD: {dd_f:.2f}%")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():

    df = load_data()

    # Base
    run_scenario(df, "BASE")

    # SHORT only
    run_scenario(df[df.direction == "SHORT"], "SHORT ONLY")

    # LONG only
    run_scenario(df[df.direction == "LONG"], "LONG ONLY")

    # MTF HIGH only
    threshold = df["mtf_score"].quantile(0.66)
    run_scenario(df[df.mtf_score >= threshold], "MTF HIGH")

    # SHORT + MTF HIGH
    run_scenario(
        df[(df.direction == "SHORT") & (df.mtf_score >= threshold)],
        "SHORT + MTF HIGH"
    )

    # SHORT + MTF HIGH + SIDEWAYS
    run_scenario(
        df[(df.direction == "SHORT") &
           (df.mtf_score >= threshold) &
           (df.regime == "SIDEWAYS")],
        "SHORT + MTF HIGH + SIDEWAYS"
    )


if __name__ == "__main__":
    main()