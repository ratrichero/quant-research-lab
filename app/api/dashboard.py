from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from app.db.session import SessionLocal
from app.db.models import Signal
from app.analytics.performance_engine import calculate_performance
from app.services.binance_service import get_klines
from app.services.config_service import get_runtime_config
from datetime import datetime, timedelta
from jinja2 import Environment, FileSystemLoader
import os, json
from app.services.binance_service import get_all_prices

router = APIRouter()

# Jinja loader thủ công
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "..", "templates")
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

from fastapi.responses import JSONResponse

@router.get("/api/open-positions")
def get_open_positions():

    db = SessionLocal()
    open_trades = db.query(Signal).filter(
        Signal.status == "OPEN"
    ).order_by(Signal.created_at.desc()).all()
    db.close()

    # ✅ Gọi Binance 1 lần
    price_map = get_all_prices()

    results = []

    for t in open_trades:

        entry = float(t.entry_price)

        # ✅ Lấy giá từ dict thay vì gọi API
        current = price_map.get(t.symbol, entry)

        pnl = ((current-entry)/entry)*100 if t.direction=="LONG" \
              else ((entry-current)/entry)*100

        results.append({
            "id": t.id,  # ✅ thêm dòng này để frontend có thể nhận biết
            "symbol": t.symbol,
            "pattern": t.pattern,
            "direction": t.direction,
            "entry": round(entry,4),
            "current": round(current,4),
            "stop_loss": float(t.stop_loss) if t.stop_loss else None,
            "take_profit": float(t.take_profit) if t.take_profit else None,
            "regime": t.regime,
            "created_at": (t.created_at + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M') if t.created_at else None,
            "score": float(t.score) if t.score else 0,
            "pnl": round(pnl,2),
            "color": "#4caf50" if pnl>=0 else "#ff5252"
        })

    return results

@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):

    cfg = get_runtime_config()

    db = SessionLocal()
    closed_trades = db.query(Signal).filter(
        Signal.status.in_(["WIN", "LOSS"])
    ).order_by(Signal.candle_time.asc()).all()

    open_trades = db.query(Signal).filter(
        Signal.status == "OPEN"
    ).order_by(Signal.candle_time.desc()).all()
    

    recent_closed = (
        db.query(Signal)
        .filter(Signal.status.in_(["WIN", "LOSS"]))
        .order_by(Signal.exit_time.desc())   # sắp xếp theo giờ đóng mới nhất
        .limit(10)
        .all()
    )
    db.close()
    # ================= PERFORMANCE =================
    if not closed_trades:
        overall = {
            "total_trades": 0,
            "winrate_percent": 0,
            "sharpe_ratio": 0,
            "max_drawdown_percent": 0,
            "profit_factor": 0,
            "expectancy_percent": 0,
        }

        equity = [10000]
        labels = ["Start"]
        drawdowns = [0]
        rolling_sharpe = 0

        weekly_stats = {
            "total_trades": 0,
            "winrate_percent": 0,
            "sharpe_ratio": 0,
        }

        monthly_stats = {
            "total_trades": 0,
            "winrate_percent": 0,
            "sharpe_ratio": 0,
        }
        no_data = True
    else:
        overall = calculate_performance(closed_trades)

        equity = [10000]
        labels = ["Start"]

        for i, t in enumerate(closed_trades):
            equity.append(equity[-1] * (1 + float(t.result_percent) / 100))
            labels.append(str(i + 1))

        peaks = []
        max_peak = equity[0]
        for val in equity:
            max_peak = max(max_peak, val)
            peaks.append(max_peak)

        drawdowns = [
            round((equity[i] - peaks[i]) / peaks[i] * 100, 2)
            for i in range(len(equity))
        ]

        # Rolling 30-day Sharpe
        cutoff_30 = datetime.utcnow() - timedelta(days=30)
        last_30 = [t for t in closed_trades if t.candle_time >= cutoff_30]
        rolling_sharpe = calculate_performance(last_30)["sharpe_ratio"] if last_30 else 0

        # Weekly / Monthly
        cutoff_week = datetime.utcnow() - timedelta(days=7)
        cutoff_month = datetime.utcnow() - timedelta(days=30)

        weekly_trades = [t for t in closed_trades if t.candle_time >= cutoff_week]
        monthly_trades = [t for t in closed_trades if t.candle_time >= cutoff_month]

        def empty_stats():
            return {
                "total_trades": 0,
                "winrate_percent": 0,
                "sharpe_ratio": 0,
                "max_drawdown_percent": 0,
                "profit_factor": 0,
                "expectancy_percent": 0,
            }

        weekly_stats = calculate_performance(weekly_trades) if weekly_trades else empty_stats()
        monthly_stats = calculate_performance(monthly_trades) if monthly_trades else empty_stats()

        no_data = False

    # Risk Guard
    MAX_DD_ALERT = 15
    risk_alert = overall["max_drawdown_percent"] <= -MAX_DD_ALERT

    # Open Positions
    open_positions = []
    for t in open_trades:
        try:
            df_now = get_klines(t.symbol, limit=2)
            current = float(df_now.iloc[-1]["close"])
        except:
            current = float(t.entry_price)

        entry = float(t.entry_price)
        pnl = ((current-entry)/entry)*100 if t.direction=="LONG" else ((entry-current)/entry)*100

        open_positions.append({
            "symbol": t.symbol,
            "pattern": t.pattern,
            "direction": t.direction,
            "entry": round(entry,4),
            "current": round(current,4),
            "pnl": round(pnl,2),
            "color": "#4caf50" if pnl>=0 else "#ff5252"
        })

    # Pattern Breakdown
    pattern_map = {}
    for t in closed_trades:
        pattern_map.setdefault(t.pattern, []).append(t)

    pattern_stats = []
    for name, trades in pattern_map.items():
        stats = calculate_performance(trades)
        pattern_stats.append({
            "name": name,
            "trades": stats["total_trades"],
            "winrate": stats["winrate_percent"],
            "expectancy": stats["expectancy_percent"],
            "profit_factor": stats["profit_factor"]
        })

    # Regime Breakdown
    regime_map = {}
    for t in closed_trades:
        regime_map.setdefault(t.regime, []).append(t)

    regime_stats = []
    for name, trades in regime_map.items():
        stats = calculate_performance(trades)
        regime_stats.append({
            "name": name,
            "trades": stats["total_trades"],
            "winrate": stats["winrate_percent"],
            "expectancy": stats["expectancy_percent"],
            "profit_factor": stats["profit_factor"]
        })

    template = env.get_template("dashboard.html")
    #print("WEEKLY:", weekly_stats)
    #print("MONTHLY:", monthly_stats)
    html = template.render(
        timedelta=timedelta,
        overall=overall,
        equity=json.dumps(equity),
        labels=json.dumps(labels),
        drawdowns=json.dumps(drawdowns),
        no_data=no_data,
        rolling_sharpe=rolling_sharpe,
        weekly_stats=weekly_stats,
        monthly_stats=monthly_stats,
        risk_alert=risk_alert,
        open_positions=open_positions,
        recent_closed=recent_closed,
        pattern_stats=pattern_stats,
        regime_stats=regime_stats,
        config=cfg
    )

    return HTMLResponse(html)

@router.post("/close/{signal_id}")
def manual_close(signal_id: int):

    db = SessionLocal()

    trade = db.query(Signal).filter(
        Signal.id == signal_id
    ).first()

    if not trade or trade.status != "OPEN":
        db.close()
        return {"error": "Invalid or already closed trade"}

    price_map = get_all_prices()
    current_price = price_map.get(trade.symbol)

    if not current_price:
        db.close()
        return {"error": "Price not available"}

    from app.services.trade_close_service import close_trade
    symbol = trade.symbol
    exit_price = current_price
    try:
        close_trade(db, trade, current_price, "MANUAL")
        print("EXIT SET:", trade.exit_price, trade.exit_reason)

        db.commit()
        #print("COMMIT DONE")

    except Exception as e:
        print("ERROR BEFORE COMMIT:", e)
        db.rollback()
    finally:
        db.close()

    return {
        "status": "closed",
        "symbol": symbol,
        "exit_price": exit_price
    }