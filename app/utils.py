PLACEHOLDER_CUSTOMER_ID = "00000000-0000-0000-0000-000000000000"


def normalize_phone(raw: str) -> str:
    p = raw.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if not p.startswith("+"):
        if p.startswith("8") and len(p) == 11:
            p = "+7" + p[1:]
        else:
            p = "+" + p
    return p


def has_real_customer_id(customer_id: str | None) -> bool:
    if not customer_id:
        return False
    cid = str(customer_id).strip()
    return bool(cid) and cid != PLACEHOLDER_CUSTOMER_ID
