import json
from app.db.session import SessionLocal
from sqlalchemy import text

DEFAULTS = {
    "BODY_RATIO_THRESHOLD": "0.35",
    "VOLUME_MULTIPLIER": "1.15",
    "ATR_RATIO_MIN": "0.0015",
    "COOLDOWN_HOURS": "4",
    "MTF_ENABLED": "true",
    "AI_THRESHOLD": "0.0",
    "TOP_LIMIT": "400",
    "DERIVATIVE_CONFIG": json.dumps({
        "pre_buffer": 1,
        "bias_scale": {
            "15m": 0.6,
            "1h": 0.8,
            "4h": 1.0
        }
    })
}

def get_runtime_config():

    db = SessionLocal()
    rows = db.execute(text("SELECT key, value FROM app_config")).fetchall()
    db.close()

    config = {k: v for k, v in rows}

    # ===== DERIVATIVE CONFIG PARSE =====
    derivative_raw = config.get(
        "DERIVATIVE_CONFIG",
        DEFAULTS["DERIVATIVE_CONFIG"]
    )

    try:
        derivative_cfg = json.loads(derivative_raw)
    except Exception:
        derivative_cfg = json.loads(DEFAULTS["DERIVATIVE_CONFIG"])

    return {
        "TIMEFRAME": config.get("TIMEFRAME", "15m"),
        "SCORE_THRESHOLD": float(config.get("SCORE_THRESHOLD", 5)),
        "BODY_RATIO_THRESHOLD": float(config.get("BODY_RATIO_THRESHOLD", 0.5)),
        "VOLUME_MULTIPLIER": float(config.get("VOLUME_MULTIPLIER", 1.3)),
        "ATR_RATIO_MIN": float(config.get("ATR_RATIO_MIN", 0.002)),
        "COOLDOWN_HOURS": int(config.get("COOLDOWN_HOURS", 4)),
        "AI_THRESHOLD": float(config.get("AI_THRESHOLD", 0.0)),
        "TOP_LIMIT": int(config.get("TOP_LIMIT", 100)),
        "MTF_ENABLED": config.get("MTF_ENABLED", "true").lower() == "true",

        # ✅ DERIVATIVE CONFIG
        "DERIVATIVE_CONFIG": derivative_cfg
    }

def update_runtime_config(data: dict):
    db = SessionLocal()
    for k, v in data.items():
        db.execute(
            text("""
                INSERT INTO app_config (key, value, updated_at)
                VALUES (:k, :v, NOW())
                ON CONFLICT (key)
                DO UPDATE SET value = :v, updated_at = NOW()
            """),
            {"k": k, "v": str(v)}
        )
    db.commit()
    db.close()