import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import time

from app.services.binance_service import get_top_symbols, get_klines
from app.services.indicator_service import add_indicators, add_indicators_advanced, detect_regime, detect_regime_advanced, get_market_state
from app.services.pattern_service import detect_pattern
from app.services.telegram_service import send_telegram

from app.db.session import SessionLocal
from app.db.models import Signal

from app.ml.predict import predict_prob
from app.ml.features import build_features_from_row
from app.services.llm_router import generate_explanation
from app.db.models import SignalFeature


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

    BATCH_SIZE = 100
    BATCH_SLEEP = 1

    scan_stats = {
        "timeframe": timeframe,
        "total_symbols": 0,
        "pattern_detected": 0,
        "score_reject": 0,
        "regime_blocked": 0,
        "duplicate_blocked": 0,
        "cooldown_blocked": 0,
        "ml_blocked": 0,
        "open_signal_blocked":0,
        "sent": 0
    }

    debug_rows = []

    print(f"\n🔄 ===== SCAN {timeframe} | Time: {get_hanoi_time()} =====")

    # ✅ HTF cache
    htf_cache = {}

    for i in range(0, len(symbols), BATCH_SIZE):

        batch = symbols[i:i+BATCH_SIZE]

        for symbol in batch:

            scan_stats["total_symbols"] += 1

            try:

                # ================= PRIMARY TF =================
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

                # ================= REGIME =================
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

                # ================= OPEN CHECK =================
                existing_open = db.query(Signal).filter(
                    Signal.symbol == symbol,
                    Signal.timeframe == timeframe,
                    Signal.status == "OPEN"
                ).first()

                if existing_open:
                    scan_stats["open_signal_blocked"] += 1
                    debug_rows[-1]["block_reason"] = "open_signal"
                    continue

                last = df.iloc[-2]
                candle_time = last["time"].to_pydatetime()

                if is_duplicate(db, symbol, timeframe, candle_time):
                    scan_stats["duplicate_blocked"] += 1
                    debug_rows[-1]["block_reason"] = "duplicate"
                    continue

                if in_cooldown(db, symbol, timeframe, hours=runtime_cfg["COOLDOWN_HOURS"]):
                    scan_stats["cooldown_blocked"] += 1
                    debug_rows[-1]["block_reason"] = "cooldown"
                    continue

                # ================= ML =================
                features = build_features_from_row(last, components, direction)
                prob = predict_prob(features)

                if prob is not None and prob < runtime_cfg["AI_THRESHOLD"]:
                    scan_stats["ml_blocked"] += 1
                    continue

                # ================= RISK =================
                entry = float(last["close"])
                atr_val = float(last["atr"])

                risk_cfg = runtime_cfg.get("RISK_CONFIG", {}).get(
                    timeframe,
                    {"sl_mult": 1.5, "tp_mult": 3}
                )

                sl_mult = risk_cfg["sl_mult"]
                tp_mult = risk_cfg["tp_mult"]

                if direction == "LONG":
                    sl = entry - atr_val * sl_mult
                    tp = entry + atr_val * tp_mult
                else:
                    sl = entry + atr_val * sl_mult
                    tp = entry - atr_val * tp_mult

                # ================= ENTRY SNAPSHOT =================
                rr = None
                if entry != sl:
                    rr = abs((tp - entry) / (entry - sl))

                ema_distance = None
                ema200 = last.get("ema200")
                close_price = last.get("close")

                if ema200 is not None and close_price is not None and ema200 != 0:
                    ema_distance = (close_price - ema200) / ema200

                atr_ratio = None
                if last.get("atr") and close_price and close_price != 0:
                    atr_ratio = last["atr"] / close_price

                # ================= CREATE SIGNAL =================
                signal = Signal(
                    symbol=symbol,
                    timeframe=timeframe,
                    pattern=pattern,
                    direction=direction,
                    score=float(score),
                    entry_price=entry,
                    stop_loss=sl,
                    take_profit=tp,
                    rsi=float(last["rsi"]) if last.get("rsi") is not None else None,
                    volume_ratio=float(last["volume"] / last["vol_ma"])
                        if last.get("vol_ma") and last["vol_ma"] > 0 else None,
                    atr_ratio=atr_ratio,
                    regime=regime,
                    candle_time=candle_time
                )

                db.add(signal)
                db.flush()

                
                feature = SignalFeature(
                    signal_id=signal.id,
                    rsi=float(last["rsi"]) if last.get("rsi") is not None else None,
                    volume_ratio=float(last["volume"] / last["vol_ma"])
                        if last.get("vol_ma") and last["vol_ma"] > 0 else None,
                    atr_ratio=atr_ratio,
                    regime=regime,
                    trend_score=components.get("trend_score"),
                    momentum_score=components.get("momentum_score"),
                    volume_score=components.get("volume_score"),
                    ema_distance=ema_distance,
                    pattern_score=components.get("pattern_score"),
                    mtf_score=components.get("mtf_score"),
                    total_score=score,
                    strict_penalty=components.get("strict_penalty"),
                    rr=rr
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

        # ✅ nghỉ giữa batch tránh burst
        time.sleep(BATCH_SLEEP)
    db.close()

    # ── Header
    print("\n===== DEBUG DASHBOARD =====")
    print(
        f"{'Symbol':<12}"
        f"{'Pattern':<22}"
        f"{'T':>3}"
        f"{'M':>4}"
        f"{'V':>5}"
        f"{'P':>6}"
        f"{'MTF':>5}"
        f"{'PEN':>5}"
        f"{'Score':>7}"
        f"  {'Bar':<12}"
        f"  Block Reason"
    )
    print("─" * 105)

    # ── Rows
    BLOCK_EMOJI = {
        "score_threshold":  "📉 score_low",
        "regime_mismatch":  "🌊 regime",
        "open_signal":      "🔒 open_signal",
        "duplicate":        "♻️  duplicate",
        "cooldown":         "⏳ cooldown",
        "ml_threshold":     "🤖 ml_prob",
        None:               "✅ PASSED",
    }

    for row in sorted(debug_rows, key=lambda x: x.get("total_score") or 0, reverse=True):

        total        = row.get("total_score")
        bar          = score_bar(total)
        reason_raw   = row.get("block_reason")
        reason_label = BLOCK_EMOJI.get(reason_raw, str(reason_raw))

        print(
            f"{str(row.get('symbol',  '')):<12}"
            f"{str(row.get('pattern', '')):<22}"
            f"{fmt(row.get('trend'),          3, decimals=0)}"   # int → no decimal
            f"{fmt(row.get('momentum'),       4, decimals=1)}"   # 0 → 2.0
            f"{fmt(row.get('volume'),         5, decimals=2)}"   # 2 decimal
            f"{fmt(row.get('pattern_score'),  6, decimals=2)}"   # 2 decimal
            f"{fmt(row.get('mtf'),            5, decimals=2)}"   # 2 decimal
            f"{fmt(row.get('penalty'),        5, decimals=1)}"   # 1 decimal
            f"{fmt(total,                     7, decimals=2)}"   # score
            f"  {bar:<12}"
            f"  {reason_label}"
        )

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

    # ================= SCAN SUMMARY =================
    total = scan_stats["total_symbols"]
    passed = scan_stats["sent"]

    # Tính tỷ lệ filter từng loại
    def pct(n, total):
        return f"{n/total*100:.1f}%" if total > 0 else "0%"

    print("\n" + "=" * 45)
    print(f"📊 SCAN SUMMARY [{timeframe}]")
    print("=" * 45)
    print(f"  🔍 Total symbols scanned : {total}")
    print(f"  🕯️  Pattern detected       : {scan_stats['pattern_detected']} ({pct(scan_stats['pattern_detected'], total)})")
    print("-" * 45)
    print("  Filtered out:")
    print(f"  📉 Score too low          : {scan_stats['score_reject']}        ({pct(scan_stats['score_reject'], total)})")
    print(f"  🌊 Regime mismatch        : {scan_stats['regime_blocked']}        ({pct(scan_stats['regime_blocked'], total)})")
    print(f"  🔒 Has open signal        : {scan_stats['open_signal_blocked']}        ({pct(scan_stats['open_signal_blocked'], total)})")  # ← NEW
    print(f"  ♻️  Duplicate candle       : {scan_stats['duplicate_blocked']}        ({pct(scan_stats['duplicate_blocked'], total)})")
    print(f"  ⏳ Cooldown active        : {scan_stats['cooldown_blocked']}        ({pct(scan_stats['cooldown_blocked'], total)})")
    print(f"  🤖 ML prob too low        : {scan_stats['ml_blocked']}        ({pct(scan_stats['ml_blocked'], total)})")
    print("-" * 45)
    print(f"  ✅ Signal sent            : {passed}        ({pct(passed, total)})")
    print("=" * 45)

    # ⚠️ Cảnh báo bất thường
    if scan_stats["open_signal_blocked"] > 20:
        print(f"\n⚠️  WARNING: {scan_stats['open_signal_blocked']} symbols bị block vì open signal")
        print("   → Xem xét giảm COOLDOWN_HOURS hoặc tăng tốc close lệnh cũ")

    if scan_stats["cooldown_blocked"] > scan_stats["sent"] * 3:
        print(f"\n⚠️  WARNING: Cooldown block ({scan_stats['cooldown_blocked']}) cao hơn sent ({scan_stats['sent']}) x3")
        print("   → Xem xét giảm COOLDOWN_HOURS")

    if scan_stats["ml_blocked"] > scan_stats["pattern_detected"] * 0.5:
        print(f"\n⚠️  WARNING: ML block {scan_stats['ml_blocked']}/{scan_stats['pattern_detected']} patterns")
        print("   → Model đang filter quá aggressive, kiểm tra AI_THRESHOLD")


# ── Helper format cell gọn
def fmt(val, width, decimals=2):
    """
    Format một giá trị thành string cố định width.
    - None / ""  → dấu '-'
    - int        → không decimal
    - float      → làm tròn `decimals` chữ số
    """
    if val is None or val == "":
        return f"{'─':>{width}}"
    try:
        f = float(val)
        if f == int(f) and decimals == 0:
            s = str(int(f))
        else:
            s = f"{f:.{decimals}f}"
    except (TypeError, ValueError):
        s = str(val)
    # Cắt nếu vẫn dài hơn width (tránh lệch)
    if len(s) > width:
        s = s[:width]
    return f"{s:>{width}}"

def get_hanoi_time():
    return datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d %H:%M:%S")