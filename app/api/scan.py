from fastapi import APIRouter
from app.services.signal_service import (
    run_market_scan_single_tf,
    run_market_scan_multi_tf
)
from app.services.config_service import get_runtime_config

router = APIRouter()


# ✅ Manual Docs → single timeframe
@router.post("/scan")
async def scan():

    runtime_cfg = get_runtime_config()
    timeframe = runtime_cfg["TIMEFRAME"]

    result = run_market_scan_single_tf(timeframe)

    return {
        "status": "ok",
        "mode": "single_tf",
        "timeframe": timeframe,
        "result": result
    }


# ✅ Cloud Scheduler → multi timeframe
import threading

@router.post("/scan-multi")
async def scan_multi():

    threading.Thread(
        target=run_market_scan_multi_tf
    ).start()

    return {"status": "started"}