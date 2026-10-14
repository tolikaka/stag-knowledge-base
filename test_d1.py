# FILE: test_d1.py | VERSION: 1.1.0 | DATE: 2026-10-14
# ==============================================================================
#  test_d1.py — Тесты для пакета D1
# ==============================================================================
#
#  Проверяет:
#  1. _save_local — прямая запись без .tmp, файл создаётся корректно
#  2. add_pending_question — новая запись добавляется со всеми полями
#  3. add_pending_question — дубликат обновляет поля, не создаёт новую запись
#  4. ai_answer сохраняется при нажатии кнопки
#
#  Запуск (из папки C:\stag_bot\):
#      python test_d1.py
#
#  Ожидаемый результат: все тесты PASSED, нет FAILED
# ==============================================================================

import asyncio        # Для запуска async-функций в тестах
import json           # Проверка содержимого файла
import os             # Работа с файловой системой
import sys            # Выход с кодом ошибки
import tempfile       # Временная папка для тестов
from pathlib import Path  # Удобные пути

# ==============================================================================
#  Заглушки конфигурации (чтобы не зависеть от config.py при тестировании)
# ==============================================================================
# Подменяем модуль config до импорта knowledge_manager
import types
_fake_config = types.ModuleType("config")
_fake_config.GITHUB_TOKEN        = ""
_fake_config.GITHUB_REPO         = ""
_fake_config.GITHUB_FILE_PATH    = "knowledge_base.json"
_fake_config.GITHUB_BRANCH       = "main"
_fake_config.LOCAL_KB_PATH       = ""   # будет переопределён в каждом тесте
_fake_config.SIMILARITY_THRESHOLD = 0.45
_fake_config.TOP_K_RESULTS        = 3
sys.modules["config"] = _fake_config

# Импортируем после подстановки заглушки
import knowledge_manager as km_module
from knowledge_manager import KnowledgeManager

# ==============================================================================
#  Вспомогательные функции
# ==============================================================================

def make_manager(tmp_dir: str) -> KnowledgeManager:
    """
    Создаёт KnowledgeManager с путём к файлу во временной папке.
    Подменяет глобальную константу LOCAL_KB_PATH для изоляции тестов.
    """
    kb_path = os.path.join(tmp_dir, "test_kb.json")
    # Подменяем константу в модуле
    km_module.LOCAL_KB_PATH = kb_path
    _fake_config.LOCAL_KB_PATH = kb_path
    mgr = KnowledgeManager()
    return mgr, kb_path


# ==============================================================================
#  ТЕСТЫ
# ==============================================================================

passed = 0
failed = 0

def assert_true(condition: bool, msg: str) -> None:
    """Простая проверка с выводом результата."""
    global passed, failed
    if condition:
        print(f"  ✅ PASSED: {msg}")
        passed += 1
    else:
        print(f"  ❌ FAILED: {msg}")
        failed += 1


# ------------------------------------------------------------------------------
# ТЕСТ 1: _save_local создаёт файл без .tmp
# ------------------------------------------------------------------------------
async def test_save_local_creates_file():
    """_save_local должна создавать файл knowledge_base.json без .tmp артефактов."""
    print("\n[ТЕСТ 1] _save_local создаёт файл и не оставляет .tmp")
    with tempfile.TemporaryDirectory() as tmp_dir:
        mgr, kb_path = make_manager(tmp_dir)

        # Загружаем пустую базу (создаст файл)
        await mgr.load()

        # Проверяем что .json файл создан
        assert_true(Path(kb_path).exists(), "knowledge_base.json существует")

        # Проверяем что .tmp файл НЕ остался
        tmp_path = Path(kb_path).with_suffix(".tmp")
        assert_true(not tmp_path.exists(), ".tmp файл отсутствует")

        # Проверяем что файл валидный JSON
        with open(kb_path, encoding="utf-8") as f:
            data = json.load(f)
        assert_true("entries" in data, "JSON содержит ключ 'entries'")
        assert_true("pending_learning" in data, "JSON содержит ключ 'pending_learning'")


# ------------------------------------------------------------------------------
# ТЕСТ 2: _save_local сохраняет данные корректно
# ------------------------------------------------------------------------------
async def test_save_local_saves_data():
    """После сохранения данные должны читаться с диска без изменений."""
    print("\n[ТЕСТ 2] _save_local сохраняет данные корректно")
    with tempfile.TemporaryDirectory() as tmp_dir:
        mgr, kb_path = make_manager(tmp_dir)
        await mgr.load()

        # Добавляем тестовую запись в pending
        mgr.add_pending_question(
            user_id=12345,
            username="test_user",
            message_text="Тестовый вопрос для проверки",
            chat_id=99999,
            source_action="auto",
            source_role="system",
            ai_answer="Тестовый ответ AI",
            lang="ru",
        )

        # Читаем файл с диска и проверяем
        with open(kb_path, encoding="utf-8") as f:
            data = json.load(f)

        pending = data.get("pending_learning", [])
        assert_true(len(pending) == 1, "Одна запись в pending_learning")
        assert_true(
            pending[0]["message_text"] == "Тестовый вопрос для проверки",
            "Текст вопроса сохранён корректно"
        )
        assert_true(
            pending[0]["ai_answer"] == "Тестовый ответ AI",
            "ai_answer сохранён корректно"
        )


# ------------------------------------------------------------------------------
# ТЕСТ 3: add_pending_question — новая запись содержит все нужные поля
# ------------------------------------------------------------------------------
async def test_pending_all_fields():
    """Новая pending-запись должна содержать все поля структуры."""
    print("\n[ТЕСТ 3] add_pending_question — все поля в новой записи")
    with tempfile.TemporaryDirectory() as tmp_dir:
        mgr, kb_path = make_manager(tmp_dir)
        await mgr.load()

        mgr.add_pending_question(
            user_id=39425955,
            username="admin_user",
            message_text="что такое ошибка P0300?",
            chat_id=-100123456,
            source_action="auto",
            source_role="system",
            ai_answer="P0300 — пропуск воспламенения в нескольких цилиндрах",
            ai_answer2="",
            lang="ru",
            file_id="",
        )

        pending = mgr.get_pending()
        assert_true(len(pending) == 1, "Запись создана")

        entry = pending[0]
        required_fields = [
            "id", "user_id", "username", "message_text", "chat_id",
            "timestamp", "status", "lang", "source_action", "source_role",
            "ai_answer", "ai_answer2", "file_id",
        ]
        for field in required_fields:
            assert_true(field in entry, f"Поле '{field}' присутствует")

        assert_true(entry["source_action"] == "auto", "source_action = 'auto'")
        assert_true(entry["source_role"]   == "system", "source_role = 'system'")
        assert_true(entry["lang"]          == "ru", "lang = 'ru'")
        assert_true(entry["status"]        == "new", "status = 'new'")


# ------------------------------------------------------------------------------
# ТЕСТ 4: add_pending_question — дубликат ОБНОВЛЯЕТ запись, не создаёт новую
# ------------------------------------------------------------------------------
async def test_pending_duplicate_updates():
    """
    Кейс: AI автоматически добавил запись (action=auto),
    затем пользователь нажал кнопку (action=sat_wrong).
    Должна остаться одна запись с обновлёнными полями.
    """
    print("\n[ТЕСТ 4] add_pending_question — дубликат обновляет запись")
    with tempfile.TemporaryDirectory() as tmp_dir:
        mgr, kb_path = make_manager(tmp_dir)
        await mgr.load()

        question = "что такое ошибка P0300?"

        # Шаг 1: AI добавляет автоматически
        mgr.add_pending_question(
            user_id=39425955,
            username="admin",
            message_text=question,
            chat_id=-100123456,
            source_action="auto",
            source_role="system",
            ai_answer="Первый ответ AI",
        )

        # Шаг 2: Пользователь нажал "Не верно"
        mgr.add_pending_question(
            user_id=39425955,
            username="admin",
            message_text=question,
            chat_id=-100123456,
            source_action="sat_wrong",
            source_role="admin",
            ai_answer="Первый ответ AI",  # О1 не перезаписывается если уже есть
            ai_answer2="Второй ответ AI после retry",
        )

        pending = mgr.get_pending()

        # Проверяем: ОДНА запись (не две)
        assert_true(len(pending) == 1, "Только одна запись (нет дубликата)")

        entry = pending[0]
        # source_action должен обновиться на sat_wrong
        assert_true(entry["source_action"] == "sat_wrong", "source_action обновился на 'sat_wrong'")
        # source_role должен обновиться на admin
        assert_true(entry["source_role"] == "admin", "source_role обновился на 'admin'")
        # ai_answer2 должен появиться
        assert_true(
            entry.get("ai_answer2") == "Второй ответ AI после retry",
            "ai_answer2 сохранён"
        )
        # ai_answer НЕ должен перезаписаться (уже был заполнен)
        assert_true(
            entry.get("ai_answer") == "Первый ответ AI",
            "ai_answer (О1) не перезаписан"
        )


# ------------------------------------------------------------------------------
# ТЕСТ 5: Данные сохраняются после нажатия кнопки (интеграционный)
# ------------------------------------------------------------------------------
async def test_save_after_button_press():
    """
    Имитирует полный цикл: вопрос → ответ AI → кнопка "Уточнить".
    После нажатия кнопки данные должны быть на диске.
    """
    print("\n[ТЕСТ 5] Данные на диске после нажатия кнопки (интеграционный)")
    with tempfile.TemporaryDirectory() as tmp_dir:
        mgr, kb_path = make_manager(tmp_dir)
        await mgr.load()

        question = "Уста, какую температуру перехода на газ нужно установить?"

        # AI автоматически добавил при ответе
        mgr.add_pending_question(
            user_id=39425955,
            username="Anatoliy",
            message_text=question,
            chat_id=-1004368283151,
            source_action="auto",
            source_role="system",
            ai_answer="Температура перехода на газ обычно 50-70°C",
            lang="ru",
        )

        # Администратор нажал "Не верно"
        mgr.add_pending_question(
            user_id=39425955,
            username="Anatoliy",
            message_text=question,
            chat_id=-1004368283151,
            source_action="sat_wrong",
            source_role="admin",
            ai_answer2="Второй вариант ответа",
            lang="ru",
        )

        # Читаем файл с диска (не из памяти!)
        with open(kb_path, encoding="utf-8") as f:
            data = json.load(f)

        pending = data.get("pending_learning", [])
        assert_true(len(pending) == 1, "Одна запись на диске")
        assert_true(
            pending[0]["source_action"] == "sat_wrong",
            "source_action = 'sat_wrong' сохранён на диск"
        )
        assert_true(
            pending[0]["source_role"] == "admin",
            "source_role = 'admin' сохранён на диск"
        )


# ------------------------------------------------------------------------------
# ТЕСТ 6: повторное нажатие кнопки на rejected-запись сбрасывает статус в new
# ------------------------------------------------------------------------------
async def test_rejected_reset_to_new():
    """
    Кейс: запись была отклонена администратором (status=rejected).
    Пользователь задал тот же вопрос снова и нажал кнопку.
    Статус должен сброситься в "new" чтобы запись снова появилась
    в разделе "На проверке" (фильтр status=="new").
    """
    print("\n[ТЕСТ 6] Повторная кнопка на rejected-записи → статус сбрасывается в new")
    with tempfile.TemporaryDirectory() as tmp_dir:
        mgr, kb_path = make_manager(tmp_dir)
        await mgr.load()

        question = "что такое ошибка P0300?"

        # Шаг 1: создаём запись и сразу ставим ей статус rejected
        mgr.add_pending_question(
            user_id=39425955,
            username="admin",
            message_text=question,
            chat_id=-100123456,
            source_action="auto",
            source_role="system",
            ai_answer="P0300 — пропуск воспламенения",
        )
        # Имитируем что администратор нажал "Отклонить" в админке
        pending = mgr.get_pending()
        pending[0]["status"] = "rejected"
        mgr._save_sync()

        # Шаг 2: пользователь снова нажал кнопку "Не верно"
        mgr.add_pending_question(
            user_id=39425955,
            username="admin",
            message_text=question,
            chat_id=-100123456,
            source_action="sat_wrong",
            source_role="admin",
        )

        # Проверяем: статус должен стать "new"
        updated = mgr.get_pending()
        assert_true(len(updated) == 1, "Запись одна (не создана дублирующая)")
        assert_true(
            updated[0]["status"] == "new",
            "Статус сброшен с 'rejected' → 'new'"
        )
        assert_true(
            updated[0]["source_action"] == "sat_wrong",
            "source_action обновился на sat_wrong"
        )

        # Читаем с диска — убеждаемся что "new" записан на диск
        with open(kb_path, encoding="utf-8") as f:
            data = json.load(f)
        assert_true(
            data["pending_learning"][0]["status"] == "new",
            "Статус 'new' сохранён на диск"
        )


# ==============================================================================
#  ЗАПУСК ВСЕХ ТЕСТОВ
# ==============================================================================

async def run_all():
    """Запускает все тесты последовательно."""
    print("=" * 60)
    print("  ТЕСТЫ ПАКЕТА D1 — knowledge_manager._save_local")
    print("=" * 60)

    await test_save_local_creates_file()
    await test_save_local_saves_data()
    await test_pending_all_fields()
    await test_pending_duplicate_updates()
    await test_save_after_button_press()
    await test_rejected_reset_to_new()

    print("\n" + "=" * 60)
    print(f"  ИТОГО: {passed} PASSED  |  {failed} FAILED")
    print("=" * 60)

    if failed > 0:
        print("\n⚠️  Есть ошибки — проверьте вывод выше")
        sys.exit(1)
    else:
        print("\n✅ Все тесты прошли успешно!")


if __name__ == "__main__":
    asyncio.run(run_all())
