from pydantic import BaseModel
import os
from dotenv import load_dotenv
load_dotenv()

class Settings(BaseModel):
    admin_tg_id: int | None = int(os.getenv("ADMIN_TG_ID", "0")) or None 
    bot_token: str = os.getenv("BOT_TOKEN", "")
    iiko_api_base: str = os.getenv("IIKO_API_BASE", "https://api-ru.iiko.services")
    iiko_api_login: str = os.getenv("IIKO_API_LOGIN", "")
    iiko_org_id: str = os.getenv("IIKO_ORG_ID", "")
    database_url: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/iiko_bot")

    welcome_bonus_enabled: bool = os.getenv("WELCOME_BONUS_ENABLED", "true").lower() == "true"
    welcome_bonus_amount: int = int(os.getenv("WELCOME_BONUS_AMOUNT", "100"))
    max_pay_with_bonus_pct: int = int(os.getenv("MAX_PAY_WITH_BONUS_PCT", "50"))

    visits_poll_interval_seconds: int = int(os.getenv("VISITS_POLL_INTERVAL_SECONDS", "300"))
    visits_lookback_days: int = int(os.getenv("VISITS_LOOKBACK_DAYS", "30"))

    menu_url: str = os.getenv("MENU_URL", "")
    menu_webapp_url: str = os.getenv("MENU_WEBAPP_URL", "")

    consent_webapp_url: str = os.getenv("CONSENT_WEBAPP_ID", "")   
    policy_url: str = os.getenv("POLICY_URL", "")
    policy_file_id: str = os.getenv("POLICY_FILE_ID", "")                   

settings = Settings()
