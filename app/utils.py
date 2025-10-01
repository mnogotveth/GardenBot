def normalize_phone(raw: str) -> str:
    p = raw.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if not p.startswith("+"):
        if p.startswith("8") and len(p) == 11:
            p = "+7" + p[1:]
        else:
            p = "+" + p
    return p
