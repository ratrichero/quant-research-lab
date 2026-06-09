from fastapi import APIRouter, Request,Query
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
from sqlalchemy import desc, asc
from app.analytics.portfolio_engine import run_portfolio_simulation,run_fixed_portfolio_simulation
import numpy as np

router = APIRouter()

# Jinja loader thủ công
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "..", "templates")
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

from fastapi.responses import JSONResponse

@router.post("/close-all")
def close_all_positions():

    db = SessionLocal()

    try:
        open_trades = (
            db.query(Signal)
            .filter(Signal.status == "OPEN")
            .with_for_update()
            .all()
        )

        if not open_trades:
            return {"status": "no_open_trades"}

        price_map = get_all_prices()

        from app.services.trade_close_service import close_trade

        closed_count = 0

        for trade in open_trades:

            current_price = price_map.get(trade.symbol)

            if not current_price:
                continue

            close_trade(db, trade, current_price, "MANUAL_ALL")
            closed_count += 1

        db.commit()

        return {
            "status": "success",
            "closed": closed_count
        }

    except Exception as e:
        db.rollback()
        return {"status": "error", "message": str(e)}

    finally:
        db.close()
        
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
            "timeframe": t.timeframe,
            "stop_loss": float(t.stop_loss) if t.stop_loss else None,
            "take_profit": float(t.take_profit) if t.take_profit else None,
            "regime": t.regime,
            "created_at": (t.created_at + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M') if t.created_at else None,
            "score": float(t.score) if t.score else 0,
            "pnl": round(pnl,2),
            "color": "#4caf50" if pnl>=0 else "#ff5252"
        })

    return results

from fastapi import Query
from sqlalchemy import desc, asc, func

# Nếu sau này >100k record thì nâng cấp bảng nhằm query nhanh
# CREATE INDEX idx_signal_status_exit_time ON signals(status, exit_time DESC);
@router.get("/api/recent-closed")
def api_recent_closed(
    page: int = Query(1, ge=1),
    sort: str = "exit_time",
    order: str = "desc"
):
    db = SessionLocal()

    PER_PAGE = 10

    try:
        # ✅ Map cột được phép sort (anti SQL injection)
        sort_map = {
            "symbol": Signal.symbol,
            "pattern": Signal.pattern,
            "result_percent": Signal.result_percent,
            "exit_time": Signal.exit_time,
            "score": Signal.score,
            "timeframe": Signal.timeframe,
            "created_at": Signal.created_at,
            "direction": Signal.direction,   # ✅ thêm
            "status": Signal.status,         # ✅ thêm
            "regime": Signal.regime,         # ✅ thêm
        }

        sort_column = sort_map.get(sort, Signal.exit_time)
        sort_column = desc(sort_column) if order == "desc" else asc(sort_column)

        # ✅ Base query
        base_query = db.query(Signal).filter(
            Signal.status.in_(["WIN", "LOSS"])
        )

        # ✅ Count tổng số record (không load toàn bộ)
        total = base_query.with_entities(func.count()).scalar()

        # ✅ Server-side pagination thật sự
        rows = (
            base_query
            .order_by(sort_column)
            .offset((page - 1) * PER_PAGE)
            .limit(PER_PAGE)
            .all()
        )

        results = []
        for t in rows:
            results.append({
                "id": t.id,
                "symbol": t.symbol,
                "pattern": t.pattern,
                "direction": t.direction,
                "timeframe": t.timeframe,
                "entry": float(t.entry_price) if t.entry_price else None,
                "exit": float(t.exit_price) if t.exit_price else None,
                "stop_loss": float(t.stop_loss) if t.stop_loss else None,
                "take_profit": float(t.take_profit) if t.take_profit else None,
                "result": round(float(t.result_percent), 2) if t.result_percent else 0,
                "status": t.status,
                "regime": t.regime,
                "score": round(float(t.score), 2) if t.score else 0,
                "created_at": (
                    (t.created_at + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M')
                    if t.created_at else None
                ),
                "exit_time": (
                    (t.exit_time + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M')
                    if t.exit_time else None
                )
            })

        return {
            "data": results,
            "total_pages": (total + PER_PAGE - 1) // PER_PAGE,
            "page": page
        }

    finally:
        db.close()

@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request,page: int = 1,start_date: str = None,end_date: str = None,tf: str = None,fixed_size: float = Query(100, ge=1)):

    selected_tf = tf
    start_dt = None
    end_dt = None
    
    if start_date:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")

    if end_date:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)

    cfg = get_runtime_config()
    db = SessionLocal()

    query = db.query(Signal).filter(Signal.status.in_(["WIN", "LOSS"]))

    if selected_tf:
        query = query.filter(Signal.timeframe == selected_tf)

    if start_dt:
        query = query.filter(Signal.candle_time >= start_dt)

    if end_dt:
        query = query.filter(Signal.candle_time <= end_dt)

    closed_trades = query.order_by(Signal.candle_time.asc()).all()

    open_trades = db.query(Signal).filter(
        Signal.status == "OPEN"
    ).order_by(Signal.candle_time.desc()).all()

    recent_closed = (
        db.query(Signal)
        .filter(Signal.status.in_(["WIN", "LOSS"]))
        .order_by(Signal.exit_time.desc())
        .limit(50)
        .all()
    )

    PER_PAGE = 10
    total_recent = len(recent_closed)
    start = (page - 1) * PER_PAGE
    end = start + PER_PAGE
    recent_page = recent_closed[start:end]
    total_pages = (total_recent + PER_PAGE - 1) // PER_PAGE

    db.close()

    INITIAL_CAPITAL = 10000
   
    # ===== DEFAULT RISK VALUES =====
    strategy_dd = 0
    portfolio_dd = 0
    risk_level = "SAFE"
    risk_model_status = "NEUTRAL"
    dd_delta = 0
    dd_improvement_pct = 0

    if not closed_trades:

        strategy_stats = {
            "total_trades": 0,
            "winrate_percent": 0,
            "profit_factor": 0,
            "expectancy_percent": 0,
            "sharpe_ratio": 0,
            "max_consecutive_losses": 0,
            "max_consecutive_wins": 0,
            "total_return_percent": 0
        }

        portfolio_stats = {
            "final_nav": INITIAL_CAPITAL,
            "total_return_percent": 0,
            "max_drawdown_percent": 0,
            "calmar_ratio": 0,
            "sharpe_ratio": 0,
            "sortino_ratio": 0,
        }

        strategy_equity = [INITIAL_CAPITAL]
        portfolio_equity = [INITIAL_CAPITAL]
        labels = ["0"]
        drawdowns = [0]
        strategy_sharpe = 0
        portfolio_sharpe = 0
        risk_efficiency = 0
        no_data = True

    else:

        # ===== STRATEGY METRICS =====
        strategy_stats = calculate_performance(closed_trades)
        strategy_sharpe = strategy_stats.get("sharpe_ratio", 0)

        # ===== WEEK / MONTH =====
        cutoff_week = datetime.utcnow() - timedelta(days=7)
        cutoff_month = datetime.utcnow() - timedelta(days=30)

        weekly_trades = [t for t in closed_trades if t.candle_time >= cutoff_week]
        monthly_trades = [t for t in closed_trades if t.candle_time >= cutoff_month]

        weekly_stats = calculate_performance(weekly_trades) if weekly_trades else strategy_stats
        monthly_stats = calculate_performance(monthly_trades) if monthly_trades else strategy_stats

        # ===== PORTFOLIO METRICS =====
        PORTFOLIO_CONFIG = {
            "initial_capital": INITIAL_CAPITAL,
            "risk_per_trade": 0.01,
            "max_portfolio_risk": 0.10
        }

        portfolio_equity, timestamps, portfolio_stats = run_portfolio_simulation(
            closed_trades,
            PORTFOLIO_CONFIG
        )
        print("Fixed size:", fixed_size, type(fixed_size))
        # ===== FIXED PORTFOLIO (100$ per trade) =====
        FIXED_CONFIG = {
            "initial_capital": INITIAL_CAPITAL,
            "fixed_trade_size": fixed_size
        }

        fixed_equity, fixed_timestamps, fixed_stats = run_fixed_portfolio_simulation(
            closed_trades,
            FIXED_CONFIG
        )

        #portfolio_equity = portfolio_equity.tolist()
        portfolio_sharpe = portfolio_stats.get("sharpe_ratio", 0)

        # ===== STRATEGY EQUITY (NO SIZING) =====
        returns = np.array([float(t.result_percent) / 100 for t in closed_trades])

        strategy_equity = [INITIAL_CAPITAL]
        for r in returns:
            strategy_equity.append(strategy_equity[-1] * (1 + r))

        strategy_equity = strategy_equity

        # ===== Labels =====
        labels = [str(i) for i in range(len(strategy_equity))]

        # ===== Drawdown Strategy =====
        strategy_peaks = np.maximum.accumulate(strategy_equity)
        drawdown_strategy = (
            (np.array(strategy_equity) - strategy_peaks) / strategy_peaks * 100
        ).tolist()

        # ===== Drawdown Portfolio =====
        portfolio_peaks = np.maximum.accumulate(portfolio_equity)
        drawdown_portfolio = (
            (np.array(portfolio_equity) - portfolio_peaks) / portfolio_peaks * 100
        ).tolist()

        strategy_dd = round(min(drawdown_strategy), 2)
        portfolio_dd = round(min(drawdown_portfolio), 2)

        # ═══════════════════════════════
        # RISK MODEL DIAGNOSTIC
        # ═══════════════════════════════

        dd_delta = round(abs(strategy_dd) - abs(portfolio_dd), 2)

        if strategy_dd != 0:
            dd_improvement_pct = round((dd_delta / abs(strategy_dd)) * 100, 2)
        else:
            dd_improvement_pct = 0

        if dd_delta > 0:
            risk_model_status = "POSITIVE"
        elif dd_delta < 0:
            risk_model_status = "WARNING"
        else:
            risk_model_status = "NEUTRAL"


        # ═══════════════════════════════
        # GLOBAL RISK LEVEL
        # ═══════════════════════════════

        if abs(portfolio_dd) >= 20 or portfolio_sharpe < 0:
            risk_level = "DANGER"

        elif (
            abs(portfolio_dd) >= 15
            or abs(portfolio_dd) > abs(strategy_dd)
            or portfolio_sharpe < 0.5
        ):
            risk_level = "WARNING"

        else:
            risk_level = "SAFE"
        

        # ===== Risk Efficiency =====
        strategy_return = strategy_stats.get("total_return_percent", 0)
        portfolio_return = portfolio_stats.get("total_return_percent", 0)

        risk_efficiency = 0
        if strategy_return != 0:
            risk_efficiency = round(portfolio_return / strategy_return, 3)

        no_data = False

    # ===== Risk Guard =====
    MAX_DD_ALERT = 15
    #risk_alert = abs(strategy_stats.get("max_drawdown_percent", 0)) >= MAX_DD_ALERT
    risk_alert = abs(portfolio_dd) >= MAX_DD_ALERT # cảnh báo dựa trên vốn thực

    # ===== Open Positions =====
    price_map = get_all_prices()
    open_positions = []

    for t in open_trades:
        entry = float(t.entry_price)
        current = float(price_map.get(t.symbol, entry))
        pnl = ((current-entry)/entry)*100 if t.direction=="LONG" else ((entry-current)/entry)*100

        open_positions.append({
            "symbol": t.symbol,
            "pattern": t.pattern,
            "direction": t.direction,
            "timeframe": t.timeframe,
            "entry": round(entry,4),
            "current": round(current,4),
            "pnl": round(pnl,2),
            "color": "#4caf50" if pnl>=0 else "#ff5252"
        })

    # ===== Pattern Breakdown =====
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

    # ===== Regime Breakdown =====
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

    html = template.render(
        timedelta=timedelta,
        strategy_stats=strategy_stats,
        portfolio_stats=portfolio_stats,
        equity=json.dumps(portfolio_equity),
        strategy_equity=json.dumps(strategy_equity),
        labels=json.dumps(labels),
        #drawdowns=json.dumps(drawdowns),
        strategy_sharpe=strategy_sharpe,
        portfolio_sharpe=portfolio_sharpe,
        risk_efficiency=risk_efficiency,
        no_data=no_data,
        weekly_stats=weekly_stats,
        monthly_stats=monthly_stats,
        open_positions=open_positions,
        pattern_stats=pattern_stats,
        regime_stats=regime_stats,
        config=cfg,
        recent_closed=recent_page,
        page=page,
        total_pages=total_pages,
        drawdown_strategy=json.dumps(drawdown_strategy),
        drawdown_portfolio=json.dumps(drawdown_portfolio),
        strategy_dd=strategy_dd,
        portfolio_dd=portfolio_dd,
        risk_level=risk_level,
        risk_model_status=risk_model_status,
        dd_delta=dd_delta,
        dd_improvement_pct=dd_improvement_pct,
        request=request,
        fixed_equity=json.dumps(fixed_equity),
        fixed_size=fixed_size,
        fixed_stats=fixed_stats,
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
        db.rollback()
        db.close()
        return {"status": "error", "message": str(e)}
    finally:
        db.close()

    return {
        "status": "closed",
        "symbol": symbol,
        "exit_price": exit_price
    }