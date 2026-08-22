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
            logger.info("Курсы валют обновлены")
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
        InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh"),
        InlineKeyboardButton(text="🧪 Тест", callback_data="test_parser")
    ])
    
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="📦 Все товары", callback_data="show_all")
    ])
    
    return keyboard

async def update_main_message(user_id, items=None):
    """Обновляет главное сообщение пользователя"""
    try:
        criteria = get_user_criteria(user_id)
        
        # Формируем текст сообщения
        msg = "🏠 <b>ГЛАВНОЕ МЕНЮ МОНИТОРИНГА</b>\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        # Список критериев
        if criteria:
            msg += "📋 <b>Активные критерии:</b>\n"
            for cid, keyword, dev in criteria:
                msg += f"   • <b>{keyword}</b> (отклонение: {dev}%)\n"
        else:
            msg += "📭 <b>Нет активных критериев</b>\n"
            msg += "   Добавь первый через кнопку ниже\n"
        
        msg += "\n━━━━━━━━━━━━━━━━━━━━━\n"
        
        # Список найденных товаров
        if items and len(items) > 0:
            msg += f"📦 <b>Найдено товаров:</b> {len(items)}\n\n"
            
            # Показываем первые 7 товаров
            for i, item in enumerate(items[:7], 1):
                msg += f"<b>{i}.</b> {item['title'][:40]}\n"
                msg += f"   💰 {item['price']} ¥ | {item['usd']}$ | {item['rub']}₽\n"
                msg += f"   📊 Откл: {item['deviation']}% | 🌐 {item['site']}\n"
                msg += f"   🔗 <a href='{item['url']}'>Ссылка</a>\n"
                msg += "   ─────────────────\n"
            
            if len(items) > 7:
                msg += f"\n⚠️ Показано 7 из {len(items)} товаров"
        else:
            msg += "😴 <b>Новых товаров пока нет</b>\n"
            msg += "   Ожидай появления...\n"
        
        msg += f"\n🕒 <i>Обновлено: {datetime.now().strftime('%H:%M:%S')}</i>"
        
        # Получаем клавиатуру
        keyboard = await get_main_menu_keyboard(user_id)
        
        # Отправляем или обновляем сообщение
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
                logger.info(f"Сообщение обновлено для {user_id}")
                return
            except Exception as e:
                logger.warning(f"Не удалось обновить сообщение: {e}")
                # Удаляем старый ID
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
            logger.info(f"Новое сообщение отправлено для {user_id}")
            
            # Пытаемся закрепить сообщение
            try:
                await bot.pin_chat_message(user_id, msg_obj.message_id)
                logger.info(f"Сообщение закреплено для {user_id}")
            except Exception as e:
                logger.warning(f"Не удалось закрепить сообщение: {e}")
                
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения: {e}")
            
    except Exception as e:
        logger.error(f"Ошибка update_main_message: {e}")
        logger.error(traceback.format_exc())

async def monitor_task():
    """Фоновый мониторинг"""
    try:
        await bot.send_message(ADMIN_ID, "🚀 Бот запущен и начал мониторинг!")
        logger.info("Мониторинг запущен")
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление админу: {e}")
    
    while True:
        try:
            logger.info("Начинаю проверку...")
            await update_currency()
            users = get_all_active_users()
            logger.info(f"Активных пользователей: {len(users)}")
            
            for user_id in users:
                try:
                    criteria_list = get_user_criteria(user_id)
                    if not criteria_list:
                        # Если нет критериев, показываем пустое меню
                        await update_main_message(user_id)
                        continue
                    
                    all_items = []
                    
                    for crit_id, keyword, deviation in criteria_list:
                        logger.info(f"Парсинг для {user_id}: {keyword}")
                        items = await fetch_items_for_keyword(keyword)
                        logger.info(f"Найдено {len(items)} товаров для {keyword}")
                        
                        for item in items:
                            avg_price = get_average_price(keyword, item['site'])
                            save_price_cache(keyword, item['site'], item['price_cny'], item['url'], item['title'])
                            
                            if not check_deviation(item['price_cny'], avg_price, deviation):
                                continue
                            
                            usd, rub = convert_price(item['price_cny'])
                            
                            if avg_price and avg_price > 0:
                                dev_percent = round(((item['price_cny'] - avg_price) / avg_price) * 100, 1)
                            else:
                                dev_percent = 0
                            
                            all_items.append({
                                "title": item['title'],
                                "price": item['price_cny'],
                                "usd": usd,
                                "rub": rub,
                                "url": item['url'],
                                "site": item['site'],
                                "deviation": dev_percent,
                                "keyword": keyword
                            })
                    
                    # Обновляем главное сообщение
                    await update_main_message(user_id, all_items)
                    
                except Exception as e:
                    logger.error(f"Ошибка для пользователя {user_id}: {e}")
                    logger.error(traceback.format_exc())
            
            logger.info(f"Проверка завершена. Следующая через {CHECK_INTERVAL} сек.")
            await asyncio.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            logger.error(f"Ошибка в мониторинге: {e}")
            logger.error(traceback.format_exc())
            await asyncio.sleep(60)

# --- Команды бота ---

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    logger.info(f"Команда /start от {user_id}")
    
    try:
        # Добавляем пользователя
        add_user(user_id, message.from_user.username or "", message.from_user.first_name or "")
        
        # Отправляем приветствие
        await message.answer(
            "👋 Привет! Создаю главное меню-интерфейс...\n"
            "Оно будет закреплено сверху! ⭐"
        )
        
        # Создаем главное меню
        await update_main_message(user_id)
        
    except Exception as e:
        logger.error(f"Ошибка в start_cmd: {e}")
        logger.error(traceback.format_exc())
        await message.answer(f"❌ Ошибка: {str(e)}")

@dp.message(Command("menu"))
async def menu_cmd(message: types.Message):
    user_id = message.from_user.id
    logger.info(f"Команда /menu от {user_id}")
    await update_main_message(user_id)

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

@dp.callback_query(F.data == "refresh")
async def refresh_callback(callback: CallbackQuery):
    """Обновление меню"""
    await callback.answer("🔄 Обновляю...")
    user_id = callback.from_user.id
    await update_main_message(user_id)

@dp.callback_query(F.data == "add_criteria")
async def add_criteria_callback(callback: CallbackQuery):
    await callback.message.answer(
        "✏️ <b>Введи ключевое слово и отклонение</b>\n\n"
        "Примеры:\n"
        "<code>Raf Simons 10</code> - отклонение 10%\n"
        "<code>Raf Simons 0</code> - точное совпадение\n"
        "<code>Nike</code> - отклонение 10% (по умолчанию)\n\n"
        "После добавления меню обновится автоматически",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "test_parser")
async def test_parser_callback(callback: CallbackQuery):
    """Тест парсера"""
    await callback.answer("🧪 Тестирую...")
    
    user_id = callback.from_user.id
    criteria = get_user_criteria(user_id)
    
    if not criteria:
        await bot.send_message(
            user_id,
            "⚠️ Сначала добавь критерий для теста!"
        )
        return
    
    # Берем первый критерий
    keyword = criteria[0][1]
    
    status_msg = await bot.send_message(user_id, f"🔍 Ищу '{keyword}'...")
    
    try:
        items = await fetch_items_for_keyword(keyword)
        
        if items:
            msg = f"✅ <b>Парсер работает!</b>\n"
            msg += f"━━━━━━━━━━━━━━━━━━━━━\n"
            msg += f"📦 Найдено: {len(items)} товаров\n\n"
            
            for i, item in enumerate(items[:3], 1):
                msg += f"<b>{i}.</b> {item['title'][:40]}\n"
                msg += f"   💰 {item['price_cny']} ¥\n"
                msg += f"   🌐 {item['site']}\n"
                msg += f"   🔗 <a href='{item['url']}'>Ссылка</a>\n\n"
            
            await status_msg.edit_text(msg, parse_mode="HTML", disable_web_page_preview=True)
        else:
            await status_msg.edit_text(
                f"❌ <b>Товары не найдены</b>\n\n"
                f"Запрос: {keyword}\n"
                f"Причины: блокировка или нет товаров"
            )
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)}")

@dp.callback_query(F.data == "show_all")
async def show_all_callback(callback: CallbackQuery):
    """Показывает все товары без фильтрации"""
    await callback.answer("📦 Загружаю все товары...")
    
    user_id = callback.from_user.id
    criteria = get_user_criteria(user_id)
    
    if not criteria:
        await callback.message.answer("⚠️ Сначала добавь критерий!")
        return
    
    all_items = []
    
    for crit_id, keyword, deviation in criteria:
        items = await fetch_items_for_keyword(keyword)
        for item in items:
            usd, rub = convert_price(item['price_cny'])
            all_items.append({
                "title": item['title'],
                "price": item['price_cny'],
                "usd": usd,
                "rub": rub,
                "url": item['url'],
                "site": item['site']
            })
    
    if all_items:
        msg = f"📦 <b>ВСЕ ТОВАРЫ (без фильтрации)</b>\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"📦 Всего: {len(all_items)}\n\n"
        
        for i, item in enumerate(all_items[:20], 1):
            msg += f"<b>{i}.</b> {item['title'][:40]}\n"
            msg += f"   💰 {item['price']} ¥ | {item['usd']}$ | {item['rub']}₽\n"
            msg += f"   🌐 {item['site']}\n"
            msg += f"   🔗 <a href='{item['url']}'>Ссылка</a>\n\n"
        
        if len(all_items) > 20:
            msg += f"⚠️ Показано 20 из {len(all_items)}"
        
        await callback.message.answer(msg, parse_mode="HTML", disable_web_page_preview=True)
    else:
        await callback.message.answer("😴 Товаров не найдено.")

@dp.callback_query(F.data.startswith("del_crit_"))
async def confirm_del_criteria(callback: CallbackQuery):
    user_id = callback.from_user.id
    crit_id = int(callback.data.split("_")[2])
    remove_criteria(crit_id, user_id)
    
    await callback.answer("✅ Критерий удален!")
    
    # Обновляем главное меню
    await update_main_message(user_id)

@dp.callback_query(F.data == "admin_list_users")
async def admin_list_users(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен.")
        return
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, username, first_name FROM users WHERE is_active = 1")
    users = c.fetchall()
    conn.close()
    
    if not users:
        await callback.message.answer("📭 Нет активных пользователей.")
    else:
        text = "👥 <b>Список активных пользователей:</b>\n\n"
        for uid, uname, fname in users:
            text += f"• {uid} (@{uname or 'нет юзернейма'}) — {fname or ''}\n"
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
            f"📊 Отклонение: <b>{deviation}%</b>\n\n"
            f"Меню обновляется...",
            parse_mode="HTML"
        )
        
        # Обновляем главное меню
        await update_main_message(user_id)

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

# --- Запуск бота ---

async def main():
    try:
        logger.info("Инициализация базы данных...")
        init_db()
        add_user(ADMIN_ID, "admin", "Admin")
        logger.info("База данных инициализирована")
        
        # Запускаем мониторинг
        logger.info("Запуск мониторинга...")
        asyncio.create_task(monitor_task())
        
        # Старт бота
        logger.info("Бот запущен!")
        await dp.start_polling(bot, skip_updates=True)
        
    except Exception as e:
        logger.error(f"Ошибка в main: {e}")
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(main())
