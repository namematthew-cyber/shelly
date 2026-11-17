import os

# Тесты не должны требовать реальных ключей: подставляем заглушки до импорта shelly.
os.environ.setdefault("GEMINI_API_KEYS", "AIzaSyTEST000000000000000000000000000")
os.environ.setdefault("SHELLY_TG_TOKEN", "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
os.environ.setdefault("SHELLY_ADMIN_ID", "1")
