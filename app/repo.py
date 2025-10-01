import asyncpg
from typing import Optional, List, Dict, Any
from datetime import datetime
from .config import settings

class Repo:
    def __init__(self, dsn: str | None = None):
        self._dsn = dsn or settings.database_url
        self.pool: asyncpg.Pool | None = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=5)

    async def close(self):
        if self.pool:
            await self.pool.close()

    async def migrate(self):
        _ = (await (await self.pool.acquire()).fetchval("SELECT 1"))
        import pathlib
        path = pathlib.Path(__file__).with_name("migrations.sql")
        ddl = path.read_text(encoding="utf-8")
        async with self.pool.acquire() as conn:
            await conn.execute(ddl)

    # --- Users ---
    async def upsert_user(self, tg_id: int, phone: str, iiko_customer_id: str, bonus_balance: int):
        q = """
        INSERT INTO tg_users (tg_id, phone, iiko_customer_id, bonus_balance)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (tg_id) DO UPDATE
        SET phone=EXCLUDED.phone, iiko_customer_id=EXCLUDED.iiko_customer_id,
            bonus_balance=EXCLUDED.bonus_balance, updated_at=now();
        """
        async with self.pool.acquire() as c:
            await c.execute(q, tg_id, phone, iiko_customer_id, bonus_balance)

    async def get_user_by_tg(self, tg_id: int) -> Optional[asyncpg.Record]:
        q = "SELECT * FROM tg_users WHERE tg_id=$1"
        async with self.pool.acquire() as c:
            return await c.fetchrow(q, tg_id)

    async def update_balance(self, tg_id: int, balance: int):
        q = "UPDATE tg_users SET bonus_balance=$2, updated_at=now() WHERE tg_id=$1"
        async with self.pool.acquire() as c:
            await c.execute(q, tg_id, balance)

    async def list_users(self) -> List[asyncpg.Record]:
        q = "SELECT * FROM tg_users"
        async with self.pool.acquire() as c:
            return await c.fetch(q)

    # --- Bonus grants ---
    async def has_welcome_grant(self, iiko_customer_id: str) -> bool:
        q = "SELECT 1 FROM bonus_grants WHERE iiko_customer_id=$1 AND grant_type='WELCOME'"
        async with self.pool.acquire() as c:
            row = await c.fetchrow(q, iiko_customer_id)
            return row is not None

    async def save_welcome_grant(self, iiko_customer_id: str, amount: int):
        q = """
        INSERT INTO bonus_grants (iiko_customer_id, grant_type, amount)
        VALUES ($1, 'WELCOME', $2)
        ON CONFLICT DO NOTHING
        """
        async with self.pool.acquire() as c:
            await c.execute(q, iiko_customer_id, amount)

    # --- Visits ---
    async def visit_exists(self, tg_id: int, order_id: str) -> bool:
        q = "SELECT 1 FROM visits WHERE tg_id=$1 AND order_id=$2"
        async with self.pool.acquire() as c:
            return (await c.fetchrow(q, tg_id, order_id)) is not None

    async def add_visit(self, tg_id: int, order_id: str, visited_at: datetime,
                        bonuses_spent: int, bonuses_earned: int, amount: float, meta: dict):
        q = """
        INSERT INTO visits (tg_id, order_id, visited_at, bonuses_spent, bonuses_earned, amount, meta)
        VALUES ($1,$2,$3,$4,$5,$6,$7)
        """
        async with self.pool.acquire() as c:
            await c.execute(q, tg_id, order_id, visited_at, bonuses_spent, bonuses_earned, amount, meta)

    async def list_visits(self, tg_id: int, limit: int = 10) -> List[asyncpg.Record]:
        q = "SELECT * FROM visits WHERE tg_id=$1 ORDER BY visited_at DESC LIMIT $2"
        async with self.pool.acquire() as c:
            return await c.fetch(q, tg_id, limit)

    # --- Consent ---
    async def set_consent(self, tg_id: int):
        q = "UPDATE tg_users SET pdn_consent_at=now(), updated_at=now() WHERE tg_id=$1"
        async with self.pool.acquire() as c:
            await c.execute(q, tg_id)
