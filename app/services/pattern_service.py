def detect_pattern(df):

    if len(df) < 5:
        return None

    prev2 = df.iloc[-4]
    prev = df.iloc[-3]
    curr = df.iloc[-2]

    # -------------------------------
    # 1. Bullish Engulfing
    # -------------------------------
    if (
        prev["close"] < prev["open"] and
        curr["close"] > curr["open"] and
        curr["open"] <= prev["close"] and
        curr["close"] >= prev["open"]
    ):
        return "Bullish Engulfing"

    # -------------------------------
    # 2. Bearish Engulfing
    # -------------------------------
    if (
        prev["close"] > prev["open"] and
        curr["close"] < curr["open"] and
        curr["open"] >= prev["close"] and
        curr["close"] <= prev["open"]
    ):
        return "Bearish Engulfing"

    body = abs(curr["close"] - curr["open"])
    full_range = curr["high"] - curr["low"]
    upper_wick = curr["high"] - max(curr["close"], curr["open"])
    lower_wick = min(curr["close"], curr["open"]) - curr["low"]

    # -------------------------------
    # 3. Hammer
    # -------------------------------
    if lower_wick > body * 2 and upper_wick < body:
        return "Hammer"

    # -------------------------------
    # 4. Shooting Star
    # -------------------------------
    if upper_wick > body * 2 and lower_wick < body:
        return "Shooting Star"

    # -------------------------------
    # 5. Morning Star
    # -------------------------------
    if (
        prev2["close"] < prev2["open"] and
        abs(prev["close"] - prev["open"]) < abs(prev2["close"] - prev2["open"]) * 0.5 and
        curr["close"] > curr["open"] and
        curr["close"] > prev2["open"]
    ):
        return "Morning Star"

    # -------------------------------
    # 6. Evening Star
    # -------------------------------
    if (
        prev2["close"] > prev2["open"] and
        abs(prev["close"] - prev["open"]) < abs(prev2["close"] - prev2["open"]) * 0.5 and
        curr["close"] < curr["open"] and
        curr["close"] < prev2["open"]
    ):
        return "Evening Star"

    # -------------------------------
    # 7. Bullish Marubozu
    # -------------------------------
    if body / full_range > 0.9 and curr["close"] > curr["open"]:
        return "Bullish Marubozu"

    # -------------------------------
    # 8. Bearish Marubozu
    # -------------------------------
    if body / full_range > 0.9 and curr["close"] < curr["open"]:
        return "Bearish Marubozu"

    return None