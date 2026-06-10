import sys
import os
import pandas as pd
import numpy as np

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from app.db.session import SessionLocal
from app.db.models import Signal, TradeOutcomeAnalytics


# ─────────────────────────────────────────────
# Load data
# ─────────────────────────────────────────────

def load_trade_data():

    with SessionLocal() as db:

        rows = (
            db.query(
                TradeOutcomeAnalytics.signal_id,
                TradeOutcomeAnalytics.trade_return,
                TradeOutcomeAnalytics.label,
                TradeOutcomeAnalytics.total_score,
                TradeOutcomeAnalytics.trend_score,
                TradeOutcomeAnalytics.mtf_score,
                TradeOutcomeAnalytics.volatility_at_entry,
                TradeOutcomeAnalytics.regime,
                TradeOutcomeAnalytics.exit_reason,
            )
            .all()
        )

    df = pd.DataFrame(rows, columns=[
        "signal_id",
        "trade_return",
        "label",
        "total_score",
        "trend_score",
        "mtf_score",
        "volatility_at_entry",
        "regime",
        "exit_reason",
    ])

    df = df.dropna(subset=["trade_return"])

    # ✅ Convert Decimal -> float
    numeric_cols = [
        "trade_return",
        "total_score",
        "trend_score",
        "mtf_score",
        "volatility_at_entry",
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


# ─────────────────────────────────────────────
# Basic Metrics
# ─────────────────────────────────────────────

def basic_metrics(df):

    total = len(df)
    wins = df[df["trade_return"] > 0]
    losses = df[df["trade_return"] <= 0]

    winrate = len(wins) / total if total else 0

    avg_win = wins["trade_return"].mean() if len(wins) else 0
    avg_loss = losses["trade_return"].mean() if len(losses) else 0

    expectancy = winrate * avg_win + (1 - winrate) * avg_loss

    profit_factor = (
        wins["trade_return"].sum() / abs(losses["trade_return"].sum())
        if len(losses) else np.nan
    )

    print("\n=== BASIC METRICS ===")
    print(f"Total trades: {total}")
    print(f"Winrate: {winrate:.4f}")
    print(f"Avg win: {avg_win:.4f}")
    print(f"Avg loss: {avg_loss:.4f}")
    print(f"Expectancy: {expectancy:.4f}")
    print(f"Profit Factor: {profit_factor:.4f}")


# ─────────────────────────────────────────────
# Score Quantile Analysis
# ─────────────────────────────────────────────

def score_quantile_analysis(df):

    df["score_bucket"] = pd.qcut(df["total_score"], 4, labels=["Q1", "Q2", "Q3", "Q4"])

    print("\n=== SCORE QUANTILE ANALYSIS ===")

    grouped = df.groupby("score_bucket")

    for name, g in grouped:
        winrate = (g["trade_return"] > 0).mean()
        expectancy = g["trade_return"].mean()
        print(f"{name}: trades={len(g)}, winrate={winrate:.3f}, expectancy={expectancy:.4f}")


# ─────────────────────────────────────────────
# Regime Analysis
# ─────────────────────────────────────────────

def regime_analysis(df):

    print("\n=== REGIME ANALYSIS ===")

    grouped = df.groupby("regime")

    for name, g in grouped:
        winrate = (g["trade_return"] > 0).mean()
        expectancy = g["trade_return"].mean()
        print(f"{name}: trades={len(g)}, winrate={winrate:.3f}, expectancy={expectancy:.4f}")


# ─────────────────────────────────────────────
# MTF Analysis
# ─────────────────────────────────────────────

def mtf_analysis(df):

    df["mtf_bucket"] = pd.qcut(df["mtf_score"], 3, labels=["Low", "Mid", "High"])

    print("\n=== MTF SCORE ANALYSIS ===")

    grouped = df.groupby("mtf_bucket")

    for name, g in grouped:
        winrate = (g["trade_return"] > 0).mean()
        expectancy = g["trade_return"].mean()
        print(f"{name}: trades={len(g)}, winrate={winrate:.3f}, expectancy={expectancy:.4f}")


# ─────────────────────────────────────────────
# Volatility Analysis
# ─────────────────────────────────────────────

def volatility_analysis(df):

    if df["volatility_at_entry"].isnull().all():
        print("\nNo volatility data.")
        return

    df = df.dropna(subset=["volatility_at_entry"])

    df["vol_bucket"] = pd.qcut(df["volatility_at_entry"], 3, labels=["Low", "Mid", "High"])

    print("\n=== VOLATILITY ANALYSIS ===")

    grouped = df.groupby("vol_bucket")

    for name, g in grouped:
        winrate = (g["trade_return"] > 0).mean()
        expectancy = g["trade_return"].mean()
        print(f"{name}: trades={len(g)}, winrate={winrate:.3f}, expectancy={expectancy:.4f}")


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():

    df = load_trade_data()

    if df.empty:
        print("No trade data found.")
        return

    basic_metrics(df)
    score_quantile_analysis(df)
    regime_analysis(df)
    mtf_analysis(df)
    volatility_analysis(df)


if __name__ == "__main__":
    main()