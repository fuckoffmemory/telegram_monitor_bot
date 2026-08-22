import asyncio
import subprocess
import sys
import os

async def main():
    # Устанавливаем Playwright браузеры при запуске
    print("🚀 Установка Playwright браузеров...")
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    subprocess.run([sys.executable, "-m", "playwright", "install-deps"], check=True)
    print("✅ Playwright установлен!")
    
    # Импортируем и запускаем бота
    from bot import main as bot_main
    await bot_main()

if __name__ == "__main__":
    asyncio.run(main())
