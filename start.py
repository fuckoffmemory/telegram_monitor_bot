import asyncio
import os
import sys

print("🚀 Запуск бота...")
print(f"Python: {sys.version}")
print(f"Директория: {os.getcwd()}")

async def main():
    try:
        token = os.getenv("BOT_TOKEN")
        admin = os.getenv("ADMIN_ID")
        
        if not token:
            print("❌ ОШИБКА: BOT_TOKEN не установлен!")
            return
        
        if not admin:
            print("❌ ОШИБКА: ADMIN_ID не установлен!")
            return
        
        print(f"✅ BOT_TOKEN: {token[:10]}...")
        print(f"✅ ADMIN_ID: {admin}")
        
        from bot import main as bot_main
        print("✅ Бот импортирован")
        await bot_main()
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    asyncio.run(main())
