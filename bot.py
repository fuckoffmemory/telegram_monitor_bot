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

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

print("🚀 Запуск бота...")
print(f"BOT_TOKEN: {'✅ УСТАНОВЛЕН' if BOT_TOKEN and BOT_TOKEN != 'YOUR_BOT_TOKEN_HERE' else '❌ НЕ УСТАНОВЛЕН'}")
print(f"ADMIN_ID: {'✅ УСТАНОВЛЕН' if ADMIN_ID else '❌ НЕ УСТАНОВЛЕН'}")

if not BOT_TOKEN or BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
    print("❌ ОШИБКА: BOT_TOKEN не настроен!")
    exit(1)

if not ADMIN_ID:
    print("❌ ОШИБКА: ADMIN_ID не настроен!")
    exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Храним ID главного сообщения для каждого пользователя
user_main_message = {}

# Храним последние отправленные товары (чтобы не дублировать)
sent_items = {}

# Кеш курсов валют
currency_cache = {
    "cny_to_usd": 0.14,
    "cny_to_rub": 12.5,
    "last_update": 0
}

async def update_currency():
    """Обновляет курсы валют"""
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
    except Exception as e:
        logger.error(f"Ошибка обновления курсов: {e}")

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
    else:
        return diff_percent <= user_deviation

# --- Клавиатура для главного меню ---

async def get_main_menu_keyboard(user_id):
    """Создает клавиатуру для главного меню"""
    criteria = get_user_criteria(user_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    # Кнопка добавления критерия
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="➕ Добавить критерий", callback_data="add_criteria")
    ])
    
    # Кнопки для каждого критерия (удаление)
    for cid, keyword, dev in criteria:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"❌ {keyword} ({dev}%)",
                callback_data=f"del_crit_{cid}"
            )
        ])
    
    # Дополнительные кнопки
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="🔄 Обновить меню", callback_data="refresh_menu"),
        InlineKeyboardButton(text="🧪 Тест парсера", callback_data="test_parser")
    ])
    
    return keyboard

# --- Главное меню ---

async def update_main_menu(user_id):
    """Обновляет главное меню пользователя"""
    try:
        criteria = get_user_criteria(user_id)
        
        # Формируем текст меню
        msg = "🏠 <b>ГЛАВНОЕ МЕНЮ МОНИТОРИНГА</b>\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        if criteria:
            msg += "📋 <b>Активные критерии:</b>\n"
            for cid, keyword, dev in criteria:
                msg += f"   • <b>{keyword}</b> (отклонение: {dev}%)\n"
        else:
            msg += "📭 <b>Нет активных критериев</b>\n"
            msg += "   Нажми 'Добавить критерий' ниже\n"
        
        msg += "\n━━━━━━━━━━━━━━━━━━━━━\n"
        msg += "📌 <b>Как использовать:</b>\n"
        msg += "1. Добавь критерий через кнопку\n"
        msg += "2. Новые товары будут приходить отдельными сообщениями\n"
        msg += "3. Удаляй ненужные критерии здесь\n"
        
        msg += f"\n🕒 <i>Обновлено: {datetime.now().strftime('%H:%M:%S')}</i>"
        
        keyboard = await get_main_menu_keyboard(user_id)
        
        # Отправляем или обновляем
        if user_id in user_main_message and user_main_message[user_id]:
            try:
                await bot.edit_message_text(
                    msg,
                    chat_id=user_id,
                    message_id=user_main_message[user_id],
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
                return
            except Exception as e:
                logger.warning(f"Не удалось обновить меню: {e}")
                user_main_message[user_id] = None
        
        # Отправляем новое
        try:
            msg_obj = await bot.send_message(
                user_id,
                msg,
                parse_mode="HTML",
                reply_markup=keyboard
            )
            user_main_message[user_id] = msg_obj.message_id
            
            # Пытаемся закрепить
            try:
                await bot.pin_chat_message(user_id, msg_obj.message_id)
            except:
                pass
                
        except Exception as e:
            logger.error(f"Ошибка отправки меню: {e}")
            
    except Exception as e:
        logger.error(f"Ошибка update_main_menu: {e}")

# --- Отправка уведомлений о товарах ---

async def send_item_notification(user_id, item, keyword):
    """Отправляет уведомление о новом товаре отдельным сообщением"""
    try:
        # Проверяем, не отправляли ли уже этот товар
        item_key = f"{item['url']}_{user_id}"
        if item_key in sent_items:
            return
        
        sent_items[item_key] = time.time()
        
        # Очищаем старые записи (старше 1 часа)
        for key in list(sent_items.keys()):
            if time.time() - sent_items[key] > 3600:
                del sent_items[key]
        
        usd, rub = convert_price(item['price_cny'])
        
        # Получаем отклонение
        avg_price = get_average_price(keyword, item['site'])
        if avg_price and avg_price > 0:
            dev_percent = round(((item['price_cny'] - avg_price) / avg_price) * 100, 1)
        else:
            dev_percent = 0
        
        msg = (
            f"🔔 <b>НОВЫЙ ТОВАР</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 <b>{item['title'][:80]}</b>\n"
            f"\n"
            f"💰 <b>Цена:</b>\n"
            f"   • {item['price_cny']} ¥ (CNY)\n"
            f"   • {usd} $\n"
            f"   • {rub} ₽\n"
            f"\n"
            f"📊 <b>Отклонение от рынка:</b> {dev_percent}%\n"
            f"🌐 <b>Площадка:</b> {item['site']}\n"
            f"🔗 <b>Ссылка:</b> <a href='{item['url']}'>Перейти к товару</a>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <i>Запрос: {keyword}</i>"
        )
        
        await bot.send_message(user_id, msg, parse_mode="HTML", disable_web_page_preview=True)
        logger.info(f"Уведомление отправлено пользователю {user_id} по запросу {keyword}")
        
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления: {e}")

# --- Мониторинг ---

async def monitor_task():
    """Фоновый мониторинг"""
    try:
        await bot.send_message(ADMIN_ID, "🚀 Бот запущен и начал мониторинг!")
    except:
        pass
    
    while True:
        try:
            await update_currency()
            users = get_all_active_users()
            
            for user_id in users:
                criteria_list = get_user_criteria(user_id)
                if not criteria_list:
                    continue
                
                for crit_id, keyword, deviation in criteria_list:
                    items = await fetch_items_for_keyword(keyword)
                    
                    for item in items:
                        avg_price = get_average_price(keyword, item['site'])
                        save_price_cache(keyword, item['site'], item['price_cny'], item['url'], item['title'])
                        
                        if check_deviation(item['price_cny'], avg_price, deviation):
                            await send_item_notification(user_id, item, keyword)
                        
                        await asyncio.sleep(0.5)
            
            await asyncio.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            logger.error(f"Ошибка мониторинга: {e}")
            await asyncio.sleep(60)

# --- Команды ---

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    add_user(user_id, message.from_user.username or "", message.from_user.first_name or "")
    
    await message.answer(
        "👋 Привет! Я создаю главное меню...\n"
        "Оно будет закреплено сверху! ⭐"
    )
    
    await update_main_menu(user_id)

@dp.message(Command("menu"))
async def menu_cmd(message: types.Message):
    user_id = message.from_user.id
    await update_main_menu(user_id)

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещен.")
        return
    
    users = get_all_active_users()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить пользователя", callback_data="admin_add_user")],
        [InlineKeyboardButton(text="🗑 Удалить пользователя", callback_data="admin_del_user")],
        [InlineKeyboardButton(text="📊 Список пользователей", callback_data="admin_list_users")]
    ])
    
    await message.answer(
        f"👑 <b>Админ-панель</b>\n\n"
        f"Активных пользователей: {len(users)}",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

# --- Callback обработчики ---

@dp.callback_query(F.data == "refresh_menu")
async def refresh_menu_callback(callback: CallbackQuery):
    await callback.answer("🔄 Обновляю меню...")
    await update_main_menu(callback.from_user.id)

@dp.callback_query(F.data == "add_criteria")
async def add_criteria_callback(callback: CallbackQuery):
    await callback.message.answer(
        "✏️ <b>Введи ключевое слово и отклонение</b>\n\n"
        "Примеры:\n"
        "<code>Raf Simons 10</code> - отклонение 10%\n"
        "<code>Raf Simons 0</code> - точное совпадение\n"
        "<code>Nike</code> - отклонение 10% (по умолчанию)",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "test_parser")
async def test_parser_callback(callback: CallbackQuery):
    await callback.answer("🧪 Тестирую...")
    
    user_id = callback.from_user.id
    criteria = get_user_criteria(user_id)
    
    if not criteria:
        await bot.send_message(user_id, "⚠️ Сначала добавь критерий для теста!")
        return
    
    keyword = criteria[0][1]
    status_msg = await bot.send_message(user_id, f"🔍 Ищу '{keyword}'...")
    
    try:
        items = await fetch_items_for_keyword(keyword)
        
        if items:
            msg = f"✅ <b>Парсер работает!</b>\n"
            msg += f"━━━━━━━━━━━━━━━━━━━━━\n"
            msg += f"📦 Найдено: {len(items)} товаров\n\n"
            
            for i, item in enumerate(items[:5], 1):
                msg += f"<b>{i}.</b> {item['title'][:40]}\n"
                msg += f"   💰 {item['price_cny']} ¥\n"
                msg += f"   🌐 {item['site']}\n"
                msg += f"   🔗 <a href='{item['url']}'>Ссылка</a>\n\n"
            
            await status_msg.edit_text(msg, parse_mode="HTML", disable_web_page_preview=True)
        else:
            await status_msg.edit_text(f"❌ Товары не найдены по запросу: {keyword}")
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)}")

@dp.callback_query(F.data.startswith("del_crit_"))
async def confirm_del_criteria(callback: CallbackQuery):
    user_id = callback.from_user.id
    crit_id = int(callback.data.split("_")[2])
    remove_criteria(crit_id, user_id)
    
    await callback.answer("✅ Критерий удален!")
    await update_main_menu(user_id)

@dp.callback_query(F.data == "admin_list_users")
async def admin_list_users(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен.")
        return
    
    users = get_all_active_users()
    
    if not users:
        await callback.message.answer("📭 Нет активных пользователей.")
    else:
        text = "👥 <b>Список пользователей:</b>\n\n"
        for uid in users:
            text += f"• {uid}\n"
        await callback.message.answer(text, parse_mode="HTML")
    
    await callback.answer()

@dp.callback_query(F.data == "admin_add_user")
async def admin_add_user(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен.")
        return
    
    await callback.message.answer("✏️ Введи Telegram ID пользователя:")
    await callback.answer()

@dp.callback_query(F.data == "admin_del_user")
async def admin_del_user(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен.")
        return
    
    await callback.message.answer("✏️ Введи Telegram ID пользователя для удаления:")
    await callback.answer()

# --- Обработка текстовых сообщений ---

@dp.message(F.text)
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Проверяем, является ли сообщение добавлением критерия
    parts = text.split()
    if len(parts) >= 1:
        try:
            deviation = int(parts[-1])
            keyword = " ".join(parts[:-1])
        except ValueError:
            deviation = 10
            keyword = " ".join(parts)
        
        if len(keyword) < 2:
            await message.answer("⚠️ Слишком короткое ключевое слово (минимум 2 символа).")
            return
        
        add_criteria(user_id, keyword, deviation)
        
        await message.answer(
            f"✅ Критерий добавлен!\n"
            f"📌 Слово: <b>{keyword}</b>\n"
            f"📊 Отклонение: <b>{deviation}%</b>",
            parse_mode="HTML"
        )
        
        await update_main_menu(user_id)

# --- Админ: добавление пользователя по ID ---

@dp.message(F.text.regexp(r'^\d+$'))
async def admin_add_user_by_id(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    user_id = int(message.text)
    add_user(user_id)
    await message.answer(f"✅ Пользователь {user_id} добавлен.")

@dp.message(F.text.regexp(r'^del_\d+$'))
async def admin_del_user_by_id(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    user_id = int(message.text.split('_')[1])
    remove_user(user_id)
    await message.answer(f"✅ Пользователь {user_id} удален.")

# --- Запуск ---

async def main():
    try:
        init_db()
        add_user(ADMIN_ID, "admin", "Admin")
        
        asyncio.create_task(monitor_task())
        
        logger.info("Бот запущен!")
        await dp.start_polling(bot, skip_updates=True)
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(main())
