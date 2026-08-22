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

def check_deviation(item_price, avg_price, user_deviation):
    if avg_price is None or avg_price == 0:
        return True
    diff_percent = abs((item_price - avg_price) / avg_price) * 100
    if item_price > avg_price:
        return True
    return diff_percent <= user_deviation

# --- Клавиатура ---

async def get_keyboard(user_id):
    criteria = get_user_criteria(user_id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="➕ Добавить критерий", callback_data="add_criteria")
    ])
    
    for cid, keyword, dev in criteria:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text=f"❌ {keyword} ({dev}%)", callback_data=f"del_{cid}")
        ])
    
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh")
    ])
    
    return keyboard

# --- Главное сообщение ---

async def update_main(user_id, items=None):
    try:
        criteria = get_user_criteria(user_id)
        
        msg = "🏠 <b>МЕНЮ МОНИТОРИНГА</b>\n\n"
        
        if criteria:
            msg += "📋 <b>Критерии:</b>\n"
            for cid, keyword, dev in criteria:
                msg += f"• {keyword} ({dev}%)\n"
        else:
            msg += "📭 Нет критериев. Нажми 'Добавить'\n"
        
        msg += "\n"
        
        if items and len(items) > 0:
            msg += f"📦 <b>Товары:</b> {len(items)}\n\n"
            for i, item in enumerate(items[:15], 1):
                msg += f"{i}. {item['title'][:40]}\n"
                msg += f"   💰 {item['price']}¥ | {item['usd']}$\n"
                msg += f"   🔗 <a href='{item['url']}'>Ссылка</a>\n\n"
            if len(items) > 15:
                msg += f"⚠️ Показано 15 из {len(items)}\n"
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

# --- Мониторинг ---

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
                for cid, keyword, dev in criteria:
                    items = await fetch_items_for_keyword(keyword)
                    for item in items:
                        avg = get_average_price(keyword, item['site'])
                        save_price_cache(keyword, item['site'], item['price_cny'], item['url'], item['title'])
                        if check_deviation(item['price_cny'], avg, dev):
                            usd, rub = convert_price(item['price_cny'])
                            dev_percent = 0
                            if avg and avg > 0:
                                dev_percent = round(((item['price_cny'] - avg) / avg) * 100, 1)
                            all_items.append({
                                "title": item['title'],
                                "price": item['price_cny'],
                                "usd": usd,
                                "rub": rub,
                                "url": item['url'],
                                "site": item['site'],
                                "deviation": dev_percent
                            })
                
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
    await message.answer("⭐ Создаю меню...")
    await update_main(user_id)

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
    await callback.message.answer(
        "📝 Введи запрос и отклонение:\n"
        "Пример: Raf Simons 10"
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
    
    # Добавление критерия
    parts = text.split()
    if len(parts) >= 1:
        try:
            dev = int(parts[-1])
            keyword = " ".join(parts[:-1])
        except:
            dev = 10
            keyword = " ".join(parts)
        
        if len(keyword) < 2:
            await message.answer("⚠️ Слишком короткое слово")
            return
        
        add_criteria(user_id, keyword, dev)
        await message.answer(f"✅ Добавлено: {keyword} ({dev}%)")
        await update_main(user_id)

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

# --- Запуск ---

async def main():
    init_db()
    add_user(ADMIN_ID, "admin", "Admin")
    asyncio.create_task(monitor())
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
