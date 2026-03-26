import os
from datetime import datetime
from typing import List
from ..models.memory_unit import MemoryUnit


class MarkdownBackup:
    def __init__(self, backup_dir: str = "./data/backups"):
        self.backup_dir = backup_dir
        os.makedirs(backup_dir, exist_ok=True)

    def add_memory(self, memory: MemoryUnit):
        date = datetime.now().strftime("%Y-%m-%d")
        filename = f"{self.backup_dir}/{date}.md"
        
        entry = f"""## {memory.timestamp}

- **主題**: {memory.topic}
- **關鍵詞**: {", ".join(memory.keywords)}
- **涉及人員**: {", ".join(memory.persons) if memory.persons else "無"}
- **記憶**: {memory.lossless_text}
{memory.provenance if memory.provenance else ""}

---
"""
        
        with open(filename, "a", encoding="utf-8") as f:
            f.write(entry)

    def get_memories_by_date(self, date: str) -> List[str]:
        filename = f"{self.backup_dir}/{date}.md"
        if not os.path.exists(filename):
            return []
        with open(filename, "r", encoding="utf-8") as f:
            return f.readlines()
