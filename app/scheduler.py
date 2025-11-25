import json
import uuid
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timezone
from .repo import Repo
from .iiko_client import IikoClient
from .config import settings

BONUS_PAYMENT_KEYWORDS = ("bonus", "loyalty", "iikocard", "бонус", "лоял")
BONUS_PAYMENT_KINDS = {"LOYALTY", "LOYALTY_PROGRAM", "BONUS"}


def _is_bonus_payment(payment: dict) -> bool:
    """
    Заказы из iiko приходят с локализованными названиями платежей.
    Пробегаемся по основным полям и ищем признаки бонусного кошелька.
    """
    text_candidates = [
        payment.get("type"),
        payment.get("name"),
        payment.get("comment"),
        (payment.get("paymentType") or {}).get("name"),
    ]
    for raw in text_candidates:
        if raw:
            val = str(raw).lower()
            if any(key in val for key in BONUS_PAYMENT_KEYWORDS):
                return True

    kind_candidates = [
        payment.get("paymentTypeKind"),
        payment.get("kind"),
        (payment.get("paymentType") or {}).get("kind"),
    ]
    for raw in kind_candidates:
        if raw and str(raw).upper() in BONUS_PAYMENT_KINDS:
            return True
    return False


def extract_bonus_spent(order: dict) -> int:
    pays = order.get("payments") or []
    for payment in pays:
        if _is_bonus_payment(payment):
            val = payment.get("sum") or 0
            try:
                return int(round(float(val)))
            except (TypeError, ValueError):
                continue
    return 0

def extract_bonus_earned(order: dict) -> int:
    return int(order.get("bonusAccrued") or 0)

def extract_total(order: dict) -> float:
    return float(
        order.get("total")
        or order.get("sum")
        or order.get("orderSum")
        or order.get("fullSum")
        or 0.0
    )

def extract_closed_at(order: dict) -> datetime:
    val = (
        order.get("closedAt")
        or order.get("whenClosed")
        or order.get("deliveryDate")
        or order.get("orderCloseDate")
        or order.get("whenCreated")
    )
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except Exception:
            return datetime.now(timezone.utc)
    return datetime.now(timezone.utc)

def _extract_order_id(order: dict) -> str | None:
    for key in ("orderId", "id", "deliveryId", "externalNumber", "number"):
        val = order.get(key)
        if val:
            return str(val)
    fingerprint = f"{order.get('deliveryDate')}-{order.get('phone')}-{order.get('sum')}"
    fingerprint = fingerprint.strip("-")
    if not fingerprint:
        return None
    return str(uuid.uuid5(uuid.NAMESPACE_URL, fingerprint))

def _is_order_closed(order: dict) -> bool:
    if order.get("isDeleted"):
        return False
    status = str(
        order.get("status")
        or order.get("orderState")
        or order.get("deliveryStatus")
        or ""
    ).lower()
    if not status:
        return True
    closed_markers = ("close", "deliver", "paid", "complete", "finished")
    return any(marker in status for marker in closed_markers)

def _log_order_debug(user: dict, order: dict):
    """Помогает увидеть сырой ответ iiko для настройки правил."""
    if not settings.visits_debug_log:
        return
    snippet = {
        "tg_id": user.get("tg_id"),
        "phone": user.get("phone"),
        "order_id": order.get("id") or order.get("orderId"),
        "status": order.get("status") or order.get("orderState"),
        "payments": order.get("payments"),
        "bonusAccrued": order.get("bonusAccrued"),
        "total": order.get("total") or order.get("sum"),
    }
    try:
        payload = json.dumps(snippet, ensure_ascii=False, default=str)
    except TypeError:
        payload = str(snippet)
    print(f"[visits-debug] raw_order={payload}", flush=True)

async def sync_visits(repo: Repo, iiko: IikoClient):
    users = await repo.list_users()
    for u in users:
        phone = u.get("phone")
        if not phone or phone == "+":
            continue
        try:
            orders = await iiko.get_delivery_history_orders(phone, settings.visits_lookback_days)
        except httpx.HTTPError as exc:
            print(f"[visits-sync] Failed history lookup for {phone}: {exc}", flush=True)
            orders = []

        if not orders:
            try:
                orders = await iiko.get_orders_by_phone(phone, settings.visits_lookback_days)
            except httpx.HTTPError as exc:
                print(f"[visits-sync] Failed to load orders for {phone}: {exc}", flush=True)
                continue
        if not orders and settings.visits_debug_log:
            print(f"[visits-debug] no orders for phone={phone}", flush=True)

        for o in orders:
            _log_order_debug(u, o)
            if not _is_order_closed(o):
                continue
            order_id = _extract_order_id(o)
            if not order_id:
                continue
            spent = extract_bonus_spent(o)
            earned = extract_bonus_earned(o)
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
