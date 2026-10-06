# FILE: check_ai_models.py | VERSION: 1.2.2 | DATE: 2026-10-06
"""
check_ai_models.py — Проверка всех AI API ключей из config.py.

Проверяет все 6 AI систем включая OpenRouter и HuggingFace.
Запуск:
    cd C:\\stag_bot
    python check_ai_models.py

Результат: список AI с отметкой работает/не работает.
Окно НЕ закроется само — нажмите Enter в конце.
"""

import sys
import os
import asyncio

# Добавляем папку бота в путь чтобы импортировать config.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Импорт конфига ────────────────────────────────────────────────────────────
try:
    from config import (
        GROQ_API_KEY,
        DEEPSEEK_API_KEY,
        KIMI_API_KEY,
        GEMINI_API_KEY,
        ANTHROPIC_API_KEY,
        OPENROUTER_API_KEY,
        HF_API_KEY,
    )
except ImportError as e:
    print(f"ОШИБКА: не удалось импортировать config.py: {e}")
    input("\nНажмите Enter для выхода...")
    sys.exit(1)

# ── Проверяем наличие aiohttp ─────────────────────────────────────────────────
try:
    import aiohttp
except ImportError:
    print("ОШИБКА: aiohttp не установлен.")
    print("Выполните: pip install aiohttp")
    input("\nНажмите Enter для выхода...")
    sys.exit(1)

# Минимальный тестовый запрос
TEST_PROMPT = "Reply with one word: OK"


# ── Функции проверки каждого AI ───────────────────────────────────────────────

async def check_groq(session: aiohttp.ClientSession) -> tuple:
    """Проверяет Groq API (qwen/qwen3.8-27b)."""
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
            return "Groq", False, f"HTTP {r.status}: {data.get('error',{}).get('message','')[:100]}"
    except asyncio.TimeoutError:
        return "Groq", False, "таймаут (>20 сек)"
    except Exception as e:
        return "Groq", False, f"{type(e).__name__}: {e}"



async def check_groq2(session: aiohttp.ClientSession) -> tuple:
    """
    Проверяет второй слот Groq API (openai/gpt-oss-120b).
    Использует тот же ключ что и основной Groq но другую модель.
    """
    if not GROQ_API_KEY:
        return "Groq-2", None, "ключ не задан в config.py"
    try:
        async with session.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                     "Content-Type": "application/json"},
            json={"model": "openai/gpt-oss-120b",
                  "messages": [{"role": "user", "content": TEST_PROMPT}],
                  "max_tokens": 10},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as r:
            data = await r.json()
            if r.status == 200:
                answer = data["choices"][0]["message"]["content"].strip()
                if not answer:
                    return "Groq-2", False, "HTTP 200 но пустой ответ (модель не генерирует)"
                return "Groq-2", True, f"openai/gpt-oss-120b → '{answer}'"
            return "Groq-2", False, f"HTTP {r.status}: {data.get('error',{}).get('message','')[:100]}"
    except asyncio.TimeoutError:
        return "Groq-2", False, "таймаут (>20 сек)"
    except Exception as e:
        return "Groq-2", False, f"{type(e).__name__}: {e}"

async def check_deepseek(session: aiohttp.ClientSession) -> tuple:
    """Проверяет DeepSeek API (deepseek-chat)."""
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
            return "DeepSeek", False, f"HTTP {r.status}: {data.get('error',{}).get('message','')[:100]}"
    except asyncio.TimeoutError:
        return "DeepSeek", False, "таймаут (>20 сек)"
    except Exception as e:
        return "DeepSeek", False, f"{type(e).__name__}: {e}"


async def check_kimi(session: aiohttp.ClientSession) -> tuple:
    """Проверяет Kimi/Moonshot API (moonshot-v1-8k)."""
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
            return "Kimi/Moonshot", False, f"HTTP {r.status}: {data.get('error',{}).get('message','')[:100]}"
    except asyncio.TimeoutError:
        return "Kimi/Moonshot", False, "таймаут (>20 сек)"
    except Exception as e:
        return "Kimi/Moonshot", False, f"{type(e).__name__}: {e}"


async def check_gemini(session: aiohttp.ClientSession) -> tuple:
    """Проверяет Google Gemini API (gemini-3.5-flash-lite)."""
    if not GEMINI_API_KEY:
        return "Gemini", None, "ключ не задан в config.py"
    try:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta"
            f"/models/gemini-3.5-flash-lite:generateContent?key={GEMINI_API_KEY}"
        )
        async with session.post(
            url,
            json={"contents": [{"parts": [{"text": TEST_PROMPT}]}]},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as r:
            data = await r.json()
            if r.status == 200:
                answer = (data["candidates"][0]["content"]["parts"][0]["text"].strip())
                return "Gemini", True, f"gemini-3.5-flash-lite → '{answer}'"
            return "Gemini", False, f"HTTP {r.status}: {data.get('error',{}).get('message','')[:100]}"
    except asyncio.TimeoutError:
        return "Gemini", False, "таймаут (>20 сек)"
    except Exception as e:
        return "Gemini", False, f"{type(e).__name__}: {e}"


async def check_openrouter(session: aiohttp.ClientSession) -> tuple:
    """
    Проверяет OpenRouter API.
    Использует бесплатную модель meta-llama/llama-3.3-70b-instruct:free.
    Документация: openrouter.ai/docs
    """
    if not OPENROUTER_API_KEY:
        return "OpenRouter", None, "ключ не задан в config.py"
    try:
        async with session.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                # Обязательные заголовки для OpenRouter
                "HTTP-Referer": "https://github.com/tolikaka/stag-knowledge-base",
                "X-Title": "AI_Diag_UZ Bot",
            },
            json={
                "model": "qwen/qwen-2.5-72b-instruct:free",
                "messages": [{"role": "user", "content": TEST_PROMPT}],
                "max_tokens": 10,
            },
            timeout=aiohttp.ClientTimeout(total=25),
        ) as r:
            data = await r.json()
            if r.status == 200:
                answer = data["choices"][0]["message"]["content"].strip()
                return "OpenRouter", True, f"qwen-2.5-72b:free → '{answer}'"
            return "OpenRouter", False, f"HTTP {r.status}: {data.get('error',{}).get('message','')[:100]}"
    except asyncio.TimeoutError:
        return "OpenRouter", False, "таймаут (>25 сек)"
    except Exception as e:
        return "OpenRouter", False, f"{type(e).__name__}: {e}"


async def check_huggingface(session: aiohttp.ClientSession) -> tuple:
    """
    Проверяет HuggingFace Inference API.
    Модель: meta-llama/Llama-3.3-70B-Instruct
    Лимит: ~1000 запросов/день бесплатно.
    """
    if not HF_API_KEY:
        return "HuggingFace", None, "ключ не задан в config.py"
    try:
        # Используем новый endpoint HuggingFace Inference API v2
        url = (
            "https://router.huggingface.co/v1/chat/completions"
        )
        async with session.post(
            url,
            headers={
                "Authorization": f"Bearer {HF_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "meta-llama/Llama-3.3-70B-Instruct",
                "messages": [{"role": "user", "content": TEST_PROMPT}],
                "max_tokens": 10,
            },
            timeout=aiohttp.ClientTimeout(total=30),
        ) as r:
            if r.status == 200:
                data = await r.json()
                answer = data["choices"][0]["message"]["content"].strip()
                return "HuggingFace", True, f"Llama-3.3-70B → '{answer}'"
            elif r.status == 503:
                # 503 = модель загружается (cold start), временная ошибка
                return "HuggingFace", False, "HTTP 503: модель загружается (попробуйте позже)"
            else:
                text = await r.text()
                return "HuggingFace", False, f"HTTP {r.status}: {text[:100]}"
    except asyncio.TimeoutError:
        return "HuggingFace", False, "таймаут (>30 сек)"
    except Exception as e:
        return "HuggingFace", False, f"{type(e).__name__}: {str(e)[:100]}"


async def check_claude(session: aiohttp.ClientSession) -> tuple:
    """Проверяет Anthropic Claude Haiku API (платный fallback/арбитр)."""
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
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 10,
                "messages": [{"role": "user", "content": TEST_PROMPT}],
            },
            timeout=aiohttp.ClientTimeout(total=20),
        ) as r:
            data = await r.json()
            if r.status == 200:
                answer = data["content"][0]["text"].strip()
                return "Claude Haiku", True, f"claude-haiku → '{answer}'"
            return "Claude Haiku", False, f"HTTP {r.status}: {data.get('error',{}).get('message','')[:100]}"
    except asyncio.TimeoutError:
        return "Claude Haiku", False, "таймаут (>20 сек)"
    except Exception as e:
        return "Claude Haiku", False, f"{type(e).__name__}: {e}"


# ── Основная функция ──────────────────────────────────────────────────────────

async def main():
    """
    Запускает проверку всех AI последовательно.
    Выводит результат каждого AI сразу по мере проверки.
    В конце показывает итоговый список рабочих и нерабочих.
    """
    print("=" * 60)
    print("  Проверка AI API ключей — AI_Diag_UZ Bot")
    print("=" * 60)
    print()
    print("  Проверяем по очереди (до 30 сек на каждый)...")
    print()

    # Список всех проверок в порядке приоритета цепочки
    checkers = [
        check_groq,
        check_groq2,      # Второй слот Groq с моделью gpt-oss-120b
        check_deepseek,
        check_kimi,
        check_gemini,
        check_openrouter,
        check_huggingface,
        check_claude,
    ]

    results = []

    async with aiohttp.ClientSession() as session:
        for checker in checkers:
            try:
                result = await checker(session)
                results.append(result)
                name, ok, detail = result
                # Выводим результат сразу — не ждём остальных
                icon = "✅" if ok else ("⚪" if ok is None else "❌")
                print(f"  {icon} {name:<15} {detail}")
            except Exception as e:
                print(f"  ❌ НЕИЗВЕСТНАЯ ОШИБКА: {e}")

    # ── Итоговая статистика ───────────────────────────────────────────────────
    print()
    print("=" * 60)

    working = [r[0] for r in results if r[1] is True]
    broken  = [r[0] for r in results if r[1] is False]
    skipped = [r[0] for r in results if r[1] is None]

    if working:
        print(f"\n  ✅ Работают ({len(working)}): {', '.join(working)}")
    if broken:
        print(f"  ❌ Не работают ({len(broken)}): {', '.join(broken)}")
    if skipped:
        print(f"  ⚪ Ключ не задан ({len(skipped)}): {', '.join(skipped)}")

    # Предупреждение если меньше 4 рабочих AI
    if len(working) < 4:
        print(
            f"\n  ⚠️ Доступно менее 4 AI ({len(working)})!"
            f"\n  Для объективных ответов нужно минимум 4"
            f"\n  (3 соревнующихся + 1 арбитр)."
        )
    else:
        print(f"\n  ✅ Достаточно AI для объективных ответов ({len(working)} ≥ 4)")

    print()


# ── Точка входа ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  Прервано пользователем.")
    except Exception as e:
        print(f"\n  КРИТИЧЕСКАЯ ОШИБКА: {type(e).__name__}: {e}")

    # Окно не закроется само — ждём нажатия Enter
    input("  Нажмите Enter для выхода...")
