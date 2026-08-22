import asyncio
import random
import re
import logging
import time
from bs4 import BeautifulSoup
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def random_delay(min_sec=0.5, max_sec=2):
    """Случайная задержка"""
    time.sleep(random.uniform(min_sec, max_sec))

def clean_price(price_text):
    """Очистка цены от мусора"""
    if not price_text:
        return None
    
    price_clean = re.sub(r'[^\d.,]', '', price_text)
    price_clean = price_clean.replace(',', '')
    
    try:
        return float(price_clean)
    except:
        return None

def get_random_headers():
    """Генерация случайных заголовков"""
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    ]
    
    return {
        'User-Agent': random.choice(user_agents),
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

# ==================== ПАРСИНГ ПО КЛЮЧЕВОМУ СЛОВУ ====================

async def parse_mercari(keyword):
    """Парсинг Mercari по ключевому слову"""
    items = []
    logger.info(f"🔍 Парсинг Mercari: {keyword}")
    
    try:
        search_url = f"https://jp.mercari.com/search?keyword={keyword.replace(' ', '%20')}"
        headers = get_random_headers()
        headers.update({
            'Referer': 'https://jp.mercari.com/',
            'Origin': 'https://jp.mercari.com',
        })
        
        session = requests.Session()
        response = session.get(search_url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            cards = []
            selectors = [
                'a[href*="/item/"]',
                '.item-card',
                '.mercari-item',
                '[data-testid="item-card"]'
            ]
            
            for selector in selectors:
                found = soup.select(selector)
                if found:
                    cards = found
                    break
            
            if not cards:
                cards = soup.find_all('a', href=re.compile(r'/item/'))
            
            for card in cards[:30]:
                try:
                    price = None
                    price_selectors = ['.price', '.item-price', '[data-testid="price"]', '.number', '.bold']
                    
                    for selector in price_selectors:
                        price_elem = card.select_one(selector)
                        if price_elem:
                            price_text = price_elem.text.strip()
                            price = clean_price(price_text)
                            if price:
                                break
                    
                    if not price:
                        card_text = card.text
                        price_match = re.search(r'¥\s*([\d,]+\.?\d*)', card_text)
                        if price_match:
                            price = clean_price(price_match.group(1))
                    
                    if not price:
                        continue
                    
                    title = None
                    title_selectors = ['.item-name', '.title', '[data-testid="item-name"]', '.name', 'h3']
                    
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
                    
                    url = card.get('href')
                    if url:
                        if not url.startswith('http'):
                            url = f"https://jp.mercari.com{url}"
                    else:
                        continue
                    
                    items.append({
                        "title": title[:150],
                        "price_cny": price,
                        "url": url,
                        "site": "mercari"
                    })
                    
                    logger.info(f"✅ Mercari: {title[:30]}... - {price} ¥")
                    
                except Exception as e:
                    logger.error(f"Ошибка карточки Mercari: {e}")
                    continue
            
            logger.info(f"📊 Mercari: найдено {len(items)} товаров")
        else:
            logger.error(f"Mercari ошибка: {response.status_code}")
            
    except Exception as e:
        logger.error(f"Ошибка Mercari: {e}")
    
    return items

async def parse_goofish(keyword):
    """Парсинг Goofish по ключевому слову"""
    items = []
    logger.info(f"🔍 Парсинг Goofish: {keyword}")
    
    try:
        search_url = f"https://www.goofish.com/search?q={keyword.replace(' ', '+')}"
        headers = get_random_headers()
        headers.update({
            'Referer': 'https://www.goofish.com/',
            'Origin': 'https://www.goofish.com',
        })
        
        session = requests.Session()
        response = session.get(search_url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            cards = []
            selectors = [
                '.item-card',
                '.goods-item',
                '.product-item',
                'a[href*="/item/"]'
            ]
            
            for selector in selectors:
                found = soup.select(selector)
                if found:
                    cards = found
                    break
            
            if not cards:
                cards = soup.find_all('a', href=re.compile(r'/item/'))
            
            for card in cards[:30]:
                try:
                    price = None
                    price_selectors = ['.price', '.item-price', '.sale-price', '.number', '.actual-price']
                    
                    for selector in price_selectors:
                        price_elem = card.select_one(selector)
                        if price_elem:
                            price_text = price_elem.text.strip()
                            price = clean_price(price_text)
                            if price:
                                break
                    
                    if not price:
                        card_text = card.text
                        price_match = re.search(r'([\d,]+\.?\d*)\s*元', card_text)
                        if not price_match:
                            price_match = re.search(r'¥\s*([\d,]+\.?\d*)', card_text)
                        if price_match:
                            price = clean_price(price_match.group(1))
                    
                    if not price:
                        continue
                    
                    title = None
                    title_selectors = ['.title', '.item-title', '.name', '.goods-name', 'h3']
                    
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
                    
                    logger.info(f"✅ Goofish: {title[:30]}... - {price} ¥")
                    
                except Exception as e:
                    logger.error(f"Ошибка карточки Goofish: {e}")
                    continue
            
            logger.info(f"📊 Goofish: найдено {len(items)} товаров")
        else:
            logger.error(f"Goofish ошибка: {response.status_code}")
            
    except Exception as e:
        logger.error(f"Ошибка Goofish: {e}")
    
    return items

# ==================== ГЛАВНАЯ ФУНКЦИЯ ПОИСКА ====================

async def fetch_items_for_keyword(keyword):
    """Главная функция - собирает товары со всех сайтов по ключевому слову"""
    keyword = keyword.strip().lower()
    logger.info(f"🚀 Поиск: {keyword}")
    
    mercari_task = asyncio.create_task(parse_mercari(keyword))
    goofish_task = asyncio.create_task(parse_goofish(keyword))
    
    mercari_items = await mercari_task
    goofish_items = await goofish_task
    
    all_items = mercari_items + goofish_items
    
    logger.info(f"📊 ИТОГО: {len(all_items)} товаров")
    return all_items

# ==================== НОВАЯ ФУНКЦИЯ: ПОСЛЕДНИЕ ТОВАРЫ С ГЛАВНЫХ СТРАНИЦ ====================

async def fetch_latest_items(site):
    """Парсит последние товары с главной страницы сайта (без ключевого слова)"""
    items = []
    
    try:
        if site == 'mercari':
            url = "https://jp.mercari.com/"
            headers = get_random_headers()
            headers.update({
                'Referer': 'https://jp.mercari.com/',
                'Origin': 'https://jp.mercari.com',
            })
            
            response = requests.get(url, headers=headers, timeout=30)
            logger.info(f"Mercari главная статус: {response.status_code}")
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                cards = soup.find_all('a', href=re.compile(r'/item/'))
                logger.info(f"Mercari главная найдено карточек: {len(cards)}")
                
                for card in cards[:5]:
                    try:
                        price = None
                        price_elem = card.select_one('.price, .item-price, .number')
                        if price_elem:
                            price = clean_price(price_elem.text.strip())
                        
                        if not price:
                            card_text = card.text
                            price_match = re.search(r'¥\s*([\d,]+\.?\d*)', card_text)
                            if price_match:
                                price = clean_price(price_match.group(1))
                        
                        if not price:
                            continue
                        
                        title_elem = card.select_one('.item-name, .title, .name')
                        title = title_elem.text.strip() if title_elem else "Товар"
                        
                        if not title:
                            img = card.select_one('img')
                            if img and img.get('alt'):
                                title = img.get('alt')
                        
                        if not title:
                            title = "Товар"
                        
                        url_card = card.get('href')
                        if url_card and not url_card.startswith('http'):
                            url_card = f"https://jp.mercari.com{url_card}"
                        
                        items.append({
                            "title": title[:100],
                            "price_cny": price,
                            "url": url_card,
                            "site": "mercari"
                        })
                        logger.info(f"✅ Mercari главная: {title[:30]}... - {price} ¥")
                    except Exception as e:
                        logger.error(f"Ошибка карточки Mercari главная: {e}")
                        continue
        
        elif site == 'goofish':
            url = "https://www.goofish.com/"
            headers = get_random_headers()
            headers.update({
                'Referer': 'https://www.goofish.com/',
                'Origin': 'https://www.goofish.com',
            })
            
            response = requests.get(url, headers=headers, timeout=30)
            logger.info(f"Goofish главная статус: {response.status_code}")
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                cards = soup.find_all('a', href=re.compile(r'/item/'))
                logger.info(f"Goofish главная найдено карточек: {len(cards)}")
                
                for card in cards[:5]:
                    try:
                        price = None
                        price_elem = card.select_one('.price, .item-price, .sale-price')
                        if price_elem:
                            price = clean_price(price_elem.text.strip())
                        
                        if not price:
                            card_text = card.text
                            price_match = re.search(r'([\d,]+\.?\d*)\s*元', card_text)
                            if price_match:
                                price = clean_price(price_match.group(1))
                        
                        if not price:
                            continue
                        
                        title_elem = card.select_one('.title, .item-title, .name')
                        title = title_elem.text.strip() if title_elem else "Товар"
                        
                        if not title:
                            img = card.select_one('img')
                            if img and img.get('alt'):
                                title = img.get('alt')
                        
                        if not title:
                            title = "Товар"
                        
                        url_card = card.get('href')
                        if url_card and not url_card.startswith('http'):
                            url_card = f"https://www.goofish.com{url_card}"
                        
                        items.append({
                            "title": title[:100],
                            "price_cny": price,
                            "url": url_card,
                            "site": "goofish"
                        })
                        logger.info(f"✅ Goofish главная: {title[:30]}... - {price} ¥")
                    except Exception as e:
                        logger.error(f"Ошибка карточки Goofish главная: {e}")
                        continue
    
    except Exception as e:
        logger.error(f"fetch_latest_items error: {e}")
    
    return items

# ==================== ТЕСТ ====================

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
    
    print("\n🧪 Тестируем 'Последние 10'...")
    latest = await fetch_latest_items('mercari')
    print(f"Последние с Mercari: {len(latest)}")
    for item in latest:
        print(f"  - {item['title'][:30]}... {item['price_cny']}¥")

if __name__ == "__main__":
    asyncio.run(test_parser())
