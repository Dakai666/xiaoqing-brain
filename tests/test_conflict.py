"""Tests for conflict detection (絲絲 review B2 fix)"""

from brain.models.memory_unit import MemoryUnit
from brain.stages.conflict import ConflictResolver


def test_similar_memories_should_conflict():
    resolver = ConflictResolver()
    m1 = MemoryUnit(lossless_text="my name is xiao ming", keywords=["name"], persons=["xiao ming"])
    m2 = MemoryUnit(lossless_text="my name is xiao ming hello", keywords=["name"], persons=["xiao ming"])
    assert resolver.detect_conflict(m1, m2) is True, "高度相似的兩筆記憶應該判定為衝突"


def test_different_memories_should_not_conflict():
    resolver = ConflictResolver()
    m1 = MemoryUnit(lossless_text="my name is xiao ming", keywords=["name"])
    m2 = MemoryUnit(lossless_text="the weather is nice today", keywords=["weather"])
    assert resolver.detect_conflict(m1, m2) is False, "不相關的兩筆記憶不應判定為衝突"


def test_same_memory_id_not_conflict():
    resolver = ConflictResolver()
    m1 = MemoryUnit(id="abc", lossless_text="my name is xiao ming", keywords=["name"])
    m2 = MemoryUnit(id="abc", lossless_text="my name is xiao ming", keywords=["name"])
    assert resolver.detect_conflict(m1, m2) is False, "相同 ID 的記憶不應判定為衝突"


def test_different_intent_type_not_conflict():
    resolver = ConflictResolver()
    m1 = MemoryUnit(lossless_text="my name is xiao ming", keywords=["name"], intent_type="fact")
    m2 = MemoryUnit(lossless_text="my name is xiao ming", keywords=["name"], intent_type="preference")
    assert resolver.detect_conflict(m1, m2) is False, "不同 intent type 不應衝突"


def test_no_common_entities_not_conflict():
    resolver = ConflictResolver()
    m1 = MemoryUnit(lossless_text="my name is xiao ming", keywords=["name"], persons=["xiao ming"])
    m2 = MemoryUnit(lossless_text="the weather is rainy today", keywords=["weather"], persons=["xiao hua"])
    assert resolver.detect_conflict(m1, m2) is False, "無共同 persons/keywords 不應衝突"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
