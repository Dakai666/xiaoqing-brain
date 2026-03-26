import asyncio
from brain import SynthesisStage, MemoryUnit


async def test_synthesis():
    print("=== SynthesisStage 測試 ===\n")
    
    synthesis = SynthesisStage(buffer_size=3)
    
    memories = [
        MemoryUnit(
            id="1",
            lossless_text="使用者喜歡喝咖啡",
            keywords=["咖啡", "飲料"],
            topic="preference",
            session_id="test-session"
        ),
        MemoryUnit(
            id="2",
            lossless_text="使用者偏好熱咖啡",
            keywords=["熱咖啡", "溫度"],
            topic="preference",
            session_id="test-session"
        ),
        MemoryUnit(
            id="3",
            lossless_text="使用者喜歡燕麥奶",
            keywords=["燕麥奶", "植物奶"],
            topic="preference",
            session_id="test-session"
        ),
    ]
    
    print("輸入記憶片段：")
    for m in memories:
        print(f"  - {m.lossless_text}")
    print()
    
    result = await synthesis.process(memories)
    
    print("整合後結果：")
    for m in result:
        print(f"  - {m.lossless_text}")
        print(f"    關鍵詞: {m.keywords}")
    print()
    
    print("=== 測試完成 ===")


if __name__ == "__main__":
    asyncio.run(test_synthesis())
