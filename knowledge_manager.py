# ==============================================================================
#  knowledge_manager.py  —  Управление базой знаний AI_Diag_UZ
# ==============================================================================
#
#  ЧТО ДЕЛАЕТ ЭТОТ ФАЙЛ:
#  1. Хранит и загружает базу знаний (JSON-файл с вопросами и ответами)
#  2. Синхронизирует базу знаний с GitHub (облачное хранилище):
#       - При запуске: скачивает актуальную версию с GitHub
#       - Каждый час: автоматически обновляет локальную копию
#       - По команде: загружает изменения на GitHub
#  3. Выполняет семантический поиск (поиск по смыслу, а не по точным словам):
#       Например: "не переключается" найдёт "Почему авто не переходит на газ?"
#  4. CRUD-операции: создание, чтение, обновление, удаление записей
#  5. Сохраняет вопросы без ответов (самообучение) для проверки администратором
#
#  ПРИНЦИП СЕМАНТИЧЕСКОГО ПОИСКА (TF-IDF):
#  TF-IDF — это математический метод оценки важности слова в тексте.
#  TF (Term Frequency) — как часто слово встречается в документе
#  IDF (Inverse Document Frequency) — насколько редкое слово во всех документах
#  Редкие слова ("инжектор", "калибровка") важнее частых ("и", "в", "на").
#  Cosine similarity — мера схожести двух текстов (от 0 до 1).
#
#  ВАЖНО: Не использует внешние ML-библиотеки (sklearn, torch и т.д.) —
#  всё реализовано "с нуля" на чистом Python.
#
#  ЗАВИСИМОСТИ:
#    aiohttp  — асинхронные HTTP-запросы к GitHub API
#    aiofiles — асинхронное чтение/запись файлов
# ==============================================================================

# --- Стандартные библиотеки ---
import json      # Работа с JSON-файлами (сериализация/десериализация)
import os        # Работа с операционной системой
import re        # Регулярные выражения (для токенизации текста)
import math      # Математические функции (log, sqrt для TF-IDF)
import hashlib   # Хэш-функции (для генерации уникальных ID записей)
import logging   # Журнал событий и ошибок
import asyncio   # Асинхронное программирование
from datetime import datetime, timezone  # Работа с датой/временем
from pathlib import Path                  # Удобная работа с путями к файлам
from typing import Optional               # Типы: Optional[X] = X или None
from collections import Counter           # Подсчёт частоты элементов

# --- Сторонние библиотеки ---
import aiohttp   # Асинхронный HTTP-клиент (для запросов к GitHub API)
import aiofiles  # Асинхронная работа с файлами

logger = logging.getLogger(__name__)

# ==============================================================================
#  ЗАГРУЗКА КОНФИГУРАЦИИ
# ==============================================================================
try:
    # Пробуем загрузить настройки из config.py
    from config import (
        GITHUB_TOKEN,       # Токен доступа к GitHub
        GITHUB_REPO,        # Репозиторий: "username/repo-name"
        GITHUB_FILE_PATH,   # Путь к файлу в репозитории
        GITHUB_BRANCH,      # Ветка Git (обычно "main")
        LOCAL_KB_PATH,      # Путь к локальному файлу базы знаний
        SIMILARITY_THRESHOLD,  # Порог совпадения для поиска (0.0–1.0)
        TOP_K_RESULTS,         # Сколько результатов возвращать
    )
except ImportError:
    # Если config.py нет — используем переменные окружения или значения по умолчанию
    GITHUB_TOKEN       = os.environ.get("GITHUB_TOKEN", "")
    GITHUB_REPO        = os.environ.get("GITHUB_REPO", "")
    GITHUB_FILE_PATH   = os.environ.get("GITHUB_FILE_PATH", "knowledge_base.json")
    GITHUB_BRANCH      = os.environ.get("GITHUB_BRANCH", "main")
    LOCAL_KB_PATH      = "knowledge_base/knowledge_base.json"
    SIMILARITY_THRESHOLD = 0.45   # 45% совпадение — минимальный порог релевантности
    TOP_K_RESULTS      = 3        # Показывать топ-3 результата

# Базовый URL GitHub API
GITHUB_API = "https://api.github.com"


# ==============================================================================
#  TF-IDF СЕМАНТИЧЕСКИЙ ПОИСК
#  Реализован без внешних библиотек — только стандартный Python
# ==============================================================================

def _tokenize(text: str) -> list[str]:
    """
    Разбивает текст на отдельные слова (токены) и нормализует их.

    Процесс:
    1. Переводим в нижний регистр (STAG → stag)
    2. Убираем знаки препинания (оставляем буквы, цифры, дефисы)
    3. Разбиваем на слова
    4. Убираем "стоп-слова" — частые слова без смыслового значения
       (предлоги, союзы: "и", "в", "на", "the", "a" и т.д.)

    Аргументы:
        text (str): исходный текст

    Возвращает:
        list[str]: список значимых слов (токенов)

    Пример:
        _tokenize("Как откалибровать STAG-4?")
        → ["откалибровать", "stag-4"]
    """
    text = text.lower()  # Нижний регистр

    # Убираем всё кроме букв, цифр и дефисов
    # \w — буква или цифра, \s — пробел, \- — дефис
    text = re.sub(r"[^\w\s\-]", " ", text, flags=re.UNICODE)

    tokens = text.split()  # Разбиваем на слова по пробелам

    # Стоп-слова — слова, которые не несут смысловой нагрузки
    # Они очень часто встречаются и "засоряют" индекс
    stop_words = {
        # Русские стоп-слова
        "и", "в", "на", "с", "по", "для", "от", "до", "это", "не", "как",
        "все", "при", "или", "но", "а", "то", "же", "бы", "ли", "так",
        "уже", "вот", "что", "где", "есть", "нет", "да", "нет", "если",
        "когда", "то", "ещё", "чем", "бы", "был", "была", "было", "были",
        # Английские стоп-слова
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "to", "of", "in", "on",
        "at", "by", "for", "with", "about", "into", "through",
    }

    # Возвращаем только слова длиннее 1 символа, которых нет в стоп-словах
    return [t for t in tokens if t not in stop_words and len(t) > 1]


def _build_tfidf(documents: list[list[str]]) -> tuple[dict, list[dict]]:
    """
    Вычисляет TF-IDF векторы для набора документов.

    TF-IDF (Term Frequency — Inverse Document Frequency):
    - TF: как часто слово встречается в ДАННОМ документе
    - IDF: насколько слово редкое СРЕДИ ВСЕХ документов
    - TF-IDF = TF × IDF: важность слова в документе с учётом редкости

    Пример:
    - Слово "газ" есть во всех 100 документах → IDF низкое (слово неинформативно)
    - Слово "калибровка" есть в 5 документах → IDF высокое (слово специфично)

    Аргументы:
        documents: список документов, каждый — список слов (токенов)

    Возвращает:
        tuple: (idf_словарь, список_векторов)
        idf_словарь: {слово: idf_значение}
        список_векторов: [{слово: tfidf_значение}, ...] для каждого документа
    """
    n = len(documents)  # Количество документов

    # ── Вычисляем IDF ────────────────────────────────────────────────────────
    # df (document frequency) = в скольких документах встречается слово
    df: dict[str, int] = {}
    for doc in documents:
        for term in set(doc):  # set() убирает дубликаты внутри документа
            df[term] = df.get(term, 0) + 1

    # IDF = log((N+1) / (df+1)) + 1
    # +1 в знаменателе — сглаживание (избегаем деления на 0)
    # +1 в конце — чтобы IDF никогда не было отрицательным
    idf = {
        term: math.log((n + 1) / (count + 1)) + 1
        for term, count in df.items()
    }

    # ── Вычисляем TF-IDF векторы ─────────────────────────────────────────────
    vectors = []
    for doc in documents:
        tf = Counter(doc)      # Подсчёт частоты каждого слова
        total = len(doc) or 1  # Общее число слов (or 1 — защита от деления на 0)

        # TF = количество_слова / всего_слов (нормализованная частота)
        # TF-IDF = TF × IDF
        vec = {
            term: (tf[term] / total) * idf.get(term, 1.0)
            for term in doc
        }
        vectors.append(vec)

    return idf, vectors


def _cosine_similarity(v1: dict, v2: dict) -> float:
    """
    Вычисляет косинусное сходство двух TF-IDF векторов.

    Косинусное сходство измеряет угол между двумя векторами в многомерном
    пространстве слов. Значение от 0 до 1:
    - 1.0 = тексты идентичны
    - 0.5 = тексты похожи (50% совпадение)
    - 0.0 = тексты совершенно разные (нет общих слов)

    Формула: cos(θ) = (v1·v2) / (|v1| × |v2|)
    где v1·v2 — скалярное произведение, |v| — длина вектора

    Аргументы:
        v1, v2: словари {слово: tfidf_значение}

    Возвращает:
        float: сходство от 0.0 до 1.0
    """
    # Находим общие слова (пересечение множеств ключей)
    common_terms = set(v1.keys()) & set(v2.keys())

    # Если нет общих слов — сходство 0
    if not common_terms:
        return 0.0

    # Скалярное произведение: сумма произведений значений по общим словам
    dot_product = sum(v1[term] * v2[term] for term in common_terms)

    # Длины векторов (евклидова норма)
    norm1 = math.sqrt(sum(x * x for x in v1.values()))
    norm2 = math.sqrt(sum(x * x for x in v2.values()))

    # Защита от деления на ноль
    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)


# ==============================================================================
#  КЛАСС KnowledgeManager — ОСНОВНОЙ КЛАСС УПРАВЛЕНИЯ БАЗОЙ ЗНАНИЙ
# ==============================================================================

class KnowledgeManager:
    """
    Менеджер базы знаний.

    Отвечает за:
    - Загрузку и сохранение базы знаний (JSON)
    - Синхронизацию с GitHub
    - Семантический поиск по содержимому
    - CRUD-операции с записями
    - Накопление вопросов для самообучения
    """

    def __init__(self):
        """
        Инициализация менеджера.
        Задаём начальные значения всех атрибутов.
        """
        # Внутреннее хранилище данных базы знаний
        # Структура JSON-файла:
        # {
        #   "version": "1.0.0",
        #   "entries": [...],          — записи вопрос-ответ
        #   "categories": [...],       — список категорий
        #   "pending_learning": [...]  — вопросы без ответов
        # }
        self._kb: dict = {
            "entries": [],
            "categories": [],
            "pending_learning": []
        }

        # TF-IDF индекс для быстрого семантического поиска
        self._idf: dict = {}          # IDF-значения для каждого слова
        self._vectors: list[dict] = [] # TF-IDF векторы для каждой записи

        # SHA-хэш текущего файла на GitHub (нужен для обновления файла)
        # GitHub требует передавать SHA при PUT-запросах (обновление файла)
        self._github_sha: Optional[str] = None

        # Время последней успешной синхронизации
        self._last_sync: Optional[datetime] = None

        # asyncio Lock — предотвращает одновременный доступ к данным
        # из разных асинхронных задач (race condition)
        self._lock = asyncio.Lock()

    # ==========================================================================
    #  ЗАГРУЗКА БАЗЫ ЗНАНИЙ
    # ==========================================================================

    async def load(self) -> None:
        """
        Загружает базу знаний при запуске системы.

        Приоритет: GitHub (актуальная облачная версия) → Локальный файл.
        После загрузки перестраивает поисковый индекс.
        """
        loaded_from_github = False

        # Пробуем загрузить с GitHub если настроен токен
        if GITHUB_TOKEN and GITHUB_REPO:
            loaded_from_github = await self._load_from_github()

        # Если GitHub недоступен или не настроен — загружаем локально
        if not loaded_from_github:
            await self._load_local()

        # Перестраиваем TF-IDF индекс для поиска
        self._rebuild_index()

        logger.info(
            f"База знаний загружена: {len(self._kb.get('entries', []))} записей"
        )

    async def _load_from_github(self) -> bool:
        """
        Скачивает файл базы знаний с GitHub через GitHub API.

        GitHub API позволяет получить содержимое файла из репозитория.
        URL: GET /repos/{owner}/{repo}/contents/{path}
        Ответ содержит файл в кодировке base64 — декодируем в JSON.

        Возвращает:
            True  — успешно загружено
            False — ошибка (нет соединения, неверный токен, файл не найден)
        """
        # Заголовки HTTP-запроса к GitHub API
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",  # Авторизация по токену
            "Accept": "application/vnd.github.v3+json", # Версия API
        }

        # URL для получения файла
        url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=headers,
                    params={"ref": GITHUB_BRANCH}  # Указываем ветку
                ) as response:

                    if response.status != 200:
                        logger.warning(
                            f"GitHub API вернул статус {response.status}"
                        )
                        return False

                    data = await response.json()

                    # Декодируем base64 -> байты -> строка UTF-8 -> JSON
                    import base64
                    # Сохраняем sha ВСЕГДА — нужен для PUT при обновлении
                    if "sha" in data:
                        self._github_sha = data["sha"]
                        logger.info(f"GitHub sha получен: {self._github_sha[:12]}...")

                    raw_content = data.get("content", "")
                    if not raw_content or not raw_content.strip():
                        logger.warning("GitHub: файл пустой (sha сохранён для последующей записи)")
                        return False
                    content_bytes = base64.b64decode(raw_content)
                    content_str = content_bytes.decode("utf-8")
                    if not content_str.strip():
                        logger.warning("GitHub: пустой контент после декодирования")
                        return False
                    self._kb = json.loads(content_str)

                    # Сохраняем SHA для последующих обновлений
                    self._github_sha = data["sha"]
                    self._last_sync = datetime.now(timezone.utc)

                    # Сохраняем локальную копию
                    await self._save_local()

                    logger.info("✅ База знаний загружена с GitHub")
                    return True

        except Exception as e:
            logger.error(f"Ошибка загрузки с GitHub: {e}")
            return False

    async def _load_local(self) -> None:
        """
        Загружает базу знаний из локального JSON-файла.
        Используется как резервный вариант если GitHub недоступен.
        Если файл пустой или повреждён — создаёт пустую базу и сохраняет.
        """
        path = Path(LOCAL_KB_PATH)

        if path.exists():
            try:
                async with aiofiles.open(path, encoding="utf-8") as f:
                    content = await f.read()

                # Проверяем что файл не пустой
                if not content or not content.strip():
                    logger.warning(
                        f"⚠️ Файл БЗ пустой: {path}. Создаём новую базу."
                    )
                    self._kb = self._empty_kb()
                    await self._save_local()
                    return

                self._kb = json.loads(content)
                logger.info(f"✅ База знаний загружена локально: {path}")

            except json.JSONDecodeError as e:
                logger.warning(
                    f"⚠️ Файл БЗ повреждён ({e}). Создаём новую базу."
                )
                self._kb = self._empty_kb()
                await self._save_local()
        else:
            logger.warning(
                f"⚠️ Локальный файл БЗ не найден: {path}. "
                f"Создаём новую базу."
            )
            self._kb = self._empty_kb()
            await self._save_local()

    def _empty_kb(self) -> dict:
        """Возвращает структуру пустой базы знаний."""
        return {
            "version": "1.0.0",
            "last_updated": "",
            "entries": [],
            "categories": [
                "Легковые автомобили",
                "Грузовые автомобили",
                "Коды неисправностей",
                "Электрика и электроника",
                "Двигатель и топливная система",
                "Трансмиссия",
                "ABS, ESP и SRS",
                "CAN и J1939",
                "ГБО",
                "Общие вопросы"
            ],
            "pending_learning": []
        }

    async def _save_local(self) -> None:
        """
        Сохраняет текущую базу знаний в локальный JSON-файл.
        Вызывается автоматически после загрузки с GitHub и после изменений.
        """
        path = Path(LOCAL_KB_PATH)

        # Создаём папку если не существует
        path.parent.mkdir(parents=True, exist_ok=True)

        # Записываем JSON с форматированием (indent=2 — отступ 2 пробела)
        # ensure_ascii=False — сохраняем кириллицу как есть (не как \u0441...)
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(self._kb, ensure_ascii=False, indent=2))

    # ==========================================================================
    #  СИНХРОНИЗАЦИЯ С GITHUB
    # ==========================================================================

    async def sync_to_github(self) -> bool:
        """
        Загружает текущую базу знаний на GitHub (PUT-запрос к API).

        GitHub API для обновления файла требует:
        - Содержимое в base64
        - SHA текущей версии файла (для проверки конфликтов)
        - Сообщение коммита

        Возвращает:
            True  — успешно загружено
            False — ошибка
        """
        # Проверяем что GitHub настроен
        if not GITHUB_TOKEN or not GITHUB_REPO:
            logger.warning("GitHub не настроен (нет GITHUB_TOKEN или GITHUB_REPO)")
            return False

        import base64

        # Обновляем время последнего изменения
        self._kb["last_updated"] = datetime.now(timezone.utc).isoformat()

        # Сериализуем базу знаний в JSON-строку
        content_str = json.dumps(self._kb, ensure_ascii=False, indent=2)

        # Кодируем в base64 (требование GitHub API)
        content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("ascii")

        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
        }

        url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"

        # Тело запроса
        payload: dict = {
            "message": f"KB update {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "content": content_b64,    # Файл в base64
            "branch":  GITHUB_BRANCH,
        }

        # SHA обязателен при обновлении существующего файла на GitHub.
        # Если sha неизвестен (например файл был создан напрямую на GitHub)
        # — получаем его отдельным GET-запросом перед PUT.
        if not self._github_sha:
            logger.info("SHA неизвестен — получаем с GitHub перед обновлением...")
            try:
                async with aiohttp.ClientSession() as _s:
                    async with _s.get(
                        url,
                        headers=headers,
                        params={"ref": GITHUB_BRANCH}
                    ) as _r:
                        if _r.status == 200:
                            _d = await _r.json()
                            self._github_sha = _d.get("sha", "")
                            logger.info(f"SHA получен: {self._github_sha[:12]}...")
                        elif _r.status == 404:
                            # Файл не существует — создаём без sha (первый коммит)
                            logger.info("Файл не найден на GitHub — создаём новый")
                        else:
                            logger.warning(f"Не удалось получить SHA: HTTP {_r.status}")
            except Exception as _e:
                logger.warning(f"Ошибка получения SHA: {_e}")

        if self._github_sha:
            payload["sha"] = self._github_sha

        try:
            async with aiohttp.ClientSession() as session:
                async with session.put(url, headers=headers, json=payload) as response:
                    if response.status in (200, 201):
                        # 200 = обновлён, 201 = создан новый файл
                        data = await response.json()
                        # Обновляем SHA после успешной загрузки
                        self._github_sha = data["content"]["sha"]
                        self._last_sync = datetime.now(timezone.utc)
                        # Сохраняем локальную копию
                        await self._save_local()
                        logger.info("✅ База знаний синхронизирована на GitHub")
                        # Дополнительно синхронизируем каталог файлов
                        await self.sync_files_catalog_to_github()
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(
                            f"GitHub API ошибка {response.status}: {error_text}"
                        )
                        return False

        except Exception as e:
            logger.error(f"Ошибка синхронизации с GitHub: {e}")
            return False

    async def sync_files_catalog_to_github(self) -> bool:
        """
        Синхронизирует file_catalog.json на GitHub.
        Вызывается вместе с sync_to_github при каждой синхронизации.
        """
        if not GITHUB_TOKEN or not GITHUB_REPO:
            return False

        import base64
        from pathlib import Path

        catalog_path = Path(__file__).parent / "files_cache" / "file_catalog.json"
        if not catalog_path.exists():
            return True  # Нет каталога — пропускаем

        try:
            content_str = catalog_path.read_text(encoding="utf-8")
            content_b64 = base64.b64encode(content_str.encode()).decode("ascii")
        except Exception as e:
            logger.warning(f"Не удалось прочитать file_catalog.json: {e}")
            return False

        github_file = "files_cache/file_catalog.json"
        url     = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{github_file}"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept":        "application/vnd.github.v3+json",
        }

        # Получаем текущий sha файла каталога на GitHub
        sha = None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers,
                                       params={"ref": GITHUB_BRANCH}) as r:
                    if r.status == 200:
                        d = await r.json()
                        sha = d.get("sha")
        except Exception:
            pass

        payload = {
            "message": f"File catalog update {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "content": content_b64,
            "branch":  GITHUB_BRANCH,
        }
        if sha:
            payload["sha"] = sha

        try:
            async with aiohttp.ClientSession() as session:
                async with session.put(url, headers=headers, json=payload) as r:
                    if r.status in (200, 201):
                        logger.info("✅ file_catalog.json синхронизирован на GitHub")
                        return True
                    else:
                        text = await r.text()
                        logger.warning(f"Ошибка синхронизации каталога файлов: {r.status}: {text[:200]}")
                        return False
        except Exception as e:
            logger.warning(f"Ошибка синхронизации каталога: {e}")
            return False

    async def periodic_sync(self, interval_minutes: int = 60) -> None:
        """
        Фоновая задача периодической синхронизации.

        Запускается при старте системы через asyncio.create_task().
        Бесконечный цикл: ждёт N минут → синхронизирует → снова ждёт.

        Аргументы:
            interval_minutes: интервал между синхронизациями в минутах
        """
        while True:
            # Ждём заданное количество минут
            await asyncio.sleep(interval_minutes * 60)
            # interval_minutes * 60 = перевод минут в секунды

            # Используем Lock чтобы избежать конфликта с другими операциями
            async with self._lock:
                # Скачиваем актуальную версию с GitHub
                await self._load_from_github()
                # Перестраиваем поисковый индекс
                self._rebuild_index()

            logger.info(
                f"🔄 Периодическая синхронизация выполнена "
                f"(следующая через {interval_minutes} мин.)"
            )

    # ==========================================================================
    #  ПОИСКОВЫЙ ИНДЕКС (TF-IDF)
    # ==========================================================================

    def _rebuild_index(self) -> None:
        """
        Перестраивает TF-IDF поисковый индекс из всех записей базы знаний.

        Вызывается:
        - После загрузки базы знаний
        - После добавления/изменения/удаления записей
        - После синхронизации с GitHub

        Индекс нужен для быстрого поиска — без него пришлось бы сравнивать
        каждый запрос с каждой записью "в лоб", что медленно.
        """
        entries = self._kb.get("entries", [])

        # Формируем корпус документов для индексирования
        # Каждый документ = вопрос + ответ + ключевые слова (объединяем в один текст)
        corpus = []
        for entry in entries:
            text = (
                entry.get("question", "") + " " +   # Вопрос
                entry.get("answer", "") + " " +     # Ответ
                " ".join(entry.get("keywords", []))  # Ключевые слова
            )
            corpus.append(_tokenize(text))  # Токенизируем текст

        if corpus:
            # Строим TF-IDF индекс
            self._idf, self._vectors = _build_tfidf(corpus)
        else:
            # Пустая база — пустой индекс
            self._idf = {}
            self._vectors = []

    # ==========================================================================
    #  ПОИСК ПО БАЗЕ ЗНАНИЙ
    # ==========================================================================

    def search(
        self,
        query: str,
        top_k: int = TOP_K_RESULTS,
        scope: Optional[str] = None,
    ) -> list[dict]:
        """
        Семантический поиск по базе знаний.

        Алгоритм:
        1. Токенизируем запрос
        2. Вычисляем TF-IDF вектор запроса
        3. Сравниваем вектор запроса с векторами всех записей (cosine similarity)
        4. Возвращаем top_k самых похожих записей выше порога SIMILARITY_THRESHOLD

        Аргументы:
            query (str): поисковый запрос
            top_k (int): максимальное количество результатов

        Возвращает:
            list: список словарей [{"entry": запись, "score": float}, ...]
                  отсортированных по убыванию релевантности
        """
        # Токенизируем запрос
        query_tokens = _tokenize(query)

        # Если нет токенов или нет индекса — возвращаем пустой список
        if not query_tokens or not self._vectors:
            return []

        # Вычисляем TF-IDF вектор запроса
        total = len(query_tokens) or 1
        tf = Counter(query_tokens)
        query_vector = {
            term: (tf[term] / total) * self._idf.get(term, 1.0)
            for term in query_tokens
        }

        # Сравниваем запрос с каждой записью в индексе
        entries = self._kb.get("entries", [])
        scored_results = []
        normalized_query = " ".join(query.lower().split())

        for i, doc_vector in enumerate(self._vectors):
            entry = entries[i]
            # Старые записи без поля scope считаются общими автомобильными.
            if scope and entry.get("scope", "auto") != scope:
                continue
            score = _cosine_similarity(query_vector, doc_vector)

            # Точные коды и устойчивые фразы важнее разбавленного TF-IDF.
            normalized_question = " ".join(
                entry.get("question", "").lower().split()
            )
            if normalized_query == normalized_question:
                score = 1.0
            else:
                for keyword in entry.get("keywords", []):
                    normalized_keyword = " ".join(keyword.lower().split())
                    if len(normalized_keyword) >= 3 and normalized_keyword in normalized_query:
                        score = max(score, 0.9)

            # Включаем только записи выше порога релевантности
            if score >= SIMILARITY_THRESHOLD:
                scored_results.append({
                    "entry": entry,       # Сама запись из базы знаний
                    "score": score,       # Оценка релевантности (0.0–1.0)
                })

        # Сортируем по убыванию оценки (лучшие результаты первыми)
        scored_results.sort(key=lambda x: x["score"], reverse=True)

        # Возвращаем топ-K результатов
        return scored_results[:top_k]

    def find_best(self, query: str, scope: Optional[str] = None) -> Optional[dict]:
        """
        Находит наиболее подходящую запись в базе знаний.

        Удобная обёртка над search() — возвращает только лучший результат
        или None если ничего не нашли.

        Также увеличивает счётчик использования найденной записи
        (для статистики: какие вопросы задают чаще всего).

        Аргументы:
            query (str): вопрос пользователя

        Возвращает:
            dict — запись из БЗ если найдена (с полями id, question, answer, ...)
            None — если ничего не нашли выше порога
        """
        results = self.search(query, top_k=1, scope=scope)

        if results and results[0]["score"] >= SIMILARITY_THRESHOLD:
            best_entry = results[0]["entry"]

            # Увеличиваем счётчик использования этой записи
            for entry in self._kb.get("entries", []):
                if entry["id"] == best_entry["id"]:
                    entry["usage_count"] = entry.get("usage_count", 0) + 1
                    break

            return best_entry

        # Ничего не нашли выше порога
        return None

    # ==========================================================================
    #  CRUD — СОЗДАНИЕ, ЧТЕНИЕ, ОБНОВЛЕНИЕ, УДАЛЕНИЕ ЗАПИСЕЙ
    # ==========================================================================

    def get_all_entries(self) -> list[dict]:
        """
        Возвращает все записи из базы знаний.

        Возвращает:
            list[dict]: список всех записей
        """
        return self._kb.get("entries", [])

    def get_categories(self) -> list[str]:
        """
        Возвращает список всех категорий.

        Категории используются для классификации записей:
        "Коды ошибок", "Диагностика", "Калибровка" и т.д.

        Возвращает:
            list[str]: список названий категорий
        """
        return self._kb.get("categories", [])

    def get_entry_by_id(self, entry_id: str) -> Optional[dict]:
        """
        Находит запись по её уникальному ID.

        Аргументы:
            entry_id (str): ID записи (например "kb_a1b2c3d4")

        Возвращает:
            dict — запись если найдена
            None — если не найдена
        """
        for entry in self._kb.get("entries", []):
            if entry["id"] == entry_id:
                return entry
        return None

    def add_entry(
        self,
        category: str,    # Категория записи
        question: str,    # Вопрос
        answer: str,      # Ответ
        keywords: list[str],  # Ключевые слова для поиска
        source: str = "admin"  # Кто добавил: "admin", "learning", "manual"
    ) -> dict:
        """
        Добавляет новую запись в базу знаний.

        Автоматически генерирует:
        - Уникальный ID на основе MD5-хэша вопроса
        - Дату создания и обновления

        Аргументы:
            category: категория (должна быть из get_categories())
            question: вопрос
            answer:   ответ
            keywords: список ключевых слов для улучшения поиска
            source:   откуда добавлено ("admin" / "learning" / "manual")

        Возвращает:
            dict: созданная запись
        """
        now = datetime.now(timezone.utc).isoformat()  # Текущее время UTC

        # Генерируем ID: "kb_" + первые 8 символов MD5-хэша вопроса
        # MD5 — алгоритм хэширования, даёт одинаковый результат для одинакового текста
        entry_id = "kb_" + hashlib.md5(question.encode()).hexdigest()[:8]

        # Создаём запись
        entry = {
            "id":          entry_id,
            "category":    category,
            "question":    question,
            "keywords":    keywords,
            "answer":      answer,
            "source":      source,
            "scope":       (
                "lpg"
                if "ГБО" in category.upper() or "ГАЗ" in category.upper()
                else "auto"
            ),
            "created_at":  now,
            "updated_at":  now,
            "usage_count": 0,  # Сколько раз запись была использована в ответах
        }

        # Добавляем в список записей
        self._kb.setdefault("entries", []).append(entry)

        # Перестраиваем индекс с новой записью
        self._rebuild_index()

        logger.info(f"Добавлена запись: {entry_id} — {question[:50]}")
        return entry

    def update_entry(self, entry_id: str, **kwargs) -> bool:
        """
        Обновляет существующую запись по ID.

        **kwargs — произвольные именованные аргументы:
        Например: update_entry("kb_abc", answer="Новый ответ", category="Ошибки")

        Аргументы:
            entry_id: ID записи для обновления
            **kwargs: поля для обновления и их новые значения

        Возвращает:
            True  — успешно обновлено
            False — запись с таким ID не найдена
        """
        for entry in self._kb.get("entries", []):
            if entry["id"] == entry_id:
                # Обновляем переданные поля
                for key, value in kwargs.items():
                    entry[key] = value
                # Обновляем дату изменения
                entry["updated_at"] = datetime.now(timezone.utc).isoformat()
                # Перестраиваем индекс
                self._rebuild_index()
                logger.info(f"Обновлена запись: {entry_id}")
                return True

        logger.warning(f"Запись не найдена для обновления: {entry_id}")
        return False

    def delete_entry(self, entry_id: str) -> bool:
        """
        Удаляет запись из базы знаний по ID.

        Аргументы:
            entry_id: ID записи для удаления

        Возвращает:
            True  — запись найдена и удалена
            False — запись не найдена
        """
        entries = self._kb.get("entries", [])
        original_count = len(entries)

        # Оставляем все записи КРОМЕ той что нужно удалить
        self._kb["entries"] = [e for e in entries if e["id"] != entry_id]

        if len(self._kb["entries"]) < original_count:
            # Запись была удалена — перестраиваем индекс
            self._rebuild_index()
            logger.info(f"Удалена запись: {entry_id}")
            return True

        logger.warning(f"Запись не найдена для удаления: {entry_id}")
        return False

    def add_category(self, category: str) -> None:
        """
        Добавляет новую категорию если её ещё нет.

        Аргументы:
            category: название новой категории
        """
        categories = self._kb.setdefault("categories", [])
        if category not in categories:
            categories.append(category)
            logger.info(f"Добавлена категория: {category}")

    # ==========================================================================
    #  САМООБУЧЕНИЕ — НАКОПЛЕНИЕ ВОПРОСОВ БЕЗ ОТВЕТОВ
    # ==========================================================================

    def add_pending_question(
        self,
        user_id: int,       # Telegram ID пользователя
        username: str,      # @username пользователя
        message_text: str,  # Текст вопроса
        chat_id: int        # ID чата где был задан вопрос
    ) -> None:
        """
        Сохраняет вопрос, на который не нашлось ответа в базе знаний.

        Эти вопросы накапливаются в списке "pending_learning".
        Администратор периодически просматривает их через веб-админку
        или команду /pending и добавляет лучшие в базу знаний.

        Дублирующиеся вопросы (одинаковый текст) не сохраняются.

        Аргументы:
            user_id:      числовой ID пользователя Telegram
            username:     @username (для идентификации)
            message_text: текст заданного вопроса
            chat_id:      ID чата (для возможности ответить туда)
        """
        pending_list = self._kb.setdefault("pending_learning", [])

        # Проверяем на дубликаты — одинаковые вопросы не сохраняем
        for existing in pending_list:
            if existing["message_text"].lower() == message_text.lower():
                return  # Такой вопрос уже есть

        # Создаём запись о вопросе
        pending_entry = {
            # Уникальный ID: хэш от user_id + текста вопроса
            "id":           "pend_" + hashlib.md5(
                                f"{user_id}{message_text}".encode()
                             ).hexdigest()[:8],
            "user_id":      user_id,
            "username":     username,
            "message_text": message_text,
            "chat_id":      chat_id,
            "timestamp":    datetime.now(timezone.utc).isoformat(),
            "status":       "new",     # Статусы: new → reviewed/added/rejected
        }
        pending_list.append(pending_entry)
        logger.info(f"Сохранён вопрос для самообучения: {message_text[:50]}")

    def get_pending(self) -> list[dict]:
        """
        Возвращает все вопросы для самообучения.

        Возвращает:
            list[dict]: список всех pending-записей (все статусы)
        """
        return self._kb.get("pending_learning", [])

    def resolve_pending(self, pending_id: str, status: str) -> bool:
        """
        Изменяет статус вопроса для самообучения.

        Статусы:
        - "new"      — новый, ещё не просмотрен администратором
        - "reviewed" — просмотрен, будет добавлен в БЗ через веб-админку
        - "added"    — добавлен в базу знаний
        - "rejected" — отклонён (нерелевантный вопрос)

        Аргументы:
            pending_id: ID записи
            status:     новый статус

        Возвращает:
            True  — статус успешно изменён
            False — запись не найдена
        """
        for pending in self._kb.get("pending_learning", []):
            if pending["id"] == pending_id:
                pending["status"] = status
                logger.info(f"Статус вопроса {pending_id} изменён на: {status}")
                return True
        return False

    # ==========================================================================
    #  СВОЙСТВА И СТАТИСТИКА
    # ==========================================================================

    @property
    def last_sync(self) -> Optional[datetime]:
        """Время последней успешной синхронизации с GitHub."""
        return self._last_sync

    @property
    def stats(self) -> dict:
        """
        Возвращает статистику базы знаний.

        Возвращает словарь:
        {
            "total_entries": int,    — количество записей
            "pending_new": int,      — количество новых вопросов
            "categories": dict,      — {категория: количество_записей}
            "last_sync": str,        — время последней синхронизации
        }
        """
        entries = self._kb.get("entries", [])

        # Считаем только "новые" pending (ещё не просмотренные)
        pending_new_count = len([
            p for p in self._kb.get("pending_learning", [])
            if p["status"] == "new"
        ])

        # Подсчёт записей по категориям
        category_counts: dict[str, int] = {}
        for entry in entries:
            cat = entry.get("category", "—")
            category_counts[cat] = category_counts.get(cat, 0) + 1

        return {
            "total_entries": len(entries),
            "pending_new":   pending_new_count,
            "categories":    category_counts,
            "last_sync":     (
                self._last_sync.isoformat() if self._last_sync else "—"
            ),
        }
    async def record_feedback(self, question: str, feedback_type: str) -> None:
        """
        Записывает статистику оценок: thanks / clarify / wrong.
        Ищет вопрос в БЗ и обновляет счётчики feedback_stats.
        """
        result = self.find_best(question)
        if not result:
            return
        entry_id = result.get("id")
        for entry in self._kb.get("entries", []):
            if entry.get("id") == entry_id:
                stats = entry.setdefault(
                    "feedback_stats", {"thanks": 0, "clarify": 0, "wrong": 0}
                )
                stats[feedback_type] = stats.get(feedback_type, 0) + 1
                break
        await self._save_local()
        logger.info(f"Feedback: {entry_id} +{feedback_type}")



# ==============================================================================
#  СИНГЛТОН — единственный экземпляр менеджера для всей программы
#
#  Синглтон (Singleton) — паттерн проектирования: создаём объект ОДИН РАЗ
#  и используем его везде. Это гарантирует что у нас одна копия данных.
#  bot.py и admin.py оба импортируют этот объект.
# ==============================================================================
kb_manager = KnowledgeManager()
# Этот объект будет использоваться и в bot.py и в admin.py
# Импорт: from knowledge_manager import kb_manager
