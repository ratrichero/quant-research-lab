import pandas as pd

def build_features_from_row(row, components, direction):

    # ===== NORMALIZED COMPONENTS =====
    trend_norm = components.get("trend_score", 0) / 3
    momentum_norm = components.get("momentum_score", 0) / 2
    volume_norm = components.get("volume_score", 0) / 2
    pattern_norm = components.get("pattern_score", 0) / 2
    mtf_norm = components.get("mtf_score", 0) / 1.75
    penalty_norm = components.get("strict_penalty", 0) / 1.5

    # ===== CONTEXT FEATURES =====
    ema_distance = row.get("ema_distance", 0) or 0

    atr_ratio = 0
    if row.get("atr") and row.get("close") and row["close"] != 0:
        atr_ratio = float(row["atr"]) / float(row["close"])

    bb_position = row.get("bb_position", 0) or 0

    regime_encoded = 1 if row.get("close", 0) > row.get("ema200", 0) else 0

    direction_encoded = 1 if direction == "LONG" else 0

    return [
        trend_norm,
        momentum_norm,
        volume_norm,
        pattern_norm,
        mtf_norm,
        penalty_norm,
        ema_distance,
        atr_ratio,
        bb_position,
        regime_encoded,
        direction_encoded
    ]