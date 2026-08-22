#!/bin/bash

echo "🚀 Установка зависимостей..."
pip install -r requirements.txt

echo "🔧 Установка Playwright..."
playwright install chromium
playwright install-deps

echo "✅ Запуск бота..."
python start.py
