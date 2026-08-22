import asyncio
import subprocess
import sys
import os
import time

print("🚀 Запуск бота на Railway...")
print(f"Python версия: {sys.version}")

def install_playwright():
    """Установка Playwright с обработкой ошибок"""
    try:
        print("📦 Установка Playwright браузеров...")
        
        # Устанавливаем playwright
        subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)
        
        # Устанавливаем браузеры в home директорию
        home = os.path.expanduser("~")
        browsers_path = os.path.join(home, ".cache", "ms-playwright")
        os.makedirs(browsers_path, exist_ok=True)
        
        # Устанавливаем chromium
        subprocess.run([
            sys.executable, "-m", "playwright", "install", 
            "chromium", 
            "--path", browsers_path
        ], check=True, capture_output=True)
        
        print("✅ Playwright успешно установлен!")
        return True
    except Exception as e:
        print(f"❌ Ошибка установки Playwright: {e}")
        return False

async def main():
    # Устанавливаем Playwright
    if not install_playwright():
        print("⚠️ Не удалось установить Playwright, пробуем альтернативный метод...")
        # Пробуем без playwright (только requests)
        os.environ["USE_REQUESTS"] = "1"
    
    # Импортируем и запускаем бота
    try:
        from bot import main as bot_main
        await bot_main()
    except Exception as e:
        print(f"❌ Ошибка запуска бота: {e}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    asyncio.run(main())
