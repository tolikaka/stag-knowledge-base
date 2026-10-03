"""
tg_downloader.py — Скачивание файлов из Telegram любого размера
================================================================

Использует Telethon (MTProto Client API) — работает без ограничения 20MB.

НАСТРОЙКА (один раз):
1. Получите API_ID и API_HASH:
   - Откройте https://my.telegram.org
   - Войдите по номеру телефона
   - Apps → Create new application
   - Скопируйте api_id и api_hash в config.py

2. Добавьте в config.py:
   TG_API_ID   = 12345678          # числовой id
   TG_API_HASH = "abcdef1234567890"  # строка

3. При первом запуске бота — введите номер телефона и код из Telegram
   (создаётся файл сессии bot_session.session — храните его как config.py)

ВАЖНО: сессия создаётся ОТ ИМЕНИ ВАШЕГО АККАУНТА (не бота).
Аккаунт должен быть участником группы откуда скачиваются файлы.
"""

import asyncio
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_DIR = Path("files_cache")
SESSION_FILE = "bot_session"   # имя файла сессии (без .session)

try:
    from config import TG_API_ID, TG_API_HASH
except ImportError:
    TG_API_ID   = int(os.environ.get("TG_API_ID", "0"))
    TG_API_HASH = os.environ.get("TG_API_HASH", "")

_client = None   # единственный экземпляр Telethon клиента


async def get_client():
    """
    Возвращает подключённый Telethon клиент.
    При первом вызове создаёт клиент и подключается.
    """
    global _client
    if _client and _client.is_connected():
        return _client

    if not TG_API_ID or not TG_API_HASH:
        raise RuntimeError(
            "TG_API_ID и TG_API_HASH не заданы в config.py\\n"
            "Получите их на https://my.telegram.org → Apps"
        )

    try:
        from telethon import TelegramClient
        _client = TelegramClient(SESSION_FILE, TG_API_ID, TG_API_HASH)
        await _client.start()
        me = await _client.get_me()
        logger.info(f"Telethon подключён как: {me.first_name} (@{me.username})")
        return _client
    except ImportError:
        raise RuntimeError(
            "Библиотека telethon не установлена.\\n"
            "Выполните: pip install telethon"
        )


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
        chat_id          — id чата/группы
        message_id       — id сообщения с файлом
        filename         — имя для сохранения
        progress_callback — async func(current, total) для прогресса

    Возвращает dict:
        success    — bool
        local_path — str
        size_bytes — int
        error      — str
    """
    result = {"success": False, "local_path": "", "size_bytes": 0, "error": ""}

    CACHE_DIR.mkdir(exist_ok=True)
    local_path = CACHE_DIR / filename

    try:
        client = await get_client()

        # Получаем сообщение
        message = await client.get_messages(chat_id, ids=message_id)
        if not message or not message.file:
            result["error"] = "Сообщение не найдено или не содержит файл"
            return result

        file_size = message.file.size or 0
        logger.info(
            f"Скачиваю через MTProto: {filename} "
            f"({file_size // 1024 // 1024} MB)"
        )

        # Внутренний callback прогресса
        async def _progress(current, total):
            if progress_callback and total:
                await progress_callback(current, total)

        # Скачиваем
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
                f"Файл скачан: {local_path} "
                f"({result['size_bytes'] // 1024 // 1024} MB)"
            )
        else:
            result["error"] = "Файл не появился после скачивания"

    except RuntimeError as e:
        result["error"] = str(e)
        logger.error(f"Ошибка конфигурации: {e}")
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Ошибка скачивания {filename}: {e}")

    return result


async def is_available() -> bool:
    """Проверяет что Telethon настроен и доступен."""
    if not TG_API_ID or not TG_API_HASH:
        return False
    try:
        import telethon  # noqa
        return True
    except ImportError:
        return False
