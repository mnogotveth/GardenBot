from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timezone
from .repo import Repo
from .iiko_client import IikoClient
from .config import settings

def extract_bonus_spent(order: dict) -> int:
    pays = order.get("payments") or []
    for p in pays:
        if str(p.get("type")).lower().find("bonus") >= 0 or str(p.get("name")).lower().find("bonus") >= 0:
            return int(p.get("sum") or 0)
    return 0

def extract_bonus_earned(order: dict) -> int:
    return int(order.get("bonusAccrued") or 0)

def extract_total(order: dict) -> float:
    return float(order.get("total") or order.get("sum") or 0.0)

def extract_closed_at(order: dict) -> datetime:
    val = order.get("closedAt") or order.get("whenClosed") or order.get("whenCreated")
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except Exception:
            return datetime.now(timezone.utc)
    return datetime.now(timezone.utc)

async def sync_visits(repo: Repo, iiko: IikoClient):
    users = await repo.list_users()
    for u in users:
        orders = await iiko.get_orders_by_phone(u["phone"], settings.visits_lookback_days)
        for o in orders:
            spent = extract_bonus_spent(o)
            earned = extract_bonus_earned(o)
            if spent > 0:
                order_id = str(o.get("id") or o.get("orderId"))
                if not order_id:
                    continue
                if not await repo.visit_exists(u["tg_id"], order_id):
                    await repo.add_visit(
                        tg_id=u["tg_id"],
                        order_id=order_id,
                        visited_at=extract_closed_at(o),
                        bonuses_spent=spent,
                        bonuses_earned=earned,
                        amount=extract_total(o),
                        meta=o
                    )

def start_scheduler(repo: Repo, iiko: IikoClient):
    sched = AsyncIOScheduler()
    sched.add_job(sync_visits, "interval",
                  seconds=settings.visits_poll_interval_seconds,
                  args=[repo, iiko], id="sync_visits", replace_existing=True)
    sched.start()
    return sched
