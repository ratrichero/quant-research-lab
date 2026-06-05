from fastapi import APIRouter
from app.services.trade_monitor import monitor_open_trades
router = APIRouter()

@router.post("/monitor")
def trigger_monitor():

    monitor_open_trades()

    return {"status": "ok"}