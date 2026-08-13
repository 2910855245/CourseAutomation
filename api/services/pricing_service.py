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
