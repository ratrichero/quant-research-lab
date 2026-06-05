import pandas as pd
from app.db.session import SessionLocal
from app.db.models import ScanDebug, Signal, TradeOutcomeAnalytics


def build_dataset(timeframe="15m", limit=None):
    """
    Build dataset từ scan_debug + signal + outcome
    """

    db = SessionLocal()

    # ✅ JOIN FULL PIPELINE
    query = (
        db.query(ScanDebug, Signal, TradeOutcomeAnalytics)
        .outerjoin(Signal, ScanDebug.signal_id == Signal.id)
        .outerjoin(TradeOutcomeAnalytics, Signal.id == TradeOutcomeAnalytics.signal_id)
        .order_by(ScanDebug.created_at.asc())
    )

    if limit:
        query = query.limit(limit)

    data = query.all()
    db.close()

    rows = []

    for sd, sig, outcome in data:

        # ✅ Feature
        trend = float(sd.trend_score or 0)
        momentum = float(sd.momentum_score or 0)
        volume = float(sd.volume_score or 0)
        pattern = float(sd.pattern_score or 0)
        mtf = float(sd.mtf_score or 0)
        penalty = float(sd.penalty or 0)
        total = float(sd.total_score or 0)
        ml_prob = float(sd.ml_prob) if sd.ml_prob is not None else 0

        # ✅ Encode regime
        regime = 1 if sd.regime == "BULL" else 0

        # ✅ Label logic (QUAN TRỌNG)
        if sig is None:
            label = 0  # ❌ không trade = negative sample
        elif outcome is None:
            continue   # chưa có kết quả → bỏ
        else:
            label = 1 if outcome.label == 1 else 0

        rows.append({
            "trend": trend,
            "momentum": momentum,
            "volume": volume,
            "pattern": pattern,
            "mtf": mtf,
            "penalty": penalty,
            "total": total,
            "ml_prob": ml_prob,
            "regime": regime,
            "label": label
        })

    df = pd.DataFrame(rows)

    print("\n✅ Dataset built")
    print("Total rows:", len(df))
    print("Winrate:", df["label"].mean())

    return df