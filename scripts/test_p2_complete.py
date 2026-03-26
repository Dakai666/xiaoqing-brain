import asyncio
import os
import time
from dotenv import load_dotenv

load_dotenv()

# Manually load MINIMAX_API_KEY if .env has comments
with open('.env', 'r') as f:
    for line in f:
        if line.startswith('MINIMAX_API_KEY='):
            os.environ['MINIMAX_API_KEY'] = line.strip().split('=', 1)[1]
            break

from brain import (
    CompressionStage,
    SynthesisStage,
    ConsolidationScheduler,
    HybridRetriever,
    IntentRetriever,
    MemoryUnit,
)
from brain.utils.llm_backend import MiniMaxBackend, set_llm_backend

# Set MiniMax as global backend
set_llm_backend(MiniMaxBackend())


async def test_intent_retriever(retriever: HybridRetriever):
    print("\n=== Intent-Aware Retrieval 測試 ===\n")
    
    intent_retriever = IntentRetriever(retriever)
    
    test_queries = [
        "我最喜歡什麼程式語言？",
        "我在台北的生活習慣是什麼？",
        "技術相關的記憶有哪些？",
    ]
    
    for query in test_queries:
        print(f"查詢: {query}")
        result = await intent_retriever.search(query, 3)
        print(f"  意圖類型: {result['intent']['intent_type']}")
        print(f"  方法: {result['method']}")
        print(f"  結果數量: {len(result['results'])}")
        if result['results']:
            for r in result['results'][:2]:
                print(f"    - {r.lossless_text[:50]}...")
        print()


async def test_consolidation(sqlite, synthesis):
    print("\n=== Consolidation 測試 ===\n")
    
    scheduler = ConsolidationScheduler(sqlite, synthesis, interval_hours=1)
    
    print(f"初始狀態: {scheduler.get_stats()}")
    
    memories = [
        MemoryUnit(
            lossless_text="使用者喜歡喝咖啡",
            keywords=["咖啡"],
            topic="preference",
            session_id="test-consolidation"
        ),
        MemoryUnit(
            lossless_text="使用者偏好熱咖啡",
            keywords=["熱咖啡"],
            topic="preference",
            session_id="test-consolidation"
        ),
    ]
    
    for m in memories:
        sqlite.add(m)
    
    if scheduler.should_run():
        result = await scheduler.run()
        print(f"整合結果:")
        for session_id, synthesized in result.items():
            print(f"  Session {session_id}: {len(synthesized)} 個記憶")


async def test_full_pipeline():
    os.makedirs("./data", exist_ok=True)
    
    print("=" * 50)
    print("小晴記憶系統 P2 完整測試")
    print("=" * 50)
    
    print("\n[1] 初始化組件...")
    start = time.time()
    
    compression = CompressionStage(model="MiniMax-M2.7")
    synthesis = SynthesisStage(model="MiniMax-M2.7")
    retriever = HybridRetriever()
    
    print(f"    初始化時間: {time.time() - start:.2f}s")
    
    print("\n[2] 測試 CompressionStage...")
    start = time.time()
    
    test_conversations = [
        "使用者說他最喜歡的程式語言是 Python，平時用 VSCode 開發",
        "今天討論了要用 Next.js 來做新專案，使用者偏好 TypeScript",
    ]
    
    all_memories = []
    for conv in test_conversations:
        memories = await compression.process(conv)
        print(f"    '{conv[:30]}...' -> {len(memories)} 記憶")
        all_memories.extend(memories)
    
    print(f"    Compression 時間: {time.time() - start:.2f}s")
    
    print("\n[3] 測試 SynthesisStage...")
    start = time.time()
    
    if len(all_memories) >= 2:
        result = await synthesis.process(all_memories[:2])
        print(f"    整合 {len(all_memories[:2])} -> {len(result)} 記憶")
        print(f"    結果: {result[0].lossless_text[:50] if result else 'N/A'}...")
    print(f"    Synthesis 時間: {time.time() - start:.2f}s")
    
    print("\n[4] 測試儲存...")
    start = time.time()
    
    for m in all_memories:
        await retriever.add_memory(m)
    retriever.sync_bm25()
    
    print(f"    儲存 {len(all_memories)} 記憶")
    print(f"    儲存時間: {time.time() - start:.2f}s")
    
    print("\n[5] 測試向量檢索...")
    start = time.time()
    
    results = await retriever.vector_search("程式語言", 3)
    print(f"    查詢 '程式語言': {len(results)} 結果")
    print(f"    檢索時間: {time.time() - start:.2f}s")
    
    print("\n[6] 測試 BM25 檢索...")
    start = time.time()
    
    results = retriever.bm25_search("Python VSCode", 3)
    print(f"    查詢 'Python VSCode': {len(results)} 結果")
    print(f"    檢索時間: {time.time() - start:.2f}s")
    
    print("\n[7] 測試 Intent-Aware 檢索...")
    start = time.time()
    await test_intent_retriever(retriever)
    print(f"    Intent 檢索時間: {time.time() - start:.2f}s")
    
    print("\n[8] 測試 Consolidation...")
    await test_consolidation(retriever.sqlite, synthesis)
    
    print("\n" + "=" * 50)
    print("P2 測試完成！")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(test_full_pipeline())
