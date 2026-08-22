import asyncio
import random
import re
import logging
import time
from bs4 import BeautifulSoup
import requests
from fake_useragent import UserAgent

logging.basicConfig(level=logging.INFO)

# --- Утилиты ---

def random_delay(min_sec=0.5, max_sec=2):
    """Случайная задержка"""
    time.sleep(random.uniform(min_sec, max_sec))

def clean_price(price_text):
    """Очистка цены от мусора"""
    if not price_text:
        return None
    
    # Убираем валюту и пробелы
    price_clean = re.sub(r'[^\d.,]', '', price_text)
    price_clean = price_clean.replace(',', '')
    
    try:
        return float(price_clean)
    except:
        return None

def get_random_headers():
    """Генерация случайных заголовков"""
    ua = UserAgent()
    return {
        'User-Agent': ua.random,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
    }

# --- ПАРСЕР MERCADO (jp.mercari.com) ---

async def parse_mercari(keyword):
    """
    Парсинг Mercari через requests + BeautifulSoup
    Возвращает список товаров
    """
    items = []
    logging.info(f"🔍 Начинаю парсинг Mercari: {keyword}")
    
    try:
        # Формируем URL для поиска
        search_url = f"https://jp.mercari.com/search?keyword={keyword.replace(' ', '%20')}"
        
        # Заголовки для имитации браузера
        headers = get_random_headers()
        headers.update({
            'Referer': 'https://jp.mercari.com/',
            'Origin': 'https://jp.mercari.com',
        })
        
        # Делаем запрос
        session = requests.Session()
        response = session.get(search_url, headers=headers, timeout=30)
        
        logging.info(f"Mercari статус: {response.status_code}")
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Ищем карточки товаров (разные селекторы)
            cards = []
            
            # Пробуем разные селекторы
            selectors = [
                'a[href*="/item/"]',
                '.item-card',
                '.mercari-item',
                '[data-testid="item-card"]',
                '.items-grid a',
                '.item-list a'
            ]
            
            for selector in selectors:
                found = soup.select(selector)
                if found:
                    cards = found
                    logging.info(f"Найдено {len(cards)} карточек по селектору: {selector}")
                    break
            
            # Если ничего не нашли, ищем все ссылки с /item/
            if not cards:
                cards = soup.find_all('a', href=re.compile(r'/item/'))
                logging.info(f"Найдено {len(cards)} ссылок с /item/")
            
            # Парсим каждую карточку
            for card in cards[:30]:  # Ограничиваем 30 товаров
                try:
                    # --- Парсим цену ---
                    price = None
                    price_selectors = [
                        '.price',
                        '.item-price',
                        '[data-testid="price"]',
                        '.number',
                        '.bold',
                        '.sale-price',
                        '.item-price-number'
                    ]
                    
                    for selector in price_selectors:
                        price_elem = card.select_one(selector)
                        if price_elem:
                            price_text = price_elem.text.strip()
                            price = clean_price(price_text)
                            if price:
                                break
                    
                    # Если цена не найдена в карточке, ищем в тексте
                    if not price:
                        card_text = card.text
                        # Ищем цену с символом ¥
                        price_match = re.search(r'¥\s*([\d,]+\.?\d*)', card_text)
                        if price_match:
                            price = clean_price(price_match.group(1))
                    
                    if not price:
                        continue
                    
                    # --- Парсим название ---
                    title = None
                    title_selectors = [
                        '.item-name',
                        '.title',
                        '[data-testid="item-name"]',
                        '.name',
                        'h3',
                        'h2'
                    ]
                    
                    for selector in title_selectors:
                        title_elem = card.select_one(selector)
                        if title_elem:
                            title = title_elem.text.strip()
                            break
                    
                    # Если название не найдено, берем из alt картинки
                    if not title:
                        img = card.select_one('img')
                        if img and img.get('alt'):
                            title = img.get('alt')
                    
                    if not title:
                        # Берем первые 50 символов текста
                        card_text = card.text.strip()
                        title = card_text[:50] if len(card_text) > 50 else card_text
                    
                    if not title:
                        title = f"Товар {keyword}"
                    
                    # --- Парсим ссылку ---
                    url = card.get('href')
                    if url:
                        if not url.startswith('http'):
                            url = f"https://jp.mercari.com{url}"
                    else:
                        continue
                    
                    # Добавляем товар
                    items.append({
                        "title": title[:150],
                        "price_cny": price,
                        "url": url,
                        "site": "mercari"
                    })
                    
                    logging.info(f"✅ Mercari: {title[:30]}... - {price} ¥")
                    
                except Exception as e:
                    logging.error(f"Ошибка парсинга карточки Mercari: {e}")
                    continue
            
            logging.info(f"📊 Mercari: найдено {len(items)} товаров")
            
        else:
            logging.error(f"Mercari ошибка: {response.status_code}")
            
    except Exception as e:
        logging.error(f"Ошибка парсинга Mercari: {e}")
    
    return items

# --- ПАРСЕР GOOFISH (goofish.com) ---

async def parse_goofish(keyword):
    """
    Парсинг Goofish через requests + BeautifulSoup
    """
    items = []
    logging.info(f"🔍 Начинаю парсинг Goofish: {keyword}")
    
    try:
        # Формируем URL
        search_url = f"https://www.goofish.com/search?q={keyword.replace(' ', '+')}"
        
        headers = get_random_headers()
        headers.update({
            'Referer': 'https://www.goofish.com/',
            'Origin': 'https://www.goofish.com',
        })
        
        session = requests.Session()
        response = session.get(search_url, headers=headers, timeout=30)
        
        logging.info(f"Goofish статус: {response.status_code}")
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Ищем карточки товаров
            cards = []
            
            selectors = [
                '.item-card',
                '.goods-item',
                '.product-item',
                '[class*="item"]',
                'a[href*="/item/"]',
                '.search-item',
                '.list-item'
            ]
            
            for selector in selectors:
                found = soup.select(selector)
                if found:
                    cards = found
                    logging.info(f"Найдено {len(cards)} карточек по селектору: {selector}")
                    break
            
            if not cards:
                cards = soup.find_all('a', href=re.compile(r'/item/'))
                logging.info(f"Найдено {len(cards)} ссылок с /item/")
            
            # Парсим карточки
            for card in cards[:30]:
                try:
                    # --- Парсим цену ---
                    price = None
                    price_selectors = [
                        '.price',
                        '.item-price',
                        '.sale-price',
                        '.number',
                        '.price-number',
                        '.actual-price'
                    ]
                    
                    for selector in price_selectors:
                        price_elem = card.select_one(selector)
                        if price_elem:
                            price_text = price_elem.text.strip()
                            price = clean_price(price_text)
                            if price:
                                break
                    
                    # Если цена не найдена, ищем в тексте
                    if not price:
                        card_text = card.text
                        price_match = re.search(r'([\d,]+\.?\d*)\s*元', card_text)
                        if not price_match:
                            price_match = re.search(r'¥\s*([\d,]+\.?\d*)', card_text)
                        if price_match:
                            price = clean_price(price_match.group(1))
                    
                    if not price:
                        continue
                    
                    # --- Парсим название ---
                    title = None
                    title_selectors = [
                        '.title',
                        '.item-title',
                        '.name',
                        '.goods-name',
                        'h3',
                        'h2'
                    ]
                    
                    for selector in title_selectors:
                        title_elem = card.select_one(selector)
                        if title_elem:
                            title = title_elem.text.strip()
                            break
                    
                    if not title:
                        img = card.select_one('img')
                        if img and img.get('alt'):
                            title = img.get('alt')
                    
                    if not title:
                        card_text = card.text.strip()
                        title = card_text[:50] if len(card_text) > 50 else card_text
                    
                    if not title:
                        title = f"Товар {keyword}"
                    
                    # --- Парсим ссылку ---
                    url = card.get('href')
                    if url:
                        if not url.startswith('http'):
                            url = f"https://www.goofish.com{url}"
                    else:
                        continue
                    
                    items.append({
                        "title": title[:150],
                        "price_cny": price,
                        "url": url,
                        "site": "goofish"
                    })
                    
                    logging.info(f"✅ Goofish: {title[:30]}... - {price} ¥")
                    
                except Exception as e:
                    logging.error(f"Ошибка парсинга карточки Goofish: {e}")
                    continue
            
            logging.info(f"📊 Goofish: найдено {len(items)} товаров")
            
        else:
            logging.error(f"Goofish ошибка: {response.status_code}")
            
    except Exception as e:
        logging.error(f"Ошибка парсинга Goofish: {e}")
    
    return items

# --- ГЛАВНАЯ ФУНКЦИЯ ---

async def fetch_items_for_keyword(keyword):
    """
    Главная функция - собирает товары со всех сайтов
    """
    keyword = keyword.strip().lower()
    logging.info(f"🚀 Начинаю поиск по запросу: {keyword}")
    
    # Парсим оба сайта параллельно
    mercari_task = asyncio.create_task(parse_mercari(keyword))
    goofish_task = asyncio.create_task(parse_goofish(keyword))
    
    # Ждем результаты
    mercari_items = await mercari_task
    goofish_items = await goofish_task
    
    all_items = mercari_items + goofish_items
    
    logging.info(f"📊 ИТОГО найдено товаров: {len(all_items)}")
    return all_items

# --- ТЕСТОВАЯ ФУНКЦИЯ ---

async def test_parser():
    """Тестирование парсера"""
    print("🧪 Тестируем парсер...")
    
    keyword = "Raf Simons"
    items = await fetch_items_for_keyword(keyword)
    
    print(f"\n📦 Найдено {len(items)} товаров:")
    for i, item in enumerate(items[:5], 1):
        print(f"{i}. {item['title']}")
        print(f"   Цена: {item['price_cny']} ¥")
        print(f"   Сайт: {item['site']}")
        print(f"   Ссылка: {item['url']}")
        print()

if __name__ == "__main__":
    # Запускаем тест
    asyncio.run(test_parser())
