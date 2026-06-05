from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import traceback

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


app = FastAPI(
    title="Quant Research Lab",
    version="2.0",
    description="Hybrid Quant Trading System with ML + AI Research Assistant"
)
"""
# ✅ Optional CORS (nếu sau này frontend riêng)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
"""
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

# ==================== Monitor Open Trades / Chay trên GCP ko được đâu nhé, dung CronJob ====================

import asyncio
from app.services.trade_monitor import monitor_open_trades


monitor_task = None

@app.on_event("startup")
async def start_trade_monitor():
    global monitor_task

    if monitor_task is not None:
        return

    async def monitor_loop():
        while True:
            try:
                monitor_open_trades()
            except Exception as e:
                print(f"[MONITOR ERROR] {e}")
            await asyncio.sleep(5)

    monitor_task = asyncio.create_task(monitor_loop())

import asyncio
from datetime import datetime
from app.services.signal_service import run_market_scan


def is_scan_minute(now: datetime):
    return now.minute in [1, 16, 31, 46]


@app.on_event("startup")
async def start_local_scheduler():

    async def scan_loop():
        print("📅 Local Cron Scheduler Started")

        last_run_minute = None

        while True:
            now = datetime.utcnow()

            if is_scan_minute(now):

                # tránh chạy 2 lần trong cùng phút
                if last_run_minute != now.minute:
                    print(f"🚀 Running market scan at {now}")
                    try:
                        run_market_scan()
                    except Exception as e:
                        print(f"[SCAN ERROR] {e}")

                    last_run_minute = now.minute

            await asyncio.sleep(10)  # check mỗi 10 giây

    asyncio.create_task(scan_loop())