from typing import Optional

from fastapi import APIRouter, Depends

from api.auth import get_current_user
from api.database import db
from api.redis_client import redis_client
from config import settings

router = APIRouter(prefix="/api/invite", tags=["邀请裂变"])


@router.get("/my-code")
def my_invite_code(current_user: dict = Depends(get_current_user)):
    uid = current_user.get("user_id", "")
    invite_count = 0
    total_reward = 0.0
    invite_info = db.user_invite_get_by_inviter(uid)
    if invite_info:
        invite_count = invite_info["invite_count"] or 0
        total_reward = invite_info["total_reward"] or 0.0
    if redis_client.available:
        try:
            count_val = redis_client.zcard(f"invite:rank:user:{uid}")
            if count_val is not None:
                invite_count = count_val
        except Exception as e:
            pass
    from api.database import db as _db
    _site = _db.ypay_setting_get("site_url", "") or settings.site_url
    return {
        "code": 0,
        "data": {
            "invite_code": uid[:8].zfill(8) if uid else "",
            "invite_link": f"{_site.rstrip('/')}/#/?ref={uid[:8]}" if uid else "",
            "total_reward": total_reward,
            "invite_count": invite_count,
        },
    }


@router.get("/rank")
def invite_rank(period: str = "week", current_user: Optional[dict] = None):
    items = []
    if redis_client.available:
        try:
            key = f"invite:rank:{period}:latest"
            ranked = redis_client.zrangebyscore(key, 0, float("inf")) or []
            for uid in reversed(ranked[-20:]):
                items.append({
                    "user_id": uid,
                    "nickname": uid[:6] + "***",
                    "invite_count": 0,
                    "total_reward": 0.0,
                })
        except Exception as e:
            pass
    return {"code": 0, "data": {"period": period, "items": items}}
