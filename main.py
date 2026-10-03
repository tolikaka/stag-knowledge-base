# FILE: main.py | VERSION: 1.1.0 | DATE: 2026-10-04
"""
main.py — Точка запуска AI_Diag_UZ Bot
========================================
Авторизация Telethon выполняется в auth_telethon.py (до запуска main.py).
main.py только проверяет статус сессии и запускает бота.
"""

import asyncio
import logging
import os
import sys
import subprocess
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Только корень в sys.path — все .py файлы в корне C:\stag_bot\
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.join(BASE_DIR, "ai_diag_uz.log"),
            encoding="utf-8"
        ),
    ],
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telethon").setLevel(logging.WARNING)
logging.getLogger("telegram.ext.Updater").setLevel(logging.WARNING)
logging.getLogger("telegram.ext.Application").setLevel(logging.WARNING)
logging.getLogger("telegram.error").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def install_package(package: str, import_name: str = None) -> bool:
    """Устанавливает пакет если отсутствует."""
    name = import_name or package.split("==")[0].split(">=")[0]
    try:
        __import__(name)
        return True
    except ImportError:
        pass
    logger.info("  Устанавливаю %s...", package)
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", package, "--quiet"],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode == 0:
            try:
                __import__(name)
                logger.info("  %s: установлен OK", package)
                return True
            except ImportError:
                pass
        logger.warning("  %s: ошибка установки", package)
    except Exception as e:
        logger.warning("  %s: %s", package, e)
    return False


def check_dependencies():
    """Проверяет и устанавливает обязательные зависимости."""
    logger.info("  Проверка зависимостей...")

    # Обязательные
    for pkg, imp in [("aiohttp", None), ("Pillow", "PIL")]:
        try:
            __import__(imp or pkg)
            logger.info("  %s: OK", pkg)
        except ImportError:
            install_package(pkg, imp)

    # Telethon — только установка если нужен, авторизация в auth_telethon.py
    try:
        from config import TG_API_ID, TG_API_HASH
        if TG_API_ID and TG_API_HASH:
            try:
                import telethon
                logger.info("  telethon %s: OK", telethon.__version__)
            except ImportError:
                install_package("telethon")

            # Только статус — никакой авторизации здесь
            session = os.path.join(BASE_DIR, "bot_session.session")
            if os.path.exists(session):
                logger.info("  Telethon: сессия найдена")
            else:
                logger.warning(
                    "  Telethon: сессия не найдена — "
                    "скачивание файлов > 20MB недоступно"
                )
    except (ImportError, AttributeError):
        logger.info("  Telethon: TG_API_ID не задан")


def run_admin_in_thread():
    """Запускает Flask веб-панель в отдельном потоке."""
    try:
        from admin import run_admin
        logger.info("  Web-panel: http://localhost:8080")
        run_admin()
    except Exception as e:
        logger.error("Admin panel error: %s", e)


def main():
    logger.info("=" * 60)
    logger.info("  AI_Diag_UZ - Usta  |  CarDiag UZ Bot")
    logger.info("=" * 60)

    try:
        import config  # noqa
        logger.info("  config.py: OK")
    except ImportError:
        logger.warning("  config.py не найден!")

    # Создаём папки для данных
    for subdir in ["knowledge_base", "files_cache"]:
        os.makedirs(os.path.join(BASE_DIR, subdir), exist_ok=True)

    # Создаём file_catalog.json если нет
    import json
    catalog_path = os.path.join(BASE_DIR, "files_cache", "file_catalog.json")
    if not os.path.exists(catalog_path):
        with open(catalog_path, "w", encoding="utf-8") as f:
            json.dump(
                {"version": "1.0", "last_updated": "", "files": []},
                f, ensure_ascii=False, indent=2
            )
        logger.info("  file_catalog.json: создан")

    # Зависимости
    check_dependencies()

    # Создаём чистый event loop для бота
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Flask в отдельном потоке
    threading.Thread(target=run_admin_in_thread, daemon=True).start()

    # Запуск бота
    logger.info("  Запускаем бота...")
    from bot import main as bot_main
    bot_main()


if __name__ == "__main__":
    main()
