from enum import Enum
from typing import List, Tuple, Optional
from ..models.memory_unit import MemoryUnit


class ConflictStrategy(str, Enum):
    KEEP_BOTH = "keep_both"
    KEEP_MOST_RECENT = "keep_most_recent"
    USER_CONFIRM = "user_confirm"


class ConflictResolver:
    def __init__(self, strategy: ConflictStrategy = ConflictStrategy.KEEP_BOTH):
        self.strategy = strategy
    
    def detect_conflict(self, new: MemoryUnit, old: MemoryUnit) -> bool:
        if new.id == old.id:
            return False
        
        if new.intent_type != old.intent_type:
            return False
        
        new_entities = set(new.persons) | set(new.keywords)
        old_entities = set(old.persons) | set(old.keywords)
        
        if not new_entities.intersection(old_entities):
            return False
        
        similarity = self._content_similarity(new.lossless_text, old.lossless_text)
        
        return similarity > 0.5
    
    def _content_similarity(self, text1: str, text2: str) -> float:
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union)
    
    def resolve(self, new: MemoryUnit, old: MemoryUnit) -> Tuple[MemoryUnit, Optional[MemoryUnit]]:
        if self.strategy == ConflictStrategy.KEEP_BOTH:
            old.is_superseded = True
            old.replaced_by = new.id
            return new, old
        
        elif self.strategy == ConflictStrategy.KEEP_MOST_RECENT:
            new_date = new.timestamp if hasattr(new, 'timestamp') else ""
            old_date = old.timestamp if hasattr(old, 'timestamp') else ""
            if new_date >= old_date:
                return new, old
            else:
                return old, new
        
        else:
            new.needs_confirmation = True
            return new, old
    
    def find_conflicts(self, memories: List[MemoryUnit]) -> List[Tuple[MemoryUnit, MemoryUnit]]:
        conflicts = []
        
        for i, mem1 in enumerate(memories):
            for mem2 in memories[i+1:]:
                if self.detect_conflict(mem1, mem2):
                    conflicts.append((mem1, mem2))
        
        return conflicts


class ConflictRecord:
    id: str
    old_memory_id: str
    new_memory_id: str
    conflict_type: str
    resolved_with: str
    resolved_at: str