"""定价服务 — AI 推荐 + 打包定价计算"""
from __future__ import annotations

import json
from typing import Optional

from loguru import logger

from api.database import db


# AI 推荐定价的 prompt 模板
_RECOMMEND_PROMPT = """你是一个网课代刷平台的定价专家。请根据以下市场数据推荐最优定价方案。

## 市场行情
- 市场平均价：¥{avg}/课
- 市场最高价：¥{mx}/课
- 市场最低价：¥{mn}/课
- 我的边际成本：¥{cost}/课（机器自动刷课，几乎零成本）
- 竞品是人工刷课，成本约 ¥{cost_low:.0f}-{cost_high:.0f}/课
- 竞品对所有课程统一收费，不区分课程大小和进度
- 竞品对纯考试课程收 ¥5-6，纯考试优先级最高
{extra_section}

## AI 成本分析
- 期末考试使用 deepseek-v4-flash：输入¥1/百万tokens（缓存命中¥0.02），输出¥2/百万tokens
- 平时作业使用 deepseek-chat：同上价格
- 每道题约消耗 200-500 tokens，每门考试约 50-100 道题
- 单门考试 AI 成本约 ¥0.01-0.05（极低）
- 单门作业 AI 成本约 ¥0.005-0.02（极低）
- AI 成本几乎可忽略，定价主要考虑市场竞争

## 我的系统能力
- 支持按课程视频数分档定价（小课/中课/大课）
- 支持按学生已完成进度打折（学生看了一半的课，我工作量少一半）
- 视频+考试打包一口价
- 纯考试课程单独定价（无视频，只有期末考试）
- 纯作业课程单独定价（无视频，只有平时作业）
- 最低收费保底

## 要求
请给出打包定价方案：

1. 纯考试价格（参考竞品 ¥5-6）
2. 纯作业价格
3. 三档课程包价（小课≤30视频、中课31-80视频、大课>80视频）
4. 三档进度折扣系数（25-50%、50-75%、>75%）
5. 最低收费
6. 定价策略分析（50字以内）
7. 3个典型场景对比（课程规模×进度 vs 竞品价 vs 我的价）

请用JSON格式返回，格式如下：
{{"priceSmall":3,"priceMedium":5,"priceLarge":6,"discount25":0.7,"discount50":0.5,"discount75":0.3,"priceMinimum":2,"priceExamOnly":5,"priceHomeworkOnly":3,"strategy":"策略分析文字","scenarios":[{{"course":"场景名","videos":20,"progress":"0%","competitor":"¥5-6","your_price":"¥3","note":"说明"}}]}}"""


def _get_api_key() -> str:
    """获取 DeepSeek API Key，优先从数据库配置读取"""
    api_key = db.config_get("deepseek_api_key") or ""
    if not api_key:
        from config import settings
        api_key = settings.deepseek_api_key
    return api_key


def _call_ai_recommend(avg: float, mx: float, mn: float, cost: float, extra: str, api_key: str) -> Optional[dict]:
    """调用 DeepSeek AI 获取推荐定价方案，失败返回 None"""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        extra_section = f"- 其他信息：{extra}" if extra else ""
        prompt = _RECOMMEND_PROMPT.format(
            avg=avg, mx=mx, mn=mn, cost=cost,
            cost_low=avg * 0.5, cost_high=avg * 0.7,
            extra_section=extra_section,
        )
        pricing_model = db.config_get("deepseek_pricing_model") or "deepseek-v4-pro"
        resp = client.chat.completions.create(
            model=pricing_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.3,
            timeout=20,
        )
        content = resp.choices[0].message.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        return json.loads(content)
    except Exception as e:
        logger.warning(f"AI 推荐定价失败 error={str(e)}")
        return None


def _fallback_recommend(avg: float, mx: float, mn: float, cost: float) -> dict:
    """AI 失败时的公式兜底定价"""
    price_small = max(int(cost + 1), round(mn * 0.8))
    price_medium = max(int(cost + 2), round(avg * 0.85))
    price_large = max(int(cost + 2), round(mx * 0.9))
    if price_small >= price_medium:
        price_medium = price_small + 1
    if price_medium >= price_large:
        price_large = price_medium + 1
    price_min = max(2, int(cost + 1))
    price_exam_only = max(4, round(avg * 0.9))
    price_homework_only = max(2, round(avg * 0.5))

    scenarios = []
    for name, vcount, progress in [("小课(20节)", 20, 0), ("小课看了一半", 20, 50),
                                    ("中课(50节)", 50, 0), ("中课看了60%", 50, 60),
                                    ("大课(100节)", 100, 0), ("大课看了80%", 100, 80)]:
        base = price_small if vcount <= 30 else price_medium if vcount <= 80 else price_large
        coeff = 1.0 if progress <= 25 else 0.7 if progress <= 50 else 0.5 if progress <= 75 else 0.3
        your_price = max(price_min, round(base * coeff))
        scenarios.append({"course": name, "videos": vcount, "progress": f"{progress}%",
                          "competitor": f"¥{avg:.0f}-{mx:.0f}", "your_price": f"¥{your_price}",
                          "note": "低价" if your_price < mn else "持平"})

    return {
        "priceSmall": price_small, "priceMedium": price_medium, "priceLarge": price_large,
        "discount25": 0.7, "discount50": 0.5, "discount75": 0.3, "priceMinimum": price_min,
        "priceExamOnly": price_exam_only, "priceHomeworkOnly": price_homework_only,
        "strategy": f"小课 ¥{price_small} 抢量，大课 ¥{price_large} 封顶，纯考试 ¥{price_exam_only}，进度折扣是核心壁垒",
        "scenarios": scenarios,
    }


def recommend_pricing(avg: float, mx: float, mn: float, cost: float, extra: str = "") -> dict:
    """生成推荐定价方案（AI + 公式兜底），返回完整响应 dict"""
    api_key = _get_api_key()
    ai_plan = None
    ai_analysis = ""

    if api_key:
        ai_plan = _call_ai_recommend(avg, mx, mn, cost, extra, api_key)
        if ai_plan:
            ai_analysis = ai_plan.get("strategy", "")
        else:
            ai_analysis = "AI 分析失败，使用公式兜底"

    if not ai_plan:
        ai_plan = _fallback_recommend(avg, mx, mn, cost)

    return {
        "code": 0,
        "data": {
            "recommended": {
                "priceSmall": ai_plan.get("priceSmall", 3),
                "priceMedium": ai_plan.get("priceMedium", 5),
                "priceLarge": ai_plan.get("priceLarge", 6),
                "discount25": ai_plan.get("discount25", 0.7),
                "discount50": ai_plan.get("discount50", 0.5),
                "discount75": ai_plan.get("discount75", 0.3),
                "priceMinimum": ai_plan.get("priceMinimum", 2),
                "priceExamOnly": ai_plan.get("priceExamOnly", 5),
                "priceHomeworkOnly": ai_plan.get("priceHomeworkOnly", 3),
            },
            "market": {"avg": avg, "max": mx, "min": mn, "your_cost": cost},
            "analysis": {
                "strategy": ai_plan.get("strategy", ai_analysis),
                "scenarios": ai_plan.get("scenarios", []),
                "ai_powered": bool(api_key),
            },
        },
    }
