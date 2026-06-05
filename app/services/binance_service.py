import requests
import pandas as pd
from app.core.config import BINANCE_BASE
from functools import lru_cache


def get_all_prices():
  
    url = f"{BINANCE_BASE}/fapi/v1/ticker/price"

    try:
        data = requests.get(url, timeout=5).json()
    except Exception as e:
        print(f"Error fetching exchangeInfo: {e}")
        return []

    if not isinstance(data, list):
        print("Unexpected response:", data)
        return {}

    price_map = {item["symbol"]: float(item["price"]) for item in data}
    return price_map

def get_valid_symbols():

    url = f"{BINANCE_BASE}/fapi/v1/exchangeInfo"
    
    try:
        data = requests.get(url, timeout=10).json()
    except Exception as e:
        print(f"Error fetching exchangeInfo: {e}")
        return []

    symbols = []
    
    blacklist_keywords = ["NVDA", "TSLA", "AAPL", "AMZN", "META", "MSFT", "GOOG", "NFLX", "USD", "EUR", "GBP", "XAU"]

    for s in data["symbols"]:

        if (
            s["contractType"] == "PERPETUAL"
            and s["quoteAsset"] == "USDT"
            and s["status"] == "TRADING"
        ):
            base = s["baseAsset"]

            # Kiểm tra nếu là stock token (thường có các từ khóa trong blacklist)
            if any(keyword in base for keyword in blacklist_keywords):
                continue

            # Chỉ nhận các cặp có tên đơn giản (tránh các loại index lạ)
            # Crypto thường có tên từ 2 đến 7 ký tự (BTC, ETH, SOL, PEPE,...)
            if not base.isalpha() or len(base) > 8:
                continue

            symbols.append(s["symbol"])

    return symbols


def get_top_symbols(limit=30):

    try:
        tickers = requests.get(f"{BINANCE_BASE}/fapi/v1/ticker/24hr", timeout=10).json()
    except Exception as e:
        print(f"Error fetching tickers: {e}")
        return []
    
    valid = set(get_valid_symbols())

    usdt_pairs = [
        t for t in tickers
        if t["symbol"] in valid
    ]

    usdt_pairs = sorted(
        usdt_pairs,
        key=lambda x: float(x["quoteVolume"]),
        reverse=True
    )

    return [x["symbol"] for x in usdt_pairs[:limit]]

import requests
import pandas as pd
import time
from app.core.config import BINANCE_BASE


def get_klines(symbol, limit=200, interval=None, start_time=None, end_time=None):

    from app.services.config_service import get_runtime_config

    # ✅ Nếu không truyền interval → lấy từ runtime config
    if interval is None:
        runtime_cfg = get_runtime_config()
        interval = runtime_cfg["TIMEFRAME"]

    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }

    # ✅ Optional: truyền start/end time (ms)
    if start_time:
        params["startTime"] = int(start_time.timestamp() * 1000)

    if end_time:
        params["endTime"] = int(end_time.timestamp() * 1000)

    url = f"{BINANCE_BASE}/fapi/v1/klines"

    # ✅ Retry nhẹ để tránh timeout ngẫu nhiên
    for attempt in range(3):
        try:
            response = requests.get(url, params=params, timeout=(5, 15))
            response.raise_for_status()
            data = response.json()
            break
        except Exception as e:
            print(f"[KLINES RETRY {attempt+1}] {symbol} error: {e}")
            time.sleep(1)
    else:
        print(f"[KLINES FAILED] {symbol}")
        return pd.DataFrame()

    # ✅ Nếu Binance trả lỗi thay vì list
    if not isinstance(data, list):
        print(f"[KLINES INVALID RESPONSE] {data}")
        return pd.DataFrame()

    df = pd.DataFrame(data, columns=[
        "time", "open", "high", "low", "close", "volume",
        "_", "_", "_", "_", "_", "_"
    ])

    if df.empty:
        return df

    df["open"] = df["open"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["close"] = df["close"].astype(float)
    df["volume"] = df["volume"].astype(float)
    df["time"] = pd.to_datetime(df["time"], unit="ms")

    df = df.sort_values("time").reset_index(drop=True)
    return df

def get_binance_server_time():
    url = f"{BINANCE_BASE}/fapi/v1/time"
    r = requests.get(url, timeout=5).json()
    
    return pd.to_datetime(r["serverTime"], unit="ms")

def get_candle_duration(interval: str):
    from datetime import timedelta

    mapping = {
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "4h": timedelta(hours=4),
        "1d": timedelta(days=1)
    }

    return mapping[interval]

def get_klines_closed(symbol, limit=300, interval=None, start_time=None, end_time=None):

    df = get_klines(
        symbol=symbol,
        limit=limit,
        interval=interval,
        start_time=start_time,
        end_time=end_time
    )

    if df.empty:
        return df

    server_now = get_binance_server_time()
    duration = get_candle_duration(interval)

    # ✅ chỉ giữ candle đã đóng
    df = df[df["time"] + duration <= server_now]

    return df

def debug_candle_status(df, interval, symbol=""):

    if df is None or df.empty:
        print(f"[DEBUG] {symbol} DF EMPTY")
        return

    server_now = get_binance_server_time()
    duration = get_candle_duration(interval)

    last = df.iloc[-1]

    open_time = last["time"]
    close_time = open_time + duration

    is_closed = close_time <= server_now

    print("\n========== CANDLE DEBUG ==========")
    print(f"Symbol: {symbol}")
    print(f"Interval: {interval}")
    print(f"Server time: {server_now}")
    print(f"Last candle open:  {open_time}")
    print(f"Last candle close: {close_time}")
    print(f"Is closed: {is_closed}")
    print("==================================\n")