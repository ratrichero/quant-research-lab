# app/analytics/portfolio_engine.py

from datetime import datetime
import numpy as np


def calculate_position_size(nav, entry, sl, risk_per_trade):
    sl_distance = abs(entry - sl)
    if sl_distance <= 0:
        return 0, 0

    risk_amount = nav * risk_per_trade
    position_size = risk_amount / sl_distance

    capital_used = position_size * entry

    return position_size, risk_amount, capital_used


def run_portfolio_simulation(trades, config):

    initial_capital = config.get("initial_capital", 10000)
    risk_per_trade = config.get("risk_per_trade", 0.01)
    max_portfolio_risk = config.get("max_portfolio_risk", 0.10)

    cash = initial_capital
    nav = initial_capital

    open_positions = []
    equity_curve = []
    timestamps = []

    # ==== 1️⃣ Tạo event timeline ====
    events = []

    for t in trades:
        if not t.created_at:
            continue

        events.append(("OPEN", t.created_at, t))

        if t.exit_time:
            events.append(("CLOSE", t.exit_time, t))

    events.sort(key=lambda x: x[1])

    # ==== 2️⃣ Loop theo timeline ====
    for event_type, ts, trade in events:

        # ===== OPEN =====
        if event_type == "OPEN":

            position_size, risk_amount, capital_used = calculate_position_size(
                nav,
                float(trade.entry_price),
                float(trade.stop_loss),
                risk_per_trade
            )

            # Check portfolio risk
            current_risk = sum(p["risk"] for p in open_positions)

            if current_risk + risk_amount > nav * max_portfolio_risk:
                continue

            # Check đủ cash
            if capital_used > cash:
                continue

            open_positions.append({
                "id": trade.id,
                "entry": float(trade.entry_price),
                "direction": trade.direction,
                "size": position_size,
                "risk": risk_amount,
                "capital_used": capital_used
            })

            cash -= capital_used

        # ===== CLOSE =====
        elif event_type == "CLOSE":

            for pos in open_positions[:]:

                if pos["id"] == trade.id:

                    exit_price = float(trade.exit_price)

                    pnl = pos["size"] * (
                        exit_price - pos["entry"]
                    )

                    if pos["direction"] == "SHORT":
                        pnl *= -1

                    cash += pos["capital_used"] + pnl

                    open_positions.remove(pos)
                    break

        # ==== Update NAV ====
        unrealized = 0  # (backtest offline nên bỏ qua MTM)

        nav = cash + unrealized

        equity_curve.append(nav)
        timestamps.append(ts)

    # ==== 3️⃣ Performance Metrics (Event-Based Version - Corrected) ====

    if len(equity_curve) > 1:
        returns = np.diff(equity_curve) / equity_curve[:-1]
    else:
        returns = np.array([0])

    mean_return = np.mean(returns)
    std_return = np.std(returns)

    # ✅ Sharpe (KHÔNG annualize vì event-based)
    sharpe = 0
    if std_return != 0:
        sharpe = mean_return / std_return

    # ✅ Sortino (KHÔNG annualize)
    downside_returns = returns[returns < 0]
    downside_std = np.std(downside_returns) if len(downside_returns) > 0 else 0

    sortino = 0
    if downside_std != 0:
        sortino = mean_return / downside_std

    # ✅ Drawdown
    peaks = np.maximum.accumulate(equity_curve)
    drawdowns = (equity_curve - peaks) / peaks
    max_dd = np.min(drawdowns) * 100

    # ✅ Total Return
    total_return = (
        (equity_curve[-1] / initial_capital - 1) * 100
        if equity_curve else 0
    )

    # ✅ Calmar (dùng Total Return / Max DD)
    calmar = 0
    if max_dd != 0:
        calmar = (total_return / 100) / abs(max_dd / 100)

    # ✅ Max Consecutive Losing Trades (theo trade thật)
    trade_results = []

    for t in trades:
        if hasattr(t, "result_percent") and t.result_percent is not None:
            trade_results.append(float(t.result_percent))

    max_losing_streak = 0
    current_streak = 0

    for r in trade_results:
        if r < 0:
            current_streak += 1
            max_losing_streak = max(max_losing_streak, current_streak)
        else:
            current_streak = 0

    stats = {
        "final_nav": round(equity_curve[-1], 2) if equity_curve else initial_capital,
        "total_return_percent": round(total_return, 2),
        "sharpe_ratio": round(sharpe, 3),
        "sortino_ratio": round(sortino, 3),
        "calmar_ratio": round(calmar, 3),
        "max_drawdown_percent": round(max_dd, 2),
        "max_consecutive_losses": max_losing_streak,
        "total_trades": len(trades)
    }

    return equity_curve, timestamps, stats

