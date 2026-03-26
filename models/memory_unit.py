from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
import uuid


class MemoryUnit(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    lossless_text: str
    keywords: List[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    persons: List[str] = Field(default_factory=list)
    topic: str = "general"
    session_id: str = ""
    provenance: Optional[str] = None

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryUnit":
        return cls(**data)
