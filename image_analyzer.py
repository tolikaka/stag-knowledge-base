# ==============================================================================
#  image_analyzer.py  —  Анализ автомобильных диагностических изображений
# ==============================================================================
#
#  ЧТО ДЕЛАЕТ ЭТОТ ФАЙЛ:
#
#  Задача 1 — OCR (распознавание текста на фото):
#    Когда пользователь присылает ФОТОГРАФИЮ экрана программы STAG с ошибкой,
#    бот должен:
#      1. Скачать фото из Telegram
#      2. Распознать текст на фото (например: "Error E-04", "давление 0.3 bar")
#      3. Найти объяснение ошибки в базе знаний
#      4. Если не найдено — спросить Claude AI
#
#  Задача 2 — Визуальный поиск деталей ГБО:
#    Когда пользователь присылает ФОТОГРАФИЮ детали (блок управления, редуктор,
#    форсунка и т.д.), бот должен:
#      1. Отправить фото в Claude Vision API (Claude умеет "видеть" изображения)
#      2. Claude определяет: марку, модель, производителя, назначение
#      3. Дополнительно ищет информацию в базе знаний по найденным названиям
#
#  ТЕХНОЛОГИИ:
#    - Claude Vision (claude-opus-4-5): встроенная функция "видения" изображений
#      Это основной метод — не нужно устанавливать дополнительные программы!
#      Claude сам распознаёт текст (OCR) и определяет объекты на фото.
#
#    - pytesseract (опционально): классический OCR-движок Tesseract
#      Используется как резервный вариант если Claude Vision недоступен.
#      Требует отдельной установки (инструкция ниже в README).
#
#    - Pillow (PIL): библиотека для обработки изображений в Python
#      Используется для конвертации форматов, изменения размера и т.д.
#
#  ЗАВИСИМОСТИ:
#    pip install Pillow                    — обработка изображений
#    pip install pytesseract               — Python-обёртка для Tesseract OCR
#    Tesseract OCR (отдельная программа)  — движок распознавания текста
#
# ==============================================================================

# --- Стандартные библиотеки ---
import asyncio   # Не блокировать Telegram во время запросов к Vision API
import io        # Работа с байтовыми потоками (для изображений в памяти)
import re        # Регулярные выражения (для поиска кодов ошибок в тексте)
import base64    # Кодирование в base64 (формат для передачи изображений в API)
import logging   # Журнал событий и ошибок
import os        # Работа с операционной системой
from typing import Optional  # Типы: Optional[X] = X или None

# --- Библиотека для работы с изображениями ---
# Pillow (PIL) — самая популярная библиотека изображений для Python
# Поддерживает: JPEG, PNG, BMP, TIFF, WebP и многие другие форматы
try:
    from PIL import Image          # Основной класс изображения
    from PIL import ImageEnhance   # Улучшение качества (контраст, яркость)
    from PIL import ImageFilter    # Фильтры (резкость, размытие и т.д.)
    PIL_AVAILABLE = True
    logging.getLogger(__name__).info("✅ Pillow (PIL) доступен")
except ImportError:
    PIL_AVAILABLE = False
    logging.getLogger(__name__).warning(
        "⚠️ Pillow не установлен. Установите: pip install Pillow"
    )

# --- Tesseract OCR (резервный движок распознавания текста) ---
# pytesseract — Python-обёртка для программы Tesseract OCR от Google.
# Tesseract — один из лучших бесплатных OCR-движков, поддерживает 100+ языков.
# ВАЖНО: pytesseract — это только Python-обёртка.
#         Сам Tesseract нужно установить ОТДЕЛЬНО как программу!
try:
    import pytesseract
    TESSERACT_AVAILABLE = True
    logging.getLogger(__name__).info("✅ pytesseract доступен")
except ImportError:
    TESSERACT_AVAILABLE = False
    logging.getLogger(__name__).info(
        "ℹ️ pytesseract не установлен (необязательно). "
        "Используется Claude Vision."
    )

# --- HTTP-клиент для скачивания изображений ---
import aiohttp  # Асинхронный HTTP-клиент

# --- Клиент Anthropic (Claude AI) ---
from anthropic import Anthropic  # Клиент для Claude API

logger = logging.getLogger(__name__)

# ==============================================================================
#  LANG_INSTRUCTION — инструкции языка ответа.
#  Определены здесь, а не импортируются из bot.py, чтобы избежать
#  циклического импорта и ошибки "No module named 'bot.bot'" на Windows.
# ==============================================================================
_LANG_INSTRUCTION: dict[str, str] = {
    "ru": "Отвечай ТОЛЬКО на русском языке, кириллицей.",
    "uz_cyrillic": "Фақат ўзбек тилида жавоб бер, кирилл ёзувида.",
    "uz_latin": "Faqat o'zbek tilida javob ber, lotin yozuvida.",
    "ru_translit": (
        "Вопрос написан латиницей-транслитом. "
        "Отвечай на русском языке латиницей-транслитом."
    ),
}


# ==============================================================================
#  ЗАГРУЗКА КОНФИГУРАЦИИ
# ==============================================================================
try:
    from config import ANTHROPIC_API_KEY
except ImportError:
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Создаём клиент Claude AI
anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)

# ==============================================================================
#  КОНСТАНТЫ И НАСТРОЙКИ
# ==============================================================================

# Максимальный размер изображения для отправки в API (в пикселях)
# Большие изображения увеличивают стоимость запроса, но улучшают качество OCR
MAX_IMAGE_SIZE = (1920, 1080)  # Full HD — оптимальный баланс качества и стоимости

# Пути к Tesseract на разных ОС (резервный вариант)
TESSERACT_PATHS_WINDOWS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    r"C:\Users\{}\AppData\Local\Tesseract-OCR\tesseract.exe".format(
        os.environ.get("USERNAME", "User")
    ),
]

# Языки для Tesseract OCR
# "rus" — русский, "eng" — английский, "ukr" — украинский
# "uzb" — узбекский (нужен отдельный языковой пакет)
TESSERACT_LANGUAGES = "rus+eng"

# Паттерн для кодов OBD-II, UDS, ГБО и грузовых SPN/FMI.
ERROR_CODE_PATTERN = re.compile(
    r"\b(?:[PBCU][0-9A-F]{4}|E-?\d{1,3}|ERR(?:OR)?\s*\d{1,3}|"
    r"SPN\s*\d+(?:\s+FMI\s*\d+)?)\b",
    re.IGNORECASE | re.UNICODE,
)

# Ключевые слова для определения диагностического скриншота
# (а не деталь/блок управления)
SCREENSHOT_KEYWORDS = [
    "stag", "error", "ошибка", "давление", "pressure", "температура",
    "temperature", "rpm", "обороты", "correction", "коррекция",
    "injector", "инжектор", "calibration", "калибровка", "dtc", "obd",
    "freeze frame", "data stream", "spn", "fmi", "j1939", "bar", "бар",
    "°c", "lambda", "лямбда", "voltage", "напряжение",
]

# ==============================================================================
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================================================================

def setup_tesseract() -> bool:
    """
    Настраивает путь к программе Tesseract OCR (только для Windows).

    Tesseract — отдельная программа (не Python-пакет). После её установки
    нужно указать Python где она находится.

    Возвращает:
        True  — Tesseract найден и настроен
        False — Tesseract не найден (будем использовать Claude Vision)
    """
    if not TESSERACT_AVAILABLE:
        return False  # pytesseract не установлен — нечего настраивать

    # Пробуем найти Tesseract в стандартных местах установки Windows
    for path in TESSERACT_PATHS_WINDOWS:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            logger.info(f"✅ Tesseract найден: {path}")
            return True

    # Tesseract не найден в стандартных папках
    logger.warning(
        "⚠️ Tesseract не найден. "
        "Скачайте с: https://github.com/UB-Mannheim/tesseract/wiki\n"
        "Или используется Claude Vision (работает без Tesseract)."
    )
    return False


def preprocess_image_for_ocr(image: "Image.Image") -> "Image.Image":
    """
    Улучшает качество изображения для лучшего распознавания текста.

    OCR работает лучше когда:
    - Изображение чёрно-белое (grayscale)
    - Высокий контраст (тёмный текст на светлом фоне)
    - Убраны мелкие шумы

    Аргументы:
        image: объект PIL Image

    Возвращает:
        PIL Image: обработанное изображение
    """
    if not PIL_AVAILABLE:
        return image

    # Шаг 1: Конвертируем в оттенки серого
    # RGB (цветное) → L (grayscale, 256 градаций серого)
    img = image.convert("L")

    # Шаг 2: Увеличиваем контраст (делаем текст чётче)
    # Значение 2.0 = двойной контраст (1.0 = без изменений)
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0)

    # Шаг 3: Применяем фильтр резкости
    # SHARPEN делает края букв более чёткими
    img = img.filter(ImageFilter.SHARPEN)

    return img


def image_to_base64(image_bytes: bytes, format: str = "JPEG") -> str:
    """
    Конвертирует байты изображения в строку base64.

    Base64 — способ кодирования бинарных данных (изображений) в текст.
    Используется для передачи изображений в HTTP API (JSON не поддерживает
    бинарные данные напрямую).

    Аргументы:
        image_bytes: байты изображения (JPEG, PNG и т.д.)
        format:      формат изображения

    Возвращает:
        str: строка base64
    """
    if PIL_AVAILABLE:
        # Открываем изображение через PIL
        img = Image.open(io.BytesIO(image_bytes))

        # Изменяем размер если изображение слишком большое
        # thumbnail() — пропорциональное уменьшение (не обрезает)
        if img.size[0] > MAX_IMAGE_SIZE[0] or img.size[1] > MAX_IMAGE_SIZE[1]:
            img.thumbnail(MAX_IMAGE_SIZE, Image.Resampling.LANCZOS)
            # LANCZOS — алгоритм изменения размера с высоким качеством

        # Конвертируем обратно в байты
        buffer = io.BytesIO()
        # JPEG для экономии размера, quality=90 — высокое качество
        if img.mode in ("RGBA", "P"):
            # PNG с прозрачностью → конвертируем в RGB перед сохранением в JPEG
            img = img.convert("RGB")
        img.save(buffer, format=format, quality=90)
        image_bytes = buffer.getvalue()

    # Кодируем байты в base64 и возвращаем строку
    return base64.b64encode(image_bytes).decode("utf-8")


def is_likely_screenshot(text: str) -> bool:
    """
    Определяет: текст похож на скриншот программы STAG (с кодами ошибок)
    или это описание физической детали?

    Используется для выбора типа анализа:
    - Если скриншот → ищем коды ошибок и объясняем
    - Если деталь → определяем марку/модель

    Аргументы:
        text: распознанный текст с изображения

    Возвращает:
        True  — похоже на скриншот программы
        False — скорее всего фото детали или другое
    """
    text_lower = text.lower()

    # Считаем сколько ключевых слов из программы STAG найдено в тексте
    matches = sum(
        1 for keyword in SCREENSHOT_KEYWORDS
        if keyword in text_lower
    )

    # Если найдено 2+ ключевых слова — скорее всего скриншот
    return matches >= 2


def extract_error_codes(text: str) -> list[str]:
    """
    Извлекает все коды ошибок STAG из текста.

    Ищет паттерны: E-04, ERR 12, Error 21, Ошибка 3 и т.д.

    Аргументы:
        text: текст (распознанный с изображения или введённый вручную)

    Возвращает:
        list[str]: список найденных кодов ошибок (могут быть дубликаты)

    Пример:
        extract_error_codes("Система обнаружила E-04 и E-12")
        → ["E-04", "E-12"]
    """
    # findall() — возвращает список ВСЕХ совпадений
    codes = ERROR_CODE_PATTERN.findall(text)

    # Нормализуем формат: убираем лишние пробелы, приводим к верхнему регистру
    normalized = []
    for code in codes:
        code = code.strip().upper()
        # Добавляем дефис если его нет: "E04" → "E-04"
        if re.match(r"^E\d", code):
            code = "E-" + code[1:]
        normalized.append(code)

    # Убираем дубликаты сохраняя порядок
    seen = set()
    unique_codes = []
    for code in normalized:
        if code not in seen:
            seen.add(code)
            unique_codes.append(code)

    return unique_codes


# ==============================================================================
#  ГЛАВНЫЙ КЛАСС АНАЛИЗАТОРА ИЗОБРАЖЕНИЙ
# ==============================================================================

class ImageAnalyzer:
    """
    Анализирует изображения из Telegram.

    Поддерживает два режима:
    1. OCR — распознавание текста (скриншоты программы STAG с ошибками)
    2. Идентификация деталей — определение марки/модели ГБО-оборудования
    """

    def __init__(self):
        """Инициализация: настройка Tesseract если доступен."""
        self.tesseract_ready = setup_tesseract()
        logger.info(
            f"ImageAnalyzer инициализирован. "
            f"Tesseract: {'✅' if self.tesseract_ready else '❌ (используем Claude Vision)'}"
        )

    # ==========================================================================
    #  МЕТОД 1: ПОЛНЫЙ АНАЛИЗ ИЗОБРАЖЕНИЯ
    #  Главная точка входа — определяет тип изображения и вызывает нужный анализ
    # ==========================================================================

    async def analyze_photo(
        self,
        photo_bytes: bytes,   # Байты изображения скачанного из Telegram
        lang: str = "ru",     # Язык для ответа ('ru', 'uz_latin', 'uz_cyrillic', ...)
        user_question: str = ""  # Сопроводительный текст пользователя если есть
    ) -> dict:
        """
        Главный метод анализа фотографии.

        Алгоритм:
        1. Конвертируем в base64 для отправки в Claude Vision
        2. Просим Claude описать что на фото (скриншот или деталь)
        3. Если скриншот → ищем ошибки и объясняем
        4. Если деталь → определяем марку/модель

        Аргументы:
            photo_bytes:   байты скачанного изображения
            lang:          язык ответа
            user_question: вопрос пользователя к фото (если написал)

        Возвращает:
            dict: {
                "type":     "screenshot" | "part" | "unknown",
                "answer":   str — текст ответа для пользователя,
                "details":  dict — дополнительные данные
            }
        """
        logger.info(
            f"Начинаем анализ изображения "
            f"({len(photo_bytes)} байт, язык={lang})"
        )

        # Шаг 1: Конвертируем изображение в base64
        try:
            image_b64 = image_to_base64(photo_bytes)
        except Exception as e:
            logger.error(f"Ошибка конвертации изображения: {e}")
            return {
                "type": "error",
                "answer": "❌ Не удалось обработать изображение. "
                          "Попробуйте отправить в другом формате (JPEG/PNG).",
                "details": {}
            }

        # Шаг 2: Первичный анализ — что на фото?
        photo_type = await self._classify_image(image_b64, user_question)
        logger.info(f"Тип изображения определён: {photo_type}")

        # Шаг 3: Специализированный анализ в зависимости от типа
        if photo_type == "screenshot":
            # Скриншот программы STAG — ищем коды ошибок
            return await self._analyze_screenshot(image_b64, lang, user_question)
        elif photo_type == "part":
            # Фото детали ГБО — определяем марку/модель
            return await self._analyze_part(image_b64, lang, user_question)
        else:
            # Неизвестный тип — общий анализ
            return await self._analyze_general(image_b64, lang, user_question)

    # ==========================================================================
    #  КЛАССИФИКАЦИЯ: ЧТО НА ФОТО?
    # ==========================================================================

    async def _classify_image(
        self,
        image_b64: str,
        user_question: str = ""
    ) -> str:
        """
        Определяет тип изображения: скриншот программы или фото детали.

        Отправляет изображение в Claude Vision и просит классифицировать.

        Аргументы:
            image_b64:     изображение в base64
            user_question: вопрос пользователя (подсказка для классификации)

        Возвращает:
            "screenshot" — скриншот диагностической программы
            "part"       — фото автомобильной детали или компонента ГБО
            "unknown"    — что-то другое
        """
        # Подсказка от пользователя (если есть) помогает точнее классифицировать
        user_hint = ""
        if user_question:
            user_hint = f'\nПользователь написал: "{user_question}"'

        try:
            response = await asyncio.to_thread(
                anthropic_client.messages.create,
                model="claude-opus-4-5",
                max_tokens=100,  # Нам нужен только короткий ответ
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            # Блок изображения — Claude "видит" его
                            "type": "image",
                            "source": {
                                "type":       "base64",
                                "media_type": "image/jpeg",
                                "data":       image_b64,
                            },
                        },
                        {
                            # Текстовый вопрос
                            "type": "text",
                            "text": (
                                f"Определи что изображено на фото:{user_hint}\n\n"
                                "Отвечай ТОЛЬКО одним словом:\n"
                                "- 'screenshot' — если это скриншот/снимок экрана "
                                "диагностической программы/сканера, коды ошибок, "
                                "параметры давления/температуры)\n"
                                "- 'part' — если это фото физической детали "
                                "автомобиля или ГБО (ЭБУ, датчик, форсунка, "
                                "редуктор, клапан, разъём, узел двигателя)\n"
                                "- 'unknown' — если ни то ни другое"
                            ),
                        },
                    ],
                }],
            )

            # Извлекаем ответ и убираем лишние символы
            result = response.content[0].text.strip().lower()

            # Проверяем что ответ корректный
            if "screenshot" in result:
                return "screenshot"
            elif "part" in result:
                return "part"
            else:
                return "unknown"

        except Exception as e:
            logger.error(f"Ошибка классификации изображения: {e}")
            return "unknown"

    # ==========================================================================
    #  АНАЛИЗ СКРИНШОТА ПРОГРАММЫ (OCR + ПОИСК ОШИБОК)
    # ==========================================================================

    async def _analyze_screenshot(
        self,
        image_b64: str,
        lang: str,
        user_question: str = ""
    ) -> dict:
        """
        Анализирует скриншот автомобильной диагностической программы.

        Шаги:
        1. OCR через Claude Vision — распознаём ВЕСЬ текст на экране
        2. Ищем коды ошибок в распознанном тексте
        3. Для каждого кода — ищем объяснение в базе знаний
        4. Если не найдено в БЗ — просим Claude объяснить

        Аргументы:
            image_b64:     скриншот в base64
            lang:          язык ответа
            user_question: уточняющий вопрос пользователя

        Возвращает:
            dict с полями type, answer, details
        """
        # Импортируем здесь чтобы избежать циклических импортов
        from knowledge_manager import kb_manager

        # Инструкция по языку для Claude
        lang_note = _LANG_INSTRUCTION.get(lang, _LANG_INSTRUCTION["ru"])

        logger.info("Выполняем OCR скриншота через Claude Vision...")

        # ── Шаг 1: OCR — читаем весь текст со скриншота ──────────────────────
        try:
            ocr_response = await asyncio.to_thread(
                anthropic_client.messages.create,
                model="claude-opus-4-5",
                max_tokens=600,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type":       "base64",
                                "media_type": "image/jpeg",
                                "data":       image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Это скриншот автомобильной диагностической "
                                "программы, сканера или ПО для ГБО.\n\n"
                                "Выполни OCR — перечисли ВЕСЬ видимый текст на "
                                "экране, включая:\n"
                                "- Коды ошибок (E-01, E-04, ERR и т.д.)\n"
                                "- Значения параметров (давление, температура, "
                                "  обороты, коррекция)\n"
                                "- Названия разделов и кнопок\n"
                                "- Любые сообщения и предупреждения\n\n"
                                "Формат: просто перечисли текст, "
                                "ничего не объясняй."
                            ),
                        },
                    ],
                }],
            )
            recognized_text = ocr_response.content[0].text.strip()
            logger.info(
                f"OCR выполнен, распознано {len(recognized_text)} символов"
            )

        except Exception as e:
            logger.error(f"Ошибка OCR: {e}")
            recognized_text = ""

        # ── Шаг 2: Ищем коды ошибок в распознанном тексте ───────────────────
        error_codes = extract_error_codes(recognized_text)
        logger.info(
            f"Найдено кодов ошибок: {len(error_codes)} → {error_codes}"
        )

        # ── Шаг 3: Для каждого кода ищем объяснение ──────────────────────────
        explanations = []

        for code in error_codes:
            # Сначала ищем в базе знаний
            query = f"ошибка {code} причина устранение"
            kb_result = kb_manager.find_best(query)

            if kb_result:
                explanations.append({
                    "code":   code,
                    "source": "kb",
                    "text":   kb_result["answer"],
                })
                logger.info(f"Ошибка {code}: найдено в БЗ")
            else:
                # Не нашли в БЗ — добавим в список для AI-объяснения
                explanations.append({
                    "code":   code,
                    "source": "pending_ai",  # Объясним через AI ниже
                    "text":   "",
                })
                logger.info(f"Ошибка {code}: не найдено в БЗ, идём к AI")

        # ── Шаг 4: Отправляем в Claude для полного анализа ───────────────────
        # Составляем контекст из распознанного текста и найденных объяснений
        kb_context = ""
        for expl in explanations:
            if expl["source"] == "kb" and expl["text"]:
                kb_context += (
                    f"\n\nИз базы знаний для {expl['code']}:\n{expl['text']}"
                )

        user_q_part = ""
        if user_question:
            user_q_part = f"\n\nВопрос пользователя: {user_question}"

        try:
            analysis_response = await asyncio.to_thread(
                anthropic_client.messages.create,
                model="claude-opus-4-5",
                max_tokens=1000,
                system=(
                    "Ты — технический ассистент по диагностике легковых и "
                    "грузовых автомобилей и ГБО. Анализируй диагностический "
                    "скриншот, не угадывай маркозависимые коды и давай "
                    "проверяемые рекомендации.\n"
                    f"{lang_note}"
                ),
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type":       "base64",
                                "media_type": "image/jpeg",
                                "data":       image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                f"Распознанный текст со скриншота:\n"
                                f"{recognized_text}\n\n"
                                f"Найденные коды ошибок: "
                                f"{', '.join(error_codes) if error_codes else 'не найдено'}"
                                f"{kb_context}"
                                f"{user_q_part}\n\n"
                                "ВАЖНО: Ответ адресован квалифицированному автодиагносту/специалисту.\n"
                                "Используй профессиональную техническую терминологию.\n"
                                "НЕ объясняй базовые вещи — специалист их знает.\n\n"
                                "Структура ответа (строго соблюдай):\n"
                                "1. СНАЧАЛА — краткий вывод/диагноз (1-2 строки максимум)\n"
                                "2. Коды ошибок и их техническое значение\n"
                                "3. Вероятные причины (для специалиста)\n"
                                "4. Рекомендуемые действия по диагностике/устранению\n"
                                "5. Аномальные параметры если есть\n\n"
                                "НЕ начинай с описания что ты видишь на скриншоте — "
                                "начинай сразу с диагноза."
                            ),
                        },
                    ],
                }],
            )

            final_answer = analysis_response.content[0].text.strip()

        except Exception as e:
            logger.error(f"Ошибка анализа скриншота: {e}")
            # Если AI недоступен — формируем ответ из того что нашли в БЗ
            if explanations:
                lines = ["📋 *Найденные ошибки:*\n"]
                for expl in explanations:
                    if expl["source"] == "kb":
                        lines.append(
                            f"*{expl['code']}:*\n{expl['text']}\n"
                        )
                final_answer = "\n".join(lines)
            else:
                final_answer = (
                    "❌ Не удалось проанализировать скриншот. "
                    "Попробуйте ещё раз или опишите проблему текстом."
                )

        # Формируем итоговый ответ с заголовком
        answer = (
            f"🖥️ *Анализ диагностического скриншота:*\n\n"
            f"{final_answer}"
        )

        # Детали OCR возвращаем отдельно — бот сам решит показывать их или нет.
        # В bot.py они будут спрятаны в дополнительный вложенный спойлер.
        ocr_details = ""
        if recognized_text:
            ocr_details += f"📝 Распознанный текст:\n{recognized_text[:300]}"
            if len(recognized_text) > 300:
                ocr_details += "..."
        if error_codes:
            ocr_details += f"\n\n🔢 Найденные коды: {', '.join(error_codes)}"

        return {
            "type":       "screenshot",
            "answer":     answer,
            "ocr_details": ocr_details,
            "details": {
                "recognized_text": recognized_text,
                "error_codes":     error_codes,
                "explanations":    explanations,
            },
        }

    # ==========================================================================
    #  АНАЛИЗ АВТОМОБИЛЬНОЙ ДЕТАЛИ / КОМПОНЕНТА ГБО
    # ==========================================================================

    async def _analyze_part(
        self,
        image_b64: str,
        lang: str,
        user_question: str = ""
    ) -> dict:
        """
        Анализирует фото автомобильной детали/компонента ГБО.

        ДВА ВЫЗОВА:
        1. Идентификация — что изображено на фото (технические данные)
        2. Прямой ответ — что именно просит пользователь (ПО, ссылки, инструкция)

        Возвращает:
            answer      — прямой ответ на вопрос (показывается сразу)
            ocr_details — детали идентификации (в expandable blockquote)
        """
        from knowledge_manager import kb_manager
        lang_note = _LANG_INSTRUCTION.get(lang, _LANG_INSTRUCTION["ru"])
        user_q_part = f"\n\nВопрос специалиста: {user_question}" if user_question else ""

        logger.info("Анализируем деталь: шаг 1 — идентификация...")

        # ── ВЫЗОВ 1: Идентификация детали ────────────────────────────────────
        # Только технические данные — без рекомендаций и ответа на вопрос
        identification_text = ""
        try:
            id_response = await asyncio.to_thread(
                anthropic_client.messages.create,
                model="claude-opus-4-5",
                max_tokens=600,
                system=(
                    "Ты — технический эксперт по автомобилям и ГБО. "
                    "Задача: идентифицировать деталь на фото. "
                    "Дай ТОЛЬКО технические данные — кратко и точно.\n"
                    f"{lang_note}"
                ),
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type":       "base64",
                                "media_type": "image/jpeg",
                                "data":       image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Идентифицируй деталь на фото. Укажи ТОЛЬКО:\n"
                                "1. Тип устройства (ЭБУ/редуктор/датчик/форсунка/...)\n"
                                "2. Производитель и бренд (по логотипу/надписям)\n"
                                "3. Модель и серия (если видно)\n"
                                "4. Поколение/тип (4G, OBD, sequential...)\n"
                                "5. Все надписи и маркировки с фото ДОСЛОВНО\n\n"
                                "Формат: короткие строки, без лишних слов."
                            ),
                        },
                    ],
                }],
            )
            identification_text = id_response.content[0].text.strip()
            logger.info("Идентификация детали выполнена")
        except Exception as e:
            logger.error(f"Ошибка идентификации: {e}")
            identification_text = "Не удалось определить деталь по изображению."

        # ── Поиск в базе знаний ───────────────────────────────────────────────
        # Ищем по идентифицированным терминам — НО только релевантные!
        # Проверяем что результат БЗ действительно связан с вопросом
        kb_supplement = ""
        search_terms = []
        for term in ["редуктор", "инжектор", "форсунка", "блок управления",
                     "датчик давления", "клапан", "STAG", "Lovato", "BRC",
                     "Octron", "программа", "software", "ПО", "дастур"]:
            if term.lower() in identification_text.lower():
                search_terms.append(term)

        if search_terms and user_question:
            # Ищем только если вопрос связан с тем что нашли
            kb_query = f"{user_question} {' '.join(search_terms[:2])}"
            kb_result = kb_manager.find_best(kb_query)
            # Добавляем в ocr_details только если результат релевантен
            if kb_result and any(
                t.lower() in kb_result.get("answer","").lower()
                for t in search_terms
            ):
                kb_supplement = (
                    f"\n\n📚 Из базы знаний:\n{kb_result['answer'][:300]}..."
                    if len(kb_result.get("answer","")) > 300
                    else f"\n\n📚 Из базы знаний:\n{kb_result.get('answer','')}"
                )

        # ── ВЫЗОВ 2: Прямой ответ на вопрос пользователя ─────────────────────
        # Используем идентификацию как контекст
        # Отвечаем ТОЛЬКО на то что спросили — кратко и конкретно
        logger.info("Анализируем деталь: шаг 2 — ответ на вопрос...")
        direct_answer = ""
        if user_question:
            try:
                ans_response = await asyncio.to_thread(
                    anthropic_client.messages.create,
                    model="claude-opus-4-5",
                    max_tokens=800,
                    system=(
                        "Ты — технический консультант для квалифицированных специалистов. "
                        "Отвечай КОНКРЕТНО и ПРАКТИЧНО. "
                        "Не объясняй базовые вещи — специалист их знает.\n\n"
                        "ПРАВИЛА ОТВЕТА:\n"
                        "1. ПЕРВАЯ строка = прямой ответ на вопрос (файл/ссылка/контакт)\n"
                        "2. Если просят программу/ПО — дай конкретные ссылки для скачивания\n"
                        "3. Если официальный сайт недоступен — альтернативные источники\n"
                        "4. Контакты дилеров только если нет других вариантов\n"
                        "5. НЕ добавляй 'обратитесь к специалисту' — это уже специалист\n"
                        "6. Проверяй реальность Telegram-каналов перед упоминанием\n"
                        f"{lang_note}"
                    ),
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type":       "base64",
                                    "media_type": "image/jpeg",
                                    "data":       image_b64,
                                },
                            },
                            {
                                "type": "text",
                                "text": (
                                    f"На фото: {identification_text[:300]}\n\n"
                                    f"Вопрос специалиста: {user_question}\n\n"
                                    "Дай прямой практический ответ. "
                                    "Начни с конкретного решения (файл/ссылка/адрес). "
                                    "Если запрашивают программу — дай прямую ссылку для скачивания. "
                                    "Если нет прямой ссылки — проверенные альтернативы."
                                ),
                            },
                        ],
                    }],
                )
                direct_answer = ans_response.content[0].text.strip()
                logger.info("Прямой ответ на вопрос сформирован")
            except Exception as e:
                logger.error(f"Ошибка формирования ответа: {e}")

        # ── Сборка результата ─────────────────────────────────────────────────
        # answer      = ПРЯМОЙ ОТВЕТ (показывается сразу, первым)
        # ocr_details = ДЕТАЛИ ИДЕНТИФИКАЦИИ (expandable blockquote, после ответа)
        if direct_answer:
            answer = direct_answer
        else:
            # Если вопроса не было — первые 2 строки идентификации
            id_lines = identification_text.splitlines()
            summary = "\n".join(l for l in id_lines[:4] if l.strip())
            answer = f"🔍 {summary}" if summary else identification_text

        # Детали идентификации — всегда в ocr_details (не в answer!)
        ocr_details = identification_text
        if kb_supplement:
            ocr_details += kb_supplement

        return {
            "type":        "part",
            "answer":      answer,
            "ocr_details": ocr_details,
            "details": {
                "identification": identification_text,
                "search_terms":   search_terms,
            },
        }


    # ==========================================================================
    #  АНАЛИЗ НЕОПОЗНАННОГО ИЗОБРАЖЕНИЯ
    # ==========================================================================

    async def _analyze_general(
        self,
        image_b64: str,
        lang: str,
        user_question: str = ""
    ) -> dict:
        """
        Общий анализ изображения когда не удалось определить тип.

        Просит Claude описать что на фото и связать с тематикой ГБО/STAG.

        Аргументы:
            image_b64:     изображение в base64
            lang:          язык ответа
            user_question: вопрос пользователя

        Возвращает:
            dict с полями type, answer, details
        """
        lang_note = _LANG_INSTRUCTION.get(lang, _LANG_INSTRUCTION["ru"])

        logger.info("Выполняем общий анализ изображения...")

        user_q_part = ""
        if user_question:
            user_q_part = f"\n\nВопрос пользователя: {user_question}"

        try:
            response = await asyncio.to_thread(
                anthropic_client.messages.create,
                model="claude-opus-4-5",
                max_tokens=800,
                system=(
                    "Ты — технический ассистент по диагностике легковых и "
                    "грузовых автомобилей и ГБО. Анализируй изображения "
                    "деталей, схем, экранов сканера и следов неисправностей.\n"
                    f"{lang_note}"
                ),
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type":       "base64",
                                "media_type": "image/jpeg",
                                "data":       image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Опиши что изображено на фото и как это "
                                "связано с диагностикой или ремонтом автомобиля "
                                "либо с ГБО.\n"
                                "Если можешь помочь с техническим вопросом — "
                                f"помоги.{user_q_part}"
                            ),
                        },
                    ],
                }],
            )

            answer_text = response.content[0].text.strip()

        except Exception as e:
            logger.error(f"Ошибка общего анализа: {e}")
            answer_text = (
                "❌ Не удалось проанализировать изображение. "
                "Попробуйте описать вопрос текстом."
            )

        return {
            "type":    "unknown",
            "answer":  f"📷 *Анализ изображения:*\n\n{answer_text}",
            "details": {},
        }

    # ==========================================================================
    #  РЕЗЕРВНЫЙ OCR ЧЕРЕЗ TESSERACT (если Claude Vision недоступен)
    # ==========================================================================

    def ocr_with_tesseract(self, image_bytes: bytes) -> str:
        """
        Распознаёт текст на изображении через Tesseract OCR.

        Используется как РЕЗЕРВНЫЙ вариант если Claude Vision недоступен
        (проблемы с интернетом, исчерпан лимит API и т.д.).

        Требует:
        - Установленный Tesseract (программа)
        - Установленный pytesseract (Python-пакет)
        - Языковые пакеты: rus, eng

        Аргументы:
            image_bytes: байты изображения

        Возвращает:
            str: распознанный текст или пустую строку при ошибке
        """
        if not TESSERACT_AVAILABLE or not self.tesseract_ready:
            logger.warning("Tesseract недоступен для резервного OCR")
            return ""

        if not PIL_AVAILABLE:
            logger.warning("PIL недоступен для обработки изображения")
            return ""

        try:
            # Открываем изображение
            img = Image.open(io.BytesIO(image_bytes))

            # Улучшаем качество для лучшего распознавания
            img_processed = preprocess_image_for_ocr(img)

            # Конфигурация Tesseract:
            # --oem 3 — LSTM OCR Engine Mode (лучший режим)
            # --psm 6 — Page Segmentation Mode 6: единый блок текста
            config = "--oem 3 --psm 6"

            # Запускаем OCR
            text = pytesseract.image_to_string(
                img_processed,
                lang=TESSERACT_LANGUAGES,
                config=config,
            )

            logger.info(
                f"Tesseract OCR: распознано {len(text)} символов"
            )
            return text.strip()

        except Exception as e:
            logger.error(f"Ошибка Tesseract OCR: {e}")
            return ""


# ==============================================================================
#  СИНГЛТОН — единственный экземпляр анализатора
# ==============================================================================
image_analyzer = ImageAnalyzer()
# Использование: from image_analyzer import image_analyzer
