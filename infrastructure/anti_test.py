"""
AI 自动答题模块（兼容层）

实际实现已拆分到：
  - exam_login.py    — LoginHelper, OnlineHeartbeat, normalize_base_url
  - exam_fetcher.py  — TopicFetcher
  - exam_answerer.py — AIAnswerer, WorkSubmitter, AIWorkRunner

本文件仅做 re-export，保持 `from infrastructure.anti_test import ...` 不变。
"""

from infrastructure.exam_answerer import AIAnswerer, AIWorkRunner, WorkSubmitter
from infrastructure.exam_fetcher import TopicFetcher
from infrastructure.exam_login import LoginHelper, OnlineHeartbeat, normalize_base_url

__all__ = [
    'normalize_base_url', 'LoginHelper', 'OnlineHeartbeat',
    'TopicFetcher',
    'AIAnswerer', 'WorkSubmitter', 'AIWorkRunner',
]
