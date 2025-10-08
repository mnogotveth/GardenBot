# import httpx
# import os
# from typing import Tuple, Dict, Any, List
# from datetime import datetime, timedelta, timezone
# from .config import settings

# BASE = settings.iiko_api_base

# PATH_TOKEN       = "/api/1/access_token"
# PATH_ORGS        = "/api/1/organizations"
# PATH_CUST_FIND   = "/api/1/loyalty/iiko/customer/info"
# PATH_CUST_CREATE = "/api/1/loyalty/iiko/customer/create_or_update"
# PATH_BALANCE     = "/api/1/loyalty/balance"
# PATH_REFILL      = "/api/1/customers/refill_balance"
# PATH_ORDERS      = "/api/1/orders/by_phone"
# CONSENT_OK = 1

# def _mask_phone(p: str) -> str:
#     if not p:
#         return ""
#     p = p.replace(" ", "")
#     return p[:4] + "****" + p[-2:] if len(p) >= 6 else "***"

# def _mask_uuid(u: str) -> str:
#     s = str(u)
#     return (s[:8] + "****" + s[-4:]) if len(s) >= 12 else "***"

# DEBUG_LOGS = (os.getenv("LOG_LEVEL", "INFO").upper() == "DEBUG")
# def _dbg(msg: str):
#     if DEBUG_LOGS:
#         print(msg, flush=True)


# class IikoClient:
#     def __init__(self):
#         self._token: str | None = None

#     async def _refresh_token(self):
#         async with httpx.AsyncClient(timeout=20) as r:
#             resp = await r.post(f"{BASE}{PATH_TOKEN}", json={"apiLogin": settings.iiko_api_login})
#             resp.raise_for_status()
#             self._token = resp.json()["token"]

#     async def _request(self, path: str, payload: dict) -> httpx.Response:
#         for attempt in (1, 2):
#             if not self._token:
#                 await self._refresh_token()
#             async with httpx.AsyncClient(timeout=30, headers={"Authorization": f"Bearer {self._token}"}) as r:
#                 resp = await r.post(f"{BASE}{path}", json=payload)
#             if resp.status_code == 401 and attempt == 1:
#                 _dbg(f"[IIKO 401] {path} → refresh token")
#                 self._token = None
#                 continue
#             if resp.status_code >= 400:
#                 _dbg(f"[IIKO ERR] {path} {resp.status_code}")
#             resp.raise_for_status()
#             return resp
#         raise RuntimeError("unreachable")

#     async def ping(self) -> Dict[str, Any]:
#         resp = await self._request(PATH_ORGS, {"apiLogin": settings.iiko_api_login})
#         return resp.json()
    
#     async def _find_by_phone(self, phone: str) -> dict | None:
#         org_id = str(settings.iiko_org_id)
#         payloads = [
#             {"organizationId": org_id, "type": "phone", "phone": phone},
#             {"organizationId": org_id, "phone": phone},
#         ]
#         for p in payloads:
#             try:
#                 res = await self._request(PATH_CUST_FIND, p)
#                 data = res.json() or {}
#                 _dbg(f"[IIKO FIND OK] phone={_mask_phone(p.get('phone',''))} id={_mask_uuid(data.get('id',''))}")
#                 if isinstance(data, dict) and data.get("id"):
#                     return data
#             except httpx.HTTPStatusError as e:
#                 code = e.response.status_code if e.response else "n/a"
#                 _dbg(f"[IIKO FIND ERR] phone={_mask_phone(p.get('phone',''))} code={code}")
#                 continue
#         return None

#     async def _get_customer_info_by_id(self, customer_id: Any) -> dict | None:
#         """fallback: достаём кошельки из customer/info по id."""
#         org_id = str(settings.iiko_org_id)
#         cid = str(customer_id)
#         payloads = [
#             {"organizationId": org_id, "type": "id", "id": cid},
#             {"organizationId": org_id, "customerId": cid},
#         ]
#         for p in payloads:
#             try:
#                 res = await self._request(PATH_CUST_FIND, p)
#                 data = res.json() or {}
#                 _dbg(f"[IIKO INFO BY ID OK] id={_mask_uuid(p.get('id') or p.get('customerId',''))}")
#                 if isinstance(data, dict) and data.get("id"):
#                     return data
#             except httpx.HTTPStatusError as e:
#                 code = e.response.status_code if e.response else "n/a"
#                 _dbg(f"[IIKO INFO BY ID ERR] id={_mask_uuid(p.get('id') or p.get('customerId',''))} code={code}")
#                 continue
#         return None

#     async def _create_or_update_by_phone(self, phone: str) -> dict:
#         org_id = str(settings.iiko_org_id)
#         payload = {"organizationId": org_id, "phone": phone}
#         res = await self._request(PATH_CUST_CREATE, payload)
#         data = res.json() or {}
#         _dbg(f"[IIKO CREATE] phone={_mask_phone(payload.get('phone',''))} id={_mask_uuid(data.get('id',''))}")
#         if not isinstance(data, dict) or not data.get("id"):
#             raise ValueError(f"customer create_or_update returned no id: {data}")
#         return data

#     async def find_or_create_customer_by_phone(self, phone: str) -> tuple[dict, bool]:
#         before = await self._find_by_phone(phone)
#         if before:
#             return before, False
#         created = await self._create_or_update_by_phone(phone)
#         after = await self._find_by_phone(phone)
#         if not after:
#             raise RuntimeError(f"Customer not visible after create. create_resp={created}")
#         return after, True

#     # ---------- балансы ----------
#     def _deep_find_wallet_nodes(self, data: dict | list) -> list:
#         acc: list = []
#         def walk(x):
#             if isinstance(x, dict):
#                 for key in ("walletBalances", "balances", "wallets"):
#                     if isinstance(x.get(key), list):
#                         acc.extend(x[key])
#                 for v in x.values():
#                     walk(v)
#             elif isinstance(x, list):
#                 for v in x:
#                     walk(v)
#         walk(data)
#         return acc

#     def _normalize_wallet(self, raw: dict) -> dict:
#         wt = raw.get("walletType") or {}
#         return {
#             "id":  raw.get("walletTypeId") or wt.get("id") or raw.get("walletId") or "",
#             "name": (raw.get("name") or wt.get("name") or "").strip(),
#             "balance": float(raw.get("balance") or raw.get("points") or raw.get("amount") or 0),
#         }

#     async def _extract_wallets_from_any(self, data: dict | list) -> list[dict]:
#         if isinstance(data, dict) and "balance" in data and not data.get("walletBalances"):
#             return [{"id": "", "name": "Бонусы", "balance": float(data.get("balance", 0))}]
#         nodes = self._deep_find_wallet_nodes(data)
#         return [self._normalize_wallet(n) for n in nodes if isinstance(n, dict)]

#     async def get_wallet_balances(self, customer_id: Any) -> list[dict]:
#         """1) /loyalty/balance; 2) если пусто — customer/info по ID."""
#         org_id = str(settings.iiko_org_id)
#         cust_id = str(customer_id)
#         # основной путь
#         res = await self._request(PATH_BALANCE, {
#             "organizationId": org_id,
#             "customerId": cust_id
#         })
#         data = res.json() or {}
#         wallets = await self._extract_wallets_from_any(data)
#         if wallets:
#             _dbg(f"[IIKO WALLET LIST] count={len(wallets)}")
#             return wallets

#         # fallback
#         info = await self._get_customer_info_by_id(cust_id)
#         wallets = await self._extract_wallets_from_any(info or {})
#         _dbg(f"[IIKO WALLET LIST (fallback info)] count={len(wallets)}")
#         return wallets

#     async def get_bonus_balance(self, customer_id: Any) -> int:
#         wallets = await self.get_wallet_balances(customer_id)
#         if not wallets:
#             return 0

#         wallet_id_pref = getattr(settings, "loyalty_wallet_id", "") or ""
#         wallet_name_pref = getattr(settings, "loyalty_wallet_name", "") or ""

#         if wallet_id_pref:
#             for w in wallets:
#                 if w["id"] == wallet_id_pref:
#                     return int(round(w["balance"]))

#         if wallet_name_pref:
#             key = wallet_name_pref.lower()
#             for w in wallets:
#                 if key in (w["name"] or "").lower():
#                     return int(round(w["balance"]))

#         best = None
#         for w in wallets:
#             nm = (w["name"] or "").lower()
#             if "сертифик" in nm or "cert" in nm:
#                 continue
#             if best is None or w["balance"] > best["balance"]:
#                 best = w
#         if best:
#             return int(round(best["balance"]))
#         return int(round(sum(w["balance"] for w in wallets)))

#     async def refill_bonus(self, customer_id: Any, amount: int, comment: str = "Welcome bonus"):
#         org_id = str(settings.iiko_org_id)
#         cust_id = str(customer_id)
#         res = await self._request(PATH_REFILL, {
#             "organizationId": org_id,
#             "customerId": cust_id,
#             "sum": amount,
#             "comment": comment
#         })
#         return res.json()

#     async def get_orders_by_phone(self, phone: str, lookback_days: int) -> List[Dict[str, Any]]:
#         """Если права на /orders/by_phone отсутствуют — тихо возвращаем пустой список."""
#         org_id = str(settings.iiko_org_id)
#         since = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()
#         try:
#             res = await self._request(PATH_ORDERS, {
#                 "organizationId": org_id,
#                 "phone": phone,
#                 "dateFrom": since
#             })
#         except httpx.HTTPStatusError as e:
#             if e.response is not None and e.response.status_code == 401:
#                 _dbg("[IIKO ORDERS] 401: not allowed — skipping visits sync")
#                 return []
#             raise
#         js = res.json()
#         return js if isinstance(js, list) else (js or {}).get("orders", [])
import httpx
import os
from typing import Any, Dict, List
from datetime import datetime, timedelta, timezone
from .config import settings

BASE = settings.iiko_api_base

PATH_TOKEN       = "/api/1/access_token"
PATH_ORGS        = "/api/1/organizations"
PATH_CUST_FIND   = "/api/1/loyalty/iiko/customer/info"
PATH_CUST_CREATE = "/api/1/loyalty/iiko/customer/create_or_update"
PATH_BALANCE     = "/api/1/loyalty/balance"
PATH_REFILL      = "/api/1/customers/refill_balance"
PATH_ORDERS      = "/api/1/orders/by_phone"

# 1 — «есть согласие» в iiko
CONSENT_OK = 1

def _mask_phone(p: str) -> str:
    if not p:
        return ""
    p = p.replace(" ", "")
    return p[:4] + "****" + p[-2:] if len(p) >= 6 else "***"

def _mask_uuid(u: str) -> str:
    s = str(u)
    return (s[:8] + "****" + s[-4:]) if len(s) >= 12 else "***"

DEBUG_LOGS = (os.getenv("LOG_LEVEL", "INFO").upper() == "DEBUG")
def _dbg(msg: str):
    if DEBUG_LOGS:
        print(msg, flush=True)


class IikoClient:
    def __init__(self):
        self._token: str | None = None

    async def _refresh_token(self):
        async with httpx.AsyncClient(timeout=20) as r:
            resp = await r.post(f"{BASE}{PATH_TOKEN}", json={"apiLogin": settings.iiko_api_login})
            resp.raise_for_status()
            self._token = resp.json()["token"]

    async def _request(self, path: str, payload: dict) -> httpx.Response:
        for attempt in (1, 2):
            if not self._token:
                await self._refresh_token()
            async with httpx.AsyncClient(timeout=30, headers={"Authorization": f"Bearer {self._token}"}) as r:
                resp = await r.post(f"{BASE}{path}", json=payload)
            if resp.status_code == 401 and attempt == 1:
                _dbg(f"[IIKO 401] {path} → refresh token")
                self._token = None
                continue
            if resp.status_code >= 400:
                _dbg(f"[IIKO ERR] {path} {resp.status_code}")
            resp.raise_for_status()
            return resp
        raise RuntimeError("unreachable")

    async def ping(self) -> Dict[str, Any]:
        resp = await self._request(PATH_ORGS, {"apiLogin": settings.iiko_api_login})
        return resp.json()

    # ---------- поиск/создание клиента ----------
    async def _find_by_phone(self, phone: str) -> dict | None:
        org_id = str(settings.iiko_org_id)
        payloads = [
            {"organizationId": org_id, "type": "phone", "phone": phone},
            {"organizationId": org_id, "phone": phone},
        ]
        for p in payloads:
            try:
                res = await self._request(PATH_CUST_FIND, p)
                data = res.json() or {}
                _dbg(f"[IIKO FIND OK] phone={_mask_phone(p.get('phone',''))} id={_mask_uuid(data.get('id',''))}")
                if isinstance(data, dict) and data.get("id"):
                    return data
            except httpx.HTTPStatusError as e:
                code = e.response.status_code if e.response else "n/a"
                _dbg(f"[IIKO FIND ERR] phone={_mask_phone(p.get('phone',''))} code={code}")
                continue
        return None

    async def _get_customer_info_by_id(self, customer_id: Any) -> dict | None:
        org_id = str(settings.iiko_org_id)
        cid = str(customer_id)
        payloads = [
            {"organizationId": org_id, "type": "id", "id": cid},
            {"organizationId": org_id, "customerId": cid},
        ]
        for p in payloads:
            try:
                res = await self._request(PATH_CUST_FIND, p)
                data = res.json() or {}
                _dbg(f"[IIKO INFO BY ID OK] id={_mask_uuid(p.get('id') or p.get('customerId',''))}")
                if isinstance(data, dict) and data.get("id"):
                    return data
            except httpx.HTTPStatusError as e:
                code = e.response.status_code if e.response else "n/a"
                _dbg(f"[IIKO INFO BY ID ERR] id={_mask_uuid(p.get('id') or p.get('customerId',''))} code={code}")
                continue
        return None

    async def _create_or_update_by_phone(self, phone: str) -> dict:
        org_id = str(settings.iiko_org_id)
        payload = {"organizationId": org_id, "phone": phone}
        res = await self._request(PATH_CUST_CREATE, payload)
        data = res.json() or {}
        _dbg(f"[IIKO CREATE] phone={_mask_phone(payload.get('phone',''))} id={_mask_uuid(data.get('id',''))}")
        if not isinstance(data, dict) or not data.get("id"):
            raise ValueError(f"customer create_or_update returned no id: {data}")
        return data

    async def find_or_create_customer_by_phone(self, phone: str) -> tuple[dict, bool]:
        before = await self._find_by_phone(phone)
        if before:
            return before, False
        created = await self._create_or_update_by_phone(phone)
        after = await self._find_by_phone(phone)
        if not after:
            raise RuntimeError(f"Customer not visible after create. create_resp={created}")
        return after, True

    # ---------- согласие в iiko ----------
    async def set_consent_true(self, *, customer_id: str | None = None, phone: str | None = None) -> bool:
        """
        Проставляет «есть согласие» (CONSENT_OK) с перебором разных контрактов.
        Возвращает True при первом успешном варианте.
        """
        org = str(settings.iiko_org_id)
        cid = str(customer_id) if customer_id else None

        variants = [
            {"organizationId": org, "id": cid, "consentStatus": CONSENT_OK} if cid else None,
            {"organizationId": org, "customerId": cid, "consentStatus": CONSENT_OK} if cid else None,
            {"organizationId": org, "phone": phone, "consentStatus": CONSENT_OK} if phone else None,
            {"organizationId": org, "customer": {"id": cid, "consentStatus": CONSENT_OK}} if cid else None,
            {"organizationId": org, "customers": [{"id": cid, "consentStatus": CONSENT_OK}]} if cid else None,
        ]
        for payload in [v for v in variants if v]:
            try:
                await self._request(PATH_CUST_CREATE, payload)
                _dbg(f"[IIKO CONSENT OK] id={_mask_uuid(cid or '')} phone={_mask_phone(phone or '')}")
                return True
            except httpx.HTTPStatusError as e:
                _dbg(f"[IIKO CONSENT TRY FAIL] code={e.response.status_code if e.response else 'n/a'} "
                     f"id={_mask_uuid(cid or '')} phone={_mask_phone(phone or '')}")
                continue
            except Exception:
                continue
        return False

    # ---------- балансы ----------
    def _deep_find_wallet_nodes(self, data: dict | list) -> list:
        acc: list = []
        def walk(x):
            if isinstance(x, dict):
                for key in ("walletBalances", "balances", "wallets"):
                    if isinstance(x.get(key), list):
                        acc.extend(x[key])
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
        walk(data)
        return acc

    def _normalize_wallet(self, raw: dict) -> dict:
        wt = raw.get("walletType") or {}
        return {
            "id":  raw.get("walletTypeId") or wt.get("id") or raw.get("walletId") or "",
            "name": (raw.get("name") or wt.get("name") or "").strip(),
            "balance": float(raw.get("balance") or raw.get("points") or raw.get("amount") or 0),
        }

    async def _extract_wallets_from_any(self, data: dict | list) -> list[dict]:
        if isinstance(data, dict) and "balance" in data and not data.get("walletBalances"):
            return [{"id": "", "name": "Бонусы", "balance": float(data.get("balance", 0))}]
        nodes = self._deep_find_wallet_nodes(data)
        return [self._normalize_wallet(n) for n in nodes if isinstance(n, dict)]

    async def get_wallet_balances(self, customer_id: Any) -> list[dict]:
        org_id = str(settings.iiko_org_id)
        cust_id = str(customer_id)
        res = await self._request(PATH_BALANCE, {
            "organizationId": org_id,
            "customerId": cust_id
        })
        data = res.json() or {}
        wallets = await self._extract_wallets_from_any(data)
        if wallets:
            _dbg(f"[IIKO WALLET LIST] count={len(wallets)}")
            return wallets

        info = await self._get_customer_info_by_id(cust_id)
        wallets = await self._extract_wallets_from_any(info or {})
        _dbg(f"[IIKO WALLET LIST (fallback info)] count={len(wallets)}")
        return wallets

    async def get_bonus_balance(self, customer_id: Any) -> int:
        wallets = await self.get_wallet_balances(customer_id)
        if not wallets:
            return 0

        wallet_id_pref = getattr(settings, "loyalty_wallet_id", "") or ""
        wallet_name_pref = getattr(settings, "loyalty_wallet_name", "") or ""

        if wallet_id_pref:
            for w in wallets:
                if w["id"] == wallet_id_pref:
                    return int(round(w["balance"]))

        if wallet_name_pref:
            key = wallet_name_pref.lower()
            for w in wallets:
                if key in (w["name"] or "").lower():
                    return int(round(w["balance"]))

        best = None
        for w in wallets:
            nm = (w["name"] or "").lower()
            if "сертифик" in nm or "cert" in nm:
                continue
            if best is None or w["balance"] > best["balance"]:
                best = w
        if best:
            return int(round(best["balance"]))
        return int(round(sum(w["balance"] for w in wallets)))

    async def refill_bonus(self, customer_id: Any, amount: int, comment: str = "Welcome bonus"):
        org_id = str(settings.iiko_org_id)
        cust_id = str(customer_id)
        res = await self._request(PATH_REFILL, {
            "organizationId": org_id,
            "customerId": cust_id,
            "sum": amount,
            "comment": comment
        })
        return res.json()

    async def get_orders_by_phone(self, phone: str, lookback_days: int) -> List[Dict[str, Any]]:
        org_id = str(settings.iiko_org_id)
        since = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()
        try:
            res = await self._request(PATH_ORDERS, {
                "organizationId": org_id,
                "phone": phone,
                "dateFrom": since
            })
        except httpx.HTTPStatusError as e:
            if e.response is not None and e.response.status_code == 401:
                _dbg("[IIKO ORDERS] 401: not allowed — skipping visits sync")
                return []
            raise
        js = res.json()
        return js if isinstance(js, list) else (js or {}).get("orders", [])
