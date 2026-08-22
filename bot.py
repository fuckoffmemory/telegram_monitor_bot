import asyncio
import logging
import os
import time
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram import F
import aiohttp
import traceback

from config import ADMIN_ID, BOT_TOKEN, CHECK_INTERVAL
from database import *
from parser import fetch_items_for_keyword

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

print("🚀 Запуск бота...")

if not BOT_TOKEN or BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
    print("❌ ОШИБКА: BOT_TOKEN не настроен!")
    exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

user_main_message = {}
user_notify_interval = {}

currency_cache = {
    "cny_to_usd": 0.14,
    "cny_to_rub": 12.5,
    "last_update": 0
}

async def update_currency():
    global currency_cache
    now = time.time()
    if now - currency_cache["last_update"] < 3600:
        return
    try:
        async with aiohttp.ClientSession() as session:
            resp = await session.get("https://api.exchangerate-api.com/v4/latest/CNY", timeout=10)
            data = await resp.json()
            currency_cache["cny_to_usd"] = data["rates"].get("USD", 0.14)
            currency_cache["cny_to_rub"] = data["rates"].get("RUB", 12.5)
            currency_cache["last_update"] = now
            logger.info("Курсы обновлены")
    except Exception as e:
        logger.error(f"Ошибка курсов: {e}")

def convert_price(cny):
    usd = cny * currency_cache["cny_to_usd"]
    rub = cny * currency_cache["cny_to_rub"]
    return round(usd, 2), round(rub, 2)

# --- Клавиатура ---

async def get_keyboard(user_id):
    criteria = get_user_criteria(user_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="➕ Добавить фильтр", callback_data="add_criteria")
    ])
    
    for cid, keyword, max_price in criteria:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"❌ {keyword} (до {max_price}₽)",
                callback_data=f"del_{cid}"
            )
        ])
    
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh"),
        InlineKeyboardButton(text="📊 Последние 10", callback_data="last_10")
    ])
    
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="⏱ Интервал", callback_data="set_interval")
    ])
    
    return keyboard

# --- Главное сообщение ---

async def update_main(user_id, items=None, last_10=False):
    try:
        criteria = get_user_criteria(user_id)
        interval = user_notify_interval.get(user_id, 60)
        
        msg = "🏠 <b>МЕНЮ МОНИТОРИНГА</b>\n\n"
        
        if criteria:
            msg += "📋 <b>Фильтры:</b>\n"
            for cid, keyword, max_price in criteria:
                msg += f"• {keyword} (до {max_price}₽)\n"
        else:
            msg += "📭 Нет фильтров\n"
            msg += "Напиши: Nike 5000\n\n"
        
        msg += f"⏱ Интервал: {interval} сек\n"
        msg += "\n"
        
        if last_10 and items:
            msg += "📊 <b>ПОСЛЕДНИЕ 10</b>\n\n"
            for i, item in enumerate(items[:10], 1):
                msg += f"{i}. {item['title'][:40]}\n"
                msg += f"   💰 {item['price_rub']}₽\n"
                msg += f"   🔗 <a href='{item['url']}'>Ссылка</a>\n\n"
        
        elif items and len(items) > 0 and not last_10:
            msg += f"📦 <b>НАЙДЕНО:</b> {len(items)}\n\n"
            for i, item in enumerate(items[:10], 1):
                msg += f"{i}. {item['title'][:40]}\n"
                msg += f"   💰 {item['price_rub']}₽\n"
                msg += f"   🔗 <a href='{item['url']}'>Ссылка</a>\n\n"
            if len(items) > 10:
                msg += f"⚠️ Показано 10 из {len(items)}\n"
        else:
            msg += "😴 Товаров нет\n"
        
        msg += f"\n🕒 {datetime.now().strftime('%H:%M:%S')}"
        
        keyboard = await get_keyboard(user_id)
        
        # Пробуем обновить существующее сообщение
        if user_id in user_main_message and user_main_message[user_id]:
            try:
                await bot.edit_message_text(
                    msg,
                    chat_id=user_id,
                    message_id=user_main_message[user_id],
                    parse_mode="HTML",
                    reply_markup=keyboard,
                    disable_web_page_preview=True
                )
                return
            except Exception as e:
                logger.warning(f"Не удалось обновить: {e}")
                user_main_message[user_id] = None
        
        # Отправляем новое сообщение
        try:
            msg_obj = await bot.send_message(
                user_id,
                msg,
                parse_mode="HTML",
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
            user_main_message[user_id] = msg_obj.message_id
            
            # Пытаемся закрепить (если не получится - просто игнорируем)
            try:
                await bot.pin_chat_message(user_id, msg_obj.message_id)
            except Exception as e:
                logger.warning(f"Не удалось закрепить: {e}")
                
        except Exception as e:
            logger.error(f"Ошибка отправки: {e}")
            
    except Exception as e:
        logger.error(f"Ошибка update_main: {e}")

# --- Уведомления ---

last_notify_time = {}

async def send_notification(user_id, item, keyword):
    try:
        now = time.time()
        interval = user_notify_interval.get(user_id, 60)
        
        key = f"{user_id}_{item['url']}"
        if key in last_notify_time:
            return
        
        if user_id in last_notify_time:
            if now - last_notify_time[user_id] < interval:
                return
        
        last_notify_time[user_id] = now
        last_notify_time[key] = now
        
        usd, rub = convert_price(item['price_cny'])
        
        msg = (
            f"🔔 <b>НОВЫЙ ТОВАР</b>\n"
            f"\n"
            f"📦 {item['title'][:60]}\n"
            f"\n"
            f"💰 {item['price_cny']}¥ | {rub}₽ | {usd}$\n"
            f"🌐 {item['site']}\n"
            f"🔗 <a href='{item['url']}'>Ссылка</a>\n"
            f"\n"
            f"📌 Фильтр: {keyword}"
        )
        
        await bot.send_message(user_id, msg, parse_mode="HTML", disable_web_page_preview=True)
        logger.info(f"Уведомление для {user_id}")
        
    except Exception as e:
        logger.error(f"Ошибка уведомления: {e}")

# --- Мониторинг ---

async def monitor():
    while True:
        try:
            await update_currency()
            users = get_all_active_users()
            
            for user_id in users:
                criteria = get_user_criteria(user_id)
                if not criteria:
                    continue
                
                all_items = []
                
                for cid, keyword, max_price_rub in criteria:
                    items = await fetch_items_for_keyword(keyword)
                    
                    for item in items:
                        usd, rub = convert_price(item['price_cny'])
                        
                        # Сохраняем в кеш с ценой в рублях
                        save_price_cache(keyword, item['site'], item['price_cny'], item['url'], item['title'], rub)
                        
                        if rub <= max_price_rub:
                            all_items.append({
                                "title": item['title'],
                                "price_cny": item['price_cny'],
                                "price_rub": rub,
                                "url": item['url'],
                                "site": item['site']
                            })
                            await send_notification(user_id, item, keyword)
                        
                        await asyncio.sleep(0.3)
                
                # Обновляем меню с найденными товарами
                if all_items:
                    await update_main(user_id, all_items)
            
            await asyncio.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            logger.error(f"Мониторинг: {e}")
            await asyncio.sleep(60)

# --- Команды ---

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    add_user(user_id, message.from_user.username or "", message.from_user.first_name or "")
    user_notify_interval[user_id] = 60
    await message.answer("⭐ Создаю меню...")
    await asyncio.sleep(1)
    await update_main(user_id)

@dp.message(Command("menu"))
async def menu_cmd(message: types.Message):
    await update_main(message.from_user.id)

@dp.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещен.")
        return
    
    users = get_all_active_users()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить", callback_data="admin_add")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data="admin_del")],
        [InlineKeyboardButton(text="📊 Список", callback_data="admin_list")]
    ])
    await message.answer(f"👑 Админ-панель\nПользователей: {len(users)}", reply_markup=keyboard)

# --- Callbacks ---

@dp.callback_query(F.data == "refresh")
async def refresh_cb(callback: CallbackQuery):
    await callback.answer("🔄")
    await update_main(callback.from_user.id)

@dp.callback_query(F.data == "add_criteria")
async def add_cb(callback: CallbackQuery):
    await callback.message.answer(
        "📝 Напиши в чат:\n"
        "<code>Nike 5000</code> - искать Nike до 5000₽"
    )
    await callback.answer()

@dp.callback_query(F.data == "last_10")
async def last_10_cb(callback: CallbackQuery):
    await callback.answer("📊 Загружаю...")
    user_id = callback.from_user.id
    
    all_items = []
    for site in ['mercari', 'goofish']:
        items = get_last_items(site, 5)
        all_items.extend(items)
    
    if all_items:
        await update_main(user_id, all_items, last_10=True)
    else:
        await callback.message.answer("😴 Нет сохраненных товаров")

@dp.callback_query(F.data == "set_interval")
async def set_interval_cb(callback: CallbackQuery):
    await callback.message.answer(
        f"⏱ Текущий интервал: {user_notify_interval.get(callback.from_user.id, 60)} сек\n\n"
        "Напиши число в секундах:\n"
        "60 - 1 минута\n"
        "300 - 5 минут"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("del_"))
async def del_cb(callback: CallbackQuery):
    user_id = callback.from_user.id
    crit_id = int(callback.data.split("_")[1])
    remove_criteria(crit_id, user_id)
    await callback.answer("✅ Удалено")
    await update_main(user_id)

@dp.callback_query(F.data == "admin_add")
async def admin_add_cb(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔")
        return
    await callback.message.answer("Введи ID пользователя:")
    await callback.answer()

@dp.callback_query(F.data == "admin_del")
async def admin_del_cb(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔")
        return
    await callback.message.answer("Введи ID для удаления (del_123):")
    await callback.answer()

@dp.callback_query(F.data == "admin_list")
async def admin_list_cb(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔")
        return
    users = get_all_active_users()
    await callback.message.answer(f"👥 Пользователи:\n" + "\n".join([str(u) for u in users]))
    await callback.answer()

# --- Текст ---

@dp.message(F.text)
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Установка интервала
    if text.isdigit() and len(text) <= 4:
        interval = int(text)
        if 10 <= interval <= 3600:
            user_notify_interval[user_id] = interval
            await message.answer(f"✅ Интервал: {interval} сек")
            await update_main(user_id)
            return
    
    # Добавление фильтра
    parts = text.split()
    if len(parts) >= 2:
        try:
            max_price = int(parts[-1])
            keyword = " ".join(parts[:-1])
            
            if len(keyword) < 2:
                await message.answer("⚠️ Слишком короткое слово")
                return
            
            if max_price <= 0:
                await message.answer("⚠️ Цена должна быть > 0")
                return
            
            add_criteria(user_id, keyword, max_price)
            await message.answer(f"✅ Добавлено: {keyword} (до {max_price}₽)")
            await update_main(user_id)
            return
        except:
            pass
    
    await message.answer("⚠️ Используй: Nike 5000")

# --- Админ ---

@dp.message(F.text.regexp(r'^\d+$'))
async def admin_add_by_id(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    user_id = int(message.text)
    add_user(user_id)
    await message.answer(f"✅ Пользователь {user_id} добавлен")

@dp.message(F.text.regexp(r'^del_\d+$'))
async def admin_del_by_id(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    user_id = int(message.text.split('_')[1])
    remove_user(user_id)
    await message.answer(f"✅ Пользователь {user_id} удален")

# --- Запуск ---

async def main():
    try:
        init_db()
        add_user(ADMIN_ID, "admin", "Admin")
        logger.info("База данных готова")
        
        asyncio.create_task(monitor())
        logger.info("Мониторинг запущен")
        
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
