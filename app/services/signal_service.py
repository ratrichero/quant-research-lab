import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

from app.services.binance_service import get_top_symbols, get_klines
from app.services.indicator_service import add_indicators, add_indicators_advanced, detect_regime, detect_regime_advanced, get_market_state
from app.services.pattern_service import detect_pattern
from app.services.telegram_service import send_telegram

from app.db.session import SessionLocal
from app.db.models import Signal

from app.ml.predict import predict_prob
from app.ml.features import build_features_from_row
from app.services.llm_router import generate_explanation


# ============================================================
# TIMEZONE HELPER (Display only)
# ============================================================

def to_local_time(dt):
    return dt.replace(tzinfo=timezone.utc).astimezone(
        timezone(timedelta(hours=7))
    )


# ============================================================
# PATTERN-DRIVEN SCORE
# ============================================================

def calculate_score(df, pattern, cfg, symbol, timeframe):

    last = df.iloc[-2]
    prev = df.iloc[-3]

    state = get_market_state(df)

    # ================= DIRECTION =================
    bullish_patterns = [
        "Bullish Engulfing", "Hammer",
        "Morning Star", "Bullish Marubozu"
    ]
    bearish_patterns = [
        "Bearish Engulfing", "Shooting Star",
        "Evening Star", "Bearish Marubozu"
    ]

    if pattern in bullish_patterns:
        direction = "LONG"
    elif pattern in bearish_patterns:
        direction = "SHORT"
    else:
        return 0, None, {}

    trend_score = 0
    momentum_score = 0
    volume_score = 0
    pattern_score = 0
    mtf_score = 0
    strict_penalty = 0

    # ================= TREND =================
    ema200 = last.get("ema200")
    ema50 = last.get("ema50")

    if ema200 is not None and ema200 != 0:

        distance = (last["close"] - ema200) / ema200
        abs_distance = abs(distance)

        if direction == "LONG":
            if last["close"] > ema200:
                trend_score += 2
            elif abs_distance < 0.02:
                trend_score += 1

            if ema50 and ema50 > ema200:
                trend_score += 1

        else:
            if last["close"] < ema200:
                trend_score += 2
            elif abs_distance < 0.02:
                trend_score += 1

            if ema50 and ema50 < ema200:
                trend_score += 1

    # ================= MOMENTUM =================
    rsi = last.get("rsi")

    if rsi is not None:

        # ✅ Context boost từ market state
        if direction == "LONG" and state["rsi_oversold"]:
            momentum_score += 0.5

        elif direction == "SHORT" and state["rsi_overbought"]:
            momentum_score += 0.5

        if direction == "LONG":
            if rsi < 35:
                momentum_score += 2
            elif 35 <= rsi <= 45:
                momentum_score += 1
        else:
            if rsi > 65:
                momentum_score += 2
            elif 55 <= rsi <= 65:
                momentum_score += 1

    # ================= VOLUME =================
    vol_ratio = None
    if last.get("vol_ma") and last["vol_ma"] > 0:
        vol_ratio = last["volume"] / last["vol_ma"]

        if vol_ratio > 2:
            volume_score += 2
        elif vol_ratio > cfg["VOLUME_MULTIPLIER"]:
            volume_score += 1

    if state["high_volume"]:
        volume_score += 0.5

    # ================= PATTERN =================
    pattern_strength = {
        "Morning Star": 2,
        "Evening Star": 2,
        "Bullish Engulfing": 2,
        "Bearish Engulfing": 2,
        "Hammer": 1.5,
        "Shooting Star": 1.5,
        "Bullish Marubozu": 1.5,
        "Bearish Marubozu": 1.5
    }

    base = pattern_strength.get(pattern, 0)
    body = abs(last["close"] - last["open"])
    full_range = last["high"] - last["low"]

    if full_range > 0:
        pattern_score = base * (body / full_range)

    bb_position = last.get("bb_position")

    if bb_position is not None:

        if direction == "LONG" and bb_position < 0.2:
            pattern_score += 0.5

        elif direction == "SHORT" and bb_position > 0.8:
            pattern_score += 0.5

    # ================= MTF =================
    if cfg.get("MTF_ENABLED", False):

        higher_tf = get_higher_timeframe(timeframe)

        if higher_tf:
            df_htf = get_klines(symbol, interval=higher_tf, limit=200)
            if not df_htf.empty:
                df_htf = add_indicators_advanced(df_htf)
                htf_last = df_htf.iloc[-2]

                htf_ema200 = htf_last.get("ema200")
                htf_rsi = htf_last.get("rsi")

                if htf_ema200 and htf_ema200 != 0:
                    htf_distance = (htf_last["close"] - htf_ema200) / htf_ema200
                    abs_htf_distance = abs(htf_distance)

                    if direction == "LONG":
                        if htf_last["close"] > htf_ema200:
                            mtf_score += 1
                        elif abs_htf_distance < 0.02:
                            mtf_score += 0.5
                        if htf_rsi and htf_rsi > 50:
                            mtf_score += 0.25

                    else:
                        if htf_last["close"] < htf_ema200:
                            mtf_score += 1
                        elif abs_htf_distance < 0.02:
                            mtf_score += 0.5
                        if htf_rsi and htf_rsi < 50:
                            mtf_score += 0.25

    # ================= SOFT PENALTY =================
    body_ratio = body / full_range if full_range > 0 else 0

    if body_ratio < cfg["BODY_RATIO_THRESHOLD"]:
        strict_penalty -= 0.5

    if vol_ratio is None or vol_ratio < cfg["VOLUME_MULTIPLIER"]:
        strict_penalty -= 0.5

    atr_ratio = None
    if last.get("atr") and last["close"] != 0:
        atr_ratio = last["atr"] / last["close"]

    if atr_ratio is None or atr_ratio < cfg["ATR_RATIO_MIN"]:
        strict_penalty -= 0.5

    # ================= NORMALIZE =================
    trend_norm = trend_score / 3
    momentum_norm = momentum_score / 2
    volume_norm = volume_score / 2
    pattern_norm = pattern_score / 2
    mtf_norm = min(mtf_score / 1.75, 1)

    penalty_norm = strict_penalty / 1.5  # max -1

    rule_score = (
        0.30 * trend_norm +
        0.20 * momentum_norm +
        0.15 * volume_norm +
        0.20 * pattern_norm +
        0.15 * mtf_norm
    ) + penalty_norm

    final_score = round((rule_score + 1) * 5, 2)

    components = {
        "trend_score": trend_score,
        "momentum_score": momentum_score,
        "volume_score": volume_score,
        "pattern_score": pattern_score,
        "mtf_score": mtf_score,
        "strict_penalty": strict_penalty,
        "rule_score_raw": rule_score,
        "rule_score_scaled": final_score
    }

    return final_score, direction, components

# ============================================================
# STRICT FILTERS (ANTI-NOISE)
# ============================================================

def strict_filters(df, cfg):
    """
    Trả về penalty_score thay vì boolean.
    Penalty = 0 nếu pass hết.
    Penalty = âm nếu vi phạm.
    """
    curr = df.iloc[-2]

    body = abs(curr["close"] - curr["open"])
    full_range = curr["high"] - curr["low"]
    
    body_ratio = body / full_range if full_range > 0 else 0
    
    volume_ratio = None
    if not pd.isna(curr.get("vol_ma")) and curr["vol_ma"] > 0:
        volume_ratio = curr["volume"] / curr["vol_ma"]
    
    atr_ratio = None
    if not pd.isna(curr.get("atr")) and curr["close"] > 0:
        atr_ratio = curr["atr"] / curr["close"]

    # ===============================
    # ADAPTIVE VOLATILITY FACTOR
    # ===============================
    volatility_factor = 1.0
    if not pd.isna(curr.get("atr")) and "atr" in df.columns:
        avg_atr = df["atr"].rolling(50).mean().iloc[-2]
        if avg_atr and avg_atr > 0:
            volatility_factor = curr["atr"] / avg_atr
            volatility_factor = max(0.7, min(volatility_factor, 1.5))

    dynamic_body = cfg["BODY_RATIO_THRESHOLD"] * (1 / volatility_factor)
    dynamic_vol = cfg["VOLUME_MULTIPLIER"] * volatility_factor
    dynamic_atr = cfg["ATR_RATIO_MIN"] * (1 / volatility_factor)

    # ===============================
    # CALCULATE PENALTY (soft fail)
    # ===============================
    penalty = 0
    reasons = []

    # Body penalty: càng thấp càng phạt nặng
    if body_ratio < dynamic_body:
        if body_ratio < dynamic_body * 0.5:
            penalty -= 1
            reasons.append("body_severe")
        else:
            penalty -= 0.5
            reasons.append("body_weak")

    # Volume penalty
    if volume_ratio is None or volume_ratio < dynamic_vol:
        if volume_ratio is None or volume_ratio < dynamic_vol * 0.7:
            penalty -= 1
            reasons.append("volume_severe")
        else:
            penalty -= 0.5
            reasons.append("volume_weak")

    # ATR penalty
    if atr_ratio is None or atr_ratio < dynamic_atr:
        if atr_ratio is None or atr_ratio < dynamic_atr * 0.5:
            penalty -= 1
            reasons.append("atr_severe")
        else:
            penalty -= 0.5
            reasons.append("atr_weak")

    block_reason = ",".join(reasons) if reasons else None

    return penalty, block_reason, {
        "body_ratio": body_ratio,
        "volume_ratio": volume_ratio,
        "atr_ratio": atr_ratio,
        "volatility_factor": volatility_factor,
        "dynamic_body": dynamic_body,
        "dynamic_vol": dynamic_vol,
        "dynamic_atr": dynamic_atr
    }

def multi_timeframe_confirm(symbol, direction, current_tf):
    
    higher_tf = get_higher_timeframe(current_tf)

    if not higher_tf:
        return True  # Không có khung cao hơn -> bỏ qua confirm

    df_htf = get_klines(symbol, limit=200, interval=higher_tf)

    if df_htf.empty or len(df_htf) < 200:
        return False

    df_htf = add_indicators_advanced(df_htf)

    last_htf = df_htf.iloc[-2]

    if direction == "LONG" and last_htf["close"] > last_htf["ema200"]:
        return True

    if direction == "SHORT" and last_htf["close"] < last_htf["ema200"]:
        return True

    return False

# ============================================================
# DUPLICATE + COOLDOWN
# ============================================================

def is_duplicate(db, symbol, timeframe, candle_time):
    return db.query(Signal).filter(
        Signal.symbol == symbol,
        Signal.timeframe == timeframe,
        Signal.candle_time == candle_time
    ).first() is not None


def in_cooldown(db, symbol, timeframe, hours=4):
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    return db.query(Signal).filter(
        Signal.symbol == symbol,
        Signal.timeframe == timeframe,
        Signal.created_at >= cutoff
    ).first() is not None

def get_higher_timeframe(tf: str) -> str:
    mapping = {
        "15m": "1h",
        "1h": "4h",
        "4h": "1d"
    }
    return mapping.get(tf)

# ============================================================
# MAIN SCAN ENGINE
# ============================================================

def run_market_scan():

    from app.services.config_service import get_runtime_config
    
    from app.db.session import SessionLocal

    runtime_cfg = get_runtime_config()

    TIMEFRAME = runtime_cfg["TIMEFRAME"]
    SCORE_THRESHOLD = runtime_cfg["SCORE_THRESHOLD"]
    TOP_LIMIT = runtime_cfg["TOP_LIMIT"]

    print(f"\n[{datetime.utcnow()}] Market scan starting...")

    # ✅ Evaluate open trades trước --- Đã có monitor riêng nên không cần nữa, chạy tại main mỗi 10s đected open trades liên tục
    #from app.services.trade_evaluator import evaluate_open_trades
    # evaluate_open_trades()

    db = SessionLocal()
    symbols = get_top_symbols(TOP_LIMIT)

    scan_stats = {
        "total_symbols": 0,
        "pattern_detected": 0,
        "score_reject": 0,
        "regime_blocked": 0,
        "duplicate_blocked": 0,
        "cooldown_blocked": 0,
        "ml_blocked": 0,
        "sent": 0
    }

    debug_rows = []

    for symbol in symbols:

        scan_stats["total_symbols"] += 1

        try:
            #print(f"\nProcessing {symbol}...")

            df = get_klines(symbol)
            if df.empty or len(df) < 200:
                continue
            
            # v2 
            # df = add_indicators(df)

            # calculate_score v3
            df = add_indicators_advanced(
                df,
                ema_period=200,
                rsi_period=14,
                atr_period=14,
                volume_ma_period=20
            )

            pattern = detect_pattern(df)
            if not pattern:
                continue

            scan_stats["pattern_detected"] += 1

            # ======================================
            # ✅ SCORE (đã bao gồm strict penalty)
            # ======================================

            score, direction, components = calculate_score(
                df, pattern, runtime_cfg, symbol
            )

            # Debug log
            debug_rows.append({
                "symbol": symbol,
                "pattern": pattern,
                "trend": components.get("trend_score"),
                "momentum": components.get("momentum_score"),
                "volume": components.get("volume_score"),
                "pattern_score": components.get("pattern_score"),
                "mtf": components.get("mtf_score"),
                "penalty": components.get("strict_penalty"),
                "total_score": score,
                "passed_score": score >= SCORE_THRESHOLD,
                "block_reason": components.get("block_reason")
            })

            # ======================================
            # ✅ HARD REJECT nếu penalty quá nặng
            # ======================================

            if components.get("strict_penalty", 0) <= -5:
                debug_rows[-1]["block_reason"] = "strict_heavy_penalty"
                scan_stats["score_reject"] += 1
                continue

            # ======================================
            # ✅ SCORE THRESHOLD
            # ======================================

            if score < SCORE_THRESHOLD:
                debug_rows[-1]["block_reason"] = "score_threshold"
                scan_stats["score_reject"] += 1
                continue

            #print(f"[PASSED SCORE] {symbol} score={score}")

            # ======================================
            # ✅ REGIME FILTER
            # ======================================

            regime = detect_regime_advanced(
                df,
                method="hybrid",
                lookback=10,
                threshold=0.002
            )

            if regime == "BULL" and direction != "LONG":
                scan_stats["regime_blocked"] += 1
                continue

            if regime == "BEAR" and direction != "SHORT":
                scan_stats["regime_blocked"] += 1
                continue

            # ======================================
            # ✅ OPEN TRADE CHECK
            # ======================================

            existing_open = db.query(Signal).filter(
                Signal.symbol == symbol,
                Signal.timeframe == TIMEFRAME,
                Signal.status == "OPEN"
            ).first()

            if existing_open:
                scan_stats["cooldown_blocked"] += 1
                continue

            last = df.iloc[-2]
            candle_time = last["time"].to_pydatetime()

            # Duplicate check
            if is_duplicate(db, symbol, TIMEFRAME, candle_time):
                scan_stats["duplicate_blocked"] += 1
                continue

            # Cooldown check
            if in_cooldown(db, symbol, TIMEFRAME, hours=runtime_cfg["COOLDOWN_HOURS"]):
                scan_stats["cooldown_blocked"] += 1
                continue

            # ======================================
            # ✅ ML FILTER
            # ======================================

            # mới sửa lại lỗi truyền nhầm score
            features = build_features_from_row(last, components, direction)
            prob = predict_prob(features)

            if prob is not None and prob < runtime_cfg["AI_THRESHOLD"]:
                scan_stats["ml_blocked"] += 1
                continue

            # ======================================
            # ✅ RISK MODEL
            # ======================================

            entry = float(last["close"])
            atr = float(last["atr"])

            if direction == "LONG":
                sl = entry - atr * 1.5
                tp = entry + atr * 3
            else:
                sl = entry + atr * 1.5
                tp = entry - atr * 3

            

            #print(f"[READY TO CREATE SIGNAL] {symbol}")
            # ================= COMMON VALUES =================
            close_price = last.get("close")
            ema200 = last.get("ema200")
            atr = last.get("atr")

            # ================= RR =================
            rr = None
            if entry != sl:
                rr = abs((tp - entry) / (entry - sl))

            # ================= EMA DISTANCE =================
            ema_distance = None
            if ema200 is not None and close_price is not None and ema200 != 0:
                ema_distance = float((close_price - ema200) / ema200)

            # ================= ATR RATIO =================
            atr_ratio = None
            if atr is not None and close_price is not None and close_price != 0:
                atr_ratio = float(atr / close_price)
            # ======================================
            # ✅ CREATE SIGNAL
            # ======================================

            signal = Signal(
                symbol=symbol,
                timeframe=TIMEFRAME,
                pattern=pattern,
                direction=direction,
                score=float(score),
                entry_price=float(entry),
                stop_loss=float(sl),
                take_profit=float(tp),
                rsi=float(last["rsi"]) if last.get("rsi") is not None else None,
                volume_ratio=float(last["volume"] / last["vol_ma"])
                    if last.get("vol_ma") and last["vol_ma"] > 0 else None,
                atr_ratio=atr_ratio,
                regime=regime,
                candle_time=candle_time
            )

            db.add(signal)
            db.commit()
            db.refresh(signal)

            from app.db.models import SignalFeature

            feature = SignalFeature(
                signal_id=signal.id,

                rsi=float(last["rsi"]) if last.get("rsi") is not None else None,
                volume_ratio=float(last["volume"] / last["vol_ma"])
                    if last.get("vol_ma") and last["vol_ma"] > 0 else None,
                atr_ratio=atr_ratio,
                regime=regime,

                trend_score=float(components.get("trend_score", 0)),
                momentum_score=float(components.get("momentum_score", 0)),
                volume_score=float(components.get("volume_score", 0)),
                ema_distance=ema_distance,
                pattern_score=float(components.get("pattern_score", 0)),
                mtf_score=float(components.get("mtf_score", 0)),
                total_score=float(score),

                strict_penalty=float(components.get("strict_penalty", 0)),

                rr=float(rr) if rr is not None else None
            )

            db.add(feature)
            db.commit()

            #print(f"[FEATURE CREATED] signal_id={signal.id}")

            scan_stats["sent"] += 1

            # ======================================
            # ✅ TELEGRAM MESSAGE
            # ======================================

            prob_text = f"{prob:.2f}" if prob is not None else "N/A"
            local_time = to_local_time(candle_time)

            message = (
                f"🚨 <b>SIGNAL ALERT</b>\n\n"
                f"<b>Symbol:</b> {symbol}\n"
                f"<b>Pattern:</b> {pattern}\n"
                f"<b>Direction:</b> {direction}\n"
                f"<b>Regime:</b> {regime}\n"
                f"<b>Score:</b> {score}\n"
                f"<b>AI Prob:</b> {prob_text}\n\n"
                f"<b>Entry:</b> {entry:.4f}\n"
                f"<b>Stop Loss:</b> {sl:.4f}\n"
                f"<b>Take Profit:</b> {tp:.4f}\n"
                f"<b>RR:</b> {rr:.2f}\n\n"
                f"<b>Candle Time (GMT+7):</b> {local_time}"
            )

            send_telegram(message)

            print(f"✅ SENT: {symbol} | {pattern} | {direction}")

        except Exception as e:
            db.rollback()
            print(f"❌ Error {symbol}: {type(e).__name__} - {e}")

    db.close()

    # ======================================
    # ✅ DEBUG DASHBOARD
    # ======================================

    print("\n===== DEBUG DASHBOARD =====")

    for row in sorted(debug_rows, key=lambda x: x.get("total_score") or 0, reverse=True):

        total = row.get("total_score")
        bar = score_bar(total)

        print(
            f"{row['symbol']:<10} "
            f"{row.get('pattern',''):<15} "
            f"T={row.get('trend')} "
            f"M={row.get('momentum')} "
            f"V={row.get('volume')} "
            f"P={row.get('pattern_score')} "
            f"MTF={row.get('mtf')} "
            f"PEN={row.get('penalty')} | "
            f"{color_score(total)} {bar} | "
            f"BLOCK={row.get('block_reason')}"
        )

    print("=================================\n")

    # ======================================
    # 📊 PHÂN TÍCH PHÂN PHỐI ĐIỂM (PERCENTILES)
    # ======================================
    
    
    # Trích xuất list điểm từ debug_rows
    valid_scores = [row.get("total_score") for row in debug_rows if row.get("total_score") is not None]

    if valid_scores:
        print("\n📊 SCORE DISTRIBUTION ANALYSIS:")
        print(f"Total Signals Evaluated: {len(valid_scores)}")
        print(f"Min: {min(valid_scores):.2f} | Max: {max(valid_scores):.2f} | Avg: {sum(valid_scores)/len(valid_scores):.2f}")
        print("\n🎯 Gợi ý đặt SCORE_THRESHOLD trong DB:")
        for p in [50, 70, 80, 90, 95]:
            threshold_val = np.percentile(valid_scores, p)
            print(f"- Nếu muốn lấy Top {100-p}% tín hiệu đẹp nhất -> Đặt SCORE_THRESHOLD = {threshold_val:.2f}")
    else:
        print("\n⚠️ Không có signal nào được tính điểm.")
    
    # ======================================
    # 📊 In các chỉ số ra để debug
    # ======================================

    print("\n===== RUNTIME FILTER CONFIG =====")
    for k, v in runtime_cfg.items():
        print(f"{k}: {v}")
    print("=================================\n")

    print("\n=== SCAN SUMMARY ===")
    for k, v in scan_stats.items():
        print(f"{k}: {v}")

    return scan_stats

def score_bar(score, max_score=10, width=10):
    if score is None:
        return ""
    filled = int((score / max_score) * width)
    return "█" * filled + "░" * (width - filled)

def color_score(score):
    if score is None:
        return ""
    if score >= 8:
        return f"\033[92m{score}\033[0m"  # xanh lá
    elif score >= 6:
        return f"\033[93m{score}\033[0m"  # vàng
    else:
        return f"\033[91m{score}\033[0m"  # đỏ
    
def run_market_scan_multi_tf():

    from datetime import datetime
    from app.services.config_service import get_runtime_config
    from app.db.session import SessionLocal

    runtime_cfg = get_runtime_config()
    db = SessionLocal()

    now = datetime.utcnow()

    # ✅ 15m candle đóng tại 01,16,31,46
    if now.minute in [1, 16, 31, 46]:
        scan_timeframe(db, "15m", runtime_cfg)

    # ✅ 1h candle đóng tại phút 00 → delay 3 phút → quét phút 03
    if now.minute == 5:
        scan_timeframe(db, "1h", runtime_cfg)

    # ✅ 4h candle đóng tại giờ %4==0 phút 00 → delay 5 phút → quét phút 05
    if now.minute == 7 and now.hour % 4 == 0:
        scan_timeframe(db, "4h", runtime_cfg)

    db.close()

def run_market_scan_single_tf(timeframe):

    from app.services.config_service import get_runtime_config
    from app.db.session import SessionLocal

    runtime_cfg = get_runtime_config()
    db = SessionLocal()

    print(f"\n🚀 Running SINGLE TF scan: {timeframe}")

    result = scan_timeframe(db, timeframe, runtime_cfg)

    db.close()

    return result

def scan_timeframe(db, timeframe, runtime_cfg):

    symbols = get_top_symbols(runtime_cfg["TOP_LIMIT"])
    SCORE_THRESHOLD = runtime_cfg["SCORE_THRESHOLD"]

    scan_stats = {
        "timeframe": timeframe,
        "total_symbols": 0,
        "pattern_detected": 0,
        "score_reject": 0,
        "regime_blocked": 0,
        "duplicate_blocked": 0,
        "cooldown_blocked": 0,
        "ml_blocked": 0,
        "sent": 0
    }

    debug_rows = []

    print(f"\n🔄 ===== SCAN {timeframe} =====")

    for symbol in symbols:

        scan_stats["total_symbols"] += 1

        try:

            df = get_klines(symbol, interval=timeframe)
            if df.empty or len(df) < 200:
                continue

            df = add_indicators_advanced(
                df,
                ema_period=200,
                rsi_period=14,
                atr_period=14,
                volume_ma_period=20
            )

            pattern = detect_pattern(df)
            if not pattern:
                continue

            scan_stats["pattern_detected"] += 1

            score, direction, components = calculate_score(
                df, pattern, runtime_cfg, symbol, timeframe
            )

            debug_rows.append({
                "symbol": symbol,
                "pattern": pattern,
                "trend": components.get("trend_score"),
                "momentum": components.get("momentum_score"),
                "volume": components.get("volume_score"),
                "pattern_score": components.get("pattern_score"),
                "mtf": components.get("mtf_score"),
                "penalty": components.get("strict_penalty"),
                "total_score": score,
                "passed_score": score >= SCORE_THRESHOLD,
                "block_reason": None
            })

            if score < SCORE_THRESHOLD:
                debug_rows[-1]["block_reason"] = "score_threshold"
                scan_stats["score_reject"] += 1
                continue

            regime = detect_regime_advanced(
                df,
                method="hybrid",
                lookback=10,
                threshold=0.002
            )

            if regime == "BULL" and direction != "LONG":
                scan_stats["regime_blocked"] += 1
                continue

            if regime == "BEAR" and direction != "SHORT":
                scan_stats["regime_blocked"] += 1
                continue

            existing_open = db.query(Signal).filter(
                Signal.symbol == symbol,
                Signal.timeframe == timeframe,
                Signal.status == "OPEN"
            ).first()

            if existing_open:
                scan_stats["cooldown_blocked"] += 1
                continue

            last = df.iloc[-2]
            candle_time = last["time"].to_pydatetime()

            if is_duplicate(db, symbol, timeframe, candle_time):
                scan_stats["duplicate_blocked"] += 1
                continue

            if in_cooldown(db, symbol, timeframe, hours=runtime_cfg["COOLDOWN_HOURS"]):
                scan_stats["cooldown_blocked"] += 1
                continue

            features = build_features_from_row(last, components, direction)
            prob = predict_prob(features)

            if prob is not None and prob < runtime_cfg["AI_THRESHOLD"]:
                scan_stats["ml_blocked"] += 1
                continue

            # ✅ Risk model từ DB config
            entry = float(last["close"])
            atr = float(last["atr"])

            risk_cfg = runtime_cfg.get("RISK_CONFIG", {}).get(
                timeframe,
                {"sl_mult": 1.5, "tp_mult": 3}
            )

            sl_mult = risk_cfg["sl_mult"]
            tp_mult = risk_cfg["tp_mult"]

            if direction == "LONG":
                sl = entry - atr * sl_mult
                tp = entry + atr * tp_mult
            else:
                sl = entry + atr * sl_mult
                tp = entry - atr * tp_mult

            # ======================================
            # ✅ CREATE SIGNAL
            # ======================================

             # ================= COMMON VALUES =================
            close_price = last.get("close")
            ema200 = last.get("ema200")
            atr = last.get("atr")

            # ================= RR =================
            rr = None
            if entry != sl:
                rr = abs((tp - entry) / (entry - sl))

            # ================= EMA DISTANCE =================
            ema_distance = None
            if ema200 is not None and close_price is not None and ema200 != 0:
                ema_distance = float((close_price - ema200) / ema200)

            # ================= ATR RATIO =================
            atr_ratio = None
            if atr is not None and close_price is not None and close_price != 0:
                atr_ratio = float(atr / close_price)

            signal = Signal(
                symbol=symbol,
                timeframe=timeframe,
                pattern=pattern,
                direction=direction,
                score=float(score),
                entry_price=float(entry),
                stop_loss=float(sl),
                take_profit=float(tp),
                rsi=float(last["rsi"]) if last.get("rsi") is not None else None,
                volume_ratio=float(last["volume"] / last["vol_ma"])
                    if last.get("vol_ma") and last["vol_ma"] > 0 else None,
                atr_ratio=atr_ratio,
                regime=regime,
                candle_time=candle_time
            )

            db.add(signal)
            db.commit()
            db.refresh(signal)

            from app.db.models import SignalFeature

            feature = SignalFeature(
                signal_id=signal.id,

                rsi=float(last["rsi"]) if last.get("rsi") is not None else None,
                volume_ratio=float(last["volume"] / last["vol_ma"])
                    if last.get("vol_ma") and last["vol_ma"] > 0 else None,
                atr_ratio=atr_ratio,
                regime=regime,

                trend_score=float(components.get("trend_score", 0)),
                momentum_score=float(components.get("momentum_score", 0)),
                volume_score=float(components.get("volume_score", 0)),
                ema_distance=ema_distance,
                pattern_score=float(components.get("pattern_score", 0)),
                mtf_score=float(components.get("mtf_score", 0)),
                total_score=float(score),

                strict_penalty=float(components.get("strict_penalty", 0)),

                rr=float(rr) if rr is not None else None
            )

            db.add(feature)
            db.commit()

            scan_stats["sent"] += 1

            # ======================================
            # ✅ TELEGRAM MESSAGE
            # ======================================

            prob_text = f"{prob:.2f}" if prob is not None else "N/A"
            local_time = to_local_time(candle_time)

            message = (
                f"🚨 <b>SIGNAL ALERT</b>\n\n"
                f"<b>Symbol:</b> {symbol}\n"
                f"<b>Pattern:</b> {pattern}\n"
                f"<b>Direction:</b> {direction}\n"
                f"<b>Regime:</b> {regime}\n"
                f"<b>Score:</b> {score}\n"
                f"<b>AI Prob:</b> {prob_text}\n\n"
                f"<b>Entry:</b> {entry:.4f}\n"
                f"<b>Stop Loss:</b> {sl:.4f}\n"
                f"<b>Take Profit:</b> {tp:.4f}\n"
                f"<b>RR:</b> {rr:.2f}\n\n"
                f"<b>Candle Time (GMT+7):</b> {local_time}"
            )

            send_telegram(message)

            print(f"✅ SENT: {symbol} | {pattern} | {direction}")

        except Exception as e:
            db.rollback()
            print(f"❌ Error {symbol}: {type(e).__name__} - {e}")

    db.close()

    # ================= DEBUG OUTPUT =================

    print("\n===== DEBUG DASHBOARD =====")

    for row in sorted(debug_rows, key=lambda x: x.get("total_score") or 0, reverse=True):

        total = row.get("total_score")
        bar = score_bar(total)

        print(
            f"{row['symbol']:<10} "
            f"{row.get('pattern',''):<15} "
            f"T={row.get('trend')} "
            f"M={row.get('momentum')} "
            f"V={row.get('volume')} "
            f"P={row.get('pattern_score')} "
            f"MTF={row.get('mtf')} "
            f"PEN={row.get('penalty')} | "
            f"{color_score(total)} {bar} | "
            f"BLOCK={row.get('block_reason')}"
        )

    print("=================================\n")

    # ================= SCORE DISTRIBUTION =================

    valid_scores = [row["total_score"] for row in debug_rows if row.get("total_score")]

    if valid_scores:
        print(f"\n📊 SCORE DISTRIBUTION ANALYSIS ({timeframe})")
        print(f"Min: {min(valid_scores):.2f} | "
              f"Max: {max(valid_scores):.2f} | "
              f"Avg: {sum(valid_scores)/len(valid_scores):.2f}")
        print("\n🎯 Gợi ý đặt SCORE_THRESHOLD trong DB:")
        for p in [50, 70, 80, 90, 95]:
            threshold_val = np.percentile(valid_scores, p)
            print(f"- Nếu muốn lấy Top {100-p}% tín hiệu đẹp nhất -> Đặt SCORE_THRESHOLD = {threshold_val:.2f}")
    else:
        print("\n⚠️ Không có signal nào được tính điểm.")
        
    # ======================================
    # 📊 In các chỉ số ra để debug
    # ======================================

    print("\n===== RUNTIME FILTER CONFIG =====")
    for k, v in runtime_cfg.items():
        print(f"{k}: {v}")
    print("=================================\n")

    print("\n=== SCAN SUMMARY ===")
    for k, v in scan_stats.items():
        print(f"{k}: {v}")

    return scan_stats