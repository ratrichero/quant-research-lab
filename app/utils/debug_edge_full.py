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
# LOAD DATA
# ─────────────────────────────────────────────

def load_data():
    with SessionLocal() as db:
        rows = db.query(
            TradeOutcomeAnalytics.trade_return,
            TradeOutcomeAnalytics.max_drawdown,
            TradeOutcomeAnalytics.max_favorable,
            TradeOutcomeAnalytics.total_score,
            TradeOutcomeAnalytics.mtf_score,
            TradeOutcomeAnalytics.volatility_at_entry,
            TradeOutcomeAnalytics.regime,
            TradeOutcomeAnalytics.direction,
            TradeOutcomeAnalytics.entry_price,
            TradeOutcomeAnalytics.stop_loss,
        ).all()

    df = pd.DataFrame(rows, columns=[
        "trade_return",
        "mae",
        "mfe",
        "total_score",
        "mtf_score",
        "volatility",
        "regime",
        "direction",
        "entry_price",
        "stop_loss",
    ])

    numeric_cols = [
        "trade_return",
        "mae",
        "mfe",
        "total_score",
        "mtf_score",
        "volatility",
        "entry_price",
        "stop_loss",
    ]

    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["trade_return"])
    return df


# ─────────────────────────────────────────────
# BASIC METRICS
# ─────────────────────────────────────────────

def basic_metrics(df):
    wins = df[df.trade_return > 0]
    losses = df[df.trade_return <= 0]

    winrate = len(wins) / len(df)
    expectancy = df.trade_return.mean()
    pf = wins.trade_return.sum() / abs(losses.trade_return.sum())

    print("\n=== BASIC ===")
    print(f"Trades: {len(df)}")
    print(f"Winrate: {winrate:.3f}")
    print(f"Expectancy: {expectancy:.4f}")
    print(f"Profit Factor: {pf:.3f}")


# ─────────────────────────────────────────────
# DIRECTION ANALYSIS
# ─────────────────────────────────────────────

def direction_analysis(df):
    print("\n=== DIRECTION ANALYSIS ===")
    grouped = df.groupby("direction")
    for name, g in grouped:
        print(f"{name}: trades={len(g)}, winrate={(g.trade_return>0).mean():.3f}, expectancy={g.trade_return.mean():.4f}")


# ─────────────────────────────────────────────
# REGIME × DIRECTION
# ─────────────────────────────────────────────

def regime_direction_matrix(df):
    print("\n=== REGIME × DIRECTION ===")
    grouped = df.groupby(["regime", "direction"])
    for (reg, dir_), g in grouped:
        print(f"{reg} - {dir_}: trades={len(g)}, winrate={(g.trade_return>0).mean():.3f}, expectancy={g.trade_return.mean():.4f}")


# ─────────────────────────────────────────────
# MTF BUCKET
# ─────────────────────────────────────────────

def mtf_analysis(df):
    df["mtf_bucket"] = pd.qcut(df["mtf_score"], 3, labels=["Low", "Mid", "High"])
    print("\n=== MTF BUCKET ===")
    grouped = df.groupby("mtf_bucket")
    for name, g in grouped:
        print(f"{name}: trades={len(g)}, winrate={(g.trade_return>0).mean():.3f}, expectancy={g.trade_return.mean():.4f}")


# ─────────────────────────────────────────────
# SCORE BUCKET
# ─────────────────────────────────────────────

def score_analysis(df):
    df["score_bucket"] = pd.qcut(df["total_score"], 4, labels=["Q1","Q2","Q3","Q4"])
    print("\n=== SCORE BUCKET ===")
    grouped = df.groupby("score_bucket")
    for name, g in grouped:
        print(f"{name}: trades={len(g)}, winrate={(g.trade_return>0).mean():.3f}, expectancy={g.trade_return.mean():.4f}")


# ─────────────────────────────────────────────
# RR SIMULATION (PRECISE)
# ─────────────────────────────────────────────

def simulate_rr(df, rr_multiplier, label="ALL"):

    results = []

    for _, row in df.iterrows():

        entry = row.entry_price
        stop = row.stop_loss
        mae = row.mae
        mfe = row.mfe
        trade_return = row.trade_return

        if pd.isna(entry) or pd.isna(stop) or pd.isna(mae) or pd.isna(mfe):
            continue

        risk = abs((stop - entry) / entry * 100)
        tp_new = risk * rr_multiplier

        # Trade thắng thực tế
        if trade_return > 0:

            if mfe >= tp_new:
                results.append(tp_new)
            else:
                results.append(trade_return)

        # Trade thua thực tế
        else:

            if mfe >= tp_new:
                results.append(tp_new)
            else:
                results.append(-risk)

    if len(results) == 0:
        return

    results = np.array(results)

    winrate = (results > 0).mean()
    expectancy = results.mean()

    print(f"\nRR Simulation [{label}] Multiplier={rr_multiplier}")
    print(f"Trades={len(results)}, Winrate={winrate:.3f}, Expectancy={expectancy:.4f}")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():

    df = load_data()

    basic_metrics(df)
    direction_analysis(df)
    regime_direction_matrix(df)
    mtf_analysis(df)
    score_analysis(df)

    # RR tests ALL
    simulate_rr(df, 2.0, "ALL 1:2")
    simulate_rr(df, 1.5, "ALL 1:1.5")
    simulate_rr(df, 1.25, "ALL 1:1.25")
    simulate_rr(df, 1.0, "ALL 1:1")

    # RR tests MTF HIGH
    threshold = df["mtf_score"].quantile(0.66)
    df_high = df[df["mtf_score"] >= threshold]

    simulate_rr(df_high, 2.0, "MTF HIGH 1:2")
    simulate_rr(df_high, 1.5, "MTF HIGH 1:1.5")

    # RR tests by regime
    for reg in df["regime"].unique():
        simulate_rr(df[df["regime"] == reg], 2.0, f"{reg} 1:2")


if __name__ == "__main__":
    main()