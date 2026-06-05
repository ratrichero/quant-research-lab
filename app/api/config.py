from fastapi import APIRouter, Body
from app.services.config_service import get_runtime_config, update_runtime_config

router = APIRouter()

@router.get("/config")
def get_config():
    return get_runtime_config()

@router.post("/config")
def save_config(payload: dict = Body(...)):
    update_runtime_config(payload)
    return {"status": "updated"}