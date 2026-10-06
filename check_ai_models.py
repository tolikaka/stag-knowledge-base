# FILE: check_ai_models.py | VERSION: 1.1.0 | DATE: 2026-10-06
"""
check_ai_models.py — Проверка всех AI API ключей из config.py.

Запуск:
    cd C:\\stag_bot
    python check_ai_models.py

Результат: список AI систем с отметкой работает/не работает.
Окно НЕ закроется само — нажмите Enter в конце.
"""

import sys
import os

# Добавляем папку бота в путь чтобы импортировать config.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Импорт конфига ────────────────────────────────────────────
try:
    from config import (
        GROQ_API_KEY,
        DEEPSEEK_API_KEY,
        KIMI_API_KEY,
        GEMINI_API_KEY,
        ANTHROPIC_API_KEY,
    )
except ImportError as e:
    print(f"ОШИБКА: не удалось импортировать config.py: {e}")
    input("\nНажмите Enter для выхода...")
    sys.exit(1)

# ── Проверяем наличие aiohttp ─────────────────────────────────
try:
    import aiohttp
except ImportError:
    print("ОШИБКА: aiohttp не установлен.")
    print("Выполните: pip install aiohttp")
    input("\nНажмите Enter для выхода...")
    sys.exit(1)

import asyncio

# Тестовый запрос — минимальный, чтобы быстро получить ответ
TEST_PROMPT = "Reply with one word: OK"


# ── Функции проверки каждого AI ───────────────────────────────

async def check_groq(session: aiohttp.ClientSession) -> tuple:
    """Проверяет Groq API. Возвращает (имя, статус, детали)."""
    if not GROQ_API_KEY:
        return "Groq", None, "ключ не задан в config.py"
    try:
        async with session.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                     "Content-Type": "application/json"},
            json={"model": "qwen/qwen3.8-27b",
                  "messages": [{"role": "user", "content": TEST_PROMPT}],
                  "max_tokens": 10},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as r:
            data = await r.json()
            if r.status == 200:
                answer = data["choices"][0]["message"]["content"].strip()
                return "Groq", True, f"qwen/qwen3.8-27b → '{answer}'"
            else:
                msg = data.get("error", {}).get("message", "")[:100]
                return "Groq", False, f"HTTP {r.status}: {msg}"
    except asyncio.TimeoutError:
        return "Groq", False, "таймаут (>20 сек)"
    except Exception as e:
        return "Groq", False, f"{type(e).__name__}: {e}"


async def check_deepseek(session: aiohttp.ClientSession) -> tuple:
    """Проверяет DeepSeek API."""
    if not DEEPSEEK_API_KEY:
        return "DeepSeek", None, "ключ не задан в config.py"
    try:
        async with session.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                     "Content-Type": "application/json"},
            json={"model": "deepseek-chat",
                  "messages": [{"role": "user", "content": TEST_PROMPT}],
                  "max_tokens": 10},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as r:
            data = await r.json()
            if r.status == 200:
                answer = data["choices"][0]["message"]["content"].strip()
                return "DeepSeek", True, f"deepseek-chat → '{answer}'"
            else:
                msg = data.get("error", {}).get("message", "")[:100]
                return "DeepSeek", False, f"HTTP {r.status}: {msg}"
    except asyncio.TimeoutError:
        return "DeepSeek", False, "таймаут (>20 сек)"
    except Exception as e:
        return "DeepSeek", False, f"{type(e).__name__}: {e}"


async def check_kimi(session: aiohttp.ClientSession) -> tuple:
    """Проверяет Kimi/Moonshot API."""
    if not KIMI_API_KEY:
        return "Kimi/Moonshot", None, "ключ не задан в config.py"
    try:
        async with session.post(
            "https://api.moonshot.cn/v1/chat/completions",
            headers={"Authorization": f"Bearer {KIMI_API_KEY}",
                     "Content-Type": "application/json"},
            json={"model": "moonshot-v1-8k",
                  "messages": [{"role": "user", "content": TEST_PROMPT}],
                  "max_tokens": 10},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as r:
            data = await r.json()
            if r.status == 200:
                answer = data["choices"][0]["message"]["content"].strip()
                return "Kimi/Moonshot", True, f"moonshot-v1-8k → '{answer}'"
            else:
                msg = data.get("error", {}).get("message", "")[:100]
                return "Kimi/Moonshot", False, f"HTTP {r.status}: {msg}"
    except asyncio.TimeoutError:
        return "Kimi/Moonshot", False, "таймаут (>20 сек)"
    except Exception as e:
        return "Kimi/Moonshot", False, f"{type(e).__name__}: {e}"


async def check_gemini(session: aiohttp.ClientSession) -> tuple:
    """Проверяет Google Gemini API."""
    if not GEMINI_API_KEY:
        return "Gemini", None, "ключ не задан в config.py"
    try:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta"
            f"/models/gemini-3.8-flash:generateContent?key={GEMINI_API_KEY}"
        )
        async with session.post(
            url,
            json={"contents": [{"parts": [{"text": TEST_PROMPT}]}]},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as r:
            data = await r.json()
            if r.status == 200:
                answer = (data["candidates"][0]["content"]["parts"][0]["text"]
                          .strip())
                return "Gemini", True, f"gemini-3.8-flash → '{answer}'"
            else:
                msg = data.get("error", {}).get("message", "")[:100]
                return "Gemini", False, f"HTTP {r.status}: {msg}"
    except asyncio.TimeoutError:
        return "Gemini", False, "таймаут (>20 сек)"
    except Exception as e:
        return "Gemini", False, f"{type(e).__name__}: {e}"


async def check_claude(session: aiohttp.ClientSession) -> tuple:
    """Проверяет Anthropic Claude API."""
    if not ANTHROPIC_API_KEY:
        return "Claude Haiku", None, "ключ не задан в config.py"
    try:
        async with session.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={"model": "claude-haiku-4-5-20251001",
                  "max_tokens": 10,
                  "messages": [{"role": "user", "content": TEST_PROMPT}]},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as r:
            data = await r.json()
            if r.status == 200:
                answer = data["content"][0]["text"].strip()
                return "Claude Haiku", True, f"claude-haiku → '{answer}'"
            else:
                msg = data.get("error", {}).get("message", "")[:100]
                return "Claude Haiku", False, f"HTTP {r.status}: {msg}"
    except asyncio.TimeoutError:
        return "Claude Haiku", False, "таймаут (>20 сек)"
    except Exception as e:
        return "Claude Haiku", False, f"{type(e).__name__}: {e}"


# ── Основная функция ──────────────────────────────────────────

async def main():
    """Запускает проверку всех AI последовательно и выводит результат."""
    print("=" * 60)
    print("  Проверка AI API ключей — AI_Diag_UZ Bot")
    print("=" * 60)
    print()
    print("  Проверяем по очереди (до 20 сек на каждый)...")
    print()

    # Проверяем последовательно чтобы видеть прогресс
    async with aiohttp.ClientSession() as session:
        checkers = [
            check_groq(session),
            check_deepseek(session),
            check_kimi(session),
            check_gemini(session),
            check_claude(session),
        ]

        results = []
        for coro in checkers:
            try:
                result = await coro
                results.append(result)
                # Показываем результат сразу
                name, ok, detail = result
                icon = "✅" if ok else ("⚪" if ok is None else "❌")
                print(f"  {icon} {name:<15} {detail}")
            except Exception as e:
                print(f"  ❌ ОШИБКА: {e}")

    print()
    print("=" * 60)

    # Итог
    working = [r[0] for r in results if r[1] is True]
    broken  = [r[0] for r in results if r[1] is False]
    skipped = [r[0] for r in results if r[1] is None]

    if working:
        print(f"\n  ✅ Работают ({len(working)}): {', '.join(working)}")
    if broken:
        print(f"  ❌ Не работают ({len(broken)}): {', '.join(broken)}")
    if skipped:
        print(f"  ⚪ Ключ не задан ({len(skipped)}): {', '.join(skipped)}")

    print()


# ── Точка входа ───────────────────────────────────────────────

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  Прервано пользователем.")
    except Exception as e:
        print(f"\n  КРИТИЧЕСКАЯ ОШИБКА: {type(e).__name__}: {e}")

    # Окно не закроется само
    input("  Нажмите Enter для выхода...")
