# FILE: check_gemini_models.py | VERSION: 1.0.0 | DATE: 2026-10-06
"""
check_gemini_models.py — Поиск рабочей модели Gemini.

Проверяет все актуальные модели Gemini с вашим API ключом
и показывает какие работают. Запускать один раз для диагностики.

Запуск:
    cd C:\\stag_bot
    python check_gemini_models.py
"""

import sys
import os
import asyncio

# Добавляем папку бота в путь для импорта config.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from config import GEMINI_API_KEY
except ImportError as e:
    print(f"ОШИБКА: не удалось импортировать config.py: {e}")
    input("\nНажмите Enter для выхода...")
    sys.exit(1)

try:
    import aiohttp
except ImportError:
    print("ОШИБКА: aiohttp не установлен. Выполните: pip install aiohttp")
    input("\nНажмите Enter для выхода...")
    sys.exit(1)

# Список всех актуальных моделей Gemini для проверки
# Упорядочены от новейших к более старым и стабильным
GEMINI_MODELS = [
    "gemini-3.8-flash",           # Актуальная основная Flash модель
    "gemini-3.5-flash-lite",      # Лёгкая экономичная версия
    "gemini-3.1-flash-lite",      # Ещё более лёгкая версия
    "gemini-2.5-flash",           # Предыдущее поколение
    "gemini-2.0-flash",           # Более старое поколение
    "gemini-1.5-flash",           # Базовая версия
]

TEST_PROMPT = "Reply with one word: OK"


async def check_model(session: aiohttp.ClientSession, model: str) -> tuple:
    """
    Проверяет одну модель Gemini.

    Аргументы:
        session — aiohttp сессия
        model   — название модели (например gemini-2.5-flash)

    Возвращает:
        (model, ok, detail) — название, статус, детали
    """
    try:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta"
            f"/models/{model}:generateContent?key={GEMINI_API_KEY}"
        )
        async with session.post(
            url,
            json={"contents": [{"parts": [{"text": TEST_PROMPT}]}]},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            data = await r.json()
            if r.status == 200:
                # Извлекаем текст ответа из структуры Gemini
                answer = (
                    data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                    .strip()
                )
                return model, True, f"→ '{answer}'"
            else:
                # Извлекаем сообщение об ошибке
                err_msg = data.get("error", {}).get("message", "")[:120]
                return model, False, f"HTTP {r.status}: {err_msg}"
    except asyncio.TimeoutError:
        return model, False, "таймаут (>15 сек)"
    except Exception as e:
        return model, False, f"{type(e).__name__}: {str(e)[:80]}"


async def main():
    """Проверяет все модели Gemini и выводит результаты."""
    print("=" * 65)
    print("  Поиск рабочей модели Gemini — AI_Diag_UZ Bot")
    print("=" * 65)
    print()

    if not GEMINI_API_KEY:
        print("  ❌ GEMINI_API_KEY не задан в config.py")
        input("\n  Нажмите Enter для выхода...")
        return

    print(f"  Проверяем {len(GEMINI_MODELS)} моделей...")
    print()

    working = []

    async with aiohttp.ClientSession() as session:
        for model in GEMINI_MODELS:
            result = await check_model(session, model)
            _, ok, detail = result
            icon = "✅" if ok else "❌"
            print(f"  {icon} {model:<40} {detail}")
            if ok:
                working.append(model)

    print()
    print("=" * 65)

    if working:
        print(f"\n  ✅ Рабочие модели ({len(working)}):")
        for m in working:
            print(f"     {m}")
        print(f"\n  Рекомендация: использовать {working[0]}")
        print(f"  Скопируйте это название и сообщите Claude.")
    else:
        print("\n  ❌ Ни одна модель не работает.")
        print("  Возможные причины:")
        print("  - Временная недоступность Gemini API")
        print("  - Проблема с API ключом (проверьте aistudio.google.com)")
        print("  - Региональные ограничения")

    print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  Прервано пользователем.")
    except Exception as e:
        print(f"\n  КРИТИЧЕСКАЯ ОШИБКА: {type(e).__name__}: {e}")

    input("  Нажмите Enter для выхода...")
