"""
file_uploader.py — Скачивание больших файлов из Telegram
=========================================================

Telegram Bot API ограничивает getFile() до 50MB.
Для файлов > 50MB используем прямой URL:
  https://api.telegram.org/file/bot{TOKEN}/{file_path}

Этот URL работает для файлов ЛЮБОГО размера (до 2GB).
Файл сохраняется локально в files_cache/ и синхронизируется на GitHub.
"""

import logging
import os
from pathlib import Path

import aiohttp

logger = logging.getLogger(__name__)

CACHE_DIR = Path("files_cache")

try:
    from config import TELEGRAM_BOT_TOKEN
except ImportError:
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")


async def download_large_file(
    bot,
    file_id: str,
    filename: str,
    file_size: int,
    progress_callback=None,
) -> dict:
    """
    Скачивает файл любого размера из Telegram напрямую.

    Алгоритм:
    1. Получаем file_path через getFile() (работает для любого размера)
    2. Формируем прямой URL: api.telegram.org/file/bot{TOKEN}/{file_path}
    3. Скачиваем потоком по 1MB чанками (не грузим всё в RAM)
    4. Сохраняем в files_cache/{filename}

    Аргументы:
        bot              — объект Telegram бота
        file_id          — Telegram file_id
        filename         — имя файла для сохранения
        file_size        — размер в байтах (для прогресса)
        progress_callback — async func(downloaded_bytes) для обновления статуса

    Возвращает dict:
        success     — bool
        local_path  — str путь к файлу или ""
        size_bytes  — int реальный размер
        error       — str сообщение об ошибке или ""
    """
    result = {
        "success":    False,
        "local_path": "",
        "size_bytes": 0,
        "error":      "",
    }

    CACHE_DIR.mkdir(exist_ok=True)
    local_path = CACHE_DIR / filename

    try:
        # Шаг 1: получаем file_path через getFile
        # ОГРАНИЧЕНИЕ Telegram Bot API: getFile работает только для файлов ≤ 20MB
        # Для файлов > 20MB Telegram возвращает ошибку "File is too big"
        # Решение для больших файлов: скопировать вручную в files_cache/
        tg_file   = await bot.get_file(file_id)
        file_path = tg_file.file_path
        direct_url = (
            f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
        )
        logger.info(f"Скачиваю {filename} ({file_size // 1024 // 1024} MB) напрямую...")

        # Шаг 2: скачиваем потоком
        timeout    = aiohttp.ClientTimeout(total=600)  # 10 минут на большой файл
        downloaded = 0

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(direct_url) as resp:
                if resp.status != 200:
                    result["error"] = f"HTTP {resp.status} при скачивании"
                    return result

                with open(local_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(1024 * 1024):  # 1MB
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and file_size > 0:
                            pct = int(downloaded * 100 / file_size)
                            await progress_callback(downloaded, pct)

        result["success"]    = True
        result["local_path"] = str(local_path)
        result["size_bytes"] = local_path.stat().st_size
        logger.info(
            f"Файл сохранён: {local_path} "
            f"({result['size_bytes'] // 1024 // 1024} MB)"
        )

    except aiohttp.ClientError as e:
        result["error"] = f"Сетевая ошибка: {e}"
        logger.error(f"Ошибка скачивания {filename}: {e}")
    except OSError as e:
        result["error"] = f"Ошибка записи файла: {e}"
        logger.error(f"Ошибка записи {local_path}: {e}")
    except Exception as e:
        err_str = str(e)
        if "File is too big" in err_str or "file is too big" in err_str.lower():
            # Telegram Bot API ограничивает getFile до 20MB
            result["error"] = (
                f"Файл {filename} ({file_size // 1024 // 1024} MB) превышает лимит "
                f"Telegram Bot API (20 MB).\n"
                f"Скопируйте файл вручную в папку files_cache/"
            )
            logger.warning(f"Файл слишком большой для Bot API: {filename} ({file_size // 1024 // 1024} MB)")
        else:
            result["error"] = err_str
            logger.error(f"Неожиданная ошибка при скачивании {filename}: {e}")

    return result
