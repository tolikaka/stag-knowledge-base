import asyncio
import logging
import os
import sys
import subprocess
import threading

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
ADMIN_DIR = os.path.join(BASE_DIR, "admin")

for p in [ADMIN_DIR, BASE_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

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
    logger.info("  Проверка зависимостей...")

    for pkg, imp in [("aiohttp", None), ("Pillow", "PIL")]:
        try:
            __import__(imp or pkg)
            logger.info("  %s: OK", pkg)
        except ImportError:
            install_package(pkg, imp)

    # Telethon — устанавливаем если задан API_ID
    try:
        from config import TG_API_ID, TG_API_HASH
        if TG_API_ID and TG_API_HASH:
            try:
                import telethon
                logger.info("  telethon %s: OK", telethon.__version__)
            except ImportError:
                install_package("telethon")
            # Статус сессии
            session = os.path.join(BASE_DIR, "bot_session.session")
            if os.path.exists(session):
                logger.info("  Telethon: сессия найдена")
            else:
                logger.warning(
                    "  Telethon: сессия не найдена.\n"
                    "  Скачивание файлов > 20MB недоступно.\n"
                    "  Перезапустите start.bat для авторизации."
                )
    except (ImportError, AttributeError):
        logger.info("  Telethon: TG_API_ID не задан")


def run_admin_in_thread():
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

    for subdir in ["knowledge_base", "files_cache"]:
        os.makedirs(os.path.join(BASE_DIR, subdir), exist_ok=True)

    import json
    catalog_path = os.path.join(BASE_DIR, "files_cache", "file_catalog.json")
    if not os.path.exists(catalog_path):
        with open(catalog_path, "w", encoding="utf-8") as f:
            json.dump(
                {"version": "1.0", "last_updated": "", "files": []},
                f, ensure_ascii=False, indent=2
            )

    check_dependencies()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    threading.Thread(target=run_admin_in_thread, daemon=True).start()

    logger.info("  Запускаем бота...")
    from bot import main as bot_main
    bot_main()


if __name__ == "__main__":
    main()
