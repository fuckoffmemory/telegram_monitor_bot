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
user_notify_interval = {}  # интервал в секундах для каждого пользователя

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
    except:
        pass

def convert_price(cny):
    usd = cny * currency_cache["cny_to_usd"]
    rub = cny * currency_cache["cny_to_rub"]
    return round(usd, 2), round(rub, 2)

# --- Клавиатура ---

async def get_keyboard(user_id):
    criteria = get_user_criteria(user_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    # Добавить критерий
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="➕ Добавить фильтр", callback_data="add_criteria")
    ])
    
    # Список фильтров с кнопками удаления
    for cid, keyword, max_price in criteria:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"❌ {keyword} (до {max_price}₽)",
                callback_data=f"del_{cid}"
            )
        ])
    
    # Дополнительные кнопки
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh"),
        InlineKeyboardButton(text="📊 Последние 10", callback_data="last_10")
    ])
    
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="⏱ Интервал уведомлений", callback_data="set_interval")
    ])
    
    return keyboard

# --- Главное сообщение ---

async def update_main(user_id, items=None, last_10=False):
    try:
        criteria = get_user_criteria(user_id)
        interval = user_notify_interval.get(user_id, 60)
        
        msg = "🏠 <b>МЕНЮ МОНИТОРИНГА</b>\n\n"
        
        if criteria:
            msg += "📋 <b>Активные фильтры:</b>\n"
            for cid, keyword, max_price in criteria:
                msg += f"• {keyword} (до {max_price}₽)\n"
        else:
            msg += "📭 Нет фильтров. Добавь через кнопку ниже\n"
            msg += "Пример: Nike 5000 (ищет Nike до 5000₽)\n"
        
        msg += f"\n⏱ Интервал: {interval} сек\n"
        msg += "\n"
        
        # Если это запрос "Последние 10"
        if last_10 and items:
            msg += "📊 <b>ПОСЛЕДНИЕ 10 ТОВАРОВ</b>\n\n"
            for i, item in enumerate(items[:10], 1):
                msg += f"{i}. {item['title'][:40]}\n"
                msg += f"   💰 {item['price']}¥ | {item['rub']}₽\n"
                msg += f"   🌐 {item['site']}\n"
                msg += f"   🔗 <a href='{item['url']}'>Ссылка</a>\n\n"
            msg += "━━━━━━━━━━━━━━━━━━━━━\n"
        
        # Обычный список товаров
        elif items and len(items) > 0 and not last_10:
            msg += f"📦 <b>НАЙДЕНО:</b> {len(items)}\n\n"
            for i, item in enumerate(items[:10], 1):
                msg += f"{i}. {item['title'][:40]}\n"
                msg += f"   💰 {item['price']}¥ | {item['rub']}₽\n"
                msg += f"   🔗 <a href='{item['url']}'>Ссылка</a>\n\n"
            if len(items) > 10:
                msg += f"⚠️ Показано 10 из {len(items)}\n"
        else:
            msg += "😴 Товаров нет\n"
        
        msg += f"\n🕒 {datetime.now().strftime('%H:%M:%S')}"
        
        keyboard = await get_keyboard(user_id)
        
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
            except:
                user_main_message[user_id] = None
        
        msg_obj = await bot.send_message(
            user_id,
            msg,
            parse_mode="HTML",
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        user_main_message[user_id] = msg_obj.message_id
        try:
            await bot.pin_chat_message(user_id, msg_obj.message_id)
        except:
            pass
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")

# --- Отправка уведомления о новом товаре ---

last_notify_time = {}

async def send_notification(user_id, item, keyword):
    """Отправляет отдельное уведомление о новом товаре"""
    try:
        # Проверяем интервал
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
        logger.info(f"Уведомление для {user_id}: {keyword}")
        
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
                
                for cid, keyword, max_price_rub in criteria:
                    items = await fetch_items_for_keyword(keyword)
                    
                    for item in items:
                        # Конвертируем цену в рубли
                        usd, rub = convert_price(item['price_cny'])
                        
                        # Проверяем, что цена меньше максимальной
                        if rub <= max_price_rub:
                            # Отправляем уведомление
                            await send_notification(user_id, item, keyword)
                            
                            # Сохраняем в кеш для "Последних 10"
                            save_price_cache(
                                keyword, 
                                item['site'], 
                                item['price_cny'], 
                                item['url'], 
                                item['title']
                            )
                        
                        await asyncio.sleep(0.5)
            
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
        [InlineKeyboardButton(text="➕ Добавить пользователя", callback_data="admin_add")],
        [InlineKeyboardButton(text="🗑 Удалить пользователя", callback_data="admin_del")],
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
    # Отправляем сообщение с инструкцией
    msg = await callback.message.answer(
        "📝 <b>Добавь фильтр</b>\n\n"
        "Напиши в чат:\n"
        "<code>Nike 5000</code> - искать Nike до 5000₽\n"
        "<code>Raf Simons 15000</code> - искать Raf Simons до 15000₽\n\n"
        "После добавления меню обновится автоматически"
    )
    await callback.answer()
    
    # Удаляем это сообщение через 5 секунд
    await asyncio.sleep(5)
    try:
        await msg.delete()
    except:
        pass

@dp.callback_query(F.data == "last_10")
async def last_10_cb(callback: CallbackQuery):
    await callback.answer("📊 Загружаю...")
    
    user_id = callback.from_user.id
    all_items = []
    
    # Берем последние 5 с каждого сайта
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
        "⏱ <b>Интервал между уведомлениями</b>\n\n"
        "Напиши число в секундах:\n"
        "60 - 1 минута\n"
        "300 - 5 минут\n"
        "600 - 10 минут\n\n"
        "Текущий: {} сек".format(user_notify_interval.get(callback.from_user.id, 60))
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
    
    # Проверяем на установку интервала (только число)
    if text.isdigit() and len(text) <= 4:
        interval = int(text)
        if 10 <= interval <= 3600:
            user_notify_interval[user_id] = interval
            await message.answer(f"✅ Интервал установлен: {interval} сек")
            await update_main(user_id)
            return
    
    # Добавление фильтра: "Nike 5000"
    parts = text.split()
    if len(parts) >= 2:
        try:
            max_price = int(parts[-1])
            keyword = " ".join(parts[:-1])
            
            if len(keyword) < 2:
                await message.answer("⚠️ Слишком короткое слово")
                return
            
            if max_price <= 0:
                await message.answer("⚠️ Цена должна быть больше 0")
                return
            
            add_criteria(user_id, keyword, max_price)
            await message.answer(f"✅ Добавлено: {keyword} (до {max_price}₽)")
            await update_main(user_id)
            return
            
        except:
            pass
    
    await message.answer("⚠️ Неправильный формат. Используй: Nike 5000")

# --- Админ: добавление/удаление ---

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

# --- Функция для "Последних 10" ---

def get_last_items(site, limit=5):
    """Получает последние N товаров с сайта"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT title, price, url, site 
            FROM price_cache 
            WHERE site = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (site, limit))
        data = c.fetchall()
        conn.close()
        
        items = []
        for title, price, url, site in data:
            usd, rub = convert_price(price)
            items.append({
                "title": title,
                "price": price,
                "rub": rub,
                "usd": usd,
                "url": url,
                "site": site
            })
        return items
    except Exception as e:
        logger.error(f"Ошибка get_last_items: {e}")
        return []

# --- Запуск ---

async def main():
    init_db()
    add_user(ADMIN_ID, "admin", "Admin")
    
    # Обновляем базу данных - добавляем колонку max_price в criteria (если нет)
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("PRAGMA table_info(criteria)")
        columns = [col[1] for col in c.fetchall()]
        if 'max_price' not in columns:
            c.execute("ALTER TABLE criteria ADD COLUMN max_price INTEGER DEFAULT 0")
        conn.commit()
        conn.close()
    except:
        pass
    
    asyncio.create_task(monitor())
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
