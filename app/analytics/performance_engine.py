import numpy as np

def calculate_performance(trades, initial_capital=10000):

    if not trades:
        return {}

    returns = np.array([float(t.result_percent)/100 for t in trades])

    # Equity curve
    equity = [initial_capital]
    for r in returns:
        equity.append(equity[-1] * (1 + r))

    equity = np.array(equity)

    # Max Drawdown
    peaks = np.maximum.accumulate(equity)
    drawdowns = (equity - peaks) / peaks
    max_dd = drawdowns.min()

    # Sharpe Ratio
    if returns.std() != 0:
        sharpe = returns.mean() / returns.std() * np.sqrt(252)
    else:
        sharpe = 0

    # Profit Factor
    profits = returns[returns > 0].sum()
    losses = abs(returns[returns < 0].sum())
    profit_factor = profits / losses if losses != 0 else 0

    # Expectancy
    winrate = (returns > 0).mean()
    avg_win = returns[returns > 0].mean() if (returns > 0).any() else 0
    avg_loss = abs(returns[returns < 0].mean()) if (returns < 0).any() else 0

    expectancy = winrate * avg_win - (1 - winrate) * avg_loss

    return {
        "total_trades": len(trades),
        "winrate_percent": round(winrate * 100, 2),
        "avg_win_percent": round(avg_win * 100, 2),
        "avg_loss_percent": round(avg_loss * 100, 2),
        "profit_factor": round(profit_factor, 3),
        "expectancy_percent": round(expectancy * 100, 3),
        "max_drawdown_percent": round(max_dd * 100, 2),
        "sharpe_ratio": round(sharpe, 3),
        "final_equity": round(float(equity[-1]), 2)
    }