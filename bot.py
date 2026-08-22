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

from config import ADMIN_ID, BOT_TOKEN, CHECK_INTERVAL
from database import *
from parser import fetch_items_for_keyword

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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

# Кеш для сообщений пользователей (чтобы обновлять их)
user_messages = {}

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
            resp = await session.get("https://api.exchangerate-api.com/v4/latest/CNY")
            data = await resp.json()
            currency_cache["cny_to_usd"] = data["rates"].get("USD", 0.14)
            currency_cache["cny_to_rub"] = data["rates"].get("RUB", 12.5)
            currency_cache["last_update"] = now
            logging.info(f"Курсы обновлены")
    except Exception as e:
        logging.error(f"Ошибка обновления курсов: {e}")

def convert_price(cny):
    """Конвертирует юани в доллары и рубли"""
    usd = cny * currency_cache["cny_to_usd"]
    rub = cny * currency_cache["cny_to_rub"]
    return round(usd, 2), round(rub, 2)

def check_deviation(item_price, avg_price, user_deviation, show_all=False):
    """Проверяет отклонение цены"""
    if show_all:  # Режим "Все товары"
        return True
    
    if avg_price is None or avg_price == 0:
        return True
    diff_percent = abs((item_price - avg_price) / avg_price) * 100
    if item_price > avg_price:
        return True
    else:
        return diff_percent <= user_deviation

async def send_or_update_message(user_id, text, keyboard=None):
    """Отправляет новое сообщение или обновляет существующее"""
    # Если у пользователя уже есть сообщение, обновляем его
    if user_id in user_messages:
        try:
            await bot.edit_message_text(
                text,
                chat_id=user_id,
                message_id=user_messages[user_id],
                parse_mode="HTML",
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
            return
        except Exception as e:
            # Если не удалось обновить (сообщение удалено или изменилось), отправляем новое
            logging.warning(f"Не удалось обновить сообщение: {e}")
            del user_messages[user_id]
    
    # Отправляем новое сообщение
    msg = await bot.send_message(
        user_id,
        text,
        parse_mode="HTML",
        reply_markup=keyboard,
        disable_web_page_preview=True
    )
    user_messages[user_id] = msg.message_id

async def monitor_task():
    """Фоновый мониторинг с обновлением одного сообщения"""
    await bot.send_message(ADMIN_ID, "🚀 Бот запущен и начал мониторинг!")
    
    while True:
        try:
            await update_currency()
            users = get_all_active_users()
            
            for user_id in users:
                criteria_list = get_user_criteria(user_id)
                if not criteria_list:
                    continue
                
                all_found_items = []
                
                for crit_id, keyword, deviation in criteria_list:
                    items = await fetch_items_for_keyword(keyword)
                    
                    for item in items:
                        avg_price = get_average_price(keyword, item['site'])
                        save_price_cache(keyword, item['site'], item['price_cny'], item['url'], item['title'])
                        
                        # Проверяем отклонение
                        if not check_deviation(item['price_cny'], avg_price, deviation):
                            continue
                        
                        usd, rub = convert_price(item['price_cny'])
                        
                        if avg_price and avg_price > 0:
                            dev_percent = round(((item['price_cny'] - avg_price) / avg_price) * 100, 1)
                        else:
                            dev_percent = 0
                        
                        all_found_items.append({
                            "title": item['title'],
                            "price": item['price_cny'],
                            "usd": usd,
                            "rub": rub,
                            "url": item['url'],
                            "site": item['site'],
                            "deviation": dev_percent,
                            "keyword": keyword
                        })
                
                # Формируем одно сообщение со всеми товарами
                if all_found_items:
                    # Берем первые 10 товаров (чтобы не перегружать)
                    items_to_show = all_found_items[:10]
                    total_count = len(all_found_items)
                    
                    msg = f"🔄 <b>МОНИТОРИНГ ТОВАРОВ</b>\n"
                    msg += f"━━━━━━━━━━━━━━━━━━━━━\n"
                    msg += f"📦 Найдено новых: {total_count}\n"
                    msg += f"🕒 {datetime.now().strftime('%H:%M:%S')}\n"
                    msg += f"━━━━━━━━━━━━━━━━━━━━━\n\n"
                    
                    for i, item in enumerate(items_to_show, 1):
                        msg += f"<b>{i}.</b> {item['title'][:60]}\n"
                        msg += f"   🌐 {item['site']}\n"
                        msg += f"   💰 {item['price']} ¥ | {item['usd']}$ | {item['rub']}₽\n"
                        msg += f"   📊 Отклонение: {item['deviation']}%\n"
                        msg += f"   🔗 <a href='{item['url']}'>Ссылка</a>\n"
                        msg += f"━━━━━━━━━━━━━━━━━━━━━\n"
                    
                    if total_count > 10:
                        msg += f"\n⚠️ Показано 10 из {total_count} товаров"
                    
                    # Кнопка "Обновить" для ручного обновления
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔄 Обновить сейчас", callback_data="refresh")]
                    ])
                    
                    await send_or_update_message(user_id, msg, keyboard)
                else:
                    # Если товаров нет - показываем это
                    msg = f"🔄 <b>МОНИТОРИНГ ТОВАРОВ</b>\n"
                    msg += f"━━━━━━━━━━━━━━━━━━━━━\n"
                    msg += f"😴 Новых товаров нет\n"
                    msg += f"🕒 {datetime.now().strftime('%H:%M:%S')}\n"
                    msg += f"━━━━━━━━━━━━━━━━━━━━━\n"
                    msg += f"\n💡 <i>Товары появятся здесь автоматически</i>"
                    
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔄 Обновить сейчас", callback_data="refresh")]
                    ])
                    
                    await send_or_update_message(user_id, msg, keyboard)
            
            await asyncio.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            logging.error(f"Ошибка в мониторинге: {e}")
            await asyncio.sleep(60)

# --- Команды бота ---

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    add_user(user_id, message.from_user.username or "", message.from_user.first_name or "")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить критерий", callback_data="add_criteria")],
        [InlineKeyboardButton(text="📋 Мои критерии", callback_data="my_criteria")],
        [InlineKeyboardButton(text="❌ Удалить критерий", callback_data="del_criteria")],
        [InlineKeyboardButton(text="🧪 Тест парсера", callback_data="test_parser")],
        [InlineKeyboardButton(text="📦 Все товары (без фильтра)", callback_data="show_all")]
    ])
    
    await message.answer(
        "👋 Привет! Я бот-мониторинг площадок Mercari и Goofish.\n\n"
        "📌 <b>Как использовать:</b>\n"
        "• Добавь критерий: <code>Raf Simons 10</code>\n"
        "• Я буду присылать ОДНО сообщение с ВСЕМИ товарами\n"
        "• Сообщение будет обновляться автоматически\n\n"
        "🧪 Нажми <b>'Тест парсера'</b> чтобы проверить работу",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

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
    """Принудительное обновление"""
    await callback.answer("🔄 Обновляю...")
    # Просто удаляем кеш сообщения, чтобы оно пересоздалось
    if callback.from_user.id in user_messages:
        del user_messages[callback.from_user.id]
    # Мониторинг обновится сам через CHECK_INTERVAL

@dp.callback_query(F.data == "test_parser")
async def test_parser_callback(callback: CallbackQuery):
    """Тест парсера"""
    await callback.answer("🧪 Тестирую парсер...")
    
    user_id = callback.from_user.id
    
    # Отправляем статус
    status_msg = await bot.send_message(user_id, "🔍 Ищу товары по запросу 'Raf Simons'...")
    
    try:
        # Делаем тестовый запрос
        items = await fetch_items_for_keyword("Raf Simons")
        
        if items:
            msg = f"✅ <b>Парсер работает!</b>\n"
            msg += f"━━━━━━━━━━━━━━━━━━━━━\n"
            msg += f"📦 Найдено товаров: {len(items)}\n\n"
            
            for i, item in enumerate(items[:5], 1):
                msg += f"<b>{i}.</b> {item['title'][:50]}\n"
                msg += f"   💰 {item['price_cny']} ¥\n"
                msg += f"   🌐 {item['site']}\n"
                msg += f"   🔗 <a href='{item['url']}'>Ссылка</a>\n\n"
            
            if len(items) > 5:
                msg += f"⚠️ Показано 5 из {len(items)} товаров"
            
            await status_msg.edit_text(msg, parse_mode="HTML", disable_web_page_preview=True)
        else:
            await status_msg.edit_text(
                "❌ <b>Товары не найдены</b>\n\n"
                "Возможные причины:\n"
                "• Сайты блокируют запросы\n"
                "• Нет товаров по запросу 'Raf Simons'\n"
                "• Нужно обновить селекторы парсера",
                parse_mode="HTML"
            )
    except Exception as e:
        await status_msg.edit_text(
            f"❌ <b>Ошибка парсера:</b>\n"
            f"<code>{str(e)}</code>",
            parse_mode="HTML"
        )
        logging.error(f"Ошибка теста парсера: {e}")

@dp.callback_query(F.data == "show_all")
async def show_all_callback(callback: CallbackQuery):
    """Включает режим показа всех товаров без фильтрации"""
    await callback.answer("📦 Показываю все товары...")
    
    user_id = callback.from_user.id
    criteria = get_user_criteria(user_id)
    
    if not criteria:
        await callback.message.answer("⚠️ Сначала добавь хотя бы один критерий для поиска.")
        return
    
    # Показываем все товары без фильтрации
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
                "site": item['site'],
                "keyword": keyword
            })
    
    if all_items:
        msg = f"📦 <b>ВСЕ ТОВАРЫ (без фильтрации)</b>\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"📦 Найдено: {len(all_items)}\n\n"
        
        for i, item in enumerate(all_items[:15], 1):
            msg += f"<b>{i}.</b> {item['title'][:50]}\n"
            msg += f"   💰 {item['price']} ¥ | {item['usd']}$ | {item['rub']}₽\n"
            msg += f"   🌐 {item['site']} | 🔗 <a href='{item['url']}'>Ссылка</a>\n\n"
        
        if len(all_items) > 15:
            msg += f"⚠️ Показано 15 из {len(all_items)} товаров"
        
        await callback.message.answer(msg, parse_mode="HTML", disable_web_page_preview=True)
    else:
        await callback.message.answer("😴 Товаров не найдено.")

@dp.callback_query(F.data == "add_criteria")
async def add_criteria_callback(callback: CallbackQuery):
    await callback.message.answer(
        "✏️ Введи ключевое слово и через пробел отклонение в %.\n\n"
        "Примеры:\n"
        "<code>Raf Simons 10</code> - с отклонением 10%\n"
        "<code>Raf Simons 0</code> - только точное совпадение\n"
        "<code>Nike</code> - с отклонением 10% (по умолчанию)",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "my_criteria")
async def my_criteria_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    criteria = get_user_criteria(user_id)
    
    if not criteria:
        await callback.message.answer("📭 У тебя пока нет добавленных критериев.")
    else:
        text = "📋 <b>Твои критерии:</b>\n\n"
        for cid, keyword, dev in criteria:
            text += f"• <b>{keyword}</b> (отклонение: {dev}%)\n"
        await callback.message.answer(text, parse_mode="HTML")
    
    await callback.answer()

@dp.callback_query(F.data == "del_criteria")
async def del_criteria_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    criteria = get_user_criteria(user_id)
    
    if not criteria:
        await callback.message.answer("📭 У тебя нет критериев для удаления.")
        await callback.answer()
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for cid, keyword, dev in criteria:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"❌ {keyword} ({dev}%)",
                callback_data=f"del_crit_{cid}"
            )
        ])
    
    await callback.message.answer("Выбери критерий для удаления:", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data.startswith("del_crit_"))
async def confirm_del_criteria(callback: CallbackQuery):
    user_id = callback.from_user.id
    crit_id = int(callback.data.split("_")[2])
    remove_criteria(crit_id, user_id)
    
    # Удаляем кеш сообщения
    if user_id in user_messages:
        del user_messages[user_id]
    
    await callback.message.answer("✅ Критерий удален.")
    await callback.answer()

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
    
    await callback.message.answer("✏️ Введи Telegram ID пользователя, которого нужно добавить:")
    await callback.answer()

@dp.callback_query(F.data == "admin_del_user")
async def admin_del_user(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен.")
        return
    
    await callback.message.answer("✏️ Введи Telegram ID пользователя, которого нужно удалить:")
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
        
        # Удаляем кеш сообщения, чтобы обновилось
        if user_id in user_messages:
            del user_messages[user_id]
        
        await message.answer(
            f"✅ Критерий добавлен!\n"
            f"📌 Слово: <b>{keyword}</b>\n"
            f"📊 Отклонение: <b>{deviation}%</b>\n\n"
            f"Скоро появится первое уведомление.",
            parse_mode="HTML"
        )

# --- Админ: добавление пользователя по ID ---

@dp.message(F.text.regexp(r'^\d+$'))
async def admin_add_user_by_id(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    user_id = int(message.text)
    add_user(user_id)
    await message.answer(f"✅ Пользователь {user_id} добавлен в базу.")

# --- Админ: удаление пользователя ---

@dp.message(F.text.regexp(r'^del_\d+$'))
async def admin_del_user_by_id(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    user_id = int(message.text.split('_')[1])
    remove_user(user_id)
    await message.answer(f"✅ Пользователь {user_id} удален из базы.")

# --- Запуск бота ---

async def main():
    init_db()
    add_user(ADMIN_ID, "admin", "Admin")
    
    # Запускаем мониторинг
    asyncio.create_task(monitor_task())
    
    # Старт бота
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
