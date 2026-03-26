import asyncio
import os
from brain import (
    CompressionStage,
    LanceDBStorage,
    SQLiteStorage,
    HybridRetriever,
    MemoryUnit,
)


async def main():
    os.makedirs("./data", exist_ok=True)
    
    print("=== 小晴記憶系統測試 ===\n")
    
    print("1. 初始化儲存...")
    lancedb = LanceDBStorage(db_path="./data/lancedb")
    sqlite = SQLiteStorage(db_path="./data/memories.db")
    print("   [OK] LanceDB + SQLite 初始化完成\n")
    
    print("2. 初始化壓縮 Stage...")
    compression = CompressionStage(model="qwen3.5:2b")
    print("   [OK] CompressionStage 初始化完成\n")
    
    print("3. 初始化檢索器...")
    retriever = HybridRetriever(lancedb, sqlite)
    print("   [OK] HybridRetriever 初始化完成\n")
    
    test_conversations = [
        "使用者說他最喜歡的程式語言是 Python，平時用 VSCode 開發",
        "今天討論了要用 Next.js 來做新專案，使用者偏好 TypeScript",
        "使用者提到他住在台北，平時騎機車上班",
    ]
    
    print("4. 處理測試對話...")
    for i, conv in enumerate(test_conversations, 1):
        print(f"\n   對話 {i}: {conv}")
        memories = await compression.process(conv)
        for memory in memories:
            print(f"   → 記憶: {memory.lossless_text}")
            print(f"     主題: {memory.topic}, 關鍵詞: {memory.keywords}")
            await retriever.add_memory(memory)
    print("\n   [OK] 記憶新增完成\n")
    
    print("5. 測試向量檢索...")
    query = "程式語言 開發工具"
    results = await retriever.vector_search(query, 3)
    print(f"   查詢: '{query}'")
    for r in results:
        print(f"   → {r.lossless_text}")
    print()
    
    print("6. 測試 BM25 檢索...")
    retriever.sync_bm25()
    results = retriever.bm25_search("住在台北", 3)
    print(f"   查詢: '住在台北'")
    for r in results:
        print(f"   → {r.lossless_text}")
    print()
    
    print("=== 測試完成 ===")


if __name__ == "__main__":
    asyncio.run(main())
