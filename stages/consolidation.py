import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from ..models.memory_unit import MemoryUnit
from ..storage.sqlite import SQLiteStorage
from ..storage.markdown import MarkdownBackup
from ..stages.synthesis import SynthesisStage


class ConsolidationScheduler:
    def __init__(
        self,
        sqlite: SQLiteStorage,
        synthesis: SynthesisStage,
        markdown_backup: Optional[MarkdownBackup] = None,
        interval_hours: int = 24
    ):
        self.sqlite = sqlite
        self.synthesis = synthesis
        self.markdown = markdown_backup or MarkdownBackup()
        self.interval_hours = interval_hours
        self.last_run: Optional[datetime] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    def should_run(self) -> bool:
        if self._running:
            return False
        if self.last_run is None:
            return True
        
        elapsed = datetime.now() - self.last_run
        return elapsed >= timedelta(hours=self.interval_hours)

    async def run(self) -> Dict[str, List[MemoryUnit]]:
        self._running = True
        
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            
            # 只取出**當天**的記憶，避免混入過去事件
            all_memories = self.sqlite.get_by_topic("general") + \
                          self.sqlite.get_by_topic("preference") + \
                          self.sqlite.get_by_topic("personal") + \
                          self.sqlite.get_by_topic("diary")
            
            # 過濾：只保留今天的記憶
            today_memories = [m for m in all_memories if m.date == today]
            
            # 排除已有"日記"關鍵詞的記憶（避免重複整合）
            today_memories = [m for m in today_memories if "日記" not in m.keywords]
            
            # 按 session_id 分組
            session_groups: Dict[str, List[MemoryUnit]] = {}
            for m in today_memories:
                if m.session_id not in session_groups:
                    session_groups[m.session_id] = []
                session_groups[m.session_id].append(m)
            
            consolidated: Dict[str, List[MemoryUnit]] = {}
            total_diary_entries = 0
            
            for session_id, session_memories in session_groups.items():
                if len(session_memories) >= 2:
                    # 對同一 session 的多筆記憶進行整合
                    result = await self.synthesis.process(session_memories)
                    
                    # 為每個整合後的記憶加上"日記"關鍵詞
                    for m in result:
                        if "日記" not in m.keywords:
                            m.keywords.append("日記")
                        m.topic = "diary"
                        m.session_id = f"diary-{today}"
                        # 寫入儲存
                        self.sqlite.add(m)
                        self.markdown.add_memory(m)
                        total_diary_entries += 1
                    
                    consolidated[session_id] = result
                else:
                    consolidated[session_id] = session_memories
            
            self.last_run = datetime.now()
            
            print(f"Consolidation 完成: {total_diary_entries} 筆日記寫入 (今天: {today})")
            return consolidated
        finally:
            self._running = False

    async def _run_loop(self):
        while not self._stop_event.is_set():
            if self.should_run():
                try:
                    result = await self.run()
                    print(f"Consolidation completed: {len(result)} sessions processed")
                except Exception as e:
                    print(f"Consolidation error: {e}")
            
            await asyncio.sleep(3600)

    def start(self):
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run_loop())
            print(f"ConsolidationScheduler started (interval: {self.interval_hours}h)")

    async def stop(self):
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        print("ConsolidationScheduler stopped")

    def apply_decay(self) -> dict:
        all_memories = self.sqlite.search("", 10000)
        decay_stats = {"fast": 0, "normal": 0, "slow": 0, "none": 0, "total_updated": 0}
        
        for m in all_memories:
            if m.decay_rate.value == "none":
                decay_stats["none"] += 1
                continue
            
            if hasattr(m, 'last_accessed') and m.last_accessed:
                last_acc = datetime.fromisoformat(m.last_accessed.replace("Z", "+00:00"))
                if hasattr(last_acc, 'tzinfo') and last_acc.tzinfo:
                    last_acc = last_acc.replace(tzinfo=None)
                days = (datetime.now() - last_acc).days
            else:
                ts = m.timestamp.replace("Z", "+00:00")
                ts_date = datetime.fromisoformat(ts).date()
                days = (datetime.now().date() - ts_date).days
            
            old_conf = m.confidence
            m.confidence = m.apply_decay(days)
            
            if abs(m.confidence - old_conf) > 0.001:
                self.sqlite.update_confidence(m.id, m.confidence)
                decay_stats["total_updated"] += 1
                decay_stats[m.decay_rate.value] += 1
        
        print(f"Decay job 完成: 更新 {decay_stats['total_updated']} 筆記憶")
        return decay_stats

    def get_stats(self) -> dict:
        all_memories = self.sqlite.search("", 10000)
        return {
            "total_memories": len(all_memories),
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "interval_hours": self.interval_hours,
            "should_run": self.should_run()
        }
