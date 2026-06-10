from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import asyncio
from datetime import datetime
import traceback
import threading
from asyncio import Queue
from datetime import datetime, timezone, timedelta

# ===== Import service chạy ngầm =====
from app.services.signal_service import run_market_scan_single_tf
from app.services.trade_monitor import monitor_open_trades
from app.services.pending_engine import process_pending_signals

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

from app.bot.telegram_bot import run_bot
from app.core.config import TELEGRAM_TOKEN

#TELEGRAM_TOKEN1 ="8833288986:AAGFhD-D2Kw6UtXJy4VZ1h9XmN2aYTCdwVE"
TELEGRAM_TOKEN1 =TELEGRAM_TOKEN
time_scheduler = 1
time_monitor = 5


scan_queue = Queue()

# ==============================
# SCAN WORKER (Sequential Executor)
# ==============================
async def scan_worker():
    while True:
        timeframe = await scan_queue.get()
        try:
            
            print(
                f"🚀 [SCAN START] {timeframe} | "
                f"{datetime.now(timezone(timedelta(hours=7))).strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            await asyncio.to_thread(run_market_scan_single_tf, timeframe)
            print(f"✅ [SCAN DONE] {timeframe}")
        except Exception as e:
            print(f"[SCAN WORKER ERROR] {e}")
        finally:
            scan_queue.task_done()

# ==============================
# SCHEDULER LOOP (Non-blocking)
# ==============================
async def scheduler_loop():

    last_executed = {
        "15m": None,
        "1h": None,
        "4h": None
    }

    while True:

        cfg = get_runtime_config()

        if not cfg["ENABLE_SCHEDULER"]:
            await asyncio.sleep(5)
            continue

        now = datetime.now()

        # ===== 15m =====
        if now.minute in [1, 16, 31, 46]:
            if last_executed["15m"] != now.minute:
                await scan_queue.put("15m")
                last_executed["15m"] = now.minute

        # ===== 1h =====
        if now.minute == 1:
            if last_executed["1h"] != now.hour:
                await scan_queue.put("1h")
                last_executed["1h"] = now.hour

        # ===== 4h =====
        if now.minute == 1 and now.hour % 4 == 0:
            if last_executed["4h"] != now.hour:
                await scan_queue.put("4h")
                last_executed["4h"] = now.hour

        await asyncio.sleep(time_scheduler)

""" 
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

        await asyncio.sleep(time_scheduler)

"""
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
            # ✅ 1. Process Pending (fill + expire)
            await asyncio.to_thread(process_pending_signals)

            # ✅ 2. Process Open Trades (SL/TP)
            #print(f"[MONITOR At:] {start}")
            await asyncio.to_thread(monitor_open_trades)

        except Exception as e:
            print(f"[MONITOR ERROR] {e}")

        elapsed = (datetime.now() - start).total_seconds()
        sleep_time = max(0, time_monitor - elapsed)
        await asyncio.sleep(sleep_time)


# ==============================
# 3️⃣ Lifespan App
# ==============================
@asynccontextmanager
async def lifespan(app: FastAPI):

    print("✅ Starting background tasks...")

    scheduler_task = asyncio.create_task(scheduler_loop())
    worker_task = asyncio.create_task(scan_worker())
    monitor_task = asyncio.create_task(monitor_loop())

    # Telegram bot thread
    def start_bot():
        run_bot(TELEGRAM_TOKEN1)

    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()

    yield

    print("🛑 Shutting down background tasks...")

    scheduler_task.cancel()
    worker_task.cancel()
    monitor_task.cancel()

    await asyncio.gather(
        scheduler_task,
        worker_task,
        monitor_task,
        return_exceptions=True
    )


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