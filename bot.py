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
from parser import fetch_items_for_keyword, fetch_latest_items

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

# ==================== КЛАВИАТУРА ====================

async def get_keyboard(user_id):
    criteria = get_user_criteria(user_id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="➕ Добавить фильтр", callback_data="add_filter")
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
        InlineKeyboardButton(text="📊 Последние 10", callback_data="last10")
    ])
    
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="⏱ Интервал", callback_data="interval")
    ])
    
    return keyboard

# ==================== ГЛАВНОЕ СООБЩЕНИЕ ====================

async def update_main(user_id, items=None, last10=False, loading=False):
    try:
        criteria = get_user_criteria(user_id)
        interval = user_notify_interval.get(user_id, 60)
        
        msg = "🏠 <b>МЕНЮ МОНИТОРИНГА</b>\n"
        msg += "─────────────────\n\n"
        
        if criteria:
            msg += "📋 <b>Фильтры:</b>\n"
            for cid, keyword, max_price in criteria:
                msg += f"• {keyword} (до {max_price}₽)\n"
        else:
            msg += "📭 <b>Нет фильтров</b>\n"
            msg += "Напиши: <code>Nike 5000</code>\n\n"
        
        msg += f"⏱ Интервал: {interval} сек\n"
        msg += "─────────────────\n\n"
        
        if loading:
            msg += "⏳ <b>Загрузка последних товаров...</b>\n"
            msg += "Пожалуйста, подожди 10-15 секунд\n"
        
        elif last10 and items:
            msg += "📊 <b>ПОСЛЕДНИЕ 10 ТОВАРОВ</b>\n"
            msg += "(с сайтов в реальном времени)\n\n"
            
            mercari_items = [i for i in items if i['site'] == 'mercari']
            goofish_items = [i for i in items if i['site'] == 'goofish']
            
            if mercari_items:
                msg += "🟢 <b>Mercari:</b>\n"
                for i, item in enumerate(mercari_items[:5], 1):
                    msg += f"  {i}. {item['title'][:35]}\n"
                    msg += f"     💰 {item['price_rub']}₽ | {item['price_cny']}¥\n"
                    msg += f"     🔗 <a href='{item['url']}'>Ссылка</a>\n\n"
            
            if goofish_items:
                msg += "🔵 <b>Goofish:</b>\n"
                for i, item in enumerate(goofish_items[:5], 1):
                    msg += f"  {i}. {item['title'][:35]}\n"
                    msg += f"     💰 {item['price_rub']}₽ | {item['price_cny']}¥\n"
                    msg += f"     🔗 <a href='{item['url']}'>Ссылка</a>\n\n"
            
            msg += "─────────────────\n"
            msg += "🔄 Нажми 'Обновить' для возврата"
        
        elif items and len(items) > 0 and not last10:
            msg += f"📦 <b>НАЙДЕНО:</b> {len(items)}\n\n"
            for i, item in enumerate(items[:10], 1):
                msg += f"{i}. {item['title'][:40]}\n"
                msg += f"   💰 {item['price_rub']}₽\n"
                msg += f"   🔗 <a href='{item['url']}'>Ссылка</a>\n\n"
            if len(items) > 10:
                msg += f"⚠️ Показано 10 из {len(items)}\n"
        else:
            msg += "😴 <b>Товаров нет</b>\n"
            msg += "Ожидай появления...\n"
        
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
            except Exception as e:
                logger.warning(f"Edit failed: {e}")
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
        except Exception as e:
            logger.warning(f"Pin failed: {e}")
            
    except Exception as e:
        logger.error(f"update_main error: {e}")
        logger.error(traceback.format_exc())

# ==================== УВЕДОМЛЕНИЯ ====================

last_notify_time = {}

async def send_notification(user_id, item, keyword):
    try:
        now = time.time()
        interval = user_notify_interval.get(user_id, 60)
        
        key = f"{user_id}_{item['url']}"
        if key in last_notify_time:
            return
        
        if user_id in last_notify_time and now - last_notify_time[user_id] < interval:
            return
        
        last_notify_time[user_id] = now
        last_notify_time[key] = now
        
        usd, rub = convert_price(item['price_cny'])
        
        msg = (
            f"🔔 <b>НОВЫЙ ТОВАР</b>\n\n"
            f"📦 {item['title'][:60]}\n\n"
            f"💰 {item['price_cny']}¥ | {rub}₽ | {usd}$\n"
            f"🌐 {item['site']}\n"
            f"🔗 <a href='{item['url']}'>Ссылка</a>\n\n"
            f"📌 Фильтр: {keyword}"
        )
        
        await bot.send_message(user_id, msg, parse_mode="HTML", disable_web_page_preview=True)
        logger.info(f"Уведомление {user_id}: {keyword}")
        
    except Exception as e:
        logger.error(f"send_notification error: {e}")

# ==================== МОНИТОРИНГ ====================

async def monitor():
    while True:
        try:
            await update_currency()
            users = get_all_active_users()
            
            for user_id in users:
                criteria = get_user_criteria(user_id)
                if not criteria:
                    await update_main(user_id)
                    continue
                
                all_items = []
                
                for cid, keyword, max_price_rub in criteria:
                    items = await fetch_items_for_keyword(keyword)
                    
                    for item in items:
                        usd, rub = convert_price(item['price_cny'])
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
                
                await update_main(user_id, all_items)
            
            await asyncio.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            logger.error(f"monitor error: {e}")
            await asyncio.sleep(60)

# ==================== ФУНКЦИЯ ДЛЯ "ПОСЛЕДНИХ 10" ====================

async def fetch_last_10():
    """Парсит последние товары с сайтов в реальном времени"""
    all_items = []
    
    try:
        mercari_items = await fetch_latest_items('mercari')
        all_items.extend(mercari_items[:5])
    except Exception as e:
        logger.error(f"Mercari latest error: {e}")
    
    try:
        goofish_items = await fetch_latest_items('goofish')
        all_items.extend(goofish_items[:5])
    except Exception as e:
        logger.error(f"Goofish latest error: {e}")
    
    return all_items

# ==================== КОМАНДЫ ====================

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    try:
        user_id = message.from_user.id
        logger.info(f"Команда /start от {user_id}")
        
        add_user(user_id, message.from_user.username or "", message.from_user.first_name or "")
        user_notify_interval[user_id] = 60
        
        await message.answer("⭐ Создаю меню...")
        await asyncio.sleep(0.5)
        await update_main(user_id)
        
    except Exception as e:
        logger.error(f"start_cmd error: {e}")
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command("menu"))
async def menu_cmd(message: types.Message):
    try:
        await update_main(message.from_user.id)
    except Exception as e:
        logger.error(f"menu_cmd error: {e}")

@dp.message(Command("admin"))
async def admin_cmd(message: types.Message):
    try:
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
    except Exception as e:
        logger.error(f"admin_cmd error: {e}")

# ==================== CALLBACK ====================

@dp.callback_query(F.data == "refresh")
async def refresh_cb(callback: CallbackQuery):
    try:
        await callback.answer("🔄")
        await update_main(callback.from_user.id)
    except Exception as e:
        logger.error(f"refresh_cb error: {e}")

@dp.callback_query(F.data == "add_filter")
async def add_filter_cb(callback: CallbackQuery):
    try:
        await callback.answer("📝 Напиши в чат: Nike 5000")
    except Exception as e:
        logger.error(f"add_filter_cb error: {e}")

@dp.callback_query(F.data == "last10")
async def last10_cb(callback: CallbackQuery):
    try:
        user_id = callback.from_user.id
        
        await callback.answer("⏳ Загружаю...")
        await update_main(user_id, loading=True)
        
        items = await fetch_last_10()
        
        if items:
            for item in items:
                usd, rub = convert_price(item['price_cny'])
                item['price_rub'] = rub
            
            await update_main(user_id, items, last10=True)
        else:
            await update_main(user_id)
            
    except Exception as e:
        logger.error(f"last10_cb error: {e}")
        await update_main(callback.from_user.id)

@dp.callback_query(F.data == "interval")
async def interval_cb(callback: CallbackQuery):
    try:
        await callback.answer("⏱ Напиши число в чат (секунды)")
    except Exception as e:
        logger.error(f"interval_cb error: {e}")

@dp.callback_query(F.data.startswith("del_"))
async def del_cb(callback: CallbackQuery):
    try:
        user_id = callback.from_user.id
        crit_id = int(callback.data.split("_")[1])
        remove_criteria(crit_id, user_id)
        await callback.answer("✅")
        await update_main(user_id)
    except Exception as e:
        logger.error(f"del_cb error: {e}")

@dp.callback_query(F.data == "admin_add")
async def admin_add_cb(callback: CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("⛔")
            return
        await callback.message.answer("Введи ID пользователя:")
        await callback.answer()
    except Exception as e:
        logger.error(f"admin_add_cb error: {e}")

@dp.callback_query(F.data == "admin_del")
async def admin_del_cb(callback: CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("⛔")
            return
        await callback.message.answer("Введи del_123:")
        await callback.answer()
    except Exception as e:
        logger.error(f"admin_del_cb error: {e}")

@dp.callback_query(F.data == "admin_list")
async def admin_list_cb(callback: CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("⛔")
            return
        users = get_all_active_users()
        await callback.message.answer("👥 Пользователи:\n" + "\n".join([str(u) for u in users]))
        await callback.answer()
    except Exception as e:
        logger.error(f"admin_list_cb error: {e}")

# ==================== ТЕКСТ ====================

@dp.message(F.text)
async def handle_text(message: types.Message):
    try:
        user_id = message.from_user.id
        text = message.text.strip()
        
        # Добавление пользователя админом
        if message.from_user.id == ADMIN_ID:
            if text.isdigit() and len(text) >= 5:
                user_id_to_add = int(text)
                add_user(user_id_to_add)
                await message.answer(f"✅ Пользователь {user_id_to_add} добавлен!")
                return
            
            if text.startswith('del_') and text[4:].isdigit():
                user_id_to_del = int(text[4:])
                remove_user(user_id_to_del)
                await message.answer(f"✅ Пользователь {user_id_to_del} удален!")
                return
        
        # Интервал
        if text.isdigit() and len(text) <= 4:
            interval = int(text)
            if 10 <= interval <= 3600:
                user_notify_interval[user_id] = interval
                await message.answer(f"✅ Интервал: {interval} сек")
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
                    await message.answer("⚠️ Цена должна быть > 0")
                    return
                
                add_criteria(user_id, keyword, max_price)
                await message.answer(f"✅ Добавлено: {keyword} (до {max_price}₽)")
                await update_main(user_id)
                return
            except:
                pass
        
        await message.answer("⚠️ Используй: <code>Nike 5000</code>", parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"handle_text error: {e}")
        await message.answer(f"❌ Ошибка: {e}")

# ==================== ЗАПУСК ====================

async def main():
    try:
        init_db()
        add_user(ADMIN_ID, "admin", "Admin")
        logger.info("База данных готова")
        
        asyncio.create_task(monitor())
        logger.info("Мониторинг запущен")
        
        logger.info("Бот готов к работе!")
        await dp.start_polling(bot, skip_updates=True)
        
    except Exception as e:
        logger.error(f"Ошибка main: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
