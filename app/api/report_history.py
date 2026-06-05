from fastapi import APIRouter
from app.db.session import SessionLocal
from sqlalchemy import text

router = APIRouter()

@router.get("/report/{report_type}")
def get_latest_report(report_type: str):

    db = SessionLocal()

    result = db.execute(text("""
        SELECT content
        FROM reports
        WHERE report_type = :type
        ORDER BY created_at DESC
        LIMIT 1
    """), {"type": report_type}).fetchone()

    db.close()

    if result:
        return {"content": result[0]}

    return {"content": "Chưa có báo cáo."}