from fastapi import APIRouter, Depends

from api.auth import get_current_user
from api.database import db
from api.models import ApiResponse

router = APIRouter(prefix="/api/wallet", tags=["钱包"])


@router.get("/balance", response_model=ApiResponse)
def get_balance(current_user: dict = Depends(get_current_user)):
    balance = db.get_user_balance(current_user["user_id"])
    return ApiResponse(data={"balance": balance})


@router.get("/transactions", response_model=ApiResponse)
def list_transactions(
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    txs = db.get_user_transactions(current_user["user_id"], limit=limit)
    return ApiResponse(data=txs)
