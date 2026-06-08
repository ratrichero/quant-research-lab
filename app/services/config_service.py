import json
from app.db.session import SessionLocal
from sqlalchemy import text

DEFAULTS = {
    "TIMEFRAME": "15m",              # ✅ thêm dòng này
    "SCORE_THRESHOLD": "5",          # ✅ thêm nếu chưa có
    "BODY_RATIO_THRESHOLD": "0.35",
    "VOLUME_MULTIPLIER": "1.15",
    "ATR_RATIO_MIN": "0.0015",
    "COOLDOWN_HOURS": "4",
    "MTF_ENABLED": "true",
    "AI_THRESHOLD": "0.0",
    "TOP_LIMIT": "400",
    "ENABLE_SCHEDULER": "true",
    "ENABLE_MONITOR": "true",
    "RISK_CONFIG": json.dumps({
            "15m": {"sl_mult": 1.5, "tp_mult": 3},
            "1h":  {"sl_mult": 1.8, "tp_mult": 3.5},
            "4h":  {"sl_mult": 2.0, "tp_mult": 4}
        }),
    "DERIVATIVE_CONFIG": json.dumps({
        "pre_buffer": 1,
        "bias_scale": {
            "15m": 0.6,
            "1h": 0.8,
            "4h": 1.0
        }
    })
}
_runtime_cache = None

def get_runtime_config(force_reload=False):

    global _runtime_cache

    # ✅ Nếu đã có cache và không force reload
    if _runtime_cache and not force_reload:
        return _runtime_cache
    
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

    # ===== RISK CONFIG ===== ✅ THÊM PHẦN NÀY
    risk_raw = config.get(
        "RISK_CONFIG",
        DEFAULTS["RISK_CONFIG"]
    )

    try:
        risk_cfg = json.loads(risk_raw)
    except Exception:
        risk_cfg = json.loads(DEFAULTS["RISK_CONFIG"])


     # ✅ Build config dict
    _runtime_cache = {
        "TIMEFRAME": config.get("TIMEFRAME", DEFAULTS["TIMEFRAME"]),
        "SCORE_THRESHOLD": float(config.get("SCORE_THRESHOLD", DEFAULTS["SCORE_THRESHOLD"])),
        "BODY_RATIO_THRESHOLD": float(config.get("BODY_RATIO_THRESHOLD", DEFAULTS["BODY_RATIO_THRESHOLD"])),
        "VOLUME_MULTIPLIER": float(config.get("VOLUME_MULTIPLIER", DEFAULTS["VOLUME_MULTIPLIER"])),
        "ATR_RATIO_MIN": float(config.get("ATR_RATIO_MIN", DEFAULTS["ATR_RATIO_MIN"])),
        "COOLDOWN_HOURS": int(config.get("COOLDOWN_HOURS", DEFAULTS["COOLDOWN_HOURS"])),
        "AI_THRESHOLD": float(config.get("AI_THRESHOLD", DEFAULTS["AI_THRESHOLD"])),
        "TOP_LIMIT": int(config.get("TOP_LIMIT", DEFAULTS["TOP_LIMIT"])),
        "MTF_ENABLED": config.get("MTF_ENABLED", DEFAULTS["MTF_ENABLED"]).lower() == "true",
        "ENABLE_SCHEDULER": config.get("ENABLE_SCHEDULER", "true").lower() == "true",
        "ENABLE_MONITOR": config.get("ENABLE_MONITOR", "true").lower() == "true",
        "DERIVATIVE_CONFIG": derivative_cfg,
        "RISK_CONFIG": risk_cfg
    }
    
    return _runtime_cache

def update_runtime_config(data: dict):
    global _runtime_cache
    db = SessionLocal()
    for k, v in data.items():

        # ✅ Nếu là JSON config thì validate
        if k in ["DERIVATIVE_CONFIG", "RISK_CONFIG"]:
            try:
                json.loads(v)   # validate JSON
            except Exception:
                db.close()
                raise ValueError(f"{k} is invalid JSON")

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
    # ✅ Clear cache
    _runtime_cache = None