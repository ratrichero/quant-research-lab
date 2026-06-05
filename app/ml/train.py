import joblib
import numpy as np
import xgboost as xgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import roc_auc_score
from app.db.session import SessionLocal
from app.db.models import SignalFeature, TradeOutcomeAnalytics

MODEL_PATH = "app/ml/model.pkl"


def build_features(feature_row):
    """
    Feature vector v3 (ML-first)
    """

    return [
        float(feature_row.trend_score or 0) / 3,
        float(feature_row.momentum_score or 0) / 2,
        float(feature_row.volume_score or 0) / 2,
        float(feature_row.pattern_score or 0) / 2,
        float(feature_row.mtf_score or 0) / 1.75,
        float(feature_row.strict_penalty or 0) / 1.5,
        float(feature_row.ema_distance or 0),
        float(feature_row.atr_ratio or 0),
        float(feature_row.volume_ratio or 0),
        1 if feature_row.regime == "BULL" else 0,
    ]


def train_model():

    db = SessionLocal()

    # ✅ Join entry feature + outcome snapshot
    data = (
        db.query(SignalFeature, TradeOutcomeAnalytics)
        .join(TradeOutcomeAnalytics, SignalFeature.signal_id == TradeOutcomeAnalytics.signal_id)
        .order_by(TradeOutcomeAnalytics.created_at.asc())
        .all()
    )

    db.close()

    if len(data) < 100:
        print("Not enough data")
        return

    X = []
    y = []

    for feature_row, outcome_row in data:
        X.append(build_features(feature_row))
        y.append(1 if outcome_row.label == 1 else 0)

    X = np.array(X)
    y = np.array(y)

    tscv = TimeSeriesSplit(n_splits=5)

    auc_scores = []

    for train_idx, test_idx in tscv.split(X):

        model = xgb.XGBClassifier(
            max_depth=4,
            reg_alpha=2,
            reg_lambda=3,
            n_estimators=300,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            use_label_encoder=False,
            eval_metric="logloss"
        )

        model.fit(X[train_idx], y[train_idx])

        preds = model.predict_proba(X[test_idx])[:, 1]
        auc = roc_auc_score(y[test_idx], preds)
        auc_scores.append(auc)

        print("Fold AUC:", round(auc, 4))

    avg_auc = np.mean(auc_scores)

    # ✅ Train full model
    final_model = xgb.XGBClassifier(
        max_depth=4,
        reg_alpha=2,
        reg_lambda=3,
        n_estimators=300,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        use_label_encoder=False,
        eval_metric="logloss"
    )

    final_model.fit(X, y)

    joblib.dump(final_model, MODEL_PATH)

    print("Model saved")
    print("Average AUC:", round(avg_auc, 4))

    return {
        "train_size": len(y),
        "auc": float(avg_auc),
        "sharpe": 0,
        "max_dd": 0
    }