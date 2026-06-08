from app.services.binance_service import get_valid_symbols

# Load một lần khi import
VALID_SYMBOLS = set(get_valid_symbols())