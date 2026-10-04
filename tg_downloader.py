# FILE: tg_downloader.py | VERSION: 1.1.0 | DATE: 2026-10-04
"""
tg_downloader.py — Скачивание файлов из Telegram через MTProto
===============================================================
Работает для файлов любого размера (до 2GB).
Требует предварительной авторизации через auth_telethon.py.

ВАЖНО:
- Авторизация выполняется ТОЛЬКО через auth_telethon.py (start.bat)
- Этот модуль только подключается к существующей сессии
- Если сессия отсутствует или устарела — сообщает об этом чётко
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR     = Path(__file__).resolve().parent
CACHE_DIR    = BASE_DIR / "files_cache"
SESSION_FILE = str(BASE_DIR / "bot_session")

try:
    from config import TG_API_ID, TG_API_HASH
except ImportError:
    TG_API_ID   = int(os.environ.get("TG_API_ID", "0"))
    TG_API_HASH = os.environ.get("TG_API_HASH", "")

_client = None


async def get_client():
    """
    Возвращает подключённый авторизованный клиент Telethon.
    Использует connect() — НЕ start().
    start() запрашивает телефон при проблемах с сессией —
    это конфликтует с auth_telethon.py.
    """
    global _client

    if not TG_API_ID or not TG_API_HASH:
        raise RuntimeError(
            "TG_API_ID / TG_API_HASH не заданы в config.py"
        )

    # Возвращаем существующий клиент если подключён и авторизован
    if _client is not None and _client.is_connected():
        if await _client.is_user_authorized():
            return _client
        # Подключён но не авторизован — отключаем и пересоздаём
        await _client.disconnect()
        _client = None

    try:
        from telethon import TelegramClient
    except ImportError:
        raise RuntimeError(
            "telethon не установлен. Выполните: pip install telethon"
        )

    client = TelegramClient(
        SESSION_FILE,
        TG_API_ID,
        TG_API_HASH,
        receive_updates=False,  # загрузчику обновления не нужны
    )

    await client.connect()

    if not await client.is_user_authorized():
        await client.disconnect()
        raise RuntimeError(
            "Telethon сессия устарела или отсутствует.\n"
            "Остановите бота и запустите start.bat для повторной авторизации."
        )

    _client = client
    me = await client.get_me()
    logger.info(
        "Telethon подключён как %s (@%s)",
        me.first_name, me.username or ""
    )
    return _client


async def download_file_by_message(
    chat_id: int,
    message_id: int,
    filename: str,
    progress_callback=None,
) -> dict:
    """
    Скачивает файл из сообщения Telegram через MTProto.
    Работает для файлов любого размера (до 2GB).

    Аргументы:
        chat_id           — id чата/группы
        message_id        — id сообщения с файлом
        filename          — имя для сохранения
        progress_callback — async func(current, total) для прогресса

    Возвращает dict:
        success    — bool
        local_path — str путь к файлу или ""
        size_bytes — int размер файла
        error      — str сообщение об ошибке или ""
    """
    result = {"success": False, "local_path": "", "size_bytes": 0, "error": ""}

    CACHE_DIR.mkdir(exist_ok=True)
    local_path = CACHE_DIR / filename

    try:
        client = await get_client()

        message = await client.get_messages(chat_id, ids=message_id)
        if not message or not message.file:
            result["error"] = "Сообщение не найдено или не содержит файл"
            return result

        file_size = message.file.size or 0
        logger.info(
            "Скачиваю через MTProto: %s (%d MB)",
            filename, file_size // 1024 // 1024
        )

        async def _progress(current, total):
            if progress_callback and total:
                await progress_callback(current, total)

        await client.download_media(
            message,
            file=str(local_path),
            progress_callback=_progress,
        )

        if local_path.exists():
            result["success"]    = True
            result["local_path"] = str(local_path)
            result["size_bytes"] = local_path.stat().st_size
            logger.info(
                "Скачан: %s (%d MB)",
                filename, result["size_bytes"] // 1024 // 1024
            )
        else:
            result["error"] = "Файл не появился после скачивания"

    except RuntimeError as e:
        result["error"] = str(e)
        logger.error("Ошибка конфигурации Telethon: %s", e)
    except Exception as e:
        result["error"] = str(e)
        logger.error("Ошибка скачивания %s: %s", filename, e)

    return result


async def is_available() -> bool:
    """
    Проверяет что Telethon настроен, установлен и сессия рабочая.
    Используется в bot.py перед вызовом download_file_by_message.
    """
    if not TG_API_ID or not TG_API_HASH:
        return False

    session = BASE_DIR / "bot_session.session"
    if not session.exists():
        return False

    try:
        from telethon import TelegramClient
        client = TelegramClient(
            SESSION_FILE,
            TG_API_ID,
            TG_API_HASH,
            receive_updates=False,
        )
        await client.connect()
        ok = await client.is_user_authorized()
        await client.disconnect()
        return ok
    except Exception:
        return False
