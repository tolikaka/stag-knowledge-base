"""
file_manager.py — Менеджер файлов для CarDiag UZ бота
=======================================================

ЧТО ДЕЛАЕТ ЭТОТ МОДУЛЬ:
1. Хранит локальные копии файлов (ПО, прошивки, документация)
   в папке files_cache/ рядом с ботом.
2. Ведёт каталог файлов: file_catalog.json
   (название, URL источника, ключевые слова, file_id Telegram).
3. При вопросе пользователя про ПО или документацию:
   а) Ищет файл в локальном каталоге по ключевым словам
   б) Если нашёл — отправляет из кэша (быстро, без интернета)
   в) Если не нашёл — пробует скачать с источника, сохраняет в кэш
4. Сохраняет file_id Telegram после первой отправки — повторные
   отправки делаются через file_id без повторной загрузки.

СТРУКТУРА КАТАЛОГА (file_catalog.json):
{
  "files": [
    {
      "id": "f001",
      "name": "STAG-4 Q-BOX Software v2.3.1",
      "filename": "stag4_qbox_v231.exe",
      "description": "Программа настройки STAG-4 Q-BOX",
      "keywords": ["stag-4", "q-box", "программа", "software", "dastur", "sozlash"],
      "source_url": "https://ac.com.pl/files/stag4_qbox_v231.exe",
      "local_path": "files_cache/stag4_qbox_v231.exe",
      "telegram_file_id": null,
      "size_bytes": 0,
      "downloaded": false,
      "category": "software"
    }
  ]
}

БЕЗОПАСНОСТЬ:
- Скачивает только файлы с разрешённых доменов (ALLOWED_DOMAINS)
- Максимальный размер файла: 50 MB (ограничение Telegram Bot API)
- Не скачивает если требуется авторизация (редирект на login)
"""

import asyncio
import hashlib
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiohttp
import aiofiles

logger = logging.getLogger(__name__)

# Корневая папка проекта — определяем относительно этого файла
BASE_DIR   = Path(__file__).parent
CACHE_DIR  = BASE_DIR / "files_cache"
CATALOG_PATH = BASE_DIR / "files_cache" / "file_catalog.json"

# Максимальный размер скачиваемого файла (50 MB — лимит Telegram)
MAX_FILE_SIZE = 50 * 1024 * 1024

# Разрешённые домены для автоскачивания.
# Файлы с других доменов не скачиваются автоматически в целях безопасности.
ALLOWED_DOMAINS = [
    "ac.com.pl",
    "forum.ac.com.pl",
    "lpgforum.ru",
    "gbo.ua",
    "gazda.ua",
    "drive.google.com",
    "yadi.sk",          # Яндекс Диск
    "disk.yandex.ru",
]

# Начальный каталог файлов с известными ресурсами AC STAG
DEFAULT_CATALOG = {
    "version": "1.0",
    "last_updated": "",
    "files": [
        {
            "id": "f001",
            "name": "STAG-4 Q-BOX Программа настройки",
            "filename": "stag4_qbox_setup.exe",
            "description": "Официальная программа настройки и диагностики STAG-4 Q-BOX",
            "keywords": [
                "stag-4", "stag4", "q-box", "qbox",
                "программа", "software", "dastur", "sozlash",
                "настройка", "калибровка", "calibration",
                "stag 4 программа скачать", "stag software"
            ],
            "source_url": "https://ac.com.pl/downloads/",
            "local_path": "",
            "telegram_file_id": None,
            "size_bytes": 0,
            "downloaded": False,
            "category": "software",
            "note": "Скачать вручную с официального сайта ac.com.pl — раздел Downloads"
        },
        {
            "id": "f002",
            "name": "STAG-400 DPI Программа настройки",
            "filename": "stag400_dpi_setup.exe",
            "description": "Программа настройки STAG-400 DPI для двигателей с прямым впрыском",
            "keywords": [
                "stag-400", "stag400", "dpi", "400 dpi",
                "прямой впрыск", "gdi", "tsi", "tfsi",
                "программа 400", "stag 400 software", "400 dpi dastur"
            ],
            "source_url": "https://ac.com.pl/downloads/",
            "local_path": "",
            "telegram_file_id": None,
            "size_bytes": 0,
            "downloaded": False,
            "category": "software",
            "note": "Скачать вручную с официального сайта ac.com.pl — раздел Downloads"
        },
        {
            "id": "f003",
            "name": "STAG-300 ISA2/ISA3 Программа настройки",
            "filename": "stag300_isa_setup.exe",
            "description": "Программа настройки для STAG-300 ISA2 и ISA3",
            "keywords": [
                "stag-300", "stag300", "isa2", "isa3", "300 isa",
                "программа 300", "stag 300 software"
            ],
            "source_url": "https://ac.com.pl/downloads/",
            "local_path": "",
            "telegram_file_id": None,
            "size_bytes": 0,
            "downloaded": False,
            "category": "software",
            "note": "Скачать вручную с официального сайта ac.com.pl — раздел Downloads"
        },
    ]
}


def _ensure_cache_dir() -> None:
    """Создаёт папку files_cache если не существует."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _load_catalog() -> dict:
    """
    Загружает каталог файлов из JSON.
    Если файл не существует — создаёт из DEFAULT_CATALOG.
    """
    _ensure_cache_dir()
    if CATALOG_PATH.exists():
        try:
            with open(CATALOG_PATH, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Ошибка чтения каталога: {e}")
    # Файл не найден или повреждён — создаём новый
    _save_catalog(DEFAULT_CATALOG)
    return DEFAULT_CATALOG.copy()


def _save_catalog(catalog: dict) -> None:
    """Сохраняет каталог файлов в JSON."""
    _ensure_cache_dir()
    catalog["last_updated"] = datetime.now().isoformat()
    try:
        with open(CATALOG_PATH, "w", encoding="utf-8") as f:
            json.dump(catalog, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.error(f"Ошибка записи каталога: {e}")


def search_file(query: str) -> Optional[dict]:
    """
    Ищет файл в каталоге по ключевым словам.

    Алгоритм:
    1. Приводим запрос к нижнему регистру
    2. Для каждого файла считаем сколько ключевых слов совпадает
    3. Возвращаем файл с наибольшим числом совпадений (если > 0)

    Аргументы:
        query (str): запрос пользователя

    Возвращает:
        dict — запись каталога или None если не найдено
    """
    catalog = _load_catalog()
    query_lower = query.lower()

    best_match: Optional[dict] = None
    best_score  = 0

    for file_entry in catalog.get("files", []):
        score = 0
        for keyword in file_entry.get("keywords", []):
            if keyword.lower() in query_lower:
                score += 1
        if score > best_score:
            best_score  = score
            best_match  = file_entry

    if best_match and best_score > 0:
        logger.info(
            f"Файл найден в каталоге: '{best_match['name']}' "
            f"(совпадений: {best_score})"
        )
        return best_match
    return None


def _is_allowed_domain(url: str) -> bool:
    """
    Проверяет что URL принадлежит разрешённому домену.

    Аргументы:
        url (str): полный URL файла

    Возвращает:
        True  — домен в белом списке ALLOWED_DOMAINS
        False — домен не разрешён, скачивание запрещено
    """
    # Извлекаем домен из URL
    match = re.search(r"https?://([^/]+)", url)
    if not match:
        return False
    domain = match.group(1).lower()
    # Убираем www. для сравнения
    domain = domain.removeprefix("www.")
    return any(domain == allowed or domain.endswith("." + allowed)
               for allowed in ALLOWED_DOMAINS)


async def download_and_cache(file_entry: dict) -> Optional[str]:
    """
    Скачивает файл с source_url и сохраняет в files_cache/.

    Проверки перед скачиванием:
    - URL принадлежит разрешённому домену
    - Размер файла не превышает MAX_FILE_SIZE (50 MB)
    - Сервер не перенаправляет на страницу авторизации

    Аргументы:
        file_entry (dict): запись из каталога

    Возвращает:
        str  — путь к скачанному файлу
        None — если скачивание невозможно или не удалось
    """
    url = file_entry.get("source_url", "")
    if not url or not url.startswith("http"):
        logger.warning(f"Некорректный URL: '{url}'")
        return None

    if not _is_allowed_domain(url):
        logger.warning(f"Домен не разрешён для скачивания: {url}")
        return None

    filename  = file_entry.get("filename", "")
    if not filename:
        # Берём имя файла из URL
        filename = url.rstrip("/").split("/")[-1] or "file"

    local_path = CACHE_DIR / filename
    _ensure_cache_dir()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 Chrome/120.0",
    }

    try:
        timeout = aiohttp.ClientTimeout(total=120, connect=10)
        async with aiohttp.ClientSession(
            headers=headers, timeout=timeout
        ) as session:
            async with session.get(url, allow_redirects=True) as resp:
                # Проверяем что не редирект на логин/авторизацию
                final_url = str(resp.url)
                auth_keywords = ["login", "signin", "auth", "account", "register"]
                if any(kw in final_url.lower() for kw in auth_keywords):
                    logger.warning(
                        f"Сервер требует авторизацию: {final_url}"
                    )
                    return None

                if resp.status != 200:
                    logger.warning(
                        f"HTTP {resp.status} при скачивании {url}"
                    )
                    return None

                # Проверяем размер
                content_length = resp.headers.get("Content-Length")
                if content_length and int(content_length) > MAX_FILE_SIZE:
                    logger.warning(
                        f"Файл слишком большой: {int(content_length) // 1024 // 1024} MB "
                        f"(лимит {MAX_FILE_SIZE // 1024 // 1024} MB)"
                    )
                    return None

                # Скачиваем
                downloaded = 0
                async with aiofiles.open(local_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(65536):
                        downloaded += len(chunk)
                        if downloaded > MAX_FILE_SIZE:
                            logger.warning("Файл превысил лимит при скачивании")
                            await f.close()
                            local_path.unlink(missing_ok=True)
                            return None
                        await f.write(chunk)

        logger.info(
            f"Файл скачан: {filename} "
            f"({downloaded // 1024} KB)"
        )

        # Обновляем каталог
        catalog = _load_catalog()
        for entry in catalog["files"]:
            if entry["id"] == file_entry["id"]:
                entry["local_path"]  = "files_cache/" + local_path.name
                entry["size_bytes"]  = downloaded
                entry["downloaded"]  = True
                break
        _save_catalog(catalog)

        return str(local_path)

    except asyncio.TimeoutError:
        logger.error(f"Таймаут при скачивании: {url}")
    except aiohttp.ClientError as e:
        logger.error(f"Ошибка сети при скачивании {url}: {e}")
    except OSError as e:
        logger.error(f"Ошибка записи файла {local_path}: {e}")
    return None


def save_telegram_file_id(file_id_catalog: str, telegram_file_id: str) -> None:
    """
    Сохраняет file_id Telegram после первой успешной отправки файла.

    После того как файл отправлен в Telegram первый раз, сервер
    присваивает ему file_id. Следующие отправки можно делать через
    file_id — быстро и без повторной загрузки.

    Аргументы:
        file_id_catalog (str): id записи в нашем каталоге ("f001")
        telegram_file_id (str): file_id полученный от Telegram
    """
    catalog = _load_catalog()
    for entry in catalog["files"]:
        if entry["id"] == file_id_catalog:
            entry["telegram_file_id"] = telegram_file_id
            break
    _save_catalog(catalog)
    logger.info(f"Telegram file_id сохранён для {file_id_catalog}")


def add_file_to_catalog(
    name: str,
    filename: str,
    description: str,
    keywords: list[str],
    source_url: str,
    category: str = "software",
    note: str = "",
) -> str:
    """
    Добавляет новый файл в каталог (через веб-админку или команду).

    Аргументы:
        name:        отображаемое название
        filename:    имя файла на диске
        description: описание
        keywords:    список ключевых слов для поиска
        source_url:  URL источника
        category:    категория ("software", "manual", "firmware")
        note:        примечание (например об авторизации)

    Возвращает:
        str: присвоенный id записи (например "f007")
    """
    catalog = _load_catalog()
    existing_ids = [e["id"] for e in catalog.get("files", [])]
    # Генерируем новый id: f001, f002, ...
    max_num = max(
        (int(eid[1:]) for eid in existing_ids if eid.startswith("f") and eid[1:].isdigit()),
        default=0
    )
    new_id = f"f{max_num + 1:03d}"

    new_entry = {
        "id":               new_id,
        "name":             name,
        "filename":         filename,
        "description":      description,
        "keywords":         keywords,
        "source_url":       source_url,
        "local_path":       "",
        "telegram_file_id": None,
        "size_bytes":       0,
        "downloaded":       False,
        "category":         category,
        "note":             note,
    }
    catalog.setdefault("files", []).append(new_entry)
    _save_catalog(catalog)
    logger.info(f"В каталог добавлен файл: {new_id} — {name}")
    return new_id


def get_all_files() -> list[dict]:
    """Возвращает все файлы из каталога."""
    return _load_catalog().get("files", [])


def get_file_by_id(file_id: str) -> Optional[dict]:
    """Возвращает запись каталога по id."""
    for entry in _load_catalog().get("files", []):
        if entry["id"] == file_id:
            return entry
    return None


# Синглтон каталога для быстрого доступа
def reload_catalog() -> dict:
    """Перезагружает каталог с диска."""
    return _load_catalog()
