from pydantic import BaseModel, Field, model_validator
from typing import List, Optional
from datetime import datetime, timedelta
from enum import Enum
import uuid


class IntentType(str, Enum):
    FACT = "fact"        # 用戶明確陳述的事實
    IMPRESSION = "impression"  # 推斷、印象、猜測
    PREFERENCE = "preference"  # 偏好、喜歡、厭惡
    HABIT = "habit"      # 習慣、日常行為

    @property
    def icon(self) -> str:
        icons = {
            "fact": "🔵",
            "impression": "💫",
            "preference": "🎯",
            "habit": "🌱",
        }
        return icons.get(self.value, "🔵")


class DecayRate(str, Enum):
    FAST = "fast"      # 天氣、新聞 - 每天衰減 50%
    NORMAL = "normal"  # 一般資訊 - 每天衰減 10%
    SLOW = "slow"      # 偏好、習慣 - 每天衰減 2%
    NONE = "none"      # 身份、永久事實 - 不衰減


DECAY_MULTIPLIERS = {
    DecayRate.FAST: 0.5,
    DecayRate.NORMAL: 0.1,
    DecayRate.SLOW: 0.02,
    DecayRate.NONE: 0.0,
}


# 預設 source_reliability
DEFAULT_RELIABILITY = {
    IntentType.FACT: 1.0,
    IntentType.IMPRESSION: 0.6,
    IntentType.PREFERENCE: 0.9,
    IntentType.HABIT: 0.85,
}


class MemoryUnit(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    lossless_text: str
    keywords: List[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    date: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    persons: List[str] = Field(default_factory=list)
    topic: str = "general"
    session_id: str = ""
    provenance: Optional[str] = None
    
    intent_type: IntentType = IntentType.FACT
    source_reliability: float = 1.0
    decay_rate: DecayRate = DecayRate.NORMAL
    confidence: float = 1.0
    last_accessed: Optional[str] = None
    access_count: int = 0
    
    is_superseded: bool = False
    replaced_by: Optional[str] = None
    needs_confirmation: bool = False
    
    @model_validator(mode="before")
    @classmethod
    def extract_date_from_timestamp(cls, data: dict) -> dict:
        if isinstance(data, dict):
            if "timestamp" in data and "date" not in data:
                ts = data["timestamp"]
                if isinstance(ts, str) and len(ts) >= 10:
                    data["date"] = ts[:10]
            elif "date" not in data:
                data["date"] = datetime.now().strftime("%Y-%m-%d")
        return data
    
    def apply_decay(self, days: int) -> float:
        if self.decay_rate == DecayRate.NONE or self.confidence <= 0:
            return self.confidence
        
        daily_decay = DECAY_MULTIPLIERS[self.decay_rate]
        new_confidence = self.confidence * ((1 - daily_decay) ** days)
        return max(0.0, new_confidence)
    
    def record_access(self):
        self.last_accessed = datetime.now().isoformat()
        self.access_count += 1
        self.confidence = min(1.0, self.confidence + 0.05)

    def get_time_distance(self, now: Optional[datetime] = None) -> str:
        if now is None:
            now = datetime.now()
        try:
            mem_time = datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
            if hasattr(mem_time, 'tzinfo') and mem_time.tzinfo is not None:
                mem_time = mem_time.replace(tzinfo=None)
            mem_date = mem_time.date()
            today = now.date()
            delta = (today - mem_date).days
            
            if delta == 0:
                return "今天"
            elif delta == 1:
                return "昨天"
            elif delta <= 7:
                return f"{delta}天前"
            elif delta <= 14:
                return "大約一週前"
            elif delta <= 30:
                return "大約一個月前"
            elif delta <= 90:
                return "大約三個月前"
            elif delta <= 180:
                return "大約半年前"
            elif delta <= 365:
                return "大約一年前"
            else:
                return "更久以前"
        except (ValueError, TypeError):
            return "未知時間"

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryUnit":
        return cls(**data)
