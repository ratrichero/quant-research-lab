from datetime import datetime, timedelta
from app.db.session import SessionLocal
from app.db.models import Signal
from app.ml.train import train_model
from sqlalchemy import text

MIN_NEW_TRADES = 20   # chỉ retrain nếu có >= 20 trade mới
RETRAIN_INTERVAL_DAYS = 1

def should_retrain():

    db = SessionLocal()

    # Lấy lần retrain gần nhất
    last = db.execute(text("""
        SELECT created_at
        FROM model_registry
        ORDER BY created_at DESC
        LIMIT 1
    """)).fetchone()

    # Nếu chưa từng train → train ngay
    if not last:
        db.close()
        return True

    last_train_time = last[0]

    # Nếu chưa đủ thời gian
    if datetime.utcnow() - last_train_time < timedelta(days=RETRAIN_INTERVAL_DAYS):
        db.close()
        return False

    # Kiểm tra có đủ trade mới không
    count = db.query(Signal).filter(
        Signal.status.in_(["WIN", "LOSS"]),
        Signal.created_at > last_train_time
    ).count()

    db.close()

    return count >= MIN_NEW_TRADES


def retrain_model():

    if not should_retrain():
        print("⏳ Retrain skipped (conditions not met)")
        return {"status": "skipped"}

    print("🚀 Retraining model...")

    metrics = train_model()   # sửa train_model để trả metrics

    db = SessionLocal()

    db.execute(text("""
        INSERT INTO model_registry
        (model_version, train_size, auc, sharpe, max_drawdown)
        VALUES (:version, :size, :auc, :sharpe, :dd)
    """), {
        "version": datetime.utcnow().strftime("%Y%m%d%H%M%S"),
        "size": metrics.get("train_size", 0),
        "auc": metrics.get("auc", 0),
        "sharpe": metrics.get("sharpe", 0),
        "dd": metrics.get("max_dd", 0)
    })

    db.commit()
    db.close()

    print("✅ Retrain complete")

    return {"status": "trained", "metrics": metrics}