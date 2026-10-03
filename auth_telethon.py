"""
auth_telethon.py - Авторизация Telethon
Запускается автоматически из start.bat если нет bot_session.session
"""
import asyncio
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

try:
    from config import TG_API_ID, TG_API_HASH
except ImportError:
    print("ОШИБКА: config.py не найден")
    sys.exit(1)

SESSION = os.path.join(BASE_DIR, "bot_session")


async def main():
    from telethon import TelegramClient
    from telethon.errors import FloodWaitError, SessionPasswordNeededError

    print()
    print("=" * 60)
    print("  АВТОРИЗАЦИЯ TELEGRAM")
    print("  Код придёт в приложение Telegram")
    print("  (сообщение от контакта 'Telegram')")
    print("=" * 60)
    print()

    client = TelegramClient(SESSION, TG_API_ID, TG_API_HASH)

    try:
        await client.connect()

        if await client.is_user_authorized():
            me = await client.get_me()
            print(f"Уже авторизован: {me.first_name} (@{me.username or ''})")
            await client.disconnect()
            sys.exit(0)

        phone = input("Номер телефона (+998XXXXXXXXX): ").strip()

        try:
            await client.send_code_request(phone)
        except FloodWaitError as e:
            print(f"\nTelegram: подождите {e.seconds} секунд и повторите.")
            await client.disconnect()
            sys.exit(2)

        print("\nОткройте Telegram — найдите сообщение от 'Telegram'")
        print("с кодом вида: Login code: 12345")
        code = input("Введите код: ").strip()

        try:
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            print("\nВведите пароль двухфакторной аутентификации:")
            password = input("Пароль 2FA: ").strip()
            await client.sign_in(password=password)

        if await client.is_user_authorized():
            me = await client.get_me()
            print()
            print("=" * 60)
            print(f"  Авторизация успешна!")
            print(f"  Аккаунт: {me.first_name} (@{me.username or ''})")
            print(f"  Файл сессии: bot_session.session")
            print("=" * 60)
            print()

        await client.disconnect()
        sys.exit(0)

    except FloodWaitError as e:
        print(f"\nTelegram заблокировал на {e.seconds} сек.")
        print(f"Подождите {e.seconds // 60 + 1} мин. и запустите start.bat снова.")
        await client.disconnect()
        sys.exit(2)
    except KeyboardInterrupt:
        print("\nАвторизация отменена.")
        await client.disconnect()
        sys.exit(1)
    except Exception as e:
        print(f"\nОшибка: {e}")
        await client.disconnect()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
