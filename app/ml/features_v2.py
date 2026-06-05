import pandas as pd

def build_features_from_row(row, score, direction):
    return [
        float(row["rsi"]) if not pd.isna(row["rsi"]) else 50,
        float(row["volume"]) / float(row["vol_ma"]) if row.get("vol_ma") and row["vol_ma"] > 0 else 1,
        float(score),
        1 if direction == "LONG" else 0
    ]