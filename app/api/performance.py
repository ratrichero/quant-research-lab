from fastapi import APIRouter
from app.db.session import SessionLocal
from app.db.models import Signal
from app.analytics.performance_engine import calculate_performance

router = APIRouter()

@router.get("/performance")
def performance():

    db = SessionLocal()

    trades = db.query(Signal).filter(
        Signal.status.in_(["WIN", "LOSS"])
    ).order_by(Signal.candle_time.asc()).all()

    db.close()

    overall = calculate_performance(trades)

    # Breakdown by pattern
    patterns = {}
    for t in trades:
        patterns.setdefault(t.pattern, []).append(t)

    pattern_stats = {
        p: calculate_performance(ts)
        for p, ts in patterns.items()
    }

    # Breakdown by regime
    regimes = {}
    for t in trades:
        regimes.setdefault(t.regime, []).append(t)

    regime_stats = {
        r: calculate_performance(ts)
        for r, ts in regimes.items()
    }

    return {
        "overall": overall,
        "by_pattern": pattern_stats,
        "by_regime": regime_stats
    }