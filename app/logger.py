import os
import logging
from logging.handlers import RotatingFileHandler

# --- Створюємо папку для логів, якщо її немає ---
os.makedirs("logs", exist_ok=True)

# --- Формат логів ---
formatter = logging.Formatter("%(asctime)s - [%(levelname)s] - %(name)s - %(message)s")

# --- Хендлер для файлу з ротацією (5 файлів по 10MB) ---
file_handler = RotatingFileHandler(
    "logs/bot.log", maxBytes=10_000_000, backupCount=5, encoding="utf-8"
)
file_handler.setFormatter(formatter)

# --- Хендлер для консолі ---
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

# --- Головний логер ---
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(console_handler)
