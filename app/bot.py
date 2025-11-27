import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    CallbackQuery,
    KeyboardButton,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
)

from .config import settings
from .utils import normalize_phone
from .repo import Repo
from .iiko_client import IikoClient
from .scheduler_tx import start_scheduler

# ----- подписи кнопок -----
BTN_OPEN_POLICY = "📝 Политика"
BTN_CONSENT     = "✅ Я прочитал и согласен"
BTN_SHARE       = "📱 Поделиться номером"
BTN_VISITS      = "🧾 Посещения"
BTN_MENU        = "📖 Меню"
BTN_BALANCE     = "💳 Баланс"

CB_CONSENT_OK   = "consent_ok"

# ----- клавиатуры -----
def kb_share_phone() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_SHARE, request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Нажмите кнопку, чтобы поделиться номером"
    )

def kb_policy() -> ReplyKeyboardMarkup:
    if settings.consent_webapp_url:
        open_btn = KeyboardButton(text=BTN_OPEN_POLICY, web_app=WebAppInfo(url=settings.consent_webapp_url))
    else:
        open_btn = KeyboardButton(text=BTN_OPEN_POLICY)
    return ReplyKeyboardMarkup(
        keyboard=[
            [open_btn],
            [KeyboardButton(text=BTN_CONSENT)],
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )

def kb_main() -> ReplyKeyboardMarkup:
    main_row = [KeyboardButton(text=BTN_BALANCE), KeyboardButton(text=BTN_VISITS)]
    if settings.menu_webapp_url:
        menu_btn = KeyboardButton(text=BTN_MENU, web_app=WebAppInfo(url=settings.menu_webapp_url))
    else:
        menu_btn = KeyboardButton(text=BTN_MENU)
    return ReplyKeyboardMarkup(
        keyboard=[main_row, [menu_btn]],
        resize_keyboard=True,
        one_time_keyboard=False
    )

def ikb_consent() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✅ Я прочитал(а) и согласен(на)", callback_data=CB_CONSENT_OK)]]
    )

def ikb_menu_url():
    if settings.menu_url:
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Открыть меню", url=settings.menu_url)]])
    return None

# ----- init -----
bot = Bot(settings.bot_token)
dp = Dispatcher()

repo = Repo(settings.database_url)
iiko = IikoClient()
# сохраняем APScheduler, чтобы его не собрал GC и не остановил синхронизацию визитов
scheduler: AsyncIOScheduler | None = None

async def send_policy_pdf(chat_id: int):
    caption = (
        "Политика обработки персональных данных.\n"
        "Пожалуйста, внимательно ознакомьтесь с документом.\n"
        "После прочтения нажмите кнопку ниже."
    )
    if getattr(settings, "policy_file_id", ""):
        await bot.send_document(chat_id, settings.policy_file_id, caption=caption, reply_markup=ikb_consent())
        return
    if settings.policy_url:
        await bot.send_document(chat_id, settings.policy_url, caption=caption, reply_markup=ikb_consent())
        return
    await bot.send_message(chat_id, "PDF политики не настроен (POLICY_FILE_ID или POLICY_URL).")

async def ensure_registered(m: Message):
    u = await repo.get_user_by_tg(m.from_user.id)
    if not u or not u.get("pdn_consent_at"):
        await m.answer(
            "Перед продолжением, пожалуйста, ознакомьтесь с политикой обработки персональных данных "
            "и подтвердите согласие.",
            reply_markup=kb_policy()
        )
        await send_policy_pdf(chat_id=m.chat.id)
        if not u:
            await repo.upsert_user(
                tg_id=m.from_user.id,
                phone="+",
                iiko_customer_id="00000000-0000-0000-0000-000000000000",
                bonus_balance=0
            )
        return None
    return u

# ----- handlers -----
@dp.message(CommandStart())
async def start(m: Message):
    u = await repo.get_user_by_tg(m.from_user.id)
    if not u or not u.get("pdn_consent_at"):
        await m.answer("Привет! Перед началом работы ознакомьтесь с политикой обработки персональных данных.",
                       reply_markup=kb_policy())
        await send_policy_pdf(chat_id=m.chat.id)
        if not u:
            await repo.upsert_user(
                tg_id=m.from_user.id,
                phone="+",
                iiko_customer_id="00000000-0000-0000-0000-000000000000",
                bonus_balance=0
            )
        return
    await m.answer("Готово! Меню ниже 👇", reply_markup=kb_main())

@dp.message(F.text == BTN_OPEN_POLICY)
async def open_policy(m: Message):
    await send_policy_pdf(chat_id=m.chat.id)

@dp.callback_query(F.data == CB_CONSENT_OK)
async def on_consent_ok(cq: CallbackQuery):
    await repo.set_consent(cq.from_user.id)
    # пробуем проставить согласие и в iiko, если у нас уже известен клиент
    u = await repo.get_user_by_tg(cq.from_user.id)
    if u and u.get("iiko_customer_id"):
        try:
            ok = await iiko.set_consent_true(customer_id=str(u["iiko_customer_id"]), phone=u.get("phone"))
            if not ok:
                print("[WARN] set_consent iiko not confirmed by any variant", flush=True)
        except Exception as e:
            print("[WARN] set_consent iiko failed:", e, flush=True)

    try:
        await cq.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await cq.message.answer("Спасибо! Теперь вы можете поделиться номером телефона 👇", reply_markup=kb_share_phone())
    await cq.answer()

@dp.message(F.web_app_data)
async def on_webapp_data(m: Message):
    data = (m.web_app_data and m.web_app_data.data or "") if hasattr(m, "web_app_data") else ""
    if data and data.lower().startswith("consent:ok"):
        await repo.set_consent(m.from_user.id)
        await m.answer("Спасибо! Теперь вы можете продолжить.", reply_markup=kb_share_phone())
    else:
        await m.answer("Не удалось подтвердить согласие. Попробуйте ещё раз.", reply_markup=kb_policy())

@dp.message(F.text == BTN_CONSENT)
async def manual_consent(m: Message):
    await repo.set_consent(m.from_user.id)
    # если клиента уже знаем — продублируем согласие в iiko
    u = await repo.get_user_by_tg(m.from_user.id)
    if u and u.get("iiko_customer_id"):
        try:
            await iiko.set_consent_true(customer_id=str(u["iiko_customer_id"]), phone=u.get("phone"))
        except Exception as e:
            print("[WARN] set_consent iiko failed:", e, flush=True)
    await m.answer("Спасибо! Теперь вы можете продолжить.", reply_markup=kb_share_phone())

@dp.message(F.contact)
async def got_contact(m: Message):
    try:
        u = await repo.get_user_by_tg(m.from_user.id)
        if not u or not u.get("pdn_consent_at"):
            await m.answer("Сначала подтвердите согласие на обработку ПДн.", reply_markup=kb_policy())
            await send_policy_pdf(chat_id=m.chat.id)
            return

        if not m.contact.user_id or m.contact.user_id != m.from_user.id:
            await m.answer("Пожалуйста, отправьте свой контакт через кнопку.", reply_markup=kb_share_phone())
            return

        phone = normalize_phone(m.contact.phone_number)
        tg_id = m.from_user.id

        customer, is_new = await iiko.find_or_create_customer_by_phone(phone)

        # если согласие уже дано — попробуем синхронизировать его в iiko
        try:
            await iiko.set_consent_true(customer_id=str(customer["id"]), phone=phone)
        except Exception as e:
            print("[WARN] set_consent iiko failed:", e, flush=True)

        if settings.welcome_bonus_enabled and is_new:
            if not await repo.has_welcome_grant(customer["id"]):
                try:
                    comment = f"Welcome bonus via TG {tg_id}-{customer['id']}"
                    await iiko.refill_bonus(customer["id"], settings.welcome_bonus_amount, comment=comment)
                    await repo.save_welcome_grant(customer["id"], settings.welcome_bonus_amount)
                except Exception as e:
                    import traceback
                    print("[WARN] refill failed:", e, traceback.format_exc(), flush=True)

        balance = await iiko.get_bonus_balance(customer["id"])

        await repo.upsert_user(tg_id=tg_id, phone=phone, iiko_customer_id=customer["id"], bonus_balance=balance)

        txt = (
            f"Готово! Ваш бонусный баланс: {balance} 🎉\n"
            f"Бонусами можно оплатить до {settings.max_pay_with_bonus_pct}% чека.\n\n"
            f"Меню ниже 👇"
        )
        await m.answer(txt, reply_markup=kb_main())
        if settings.menu_url:
            ikb = ikb_menu_url()
            if ikb:
                await m.answer("Меню ресторана:", reply_markup=ikb)

    except Exception as e:
        import traceback
        print("[ERR] got_contact failed:", e, traceback.format_exc(), flush=True)
        await m.answer("Временная ошибка подключения к iiko. Попробуйте ещё раз чуть позже 🙏",
                       reply_markup=kb_share_phone())

@dp.message(F.text == BTN_BALANCE)
@dp.message(Command("balance"))
async def balance(m: Message):
    u = await ensure_registered(m)
    if not u:
        return
    try:
        new_balance = await iiko.get_bonus_balance(u["iiko_customer_id"])
        await repo.update_balance(u["tg_id"], new_balance)
        await m.answer(f"Текущий баланс: {new_balance} бонусов ✅", reply_markup=kb_main())
    except Exception as e:
        import traceback
        print("[ERR] /balance:", e, traceback.format_exc(), flush=True)
        await m.answer("Не удалось получить баланс, попробуйте позже 🙏", reply_markup=kb_main())

@dp.message(F.text == BTN_VISITS)
@dp.message(Command("visits"))
async def visits(m: Message):
    u = await ensure_registered(m)
    if not u:
        return
    customer_id = u.get("iiko_customer_id")
    visits_count_30d = 0
    if customer_id:
        try:
            visits_count_30d = await iiko.get_orders_count_last_30_days(str(customer_id))
        except Exception as e:
            import traceback
            print("[ERR] visits counters:", e, traceback.format_exc(), flush=True)
    try:
        items = await repo.list_visits_by_day(m.from_user.id, limit=10)
        if not items:
            header = ""
            if visits_count_30d:
                header = (
                    f"За последние 30 дней вы были в ресторане: {visits_count_30d} раз(а).\n\n"
                )
            await m.answer(
                header + "Пока нет зафиксированных посещений.",
                reply_markup=kb_main()
            )
            return
        txt = "\n".join(
            f"• {v['day']:%d.%m.%Y} списано {int(v['spent'] or 0)}, начислено {int(v['earned'] or 0)}"
            for v in items
        )
        header = ""
        if visits_count_30d:
            header = (
                f"За последние 30 дней вы были в ресторане: {visits_count_30d} раз(а).\n\n"
            )
        await m.answer(header + "Последние посещения:\n" + txt, reply_markup=kb_main())
    except Exception as e:
        import traceback
        print("[ERR] /visits:", e, traceback.format_exc(), flush=True)
        await m.answer("Не удалось получить посещения, попробуйте позже 🙏", reply_markup=kb_main())

@dp.message(F.text == BTN_MENU)
async def open_menu(m: Message):
    if settings.menu_url:
        ikb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Открыть меню", url=settings.menu_url)]]
        )
        await m.answer("Меню ресторана:", reply_markup=ikb)
    else:
        await m.answer("Ссылка на меню пока не настроена. Попросите администратора указать MENU_URL в .env 🙏",
                       reply_markup=kb_main())

# ----- main -----
async def main():
    await repo.connect()
    await repo.migrate()
    global scheduler
    scheduler = start_scheduler(repo, iiko)
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    print("=== GARDEN BOT STARTED FROM DOCKER ===")
    asyncio.run(main())
