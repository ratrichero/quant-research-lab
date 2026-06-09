from datetime import datetime, timedelta
from sqlalchemy import and_
from app.db.session import SessionLocal
from app.db.models import PendingSignal, Signal, SignalFeature, ScanDebug
from app.services.binance_service import get_all_prices
from app.services.telegram_service import send_telegram
from app.services.signal_service import to_local_time



def process_pending_signals():

    with SessionLocal() as db:
        now = datetime.utcnow()

        # ============================================================
        # STEP 1: BATCH EXPIRE
        # ============================================================

        expired_count = db.query(PendingSignal).filter(
            PendingSignal.status == "WAIT",
            PendingSignal.expire_at < now
        ).update({
            "status": "CANCELLED"
        }, synchronize_session=False)

        if expired_count > 0:
            db.commit()

        # ============================================================
        # STEP 2: LẤY PENDING CÒN HIỆU LỰC
        # ============================================================

        pendings = db.query(PendingSignal).filter(
            PendingSignal.status == "WAIT"
        ).all()

        if not pendings:
            return

        # ============================================================
        # STEP 3: LẤY TẤT CẢ GIÁ 1 LẦN DUY NHẤT
        # ============================================================

        price_map = get_all_prices()

        if not price_map:
            return

        # ============================================================
        # STEP 4: CHECK FILL CHO TỪNG PENDING
        # ============================================================

        for p in pendings:

            try:
                # ================= PRICE CHECK =================
                current_price = price_map.get(p.symbol)

                if not current_price:
                    continue

                should_fill = False

                if p.direction == "LONG" and current_price <= p.trigger_price:
                    should_fill = True

                if p.direction == "SHORT" and current_price >= p.trigger_price:
                    should_fill = True

                if not should_fill:
                    continue

                # ================= SAFE UPDATE =================
                updated = db.query(PendingSignal).filter(
                    and_(
                        PendingSignal.id == p.id,
                        PendingSignal.status == "WAIT"
                    )
                ).update({
                    "status": "FILLED",
                    "filled_at": now
                })

                if updated == 0:
                    continue

                # ================= CREATE SIGNAL =================
                signal = Signal(
                    symbol=p.symbol,
                    timeframe=p.timeframe,
                    pattern=p.pattern,
                    strategy_name=p.strategy_name,
                    direction=p.direction,
                    score=p.signal_score,
                    entry_price=p.trigger_price,
                    stop_loss=p.stop_loss,
                    take_profit=p.take_profit,
                    rsi=p.indicators_snapshot.get("rsi") if p.indicators_snapshot else None,
                    volume_ratio=p.indicators_snapshot.get("volume_ratio") if p.indicators_snapshot else None,
                    atr_ratio=p.indicators_snapshot.get("atr_ratio") if p.indicators_snapshot else None,
                    regime=p.regime,
                    candle_time=p.candle_time,
                    engine_version= p.indicators_snapshot.get("engine_version")
                )

                db.add(signal)
                db.flush()

                # ================= CREATE SIGNAL FEATURE =================
                feature = SignalFeature(
                    signal_id=signal.id,
                    rsi=p.indicators_snapshot.get("rsi") if p.indicators_snapshot else None,
                    volume_ratio=p.indicators_snapshot.get("volume_ratio") if p.indicators_snapshot else None,
                    atr_ratio=p.indicators_snapshot.get("atr_ratio") if p.indicators_snapshot else None,
                    regime=p.regime,
                    trend_score=p.trend_score,
                    momentum_score=p.momentum_score,
                    volume_score=p.volume_score,
                    ema_distance=p.indicators_snapshot.get("ema_distance"),
                    pattern_score=p.pattern_score,
                    mtf_score=p.mtf_score,
                    total_score=p.signal_score,
                    penalty_norm=p.penalty,
                    rr=p.rr
                )

                db.add(feature)

                # ================= LINK DEBUG =================
                if p.scan_debug_id:
                    debug = db.query(ScanDebug).get(p.scan_debug_id)
                    if debug:
                        debug.signal_id = signal.id

                db.commit()

                # ================= TELEGRAM =================
                prob = p.ml_prob
                prob_text = f"{prob:.2f}" if prob is not None else "N/A"
                rr_text = f"{p.rr:.2f}" if p.rr is not None else "N/A"

                duration_map = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}
                minutes = duration_map.get(p.timeframe, 15)
                close_time = p.candle_time + timedelta(minutes=minutes)
                local_time = to_local_time(close_time)

                tf_icon = {"15m": "⚡", "1h": "🕐", "4h": "🕓", "1d": "📅"}.get(p.timeframe, "🕒")
                confidence_tag = " 🔥 HIGH CONF" if (prob is not None and prob >= 0.7) else ""
                score_tag = " 🌟" if (p.signal_score is not None and p.signal_score >= 8) else ""

                message = (
                    f"🚨 <b>SIGNAL ALERT</b>{score_tag}\n\n"
                    f"<b>Symbol:</b> {p.symbol}\n"
                    f"<b>Timeframe:</b> {p.timeframe} {tf_icon}\n"
                    f"<b>Pattern:</b> {p.pattern}\n"
                    f"<b>Direction:</b> {p.direction}\n"
                    f"<b>Regime:</b> {p.regime}\n"
                    f"<b>Score:</b> {p.signal_score}\n"
                    f"<b>Entry:</b> {p.trigger_price:.4f}\n"
                    f"<b>Stop Loss:</b> {p.stop_loss:.4f}\n"
                    f"<b>Take Profit:</b> {p.take_profit:.4f}\n"
                    f"<b>RR:</b> {rr_text}\n\n"
                    f"<b>Candle Close (GMT+7):</b> {local_time.strftime('%Y-%m-%d %H:%M:%S')}"
                )

                send_telegram(message)
                print(f"✅ PENDING FILLED: {p.symbol} | {p.trigger_price:.4f} | {p.pattern} | {p.direction} | Score={p.signal_score}")

            except Exception as e:
                db.rollback()
                print(f"❌ Error pending {p.id}: {type(e).__name__} - {e}")
                continue