# app/analytics/portfolio_engine.py

import numpy as np


# ==========================================================
# ✅ COMPOUND PORTFOLIO ENGINE (Capital-Level)
# ==========================================================

def run_portfolio_simulation(trades, config):

    initial_capital = config.get("initial_capital", 10000)

    # ✅ Chỉ lấy WIN / LOSS
    closed_trades = [
        t for t in trades
        if t.status in ("WIN", "LOSS")
        and t.result_percent is not None
        and t.exit_time is not None
    ]

    # ✅ Sort theo exit_time
    closed_trades.sort(key=lambda t: t.exit_time)

    nav = initial_capital
    equity_curve = [nav]
    timestamps = []

    for t in closed_trades:
        r = float(t.result_percent) / 100.0
        nav *= (1 + r)
        equity_curve.append(nav)
        timestamps.append(t.exit_time)

    equity_array = np.array(equity_curve)

    # ===== RETURNS =====
    if len(equity_array) > 1:
        returns = np.diff(equity_array) / equity_array[:-1]
    else:
        returns = np.array([0.0])

    mean_return = np.mean(returns)
    std_return = np.std(returns)

    # ✅ Sharpe fix
    if std_return < 1e-12:
        sharpe = 0
    else:
        sharpe = mean_return / std_return

    # ✅ Sortino fix
    downside_returns = returns[returns < 0]
    downside_std = np.std(downside_returns) if len(downside_returns) > 0 else 0

    if downside_std < 1e-12:
        sortino = 0
    else:
        sortino = mean_return / downside_std

    # ===== DRAW DOWN =====
    peaks = np.maximum.accumulate(equity_array)
    drawdowns = (equity_array - peaks) / peaks
    max_dd = np.min(drawdowns) * 100

    # ===== TOTAL RETURN =====
    total_return = (
        (equity_array[-1] / initial_capital - 1) * 100
        if len(equity_array) > 0 else 0
    )

    # ===== CALMAR =====
    if abs(max_dd) < 1e-12:
        calmar = 0
    else:
        calmar = (total_return / 100) / abs(max_dd / 100)

    # ===== MAX LOSING STREAK =====
    trade_results = [float(t.result_percent) for t in closed_trades]

    max_losing_streak = 0
    current_streak = 0

    for r in trade_results:
        if r < 0:
            current_streak += 1
            max_losing_streak = max(max_losing_streak, current_streak)
        else:
            current_streak = 0

    stats = {
        "final_nav": round(equity_array[-1], 2),
        "total_return_percent": round(total_return, 2),
        "sharpe_ratio": round(sharpe, 3),
        "sortino_ratio": round(sortino, 3),
        "calmar_ratio": round(calmar, 3),
        "max_drawdown_percent": round(max_dd, 2),
        "max_consecutive_losses": max_losing_streak,
        "total_trades": len(closed_trades)
    }

    return equity_curve, timestamps, stats


# ==========================================================
# ✅ FIXED SIZE PORTFOLIO ENGINE
# ==========================================================

def run_fixed_portfolio_simulation(trades, config):

    initial_capital = config.get("initial_capital", 10000)
    fixed_size = config.get("fixed_trade_size", 100)

    nav = initial_capital
    equity_curve = [nav]
    timestamps = []

    closed_trades = [
        t for t in trades
        if t.status in ("WIN", "LOSS")
        and t.result_percent is not None
        and t.exit_time is not None
    ]

    closed_trades.sort(key=lambda t: t.exit_time)

    for t in closed_trades:

        pnl = fixed_size * (float(t.result_percent) / 100.0)
        nav += pnl

        equity_curve.append(nav)
        timestamps.append(t.exit_time)

    equity_array = np.array(equity_curve)

    # ===== RETURNS =====
    if len(equity_array) > 1:
        returns = np.diff(equity_array) / equity_array[:-1]
    else:
        returns = np.array([0.0])

    mean_return = np.mean(returns)
    std_return = np.std(returns)

    # ✅ Sharpe fix
    if std_return < 1e-12:
        sharpe = 0
    else:
        sharpe = mean_return / std_return

    # ===== DRAW DOWN =====
    peaks = np.maximum.accumulate(equity_array)
    drawdowns = (equity_array - peaks) / peaks
    max_dd = np.min(drawdowns)

    total_return = (
        (equity_array[-1] / initial_capital - 1) * 100
        if len(equity_array) > 0 else 0
    )

    if abs(max_dd) < 1e-12:
        calmar = 0
    else:
        calmar = (total_return / 100) / abs(max_dd)

    stats = {
        "final_nav": round(equity_array[-1], 2),
        "total_return_percent": round(total_return, 2),
        "sharpe_ratio": round(sharpe, 3),
        "calmar_ratio": round(calmar, 3),
        "max_drawdown_percent": round(max_dd * 100, 2),
        "total_trades": len(closed_trades),
        "fixed_trade_size": fixed_size
    }

    return equity_curve, timestamps, stats
