import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BINANCE_BASE = "https://fapi.binance.com"
ENGINE_VERSION = 4.06

"""
TIMEFRAME = os.getenv("TIMEFRAME", "15m")
TOP_LIMIT = int(os.getenv("TOP_LIMIT", 30))
SCORE_THRESHOLD = int(os.getenv("SCORE_THRESHOLD", 5))
AI_THRESHOLD = float(os.getenv("AI_THRESHOLD", 0.6))

BODY_RATIO_THRESHOLD = float(os.getenv("BODY_RATIO_THRESHOLD", 0.5))
VOLUME_MULTIPLIER = float(os.getenv("VOLUME_MULTIPLIER", 1.3))
ATR_RATIO_MIN = float(os.getenv("ATR_RATIO_MIN", 0.002))
COOLDOWN_HOURS = int(os.getenv("COOLDOWN_HOURS", 4))
MTF_ENABLED = os.getenv("MTF_ENABLED", "true").lower() == "true"

"""