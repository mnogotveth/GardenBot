CREATE TABLE IF NOT EXISTS tg_users (
  tg_id             BIGINT PRIMARY KEY,
  phone             TEXT NOT NULL,
  iiko_customer_id  UUID,
  bonus_balance     INTEGER DEFAULT 0,
  pdn_consent_at    TIMESTAMPTZ,           -- ⬅️ когда пользователь дал согласие
  created_at        TIMESTAMPTZ DEFAULT now(),
  updated_at        TIMESTAMPTZ DEFAULT now()
);

-- На случай, если таблица уже была создана раньше — добавим колонку
ALTER TABLE tg_users ADD COLUMN IF NOT EXISTS pdn_consent_at TIMESTAMPTZ;

-- Разовые гранты (чтобы не выдать приветствие дважды)
CREATE TABLE IF NOT EXISTS bonus_grants (
  id                BIGSERIAL PRIMARY KEY,
  iiko_customer_id  UUID NOT NULL,
  grant_type        TEXT NOT NULL,          -- 'WELCOME'
  amount            INTEGER NOT NULL,
  granted_at        TIMESTAMPTZ DEFAULT now(),
  UNIQUE (iiko_customer_id, grant_type)
);

-- Посещения (фиксируем по списаниям бонусов)
CREATE TABLE IF NOT EXISTS visits (
  id                BIGSERIAL PRIMARY KEY,
  tg_id             BIGINT REFERENCES tg_users(tg_id),
  order_id          UUID,
  visited_at        TIMESTAMPTZ NOT NULL,
  bonuses_spent     INTEGER DEFAULT 0,
  bonuses_earned    INTEGER DEFAULT 0,
  amount            NUMERIC(10,2),
  meta              JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_tg_users_phone ON tg_users((lower(phone)));
