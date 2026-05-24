from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Optional

from loguru import logger


# 三级代理分层佣金体系
# 经济学设计原则：
#   1. L1直销佣金足够高（30-40%），代理拉客有动力
#   2. L2/L3间推佣金递减，鼓励发展下线但不鼓励躺赚
#   3. 成本折扣逐级递增，高级代理自己刷课更便宜
#   4. 流水阈值+邀请数双门槛，自动升级有据可依
#
# 平台利润率模拟（¥10订单，三级代理都在线）：
#   L3直推：¥4.00(40%)，L2间推：¥0.60(10%)，L1二级间推：¥0.16(3%)
#   总佣金：¥4.76(47.6%)，平台毛利：¥5.24(52.4%)
#   L1直推场景（最常见）：¥3.00(30%)，平台毛利：¥7.00(70%)
DEFAULT_TIER_RULES = {
    1: {
        "name": "入门代理",
        "lv1_rate": 0.30,   # 直推佣金 30%
        "lv2_rate": 0.00,   # 间推佣金 0%（入门无间推权）
        "lv3_rate": 0.00,
        "cost_discount": 0.95,       # 自己下单 95 折
        "flow_threshold": 0,         # 无条件准入
        "invite_threshold": 0,
        "join_fee": 0,
    },
    2: {
        "name": "高级代理",
        "lv1_rate": 0.35,   # 直推佣金 35%
        "lv2_rate": 0.08,   # 间推佣金 8%
        "lv3_rate": 0.00,
        "cost_discount": 0.90,       # 自己下单 9 折
        "flow_threshold": 500,       # 累计流水 ¥500 可升级
        "invite_threshold": 3,       # 邀请 3 个代理
        "join_fee": 0,
    },
    3: {
        "name": "资深代理",
        "lv1_rate": 0.40,   # 直推佣金 40%
        "lv2_rate": 0.10,   # 间推佣金 10%
        "lv3_rate": 0.03,   # 二级间推 3%
        "cost_discount": 0.85,       # 自己下单 85 折
        "flow_threshold": 3000,      # 累计流水 ¥3000 可升级
        "invite_threshold": 10,      # 邀请 10 个代理
        "join_fee": 0,
    },
}

MAX_LEVEL = 3
MAX_TOTAL_COMMISSION_RATE = 0.50  # 总佣金上限 50%，保证平台至少 50% 毛利
C_USER_REWARD_RATE = 0.00         # 普通用户邀请奖励（非代理），暂不启用


class CrackEngine:

    def __init__(self):
        self.tier_rules: Dict[int, Dict] = dict(DEFAULT_TIER_RULES)

    def set_tier_rules(self, rules: Dict[int, Dict]):
        self.tier_rules.update(rules)

    def get_commission_rates(self, tier: int) -> Dict[str, float]:
        rule = self.tier_rules.get(tier) or self.tier_rules.get(1, DEFAULT_TIER_RULES[1])
        return {
            "lv1_rate": rule["lv1_rate"],
            "lv2_rate": rule["lv2_rate"],
            "lv3_rate": rule["lv3_rate"],
            "cost_discount": rule["cost_discount"],
        }

    def calculate_commissions(self, order_amount: float, direct_agent: Optional[Dict],
                               parent_agent: Optional[Dict],
                               grandparent_agent: Optional[Dict]) -> List[Dict[str, Any]]:
        commissions = []
        remaining = Decimal(str(order_amount))
        agents = [
            (direct_agent, "lv1", 1),
            (parent_agent, "lv2", 2),
            (grandparent_agent, "lv3", 3),
        ]
        for agent_data, rate_key, depth in agents:
            if not agent_data:
                continue
            if agent_data.get("status") != "active":
                continue
            rates = self.get_commission_rates(agent_data.get("tier_level", 1))
            # 如果代理有独立的佣金比例（手动设置），L1 直推使用该比例
            custom_rate = float(agent_data.get("flow_commission_rate", 0) or 0)
            if depth == 1 and custom_rate > 0:
                rate = Decimal(str(custom_rate))
            else:
                rate = Decimal(str(rates.get(f"{rate_key}_rate", 0)))
            if rate <= 0:
                continue
            if depth > 1 and remaining <= 0:
                continue
            base = Decimal(str(order_amount)) if depth == 1 else remaining
            amount = (base * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            cap = (Decimal(str(order_amount)) * Decimal(str(MAX_TOTAL_COMMISSION_RATE))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            already = sum(Decimal(str(c["amount"])) for c in commissions)
            if already + amount > cap:
                amount = (cap - already).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if amount <= 0:
                continue
            commissions.append({
                "agent_id": agent_data["agent_id"],
                "user_id": agent_data.get("user_id", ""),
                "level": depth,
                "rate": float(rate),
                "amount": float(amount),
                "type": f"lv{depth}_commission",
                "note": f"第{depth}级推广佣金",
            })
            remaining -= amount
        return commissions

    def calculate_user_reward(self, order_amount: float) -> Dict[str, Any]:
        reward = (Decimal(str(order_amount)) * Decimal(str(C_USER_REWARD_RATE))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return {
            "rate": C_USER_REWARD_RATE,
            "amount": float(reward),
            "type": "invite_reward",
            "note": "邀请返佣奖励",
        }

    def check_tier_upgrade(self, agent: Dict) -> Optional[int]:
        current_tier = int(agent.get("tier_level", 1))
        total_flow = float(agent.get("total_flow", 0))
        total_invites = int(agent.get("total_invites", 0))
        for tier, rule in sorted(self.tier_rules.items()):
            if tier <= current_tier:
                continue
            flow_ok = total_flow >= rule.get("flow_threshold", 0)
            invites_ok = total_invites >= rule.get("invite_threshold", 0)
            if flow_ok and invites_ok:
                return tier
        return None


crack_engine = CrackEngine()
