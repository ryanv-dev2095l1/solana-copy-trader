import asyncio
import aiosqlite
from typing import Optional, Dict, Any, List
from pathlib import Path


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS seen_transactions (
    signature TEXT PRIMARY KEY,
    wallet TEXT NOT NULL,
    slot INTEGER NOT NULL,
    seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS positions (
    token_mint TEXT PRIMARY KEY,
    symbol TEXT,
    amount_in_lamports INTEGER NOT NULL,
    token_amount INTEGER NOT NULL,
    buy_signature TEXT NOT NULL,
    buy_slot INTEGER NOT NULL,
    opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'open'
);

CREATE TABLE IF NOT EXISTS execution_latencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signature TEXT NOT NULL,
    target_wallet TEXT NOT NULL,
    detection_ms REAL NOT NULL,
    simulation_ms REAL,
    submission_ms REAL NOT NULL,
    total_ms REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_seen_wallet ON seen_transactions(wallet);
CREATE INDEX IF NOT EXISTS idx_latency_created ON execution_latencies(created_at);
"""


class Database:
    """Local SQLite store for deduplicating incoming swaps and keeping active positions."""

    def __init__(self, db_path: str = "bot.db"):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def connect(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        # wal mode setup needs script exec before regular queries
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def is_tx_seen(self, signature: str) -> bool:
        if not self._conn:
            raise RuntimeError("Database not connected")
        async with self._conn.execute(
            "SELECT 1 FROM seen_transactions WHERE signature = ? LIMIT 1",
            (signature,),
        ) as cur:
            row = await cur.fetchone()
            return row is not None

    async def mark_tx_seen(self, signature: str, wallet: str, slot: int):
        async with self._lock:
            await self._conn.execute(
                "INSERT OR IGNORE INTO seen_transactions (signature, wallet, slot) VALUES (?, ?, ?)",
                (signature, wallet, slot),
            )
            await self._conn.commit()

    async def save_position(
        self,
        token_mint: str,
        symbol: str,
        amount_in_lamports: int,
        token_amount: int,
        buy_signature: str,
        buy_slot: int,
    ):
        async with self._lock:
            await self._conn.execute(
                """
                INSERT OR REPLACE INTO positions (
                    token_mint, symbol, amount_in_lamports, token_amount, buy_signature, buy_slot, status
                ) VALUES (?, ?, ?, ?, ?, ?, 'open')
                """,
                (token_mint, symbol, amount_in_lamports, token_amount, buy_signature, buy_slot),
            )
            await self._conn.commit()

    async def get_open_positions(self) -> List[Dict[str, Any]]:
        async with self._conn.execute(
            "SELECT * FROM positions WHERE status = 'open'"
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def close_position(self, token_mint: str):
        async with self._lock:
            await self._conn.execute(
                "UPDATE positions SET status = 'closed' WHERE token_mint = ?",
                (token_mint,),
            )
            await self._conn.commit()

    async def log_latency(
        self,
        signature: str,
        target_wallet: str,
        detection_ms: float,
        simulation_ms: Optional[float],
        submission_ms: float,
        total_ms: float,
    ):
        # print(f"[debug] logging latency: {total_ms:.1f}ms")
        async with self._lock:
            await self._conn.execute(
                """
                INSERT INTO execution_latencies (
                    signature, target_wallet, detection_ms, simulation_ms, submission_ms, total_ms
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (signature, target_wallet, detection_ms, simulation_ms, submission_ms, total_ms),
            )
            await self._conn.commit()

    async def prune_old_seen(self, keep_latest: int = 50000):
        # Keep DB from growing without bound if daemon runs for weeks
        async with self._lock:
            await self._conn.execute(
                """
                DELETE FROM seen_transactions
                WHERE signature NOT IN (
                    SELECT signature FROM seen_transactions
                    ORDER BY seen_at DESC LIMIT ?
                )
                """,
                (keep_latest,),
            )
            await self._conn.commit()
