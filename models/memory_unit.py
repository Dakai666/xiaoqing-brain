from pydantic import BaseModel, Field, model_validator
from typing import List, Optional
from datetime import datetime, timedelta
import uuid


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
