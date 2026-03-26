from typing import List

TOPICS = {
    "personal",      # 個人資訊（姓名、習慣）
    "technical",     # 技術知識（程式、工具）
    "preference",    # 偏好設定
    "project",       # 專案相關
    "event",         # 事件記錄
    "decision",      # 重要決定
    "learning",      # 學習心得
    "routine",       # 日常作息
    "general",       # 一般（預設）
}

def is_valid_topic(topic: str) -> bool:
    return topic in TOPICS
