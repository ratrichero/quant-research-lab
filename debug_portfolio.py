from app.db.session import SessionLocal
from app.db.models import Signal
from app.analytics.performance_engine import calculate_performance
from app.analytics.portfolio_engine import run_portfolio_simulation
from datetime import datetime
import numpy as np


def run_debug():

    db = SessionLocal()

    trades = db.query(Signal).filter(
        Signal.status.in_(["WIN", "LOSS"])
    ).order_by(Signal.candle_time.asc()).all()

    db.close()

    print("TOTAL TRADES:", len(trades))

    # ===== Strategy Stats =====
    strategy_stats = calculate_performance(trades)

    print("\n--- STRATEGY METRICS ---")
    print("Winrate:", strategy_stats["winrate_percent"])
    print("Profit Factor:", strategy_stats["profit_factor"])
    print("Expectancy %:", strategy_stats["expectancy_percent"])
    print("Sharpe:", strategy_stats["sharpe_ratio"])
    print("Max Losing Streak:", strategy_stats["max_consecutive_losses"])
    print("Max Win Streak:", strategy_stats["max_consecutive_wins"])

    # ===== Portfolio Stats =====
    PORTFOLIO_CONFIG = {
        "initial_capital": 10000,
        "risk_per_trade": 0.01,
        "max_portfolio_risk": 0.10
    }

    equity, timestamps, portfolio_stats = run_portfolio_simulation(
        trades,
        PORTFOLIO_CONFIG
    )

    print("\n--- PORTFOLIO METRICS ---")
    print("Final NAV:", portfolio_stats["final_nav"])
    print("Total Return %:", portfolio_stats["total_return_percent"])
    print("Max Drawdown %:", portfolio_stats["max_drawdown_percent"])
    print("Sharpe (Portfolio):", portfolio_stats["sharpe_ratio"])

    print("\n--- DEBUG EXTRA ---")
    print("Min NAV:", min(equity))
    print("Max NAV:", max(equity))

    returns = np.array([float(t.result_percent) / 100 for t in trades])
    print("Mean Trade Return %:", np.mean(returns) * 100)
    print("Total Profit Sum:", returns[returns > 0].sum())
    print("Total Loss Sum:", abs(returns[returns < 0].sum()))

    sl_distances = [
        abs(float(t.entry_price) - float(t.stop_loss))
        for t in trades
        if t.stop_loss is not None
    ]

    if sl_distances:
        print("Avg SL Distance:", sum(sl_distances) / len(sl_distances))

    print("MIN SL DIST:", min(sl_distances))
    print("MAX SL DIST:", max(sl_distances))


if __name__ == "__main__":
    run_debug()