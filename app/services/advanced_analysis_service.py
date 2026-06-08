from app.services.binance_service import get_klines_closed
from app.services.indicator_service import add_indicators_advanced, detect_regime_advanced
from app.services.derivatives_service import get_derivative_data
from app.services.block_service import check_htf_atr_block, check_funding_block
from app.services.signal_service import calculate_score
from app.services.config_service import get_runtime_config


def analyze_advanced(symbol: str, timeframe: str):

    runtime_cfg = get_runtime_config()

    lookback = 400
    df = get_klines_closed(symbol, interval=timeframe, limit=lookback)

    if df is None or df.empty:
        return {"error": "No data"}

    df = add_indicators_advanced(df)
    regime = detect_regime_advanced(df)

    last = df.iloc[-1]
    close = float(last["close"])
    atr = float(last["atr"])
    ema200 = float(last["ema200"])

    atr_pct = round(atr / close * 100, 2)
    ema_dist_pct = round((close - ema200) / ema200 * 100, 2)

    derivative_data = get_derivative_data(symbol, timeframe)
    funding = derivative_data["funding_rate"]
    derivative_bias_long = get_derivative_data(symbol, timeframe)["funding_rate"]

    results = {}

    for direction, fake_pattern in [
        ("LONG", "Bullish Engulfing"),
        ("SHORT", "Bearish Engulfing"),
    ]:

        score, _, components = calculate_score(
            df=df,
            pattern=fake_pattern,
            cfg=runtime_cfg,
            symbol=symbol,
            timeframe=timeframe,
            regime=regime
        )

        htf_block, htf_reason = check_htf_atr_block(
            df=df,
            direction=direction,
            timeframe=timeframe
        )

        funding_block, funding_reason = check_funding_block(
            symbol=symbol,
            direction=direction,
            timeframe=timeframe
        )

        results[direction] = {
            "score": score,
            "components": components,
            "htf_block": htf_block,
            "funding_block": funding_block,
            "htf_reason": htf_reason,
            "funding_reason": funding_reason,
        }

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "regime": regime,
        "atr_pct": atr_pct,
        "ema_dist_pct": ema_dist_pct,
        "funding_rate": funding,
        "long": results["LONG"],
        "short": results["SHORT"],
    }