import pandas as pd
import numpy as np
from sqlalchemy import create_engine

from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

import shap
import matplotlib.pyplot as plt


# ===============================
# CONFIG
# ===============================

DATABASE_URL = "postgresql://postgres.oppqzyulpqeggcmpeajp:Dotask%4024h365@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres"

FEATURES = [
    "trend_score",
    "momentum_score",
    "volume_score",
    "pattern_score",
    "mtf_score",
    "penalty_norm"
]

engine = create_engine(DATABASE_URL)


# ===============================
# LOAD DATA
# ===============================

query = """
SELECT
    sf.trend_score,
    sf.momentum_score,
    sf.volume_score,
    sf.pattern_score,
    sf.mtf_score,
    sf.strict_penalty AS penalty_norm,
    s.result_percent,
    CASE WHEN s.status = 'WIN' THEN 1 ELSE 0 END AS win_label
FROM signal_features sf
JOIN signals s ON s.id = sf.signal_id
WHERE s.status IN ('WIN','LOSS')
"""

df = pd.read_sql(query, engine)

if len(df) < 100:
    print("⚠️ Warning: Too few trades for reliable ML analysis")

X = df[FEATURES]
y = df["win_label"]


# ===============================
# 1️⃣ RANDOM FOREST IMPORTANCE
# ===============================

rf = RandomForestClassifier(
    n_estimators=300,
    max_depth=6,
    random_state=42
)

rf.fit(X, y)

rf_importance = pd.Series(
    rf.feature_importances_,
    index=FEATURES
).sort_values(ascending=False)

print("\n🌲 Random Forest Feature Importance:\n")
print(rf_importance)


# ===============================
# 2️⃣ SHAP ANALYSIS
# ===============================

print("\n🔍 Running SHAP analysis...")

explainer = shap.TreeExplainer(rf)
shap_values = explainer.shap_values(X)

shap.summary_plot(
    shap_values[1],
    X,
    show=False
)

plt.title("SHAP Summary Plot")
plt.tight_layout()
plt.savefig("shap_summary.png")
print("✅ SHAP plot saved as shap_summary.png")


# ===============================
# 3️⃣ LOGISTIC REGRESSION
# ===============================

log_model = Pipeline([
    ("scaler", StandardScaler()),
    ("logreg", LogisticRegression(max_iter=1000))
])

log_model.fit(X, y)

coefs = log_model.named_steps["logreg"].coef_[0]

log_importance = pd.Series(
    coefs,
    index=FEATURES
).sort_values(ascending=False)

print("\n📈 Logistic Regression Coefficients:\n")
print(log_importance)


# ===============================
# 4️⃣ AUTO WEIGHT OPTIMIZER
# ===============================

print("\n⚙️ Generating Optimized Weights...")

abs_coefs = np.abs(coefs)
normalized_weights = abs_coefs / abs_coefs.sum()

weight_dict = dict(zip(FEATURES, normalized_weights))

print("\n✅ Suggested Weight Distribution:\n")
for k, v in sorted(weight_dict.items(), key=lambda x: x[1], reverse=True):
    print(f"{k:20s}: {v:.3f}")


# ===============================
# 5️⃣ SAVE REPORT CSV
# ===============================

report = pd.DataFrame({
    "RandomForest": rf_importance,
    "LogisticCoeff": log_importance
})

report.to_csv("feature_importance_report.csv")

print("\n📁 feature_importance_report.csv saved.")