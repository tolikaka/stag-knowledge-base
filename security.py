"""
security.py — Защита бота и базы данных
=========================================

Уровни защиты:

1. RATE LIMITING (ограничение частоты запросов)
   - Не более MAX_REQUESTS_PER_MINUTE запросов в минуту от одного user_id
   - При превышении — временная блокировка RATE_BLOCK_SECONDS секунд
   - Защищает от спама и DDoS через бота

2. BLACKLIST (чёрный список пользователей)
   - Администратор может заблокировать пользователя командой /block <user_id>
   - Список хранится в security_blacklist.json рядом с ботом
   - Заблокированные пользователи получают отказ без объяснений

3. ALLOWED GROUPS (белый список групп)
   - Бот отвечает только в группах из конфига TELEGRAM_CHANNEL_ID
   - В других группах игнорирует все сообщения

4. FILE SYSTEM PROTECTION (рекомендации для сервера)
   - Папка с ботом должна принадлежать отдельному пользователю ОС (не root)
   - Права на папку: 750 (только владелец читает/пишет/выполняет)
   - Права на config.py: 600 (только владелец читает/пишет)
   - База знаний: 640
   - Инструкции по настройке: см. ИНСТРУКЦИЯ_СЕРВЕР.md

ИСПОЛЬЗОВАНИЕ В bot.py:
    from security import rate_check, is_blacklisted, block_user, unblock_user
"""

import json
import logging
import time
from collections import defaultdict, deque
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Конфигурация ──────────────────────────────────────────────────────────────
MAX_REQUESTS_PER_MINUTE = 20  # Максимум запросов в минуту от одного пользователя
RATE_BLOCK_SECONDS      = 60  # Блокировка при превышении лимита (секунд)
BLACKLIST_PATH = Path(__file__).parent / "security_blacklist.json"

# ── Хранилища (в памяти, сбрасываются при перезапуске) ───────────────────────
# {user_id: deque([timestamp1, timestamp2, ...])} — история запросов
_request_history: defaultdict[int, deque] = defaultdict(lambda: deque())
# {user_id: block_until_timestamp}
_rate_blocked: dict[int, float] = {}


# ── Rate Limiting ─────────────────────────────────────────────────────────────

def rate_check(user_id: int) -> tuple[bool, str]:
    """
    Проверяет не превышен ли лимит запросов.

    Алгоритм скользящего окна (sliding window):
    Считаем запросы за последние 60 секунд.
    Если > MAX_REQUESTS_PER_MINUTE — блокируем на RATE_BLOCK_SECONDS.

    Аргументы:
        user_id: Telegram user_id

    Возвращает:
        (True, "")            — запрос разрешён
        (False, причина)      — запрос заблокирован
    """
    now = time.monotonic()

    # Проверяем активную блокировку
    block_until = _rate_blocked.get(user_id, 0)
    if now < block_until:
        remaining = int(block_until - now)
        return False, f"rate_limited:{remaining}"

    # Очищаем историю старше 60 секунд
    history = _request_history[user_id]
    while history and now - history[0] > 60:
        history.popleft()

    # Проверяем лимит
    if len(history) >= MAX_REQUESTS_PER_MINUTE:
        # Превышен — блокируем
        _rate_blocked[user_id] = now + RATE_BLOCK_SECONDS
        logger.warning(
            f"Rate limit превышен: user_id={user_id}, "
            f"запросов за минуту={len(history)}"
        )
        return False, f"rate_limited:{RATE_BLOCK_SECONDS}"

    # Записываем этот запрос
    history.append(now)
    return True, ""


# ── Blacklist ─────────────────────────────────────────────────────────────────

def _load_blacklist() -> set[int]:
    """Загружает чёрный список из файла."""
    if BLACKLIST_PATH.exists():
        try:
            with open(BLACKLIST_PATH, encoding="utf-8") as f:
                data = json.load(f)
            return set(data.get("blocked", []))
        except Exception as e:
            logger.error(f"Ошибка чтения blacklist: {e}")
    return set()


def _save_blacklist(blacklist: set[int]) -> None:
    """Сохраняет чёрный список в файл."""
    try:
        with open(BLACKLIST_PATH, "w", encoding="utf-8") as f:
            json.dump({"blocked": list(blacklist)}, f, indent=2)
    except Exception as e:
        logger.error(f"Ошибка записи blacklist: {e}")


# Загружаем при старте
_blacklist: set[int] = _load_blacklist()


def is_blacklisted(user_id: int) -> bool:
    """Возвращает True если пользователь в чёрном списке."""
    return user_id in _blacklist


def block_user(user_id: int) -> None:
    """Добавляет пользователя в чёрный список."""
    _blacklist.add(user_id)
    _save_blacklist(_blacklist)
    logger.info(f"Пользователь {user_id} заблокирован")


def unblock_user(user_id: int) -> bool:
    """Удаляет пользователя из чёрного списка. Возвращает True если был заблокирован."""
    if user_id in _blacklist:
        _blacklist.discard(user_id)
        _save_blacklist(_blacklist)
        logger.info(f"Пользователь {user_id} разблокирован")
        return True
    return False


def get_blacklist() -> list[int]:
    """Возвращает список заблокированных пользователей."""
    return list(_blacklist)
