# FILE: main.py | VERSION: 1.2.0 | DATE: 2026-10-04
"""
main.py — Точка запуска AI_Diag_UZ Bot
========================================
Авторизация Telethon выполняется в auth_telethon.py (до запуска main.py).
main.py только проверяет статус сессии и запускает бота.
"""

import asyncio
import logging
import os
import sys
import subprocess
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Только корень в sys.path — все .py файлы в корне C:\stag_bot\
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.join(BASE_DIR, "ai_diag_uz.log"),
            encoding="utf-8"
        ),
    ],
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telethon").setLevel(logging.WARNING)
logging.getLogger("telegram.ext.Updater").setLevel(logging.WARNING)
logging.getLogger("telegram.ext.Application").setLevel(logging.WARNING)
logging.getLogger("telegram.error").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def install_package(package: str, import_name: str = None) -> bool:
    """Устанавливает пакет если отсутствует."""
    name = import_name or package.split("==")[0].split(">=")[0]
    try:
        __import__(name)
        return True
    except ImportError:
        pass
    logger.info("  Устанавливаю %s...", package)
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", package, "--quiet"],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode == 0:
            try:
                __import__(name)
                logger.info("  %s: установлен OK", package)
                return True
            except ImportError:
                pass
        logger.warning("  %s: ошибка установки", package)
    except Exception as e:
        logger.warning("  %s: %s", package, e)
    return False


async def check_ai_availability() -> list:
    """
    Проверяет доступность всех настроенных AI API при старте бота.

    Выполняет минимальный тестовый запрос к каждому API.
    Результат выводится в консоль — список рабочих и нерабочих AI.
    Предупреждение если доступно менее 4 AI (недостаточно для
    объективного ответа: 3 соревнующихся + 1 арбитр).

    Возвращает:
        Список имён доступных AI (например ['Groq', 'Gemini', 'Claude'])
    """
    try:
        import aiohttp as _aiohttp
        from config import (
            GROQ_API_KEY, DEEPSEEK_API_KEY, GEMINI_API_KEY,
            ANTHROPIC_API_KEY, OPENROUTER_API_KEY, HF_API_KEY,
        )
    except ImportError:
        logger.warning("  Проверка AI: не удалось импортировать зависимости")
        return []

    # Минимальный тестовый запрос — быстро и не тратит токены
    TEST = "Reply with one word: OK"
    available = []

    logger.info("  Проверка доступности AI...")

    async def _test(name: str, coro) -> bool:
        """Выполняет тест и логирует результат."""
        try:
            result = await asyncio.wait_for(coro, timeout=15)
            ok = bool(result and len(result) > 0)
            icon = "✅" if ok else "❌"
            logger.info(f"  {icon} {name:<15} {'доступен' if ok else 'нет ответа'}")
            return ok
        except asyncio.TimeoutError:
            logger.info(f"  ❌ {name:<15} таймаут (>15 сек)")
            return False
        except Exception as e:
            logger.info(f"  ❌ {name:<15} ошибка: {e}")
            return False

    async with _aiohttp.ClientSession() as session:

        # ── Groq ──────────────────────────────────────────────────────────────
        if GROQ_API_KEY:
            async def _groq():
                async with session.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                    json={"model": "qwen/qwen3.8-27b",
                          "messages": [{"role": "user", "content": TEST}],
                          "max_tokens": 5},
                ) as r:
                    return (await r.json()).get("choices", [{}])[0].get(
                        "message", {}).get("content", "") if r.status == 200 else ""
            if await _test("Groq", _groq()):
                available.append("Groq")

        # ── DeepSeek ──────────────────────────────────────────────────────────
        if DEEPSEEK_API_KEY:
            async def _deepseek():
                async with session.post(
                    "https://api.deepseek.com/chat/completions",
                    headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
                    json={"model": "deepseek-chat",
                          "messages": [{"role": "user", "content": TEST}],
                          "max_tokens": 5},
                ) as r:
                    return (await r.json()).get("choices", [{}])[0].get(
                        "message", {}).get("content", "") if r.status == 200 else ""
            if await _test("DeepSeek", _deepseek()):
                available.append("DeepSeek")

        # ── Gemini ────────────────────────────────────────────────────────────
        if GEMINI_API_KEY:
            async def _gemini():
                async with session.post(
                    f"https://generativelanguage.googleapis.com/v1beta"
                    f"/models/gemini-3.8-flash:generateContent?key={GEMINI_API_KEY}",
                    json={"contents": [{"parts": [{"text": TEST}]}]},
                ) as r:
                    data = await r.json()
                    return (data.get("candidates", [{}])[0]
                            .get("content", {})
                            .get("parts", [{}])[0]
                            .get("text", "")) if r.status == 200 else ""
            if await _test("Gemini", _gemini()):
                available.append("Gemini")

        # ── OpenRouter ────────────────────────────────────────────────────────
        if OPENROUTER_API_KEY:
            async def _openrouter():
                async with session.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "HTTP-Referer": "https://github.com/tolikaka/stag-knowledge-base",
                        "X-Title": "AI_Diag_UZ Bot",
                    },
                    json={"model": "meta-llama/llama-3.3-70b-instruct:free",
                          "messages": [{"role": "user", "content": TEST}],
                          "max_tokens": 5},
                ) as r:
                    return (await r.json()).get("choices", [{}])[0].get(
                        "message", {}).get("content", "") if r.status == 200 else ""
            if await _test("OpenRouter", _openrouter()):
                available.append("OpenRouter")

        # ── HuggingFace ───────────────────────────────────────────────────────
        if HF_API_KEY:
            async def _hf():
                async with session.post(
                    "https://api-inference.huggingface.co/models/"
                    "meta-llama/Llama-3.3-70B-Instruct/v1/chat/completions",
                    headers={"Authorization": f"Bearer {HF_API_KEY}"},
                    json={"model": "meta-llama/Llama-3.3-70B-Instruct",
                          "messages": [{"role": "user", "content": TEST}],
                          "max_tokens": 5},
                ) as r:
                    return (await r.json()).get("choices", [{}])[0].get(
                        "message", {}).get("content", "") if r.status == 200 else ""
            if await _test("HuggingFace", _hf()):
                available.append("HuggingFace")

        # ── Claude Haiku (всегда проверяем — это арбитр/fallback) ─────────────
        if ANTHROPIC_API_KEY:
            async def _claude():
                async with session.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": ANTHROPIC_API_KEY,
                             "anthropic-version": "2023-06-01"},
                    json={"model": "claude-haiku-4-5-20251001",
                          "max_tokens": 5,
                          "messages": [{"role": "user", "content": TEST}]},
                ) as r:
                    data = await r.json()
                    return data.get("content", [{}])[0].get(
                        "text", "") if r.status == 200 else ""
            if await _test("Claude Haiku", _claude()):
                available.append("Claude")

    # ── Итог ──────────────────────────────────────────────────────────────────
    total = len(available)
    logger.info(f"  Доступно AI: {total} — {', '.join(available) if available else 'нет'}")

    if total < 4:
        logger.warning(
            f"  ⚠️ Доступно менее 4 AI ({total})! "
            f"Для объективных ответов нужно минимум 4 "
            f"(3 соревнующихся + 1 арбитр). "
            f"Проверьте API ключи в config.py."
        )
    else:
        logger.info(f"  ✅ Достаточно AI для объективных ответов ({total} ≥ 4)")

    return available



def check_dependencies():
    """Проверяет и устанавливает обязательные зависимости."""
    logger.info("  Проверка зависимостей...")

    # Обязательные
    for pkg, imp in [("aiohttp", None), ("Pillow", "PIL")]:
        try:
            __import__(imp or pkg)
            logger.info("  %s: OK", pkg)
        except ImportError:
            install_package(pkg, imp)

    # Telethon — только установка если нужен, авторизация в auth_telethon.py
    try:
        from config import TG_API_ID, TG_API_HASH
        if TG_API_ID and TG_API_HASH:
            try:
                import telethon
                logger.info("  telethon %s: OK", telethon.__version__)
            except ImportError:
                install_package("telethon")

            # Только статус — никакой авторизации здесь
            session = os.path.join(BASE_DIR, "bot_session.session")
            if os.path.exists(session):
                logger.info("  Telethon: сессия найдена")
            else:
                logger.warning(
                    "  Telethon: сессия не найдена — "
                    "скачивание файлов > 20MB недоступно"
                )
    except (ImportError, AttributeError):
        logger.info("  Telethon: TG_API_ID не задан")


def run_admin_in_thread():
    """Запускает Flask веб-панель в отдельном потоке."""
    try:
        from admin import run_admin
        logger.info("  Web-panel: http://localhost:8080")
        run_admin()
    except Exception as e:
        logger.error("Admin panel error: %s", e)


def main():
    logger.info("=" * 60)
    logger.info("  AI_Diag_UZ - Usta  |  CarDiag UZ Bot")
    logger.info("=" * 60)

    try:
        import config  # noqa
        logger.info("  config.py: OK")
    except ImportError:
        logger.warning("  config.py не найден!")

    # Создаём папки для данных
    for subdir in ["knowledge_base", "files_cache"]:
        os.makedirs(os.path.join(BASE_DIR, subdir), exist_ok=True)

    # Создаём file_catalog.json если нет
    import json
    catalog_path = os.path.join(BASE_DIR, "files_cache", "file_catalog.json")
    if not os.path.exists(catalog_path):
        with open(catalog_path, "w", encoding="utf-8") as f:
            json.dump(
                {"version": "1.0", "last_updated": "", "files": []},
                f, ensure_ascii=False, indent=2
            )
        logger.info("  file_catalog.json: создан")

    # Зависимости
    check_dependencies()

    # Проверяем доступность AI API при старте (G7)
    # Запускаем во временном event loop до создания основного
    try:
        _ai_loop = asyncio.new_event_loop()
        available_ai = _ai_loop.run_until_complete(check_ai_availability())
        _ai_loop.close()
    except Exception as e:
        logger.warning("  Проверка AI не выполнена: %s", e)
        available_ai = []

    # Создаём чистый event loop для бота
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Flask в отдельном потоке
    threading.Thread(target=run_admin_in_thread, daemon=True).start()

    # Запуск бота
    logger.info("  Запускаем бота...")
    from bot import main as bot_main
    bot_main()


if __name__ == "__main__":
    main()
