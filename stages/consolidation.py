import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from ..models.memory_unit import MemoryUnit
from ..storage.sqlite import SQLiteStorage
from ..stages.synthesis import SynthesisStage


class ConsolidationScheduler:
    def __init__(
        self,
        sqlite: SQLiteStorage,
        synthesis: SynthesisStage,
        interval_hours: int = 24
    ):
        self.sqlite = sqlite
        self.synthesis = synthesis
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
            memories = self.sqlite.get_by_topic("general") + \
                      self.sqlite.get_by_topic("preference") + \
                      self.sqlite.get_by_topic("personal")
            
            session_groups: Dict[str, List[MemoryUnit]] = {}
            for m in memories:
                if m.session_id not in session_groups:
                    session_groups[m.session_id] = []
                session_groups[m.session_id].append(m)
            
            consolidated: Dict[str, List[MemoryUnit]] = {}
            
            for session_id, session_memories in session_groups.items():
                if len(session_memories) >= 2:
                    result = await self.synthesis.process(session_memories)
                    consolidated[session_id] = result
                else:
                    consolidated[session_id] = session_memories
            
            self.last_run = datetime.now()
            
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

    def get_stats(self) -> dict:
        all_memories = self.sqlite.search("", 10000)
        return {
            "total_memories": len(all_memories),
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "interval_hours": self.interval_hours,
            "should_run": self.should_run()
        }
