import sqlite3
import json
from typing import List, Optional, Dict, Any
from datetime import datetime, date
from enum import Enum
from dataclasses import dataclass
import re


class TransactionType(Enum):
    EXPENSE = "expense"
    INCOME = "income"
    TRANSFER = "transfer"


class Category(Enum):
    FOOD = "food"
    TRANSPORT = "transport"
    ENTERTAINMENT = "entertainment"
    SHOPPING = "shopping"
    HEALTH = "health"
    EDUCATION = "education"
    LIVING = "living"
    OTHER = "other"


@dataclass
class Transaction:
    id: str
    type: TransactionType
    amount: float
    category: Category
    description: str
    timestamp: str
    date: str
    session_id: str


class AccountingStorage:
    DB_PATH = "/home/user/.kimaki/projects/xiaoqing/data/accounting.db"

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or self.DB_PATH
        self._ensure_table()

    def _ensure_table(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS accounting (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    amount REAL NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    date TEXT NOT NULL,
                    session_id TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_date ON accounting(date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_type ON accounting(type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON accounting(category)")

    def add(self, tx: Transaction) -> str:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO accounting (id, type, amount, category, description, timestamp, date, session_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tx.id, tx.type.value, tx.amount, tx.category.value,
                tx.description, tx.timestamp, tx.date, tx.session_id
            ))
        return tx.id

    def get_by_date_range(
        self, start_date: str, end_date: Optional[str] = None
    ) -> List[Transaction]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if end_date:
                cursor = conn.execute(
                    "SELECT * FROM accounting WHERE date >= ? AND date <= ? ORDER BY timestamp DESC",
                    (start_date, end_date)
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM accounting WHERE date = ? ORDER BY timestamp DESC",
                    (start_date,)
                )
            return [self._row_to_tx(row) for row in cursor.fetchall()]

    def get_all(self) -> List[Transaction]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM accounting ORDER BY timestamp DESC")
            return [self._row_to_tx(row) for row in cursor.fetchall()]

    def _row_to_tx(self, row: sqlite3.Row) -> Transaction:
        return Transaction(
            id=row["id"],
            type=TransactionType(row["type"]),
            amount=row["amount"],
            category=Category(row["category"]),
            description=row["description"],
            timestamp=row["timestamp"],
            date=row["date"],
            session_id=row["session_id"],
        )


class AccountingParser:
    PATTERNS = [
        (r"(\d+(?:\.\d+)?)\s*(?:元|块|块人民币)", "amount_only"),
        (r"花[了]?(\d+(?:\.\d+)?)\s*(?:元|块|块人民币)", "expense"),
        (r"支[出]?(\d+(?:\.\d+)?)\s*(?:元|块|块人民币)", "expense"),
        (r"買[了]?(\d+(?:\.\d+)?)\s*(?:元|块|块人民币)", "expense"),
        (r"消費[了]?(\d+(?:\.\d+)?)\s*(?:元|块|块人民币)", "expense"),
        (r"赚[了]?(\d+(?:\.\d+)?)\s*(?:元|块|块人民币)", "income"),
        (r"收入[了]?(\d+(?:\.\d+)?)\s*(?:元|块|块人民币)", "income"),
        (r"掙[了]?(\d+(?:\.\d+)?)\s*(?:元|块|块人民币)", "income"),
        (r"得到[了]?(\d+(?:\.\d+)?)\s*(?:元|块|块人民币)", "income"),
        (r"入帳[了]?(\d+(?:\.\d+)?)\s*(?:元|块|块人民币)", "income"),
        (r"入[帳]?(\d+(?:\.\d+)?)\s*(?:元|块|块人民币)", "income"),
    ]

    KEYWORD_CATEGORIES = {
        "food": ["吃", "飯", "食", "餐", "早餐", "午餐", "晚餐", "宵夜", "零食", "飲料", "咖啡", "奶茶", "便當", "麵", "飯", " pizza", "麥當勞", "肯德基"],
        "transport": ["車", "交通費", " bus", "捷運", "地铁", " Uber", "計程車", "公車", "加油", "停車", "过路费", "油錢"],
        "entertainment": ["電影", "游戏", "Netflix", "Disney", "演唱會", " KTV", "唱歌", "酒吧", "音樂", "書", "影集"],
        "shopping": ["買", " shopping", "網購", "淘寶", "蝦皮", "衣服", "鞋子", "包", "禮物"],
        "health": ["醫", "葯", "健康", "体检", "牙醫", "医院", "保健"],
        "education": ["書", "課", "學", "学费", "補習", "教材", "课程"],
        "living": ["房租", "水電", "網路", "電話", "生活", "日常", " bill", "帐单"],
    }

    def parse(self, text: str) -> Optional[Dict[str, Any]]:
        text = text.strip()
        amount = None
        tx_type = None
        category = Category.OTHER
        description = text

        income_kw = ["赚", "收入", "掙", "得到", "入帳", "入"]
        for kw in income_kw:
            if kw in text:
                tx_type = TransactionType.INCOME
                break

        for pattern, mode in self.PATTERNS:
            m = re.search(pattern, text)
            if m:
                amount = float(m.group(1))
                if mode == "expense":
                    tx_type = TransactionType.EXPENSE
                elif mode == "income":
                    tx_type = TransactionType.INCOME
                elif mode == "amount_only":
                    if tx_type is None:
                        tx_type = TransactionType.EXPENSE
                break

        if amount is None:
            numbers = re.findall(r"(\d+(?:\.\d+)?)", text)
            if numbers:
                amount = float(numbers[0])
                if tx_type is None:
                    tx_type = TransactionType.EXPENSE

        if amount is None:
            return None

        for cat_name, keywords in self.KEYWORD_CATEGORIES.items():
            for kw in keywords:
                if kw in text:
                    category = Category(cat_name)
                    break

        if tx_type is None:
            for kw in ["赚", "收入", "掙", "得到"]:
                if kw in text:
                    tx_type = TransactionType.INCOME
                    break
            if tx_type is None:
                tx_type = TransactionType.EXPENSE

        return {
            "amount": amount,
            "type": tx_type,
            "category": category,
            "description": description,
        }


class AccountingService:
    def __init__(self):
        self.storage = AccountingStorage()
        self.parser = AccountingParser()

    def add_transaction(
        self, text: str, session_id: str
    ) -> tuple[bool, str, Optional[Transaction]]:
        parsed = self.parser.parse(text)
        if not parsed:
            return False, "無法解析帳目，請檢查格式", None

        now = datetime.now()
        import uuid
        tx = Transaction(
            id=str(uuid.uuid4()),
            type=parsed["type"],
            amount=parsed["amount"],
            category=parsed["category"],
            description=parsed["description"],
            timestamp=now.isoformat(),
            date=now.strftime("%Y-%m-%d"),
            session_id=session_id,
        )
        self.storage.add(tx)

        emoji = "💸" if tx.type == TransactionType.EXPENSE else "💰"
        type_str = "支出" if tx.type == TransactionType.EXPENSE else "收入"
        return True, f"{emoji} 已記錄：{type_str} {tx.amount:.0f} 元（{tx.category.value}）- {tx.description}", tx

    def get_summary(self, days: int = 30) -> str:
        end_date = datetime.now()
        start_date = end_date.replace(day=1)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        txs = self.storage.get_by_date_range(start_str, end_str)

        if not txs:
            return "本月的帳目還沒有任何記錄喔～開始記錄第一筆吧！"

        total_income = sum(tx.amount for tx in txs if tx.type == TransactionType.INCOME)
        total_expense = sum(tx.amount for tx in txs if tx.type == TransactionType.EXPENSE)
        balance = total_income - total_expense

        cat_totals: Dict[str, float] = {}
        for tx in txs:
            if tx.type == TransactionType.EXPENSE:
                cat_totals[tx.category.value] = cat_totals.get(tx.category.value, 0) + tx.amount

        lines = [
            f"📊 **{end_date.strftime('%Y年%m月')} 月記帳摘要**",
            f"總收入：💰 {total_income:,.0f} 元",
            f"總支出：💸 {total_expense:,.0f} 元",
            f"本月餘額：{'+' if balance >= 0 else ''}{balance:,.0f} 元",
            "",
            "**支出分類：**",
        ]

        sorted_cats = sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)
        for cat, amt in sorted_cats:
            pct = (amt / total_expense * 100) if total_expense > 0 else 0
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            lines.append(f"  {cat:>15} {bar} {pct:5.1f}% ({amt:,.0f} 元)")

        lines.append("")
        lines.append(f"共 {len(txs)} 筆記錄")

        return "\n".join(lines)

    def get_today(self) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        txs = self.storage.get_by_date_range(today)
        if not txs:
            return "今天還沒有記錄喔～"

        lines = [f"📅 **今天 {datetime.now().strftime('%m/%d')} 的記錄**", ""]
        day_income = 0.0
        day_expense = 0.0
        for tx in txs:
            emoji = "💸" if tx.type == TransactionType.EXPENSE else "💰"
            type_str = "支出" if tx.type == TransactionType.EXPENSE else "收入"
            time_str = datetime.fromisoformat(tx.timestamp).strftime("%H:%M")
            lines.append(f"{emoji} [{time_str}] {type_str} {tx.amount:.0f} 元（{tx.category.value}）- {tx.description}")
            if tx.type == TransactionType.INCOME:
                day_income += tx.amount
            else:
                day_expense += tx.amount

        lines.append("")
        lines.append(f"今日合計：收入 {day_income:,.0f} / 支出 {day_expense:,.0f}")
        return "\n".join(lines)

    def get_all(self) -> str:
        txs = self.storage.get_all()
        if not txs:
            return "目前還沒有任何記錄喔～"

        lines = ["📋 **全部帳目記錄**", ""]
        for tx in txs[:50]:
            emoji = "💸" if tx.type == TransactionType.EXPENSE else "💰"
            type_str = "支出" if tx.type == TransactionType.EXPENSE else "收入"
            dt = datetime.fromisoformat(tx.timestamp)
            lines.append(f"{emoji} [{dt.strftime('%m/%d %H:%M')}] {type_str} {tx.amount:.0f} 元（{tx.category.value}）- {tx.description}")

        if len(txs) > 50:
            lines.append(f"\n...還有 {len(txs) - 50} 筆")
        return "\n".join(lines)