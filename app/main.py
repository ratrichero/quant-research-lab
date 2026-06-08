from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import asyncio
from datetime import datetime
import traceback

# ===== Import service chạy ngầm =====
from app.services.signal_service import run_market_scan_multi_tf
from app.services.trade_monitor import monitor_open_trades

# ===== Import routers =====
from app.api.health import router as health_router
from app.api.scan import router as scan_router
from app.api.ml import router as ml_router
from app.api.performance import router as performance_router
from app.api.dashboard import router as dashboard_router
from app.api.assistant import router as assistant_router
from app.api.report import router as report_router
from app.api.report_history import router as report_history_router
from app.api.telegram_webhook import router as telegram_webhook_router
from app.api.config import router as config_router
from app.api.monitor_trade import router as monitor_trade_router
from app.services.config_service import get_runtime_config

# ==============================
# 1️⃣ Scheduler Market Scan
# ==============================
async def scheduler_loop():
    last_run_minute = None

    while True:
        
        cfg = get_runtime_config()

        # ✅ Nếu bị tắt thì ngủ 5s rồi check lại
        if not cfg["ENABLE_SCHEDULER"]:
            await asyncio.sleep(5)
            continue

        now = datetime.now()

        if now.minute in [1, 5, 10, 16, 31, 46] and now.minute != last_run_minute:
            #print(f"🚀 Scan market lúc {now.strftime('%H:%M:%S')}")
            last_run_minute = now.minute

            try:
                await asyncio.to_thread(run_market_scan_multi_tf)
            except Exception as e:
                print(f"[SCAN ERROR] {e}")

        await asyncio.sleep(1)


# ==============================
# 2️⃣ Monitor Trade mỗi 5s
# ==============================
async def monitor_loop():
    while True:
        
        cfg = get_runtime_config()

        # ✅ Nếu monitor bị tắt
        if not cfg["ENABLE_MONITOR"]:
            await asyncio.sleep(5)
            continue

        start = datetime.now()

        try:
            #print(f"[MONITOR At:] {start}")
            await asyncio.to_thread(monitor_open_trades)
        except Exception as e:
            print(f"[MONITOR ERROR] {e}")

        elapsed = (datetime.now() - start).total_seconds()
        sleep_time = max(0, 5 - elapsed)
        await asyncio.sleep(sleep_time)


# ==============================
# 3️⃣ Lifespan App
# ==============================
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("✅ Starting background tasks...")

    scan_task = asyncio.create_task(scheduler_loop())
    monitor_task = asyncio.create_task(monitor_loop())

    yield

    print("🛑 Shutting down background tasks...")
    scan_task.cancel()
    monitor_task.cancel()

    await asyncio.gather(scan_task, monitor_task, return_exceptions=True)


# ==============================
# 4️⃣ FastAPI App
# ==============================
app = FastAPI(
    title="Quant Research Lab",
    version="2.0",
    description="Hybrid Quant Trading System with ML + AI Research Assistant",
    lifespan=lifespan  # ✅ thêm dòng này
)

# ✅ Register routers
app.include_router(health_router)
app.include_router(scan_router)
app.include_router(ml_router)
app.include_router(performance_router)
app.include_router(dashboard_router)
app.include_router(assistant_router)
app.include_router(report_router)
app.include_router(report_history_router)
app.include_router(telegram_webhook_router)
app.include_router(config_router)
app.include_router(monitor_trade_router)


@app.get("/")
def root():
    return {
        "message": "✅ Quant Research Lab Running",
        "docs": "/docs",
        "dashboard": "/dashboard"
    }


# ==================== GLOBAL ERROR HANDLER ====================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_msg = f"{type(exc).__name__}: {str(exc)}"
    print("\n" + "="*80)
    print("🚨 INTERNAL SERVER ERROR")
    print(error_msg)
    print("Traceback:")
    print(traceback.format_exc())
    print("="*80 + "\n")

    return JSONResponse(
        status_code=500,
        content={"error": error_msg, "detail": "Check terminal for full traceback"}
    )