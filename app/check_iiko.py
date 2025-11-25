import argparse
import asyncio
from datetime import datetime

from .iiko_client import IikoClient
from .config import settings


async def fetch_orgs(client: IikoClient):
    data = await client.ping()
    orgs = data.get("organizations") if isinstance(data, dict) else data
    print("== Organizations ==")
    if not orgs:
        print("No organizations returned")
        return
    for org in orgs:
        print(f"- {org.get('name')} :: {org.get('id')} :: crmId={org.get('crmId')}")


async def fetch_history(client: IikoClient, phone: str):
    orders = await client.get_delivery_history_orders(phone, settings.visits_lookback_days)
    print(f"\nHistory orders ({len(orders)}):")
    for order in orders:
        print(
            f"  #{order.get('externalNumber') or order.get('id')} "
            f"{order.get('status')} sum={order.get('sum')} "
            f"date={order.get('deliveryDate')}"
        )


async def fetch_orders_fallback(client: IikoClient, phone: str):
    orders = await client.get_orders_by_phone(phone, settings.visits_lookback_days)
    print(f"\nFallback orders/by_phone ({len(orders)}):")
    for order in orders:
        closed = order.get("whenClosed") or order.get("closedAt") or ""
        if isinstance(closed, datetime):
            closed = closed.isoformat()
        print(
            f"  #{order.get('orderId') or order.get('id')} "
            f"{order.get('status')} sum={order.get('sum') or order.get('total')} "
            f"closed={closed}"
        )


async def main():
    parser = argparse.ArgumentParser(description="Inspect iiko orgs, orders and counters")
    parser.add_argument("--phone", required=True, help="Phone number, e.g. +7913...")
    parser.add_argument("--customer-id", help="UUID of iiko customer to fetch counters")
    args = parser.parse_args()

    client = IikoClient()
    await fetch_orgs(client)
    await fetch_history(client, args.phone)
    await fetch_orders_fallback(client, args.phone)
    if args.customer_id:
        count = await client.get_orders_count_last_30_days(args.customer_id)
        print(f"\nCounters (orders last 30 days) for {args.customer_id}: {count}")
    else:
        print("\nPass --customer-id <uuid> to check get_counters response")


if __name__ == "__main__":
    asyncio.run(main())
