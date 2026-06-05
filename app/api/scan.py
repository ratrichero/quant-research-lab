from fastapi import APIRouter
from app.services.signal_service import run_market_scan

router = APIRouter()

@router.post("/scan")
async def scan():
    result = run_market_scan()
    return {"status": "ok", "signals_sent": len(result), "signals": result}