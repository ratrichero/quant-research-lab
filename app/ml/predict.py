import joblib, os
MODEL_PATH="app/ml/model.pkl"
_model=None

def load():
    global _model
    if _model is None and os.path.exists(MODEL_PATH):
        _model=joblib.load(MODEL_PATH)
    return _model

def predict_prob(features):
    m=load()
    if not m: return None
    return float(m.predict_proba([features])[0][1])
