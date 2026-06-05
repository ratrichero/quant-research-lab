import pandas as pd
from app.db.session import SessionLocal
from app.db.models import SignalFeature

def analyze_performance():

    db = SessionLocal()

    data = db.query(SignalFeature).filter(
        SignalFeature.trade_return != None
    ).all()

    db.close()

    if not data:
        print("No closed trades yet.")
        return

    df = pd.DataFrame([{
        "trend": float(d.trend_score or 0),
        "mtf": float(d.mtf_score or 0),
        "penalty": float(d.strict_penalty or 0),
        "total": float(d.total_score or 0),
        "return": float(d.trade_return or 0),
        "label": int(d.label or 0)
    } for d in data])

    print("\n===== OVERALL =====")
    print("Total Trades:", len(df))
    print("Winrate:", df["label"].mean())
    print("Avg Return:", df["return"].mean())

    # =============================
    # 📊 PHÂN TÍCH THEO MTF SCORE
    # =============================

    print("\n===== MTF ANALYSIS =====")

    mtf_groups = df.groupby("mtf").agg({
        "label": "mean",
        "return": "mean",
        "total": "count"
    }).rename(columns={
        "label": "winrate",
        "return": "avg_return",
        "total": "count"
    })

    print(mtf_groups)

    # =============================
    # 📊 PHÂN TÍCH THEO TREND SCORE
    # =============================

    print("\n===== TREND ANALYSIS =====")

    trend_groups = df.groupby("trend").agg({
        "label": "mean",
        "return": "mean",
        "total": "count"
    }).rename(columns={
        "label": "winrate",
        "return": "avg_return",
        "total": "count"
    })

    print(trend_groups)

    # =============================
    # 📊 PHÂN TÍCH THEO PENALTY
    # =============================

    print("\n===== PENALTY ANALYSIS =====")

    penalty_groups = df.groupby("penalty").agg({
        "label": "mean",
        "return": "mean",
        "total": "count"
    }).rename(columns={
        "label": "winrate",
        "return": "avg_return",
        "total": "count"
    })


    print(penalty_groups)

    df["expectancy"] = df["return"]

    print("\nTop 20% score trades expectancy:",
        df[df["total"] > df["total"].quantile(0.8)]["expectancy"].mean())