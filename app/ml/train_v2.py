import joblib, numpy as np, xgboost as xgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import roc_auc_score
from app.db.session import SessionLocal
from app.db.models import Signal

MODEL_PATH="app/ml/model.pkl"

def build_features(s):
    return [
        float(s.rsi or 50),
        float(s.volume_ratio or 1),
        float(s.score),
        1 if s.direction=="LONG" else 0
    ]

def train_model():
    db=SessionLocal()
    data=db.query(Signal).filter(Signal.status.in_(["WIN","LOSS"])).order_by(Signal.candle_time.asc()).all()
    db.close()
    if len(data)<100:
        print("Not enough data")
        return
    X=np.array([build_features(s) for s in data])
    y=np.array([1 if s.status=="WIN" else 0 for s in data])
    tscv=TimeSeriesSplit(n_splits=5)
    for tr,te in tscv.split(X):
        model=xgb.XGBClassifier(max_depth=3,reg_alpha=2,reg_lambda=3,n_estimators=300)
        model.fit(X[tr],y[tr])
        preds=model.predict_proba(X[te])[:,1]
        print("Fold AUC:",roc_auc_score(y[te],preds))
    model.fit(X,y)
    joblib.dump(model,MODEL_PATH)
    print("Model saved")
    return {
    "train_size": len(y),
    "auc": float(avg_auc),
    "sharpe": 0,     # có thể bổ sung sau
    "max_dd": 0
}
