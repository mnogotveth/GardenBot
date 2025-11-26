import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from .iiko_client import IikoClient
from .utils import normalize_phone


async def probe_transactions(*, phone: str | None, customer_id: str | None, days: int):
    client = IikoClient()
    cid = None

    if customer_id:
        cid = str(customer_id)
    elif phone:
        normalized = normalize_phone(phone)
        info, _ = await client.find_or_create_customer_by_phone(normalized)
        cid = str(info["id"])
        print(f"[ok] resolved phone {normalized} to customer {cid}")

    if not cid:
        raise SystemExit("provide either --customer-id or --phone")

    date_to = datetime.now(timezone.utc)
    date_from = date_to - timedelta(days=days)
    print(f"[info] requesting transactions {date_from.isoformat()}..{date_to.isoformat()}")
    transactions = await client.get_customer_transactions(cid, date_from, date_to)
    print(f"[info] received {len(transactions)} rows")
    for tx in transactions:
        ts = tx.get("operationTime") or tx.get("date") or tx.get("createdAt")
        amount = tx.get("amount") or tx.get("sum")
        tx_type = tx.get("transactionType") or tx.get("type")
        tx_id = tx.get("id") or tx.get("transactionId") or tx.get("orderId")
        print(f"- {ts} amount={amount} type={tx_type} id={tx_id}")


async def main():
    parser = argparse.ArgumentParser(description="Check iiko /customer/transactions access")
    parser.add_argument("--phone", help="Phone number to resolve customer")
    parser.add_argument("--customer-id", help="Customer UUID if already known")
    parser.add_argument("--days", type=int, default=30, help="Lookback window in days")
    args = parser.parse_args()

    await probe_transactions(phone=args.phone, customer_id=args.customer_id, days=args.days)


if __name__ == "__main__":
    asyncio.run(main())
