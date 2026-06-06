import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

# ✅ Cấu hình DB
DATABASE_URL = "postgresql://postgres.oppqzyulpqeggcmpeajp:Dotask%4024h365@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres"
engine = create_engine(DATABASE_URL)


# ─────────────────────────────────────────────
# 1️⃣ Load data
# ─────────────────────────────────────────────

query = """
SELECT
    sf.trend_score,
    sf.momentum_score,
    sf.volume_score,
    sf.pattern_score,
    sf.mtf_score,
    sf.strict_penalty AS penalty_norm,
    sf.total_score,
    sd.rule_score_raw,
    s.result_percent,
    CASE WHEN s.status = 'WIN' THEN 1 ELSE 0 END AS win_label
FROM signal_features sf
JOIN signals s ON s.id = sf.signal_id
LEFT JOIN scan_debug sd ON sd.signal_id = s.id
WHERE s.status IN ('WIN','LOSS')
"""

df = pd.read_sql(query, engine)

if df.empty:
    print("❌ No data found.")
    exit()


# ─────────────────────────────────────────────
# 2️⃣ Correlation analysis
# ─────────────────────────────────────────────

print("\n📊 Correlation with Result Percent:\n")

correlations = {}

for col in [
    "trend_score",
    "momentum_score",
    "volume_score",
    "pattern_score",
    "mtf_score",
    "penalty_norm",
    "rule_score_raw"
]:
    corr = df[col].corr(df["result_percent"])
    correlations[col] = corr

corr_df = (
    pd.Series(correlations)
    .sort_values(ascending=False)
    .to_frame(name="correlation")
)

print(corr_df)


# ─────────────────────────────────────────────
# 3️⃣ Logistic Regression Importance
# ─────────────────────────────────────────────

features = [
    "trend_score",
    "momentum_score",
    "volume_score",
    "pattern_score",
    "mtf_score",
    "penalty_norm"
]

X = df[features]
y = df["win_label"]

# Pipeline: scale + logistic
model = Pipeline([
    ("scaler", StandardScaler()),
    ("logreg", LogisticRegression(max_iter=1000))
])

model.fit(X, y)

coefs = model.named_steps["logreg"].coef_[0]

importance = pd.Series(
    coefs,
    index=features
).sort_values(ascending=False)

print("\n📈 Logistic Regression Feature Importance:\n")
print(importance)


# ─────────────────────────────────────────────
# 4️⃣ Ranking summary
# ─────────────────────────────────────────────

print("\n🏆 Feature Ranking:\n")

for i, (feature, value) in enumerate(importance.items(), start=1):
    print(f"{i}. {feature:20s}  coefficient={value:.4f}")