import pandas as pd
from app.db.session import SessionLocal
from app.db.models import SignalFeature, TradeOutcomeAnalytics


def build_dataset():

    db = SessionLocal()

    data = (
        db.query(SignalFeature, TradeOutcomeAnalytics)
        .join(TradeOutcomeAnalytics, SignalFeature.signal_id == TradeOutcomeAnalytics.signal_id)
        .all()
    )

    db.close()

    rows = []

    for f, o in data:

        rows.append({
            "trend": float(f.trend_score or 0),
            "momentum": float(f.momentum_score or 0),
            "volume": float(f.volume_score or 0),
            "pattern": float(f.pattern_score or 0),
            "mtf": float(f.mtf_score or 0),
            "penalty": float(f.strict_penalty or 0),
            "ema_distance": float(f.ema_distance or 0),
            "atr_ratio": float(f.atr_ratio or 0),
            "volume_ratio": float(f.volume_ratio or 0),
            "regime": 1 if f.regime == "BULL" else 0,
            "label": 1 if o.label == 1 else 0
        })

    df = pd.DataFrame(rows)

    print("\n✅ Dataset built")
    print("Total rows:", len(df))
    print("Winrate:", df["label"].mean())

    return df