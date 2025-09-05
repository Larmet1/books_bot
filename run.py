import asyncio
import os
import inspect
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramRetryAfter, TelegramAPIError
from dotenv import load_dotenv
from app.handlers import router
from app.db import init_db
from app.logger import logger  # підключаємо логер

# --- Завантажуємо .env ---
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    logger.error("❌ Не знайдено BOT_TOKEN у .env файлі")
    raise ValueError("Не знайдено BOT_TOKEN у .env файлі")

# --- Головний об’єкт ---
bot = Bot(token=TOKEN)
dp = Dispatcher()


# --- Запуск ---
async def main():
    # Ініціалізація бази даних.
    # Підтримуємо і синхронну, і асинхронну реалізацію init_db.
    try:
        if inspect.iscoroutinefunction(init_db):
            await init_db()
        else:
            maybe_coro = init_db()
            if asyncio.iscoroutine(maybe_coro):
                await maybe_coro
    except Exception as e:
        logger.exception(f"Помилка ініціалізації БД: {e}")
        raise

    dp.include_router(router)
    try:
        logger.info("Бот запускається...")
        # Показуємо користувачам reply-клавіатуру при старті
        await dp.start_polling(bot, skip_updates=True)
    except TelegramRetryAfter as e:
        logger.warning(f"Отримали Flood Control. Спимо {e.retry_after} сек...")
        await asyncio.sleep(e.retry_after)
        return await main()  # пробуємо ще раз
    except TelegramAPIError as e:
        logger.error(f"Помилка Telegram API: {e}")
    except Exception as e:
        logger.exception(f"Непередбачена помилка: {e}")
    finally:
        # Закриваємо сесію бота (без помилки, якщо нема атрибуту)
        try:
            await bot.session.close()
        except Exception:
            pass
        logger.info("Бот завершив роботу")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот зупинено вручну")
