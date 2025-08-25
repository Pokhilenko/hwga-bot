import logging
import sys
from db import setup_database, get_all_chat_poll_times, DB_FILE
import asyncio
import os

# Настраиваем логирование
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


async def test_database_operations():
    """Test various database operations"""
    logger.info("Testing database operations...")

    # Force error by temporarily making database read-only
    if os.path.exists(DB_FILE):
        # Только на macOS/Linux
        try:
            current_mode = os.stat(DB_FILE).st_mode
            os.chmod(DB_FILE, 0o444)  # Read-only для всех
            logger.info("Made database read-only for testing errors")

            # Попытка получить данные с кликабельной ссылкой на ошибку
            times = await get_all_chat_poll_times()
            logger.info(f"Got chat times: {times}")
        except Exception as e:
            logger.error(f"Expected error occurred: {e}")
        finally:
            # Вернуть права доступа
            os.chmod(DB_FILE, current_mode)
            logger.info("Restored database permissions")

    # Проверяем, что база данных работает нормально
    times = await get_all_chat_poll_times()
    logger.info(f"Got chat times: {times}")

    return True


async def main_async():
    """Async version of main"""
    try:
        logger.info("Testing database setup...")
        setup_database()
        logger.info("Database setup completed successfully!")

        # Тестируем операции с базой данных
        success = await test_database_operations()
        if success:
            logger.info("All database tests completed!")
    except Exception as e:
        logger.error(f"Error during tests: {e}")
        import traceback

        traceback.print_exc()
        return 1
    return 0


def main():
    """Main entry point"""
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
