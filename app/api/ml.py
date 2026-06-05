from fastapi import APIRouter
from app.ml.train import train_model
router=APIRouter()
@router.post("/train-model")
def train():
    train_model()
    return {"status":"trained"}
