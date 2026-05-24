from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import get_current_admin
from api.database import db
from api.services.crack import crack_engine

router = APIRouter(prefix="/api/admin/crack", tags=["裂变管理"])


class TierRule(BaseModel):
    name: str
    lv1_rate: float
    lv2_rate: float
    lv3_rate: float
    cost_discount: float
    flow_threshold: float
    invite_threshold: int
    join_fee: float


class TierRulesUpdate(BaseModel):
    rules: dict


class InviteRewardRate(BaseModel):
    rate: float


@router.get("/rules")
def get_rules(admin: dict = Depends(get_current_admin)):
    return {"code": 0, "data": crack_engine.tier_rules}


@router.put("/rules")
def update_rules(payload: TierRulesUpdate, admin: dict = Depends(get_current_admin)):
    rules = {}
    for key, val in payload.rules.items():
        try:
            rules[int(key)] = {
                "name": val.get("name", ""),
                "lv1_rate": val.get("lv1_rate", 0),
                "lv2_rate": val.get("lv2_rate", 0),
                "lv3_rate": val.get("lv3_rate", 0),
                "cost_discount": val.get("cost_discount", 0.9),
                "flow_threshold": val.get("flow_threshold", 0),
                "invite_threshold": val.get("invite_threshold", 0),
                "join_fee": val.get("join_fee", 0),
            }
        except Exception as e:
            continue
    if rules:
        crack_engine.set_tier_rules(rules)
    db.audit_log("crack_rules_updated", operator=admin.get("username", "admin"),
                 detail=f"裂变规则已更新 {len(rules)} 个等级")
    return {"code": 0, "message": "规则已更新", "data": crack_engine.tier_rules}


@router.post("/invite-reward-rate")
def set_invite_reward_rate(payload: InviteRewardRate, admin: dict = Depends(get_current_admin)):
    import api.services.crack as crack_module
    crack_module.C_USER_REWARD_RATE = payload.rate
    db.audit_log("invite_rate_updated", operator=admin.get("username", "admin"),
                 detail=f"C端邀请返佣比例已更新为 {payload.rate}")
    return {"code": 0, "message": "返佣比例已更新", "data": {"rate": payload.rate}}
