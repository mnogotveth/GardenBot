from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta, timezone, date, time
from decimal import Decimal
import uuid
import json
from .repo import Repo
from .iiko_client import IikoClient
from .config import settings


def _normalize_dt(val):
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except Exception:
            return datetime.now(timezone.utc)
    return datetime.now(timezone.utc)


def _detect_spent_earned(tx: dict) -> tuple[int, int]:
    amount = float(tx.get("amount") or tx.get("sum") or 0)
    spent = int(abs(amount)) if amount < 0 else 0
    earned = int(amount) if amount > 0 else 0
    if not spent and not earned:
        kind = str(tx.get("transactionType") or tx.get("type") or "").lower()
        if "write" in kind or "spend" in kind or "charge" in kind:
            spent = int(abs(amount))
        if "accru" in kind or "top" in kind or "bonus" in kind:
            earned = int(abs(amount))
    return spent, earned


def _amount_from_tx(tx: dict) -> float:
    return float(tx.get("orderSum") or tx.get("checkSum") or tx.get("amount") or tx.get("sum") or 0)


def _json_safe(value):
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, set):
        return [_json_safe(v) for v in value]
    return value


def _build_tx_id(tx: dict) -> str:
    raw = tx.get("id") or tx.get("transactionId") or tx.get("orderId")
    if raw:
        raw = str(raw)
        try:
            uuid.UUID(raw)
            return raw
        except ValueError:
            return str(uuid.uuid5(uuid.NAMESPACE_URL, raw))
    base = f"{tx.get('operationTime')}-{tx.get('amount')}-{tx.get('transactionType')}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, base))


async def sync_visits(repo: Repo, iiko: IikoClient):
    users = await repo.list_users()
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=settings.visits_lookback_days)
    for u in users:
        customer_id = u.get("iiko_customer_id")
        if not customer_id:
            continue
        try:
            transactions = await iiko.get_customer_transactions(customer_id, since, now)
        except Exception as exc:
            print(f"[visits-sync] transactions failed for {customer_id}: {exc}", flush=True)
            continue
        for tx in transactions:
            tx_id = _build_tx_id(tx)
            if await repo.visit_exists(u["tg_id"], tx_id):
                continue
            visited_at = _normalize_dt(tx.get("operationTime") or tx.get("date") or tx.get("createdAt"))
            spent, earned = _detect_spent_earned(tx)
            await repo.add_visit(
                tg_id=u["tg_id"],
                order_id=tx_id,
                visited_at=visited_at,
                bonuses_spent=spent,
                bonuses_earned=earned,
                amount=_amount_from_tx(tx),
                meta=json.dumps(_json_safe({"source": "iiko_tx", "raw": tx}), ensure_ascii=False),
            )


def start_scheduler(repo: Repo, iiko: IikoClient):
    sched = AsyncIOScheduler()
    sched.add_job(sync_visits, "interval",
                  seconds=settings.visits_poll_interval_seconds,
                  args=[repo, iiko], id="sync_visits", replace_existing=True)
    sched.start()
    return sched
