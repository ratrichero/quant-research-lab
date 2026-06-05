from fastapi import APIRouter
from app.services.model_retrainer import retrain_model

router = APIRouter()

@router.post("/retrain")
def retrain():
    result = retrain_model()
    return result