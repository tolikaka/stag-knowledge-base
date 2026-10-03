# FILE: auth_telethon.py | VERSION: 1.1.0 | DATE: 2026-10-04
"""
auth_telethon.py — Авторизация Telethon
========================================
Запускается из start.bat при каждом старте бота.
Если сессия рабочая — завершается за 1-2 сек без вопросов.
Если сессии нет или она повреждена — проводит авторизацию.

Логика основана на telethon_debug.py — проверено и работает.
"""

import asyncio
import sys
import os
import logging

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# Минимальное логирование для читаемого вывода
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.WARNING,
)
logging.getLogger("telethon").setLevel(logging.WARNING)

SESSION = os.path.join(BASE_DIR, "bot_session")

try:
    from config import TG_API_ID, TG_API_HASH
    API_ID   = int(TG_API_ID)   if TG_API_ID   else 0
    API_HASH = str(TG_API_HASH) if TG_API_HASH else ""
except (ImportError, AttributeError, TypeError, ValueError):
    print("ОШИБКА: не удалось прочитать TG_API_ID / TG_API_HASH из config.py")
    sys.exit(0)  # Выходим без ошибки — бот запустится без Telethon

if not API_ID or not API_HASH:
    print("TG_API_ID не задан — Telethon пропускается")
    sys.exit(0)


async def main():
    try:
        from telethon import TelegramClient
        from telethon.errors import (
            FloodWaitError,
            PhoneCodeInvalidError,
            PhoneCodeExpiredError,
            SessionPasswordNeededError,
            PhoneNumberInvalidError,
            ApiIdInvalidError,
        )
    except ImportError:
        print("telethon не установлен — пропускаем")
        sys.exit(0)

    client = TelegramClient(SESSION, API_ID, API_HASH, receive_updates=False)

    try:
        await client.connect()

        # Сессия рабочая — выходим без вопросов
        if await client.is_user_authorized():
            me = await client.get_me()
            print(f"Telethon OK: {me.first_name} (@{me.username or ''})")
            await client.disconnect()
            sys.exit(0)

        # Сессия повреждена или отсутствует — авторизуемся
        await client.disconnect()

    except Exception:
        try:
            await client.disconnect()
        except Exception:
            pass

    # Авторизация
    print()
    print("=" * 60)
    print("  АВТОРИЗАЦИЯ TELEGRAM (выполняется один раз)")
    print("=" * 60)
    print()
    print("  Код придёт в приложение Telegram.")
    print("  Найдите сообщение от контакта 'Telegram'.")
    print("  Текст: Login code: XXXXX")
    print()
    print("  Если 2FA включена — после кода введите облачный пароль.")
    print("=" * 60)
    print()

    phone = input("  Номер телефона (+998XXXXXXXXX): ").strip()
    if not phone:
        print("  Авторизация отменена.")
        sys.exit(1)

    client2 = TelegramClient(SESSION, API_ID, API_HASH, receive_updates=False)

    try:
        await client2.connect()

        # Запрашиваем код и сохраняем phone_code_hash
        try:
            sent = await client2.send_code_request(phone)
            phone_code_hash = sent.phone_code_hash
            code_type = type(sent.type).__name__
            if "App" in code_type:
                print("  Код отправлен в приложение Telegram.")
            elif "Sms" in code_type:
                print("  Код отправлен по SMS.")
            else:
                print(f"  Код отправлен ({code_type}).")
        except FloodWaitError as e:
            mins = e.seconds // 60
            secs = e.seconds % 60
            print(f"\n  Telegram: подождите {mins} мин {secs} сек и запустите снова.")
            await client2.disconnect()
            sys.exit(1)
        except PhoneNumberInvalidError:
            print(f"\n  Неверный номер: {phone}")
            print("  Используйте формат: +998901234567")
            await client2.disconnect()
            sys.exit(1)
        except ApiIdInvalidError:
            print("\n  Ошибка: неверный TG_API_ID или TG_API_HASH в config.py")
            await client2.disconnect()
            sys.exit(1)

        print()
        code = input("  Введите код: ").strip()
        if not code:
            print("  Авторизация отменена.")
            await client2.disconnect()
            sys.exit(1)

        # Входим с кодом — ОБЯЗАТЕЛЬНО передаём phone_code_hash
        try:
            await client2.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=phone_code_hash,
            )
        except PhoneCodeInvalidError:
            print("\n  Ошибка: неверный код.")
            print("  Запустите start.bat снова для получения нового кода.")
            await client2.disconnect()
            sys.exit(1)
        except PhoneCodeExpiredError:
            print("\n  Ошибка: код истёк.")
            print("  Запустите start.bat снова для получения нового кода.")
            await client2.disconnect()
            sys.exit(1)
        except SessionPasswordNeededError:
            # 2FA
            print()
            print("  Двухфакторная аутентификация (2FA).")
            password = input("  Введите облачный пароль Telegram: ").strip()
            try:
                await client2.sign_in(password=password)
            except Exception as e:
                print(f"\n  Ошибка 2FA: {e}")
                await client2.disconnect()
                sys.exit(1)
        except FloodWaitError as e:
            mins = e.seconds // 60
            print(f"\n  Telegram: подождите {mins} мин и запустите снова.")
            await client2.disconnect()
            sys.exit(1)

        # Проверяем результат
        if await client2.is_user_authorized():
            me = await client2.get_me()
            print()
            print("=" * 60)
            print("  Авторизация успешна!")
            print(f"  Аккаунт: {me.first_name} (@{me.username or ''})")
            print("  Сессия сохранена: bot_session.session")
            print("  При следующем запуске авторизация не нужна.")
            print("=" * 60)
            print()
            await client2.disconnect()
            sys.exit(0)
        else:
            print("\n  Авторизация не завершена.")
            await client2.disconnect()
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n  Авторизация отменена.")
        try:
            await client2.disconnect()
        except Exception:
            pass
        sys.exit(1)
    except Exception as e:
        print(f"\n  Непредвиденная ошибка: {e}")
        try:
            await client2.disconnect()
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
