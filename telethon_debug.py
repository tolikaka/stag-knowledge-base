"""
telethon_debug.py - Автономная диагностика Telethon авторизации
===============================================================
Запуск: python telethon_debug.py
Полное логирование всех сеансов связи с Telegram.
НЕ зависит от остальных файлов бота.
"""

import asyncio
import logging
import sys
import os
from datetime import datetime

# ── Полное логирование ────────────────────────────────────────────────────────
log_file = f"telethon_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ]
)

# Включаем DEBUG для всех компонентов Telethon
for logger_name in [
    "telethon",
    "telethon.network",
    "telethon.network.mtprotosender",
    "telethon.network.connection",
    "telethon.client",
    "telethon.client.auth",
    "telethon.crypto",
]:
    logging.getLogger(logger_name).setLevel(logging.DEBUG)

logger = logging.getLogger("DEBUG_AUTH")

# ── Параметры ─────────────────────────────────────────────────────────────────
API_ID   = 34148271
API_HASH = "284ceaaf6f4916c180c94b27f6cfb3f3"
SESSION  = "debug_session"  # Отдельная сессия - не затрагивает bot_session


async def check_environment():
    """Проверяет окружение перед авторизацией."""
    logger.info("=" * 60)
    logger.info("ДИАГНОСТИКА ОКРУЖЕНИЯ")
    logger.info("=" * 60)
    logger.info("Python: %s", sys.version)
    logger.info("OS: %s", sys.platform)
    logger.info("API_ID: %d", API_ID)
    logger.info("Session file: %s.session", SESSION)

    try:
        import telethon
        logger.info("Telethon версия: %s", telethon.__version__)
    except ImportError:
        logger.error("Telethon НЕ установлен!")
        return False

    # Проверяем существующую сессию
    if os.path.exists(f"{SESSION}.session"):
        logger.info("Найден файл сессии: %s.session", SESSION)
    else:
        logger.info("Файл сессии отсутствует - будет создан новый")

    return True


async def test_connection():
    """Тест соединения с серверами Telegram."""
    logger.info("=" * 60)
    logger.info("ТЕСТ СОЕДИНЕНИЯ С TELEGRAM")
    logger.info("=" * 60)

    from telethon import TelegramClient
    from telethon.network import ConnectionTcpFull

    client = TelegramClient(
        SESSION,
        API_ID,
        API_HASH,
        connection=ConnectionTcpFull,
        receive_updates=False,
    )

    try:
        logger.info("Подключаемся к серверу Telegram...")
        await client.connect()
        logger.info("Соединение установлено: %s", client.is_connected())

        # Проверяем авторизацию
        is_auth = await client.is_user_authorized()
        logger.info("Авторизован: %s", is_auth)

        if is_auth:
            me = await client.get_me()
            logger.info("Текущий аккаунт: %s (@%s)", me.first_name, me.username or "")
            await client.disconnect()
            return "already_authorized"

        await client.disconnect()
        return "not_authorized"

    except Exception as e:
        logger.error("Ошибка соединения: %s: %s", type(e).__name__, e)
        try:
            await client.disconnect()
        except Exception:
            pass
        return "connection_error"


async def request_code(phone: str):
    """Запрашивает код подтверждения."""
    logger.info("=" * 60)
    logger.info("ЗАПРОС КОДА ПОДТВЕРЖДЕНИЯ")
    logger.info("=" * 60)
    logger.info("Номер телефона: %s", phone)

    from telethon import TelegramClient
    from telethon.errors import (
        FloodWaitError,
        PhoneNumberInvalidError,
        PhoneNumberBannedError,
        ApiIdInvalidError,
    )

    client = TelegramClient(SESSION, API_ID, API_HASH, receive_updates=False)

    try:
        await client.connect()
        logger.info("Отправляем запрос кода...")

        sent = await client.send_code_request(phone)

        logger.info("КОД ОТПРАВЛЕН УСПЕШНО")
        logger.info("Тип доставки: %s", type(sent.type).__name__)
        logger.info("Следующий тип: %s",
                    type(sent.next_type).__name__ if sent.next_type else "нет")
        logger.info("phone_code_hash: %s...", sent.phone_code_hash[:8])
        logger.info("Timeout: %s сек", sent.timeout)

        # Определяем куда придёт код
        code_type = type(sent.type).__name__
        if "App" in code_type:
            print()
            print("=" * 60)
            print("  КОД ОТПРАВЛЕН В ПРИЛОЖЕНИЕ TELEGRAM")
            print("  Откройте Telegram на телефоне или компьютере")
            print("  Найдите сообщение от контакта 'Telegram'")
            print("  Текст: Login code: XXXXX")
            print("=" * 60)
        elif "Sms" in code_type:
            print()
            print("=" * 60)
            print("  КОД ОТПРАВЛЕН ПО SMS")
            print(f"  На номер: {phone}")
            print("=" * 60)
        else:
            print(f"\n  Код отправлен ({code_type})")

        await client.disconnect()
        return sent.phone_code_hash

    except FloodWaitError as e:
        logger.error("FLOOD WAIT: нужно ждать %d секунд (%d минут)",
                     e.seconds, e.seconds // 60)
        print()
        print("=" * 60)
        print(f"  TELEGRAM БЛОКИРОВКА (FloodWait)")
        print(f"  Нужно подождать: {e.seconds // 60} мин {e.seconds % 60} сек")
        print(f"  Причина: слишком много запросов кода")
        print("=" * 60)
        await client.disconnect()
        return None

    except PhoneNumberInvalidError:
        logger.error("ОШИБКА: Неверный формат номера телефона: %s", phone)
        print(f"\n  Неверный номер: {phone}")
        print("  Используйте формат: +998901234567")
        await client.disconnect()
        return None

    except PhoneNumberBannedError:
        logger.error("ОШИБКА: Номер телефона заблокирован Telegram")
        await client.disconnect()
        return None

    except ApiIdInvalidError:
        logger.error("ОШИБКА: Неверный API_ID или API_HASH")
        await client.disconnect()
        return None

    except Exception as e:
        logger.error("НЕОЖИДАННАЯ ОШИБКА: %s: %s", type(e).__name__, e)
        try:
            await client.disconnect()
        except Exception:
            pass
        return None


async def sign_in_with_code(phone: str, code: str, phone_code_hash: str):
    """Выполняет вход с кодом подтверждения."""
    logger.info("=" * 60)
    logger.info("ВХОД С КОДОМ ПОДТВЕРЖДЕНИЯ")
    logger.info("=" * 60)
    logger.info("Код: %s", code)
    logger.info("Hash: %s...", phone_code_hash[:8])

    from telethon import TelegramClient
    from telethon.errors import (
        PhoneCodeInvalidError,
        PhoneCodeExpiredError,
        SessionPasswordNeededError,
        FloodWaitError,
    )

    client = TelegramClient(SESSION, API_ID, API_HASH, receive_updates=False)

    try:
        await client.connect()
        logger.info("Отправляем sign_in запрос...")

        await client.sign_in(
            phone=phone,
            code=code,
            phone_code_hash=phone_code_hash,
        )

        if await client.is_user_authorized():
            me = await client.get_me()
            logger.info("АВТОРИЗАЦИЯ УСПЕШНА: %s (@%s)",
                        me.first_name, me.username or "")
            print()
            print("=" * 60)
            print(f"  АВТОРИЗАЦИЯ УСПЕШНА!")
            print(f"  Аккаунт: {me.first_name} (@{me.username or ''})")
            print(f"  Сессия: {SESSION}.session")
            print("=" * 60)
            await client.disconnect()
            return True

    except PhoneCodeInvalidError:
        logger.error("ОШИБКА: Неверный код подтверждения")
        print("\n  Ошибка: неверный код. Попробуйте ещё раз.")
        await client.disconnect()
        return False

    except PhoneCodeExpiredError:
        logger.error("ОШИБКА: Код истёк")
        print("\n  Ошибка: код истёк. Запросите новый.")
        await client.disconnect()
        return False

    except SessionPasswordNeededError:
        logger.info("Требуется пароль 2FA")
        print()
        print("  Включена двухфакторная аутентификация (2FA).")
        password = input("  Введите облачный пароль Telegram: ").strip()

        try:
            await client.sign_in(password=password)
            me = await client.get_me()
            logger.info("АВТОРИЗАЦИЯ С 2FA УСПЕШНА: %s", me.first_name)
            print(f"\n  Авторизация успешна: {me.first_name}")
            await client.disconnect()
            return True
        except Exception as e2:
            logger.error("ОШИБКА 2FA: %s", e2)
            print(f"\n  Ошибка 2FA: {e2}")
            await client.disconnect()
            return False

    except FloodWaitError as e:
        logger.error("FLOOD WAIT: %d секунд", e.seconds)
        print(f"\n  FloodWait: подождите {e.seconds // 60} мин.")
        await client.disconnect()
        return False

    except Exception as e:
        logger.error("НЕОЖИДАННАЯ ОШИБКА: %s: %s", type(e).__name__, e)
        try:
            await client.disconnect()
        except Exception:
            pass
        return False


async def main():
    print()
    print("=" * 60)
    print("  TELETHON ДИАГНОСТИКА И АВТОРИЗАЦИЯ")
    print(f"  Лог сохраняется в: {log_file}")
    print("=" * 60)
    print()

    # Шаг 1: Проверка окружения
    ok = await check_environment()
    if not ok:
        print("\nУстановите telethon: pip install telethon==1.36.0")
        return

    # Шаг 2: Тест соединения
    status = await test_connection()

    if status == "already_authorized":
        print("\n  Уже авторизован. Сессия рабочая.")
        print(f"  Скопируйте {SESSION}.session → bot_session.session")
        return

    if status == "connection_error":
        print("\n  Не удалось подключиться к Telegram.")
        print("  Проверьте интернет-соединение.")
        return

    # Шаг 3: Запрос кода
    print()
    phone = input("  Введите номер телефона (+998XXXXXXXXX): ").strip()

    phone_code_hash = await request_code(phone)

    if phone_code_hash is None:
        print(f"\n  Лог сохранён в: {log_file}")
        print("  Изучите лог для диагностики проблемы.")
        return

    # Шаг 4: Ввод кода
    print()
    code = input("  Введите код из Telegram: ").strip()

    success = await sign_in_with_code(phone, code, phone_code_hash)

    print()
    print(f"  Полный лог сохранён в: {log_file}")

    if success:
        print(f"  Скопируйте {SESSION}.session → bot_session.session")
        print("  Затем запустите start.bat")


if __name__ == "__main__":
    asyncio.run(main())
