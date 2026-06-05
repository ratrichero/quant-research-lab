from fastapi import APIRouter
from app.services.report_service import send_weekly, send_monthly

router = APIRouter()

@router.post("/weekly-report")
def weekly():
    send_weekly()
    return {"status": "weekly sent"}

@router.post("/monthly-report")
def monthly():
    send_monthly()
    return {"status": "monthly sent"}