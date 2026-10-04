# FILE: bot.py | VERSION: 1.2.1 | DATE: 2026-10-04
# ==============================================================================
#  bot.py  —  Главный файл Telegram-бота AI_Diag_UZ («Уста»)
# ==============================================================================
#
#  ЧТО ДЕЛАЕТ ЭТОТ ФАЙЛ:
#  1. Подключается к Telegram и слушает все сообщения в канале/группе
#  2. Реагирует ТОЛЬКО на обращение "Уста" / "Usta" / @cardiagUZ_bot
#  3. Определяет язык вопроса (русский / узбекский кирилл / узбекский латиница
#     / русский транслитом)
#  4. Ищет ответ по цепочке:
#       а) В базе знаний (knowledge_base.json)
#       б) На сайте ac.com.pl (официальный сайт производителя)
#       в) На украинских сайтах о ГБО
#       г) На российских сайтах о ГБО
#       д) На белорусских сайтах о ГБО
#       е) Генерирует ответ через Claude AI (Anthropic)
#  5. Отвечает на том же языке, на котором был задан вопрос
#  6. Если вопрос слишком короткий/непонятный — задаёт уточняющий вопрос
#  7. Предоставляет команды администраторам для управления базой знаний
#
#  ЗАВИСИМОСТИ (устанавливаются через pip):
#    python-telegram-bot  — библиотека для работы с Telegram Bot API
#    anthropic            — библиотека для работы с Claude AI
#    aiohttp              — асинхронные HTTP-запросы (поиск в интернете)
# ==============================================================================

# --- Стандартные библиотеки Python (устанавливать не нужно) ---
import asyncio   # Асинхронное программирование: позволяет боту делать несколько
                 # дел одновременно (отвечать разным пользователям параллельно)
import html      # Декодирование HTML-фрагментов результатов поиска
import logging   # Запись логов (журнала работы) — что происходит, ошибки и т.д.
import os        # Работа с операционной системой: чтение переменных окружения
import re        # Регулярные выражения: поиск паттернов в тексте (для триггеров)
import time      # Таймер ожидания следующего сообщения пользователя
from typing import Optional  # Подсказки типов: Optional[str] = строка или None

# --- Сторонние библиотеки (устанавливаются через pip install) ---
import aiohttp   # Асинхронный HTTP-клиент для запросов в интернет (поиск)
from anthropic import Anthropic  # Клиент для Claude AI от Anthropic

# Компоненты библиотеки python-telegram-bot:
from telegram import (
    Update,                # Объект "обновление" — любое событие в Telegram
    InlineKeyboardButton,  # Кнопка в сообщении (нажимаемая)
    InlineKeyboardMarkup,  # Набор кнопок (сетка кнопок под сообщением)
    Message,               # Объект сообщения в Telegram
)
from telegram.ext import (
    Application,           # Главный объект приложения бота
    CommandHandler,        # Обработчик команд (/start, /help и т.д.)
    MessageHandler,        # Обработчик обычных текстовых сообщений
    CallbackQueryHandler,  # Обработчик нажатий на inline-кнопки
    ContextTypes,          # Типы контекста для обработчиков
    filters,               # Фильтры сообщений (только текст, только группы и т.д.)
)
from telegram.constants import (
    ParseMode,   # Режим форматирования текста (Markdown, HTML)
    ChatAction,  # Действия бота: "печатает...", "загружает файл..." и т.д.
)

# Наш собственный модуль управления базой знаний (файл knowledge_manager.py)
from knowledge_manager import kb_manager

# Менеджер файлового кэша (ПО, документация, прошивки)
try:
    from file_manager import (
        search_file, download_and_cache,
        save_telegram_file_id, get_all_files,
    )
    FILE_MANAGER_AVAILABLE = True
except ImportError as _fm_err:
    FILE_MANAGER_AVAILABLE = False
    logging.getLogger(__name__).warning(
        f"file_manager.py не найден: {_fm_err}. Отправка файлов недоступна."
    )

# Модуль безопасности: rate limiting и blacklist
try:
    from security import (
        rate_check, is_blacklisted, block_user, unblock_user, get_blacklist,
    )
    SECURITY_AVAILABLE = True
except ImportError as _sec_err:
    SECURITY_AVAILABLE = False
    # Заглушки — если security.py не найден, бот работает без защиты
    def rate_check(uid): return (True, "")          # noqa
    def is_blacklisted(uid): return False            # noqa
    def block_user(uid): pass                        # noqa
    def unblock_user(uid): return False              # noqa
    def get_blacklist(): return []                   # noqa

# Модуль анализа изображений (OCR + идентификация деталей ГБО)
# Импортируем с обработкой ошибки — если файл не найден, фото-функции отключатся
try:
    from image_analyzer import image_analyzer
    IMAGE_ANALYSIS_AVAILABLE = True
except ImportError as _img_err:
    IMAGE_ANALYSIS_AVAILABLE = False
    logging.getLogger(__name__).warning(
        f"⚠️ Модуль анализа изображений недоступен: {_img_err}. "
        "Анализ изображений недоступен."
    )

# ==============================================================================
#  НАСТРОЙКА ЛОГИРОВАНИЯ
#  Логи (журнал) помогают понять что делает бот и найти ошибки.
#  Они выводятся в консоль и сохраняются в файл ai_diag_uz.log
# ==============================================================================
logger = logging.getLogger(__name__)
# __name__ — автоматически подставляет имя текущего модуля ("bot")

# ==============================================================================
#  ЗАГРУЗКА КОНФИГУРАЦИИ
#  Пробуем загрузить из файла config.py.
#  Если config.py не найден — читаем из переменных окружения Windows.
#  Переменные окружения можно задать в командной строке или в .env файле.
# ==============================================================================
try:
    # Импортируем настройки из config.py (файл должен быть в той же папке)
    from config import (
        TELEGRAM_BOT_TOKEN,    # Токен бота от @BotFather
        TELEGRAM_CHANNEL_ID,   # Старый параметр одной группы (совместимость)
        TELEGRAM_ADMIN_IDS,    # Список Telegram ID администраторов
        ANTHROPIC_API_KEY,     # Ключ API для Claude AI
        SYNC_INTERVAL_MINUTES, # Интервал синхронизации с GitHub (в минутах)
    )
    try:
        from config import ALLOWED_CHAT_IDS  # Необязательный список групп
    except ImportError:
        ALLOWED_CHAT_IDS = []
    # Если импорт прошёл успешно — config.py найден и все настройки загружены
except ImportError:
    # config.py не найден — читаем из переменных окружения
    # os.environ["KEY"] — обязательная переменная (падаёт с ошибкой если нет)
    # os.environ.get("KEY", "default") — необязательная (возвращает "default")
    TELEGRAM_BOT_TOKEN    = os.environ["TELEGRAM_BOT_TOKEN"]
    TELEGRAM_CHANNEL_ID   = os.environ.get("TELEGRAM_CHANNEL_ID", "")
    TELEGRAM_ADMIN_IDS    = (
        list(map(int, os.environ.get("ADMIN_IDS", "").split(",")))
        if os.environ.get("ADMIN_IDS") else []
    )
    ANTHROPIC_API_KEY     = os.environ["ANTHROPIC_API_KEY"]
    SYNC_INTERVAL_MINUTES = 60  # По умолчанию — синхронизация каждый час
    ALLOWED_CHAT_IDS      = [
        int(value.strip())
        for value in os.environ.get("ALLOWED_CHAT_IDS", "").split(",")
        if value.strip()
    ]

# Пустой список означает: бот работает во всех группах, куда его добавили.

# Создаём клиент для работы с Claude AI.
# api_key — ключ авторизации, получается на console.anthropic.com
anthropic = Anthropic(api_key=ANTHROPIC_API_KEY)

# ==============================================================================
#  ТРИГГЕРЫ — ОБРАЩЕНИЯ К БОТУ
#
#  Бот реагирует ТОЛЬКО когда в сообщении есть одно из этих обращений:
#    "Уста" — кириллица
#    "Usta" — латиница
#    "@cardiagUZ_bot" — прямое упоминание Telegram-бота
#
#  Регулярное выражение (regex) — это шаблон для поиска в тексте.
#  Объяснение паттерна: обращения «Уста/Usta» или @cardiagUZ_bot.
#    \b       — граница слова (чтобы не срабатывало внутри другого слова)
#    usta     — обращение латиницей
#    |        — ИЛИ (альтернатива)
#    уста     — обращение кириллицей
#    re.IGNORECASE — игнорировать регистр (USTA = Usta = usta)
#    re.UNICODE    — правильно работать с кириллицей
# ==============================================================================
# Триггер-слова для обращения к боту.
# Поддерживаемые варианты (регистр не важен):
#   Уста / уста / УСТА   — узбекское "мастер" (кириллица)
#   Усто / усто / УСТО   — вариант написания того же слова (кириллица)
#   Usta / usta / USTA   — узбекский латиница
#   Usto / usto / USTO   — вариант латиницей
#   @cardiagUZ_bot       — прямое упоминание бота
# \b — граница слова: не срабатывает на "густо", "августа", "ustop"
TRIGGER_RE = re.compile(
    r"(?:\b(?:usto|usta|усто|уста)\b|@cardiaguz_bot\b)",
    re.IGNORECASE | re.UNICODE,
)

# Паттерн вступительных фраз — когда пользователь только обращается к боту
# без конкретного вопроса (например просто "Уста" или "Уста, привет")
INTRO_RE = re.compile(
    r"^(?:usto|usta|усто|уста|@cardiaguz_bot)"
    r"(?:[\s,\.!?]*(?:привет|здравствуй|hello|hi|salom|assalom|"
    r"салом|ассалом|мархамат|marhamat)?[\s,\.!?]*)$",
    re.IGNORECASE | re.UNICODE,
)


def contains_trigger(text: str) -> bool:
    """
    Проверяет, содержит ли текст сообщения обращение к боту.

    Аргументы:
        text (str): текст сообщения из Telegram

    Возвращает:
        True  — если найдено «Usta», «Уста» или @cardiagUZ_bot
        False — если обращения нет (бот должен молчать)

    Примеры:
        contains_trigger("Уста, почему не запускается?")       → True
        contains_trigger("Усто, P0420 xatosi nima?")           → True
        contains_trigger("Usta dvigatel troiyt")               → True
        contains_trigger("Usto, помоги разобраться")           → True
        contains_trigger("@cardiagUZ_bot помоги")              → True
        contains_trigger("у меня обычный вопрос")              → False
        contains_trigger("просто проходил мимо")               → False
    """
    return bool(TRIGGER_RE.search(text))
    # TRIGGER_RE.search(text) ищет паттерн в тексте
    # bool() преобразует результат в True/False


def extract_question(text: str) -> str:
    """
    Извлекает собственно вопрос из сообщения — удаляет обращение к боту.

    Например:
        "Уста, двигатель троит на холостых"
         → "двигатель троит на холостых"

        "Usta P0420 xatosi nima degani?"
         → "E-04 xatosi nima degani?"

    Аргументы:
        text (str): исходное сообщение с обращением

    Возвращает:
        str: текст вопроса без обращения к боту
    """
    # Удаляем обращение к боту из текста
    cleaned = TRIGGER_RE.sub("", text)
    # re.sub(паттерн, замена, текст) — заменяет найденное на пустую строку ""

    # Убираем лишние знаки препинания и пробелы в начале строки
    # ^ — начало строки
    # [\s,\.\!\?:;\-]+ — один или более пробелов/запятых/точек/восклицаний и т.д.
    cleaned = re.sub(r"^[\s,\.\!\?:;\-]+", "", cleaned).strip()

    # Если после очистки что-то осталось — возвращаем это
    # Если ничего не осталось (например написали просто "Уста") — возвращаем
    # исходный текст (чтобы бот мог спросить уточнение)
    return cleaned if cleaned else text.strip()


# ==============================================================================
#  ОПРЕДЕЛЕНИЕ ЯЗЫКА И ШРИФТА СООБЩЕНИЯ
#
#  Участники канала пишут на 4 вариантах:
#  1. Русский кириллица       — "Почему не переключается на газ?"
#  2. Узбекский кириллица     — "Газга ўтмаяпти, нима қилай?"
#     (узнаём по буквам ў қ ғ ҳ — они есть только в узбекском)
#  3. Узбекский латиница      — "Gaz ga o'tmayapti, nima qilaman?"
#     (узнаём по характерным узбекским словам)
#  4. Русский транслит лат.   — "Pochemu ne perekvlyuchaetsya na gaz?"
#     (латиница, но не узбекский)
# ==============================================================================

def detect_language(text: str) -> str:
    """
    Определяет язык текста сообщения.

    Возвращает один из кодов:
        'ru'           — русский
        'uz_cyrillic'  — узбекский кириллица
        'uz_latin'     — узбекский латиница
        'ru_translit'  — русский транслитом
        'en'           — английский
        'uk'           — украинский
        'be'           — белорусский
        'de'           — немецкий
        'kk'           — казахский (кириллица или латиница)
        'ky'           — киргизский
        'tg'           — таджикский
        'tk'           — туркменский

    ПОРЯДОК ВАЖЕН: более специфичные проверки идут раньше общих.
    """
    # ── Кириллица: специфические буквы ───────────────────────────────────────

    # Казахский: ә ң ү ұ ө һ і — проверяем ДО узбекского
    # т.к. қ есть в обоих языках
    if re.search(r"[әңүұөһі]", text, re.UNICODE):
        return "kk"

    # Узбекский кириллица: ў ғ ҳ қ
    if re.search(r"[ўғҳқ]", text, re.UNICODE):
        return "uz_cyrillic"

    # Таджикский: ӣ ӯ ҷ
    if re.search(r"[ӣӯҷ]", text, re.UNICODE):
        return "tg"
    if re.search(
        r"\b(ман|шумо|чӣ|чаро|куҷо|кӯмак|хатои|маъно|дорад)\b",
        text, re.IGNORECASE | re.UNICODE
    ):
        return "tg"

    # Украинский: і ї є ґ
    if re.search(r"[іїєґ]", text, re.UNICODE):
        return "uk"
    if re.search(
        r"\b(що|як|де|коли|чому|помилка|означає)\b",
        text, re.IGNORECASE | re.UNICODE
    ):
        return "uk"

    # Белорусский маркеры
    if re.search(
        r"\b(што|азначае|дзе|калі|чаму|памылка)\b",
        text, re.IGNORECASE | re.UNICODE
    ):
        return "be"

    # Киргизский маркеры (кириллица без спецбукв)
    if re.search(
        r"\b(эмнени|билдирет|каталыгы|каталык|кантип|"
        r"жардам|иштебейт|эмне|кайда|качан)\b",
        text, re.IGNORECASE | re.UNICODE
    ):
        return "ky"

    # Узбекский кириллица маркеры (общая кириллица без спецбукв)
    if re.search(
        r"\b(хатоси|нимани|англатади|савол|нима|нега|"
        r"ишламай|хатолик|юклаш|мумкин|керак|"
        r"ишлаяпти|ишламаяпти|менга|сизга)\b",
        text, re.IGNORECASE | re.UNICODE
    ):
        return "uz_cyrillic"

    # Любая кириллица → русский
    if re.search(r"[а-яёА-ЯЁ]", text, re.UNICODE):
        return "ru"

    # ── Латиница ──────────────────────────────────────────────────────────────

    # Туркменский: ý ň ž — ДО немецкого (ä/ö/ü частично общие)
    if re.search(r"[ýňžÝŇŽ]", text, re.UNICODE):
        return "tk"
    if re.search(
        r"\b(näme|nädip|nirede|haçan|ýalňyşlygy|aňladýar|kömek)\b",
        text, re.IGNORECASE
    ):
        return "tk"

    # Немецкий: ä ö ü ß
    if re.search(r"[äöüßÄÖÜ]", text, re.UNICODE):
        return "de"
    if re.search(
        r"\b(warum|wie|wo|wann|hilfe|fehler|was|bedeutet|funktioniert)\b",
        text, re.IGNORECASE
    ):
        return "de"

    # Казахский латиница
    if re.search(
        r"\b(qalai|qayda|qachon|qate|júkteu|bağdarlama)\b",
        text, re.IGNORECASE
    ):
        return "kk"

    # Английский
    if re.search(
        r"\b(what|why|how|where|when|help|error|does|mean|"
        r"not\s+working|download|please|thanks|thank)\b",
        text, re.IGNORECASE
    ):
        return "en"

    # Узбекский латиница
    if re.search(
        r"\b(nima|qanday|nega|xato|nimani|anglatadi|"
        r"xatosi|ishlamay|qayerda|qachon)\b",
        text, re.IGNORECASE
    ):
        return "uz_latin"

    # Русский транслит
    if re.search(
        r"\b(pochemu|kak|chto|gde|oshibka|rabotaet|pomogite)\b",
        text, re.IGNORECASE
    ):
        return "ru_translit"

    # По умолчанию — узбекский латиница
    return "uz_latin"

def is_dialog_intro(text: str) -> bool:
    """Распознаёт вступление, после которого пользователь ещё задаст вопрос."""
    normalized = re.sub(r"\s+", " ", text.strip(" ,.!?"))
    return bool(INTRO_RE.search(normalized))


def is_question_clear(text: str) -> bool:
    """
    Проверяет, достаточно ли вопрос конкретен для ответа.

    Критерии "непонятного" вопроса:
    - Менее 3 слов (слишком коротко)
    - Состоит только из общих слов типа "помогите", "help", "yordam"

    Аргументы:
        text (str): текст вопроса (уже без обращения к боту)

    Возвращает:
        True  — вопрос достаточно конкретен, можно отвечать
        False — вопрос слишком расплывчатый, нужно уточнить

    Примеры:
        is_question_clear("почему не переключается на газ?") → True
        is_question_clear("помогите")                        → False
        is_question_clear("E-04")                            → True (это код ошибки)
    """
    words = text.split()

    # Если в вопросе меньше 3 слов — слишком коротко
    if len(words) < 3:
        # Но! Если есть код ошибки типа "E-04" — это достаточно конкретно
        # r"E-\d+" — буква E, дефис, одна или более цифр
        if re.search(
            r"\b(?:[PBCU][0-9A-F]{4}|E-?\d{1,3}|SPN\s*\d+(?:\s+FMI\s*\d+)?)\b",
            text,
            re.IGNORECASE,
        ):
            return True  # Код ошибки — достаточно
        return False

    # Проверяем что вопрос — не просто одно общее слово
    # re.fullmatch — совпадение должно быть полным (весь текст)
    vague_only = re.fullmatch(
        r"(pomogite|help|помогите|yordam|kerak|нужна помощь|"
        r"savol|вопрос|вопросик|privet|привет|salom|салом)\s*[\?\!]?",
        text.strip(),
        re.IGNORECASE | re.UNICODE,
    )
    if vague_only:
        return False

    # Вопрос достаточно конкретен
    return True


LPG_QUERY_RE = re.compile(
    r"\b(гбо|газобаллон|пропан|метан|cng|lpg|stag|qbox|qnext|"
    r"редуктор|мультиклапан|газов(?:ая|ые|ый|ого|ому|ым|ых)?\s+форсунк|"
    r"переключ\w*\s+на\s+газ)\b",
    re.IGNORECASE | re.UNICODE,
)


def is_lpg_question(text: str) -> bool:
    """Определяет, относится ли запрос к ГБО, для выбора раздела базы знаний."""
    return bool(LPG_QUERY_RE.search(text))


TRUCK_QUERY_RE = re.compile(
    r"\b(spn|fmi|j1939|тягач|грузовик|камаз|маз|man|scania|daf|iveco|"
    r"volvo\s+truck|renault\s+truck|freightliner|cummins|detroit\s+diesel)\b",
    re.IGNORECASE | re.UNICODE,
)


def is_truck_question(text: str) -> bool:
    return bool(TRUCK_QUERY_RE.search(text))


# ==============================================================================
#  СИСТЕМНЫЙ ПРОМПТ ДЛЯ CLAUDE AI
#
#  Системный промпт — это инструкция для AI, которая задаёт его "роль" и
#  базу знаний. Отправляется с каждым запросом, но не видна пользователю.
#  Чем подробнее промпт — тем точнее и правильнее ответы AI.
# ==============================================================================
SYSTEM_PROMPT = """Ты — «Уста», технический ассистент сообщества AI_Diag_UZ.
Твоя специализация — диагностика, ремонт и обслуживание легковых и грузовых
автомобилей, а также автомобильное газобаллонное оборудование (ГБО), включая
системы AC STAG и оборудование других производителей.

ТВОЯ АУДИТОРИЯ:
- Автодиагносты, электрики, механики, установщики ГБО и мастера СТО
- Владельцы легковых автомобилей, фургонов, автобусов и грузовиков

ОБЛАСТИ ПОМОЩИ:
- OBD-II/EOBD, фирменные DTC, параметры Data Stream и Freeze Frame
- Двигатель, топливная система, зажигание, дизель Common Rail, SCR/DPF/AdBlue
- АКПП/МКПП, ABS/ESP, SRS, BCM, климат, электрика и CAN/J1939
- Датчики, исполнительные механизмы, осциллограммы и электросхемы
- ГБО разных поколений и производителей, настройка и диагностика
- Диагностика легковых и грузовых автомобилей

ПРАВИЛА ОТВЕТОВ:
1. Язык ответа — строго по отдельной инструкции (будет добавлена к этому промпту)
2. Не расшифровывай код только по номеру, если он зависит от марки или блока.
   Запроси марку, модель, год, двигатель, систему/ЭБУ и точный текст ошибки.
3. Отделяй подтверждённые факты от предположений. Не выдумывай распиновки,
   нормативы, моменты затяжки, схемы, коды и процедуры.
4. Давай план проверки от простого и безопасного к сложному: визуальный осмотр,
   питание/масса, разъёмы, параметры, измерения, исполнительные тесты.
5. Перед заменой детали предлагай проверку, которая подтверждает неисправность.
6. Указывай единицы измерения и условия замера. Для грузовиков учитывай 12/24 В,
   J1939, пневмосистемы и конкретного производителя.
7. Для SRS, высокого напряжения гибридов/EV, топлива под высоким давлением,
   тормозов и газовых магистралей обязательно предупреждай о риске и требуй
   соблюдения заводской процедуры безопасности.
8. Для техспециалистов давай точные шаги; владельцам объясняй простыми словами.
9. Отвечай лаконично. Если данных не хватает — задай до четырёх конкретных
   уточняющих вопросов вместо догадки.
10. Не предлагай отключать экологические системы или защитные функции.
11. Не считай автоматически, что новый вопрос относится к прежнему автомобилю
   или ЭБУ. Если связь неочевидна, уточни: это продолжение прежней темы или
   новый автомобиль/блок управления.
12. Если точного ответа нет, прямо сообщи об этом и перечисли, какие данные
   нужны для продолжения диагностики."""


# ==============================================================================
#  ПРИОРИТЕТНЫЕ ВЕБ-ИСТОЧНИКИ ДЛЯ ПОИСКА
#
#  Когда ответа нет в базе знаний, бот ищет в интернете.
#  Поиск идёт строго в указанном порядке приоритетов:
#    1. Официальный сайт AC (Польша) — самый достоверный источник
#    2. Украинские ресурсы о ГБО
#    3. Российские ресурсы о ГБО
#    4. Белорусские ресурсы о ГБО
#
#  Внутри одного приоритета поиск идёт параллельно (одновременно),
#  чтобы не ждать каждый сайт по очереди.
# ==============================================================================
LPG_SEARCH_SOURCES = [
    # ── Приоритет 1: Официальный сайт производителя (Польша) ─────────────────
    {
        "name": "AC официальный (ac.com.pl)",
        "site": "ac.com.pl",
        "priority": 1,
        # Главный источник: документация, прошивки, официальные инструкции
    },
    {
        "name": "Форум AC (forum.ac.com.pl)",
        "site": "forum.ac.com.pl",
        "priority": 1,
        # Официальный форум: вопросы/ответы от технических специалистов AC
    },

    # ── Приоритет 2: Украинские ресурсы ──────────────────────────────────────
    {
        "name": "gbo.ua",
        "site": "gbo.ua",
        "priority": 2,
        # Украинский портал о газобаллонном оборудовании
    },
    {
        "name": "gazda.ua",
        "site": "gazda.ua",
        "priority": 2,
        # Украинский поставщик и ресурс по ГБО
    },
    {
        "name": "autocentre.ua",
        "site": "autocentre.ua",
        "priority": 2,
        # Украинский автомобильный портал
    },

    # ── Приоритет 3: Российские ресурсы ──────────────────────────────────────
    {
        "name": "lpgforum.ru",
        "site": "lpgforum.ru",
        "priority": 3,
        # Крупнейший российский форум по ГБО
    },
    {
        "name": "gbo.pro",
        "site": "gbo.pro",
        "priority": 3,
        # Российский профессиональный портал по ГБО
    },
    {
        "name": "drive2.ru",
        "site": "drive2.ru",
        "priority": 3,
        # Российское автосообщество, много записей об установке ГБО
    },

    # ── Приоритет 4: Белорусские ресурсы ────────────────────────────────────
    {
        "name": "gbo.by",
        "site": "gbo.by",
        "priority": 4,
        # Белорусский портал о ГБО
    },
    {
        "name": "autoforum.by",
        "site": "autoforum.by",
        "priority": 4,
        # Белорусский автомобильный форум
    },
]

GENERAL_SEARCH_SOURCES = [
    # ── Приоритет 1: Производители компонентов ────────────────────────────────
    {"name": "Bosch Aftermarket",   "site": "boschaftermarket.com",  "priority": 1},
    {"name": "DENSO Aftermarket",   "site": "denso-am.eu",           "priority": 1},
    {"name": "NGK/NTK Technical",   "site": "ngkntk.com",            "priority": 1},
    {"name": "Delphi Technologies", "site": "delphiautoparts.com",    "priority": 1},
    {"name": "OBD-II Reference",    "site": "obd-codes.com",          "priority": 1},
    # ── Приоритет 2: Форумы диагностики и чипования ─────────────────────────
    {"name": "Drive2.ru",           "site": "drive2.ru",              "priority": 2},
    {"name": "Chiptuner.ru",        "site": "chiptuner.ru",           "priority": 2},
    {"name": "MHH Auto",            "site": "mhhauto.com",            "priority": 2},
    {"name": "PCM Hacking",         "site": "pcmhacking.net",         "priority": 2},
    {"name": "AutoDevice.ru",       "site": "autodevice.ru",          "priority": 2},
    {"name": "OBD2.su",             "site": "obd2.su",                "priority": 2},
    {"name": "Injector Service UA", "site": "injectorservice.com.ua", "priority": 2},
    # ── Приоритет 3: Международные форумы и ресурсы ──────────────────────────
    {"name": "Reddit r/AskMechanics","site": "reddit.com/r/AskMechanics", "priority": 3},
    {"name": "Reddit r/MechanicAdvice","site": "reddit.com/r/MechanicAdvice", "priority": 3},
    {"name": "HP Tuners Forums",    "site": "hptuners.com/forum",     "priority": 3},
    {"name": "CarMasters",          "site": "carmasters.org",         "priority": 3},
    {"name": "AutoPogs",            "site": "autopogs.com",           "priority": 3},
    {"name": "MPLab UA",            "site": "mplab.org.ua",           "priority": 3},
    {"name": "ChipSoft",            "site": "chipsoft.com.ua",        "priority": 3},
    {"name": "AKPP Help",           "site": "akpphelp.ru",            "priority": 3},
    {"name": "Auto-BK",             "site": "auto-bk.ru",             "priority": 3},
]

TRUCK_SEARCH_SOURCES = [
    {"name": "Cummins",         "site": "cummins.com",       "priority": 1},
    {"name": "Volvo Trucks",    "site": "volvotrucks.com",   "priority": 1},
    {"name": "Scania",          "site": "scania.com",         "priority": 1},
    {"name": "MAN Truck & Bus", "site": "man.eu",             "priority": 1},
    {"name": "MHH Auto Trucks", "site": "mhhauto.com",        "priority": 2},
    {"name": "PCM Hacking",     "site": "pcmhacking.net",     "priority": 2},
    {"name": "Chiptuner Trucks","site": "chiptuner.ru",       "priority": 2},
    {"name": "OBD2.su Trucks",  "site": "obd2.su",            "priority": 2},
]


async def _ddg_search(
    session: aiohttp.ClientSession,
    query: str,
    site: str
) -> Optional[str]:
    """
    Выполняет поиск через HTML-выдачу DuckDuckGo на конкретном сайте.
    Instant Answer API почти никогда не возвращает результаты технического
    поиска, поэтому извлекаем обычные поисковые сниппеты.

    Аргументы:
        session (aiohttp.ClientSession): HTTP-сессия для запросов
        query (str): поисковый запрос (вопрос пользователя)
        site (str): домен сайта для поиска (например "ac.com.pl")

    Возвращает:
        str  — найденный текст (если нашёл что-то полезное)
        None — если ничего не нашёл или произошла ошибка
    """
    try:
        logger.info(f"Внешний поиск: site:{site} | запрос='{query[:80]}'")
        async with session.get(
            "https://html.duckduckgo.com/html/",
            params={"q": f"{query} site:{site}", "kl": "ru-ru"},
            headers={"User-Agent": "Mozilla/5.0 AI_Diag_UZ/1.0"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            if r.status != 200:
                logger.warning(f"Внешний поиск {site}: HTTP {r.status}")
                return None
            body = await r.text(errors="ignore")
            snippets = re.findall(
                r'class="result__snippet"[^>]*>(.*?)</(?:a|div)>',
                body,
                flags=re.IGNORECASE | re.DOTALL,
            )
            cleaned = []
            for snippet in snippets[:3]:
                plain = re.sub(r"<[^>]+>", " ", snippet)
                plain = html.unescape(re.sub(r"\s+", " ", plain)).strip()
                if len(plain) >= 50:
                    cleaned.append(plain)
            if cleaned:
                logger.info(f"Внешний поиск {site}: найдено {len(cleaned)} фрагм.")
                return "\n".join(cleaned)
            logger.info(f"Внешний поиск {site}: результатов нет")
            return None

    except Exception as e:
        logger.warning(f"Внешний поиск {site}: {type(e).__name__}: {e}")
        return None


async def search_web_prioritized(query: str) -> Optional[tuple[str, str]]:
    """
    Ищет ответ на вопрос по всем источникам в порядке приоритета.

    Логика работы:
    1. Группируем источники по приоритетам (1, 2, 3, 4)
    2. Для каждого приоритета запускаем поиск ПАРАЛЛЕЛЬНО на всех сайтах группы
    3. Если нашли ответ — возвращаем его, не переходим к следующему приоритету
    4. Если не нашли — переходим к следующему приоритету

    Аргументы:
        query (str): вопрос пользователя для поиска

    Возвращает:
        tuple(текст_ответа, название_источника) — если нашли
        None — если нигде не нашли
    """
    if is_lpg_question(query):
        selected_sources = LPG_SEARCH_SOURCES + GENERAL_SEARCH_SOURCES
    elif is_truck_question(query):
        selected_sources = TRUCK_SEARCH_SOURCES + GENERAL_SEARCH_SOURCES
    else:
        selected_sources = GENERAL_SEARCH_SOURCES

    logger.info(
        f"Запущен внешний поиск: источников={len(selected_sources)}, "
        f"тип={'ГБО' if is_lpg_question(query) else 'грузовой' if is_truck_question(query) else 'общий'}"
    )

    # Группируем источники по приоритетам
    # Результат: {1: [ac.com.pl, forum.ac.com.pl], 2: [gbo.ua, ...], ...}
    by_priority: dict[int, list[dict]] = {}
    for src in selected_sources:
        priority = src["priority"]
        if priority not in by_priority:
            by_priority[priority] = []
        by_priority[priority].append(src)

    # Создаём одну HTTP-сессию для всех запросов (эффективнее)
    timeout = aiohttp.ClientTimeout(total=15, connect=5)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # Перебираем приоритеты по порядку: 1, 2, 3, 4
        for priority in sorted(by_priority.keys()):
            group = by_priority[priority]

            # Запускаем поиск на всех сайтах группы ОДНОВРЕМЕННО
            # asyncio.gather() — запускает несколько асинхронных задач параллельно
            results = await asyncio.gather(
                *[_ddg_search(session, query, src["site"]) for src in group],
                return_exceptions=True,  # Ошибки не бросают исключение, а возвращаются
            )

            # Проверяем результаты
            for i, result in enumerate(results):
                if isinstance(result, str) and result:
                    logger.info(f"Внешний поиск: выбран источник {group[i]['name']}")
                    return result, group[i]["name"]

            # На этом приоритете ничего не нашли — переходим к следующему

    logger.info("Внешний поиск завершён: подходящих результатов нет")
    return None


# ==============================================================================
#  ХРАНИЛИЩЕ ИСТОРИИ ДИАЛОГОВ
#
#  Claude AI не помнит предыдущие сообщения — каждый запрос независим.
#  Чтобы вести связный диалог (бот помнит контекст), мы храним историю
#  последних N сообщений для каждого пользователя и отправляем её с каждым
#  новым запросом к AI.
#
#  Структура:
#    conversations = {
#        user_id_1: [
#            {"role": "user",      "content": "Что значит E-04?"},
#            {"role": "assistant", "content": "E-04 — ошибка инжектора..."},
#            {"role": "user",      "content": "Как проверить инжектор?"},
#        ],
#        user_id_2: [...],
#    }
# ==============================================================================
# ==============================================================================
#  ФАЙЛОВЫЙ КЭШ — ОПРЕДЕЛЕНИЕ ЗАПРОСА И ОТПРАВКА ФАЙЛОВ
#
#  Если пользователь просит скачать программу, прошивку или документацию,
#  бот сначала ищет файл в локальном каталоге file_catalog.json.
#  Если файл уже скачан — отправляет с диска или по telegram_file_id.
#  Если нет — пробует скачать с source_url (только разрешённые домены).
#  Если скачать нельзя — отдаёт ссылку для ручного скачивания.
# ==============================================================================

# Слова-признаки того что пользователь просит файл/ПО
FILE_REQUEST_KEYWORDS = [
    # Русский
    "скачать", "скачай", "загрузить", "загрузи", "программа", "установить",
    "installer", "setup", "прошивка", "firmware", "драйвер", "driver",
    "документация", "мануал", "инструкция", "руководство", "pdf",
    # Узбекский (латин + кирилл)
    "yuklab", "yukla", "dastur", "sozlash", "qollanma",
    "юклаш", "юкла", "дастур", "созлаш", "қўлланма",
]


def is_file_request(text: str) -> bool:
    """Проверяет содержит ли вопрос запрос на файл/ПО/документацию."""
    tl = text.lower()
    return any(kw in tl for kw in FILE_REQUEST_KEYWORDS)


async def handle_file_request(
    msg,
    question: str,
    lang: str,
    context,
) -> bool:
    """
    Обрабатывает запрос на получение файла.

    Цепочка:
    1. Ищем в каталоге по ключевым словам
    2. Нашли + telegram_file_id → отправляем мгновенно
    3. Нашли + local_path → отправляем с диска, сохраняем file_id
    4. Нашли + source_url → скачиваем, отправляем, сохраняем file_id
    5. Нельзя скачать (авторизация/домен) → даём ссылку для ручного скачивания
    6. Не нашли в каталоге → возвращаем False (обычный поиск продолжается)

    Возвращает:
        True  — запрос обработан (бот уже ответил)
        False — файл не найден, продолжить обычный поиск
    """
    if not FILE_MANAGER_AVAILABLE:
        return False

    file_entry = search_file(question)
    if not file_entry:
        return False

    file_name  = file_entry["name"]
    file_desc  = file_entry.get("description", "")
    tg_file_id = file_entry.get("telegram_file_id")
    local_path = file_entry.get("local_path", "")
    source_url = file_entry.get("source_url", "")
    note       = file_entry.get("note", "")

    logger.info(f"Файловый запрос: '{file_name}' (id={file_entry['id']})")

    SEARCHING = {
        "ru":          "🔍 Ищу файл в базе...",
        "uz_cyrillic": "🔍 Файл қидираман...",
        "uz_latin":    "🔍 Fayl qidiraman...",
        "ru_translit": "🔍 Ishu fayl...",
    }
    status_msg = await msg.reply_text(SEARCHING.get(lang, "🔍 Ищу файл..."))

    caption = (
        f"📦 *{file_name}*\n"
        f"{file_desc}\n\n"
        f"_Источник: {source_url}_"
    )

    # Вариант А: есть telegram_file_id — мгновенная отправка
    if tg_file_id:
        try:
            sent = await msg.reply_document(
                document=tg_file_id,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
            )
            await status_msg.delete()
            return True
        except Exception as e:
            logger.warning(f"file_id устарел ({e}), пробуем с диска")

    # Вариант Б: локальный файл на диске
    if local_path and os.path.exists(local_path):
        try:
            with open(local_path, "rb") as fh:
                sent = await msg.reply_document(
                    document=fh,
                    filename=os.path.basename(local_path),
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN,
                )
            if sent and sent.document:
                save_telegram_file_id(file_entry["id"], sent.document.file_id)
            await status_msg.delete()
            return True
        except Exception as e:
            logger.warning(f"Ошибка отправки с диска: {e}")

    # Вариант В: скачиваем с source_url
    if source_url and source_url.startswith("http"):
        await status_msg.edit_text("⬇️ Скачиваю с сервера производителя...")
        dl_path = await download_and_cache(file_entry)
        if dl_path and os.path.exists(dl_path):
            try:
                with open(dl_path, "rb") as fh:
                    sent = await msg.reply_document(
                        document=fh,
                        filename=os.path.basename(dl_path),
                        caption=caption,
                        parse_mode=ParseMode.MARKDOWN,
                    )
                if sent and sent.document:
                    save_telegram_file_id(file_entry["id"], sent.document.file_id)
                await status_msg.delete()
                return True
            except Exception as e:
                logger.error(f"Ошибка отправки скачанного файла: {e}")

    # Вариант Г: нельзя скачать — даём ссылку
    NOTE_LINE = f"\n📝 {note}" if note else ""
    MANUAL = {
        "ru": (
            f"📦 *{file_name}*\n{file_desc}\n\n"
            f"⚠️ Файл необходимо скачать с официального сайта.{NOTE_LINE}\n"
            f"🔗 {source_url}"
        ),
        "uz_latin": (
            f"📦 *{file_name}*\n{file_desc}\n\n"
            f"⚠️ Ushbu faylni rasmiy saytdan yuklab olish kerak.{NOTE_LINE}\n"
            f"🔗 {source_url}"
        ),
        "uz_cyrillic": (
            f"📦 *{file_name}*\n{file_desc}\n\n"
            f"⚠️ Бу файлни расмий сайтдан юклаш керак.{NOTE_LINE}\n"
            f"🔗 {source_url}"
        ),
        "ru_translit": (
            f"📦 *{file_name}*\n{file_desc}\n\n"
            f"⚠️ Fayl ruchnogo skachivanya trebuet.{NOTE_LINE}\n"
            f"🔗 {source_url}"
        ),
    }
    try:
        await status_msg.edit_text(
            MANUAL.get(lang, MANUAL["ru"]),
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception:
        await status_msg.edit_text(f"📦 {file_name}\n\nСкачать: {source_url}")
    return True


conversations: dict[tuple[int, int], list[dict]] = {}

# Временное хранилище для кнопок обратной связи.
# {feedback_id: {question, answer, source, user_id, username, chat_id}}
# Очищается при обработке или перезапуске бота.
pending_feedback: dict[str, dict] = {}

# Временное хранилище для подтверждения фото-вопросов.
# {(chat_id, user_id): (timestamp, photo_bytes, question, lang)}
# Используется когда бот уточняет "Вы про недавнее фото?"
pending_photo_questions: dict[tuple[int, int], tuple] = {}

# Отслеживание попыток ответа на один и тот же вопрос.
# {(chat_id, user_id): {"question": str, "attempts": int, "answer": str}}
# Используется для кнопки "Ответ неверный" — бот пробует 2 раза, потом передаёт админу.
answer_attempts: dict[tuple[int, int], dict] = {}

# Контекст уточняющего вопроса (Уточнить → пользователь пишет без триггера)
# {(chat_id, user_id): {"original_question": str, "original_answer": str, "ts": float}}
clarify_context: dict[tuple[int, int], dict] = {}
CLARIFY_CONTEXT_TTL = 10 * 60  # 10 минут

# Статистика оценок ответов — хранится в knowledge_base.json через kb_manager.
# Ключи: "thanks", "clarify", "wrong" для каждого вопроса в БЗ.

# Кэш последних фото пользователей.
# Структура: {(chat_id, user_id): (timestamp, photo_bytes, caption)}
# Используется чтобы связать фото отправленное отдельно с последующим вопросом.
# TTL: 5 минут — после этого фото считается нерелевантным.
recent_photos: dict[tuple[int, int], tuple[float, bytes, str]] = {}
RECENT_PHOTO_TTL = 5 * 60  # 5 минут в секундах

# Слова-признаки что пользователь ссылается на ранее отправленное изображение
IMAGE_REF_KEYWORDS = [
    # Русский
    "картинк", "фото", "изображени", "снимок", "скриншот", "фотограф",
    "на фото", "на картинк", "что здесь", "что это", "видишь", "видно",
    "распозна", "прочитай", "считай текст",
    # Узбекский (лат + кир)
    "rasm", "fotosurat", "tasvir", "skrinshotni", "rasmdagi", "nima bu",
    "расм", "фотосурат", "тасвир",
]

def is_image_reference(text: str) -> bool:
    """Проверяет что вопрос ссылается на изображение (без приложенного фото)."""
    tl = text.lower()
    return any(kw in tl for kw in IMAGE_REF_KEYWORDS)

def save_recent_photo(
    chat_id: int, user_id: int, photo_bytes: bytes, caption: str
) -> None:
    """Сохраняет фото в кэш для последующей привязки к вопросу."""
    recent_photos[(chat_id, user_id)] = (time.monotonic(), photo_bytes, caption)

def get_recent_photo(
    chat_id: int, user_id: int
) -> tuple[bytes, str] | None:
    """
    Возвращает кэшированное фото если не истёк TTL.
    Возвращает (bytes, caption) или None.
    """
    entry = recent_photos.get((chat_id, user_id))
    if not entry:
        return None
    ts, photo_bytes, caption = entry
    if time.monotonic() - ts > RECENT_PHOTO_TTL:
        recent_photos.pop((chat_id, user_id), None)
        return None
    return photo_bytes, caption
awaiting_questions: dict[tuple[int, int], tuple[float, str]] = {}

MAX_HISTORY = 10  # Хранить не более 10 последних сообщений на пользователя
AWAITING_QUESTION_TTL = 10 * 60  # 10 минут на следующий вопрос без «Уста»
# Больше = больше контекста, но дороже запрос к AI (платим за токены)


def conversation_key(chat_id: int, user_id: int) -> tuple[int, int]:
    """Возвращает отдельный ключ диалога для каждой группы и пользователя."""
    return (chat_id, user_id)


def add_history(chat_id: int, user_id: int, role: str, content: str) -> None:
    """
    Добавляет сообщение в историю диалога пользователя.

    Аргументы:
        uid (int):     Telegram user_id пользователя
        role (str):    "user" (вопрос) или "assistant" (ответ бота)
        content (str): текст сообщения
    """
    # Создаём пустую историю если пользователь новый
    key = conversation_key(chat_id, user_id)
    if key not in conversations:
        conversations[key] = []

    # Добавляем сообщение
    conversations[key].append({"role": role, "content": content})

    # Обрезаем историю если превысили лимит (оставляем последние MAX_HISTORY)
    if len(conversations[key]) > MAX_HISTORY:
        conversations[key] = conversations[key][-MAX_HISTORY:]
        # [-MAX_HISTORY:] — срез: последние MAX_HISTORY элементов списка


def get_history(chat_id: int, user_id: int) -> list[dict]:
    """
    Возвращает историю диалога пользователя.

    Аргументы:
        uid (int): Telegram user_id

    Возвращает:
        list: список сообщений в формате [{"role": ..., "content": ...}, ...]
              или пустой список если истории нет
    """
    return conversations.get(conversation_key(chat_id, user_id), [])
    # dict.get(key, default) — возвращает default если ключ не найден


def clear_history(chat_id: int, user_id: int) -> None:
    """
    Очищает историю диалога пользователя (например, по команде /reset).

    Аргументы:
        uid (int): Telegram user_id
    """
    conversations[conversation_key(chat_id, user_id)] = []


def wait_for_question(chat_id: int, user_id: int, lang: str) -> None:
    awaiting_questions[conversation_key(chat_id, user_id)] = (time.monotonic(), lang)


def consume_waiting_question(chat_id: int, user_id: int) -> Optional[str]:
    """Возвращает предполагаемый язык и снимает ожидание следующего вопроса."""
    key = conversation_key(chat_id, user_id)
    state = awaiting_questions.pop(key, None)
    if not state:
        return None
    started_at, assumed_lang = state
    if time.monotonic() - started_at > AWAITING_QUESTION_TTL:
        return None
    return assumed_lang


FOLLOWUP_RE = re.compile(
    r"^(а\s+|и\s+|тогда\s+|если\s+|как\s+(?:его|её|это|проверить)|"
    r"где\s+(?:он|она|это)|что\s+с\s+(?:ним|ней|этим)|"
    r"bu\s+|unda\s+|agar\s+|qanday\s+(?:tekshirish|qilaman))",
    re.IGNORECASE | re.UNICODE,
)


def looks_like_followup(question: str) -> bool:
    """Сохраняет прошлый контекст только при явных признаках продолжения."""
    return bool(FOLLOWUP_RE.search(question.strip()))


def is_admin(uid: int) -> bool:
    """
    Проверяет, является ли пользователь администратором.
    Список администраторов задаётся в config.py (TELEGRAM_ADMIN_IDS).

    Аргументы:
        uid (int): Telegram user_id

    Возвращает:
        True  — пользователь является администратором
        False — обычный пользователь
    """
    return uid in TELEGRAM_ADMIN_IDS


def is_chat_allowed(chat_id: int) -> bool:
    """Разрешает все чаты либо только перечисленные в ALLOWED_CHAT_IDS."""
    return not ALLOWED_CHAT_IDS or chat_id in ALLOWED_CHAT_IDS


def progress_bar(percent: int) -> str:
    filled = max(0, min(10, percent // 10))
    return "▰" * filled + "▱" * (10 - filled)


def progress_text(lang: str, percent: int, context_label: str = "") -> str:
    """
    Формирует текст прогресса с % и прогресс-баром.
    Под баром показывает подсказку на языке пользователя.
    """
    # Подсказки меняются в зависимости от % прогресса
    STAGE_LABELS = {
        "ru": {
            10:  "Скачиваю изображение...",
            25:  "Анализирую содержимое...",
            45:  "Распознаю текст и коды...",
            60:  "Ищу в базе знаний...",
            75:  "Формирую ответ...",
            90:  "Почти готово...",
            100: "Готово!",
        },
        "uz_cyrillic": {
            10:  "Расмни юклаяпман...",
            25:  "Мазмунни таҳлил қиляпман...",
            45:  "Матн ва кодларни аниқлаяпман...",
            60:  "Билимлар базасида қидираман...",
            75:  "Жавоб тайёрлаяпман...",
            90:  "Деярли тайёр...",
            100: "Тайёр!",
        },
        "uz_latin": {
            10:  "Rasmni yuklayman...",
            25:  "Mazmunni tahlil qilaman...",
            45:  "Matn va kodlarni aniqlayman...",
            60:  "Bilimlar bazasida qidiraman...",
            75:  "Javob tayyorlayman...",
            90:  "Deyarli tayyor...",
            100: "Tayyor!",
        },
        "ru_translit": {
            10:  "Skachivayu izobrazhenie...",
            25:  "Analiziruyu soderzhimoe...",
            45:  "Raspoznayu tekst...",
            60:  "Ishu v baze...",
            75:  "Formiruu otvet...",
            90:  "Pochti gotovo...",
            100: "Gotovo!",
        },
        "en": {
            10:  "Downloading image...",
            25:  "Analysing content...",
            45:  "Recognising text and codes...",
            60:  "Searching knowledge base...",
            75:  "Preparing answer...",
            90:  "Almost ready...",
            100: "Done!",
        },
        "uk": {
            10:  "Завантажую зображення...",
            25:  "Аналізую вміст...",
            45:  "Розпізнаю текст та коди...",
            60:  "Шукаю в базі знань...",
            75:  "Формую відповідь...",
            90:  "Майже готово...",
            100: "Готово!",
        },
        "be": {
            10:  "Спампоўваю выяву...",
            25:  "Аналізую змест...",
            45:  "Распазнаю тэкст і коды...",
            60:  "Шукаю ў базе ведаў...",
            75:  "Фармірую адказ...",
            90:  "Амаль гатова...",
            100: "Гатова!",
        },
        "de": {
            10:  "Bild wird heruntergeladen...",
            25:  "Inhalt wird analysiert...",
            45:  "Text und Codes werden erkannt...",
            60:  "Suche in der Wissensdatenbank...",
            75:  "Antwort wird vorbereitet...",
            90:  "Fast fertig...",
            100: "Fertig!",
        },
        "kk": {
            10:  "Сурет жүктелуде...",
            25:  "Мазмұн талдануда...",
            45:  "Мәтін мен кодтар анықталуда...",
            60:  "Білім қорынан іздеуде...",
            75:  "Жауап дайындалуда...",
            90:  "Дерлік дайын...",
            100: "Дайын!",
        },
        "ky": {
            10:  "Сүрөт жүктөлүүдө...",
            25:  "Мазмун талдануудa...",
            45:  "Текст жана кодтор аныкталууда...",
            60:  "Билим базасынан издөөдө...",
            75:  "Жооп даярдалууда...",
            90:  "Дээрлик даяр...",
            100: "Даяр!",
        },
        "tg": {
            10:  "Тасвир боргирӣ мешавад...",
            25:  "Мазмун таҳлил мешавад...",
            45:  "Матн ва рамзҳо муайян мешаванд...",
            60:  "Дар пойгоҳи дониш ҷустуҷӯ...",
            75:  "Ҷавоб омода мешавад...",
            90:  "Қариб тайёр...",
            100: "Тайёр!",
        },
        "tk": {
            10:  "Surat ýüklenýär...",
            25:  "Mazmuny derňelýär...",
            45:  "Tekst we kodlar kesgitlenýär...",
            60:  "Bilim bazasynda gözlenýär...",
            75:  "Jogap taýýarlanýär...",
            90:  "Diýen ýaly taýýar...",
            100: "Taýýar!",
        },
    }
    lang_stages = STAGE_LABELS.get(lang, STAGE_LABELS["ru"])
    # Берём подсказку для ближайшего этапа
    stage_label = lang_stages[10]  # По умолчанию
    for threshold in sorted(lang_stages.keys()):
        if percent >= threshold:
            stage_label = lang_stages[threshold]

    bar = progress_bar(percent)
    return f"⏳ {percent}%  {bar}\n{stage_label}"


async def animate_progress(message: Message, stop_event: asyncio.Event, lang: str) -> None:
    """
    Анимирует прогресс в одном Telegram-сообщении.
    Показывает % прогресса + прогресс-бар + текст на языке пользователя.
    Не создаёт новых сообщений — редактирует одно существующее.
    """
    for percent in (20, 35, 50, 65, 78, 88, 94):
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=2.5)
            return
        except asyncio.TimeoutError:
            try:
                await message.edit_text(progress_text(lang, percent))
            except Exception:
                pass


def user_error_reason(error: Exception) -> str:
    text = str(error).lower()
    if "timeout" in text or "timed out" in text:
        return "источник ответа не успел ответить вовремя"
    if "authentication" in text or "401" in text or "api key" in text:
        return "ошибка авторизации сервиса ответов"
    if "rate" in text or "429" in text:
        return "временно превышен лимит запросов"
    if "network" in text or "connect" in text:
        return "нет соединения с внешним сервисом"
    return "внутренняя ошибка обработки"


# ==============================================================================
#  ОСНОВНАЯ ЛОГИКА — ГЕНЕРАЦИЯ ОТВЕТА
#
#  Это главная функция бота. Она получает вопрос и по цепочке ищет ответ:
#  База знаний → Официальный сайт → UA сайты → RU сайты → BY сайты → Claude AI
# ==============================================================================

# ==============================================================================
#  МНОГОУРОВНЕВЫЙ AI: БЕСПЛАТНЫЕ МОДЕЛИ + ПЛАТНЫЙ FALLBACK
#
#  Порядок попыток:
#  1. Groq API (бесплатный tier) — llama-3.3-70b-versatile
#     Сайт: console.groq.com → бесплатная регистрация → API Key
#     Лимит бесплатного плана: ~14 400 запросов/день
#
#  2. Google Gemini API (бесплатный tier) — gemini-1.5-flash
#     Сайт: aistudio.google.com → Get API Key (бесплатно)
#     Лимит: 15 запросов/минуту, 1500/день
#
#  3. Anthropic Claude (платный fallback) — claude-haiku-4-5 (самый дешёвый)
#     Используется только если бесплатные недоступны.
#     ~$0.00025 за запрос (haiku намного дешевле opus)
#
#  Настройка: добавьте в config.py:
#    GROQ_API_KEY = "gsk_..."        # из console.groq.com
#    GEMINI_API_KEY = "AIza..."      # из aistudio.google.com
# ==============================================================================

# Загружаем ключи бесплатных AI из конфига
try:
    from config import GROQ_API_KEY
except ImportError:
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

try:
    from config import GEMINI_API_KEY
except ImportError:
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

try:
    from config import DEEPSEEK_API_KEY
except ImportError:
    DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

try:
    from config import KIMI_API_KEY
except ImportError:
    KIMI_API_KEY = os.environ.get("KIMI_API_KEY", "")


async def _call_groq(system: str, messages: list, question: str) -> str:
    """
    Вызов Groq API (бесплатный).
    Модель: llama-3.3-70b-versatile — мощная, быстрая, бесплатная.
    Документация: console.groq.com/docs
    """
    if not GROQ_API_KEY:
        return ""
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
        # Groq использует формат OpenAI: system + user messages
        groq_messages = [{"role": "system", "content": system}]
        for m in messages:
            groq_messages.append({"role": m["role"], "content": m["content"]})

        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": groq_messages,
            "max_tokens": 1200,
            "temperature": 0.3,
        }
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    answer = data["choices"][0]["message"]["content"].strip()
                    if answer:
                        logger.info("AI ответ получен: Groq (llama-3.3-70b)")
                    return answer
                else:
                    text = await resp.text()
                    logger.warning(f"Groq API error {resp.status}: {text[:200]}")
                    return ""
    except Exception as e:
        logger.warning(f"Groq недоступен: {e}")
        return ""


async def _call_gemini(system: str, messages: list, question: str) -> str:
    """
    Вызов Google Gemini API (бесплатный tier).
    Модель: gemini-1.5-flash — быстрая, бесплатная (1500 запросов/день).
    Документация: aistudio.google.com
    """
    if not GEMINI_API_KEY:
        return ""
    try:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        )
        # Gemini: system через systemInstruction, history через contents
        contents = []
        for m in messages:
            role = "user" if m["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})

        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {"maxOutputTokens": 1200, "temperature": 0.3},
        }
        timeout = aiohttp.ClientTimeout(total=25)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        answer = " ".join(p.get("text", "") for p in parts).strip()
                        if answer:
                            logger.info("AI ответ получен: Gemini (gemini-1.5-flash)")
                        return answer
                else:
                    text = await resp.text()
                    logger.warning(f"Gemini API error {resp.status}: {text[:200]}")
                    return ""
    except Exception as e:
        logger.warning(f"Gemini недоступен: {e}")
        return ""


async def _call_claude_haiku(system: str, messages: list, question: str) -> str:
    """
    Вызов Anthropic Claude Haiku (платный fallback, самый дешёвый).
    ~$0.00025 за запрос — используется только если бесплатные недоступны.
    """
    try:
        response = await asyncio.to_thread(
            anthropic.messages.create,
            model="claude-haiku-4-5",
            max_tokens=1200,
            system=system,
            messages=messages,
        )
        answer = "\n".join(
            block.text.strip()
            for block in response.content
            if getattr(block, "text", "").strip()
        ).strip()
        if answer:
            logger.info("AI ответ получен: Claude Haiku (платный fallback)")
        return answer
    except Exception as e:
        logger.warning(f"Claude Haiku недоступен: {e}")
        return ""



async def _call_deepseek(system: str, messages: list, question: str) -> str:
    """
    Вызов DeepSeek API.
    Модель: deepseek-chat (DeepSeek-V3)
    Особенно хорош для технических вопросов об автомобилях,
    включая китайские марки (BYD, Chery, Geely, Great Wall, JAC и др.).
    API совместим с форматом OpenAI.
    Регистрация: platform.deepseek.com
    Бесплатно: $5 кредитов при регистрации, затем ~$0.00014/1K токенов.
    """
    if not DEEPSEEK_API_KEY:
        return ""
    try:
        url = "https://api.deepseek.com/chat/completions"
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        }
        ds_messages = [{"role": "system", "content": system}]
        for m in messages:
            ds_messages.append({"role": m["role"], "content": m["content"]})
        payload = {
            "model": "deepseek-chat",
            "messages": ds_messages,
            "max_tokens": 1200,
            "temperature": 0.3,
        }
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    answer = data["choices"][0]["message"]["content"].strip()
                    if answer:
                        logger.info("AI ответ получен: DeepSeek (deepseek-chat)")
                    return answer
                else:
                    text = await resp.text()
                    logger.warning(f"DeepSeek API error {resp.status}: {text[:200]}")
                    return ""
    except Exception as e:
        logger.warning(f"DeepSeek недоступен: {e}")
        return ""


async def _call_kimi(system: str, messages: list, question: str) -> str:
    """
    Вызов Kimi (Moonshot AI) API.
    Модель: moonshot-v1-8k
    Специализируется на китайскоязычном контенте.
    Отлично подходит для вопросов о китайских автомобилях и оборудовании:
    BYD, SAIC, FAW, Chery, Geely, Great Wall, JAC, Foton, Yutong и др.
    Регистрация: platform.moonshot.cn
    Бесплатно: 15 млн токенов при регистрации.
    """
    if not KIMI_API_KEY:
        return ""
    try:
        url = "https://api.moonshot.cn/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {KIMI_API_KEY}",
            "Content-Type": "application/json",
        }
        kimi_messages = [{"role": "system", "content": system}]
        for m in messages:
            kimi_messages.append({"role": m["role"], "content": m["content"]})
        payload = {
            "model": "moonshot-v1-8k",
            "messages": kimi_messages,
            "max_tokens": 1200,
            "temperature": 0.3,
        }
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    answer = data["choices"][0]["message"]["content"].strip()
                    if answer:
                        logger.info("AI ответ получен: Kimi Moonshot (moonshot-v1-8k)")
                    return answer
                else:
                    text = await resp.text()
                    logger.warning(f"Kimi API error {resp.status}: {text[:200]}")
                    return ""
    except Exception as e:
        logger.warning(f"Kimi недоступен: {e}")
        return ""


async def _call_ai_with_fallback(
    system: str,
    messages: list,
    question: str,
) -> str:
    """
    Многоуровневый AI с приоритетом бесплатных моделей.

    Порядок:
    1. Groq (бесплатно, llama-3.3-70b) — если GROQ_API_KEY задан
    2. Gemini (бесплатно, gemini-1.5-flash) — если GEMINI_API_KEY задан
    3. Claude Haiku (платно, fallback) — всегда доступен

    Возвращает первый непустой ответ.
    """
    # Приоритет бесплатных моделей, Claude Haiku — только резерв.
    # DeepSeek и Kimi добавлены для лучшего покрытия китайских авто.

    # 1. Groq (бесплатно, llama-3.3-70b — быстрый и мощный)
    if GROQ_API_KEY:
        answer = await _call_groq(system, messages, question)
        if answer:
            logger.info("AI ответ: Groq (llama-3.3-70b)")
            return answer, "Groq"

    # 2. DeepSeek (почти бесплатно, отличен для технических авто-вопросов)
    if DEEPSEEK_API_KEY:
        answer = await _call_deepseek(system, messages, question)
        if answer:
            logger.info("AI ответ: DeepSeek (deepseek-chat)")
            return answer, "DeepSeek"

    # 3. Kimi / Moonshot (бесплатно, лучший для китайских авто и оборудования)
    if KIMI_API_KEY:
        answer = await _call_kimi(system, messages, question)
        if answer:
            logger.info("AI ответ: Kimi (moonshot-v1-8k)")
            return answer, "Kimi"

    # 4. Gemini (бесплатно, gemini-1.5-flash)
    if GEMINI_API_KEY:
        answer = await _call_gemini(system, messages, question)
        if answer:
            logger.info("AI ответ: Gemini (gemini-1.5-flash)")
            return answer, "Gemini"

    # 5. Claude Haiku (платный fallback — только если все остальные недоступны)
    answer = await _call_claude_haiku(system, messages, question)
    logger.info("AI ответ: Claude Haiku (fallback)")
    return answer, "Claude"


async def generate_answer(
    user_id: int,        # Telegram ID пользователя
    question: str,       # Текст вопроса
    lang: str,           # Язык ответа ('ru', 'uz_cyrillic', ...)
    username: str = "",  # @username для логов
    chat_id: int = 0,    # ID чата для pending
    msg_obj=None,        # Объект Message — нужен для handle_file_request
    ctx_obj=None,        # Объект context — нужен для handle_file_request
) -> tuple[str, str]:
    """
    Главная функция поиска ответа. Перебирает источники по цепочке.

    Возвращает:
        tuple: (текст_ответа, источник)
        источник — одно из: 'kb' | 'web' | 'ai' | 'error'
    """

    # ── Шаг 0: Проверяем запрос на файл/ПО ─────────────────────────────────────
    # Если пользователь просит скачать программу, прошивку или документацию —
    # обрабатываем отдельно через file_manager, не идём в базу знаний.
    # handle_file_request() возвращает True если запрос обработан (файл найден).
    # Параметр msg_obj передаётся только если вызов из chat-обработчика.
    if FILE_MANAGER_AVAILABLE and is_file_request(question) and msg_obj is not None:
        handled = await handle_file_request(msg_obj, question, lang, ctx_obj)
        if handled:
            return "", "file", ""  # Сигнал что ответ уже отправлен напрямую

    # ── Шаг 1: Ищем в Базе Знаний ────────────────────────────────────────────
    # База знаний — это JSON-файл с готовыми вопросами и ответами.
    # kb_manager.find_best() ищет семантически похожий вопрос (по смыслу, не
    # по точному совпадению). Например: "не переключается" найдёт запись
    # "Почему автомобиль не переключается на газ?"
    kb_scope = "lpg" if is_lpg_question(question) else "auto"
    kb_result = kb_manager.find_best(question, scope=kb_scope)
    if kb_result:
        # Нашли в базе знаний — формируем ответ с заголовком
        answer = f"📚 *Из базы знаний:*\n\n{kb_result['answer']}"
        return answer, "kb", ""  # "kb" = knowledge base

    # ── Шаг 2–4: Внешний поиск ───────────────────────────────────────────────
    logger.info(f"Начинаем внешний поиск | вопрос='{question[:60]}'")
    web = await search_web_prioritized(question)
    web_context = ""
    web_source = ""
    if web:
        web_text, web_source = web
        logger.info(f"Внешний поиск: найдено в {web_source}")
        web_context = (
            "\n\nКОНТЕКСТ ИЗ ВНЕШНЕГО ИСТОЧНИКА "
            f"({web_source}):\n{web_text}\n"
            "Используй только релевантные сведения. Сниппет может быть неполным; "
            "не выдавай его за заводскую документацию и не придумывай детали."
        )

    # ── Шаг 5: Генерируем ответ через Claude AI ──────────────────────────────
    # Если не нашли ни в базе знаний, ни в интернете — спрашиваем у AI.
    # Claude AI — языковая модель от Anthropic, знает о ГБО из обучающих данных.

    # Добавляем языковую инструкцию к системному промпту
    lang_note = LANG_INSTRUCTION.get(lang, LANG_INSTRUCTION["ru"])
    system = f"{SYSTEM_PROMPT}\n\nЯЗЫК ОТВЕТА: {lang_note}{web_context}"

    # Не переносим автомобиль/ЭБУ из прошлого вопроса автоматически. История
    # используется только при явных признаках продолжения («а как проверить…»).
    previous_history = get_history(chat_id, user_id)
    if previous_history and not looks_like_followup(question):
        logger.info(
            f"Новая тема: очищен предыдущий контекст | user_id={user_id} | "
            f"chat_id={chat_id}"
        )
        clear_history(chat_id, user_id)

    # Добавляем вопрос в историю диалога
    add_history(chat_id, user_id, "user", question)

    try:
        # ── Многоуровневый AI: пробуем бесплатные модели сначала ─────────────
        # Порядок: Groq (бесплатно) → Gemini (бесплатно) → Claude (платно)
        # Используем первый успешный ответ.
        ai_answer, ai_source = await _call_ai_with_fallback(
            system=system,
            messages=get_history(chat_id, user_id),
            question=question,
        )

        if not ai_answer:
            logger.warning("AI вернул пустой ответ; вопрос сохранён в pending")
            kb_manager.add_pending_question(user_id, username, question, chat_id)
            return UNAVAILABLE_MSG.get(lang, UNAVAILABLE_MSG["ru"]), "unavailable", ""

        # Сохраняем ответ AI в историю диалога
        add_history(chat_id, user_id, "assistant", ai_answer)

        # Сохраняем вопрос для самообучения базы знаний
        kb_manager.add_pending_question(user_id, username, question, chat_id)

        return ai_answer, ("web_ai" if web_source else "ai"), ai_source

    except Exception as e:
        # Что-то пошло не так (нет интернета, проблема с API и т.д.)
        logger.exception("Ошибка формирования ответа через AI")
        kb_manager.add_pending_question(user_id, username, question, chat_id)
        reason = user_error_reason(e)
        fallback = UNAVAILABLE_MSG.get(lang, UNAVAILABLE_MSG["ru"])
        return f"❌ Причина: {reason}.\n\n{fallback}", "error", ""


# ==============================================================================
#  ОБРАБОТЧИКИ СООБЩЕНИЙ TELEGRAM
#
#  Обработчик — это функция, которая вызывается когда приходит
#  определённый тип сообщения.
# ==============================================================================

async def process_user_question(
    msg: Message,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    username: str,
    question: str,
    lang: str,
) -> None:
    """Проверяет вопрос, показывает прогресс и гарантированно отправляет итог."""
    # ── Режим уточнения (после нажатия кнопки "Уточнить") ───────────────────
    # Если пользователь нажал "Уточнить" — следующее сообщение обрабатывается
    # БЕЗ триггера-слова, с контекстом оригинального вопроса и ответа.
    clarify_key = (msg.chat.id, user_id)
    clarify_entry = clarify_context.get(clarify_key)
    if clarify_entry and (time.monotonic() - clarify_entry["ts"]) < CLARIFY_CONTEXT_TTL:
        # Добавляем контекст к новому вопросу
        orig_q = clarify_entry["original_question"]
        orig_a = clarify_entry["original_answer"]
        clarify_context.pop(clarify_key, None)  # Удаляем контекст (одноразовый)
        # Формируем расширенный вопрос с контекстом предыдущего диалога
        question = (
            f"{question}\n\n"
            f"[Контекст: ранее был вопрос '{orig_q[:100]}' "
            f"и ответ '{orig_a[:150]}...']"
        )
        logger.info(f"Уточняющий вопрос | user_id={user_id} | '{question[:60]}'")

    if not is_question_clear(question):
        logger.info(
            f"Недостаточно данных | user_id={user_id} | вопрос='{question[:80]}'"
        )
        clarify = CLARIFY_MSG.get(lang, CLARIFY_MSG["ru"])
        try:
            await msg.reply_text(clarify, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception:
            await msg.reply_text(clarify)
        return

    # ── Проверка кэша фото ─────────────────────────────────────────────────
    # Логика привязки фото к последующему вопросу:
    # A) Есть кэш + вопрос содержит маркеры фото → анализируем сразу
    # B) Есть кэш + нет маркеров → спрашиваем кнопками "Про это фото?"
    # C) Нет кэша + есть маркеры → просим прислать фото
    # D) Нет кэша + нет маркеров → обычный текстовый поиск (продолжаем)
    if IMAGE_ANALYSIS_AVAILABLE:
        cached = get_recent_photo(msg.chat.id, user_id)
        has_img_ref = is_image_reference(question)

        if cached:
            cached_bytes, cached_caption = cached

            # Lazy loading — скачиваем если ещё не скачаны
            if cached_bytes == b"__pending__":
                last_fid = context.chat_data.get("last_photo_file_id")
                if last_fid:
                    try:
                        photo_file = await context.bot.get_file(last_fid)
                        cached_bytes = bytes(await photo_file.download_as_bytearray())
                        save_recent_photo(msg.chat.id, user_id, cached_bytes, cached_caption)
                        logger.info(f"Lazy-загрузка фото: {len(cached_bytes)} байт")
                    except Exception as e:
                        logger.warning(f"Ошибка загрузки кэшированного фото: {e}")
                        cached_bytes = b""

            if cached_bytes and cached_bytes != b"__pending__":
                if has_img_ref:
                    # A) Маркеры есть — анализируем сразу
                    await _analyze_cached_photo(
                        msg, context, cached_bytes, question, lang, user_id, username
                    )
                    return
                else:
                    # B) Маркеров нет — уточняем через кнопки
                    pending_photo_questions[(msg.chat.id, user_id)] = (
                        time.monotonic(), cached_bytes, question, lang
                    )
                    CONFIRM_PHOTO = {
                        "ru":          "🖼️ Вы спрашиваете про недавно отправленное фото?",
                        "uz_latin":    "🖼️ Yaqinda yuborgan rasmingiz haqida so'rayapsizmi?",
                        "uz_cyrillic": "🖼️ Яқинда юборган расмингиз ҳақида сўраяпсизми?",
                        "ru_translit": "🖼️ Vy sprashivaete pro nedavno otpravlennoe foto?",
                    }
                    # Надписи кнопок на языке вопроса
                    BTN_YES = {
                        "ru":          "✅ Да, про это фото",
                        "uz_cyrillic": "✅ Ҳа, бу расм ҳақида",
                        "uz_latin":    "✅ Ha, bu rasm haqida",
                        "ru_translit": "✅ Da, pro eto foto",
                    }
                    BTN_NO = {
                        "ru":          "❌ Нет, другой вопрос",
                        "uz_cyrillic": "❌ Йўқ, бошқа савол",
                        "uz_latin":    "❌ Yo'q, boshqa savol",
                        "ru_translit": "❌ Net, drugoy vopros",
                    }
                    keyboard = InlineKeyboardMarkup([[
                        InlineKeyboardButton(
                            BTN_YES.get(lang, BTN_YES["ru"]),
                            callback_data=f"photo_yes:{msg.chat.id}:{user_id}"
                        ),
                        InlineKeyboardButton(
                            BTN_NO.get(lang, BTN_NO["ru"]),
                            callback_data=f"photo_no:{msg.chat.id}:{user_id}"
                        ),
                    ]])
                    await msg.reply_text(
                        CONFIRM_PHOTO.get(lang, CONFIRM_PHOTO["ru"]),
                        reply_markup=keyboard,
                    )
                    return

        elif has_img_ref:
            # C) Кэша нет, но вопрос про изображение — просим прислать
            PHOTO_WHERE = {
                "ru": (
                    "🖼️ Похоже, вы спрашиваете про изображение.\n\n"
                    "Отправьте фото в чат и напишите вопрос в подписи.\n"
                    "Пример: прикрепите фото + в подписи `Уста, что за ошибка?`"
                ),
                "uz_latin": (
                    "🖼️ Siz rasm haqida so'rayotganga o'xshaysiz.\n\n"
                    "Rasmni chatga yuboring, savolni rasm tagiga yozing.\n"
                    "Misol: rasm + tagida `Usta, bu xato nima?`"
                ),
                "uz_cyrillic": (
                    "🖼️ Сиз расм ҳақида сўраётгандек.\n\n"
                    "Расмни чатга юборинг, саволни расм тагига ёзинг.\n"
                    "Мисол: расм + тагида `Уста, бу хато нима?`"
                ),
                "ru_translit": (
                    "🖼️ Otpravte foto v chat i napishite vopros v podpisi.\n"
                    "Primer: foto + `Usta, chto za oshibka?`"
                ),
            }
            try:
                await msg.reply_text(
                    PHOTO_WHERE.get(lang, PHOTO_WHERE["ru"]),
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception:
                await msg.reply_text(PHOTO_WHERE.get(lang, PHOTO_WHERE["ru"]))
            return
        # D) Нет кэша и нет маркеров — продолжаем обычный поиск
    await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.TYPING)
    status_message = await msg.reply_text(progress_text(lang, 10))
    stop_event = asyncio.Event()
    progress_task = asyncio.create_task(
        animate_progress(status_message, stop_event, lang)
    )

    try:
        answer, source, ai_source = await generate_answer(
            user_id, question, lang, username, msg.chat_id,
            msg_obj=msg, ctx_obj=context,
        )
        # Если generate_answer вернул ("", "file") — файл уже отправлен
        # handle_file_request, удаляем прогресс-сообщение и выходим
        if source == "file":
            stop_event.set()
            try:
                await status_message.delete()
            except Exception:
                pass
            return
    except Exception as e:
        logger.exception("Необработанная ошибка при подготовке ответа")
        kb_manager.add_pending_question(user_id, username, question, msg.chat_id)
        reason = user_error_reason(e)
        answer = (
            f"❌ Причина: {reason}.\n\n"
            f"{UNAVAILABLE_MSG.get(lang, UNAVAILABLE_MSG['ru'])}"
        )
        source = "error"
    finally:
        stop_event.set()
        try:
            await progress_task
        except Exception:
            pass

    completed = "✅ Обработка завершена: 100%\n" + progress_bar(100)
    if source in {"error", "unavailable"}:
        completed = "⚠️ Обработка завершена без готового ответа: 100%\n" + progress_bar(100)
    try:
        await status_message.edit_text(completed)
    except Exception:
        pass

    source_labels = {
        "kb": "📚 База знаний",
        "web": "🌐 Веб-источник",
        "web_ai": "🌐 Внешний поиск + AI",
        "ai": "🤖 AI-ассистент",
        "unavailable": "⏳ Поставлено на обработку",
        "error": "❌ Ошибка обработки",
    }
    label = source_labels.get(source, "🤖 AI_Diag_UZ")
    # Добавляем имя AI системы в футер если источник — AI
    if source in {"ai", "web_ai"} and ai_source:
        label = f"{label} · {ai_source}"

    # ── Спойлер для длинных ответов (порог: 4 непустые строки) ─────────────
    # Строки 1–3 видны сразу. Строки 4+ скрыты под спойлером.
    # Используем MarkdownV2 ||скрытый текст|| — официальный spoiler синтаксис
    # Telegram Bot API v5.0+. Надёжнее чем HTML <tg-spoiler>.
    #
    # Экранирование MarkdownV2: символы _ * [ ] ( ) ~ ` > # + - = | { } . !
    # должны быть экранированы обратным слешем если не являются форматированием.

    SPOILER_THRESHOLD = 4  # минимум непустых строк для сворачивания

    def _esc_html(t: str) -> str:
        """Экранирует спецсимволы HTML."""
        return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _md_to_html(line: str) -> str:
        """Конвертирует простой Markdown в HTML для Telegram."""
        line = _esc_html(line)
        # *жирный* → <b>жирный</b>
        line = re.sub(r"(?<![•\-])\*(?!\s)(.+?)(?<!\s)\*", r"<b>\1</b>", line)
        # _курсив_ → <i>курсив</i>
        line = re.sub(r"_(?!\s)(.+?)(?<!\s)_", r"<i>\1</i>", line)
        # `код` → <code>код</code>
        line = re.sub(r"`(.+?)`", r"<code>\1</code>", line)
        return line

    non_empty_lines = [ln for ln in answer.splitlines() if ln.strip()]
    all_lines = answer.splitlines()

    if len(non_empty_lines) >= SPOILER_THRESHOLD and source not in {"error", "unavailable"}:
        # Первые 3 непустые строки — видны сразу (preview)
        # Строки 4+ — свёрнуты под кнопку ▼ (expandable blockquote)
        #
        # Telegram expandable blockquote (Bot API 7.4+):
        # <blockquote expandable>текст</blockquote>
        # Показывает ~3 строки, остальное под кнопкой ▼ — пользователь нажимает чтобы раскрыть.
        # Это НЕ blur/размытие — текст виден в превью, просто обрезан.
        preview_count = 0
        split_idx = 0
        for i, line in enumerate(all_lines):
            if line.strip():
                preview_count += 1
            if preview_count == 3:
                split_idx = i + 1
                break

        preview_html = "\n".join(_md_to_html(l) for l in all_lines[:split_idx])
        hidden_html  = "\n".join(_md_to_html(l) for l in all_lines[split_idx:])
        footer_html  = f"\n\n<i>{_esc_html(label)} · AI_Diag_UZ · Уста</i>"

        html_body = (
            f"{preview_html}\n"
            f"<blockquote expandable>{hidden_html}</blockquote>"
            f"{footer_html}"
        )
        try:
            await msg.reply_text(html_body, parse_mode=ParseMode.HTML)
            if source not in {"error", "unavailable", "file"}:
                await send_combined_rating_buttons(
                    msg, question, answer, user_id, username, msg.chat_id, lang
                )
            return
        except Exception as html_err:
            logger.warning(f"HTML expandable blockquote отклонён: {html_err}")

    # ── Короткий ответ или fallback ───────────────────────────────────────────
    markdown_footer = f"\n\n_{label} · AI_Diag_UZ · Уста_"
    plain_footer    = f"\n\n{label} · AI_Diag_UZ · Уста"
    try:
        await msg.reply_text(answer + markdown_footer, parse_mode=ParseMode.MARKDOWN)
        if source not in {"error", "unavailable", "file"}:
            await send_combined_rating_buttons(
                msg, question, answer, user_id, username, msg.chat_id, lang
            )
    except Exception as markdown_error:
        logger.warning(f"Markdown отклонён: {markdown_error}")
        try:
            await msg.reply_text(answer + plain_footer)
        except Exception:
            logger.exception("Не удалось отправить ответ пользователю")


async def handle_channel_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Обработчик сообщений в канале и группах.

    Вызывается для КАЖДОГО текстового сообщения в канале/группе,
    но реагирует ТОЛЬКО если сообщение содержит триггер-обращение.

    Аргументы:
        update:  объект с информацией о новом событии в Telegram
        context: контекст выполнения (данные бота, очередь задач и т.д.)
    """
    # Получаем объект сообщения.
    # В каналах сообщения приходят как channel_post, в группах — как message
    msg: Message = update.message or update.channel_post

    # Если сообщения нет или оно не текстовое — ничего не делаем
    if not msg or not msg.text:
        return

    text = msg.text.strip()  # Убираем лишние пробелы по краям

    if not is_chat_allowed(msg.chat.id):
        return

    # Получаем информацию об отправителе
    user     = msg.from_user             # Объект пользователя Telegram
    user_id  = user.id if user else msg.chat.id          # Числовой ID
    username = user.username if user else str(msg.chat.id) # @username
    # ── Безопасность ─────────────────────────────────────────────────────────
    if is_blacklisted(user_id):
        logger.info(f"Игнорирую заблокированного | user_id={user_id}")
        return
    allowed_req, rate_reason = rate_check(user_id)
    if not allowed_req:
        remaining = rate_reason.split(":")[1] if ":" in rate_reason else "60"
        try:
            await msg.reply_text(
                f"⏱️ Слишком много запросов. Подождите {remaining} сек."
            )
        except Exception:
            pass
        return
    # ────────────────────────────────────────────────────────────────────────

    has_trigger = contains_trigger(text)
    assumed_lang = None
    if not has_trigger:
        assumed_lang = consume_waiting_question(msg.chat.id, user_id)
        if assumed_lang is None:
            return

    question = extract_question(text) if has_trigger else text
    # После получения настоящего вопроса язык определяется повторно. Для
    # неопределённой латиницы detect_language исходит из узбекского языка.
    lang = detect_language(question)
    if assumed_lang and not question.strip():
        lang = assumed_lang

    logger.info(
        f"Сообщение боту | user_id={user_id} | lang={lang} | "
        f"trigger={has_trigger} | "
        f"вопрос='{question[:80]}'"
    )

    if has_trigger and is_dialog_intro(question):
        wait_for_question(msg.chat.id, user_id, lang)
        listening = LISTEN_MSG.get(lang, LISTEN_MSG["ru"])
        try:
            await msg.reply_text(listening)
        except Exception:
            logger.exception("Не удалось отправить приглашение задать вопрос")
        return

    if has_trigger:
        awaiting_questions.pop(conversation_key(msg.chat.id, user_id), None)

    await process_user_question(
        msg, context, user_id, username, question, lang
    )


async def handle_private_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Обработчик личных сообщений боту (в личке).

    В отличие от канала — в личке бот отвечает на ЛЮБОЕ сообщение,
    без требования написать «Уста». Удобно для тестирования и
    прямого общения администраторов с ботом.

    Аргументы:
        update:  объект события Telegram
        context: контекст выполнения
    """
    msg = update.message
    if not msg or not msg.text:
        return

    user = msg.from_user
    text = msg.text.strip()

    # Проверки безопасности для личных сообщений
    if user and is_blacklisted(user.id):
        return
    if user:
        allowed, reason = rate_check(user.id)
        if not allowed:
            remaining = reason.split(":")[1] if ":" in reason else "60"
            await msg.reply_text(f"⏱️ Слишком много запросов. Подождите {remaining} сек.")
            return

    private_question = extract_question(text)
    # Сначала убираем обращение, затем определяем язык самого вопроса.
    lang = detect_language(private_question)

    if is_dialog_intro(private_question):
        wait_for_question(msg.chat.id, user.id, lang)
        await msg.reply_text(LISTEN_MSG.get(lang, LISTEN_MSG["ru"]))
        return

    awaiting_questions.pop(conversation_key(msg.chat.id, user.id), None)
    await process_user_question(
        msg,
        context,
        user.id,
        user.username or str(user.id),
        private_question,
        lang,
    )


# ==============================================================================
#  КОМАНДЫ БОТА
#
#  Команды — это специальные сообщения начинающиеся с "/" (слэша).
#  Например: /start, /help, /error E-04
#  Они обрабатываются отдельно от обычных сообщений.
# ==============================================================================

async def cmd_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Обработчик команды /start
    Вызывается когда пользователь впервые открывает бота или нажимает Start.
    Показывает приветственное сообщение и инструкцию.
    """
    u = update.effective_user  # effective_user — работает и в группах и в личке

    # Для администраторов добавляем специальную подсказку
    admin_note = "\n\n🔑 *Вы — администратор.* /admin" if is_admin(u.id) else ""

    text = (
        f"👋 Привет, *{u.first_name}*\\!\n\n"  # Экранируем ! для Markdown V2
        "🔧 Технический помощник *AI_Diag_UZ — Уста*\n\n"
        "Помогаю с ГБО и диагностикой легковых и грузовых автомобилей\\.\n\n"
        "Бот: *@cardiagUZ\\_bot*\n\n"
        "*Как обращаться в группе:*\n"
        "`Уста, Chevrolet Cobalt P0171 — с чего начать?`\n"
        "`Usta, MAN TGX SPN 5246 FMI 0 nimani bildiradi?`\n\n"
        "Работаю на 4 языках:\n"
        "🇷🇺 Русский \\(кириллица и транслит\\)\n"
        "🇺🇿 O'zbek \\(lotin va kirill\\)\n\n"
        "/help — все команды" + admin_note
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)


async def cmd_help(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Обработчик команды /help
    Показывает список всех доступных команд.
    Администраторы видят расширенный список.
    """
    text = (
        "📖 *Команды бота:*\n\n"
        "/start — Приветствие и инструкция\n"
        "/help — Эта справка\n"
        "/reset — Сбросить историю диалога\n"
        "/stats — Статистика базы знаний\n"
        "/search [запрос] — Поиск по базе знаний\n"
        "/dtc P0420 — Диагностика по коду неисправности\n"
        "/error E-04 — Совместимая команда для кодов ГБО\n"
    )
    # Для администраторов добавляем их команды
    if is_admin(update.effective_user.id):
        text += (
            "\n*🔑 Команды администратора:*\n"
            "/admin — Панель управления (меню)\n"
            "/pending — Просмотр вопросов для самообучения\n"
            "/sync — Синхронизация базы знаний с GitHub\n"
        )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_reset(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Обработчик команды /reset
    Очищает историю диалога пользователя.
    Полезно если AI "запутался" и даёт неверные ответы.
    """
    clear_history(update.effective_chat.id, update.effective_user.id)
    await update.message.reply_text(
        "🔄 История диалога сброшена! Начинаем с чистого листа."
    )


async def cmd_stats(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Обработчик команды /stats
    Показывает статистику базы знаний: количество записей, категории,
    время последней синхронизации с GitHub.
    """
    s = kb_manager.stats  # Получаем статистику от менеджера базы знаний

    # Формируем список категорий с количеством записей
    cats = "\n".join(
        f"  • {category}: {count}"
        for category, count in s["categories"].items()
    )

    text = (
        f"📊 *База знаний AI_Diag_UZ:*\n\n"
        f"📝 Записей: *{s['total_entries']}*\n"
        f"⏳ Ожидают проверки: *{s['pending_new']}*\n"
        f"🔄 Последняя синхр.: `{s['last_sync'][:16] if s['last_sync'] != '—' else '—'}`\n\n"
        f"*По категориям:*\n{cats or '  — пусто —'}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_search(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Обработчик команды /search [запрос]
    Ищет записи в базе знаний по семантическому совпадению.
    Показывает топ-3 найденных результата с процентом совпадения.

    Пример: /search давление газа не нормальное
    """
    # context.args — список аргументов команды (слова после /search)
    if not context.args:
        await update.message.reply_text(
            "Использование: `/search давление газа`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Объединяем все слова аргументов в один запрос
    query = " ".join(context.args)

    # Ищем в базе знаний
    results = kb_manager.search(query)

    if not results:
        await update.message.reply_text(
            "❌ Ничего не найдено в базе знаний по этому запросу."
        )
        return

    # Формируем список результатов
    lines = [f"🔍 *Результаты поиска:* `{query}`\n"]
    for i, r in enumerate(results, 1):
        e = r["entry"]                      # Запись из базы знаний
        pct = int(r["score"] * 100)         # Процент совпадения
        lines.append(
            f"*{i}. {e['question']}* ({pct}%)\n"
            f"_{e.get('category', '')}_ \n"
        )

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN
    )


async def cmd_error(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Обработчик команды /error [код]
    Быстрая расшифровка кода ошибки (OBD/STAG/CAN и др.).
    Автоматически определяет язык по контексту.

    Примеры:
        /error E-04    — ошибка инжектора цилиндра №1
        /error E-12    — нет сигнала RPM
        /error 15      — тоже работает (добавит "E-" автоматически)
    """
    if not context.args:
        await update.message.reply_text(
            "Использование: `/dtc P0420`\n"
            "Для ГБО также доступно: `/error E-04`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Объединяем аргументы и приводим к верхнему регистру
    code = " ".join(context.args).upper()

    # Определяем язык из текста команды
    lang = detect_language(update.message.text or "")

    await process_user_question(
        update.message,
        context,
        update.effective_user.id,
        update.effective_user.username or str(update.effective_user.id),
        f"Что означает код неисправности {code} и как его диагностировать?",
        lang,
    )


# ==============================================================================
#  КОМАНДЫ АДМИНИСТРАТОРА
#
#  Эти команды доступны только пользователям из списка TELEGRAM_ADMIN_IDS
#  (задаётся в config.py). Позволяют управлять базой знаний прямо из Telegram.
# ==============================================================================

async def cmd_admin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Обработчик команды /admin
    Показывает главное меню администратора с кнопками.
    Доступно только для администраторов.
    """
    # Проверяем права доступа
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ запрещён. Вы не администратор.")
        return

    # Получаем статистику для отображения в кнопках
    s = kb_manager.stats

    # Создаём клавиатуру с кнопками (InlineKeyboard)
    # Каждый внутренний список — это ряд кнопок
    # callback_data — идентификатор кнопки, передаётся в handle_callback
    keyboard = [
        [
            InlineKeyboardButton("📝 Записи БЗ",  callback_data="adm_list"),
            InlineKeyboardButton("➕ Добавить",    callback_data="adm_add"),
        ],
        [
            # Показываем количество ожидающих вопросов прямо в кнопке
            InlineKeyboardButton(
                f"⏳ На проверке ({s['pending_new']})",
                callback_data="adm_pending"
            ),
        ],
        [
            InlineKeyboardButton("🔄 Синхронизировать", callback_data="adm_sync"),
        ],
        [
            InlineKeyboardButton("📊 Статистика", callback_data="adm_stats"),
        ],
    ]

    await update.message.reply_text(
        "🔑 *Панель администратора*\n\n"
        "Веб-админка: `http://localhost:8080`\n"
        "_(Откройте браузер на этом ПК)_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def cmd_pending(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Обработчик команды /pending
    Показывает список вопросов, на которые бот не нашёл ответа в базе знаний.
    Администратор может добавить лучшие вопросы в базу знаний (самообучение).
    """
    if not is_admin(update.effective_user.id):
        return  # Молча игнорируем для не-администраторов

    # Фильтруем только новые (ещё не просмотренные) вопросы
    pending = [p for p in kb_manager.get_pending() if p["status"] == "new"]

    if not pending:
        await update.message.reply_text("✅ Нет новых вопросов для проверки!")
        return

    # Показываем первые 5 вопросов (чтобы не спамить)
    for p in pending[:5]:
        # Кнопки для каждого вопроса
        keyboard = [[
            InlineKeyboardButton(
                "✅ Добавить в БЗ",
                callback_data=f"pend_add_{p['id']}"  # ID вопроса в callback
            ),
            InlineKeyboardButton(
                "❌ Отклонить",
                callback_data=f"pend_rej_{p['id']}"
            ),
        ]]

        await update.message.reply_text(
            f"❓ *Вопрос без ответа в БЗ:*\n"
            f"`{p['message_text'][:200]}`\n\n"   # Первые 200 символов вопроса
            f"👤 Пользователь: `{p['username']}`\n"
            f"🕐 Время: {p['timestamp'][:16]}",   # Дата и время (без секунд)
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


async def cmd_sync(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Обработчик команды /sync
    Вручную запускает синхронизацию базы знаний с GitHub.
    Обычно синхронизация происходит автоматически каждый час,
    но иногда нужно сделать это немедленно (например, после добавления записей).
    """
    if not is_admin(update.effective_user.id):
        return

    # Отправляем сообщение "в процессе"
    msg = await update.message.reply_text("🔄 Синхронизация с GitHub...")

    # Запускаем синхронизацию
    ok = await kb_manager.sync_to_github()

    # Редактируем сообщение с результатом
    await msg.edit_text(
        "✅ База знаний успешно синхронизирована с GitHub!"
        if ok else
        "❌ Ошибка синхронизации. Проверьте GITHUB_TOKEN в config.py"
    )


async def handle_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Обработчик нажатий на inline-кнопки.
    Вызывается когда пользователь нажимает кнопку под сообщением бота.
    callback_data — идентификатор нажатой кнопки (задаётся при создании кнопки).
    """
    query = update.callback_query
    await query.answer()  # Подтверждаем получение нажатия (убирает "часики")

    data = query.data      # Получаем идентификатор нажатой кнопки

    # Проверяем права доступа
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return

    # Обрабатываем разные кнопки
    if data == "adm_stats":
        # Кнопка "Статистика"
        s = kb_manager.stats
        cats = "\n".join(
            f"  • {k}: {v}" for k, v in s["categories"].items()
        )
        await query.edit_message_text(
            f"📊 Записей: *{s['total_entries']}* | "
            f"На проверке: *{s['pending_new']}*\n"
            f"Синхр: `{s['last_sync'][:16]}`\n\n"
            f"Категории:\n{cats}",
            parse_mode=ParseMode.MARKDOWN,
        )

    elif data == "adm_sync":
        # Кнопка "Синхронизировать"
        await query.edit_message_text("🔄 Синхронизация...")
        ok = await kb_manager.sync_to_github()
        await query.edit_message_text(
            "✅ GitHub обновлён!" if ok else "❌ Ошибка синхронизации."
        )

    elif data == "adm_list":
        # Кнопка "Записи БЗ" — показываем последние 10 записей
        entries = kb_manager.get_all_entries()[:10]
        lines = ["📝 *Последние записи в БЗ:*\n"]
        for e in entries:
            # Обрезаем длинные вопросы до 55 символов
            lines.append(f"• `{e['id']}` — {e['question'][:55]}")
        lines.append(f"\n_Всего записей: {len(kb_manager.get_all_entries())}_")
        await query.edit_message_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "adm_pending":
        # Кнопка "На проверке" — показываем вопросы без ответов
        pending = [p for p in kb_manager.get_pending() if p["status"] == "new"]
        if not pending:
            await query.edit_message_text("✅ Нет новых вопросов!")
        else:
            lines = [f"⏳ *Вопросы на проверке ({len(pending)}):*\n"]
            for p in pending[:8]:
                lines.append(f"• `{p['message_text'][:80]}`")
            await query.edit_message_text(
                "\n".join(lines),
                parse_mode=ParseMode.MARKDOWN
            )

    elif data.startswith("pend_rej_"):
        # Кнопка "Отклонить" для конкретного вопроса
        pending_id = data.replace("pend_rej_", "")  # Извлекаем ID вопроса
        kb_manager.resolve_pending(pending_id, "rejected")
        await query.edit_message_text("❌ Вопрос отклонён и не будет добавлен в БЗ.")

    elif data.startswith("pend_add_"):
        # Кнопка "Добавить в БЗ" — отмечаем для добавления через веб-админку
        pending_id = data.replace("pend_add_", "")
        kb_manager.resolve_pending(pending_id, "reviewed")
        await query.edit_message_text(
            "✅ Отмечено для добавления в базу знаний.\n\n"
            "Откройте веб-админку чтобы написать ответ:\n"
            "`http://localhost:8080/pending`",
            parse_mode=ParseMode.MARKDOWN,
        )


# ==============================================================================
#  ОБРАБОТЧИК ФОТОГРАФИЙ
#
#  Обрабатывает изображения из чата:
#  - Скриншоты диагностических программ → OCR + анализ ошибок
#  - Фото автомобильных деталей и ГБО → идентификация и рекомендации
#
#  Бот реагирует на фото в двух случаях:
#  1. Фото отправлено в личку боту — всегда анализируем
#  2. Фото в канале/группе — только если есть подпись с триггером
#     («Уста, что это?» или просто «Уста»)
# ==============================================================================

async def handle_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Обработчик входящих фотографий.

    Telegram отправляет фото в нескольких размерах (thumbnail, medium, large).
    Мы берём самый большой вариант для лучшего качества OCR.

    Аргументы:
        update:  объект события Telegram с фотографией
        context: контекст выполнения бота
    """
    # Проверяем доступность модуля анализа изображений
    if not IMAGE_ANALYSIS_AVAILABLE:
        await update.effective_message.reply_text(
            "❌ Анализ изображений временно недоступен.\n"
            "Опишите проблему текстом — отвечу!"
        )
        return

    msg = update.message or update.channel_post
    if not msg:
        return

    # ── Проверка триггера для каналов/групп ──────────────────────────────────
    # В каналах и группах реагируем на фото ТОЛЬКО если есть подпись с триггером
    # В личке — реагируем на любое фото
    is_private = msg.chat.type == "private"
    caption = msg.caption or ""  # Подпись к фото (текст под изображением)

    # ── Получаем пользователя СРАЗУ — нужен для кэша фото ──────────────────
    user     = msg.from_user
    user_id  = user.id       if user else msg.chat.id
    username = user.username if user else str(msg.chat.id)

    if not is_private:
        if not is_chat_allowed(msg.chat.id):
            return
        # Если нет триггера — сохраняем фото в кэш и выходим тихо.
        # При следующем вопросе "Уста, что на этом фото?" бот найдёт его здесь.
        if not contains_trigger(caption):
            if msg.photo:
                recent_photos[(msg.chat.id, user_id)] = (
                    time.monotonic(), b"__pending__", caption
                )
                context.chat_data["last_photo_file_id"] = msg.photo[-1].file_id
                logger.info(f"Фото без триггера сохранено в кэш | chat={msg.chat.id}")
            return
        logger.info(f"Фото с триггером в группе: '{caption[:60]}'")
    else:
        logger.info("Фото в личке — анализируем без триггера")

    # Извлекаем вопрос и язык из подписи
    user_question = extract_question(caption) if caption else ""
    lang = detect_language(user_question) if user_question else "ru"

    # ── Скачиваем изображение из Telegram ────────────────────────────────────
    # msg.photo — список объектов PhotoSize (разные размеры одного фото)
    # [-1] — последний элемент = самое большое разрешение
    if not msg.photo:
        await msg.reply_text("❌ Не удалось получить изображение.")
        return

    photo_size = msg.photo[-1]   # Самое большое фото
    status_message = await msg.reply_text(progress_text(lang, 10))
    stop_event = asyncio.Event()
    progress_task = asyncio.create_task(
        animate_progress(status_message, stop_event, lang)
    )

    try:
        photo_file = await context.bot.get_file(photo_size.file_id)
        await context.bot.send_chat_action(
            chat_id=msg.chat_id,
            action=ChatAction.UPLOAD_PHOTO,
        )
        photo_bytes = bytes(await photo_file.download_as_bytearray())
        logger.info(
            f"Фото скачано: {len(photo_bytes)} байт "
            f"(размер: {photo_size.width}×{photo_size.height})"
        )
        # Сохраняем фото в кэш — последующий текстовый вопрос сможет его использовать
        save_recent_photo(msg.chat.id, user_id, photo_bytes, user_question)
        await context.bot.send_chat_action(
            chat_id=msg.chat_id,
            action=ChatAction.TYPING,
        )
        result = await image_analyzer.analyze_photo(
            photo_bytes=photo_bytes,
            lang=lang,
            user_question=user_question,
        )
    except Exception as e:
        logger.exception("Сбой обработки изображения")
        reason = user_error_reason(e)
        kb_manager.add_pending_question(
            user_id, username, f"[ФОТО] {user_question or 'Без подписи'}", msg.chat_id
        )
        stop_event.set()
        try:
            await progress_task
            await status_message.edit_text(
                f"⚠️ Анализ изображения завершён с ошибкой: 100%\n{progress_bar(100)}"
            )
        except Exception:
            pass
        await msg.reply_text(
            f"❌ Не удалось распознать содержимое изображения: {reason}.\n\n"
            "Пожалуйста, отправьте более чёткое изображение или введите вручную "
            "видимый текст, код ошибки и данные автомобиля. Вопрос сохранён для "
            "обработки; можно обратиться повторно через 24 часа."
        )
        return
    finally:
        if not stop_event.is_set():
            stop_event.set()
            try:
                await progress_task
            except Exception:
                pass

    # ── Формируем HTML ответа (СТРУКТУРА ЗАФИКСИРОВАНА — НЕ МЕНЯТЬ) ──────────
    # Строки 1-3 ответа видны сразу
    # Строки 4+ → expandable blockquote (▼)
    # Детали анализа изображения → отдельный expandable blockquote ПОСЛЕ ответа
    answer   = (result.get("answer") or "").strip()
    img_type = result.get("type", "unknown")
    if not answer:
        answer   = "❌ Содержимое изображения распознать не удалось."
        img_type = "error"

    type_labels = {
        "screenshot": "🖥️ OCR · Скриншот программы",
        "part":       "🔍 Идентификация автомобильной детали",
        "unknown":    "📷 Анализ изображения",
        "error":      "❌ Ошибка анализа",
    }
    footer = f"\n\n_{type_labels.get(img_type, '📷')} · AI_Diag_UZ · Уста_"

    if img_type != "error":
        kb_manager.add_pending_question(
            user_id, username,
            f"[ФОТО] {user_question or 'Анализ изображения'}",
            msg.chat_id,
        )

    ocr_details  = result.get("ocr_details", "")
    footer_label = type_labels.get(img_type, "📷")

    def _esc_p(t: str) -> str:
        return t.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

    ocr_block = ""
    if ocr_details:
        ocr_block = (
            f"\n\n<blockquote expandable>"
            f"<i>🔍 Детали анализа изображения:</i>\n{_esc_p(ocr_details)}"
            f"</blockquote>"
        )
    footer_html = f"\n\n<i>{_esc_p(footer_label)} · AI_Diag_UZ · Уста</i>"

    all_photo_lines = answer.splitlines()
    non_empty_photo = [l for l in all_photo_lines if l.strip()]

    if len(non_empty_photo) >= 4 and img_type != "error":
        preview_count = split_idx_p = 0
        for i, line in enumerate(all_photo_lines):
            if line.strip(): preview_count += 1
            if preview_count == 3:
                split_idx_p = i + 1
                break
        preview_ph = "\n".join(_esc_p(l) for l in all_photo_lines[:split_idx_p])
        hidden_ph  = "\n".join(_esc_p(l) for l in all_photo_lines[split_idx_p:])
        html_answer = (
            f"{preview_ph}\n"
            f"<blockquote expandable>{hidden_ph}</blockquote>"
            f"{ocr_block}{footer_html}"
        )
    else:
        html_answer = f"{_esc_p(answer)}{ocr_block}{footer_html}"

    # Отправляем ответ: сначала пробуем отредактировать status_message (1 сообщение)
    # Это убирает прогресс-бар и заменяет его ответом в том же сообщении
    answer_sent = False
    try:
        await status_message.edit_text(html_answer, parse_mode=ParseMode.HTML)
        answer_sent = True
    except Exception as e:
        logger.warning(f"edit_text не удался ({e}), отправляем новым сообщением")

    if not answer_sent:
        # Удаляем прогресс-бар и отправляем ответ отдельным сообщением
        try:
            await status_message.delete()
        except Exception:
            pass
        try:
            await msg.reply_text(html_answer, parse_mode=ParseMode.HTML)
        except Exception:
            try:
                await msg.reply_text(answer)
            except Exception:
                logger.exception("Ошибка отправки фото-ответа")

    # Кнопки оценки (объединённые — для пользователя и администратора)
    photo_q = user_question or caption or ""
    await send_combined_rating_buttons(
        msg, photo_q, answer, user_id, username, msg.chat_id, lang
    )


# ==============================================================================
#  ИНИЦИАЛИЗАЦИЯ И ЗАПУСК БОТА
# ==============================================================================

async def post_init(application: Application) -> None:
    """
    Функция инициализации — вызывается ОДИН РАЗ при запуске бота.
    Здесь мы:
    1. Загружаем базу знаний (сначала с GitHub, потом локально)
    2. Запускаем фоновую задачу периодической синхронизации
    """
    # Загружаем базу знаний
    await kb_manager.load()

    # Запускаем фоновую задачу синхронизации каждый час
    # asyncio.create_task() — запускает корутину "в фоне", не блокируя основной поток
    asyncio.create_task(kb_manager.periodic_sync(SYNC_INTERVAL_MINUTES))

    logger.info("✅ База знаний загружена, фоновая синхронизация запущена")




async def send_feedback_buttons(
    msg,
    context,
    question: str,
    answer: str,
    source: str,
    user_id: int,
    username: str,
    chat_id: int,
) -> None:
    """
    Отправляет кнопки обратной связи "Верно / Не верно" после ответа бота.

    Кнопки видны ВСЕМ но нажать могут только администраторы.
    При нажатии:
    - "Верно"    → вопрос+ответ сохраняются в базу знаний
    - "Не верно" → вопрос попадает в раздел "Ожидает корректировки"

    Данные передаются через callback_data в формате JSON-строки.
    Из-за ограничения Telegram (64 байта) используем короткие ключи.
    Полные данные сохраняем в pending_feedback словаре.
    """
    # Сохраняем данные для обработки callback
    import time as _time
    feedback_id = f"fb_{int(_time.monotonic() * 1000) % 999999}"
    pending_feedback[feedback_id] = {
        "question": question,
        "answer":   answer,
        "source":   source,
        "user_id":  user_id,
        "username": username,
        "chat_id":  chat_id,
    }

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Верно / To'g'ri",    callback_data=f"fb_ok:{feedback_id}"),
            InlineKeyboardButton("❌ Не верно / Noto'g'ri", callback_data=f"fb_bad:{feedback_id}"),
        ]
    ])

    FEEDBACK_PROMPT = {
        "ru":          "Оцените ответ (только для администраторов):",
        "uz_latin":    "Javobni baholang (faqat adminlar uchun):",
        "uz_cyrillic": "Жавобни баҳоланг (фақат админлар учун):",
        "ru_translit": "Otsenite otvet (tolko dlya adminov):",
    }

    # Определяем язык из pending_feedback если есть
    lang_fb = "ru"
    for v in pending_feedback.values():
        if v.get("chat_id") == chat_id:
            lang_fb = "uz_cyrillic" if "uz" in str(v.get("lang","")) else "ru"
            break

    # Используем send_message с chat_id — не reply_text
    # чтобы не падать если исходное сообщение изменено или удалено
    try:
        bot_obj = msg.get_bot()
        await bot_obj.send_message(
            chat_id=chat_id,
            text=FEEDBACK_PROMPT.get(lang_fb, FEEDBACK_PROMPT["ru"]),
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.warning(f"Не удалось отправить кнопки обратной связи: {e}")


async def handle_feedback_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """
    Обрабатывает нажатие кнопок "Верно" / "Не верно".

    Только администраторы могут нажимать кнопки.
    Остальные получают уведомление "Доступно только администраторам".
    """
    query = update.callback_query
    if not query:
        return

    await query.answer()  # Убираем "часики" на кнопке

    user_id = query.from_user.id

    # Проверяем что нажал администратор
    if not is_admin(user_id):
        await query.answer(
            "⛔ Только администраторы могут оценивать ответы.",
            show_alert=True,
        )
        return

    data = query.data  # "fb_ok:fb_123456" или "fb_bad:fb_123456"
    if not data or ":" not in data:
        return

    action, feedback_id = data.split(":", 1)
    fb = pending_feedback.pop(feedback_id, None)

    if not fb:
        await query.edit_message_text("⚠️ Данные сессии устарели. Начните заново.")
        return

    question = fb["question"]
    answer   = fb["answer"]
    username = fb.get("username", "unknown")
    chat_id  = fb.get("chat_id", 0)
    fb_user  = fb.get("user_id", 0)

    if action == "fb_ok":
        # ── "Верно" — сохраняем в базу знаний ───────────────────────────────
        try:
            # Определяем категорию по содержимому вопроса
            if any(k in question.lower() for k in ["e-0", "e-1", "e-2", "err "]):
                category = "ГБО - Коды ошибок"
            elif any(k in question.lower() for k in ["p0", "p1", "p2", "b0", "c0", "u0"]):
                category = "Автодиагностика - OBD коды"
            elif any(k in question.lower() for k in ["давлени", "редуктор", "рампа"]):
                category = "ГБО - Давление"
            elif any(k in question.lower() for k in ["программ", "software", "dastur", "скачать"]):
                category = "ГБО - Программное обеспечение"
            else:
                category = "Автодиагностика - Общее"

            # Генерируем ключевые слова из вопроса (первые 5 слов)
            import re as _re
            words = [w.lower() for w in _re.findall(r"[\w]{3,}", question)][:8]

            kb_manager.add_entry(
                question=question,
                answer=answer,
                category=category,
                keywords=words,
                source="admin_feedback",
            )
            logger.info(
                f"Обратная связь 'Верно': вопрос добавлен в БЗ | "
                f"admin={user_id} | вопрос='{question[:60]}'"
            )
            await query.edit_message_text(
                f"✅ Ответ сохранён в базу знаний\n"
                f"Категория: {category}\n"
                f"_Вопрос: {question[:80]}_",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            logger.error(f"Ошибка сохранения из обратной связи: {e}")
            await query.edit_message_text(f"❌ Ошибка сохранения: {e}")

    elif action == "fb_bad":
        # ── "Не верно" — отправляем в очередь корректировки ─────────────────
        try:
            kb_manager.add_pending_question(
                user_id=fb_user,
                username=username,
                message_text=f"[КОРРЕКТИРОВКА] {question}",
                chat_id=chat_id,
            )
            logger.info(
                f"Обратная связь 'Не верно': вопрос отправлен на корректировку | "
                f"admin={user_id} | вопрос='{question[:60]}'"
            )
            await query.edit_message_text(
                f"⚠️ Ответ отправлен на корректировку\n"
                f"Откройте веб-админку → 'На проверке' → 'Ожидает корректировки'\n"
                f"_Вопрос: {question[:80]}_",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            logger.error(f"Ошибка отправки на корректировку: {e}")
            await query.edit_message_text(f"❌ Ошибка: {e}")


async def cmd_files(update, context) -> None:
    """/files - список файлов в каталоге. Только для администраторов."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Dostup zapreshchen.")
        return
    if not FILE_MANAGER_AVAILABLE:
        await update.message.reply_text("file_manager.py ne naiden.")
        return
    files = get_all_files()
    if not files:
        await update.message.reply_text("Katalog faylov pust.")
        return
    lines = ["Katalog faylov:\n"]
    for fentry in files:
        if fentry.get("telegram_file_id"):
            status = "v Telegram"
        elif fentry.get("local_path") and os.path.exists(fentry.get("local_path", "")):
            status = "na diske"
        elif fentry.get("downloaded"):
            status = "skachan"
        else:
            status = "tolko ssylka"
        lines.append(f"- {fentry['id']}: {fentry['name']} | {status} | {fentry.get('category', '')}")
    lines.append(f"\nVsego: {len(files)} faylov")
    text = "\n".join(lines)
    try:
        await update.message.reply_text(text)
    except Exception as e:
        logger.error(f"cmd_files error: {e}")


async def cmd_addfile(update, context) -> None:
    """/addfile <url> <keywords> - dobavit fayl v katalog."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Dostup zapreshchen.")
        return
    if not FILE_MANAGER_AVAILABLE:
        await update.message.reply_text("file_manager.py ne naiden.")
        return
    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text(
            "Ispolzovanie:\n/addfile URL klyuch1,klyuch2,klyuch3\n\n"
            "Primer:\n/addfile https://ac.com.pl/files/stag400.exe stag-400,dpi,programma"
        )
        return
    url = args[0]
    keywords = [k.strip() for k in args[1].split(",") if k.strip()]
    filename = url.rstrip("/").split("/")[-1] or "file"
    name = filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").title()
    from file_manager import add_file_to_catalog, download_and_cache as _dl_cache
    new_id = add_file_to_catalog(
        name=name, filename=filename,
        description=f"Dobavleno administratorom iz {url}",
        keywords=keywords, source_url=url, category="software",
    )
    msg = await update.message.reply_text(f"Fayl dobavlen: {new_id}. Skachivayu...")
    entry = {"id": new_id, "filename": filename, "source_url": url}
    dl_path = await _dl_cache(entry)
    if dl_path:
        await msg.edit_text(f"Fayl {new_id} dobavlen i skachan: {dl_path}")
    else:
        await msg.edit_text(
            f"Fayl {new_id} dobavlen v katalog. "
            f"Avtoskachivanie ne udalos - skachaetsya pri pervom zaprose."
        )


async def cmd_block(update, context) -> None:
    """/block <user_id> - zablokirovat polzovatelya."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Dostup zapreshchen.")
        return
    if not context.args:
        await update.message.reply_text("Ispolzovanie: /block 123456789")
        return
    try:
        uid = int(context.args[0])
        block_user(uid)
        await update.message.reply_text(f"Polzovatel {uid} zablokirovan.")
    except ValueError:
        await update.message.reply_text("Nekorektnyy user_id (dolzhno byt chislo).")


async def cmd_unblock(update, context) -> None:
    """/unblock <user_id> - razblokirovat polzovatelya."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Dostup zapreshchen.")
        return
    if not context.args:
        await update.message.reply_text("Ispolzovanie: /unblock 123456789")
        return
    try:
        uid = int(context.args[0])
        if unblock_user(uid):
            await update.message.reply_text(f"Polzovatel {uid} razblokirovan.")
        else:
            await update.message.reply_text(f"Polzovatel {uid} ne byl zablokirovan.")
    except ValueError:
        await update.message.reply_text("Nekorektnyy user_id.")


async def cmd_blocklist(update, context) -> None:
    """/blocklist - spisok zablokirovannyh polzovateley."""
    if not is_admin(update.effective_user.id):
        return
    bl = get_blacklist()
    if not bl:
        await update.message.reply_text("Chernyy spisok pust.")
    else:
        count = len(bl)
        ids_str = ", ".join(str(uid) for uid in bl)
        await update.message.reply_text(f"Zablokirovano: {count}\n{ids_str}")


async def _analyze_cached_photo(
    msg,
    context,
    photo_bytes: bytes,
    question: str,
    lang: str,
    user_id: int,
    username: str,
    existing_status_msg=None,
) -> None:
    """
    Анализирует кэшированное фото с вопросом пользователя.
    Вызывается из process_user_question (ветка A) и handle_photo_confirm_callback.
    existing_status_msg: уже существующее сообщение-статус (не создаём новое).
    """

    ANALYZING_FRAMES = {
        "ru": [
            "🖼️ Анализирую фото ⏳",
            "🖼️ Анализирую фото ⏳⏳",
            "🖼️ Распознаю содержимое ⏳",
            "🖼️ Формирую ответ ⏳",
        ],
        "uz_cyrillic": [
            "🖼️ Расмни таҳлил қиламан ⏳",
            "🖼️ Мазмунни аниқлаяман ⏳⏳",
            "🖼️ Жавоб тайёрлаяман ⏳",
            "🖼️ Бир оз кутинг ⏳",
        ],
        "uz_latin": [
            "🖼️ Rasmni tahlil qilaman ⏳",
            "🖼️ Mazmunni aniqlayman ⏳⏳",
            "🖼️ Javob tayyorlayman ⏳",
            "🖼️ Bir oz kuting ⏳",
        ],
        "ru_translit": [
            "🖼️ Analiziruyu foto ⏳",
            "🖼️ Raspoznayu ⏳⏳",
            "🖼️ Formiruu otvet ⏳",
            "🖼️ Podozhdite ⏳",
        ],
    }
    frames = ANALYZING_FRAMES.get(lang, ANALYZING_FRAMES["ru"])

    # ВСЕГДА создаём новое сообщение прогресса через bot.send_message
    # existing_status_msg используется только чтобы знать chat_id
    # (старое сообщение с кнопками уже отредактировано — не трогаем его)
    _chat_id = msg.chat_id
    try:
        status = await msg.get_bot().send_message(
            chat_id=_chat_id,
            text=progress_text(lang, 10),
        )
    except Exception:
        status = await msg.reply_text(progress_text(lang, 10))

    # Анимация прогресса — используем единую animate_progress
    stop_event = asyncio.Event()
    progress_task = asyncio.create_task(animate_progress(status, stop_event, lang))

    # Выполняем анализ
    answer_ph = ""
    ocr_det   = ""
    img_type  = "unknown"
    try:
        result    = await image_analyzer.analyze_photo(
            photo_bytes=photo_bytes,
            lang=lang,
            user_question=question,
        )
        answer_ph = result.get("answer", "")
        ocr_det   = result.get("ocr_details", "")
        img_type  = result.get("type", "unknown")
    except Exception as e:
        logger.error(f"Ошибка анализа кэшированного фото: {e}")
    finally:
        stop_event.set()
        try:
            await progress_task
        except Exception:
            pass

    # Удаляем сообщение-статус
    try:
        await status.delete()
    except Exception:
        pass

    if not answer_ph:
        NO_RESULT = {
            "ru":          "❌ Не удалось проанализировать изображение. Попробуйте ещё раз.",
            "uz_cyrillic": "❌ Расмни таҳлил қилиб бўлмади. Қайта уриниб кўринг.",
            "uz_latin":    "❌ Rasmni tahlil qilib bo'lmadi. Qayta urinib ko'ring.",
            "ru_translit": "❌ Ne udalos analizirovat. Poprobuite eshhyo raz.",
        }
        try:
            await context.bot.send_message(
                chat_id=msg.chat_id,
                text=NO_RESULT.get(lang, NO_RESULT["ru"])
            )
        except Exception:
            pass
        return

    # ── Формируем ответ ───────────────────────────────────────────────────────
    # Структура: диагноз сразу → expandable blockquote для деталей →
    # отдельный blockquote для OCR данных (всегда после основного ответа)

    def _esc(t):
        return t.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

    all_lines = answer_ph.splitlines()
    non_empty = [l for l in all_lines if l.strip()]

    # OCR детали — ВСЕГДА отдельный blockquote ПОСЛЕ ответа
    ocr_block = ""
    if ocr_det:
        ocr_block = (
            f"\n\n<blockquote expandable>"
            f"<i>🔍 Детали анализа изображения:</i>\n{_esc(ocr_det)}"
            f"</blockquote>"
        )

    footer = f"\n\n<i>🖼️ AI_Diag_UZ · Уста</i>"

    if len(non_empty) >= 4:
        # Длинный ответ: первые 3 строки видны, остальное под ▼
        preview_count = split_idx = 0
        for i, line in enumerate(all_lines):
            if line.strip():
                preview_count += 1
            if preview_count == 3:
                split_idx = i + 1
                break
        preview_h = "\n".join(_esc(l) for l in all_lines[:split_idx])
        hidden_h  = "\n".join(_esc(l) for l in all_lines[split_idx:])
        html_body = (
            f"{preview_h}\n"
            f"<blockquote expandable>{hidden_h}</blockquote>"
            f"{ocr_block}{footer}"
        )
    else:
        # Короткий ответ: всё видно
        html_body = f"{_esc(answer_ph)}{ocr_block}{footer}"

    try:
        await context.bot.send_message(
            chat_id=msg.chat_id,
            text=html_body,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.warning(f"HTML не прошёл: {e}")
        try:
            await context.bot.send_message(chat_id=msg.chat_id, text=answer_ph)
        except Exception:
            logger.error("Не удалось отправить ответ на фото")
            return

    # Объединённые кнопки оценки
    await send_combined_rating_buttons(
        msg, question, answer_ph, user_id, username, msg.chat_id, lang
    )


async def handle_photo_confirm_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """
    Обрабатывает нажатие кнопок "Да, про это фото" / "Нет, другой вопрос".
    Вызывается когда бот уточнял связь между фото и вопросом.
    """
    query = update.callback_query
    if not query:
        return
    await query.answer()

    data = query.data  # "photo_yes:chat_id:user_id" или "photo_no:..."
    parts = data.split(":")
    if len(parts) < 3:
        return

    action   = parts[0]  # "photo_yes" или "photo_no"
    chat_id  = int(parts[1])
    user_id  = int(parts[2])
    key      = (chat_id, user_id)

    entry = pending_photo_questions.pop(key, None)

    if action == "photo_yes" and entry:
        _, photo_bytes, question, lang = entry
        user = query.from_user
        username = user.username if user else str(user_id)

        # Убираем кнопки (редактируем сообщение) — НЕ удаляем его,
        # чтобы избежать BadRequest при reply на несуществующее сообщение
        # Берём язык из записи кэша (язык в котором был задан вопрос)
        entry_lang = entry.get("lang", "ru") if isinstance(entry, dict) else lang
        PROCESSING = {
            "ru":          "🖼️ Анализирую фото...",
            "uz_latin":    "🖼️ Rasmni tahlil qilaman...",
            "uz_cyrillic": "🖼️ Расмни таҳлил қиламан...",
            "ru_translit": "🖼️ Analiziruyu foto...",
        }
        try:
            await query.edit_message_text(
                PROCESSING.get(entry_lang, PROCESSING["ru"])
            )
        except Exception:
            pass

        # Передаём существующее сообщение-статус (с текстом "Анализирую...")
        # чтобы _analyze_cached_photo не создавало ВТОРОЕ сообщение
        await _analyze_cached_photo(
            query.message, context, photo_bytes, question, entry_lang,
            user_id, username,
            existing_status_msg=query.message,
        )

    elif action == "photo_no":
        # Пользователь сказал "нет" — убираем кнопки и продолжаем обычный поиск
        try:
            await query.edit_message_text("✅ Хорошо, отвечаю на вопрос без фото.")
        except Exception:
            pass
        # pending_photo_questions уже очищен через pop выше
        # Бот ответит на следующий вопрос как обычный текстовый

    else:
        try:
            await query.edit_message_text("⚠️ Сессия истекла. Задайте вопрос заново.")
        except Exception:
            pass


async def send_satisfaction_buttons(
    msg,
    question: str,
    answer: str,
    user_id: int,
    username: str,
    chat_id: int,
    lang: str = "ru",
) -> None:
    """
    Отправляет кнопки оценки ответа пользователем после каждого ответа бота.

    Три кнопки:
    ✅ Спасибо/Rahmat         — ответ устраивает, сбрасываем контекст
    🔧 Нужно уточнить/Aniqlashtirish kerak — бот спросит что уточнить
    ❌ Ответ неверный/Noto'g'ri — бот попробует другой вариант (макс 2 попытки)

    Статистика нажатий фиксируется в базе знаний.
    """
    import time as _time
    btn_id = f"sat_{int(_time.monotonic() * 1000) % 9999999}"

    # Сохраняем контекст для обработки callback
    answer_attempts[(chat_id, user_id)] = {
        "question":  question,
        "answer":    answer,
        "attempts":  1,
        "btn_id":    btn_id,
        "lang":      lang,
        "username":  username,
    }

    PROMPT = {
        "ru":          "Вы удовлетворены ответом?",
        "uz_latin":    "Javobdan qoniqdingizmi?",
        "uz_cyrillic": "Жавобдан қониқдингизми?",
        "ru_translit": "Vy udovletvoreny otvetom?",
        "en":          "Are you satisfied with the answer?",
        "uk":          "Чи задоволені Ви відповіддю?",
        "be":          "Ці задаволены Вы адказам?",
        "de":          "Sind Sie mit der Antwort zufrieden?",
        "kk":          "Жауаппен қанағаттандыңыз ба?",
        "ky":          "Жооптон канааттандыңызбы?",
        "tg":          "Оё шумо аз ҷавоб қонеъ ҳастед?",
        "tk":          "Jogapdan razy boldyňyzmy?",
    }
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Спасибо / Rahmat",
                             callback_data=f"sat_ok:{btn_id}"),
    ], [
        InlineKeyboardButton("🔧 Уточнить / Aniqlashtirish",
                             callback_data=f"sat_clarify:{btn_id}"),
        InlineKeyboardButton("❌ Не верно / Noto'g'ri",
                             callback_data=f"sat_wrong:{btn_id}"),
    ]])
    try:
        bot_obj = msg.get_bot()
        await bot_obj.send_message(
            chat_id=chat_id,
            text=PROMPT.get(lang, PROMPT["ru"]),
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.warning(f"Не удалось отправить кнопки оценки: {e}")


async def handle_satisfaction_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """
    Обрабатывает нажатие кнопок оценки ответа.

    sat_ok      → сбрасываем контекст диалога, записываем статистику
    sat_clarify → просим уточнить вопрос
    sat_wrong   → попытка 1: ищем другой ответ; попытка 2: передаём админу
    """
    query = update.callback_query
    if not query:
        return
    await query.answer()

    data  = query.data
    parts = data.split(":", 1)
    if len(parts) < 2:
        return

    action = parts[0]
    btn_id = parts[1]
    user   = query.from_user
    user_id  = user.id
    chat_id  = query.message.chat_id
    key      = (chat_id, user_id)

    # Находим контекст по btn_id
    entry = None
    entry_key = None
    for k, v in list(answer_attempts.items()):
        if v.get("btn_id") == btn_id:
            entry     = v
            entry_key = k
            break

    if not entry:
        await query.answer("⚠️ Сессия истекла.", show_alert=True)
        return

    # ── Проверка доступа: только автор вопроса или администратор ─────────────
    # entry_key = (chat_id автора, user_id автора)
    # Сравниваем user_id нажавшего с user_id автора вопроса
    original_user_id = entry_key[1] if entry_key else 0
    if user_id != original_user_id and not is_admin(user_id):
        ACCESS_DENIED = {
            "ru":          "⛔ Эти кнопки доступны только автору вопроса.",
            "uz_latin":    "⛔ Bu tugmalar faqat savol muallifiga tegishli.",
            "uz_cyrillic": "⛔ Бу тугмалар фақат савол муаллифига тегишли.",
            "ru_translit": "⛔ Eti knopki dostupny tolko avtoru voprosa.",
        }
        lang_deny = entry.get("lang", "ru")
        await query.answer(
            ACCESS_DENIED.get(lang_deny, ACCESS_DENIED["ru"]),
            show_alert=True,
        )
        return

    key = entry_key  # используем ключ автора вопроса

    question = entry["question"]
    answer   = entry["answer"]
    attempts = entry["attempts"]
    lang     = entry.get("lang", "ru")
    username = entry.get("username", "")

    # Записываем статистику в базу знаний с меткой роли
    # admin_thanks / admin_clarify / admin_wrong — от администратора
    # thanks / clarify / wrong — от пользователя
    is_admin_user = is_admin(user_id)
    role_prefix   = "admin_" if is_admin_user else ""
    stat_key = {
        "sat_ok":      f"{role_prefix}thanks",
        "sat_clarify": f"{role_prefix}clarify",
        "sat_wrong":   f"{role_prefix}wrong",
    }.get(action)
    if stat_key:
        try:
            kb_manager.record_feedback(question, stat_key)
        except Exception as e:
            logger.warning(f"Ошибка записи статистики: {e}")
    logger.info(
        f"Оценка ответа: {action} от {'администратора' if is_admin_user else 'пользователя'} "
        f"| user_id={user_id} | вопрос='{question[:50]}'"
    )

    if action == "sat_ok":
        # ── "Спасибо" ─────────────────────────────────────────────────────────
        # Пользователь:      → вопрос+ответ добавляются в "На проверке" (pending)
        # Администратор:     → вопрос+ответ добавляются сразу в основную БЗ
        answer_attempts.pop(key, None)
        conv_key = conversation_key(chat_id, user_id)

        if is_admin_user:
            # Администратор — добавляем сразу в БЗ
            try:
                import re as _re
                kw = [w.lower() for w in question.split() if len(w) >= 3][:8]
                # Определяем категорию автоматически
                q_low = question.lower()
                if any(k in q_low for k in ["e-0","e-1","e-2","err "]):
                    cat = "ГБО - Коды ошибок"
                elif any(k in q_low for k in ["p0","p1","b0","c0","u0"]):
                    cat = "Автодиагностика - OBD коды"
                elif any(k in q_low for k in ["программ","software","dastur"]):
                    cat = "ГБО - Программное обеспечение"
                else:
                    cat = "Автодиагностика - Общее"
                kb_manager.add_entry(
                    category=cat,
                    question=question,
                    answer=answer,
                    keywords=kw,
                    source="admin_feedback",
                )
                THANKS_ADMIN = {
                    "ru":          "✅ Ответ добавлен в базу знаний. Спасибо!",
                    "uz_latin":    "✅ Javob bilimlar bazasiga qo'shildi. Rahmat!",
                    "uz_cyrillic": "✅ Жавоб билимлар базасига қўшилди. Раҳмат!",
                    "ru_translit": "✅ Otvet dobavlen v bazu. Spasibo!",
                }
                await query.edit_message_text(
                    THANKS_ADMIN.get(lang, THANKS_ADMIN["ru"])
                )
                logger.info(f"Администратор добавил ответ в БЗ: '{question[:50]}'")
            except Exception as e:
                logger.error(f"Ошибка добавления в БЗ: {e}")
                await query.edit_message_text("❌ Ошибка добавления в базу знаний.")
        else:
            # Пользователь — добавляем в pending (на проверку)
            try:
                kb_manager.add_pending_question(
                    user_id=user_id,
                    username=username,
                    message_text=f"[ОДОБРЕНО ПОЛЬЗОВАТЕЛЕМ] {question}",
                    chat_id=chat_id,
                )
                # Сохраняем ответ рядом с вопросом для последующей обработки
                pending = kb_manager._kb.get("pending_learning", [])
                for p in pending:
                    if p.get("message_text","").endswith(question):
                        p["ai_answer"] = answer
                        p["status"]    = "user_approved"
                        break
                await kb_manager._save_local()
                THANKS_USER = {
                    "ru":          "✅ Рад помочь! Ответ отправлен на проверку администратору.",
                    "uz_latin":    "✅ Yordam bera olganimdan xursandman! Javob administratorga yuborildi.",
                    "uz_cyrillic": "✅ Ёрдам бера олганимдан хурсандман! Жавоб администраторга юборилди.",
                    "ru_translit": "✅ Rad pomoch! Otvet otpravlen na proverku.",
                }
                await query.edit_message_text(
                    THANKS_USER.get(lang, THANKS_USER["ru"])
                )
                logger.info(f"Пользователь одобрил ответ → pending: '{question[:50]}'")
            except Exception as e:
                logger.error(f"Ошибка сохранения одобренного ответа: {e}")

        # Сбрасываем контекст диалога
        conversations.pop(conv_key, None)
        awaiting_questions.pop(conv_key, None)

    elif action == "sat_clarify":
        # ── "Уточнить" ────────────────────────────────────────────────────────
        # Пользователь:  → бот запрашивает уточнение БЕЗ триггера
        # Администратор: → вопрос+ответ добавляются в pending

        if is_admin_user:
            # Администратор — добавляем в pending для проверки
            try:
                kb_manager.add_pending_question(
                    user_id=user_id,
                    username=username,
                    message_text=f"[ТРЕБУЕТ УТОЧНЕНИЯ - ADMIN] {question}",
                    chat_id=chat_id,
                )
                for p in kb_manager._kb.get("pending_learning", []):
                    if p.get("message_text","").endswith(question):
                        p["ai_answer"] = answer
                        p["status"]    = "admin_needs_clarify"
                        break
                await kb_manager._save_local()
                CLARIFY_ADMIN = {
                    "ru":          "📋 Вопрос добавлен в раздел 'На проверке' с пометкой 'Требует уточнения'.",
                    "uz_latin":    "📋 Savol 'Ko'rib chiqish' bo'limiga 'Aniqlashtirish kerak' belgisi bilan qo'shildi.",
                    "uz_cyrillic": "📋 Савол 'Кўриб чиқиш' бўлимига 'Аниқлаштириш керак' белгиси билан қўшилди.",
                    "ru_translit": "📋 Vopros dobavlen v 'Na proverke' s pometkey.",
                }
                await query.edit_message_text(CLARIFY_ADMIN.get(lang, CLARIFY_ADMIN["ru"]))
                logger.info(f"Администратор пометил вопрос как 'требует уточнения'")
            except Exception as e:
                logger.error(f"Ошибка сохранения уточнения: {e}")
        else:
            # Пользователь — разрешаем задать уточняющий вопрос без триггера
            conv_key = conversation_key(chat_id, user_id)
            # Устанавливаем режим ожидания уточнения (без триггера)
            awaiting_questions[conv_key] = (time.monotonic(), lang)
            # Сохраняем контекст предыдущего вопроса
            clarify_context[(chat_id, user_id)] = {
                "original_question": question,
                "original_answer":   answer,
                "ts": time.monotonic(),
            }
            CLARIFY_USER = {
                "ru":          "🔧 Что именно нужно уточнить? Напишите дополнительные данные или уточняющий вопрос:",
                "uz_latin":    "🔧 Nimani aniqlashtirmoqchisiz? Qo'shimcha ma'lumot yoki savol yozing:",
                "uz_cyrillic": "🔧 Нимани аниқлаштирмоқчисиз? Қўшимча маълумот ёки савол ёзинг:",
                "ru_translit": "🔧 Chto utochnit? Napishite dopolnenie ili vopros:",
            }
            try:
                await query.edit_message_text(CLARIFY_USER.get(lang, CLARIFY_USER["ru"]))
            except Exception:
                pass
            logger.info(f"Пользователь запросил уточнение | chat={chat_id}")

    elif action == "sat_wrong":
        # ── "Ответ неверный" — пробуем другой вариант ───────────────────────
        answer_attempts.pop(key, None)

        if attempts >= 2:
            # Две попытки исчерпаны — передаём администратору
            GIVE_UP = {
                "ru": (
                    "😔 Я не смог найти правильный ответ.\n\n"
                    "Вопрос передан администратору для поиска правильного ответа.\n"
                    "Пожалуйста, обратитесь за ответом позже."
                ),
                "uz_latin": (
                    "😔 To'g'ri javobni topa olmadim.\n\n"
                    "Savol administrator tomonidan ko'rib chiqiladi.\n"
                    "Iltimos, keyinroq murojaat qiling."
                ),
                "uz_cyrillic": (
                    "😔 Тўғри жавобни топа олмадим.\n\n"
                    "Савол администратор томонидан кўриб чиқилади.\n"
                    "Илтимос, кейинроқ мурожаат қилинг."
                ),
                "ru_translit": (
                    "😔 Ne smog nayti pravilnyy otvet.\n\n"
                    "Vopros peredan administratoru. Obratites pozzhe."
                ),
            }
            try:
                await query.edit_message_text(GIVE_UP.get(lang, GIVE_UP["ru"]))
            except Exception:
                pass
            # Сохраняем в pending для обработки администратором
            try:
                kb_manager.add_pending_question(
                    user_id=user_id,
                    username=username,
                    message_text=f"[НЕВЕРНЫЙ ОТВЕТ x2] {question}",
                    chat_id=chat_id,
                )
            except Exception as e:
                logger.error(f"Ошибка сохранения в pending: {e}")
            return

        # Попытка 1: ищем другой ответ
        RETRY_MSG = {
            "ru":          "🔄 Ищу другой вариант ответа...",
            "uz_latin":    "🔄 Boshqa javob variantini qidiraman...",
            "uz_cyrillic": "🔄 Бошқа жавоб вариантини қидираман...",
            "ru_translit": "🔄 Ishu drugoy variant otveta...",
        }
        try:
            await query.edit_message_text(RETRY_MSG.get(lang, RETRY_MSG["ru"]))
        except Exception:
            pass

        # Повторяем поиск с пометкой "исключить предыдущий ответ"
        retry_question = f"{question} (другой вариант, предыдущий ответ не подошёл)"
        retry_answer, retry_source, retry_ai_source = await generate_answer(
            user_id=user_id,
            question=retry_question,
            lang=lang,
            username=username,
            chat_id=chat_id,
        )

        if retry_answer and retry_answer != answer:
            # Нашли другой ответ — отправляем с кнопками (попытка 2)
            entry["attempts"] = 2
            entry["answer"]   = retry_answer
            entry["btn_id"]   = f"sat_{int(time.monotonic() * 1000) % 9999999}"
            answer_attempts[(chat_id, user_id)] = entry

            try:
                await query.message.reply_text(
                    retry_answer,
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception:
                await query.message.reply_text(retry_answer)
            await send_combined_rating_buttons(
                query.message, question, retry_answer,
                user_id, username, chat_id, lang
            )
        else:
            # Другой ответ не найден — сразу передаём администратору
            entry["attempts"] = 2
            action = "sat_wrong"  # Имитируем вторую попытку
            GIVE_UP2 = {
                "ru": (
                    "😔 Другого варианта ответа не найдено.\n\n"
                    "Вопрос передан администратору для поиска правильного ответа.\n"
                    "Пожалуйста, обратитесь за ответом позже."
                ),
                "uz_latin": (
                    "😔 Boshqa javob topilmadi.\n\n"
                    "Savol administratorga uzatildi. Keyinroq murojaat qiling."
                ),
                "uz_cyrillic": (
                    "😔 Бошқа жавоб топилмади.\n\n"
                    "Савол администраторга узатилди. Кейинроқ мурожаат қилинг."
                ),
                "ru_translit": (
                    "😔 Drugoy variant ne naiden.\n\n"
                    "Vopros peredan administratoru. Obratites pozzhe."
                ),
            }
            try:
                await query.message.reply_text(GIVE_UP2.get(lang, GIVE_UP2["ru"]))
            except Exception:
                pass
            try:
                kb_manager.add_pending_question(
                    user_id=user_id, username=username,
                    message_text=f"[НЕВЕРНЫЙ ОТВЕТ] {question}",
                    chat_id=chat_id, ai_answer=answer,
                )
            except Exception as e:
                logger.error(f"Ошибка сохранения в pending: {e}")


async def send_combined_rating_buttons(
    msg,
    question: str,
    answer: str,
    user_id: int,
    username: str,
    chat_id: int,
    lang: str = "ru",
) -> None:
    """
    Единая форма оценки ответа — 3 кнопки в одном сообщении.
    Доступна автору вопроса и администратору.
    При нажатии фиксируется роль (admin/user) в статистике БЗ.

    Заменяет send_satisfaction_buttons + send_feedback_buttons.
    """
    import time as _time
    btn_id = f"sat_{int(_time.monotonic() * 1000) % 9999999}"

    answer_attempts[(chat_id, user_id)] = {
        "question":  question,
        "answer":    answer,
        "attempts":  1,
        "btn_id":    btn_id,
        "lang":      lang,
        "username":  username,
        "user_id":   user_id,
    }

    PROMPT = {
        "ru":          "Вы удовлетворены ответом?",
        "uz_latin":    "Javobdan qoniqdingizmi?",
        "uz_cyrillic": "Жавобдан қониқдингизми?",
        "ru_translit": "Vy udovletvoreny otvetom?",
        "en":          "Are you satisfied with the answer?",
        "uk":          "Чи задоволені Ви відповіддю?",
        "be":          "Ці задаволены Вы адказам?",
        "de":          "Sind Sie mit der Antwort zufrieden?",
        "kk":          "Жауаппен қанағаттандыңыз ба?",
        "ky":          "Жооптон канааттандыңызбы?",
        "tg":          "Оё шумо аз ҷавоб қонеъ ҳастед?",
        "tk":          "Jogapdan razy boldyňyzmy?",
    }

    # Кнопки на языке пользователя
    BTN_OK = {
        "ru": "✅ Спасибо", "uz_latin": "✅ Rahmat",
        "uz_cyrillic": "✅ Rahmat", "ru_translit": "✅ Spasibo",
        "en": "✅ Thank you", "uk": "✅ Дякую",
        "be": "✅ Дзякуй", "de": "✅ Danke",
        "kk": "✅ Рақмет", "ky": "✅ Рахмат",
        "tg": "✅ Ташаккур", "tk": "✅ Sag boluň",
    }
    BTN_CLARIFY = {
        "ru": "🔧 Уточнить", "uz_latin": "🔧 Aniqlash",
        "uz_cyrillic": "🔧 Aniqlash", "ru_translit": "🔧 Utochnit",
        "en": "🔧 Clarify", "uk": "🔧 Уточнити",
        "be": "🔧 Удакладніць", "de": "🔧 Klären",
        "kk": "🔧 Нақтылау", "ky": "🔧 Тактоо",
        "tg": "🔧 Равшан кунед", "tk": "🔧 Anyklamak",
    }
    BTN_WRONG = {
        "ru": "❌ Не верно", "uz_latin": "❌ Noto'g'ri",
        "uz_cyrillic": "❌ Noto'g'ri", "ru_translit": "❌ Ne verno",
        "en": "❌ Incorrect", "uk": "❌ Невірно",
        "be": "❌ Няверна", "de": "❌ Falsch",
        "kk": "❌ Қате", "ky": "❌ Туура эмес",
        "tg": "❌ Нодуруст", "tk": "❌ Nädogry",
    }
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                BTN_OK.get(lang, BTN_OK["ru"]),
                callback_data=f"sat_ok:{btn_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                BTN_CLARIFY.get(lang, BTN_CLARIFY["ru"]),
                callback_data=f"sat_clarify:{btn_id}",
            ),
            InlineKeyboardButton(
                BTN_WRONG.get(lang, BTN_WRONG["ru"]),
                callback_data=f"sat_wrong:{btn_id}",
            ),
        ],
    ])

    try:
        bot_obj = msg.get_bot()
        await bot_obj.send_message(
            chat_id=chat_id,
            text=PROMPT.get(lang, PROMPT["ru"]),
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.warning(f"Не удалось отправить кнопки оценки: {e}")



async def handle_file_reply_add(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    msg  = update.message or update.channel_post
    user = msg.from_user
    if not user or not is_admin(user.id):
        return
    text = (msg.text or msg.caption or "").lower()
    # Триггерные фразы на русском, узбекском и транслите
    TRIGGERS = [
        # Русский
        "добавь файл", "добавить файл", "сохрани файл", "сохранить файл",
        "закинь файл", "закинь в базу", "сохрани в базу", "сохранить в базу",
        "файл в базу", "пополни базу", "добавь в базу", "добавить в базу",
        "занеси файл", "загрузи файл",
        # Узбекский латиница
        "fayl qo'sh", "bazaga qo'sh", "faylni saqlа", "add file", "bazaga yukla",
        # Транслит
        "dobavj fayl", "dobavit fayl", "sohrani fayl", "zakin fayl", "fayl v bazu",
    ]
    if not any(t in text for t in TRIGGERS):
        return
    reply = msg.reply_to_message
    if not reply:
        await msg.reply_text("Ответьте на сообщение с файлом командой: добавь файл в базу")
        return
    file_obj = reply.document or reply.audio
    if not file_obj:
        await msg.reply_text("В том сообщении нет файла.")
        return
    filename  = getattr(file_obj, "file_name", None) or "file"
    file_size = getattr(file_obj, "file_size", 0) or 0
    from pathlib import Path
    cache_dir  = Path("files_cache")
    cache_dir.mkdir(exist_ok=True)
    local_path = str(cache_dir / filename)
    downloaded = False
    too_large  = False
    size_mb    = file_size // 1024 // 1024

    status = await msg.reply_text(
        f"⬇️ Скачиваю {filename} ({size_mb} MB)..."
    )

    # Функция прогресса — обновляем сообщение каждые 10%
    _last_pct = [0]
    async def _on_progress_pct(current: int, pct: int):
        if pct - _last_pct[0] >= 10:
            _last_pct[0] = pct
            bar = "▰" * (pct // 10) + "▱" * (10 - pct // 10)
            try:
                await status.edit_text(
                    f"⬇️ Скачиваю {filename}\n{pct}%  {bar}"
                )
            except Exception:
                pass

    async def _on_progress_bytes(current: int, total: int):
        if total:
            pct = int(current * 100 / total)
            await _on_progress_pct(current, pct)

    # ── Приоритет 1: Telethon (MTProto) — любой размер до 2GB ───────────────
    tg_dl_success = False
    try:
        from tg_downloader import download_file_by_message, is_available
        if await is_available() and msg.reply_to_message:
            await status.edit_text(
                f"⬇️ Скачиваю через MTProto: {filename} ({size_mb} MB)..."
            )
            dl = await download_file_by_message(
                chat_id    = msg.chat_id,
                message_id = msg.reply_to_message.message_id,
                filename   = filename,
                progress_callback = _on_progress_bytes,
            )
            if dl["success"]:
                local_path    = dl["local_path"]
                file_size     = dl["size_bytes"]
                downloaded    = True
                tg_dl_success = True
                logger.info(f"MTProto: скачан {filename} ({file_size // 1024 // 1024} MB)")
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"MTProto скачивание не удалось: {e}")

    # ── Приоритет 2: Bot API getFile (только файлы ≤ 20MB) ──────────────────
    if not tg_dl_success:
        try:
            tg_file = await context.bot.get_file(file_obj.file_id)
            data    = bytes(await tg_file.download_as_bytearray())
            Path(local_path).write_bytes(data)
            file_size  = len(data)
            downloaded = True
            logger.info(f"Bot API: скачан {filename} ({file_size // 1024} KB)")
        except Exception as e:
            # Файл слишком большой для Bot API — предлагаем ручной путь
            too_large = True
            err_str   = str(e)
            is_big    = "too big" in err_str.lower() or "file is too big" in err_str.lower()
            hint = (
                "Файл > 20 MB — Bot API не поддерживает скачивание таких файлов.\n"
                "Для автоматического скачивания настройте Telethon:\n"
                "Добавьте TG_API_ID и TG_API_HASH в config.py (my.telegram.org)"
            ) if is_big else f"Ошибка: {err_str}"

            await status.edit_text(
                f"⚠️ {filename} ({size_mb} MB) — не удалось скачать\n\n"
                f"{hint}\n\n"
                f"📋 Сейчас скопируйте файл вручную в:\n"
                f"C:\\stag_bot\\files_cache\\{filename}\n\n"
                f"Затем: панель → Файлы → Сканировать files_cache/\n\n"
                f"Заполните метаданные в форме ниже:"
            )
    pkey = f"pf_{user.id}"
    context.bot_data[pkey] = {
        "filename":       filename,
        "local_path":     local_path if downloaded else "",
        "file_id":        file_obj.file_id,
        "file_size":      file_size,
        "downloaded":     downloaded,
        "too_large":      too_large,
        "chat_id":        msg.chat_id,
        "form_msg_id":    status.message_id,
        "reply_msg_id":   reply.message_id,
        "trigger_msg_id": msg.message_id,
        "name":     filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").title(),
        "desc":     "",
        "keywords": "",
        "category": "software",
        "step":     "name",
    }
    size_s = f"{file_size // 1024} KB" if downloaded else f"{file_size // 1024 // 1024} MB (только метаданные)"
    warn   = "\n(файл > 50MB — скопируйте вручную в files_cache/)" if too_large else ""
    await status.edit_text(
        _form_text(context.bot_data[pkey], size_s, warn),
        parse_mode=ParseMode.HTML,
        reply_markup=_form_kb(context.bot_data[pkey], user.id),
    )


def _form_text(d: dict, size_s: str = "", warn: str = "") -> str:
    ICONS = {"software": "PC", "firmware": "FW", "manual": "DOC", "driver": "DRV"}
    step  = d.get("step", "name")
    if not size_s:
        size_s = f"{d['file_size'] // 1024} KB" if d["file_size"] else ""
    PROMPTS = {
        "name":     "\n<b>Шаг 1/4 — Название:</b>\nВведите название файла в поле ниже и отправьте:",
        "desc":     "\n<b>Шаг 2/4 — Описание:</b>\nВведите краткое описание и отправьте (или нажмите Пропустить):",
        "keywords": "\n<b>Шаг 3/4 — Ключевые слова:</b>\nВведите слова через запятую и отправьте (или нажмите Пропустить):\nПример: stag-400, dpi, dastur, programma",
        "category": "\n<b>Шаг 4/4 — Категория:</b>\nВыберите категорию кнопкой ниже:",
        "confirm":  "\n<b>Проверьте данные и нажмите Сохранить.</b>\nДля исправления нажмите нужную кнопку.",
    }
    name_s = d["name"] or "(не заполнено)"
    desc_s = d["desc"] or "(не заполнено)"
    kw_s   = d["keywords"] or "(не заполнено)"
    cat_s  = d["category"]
    rows = [
        "<b>Добавление файла в каталог</b>",
        "",
        f"Файл: <code>{d['filename']}</code> ({size_s}){warn}",
        "─────────────────────",
        f"Название:  {name_s}",
        f"Описание:  {desc_s}",
        f"Ключи:     {kw_s}",
        f"Категория: {cat_s}",
        "─────────────────────",
        PROMPTS.get(step, ""),
    ]
    return "\n".join(rows)


def _form_kb(d: dict, uid: int) -> InlineKeyboardMarkup:
    step = d.get("step", "name")
    if step == "name":
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("Далее ->", callback_data=f"pf_next:{uid}"),
            InlineKeyboardButton("X Отмена",  callback_data=f"pf_cancel:{uid}"),
        ]])
    elif step in ("desc", "keywords"):
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("<- Назад",    callback_data=f"pf_back:{uid}"),
            InlineKeyboardButton("Пропустить", callback_data=f"pf_next:{uid}"),
        ], [
            InlineKeyboardButton("X Отмена",    callback_data=f"pf_cancel:{uid}"),
        ]])
    elif step == "category":
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("PC  Software",  callback_data=f"pf_cat_software:{uid}"),
                InlineKeyboardButton("FW  Firmware",  callback_data=f"pf_cat_firmware:{uid}"),
            ],
            [
                InlineKeyboardButton("DOC Manual",    callback_data=f"pf_cat_manual:{uid}"),
                InlineKeyboardButton("DRV Driver",    callback_data=f"pf_cat_driver:{uid}"),
            ],
            [
                InlineKeyboardButton("<- Назад", callback_data=f"pf_back:{uid}"),
                InlineKeyboardButton("X Отмена", callback_data=f"pf_cancel:{uid}"),
            ],
        ])
    else:  # confirm
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Назв.",  callback_data=f"pf_edit_name:{uid}"),
                InlineKeyboardButton("Опис.",  callback_data=f"pf_edit_desc:{uid}"),
            ],
            [
                InlineKeyboardButton("Ключи",  callback_data=f"pf_edit_keywords:{uid}"),
                InlineKeyboardButton("Катег.", callback_data=f"pf_edit_cat:{uid}"),
            ],
            [
                InlineKeyboardButton("СОХРАНИТЬ", callback_data=f"pf_save:{uid}"),
            ],
            [
                InlineKeyboardButton("X Отмена", callback_data=f"pf_cancel:{uid}"),
            ],
        ])


async def handle_file_form_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("Только администраторы.", show_alert=True)
        return
    raw   = query.data
    parts = raw.split(":", 1)
    action = parts[0]
    uid    = int(parts[1]) if len(parts) > 1 else query.from_user.id
    pkey  = f"pf_{uid}"
    d     = context.bot_data.get(pkey)
    if not d:
        await query.edit_message_text("Сессия истекла. Повторите команду.")
        return

    STEP_ORDER = ["name", "desc", "keywords", "category", "confirm"]

    if action == "pf_next":
        idx = STEP_ORDER.index(d["step"]) if d["step"] in STEP_ORDER else 0
        d["step"] = STEP_ORDER[min(idx + 1, len(STEP_ORDER) - 1)]
        context.bot_data[pkey] = d

    elif action == "pf_back":
        idx = STEP_ORDER.index(d["step"]) if d["step"] in STEP_ORDER else 1
        d["step"] = STEP_ORDER[max(idx - 1, 0)]
        context.bot_data[pkey] = d

    elif action.startswith("pf_cat_"):
        d["category"] = action.replace("pf_cat_", "")
        d["step"]     = "confirm"
        context.bot_data[pkey] = d

    elif action == "pf_edit_name":
        d["step"] = "name"
        context.bot_data[pkey] = d

    elif action == "pf_edit_desc":
        d["step"] = "desc"
        context.bot_data[pkey] = d

    elif action == "pf_edit_keywords":
        d["step"] = "keywords"
        context.bot_data[pkey] = d

    elif action == "pf_edit_cat":
        d["step"] = "category"
        context.bot_data[pkey] = d

    elif action == "pf_save":
        await _pf_save(query, context, d, pkey, uid)
        return

    elif action == "pf_cancel":
        context.bot_data.pop(pkey, None)
        await query.edit_message_text("Добавление файла отменено.")
        return

    await query.edit_message_text(
        _form_text(d),
        parse_mode=ParseMode.HTML,
        reply_markup=_form_kb(d, uid),
    )


async def _pf_save(query, context, d: dict, pkey: str, uid: int) -> None:
    if FILE_MANAGER_AVAILABLE:
        try:
            from file_manager import add_file_to_catalog, _load_catalog, _save_catalog
            # keywords может быть строкой "слово1, слово2" — конвертируем в список
            kw_raw = d.get("keywords", "") or ""
            if isinstance(kw_raw, list):
                kws = [k.strip() for k in kw_raw if k.strip()]
            else:
                kws = [k.strip() for k in kw_raw.split(",") if k.strip()]
            # Если ключи не введены — генерируем из имени файла и названия
            if not kws:
                name_words = [w.lower() for w in d["name"].split() if len(w) > 2]
                file_words = [w.lower() for w in d["filename"].replace("-", " ").replace("_", " ").split() if len(w) > 2]
                kws = list(dict.fromkeys(name_words + file_words))[:8]
            new_id = add_file_to_catalog(
                name        = d["name"] or d["filename"],
                filename    = d["filename"],
                description = d["desc"] or "",
                keywords    = kws,
                source_url  = "",
                category    = d["category"],
            )
            catalog = _load_catalog()
            for e in catalog["files"]:
                if e["id"] == new_id:
                    e["local_path"]      = d["local_path"]
                    e["size_bytes"]      = d["file_size"]
                    e["downloaded"]      = d["downloaded"]
                    e["telegram_file_id"] = d["file_id"] if d["downloaded"] else None
                    break
            _save_catalog(catalog)
            logger.info(f"Файл добавлен: {new_id} {d['name']}")
        except Exception as e:
            await query.edit_message_text(f"Ошибка сохранения: {e}")
            return
    chat_id = d.get("chat_id")
    for mid_key in ("reply_msg_id", "trigger_msg_id"):
        try:
            if d.get(mid_key):
                await context.bot.delete_message(chat_id, d[mid_key])
        except Exception:
            pass
    context.bot_data.pop(pkey, None)
    kw_disp   = d.get("keywords","") or "(автоматически)"
    desc_disp = d.get("desc","")     or "(не указано)"
    result_parts = [
        "ФАЙЛ ДОБАВЛЕН В КАТАЛОГ",
        "",
        "Название:  " + d["name"],
        "Описание:  " + desc_disp,
        "Файл:      " + d["filename"],
        "Категория: " + d["category"],
        "Ключи:     " + kw_disp,
        "",
        "Сообщение с файлом удалено из чата.",
    ]
    await query.edit_message_text("\n".join(result_parts))


async def handle_file_metadata(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    msg  = update.message
    if not msg:
        return
    user = msg.from_user
    if not user or not is_admin(user.id):
        return
    pkey = f"pf_{user.id}"
    d    = context.bot_data.get(pkey)
    if not d:
        return
    step = d.get("step", "name")
    if step not in ("name", "desc", "keywords"):
        return
    text = (msg.text or "").strip()
    if not text:
        return
    if step == "name":
        d["name"]  = text
        d["step"]  = "desc"
    elif step == "desc":
        d["desc"]  = text
        d["step"]  = "keywords"
    elif step == "keywords":
        d["keywords"] = text
        d["step"]     = "category"
    context.bot_data[pkey] = d
    try:
        await msg.delete()
    except Exception:
        pass
    form_msg_id = d.get("form_msg_id")
    if form_msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id    = msg.chat_id,
                message_id = form_msg_id,
                text       = _form_text(d),
                parse_mode = ParseMode.HTML,
                reply_markup = _form_kb(d, user.id),
            )
            return
        except Exception:
            pass
    sent = await msg.reply_text(
        _form_text(d),
        parse_mode   = ParseMode.HTML,
        reply_markup = _form_kb(d, user.id),
    )
    d["form_msg_id"] = sent.message_id
    context.bot_data[pkey] = d



async def handle_application_error(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """
    Глобальный обработчик необработанных исключений.

    Разделяем ошибки на две категории:
    1. Сетевые / временные (NetworkError, ReadError, TimedOut) —
       бот просто молча перезапустит polling через несколько секунд.
       Сообщать пользователю об этом не нужно — он даже не заметит.
    2. Логические (все остальные) — сообщаем пользователю и логируем.
    """
    from telegram.error import NetworkError, TimedOut
    error = context.error

    # Сетевые / временные ошибки — НЕ баги бота, восстанавливаются сами.
    # Логируем как WARNING и выходим — пользователя не тревожим.
    from telegram.error import NetworkError, TimedOut, Conflict
    TRANSIENT_ERRORS = (NetworkError, TimedOut)
    if isinstance(error, TRANSIENT_ERRORS):
        logger.warning(f"Сетевая ошибка (auto-retry): {type(error).__name__}: {error}")
        return

    # ReadError — частный случай сетевого обрыва
    if error and "ReadError" in type(error).__name__:
        logger.warning(f"ReadError (auto-retry): {error}")
        return

    # Conflict: два экземпляра бота с одним токеном.
    # Нужно закрыть лишние окна start.bat и подождать 30 секунд.
    if isinstance(error, Conflict):
        logger.warning(
            "Конфликт: запущено два экземпляра бота с одним токеном! "
            "Закройте все окна start.bat, подождите 30 сек, запустите один."
        )
        return

    # Все остальные ошибки — логируем полный traceback
    logger.error(
        "Необработанная ошибка Telegram-обработчика",
        exc_info=(type(error), error, error.__traceback__) if error else None,
    )

    # Уведомляем пользователя только если есть сообщение-источник
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ Произошла внутренняя ошибка. Вопрос сохранён.\n"
                "Попробуйте переформулировать или обратитесь повторно через 24 часа."
            )
        except Exception:
            logger.exception("Не удалось отправить уведомление об ошибке")


def main() -> None:
    """
    Точка входа — главная функция запуска бота.
    Создаёт приложение, регистрирует обработчики и запускает polling.

    Polling (опрос) — режим работы бота, при котором он постоянно
    "спрашивает" сервер Telegram: "есть ли новые сообщения?"
    Альтернатива — webhook (Telegram сам присылает уведомления),
    но он требует публичный IP и SSL-сертификат.
    """
    # Настройка логирования
    logging.basicConfig(
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        level=logging.INFO,
        handlers=[
            logging.StreamHandler(),                              # Вывод в консоль
            logging.FileHandler("ai_diag_uz.log", encoding="utf-8"),
        ],
    )
    # httpx пишет полный URL Telegram Bot API, содержащий секретный токен.
    # Оставляем только предупреждения и ошибки, чтобы токен не попадал в лог.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    # Подавляем INFO/ERROR логи внутренних компонентов PTB.
    # "telegram.ext.Updater" пишет NetworkError/ReadError как ERROR —
    # это нормальные сетевые сбои которые PTB сам восстанавливает.
    # Переводим их в WARNING чтобы не засорять лог страшными ERROR.
    logging.getLogger("telegram.ext.Updater").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext.Application").setLevel(logging.WARNING)
    logging.getLogger("telegram.error").setLevel(logging.WARNING)

    # Создаём приложение бота
    # Application.builder() — паттерн "строитель" для создания объекта
    # .token() — токен бота (от @BotFather)
    # .post_init() — функция инициализации (см. выше)
    # .build() — создаём объект
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )
    app.add_error_handler(handle_application_error)
    # Обработчик кнопок обратной связи "Верно / Не верно"
    app.add_handler(CallbackQueryHandler(
        handle_feedback_callback,
        pattern=r"^fb_(ok|bad):"
    ))
    # Обработчик кнопок подтверждения фото
    app.add_handler(CallbackQueryHandler(
        handle_photo_confirm_callback,
        pattern=r"^photo_(yes|no):"
    ))
    # Обработчик формы метаданных файла
    app.add_handler(CallbackQueryHandler(
        handle_file_form_callback,
        pattern=r"^pf_"
    ))
    # Обработчик кнопок оценки ответа пользователем
    app.add_handler(CallbackQueryHandler(
        handle_satisfaction_callback,
        pattern=r"^sat_(ok|clarify|wrong):"
    ))

    # ── Регистрируем обработчики команд ──────────────────────────────────────
    # CommandHandler("start", handler) — вызывает handler при команде /start
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("help",    cmd_help))
    app.add_handler(CommandHandler("reset",   cmd_reset))
    app.add_handler(CommandHandler("stats",   cmd_stats))
    app.add_handler(CommandHandler("search",  cmd_search))
    app.add_handler(CommandHandler("dtc",     cmd_error))
    app.add_handler(CommandHandler("error",   cmd_error))
    app.add_handler(CommandHandler("admin",   cmd_admin))    # Только для админов
    app.add_handler(CommandHandler("pending", cmd_pending))  # Только для админов
    app.add_handler(CommandHandler("sync",    cmd_sync))     # Только для админов
    # Обработчик "добавь файл в базу" — ответ на сообщение с файлом
    from telegram.ext import filters as _filters
    app.add_handler(MessageHandler(
        _filters.REPLY & _filters.TEXT & _filters.ChatType.GROUPS,
        handle_file_reply_add,
    ))
    # Обработчик метаданных файла — высокий приоритет (group=-1)
    # Работает в ЛЮБОМ чате: группе, личке, канале
    # Активируется только если есть активная форма (pf_{user_id} в bot_data)
    app.add_handler(MessageHandler(
        _filters.TEXT & ~_filters.COMMAND,
        handle_file_metadata,
    ), group=-1)
    app.add_handler(CommandHandler("files",   cmd_files))    # Каталог файлов
    app.add_handler(CommandHandler("addfile",   cmd_addfile))  # Добавить файл
    app.add_handler(CommandHandler("block",     cmd_block))    # Заблокировать
    app.add_handler(CommandHandler("unblock",   cmd_unblock))  # Разблокировать
    app.add_handler(CommandHandler("blocklist", cmd_blocklist))# Список блок.

    # ── Регистрируем обработчик inline-кнопок ────────────────────────────────
    app.add_handler(CallbackQueryHandler(handle_callback))

    # ── Регистрируем обработчик сообщений в каналах/группах ──────────────────
    # filters.TEXT            — только текстовые сообщения
    # ~filters.COMMAND        — НЕ команды (исключаем /start и т.д.)
    # filters.ChatType.GROUPS — в группах
    # filters.ChatType.CHANNEL — в каналах
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND &
        (filters.ChatType.GROUPS | filters.ChatType.CHANNEL),
        handle_channel_message,
    ))

    # ── Регистрируем обработчик личных сообщений ─────────────────────────────
    # filters.ChatType.PRIVATE — только личные сообщения (не группы)
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        handle_private_message,
    ))

    # ── Регистрируем обработчик фотографий ───────────────────────────────────
    # filters.PHOTO — только сообщения с фотографиями
    # Обрабатывает ОБА типа чатов: личку И каналы/группы
    # В каналах/группах — только если в подписи есть «Уста» / "Usta"
    # В личке — любое фото
    app.add_handler(MessageHandler(
        filters.PHOTO,      # Любое сообщение содержащее фотографию
        handle_photo,       # Наш обработчик (см. выше)
    ))

    logger.info("🚀 AI_Diag_UZ · Уста запущен! Ожидаем сообщений...")

    # Запускаем polling — бот начинает проверять новые сообщения
    # allowed_updates=Update.ALL_TYPES — получать все типы обновлений
    # Увеличиваем таймауты polling для снижения частоты ReadError.
    # read_timeout=30  — сколько секунд ждать ответа от Telegram
    # write_timeout=30 — сколько секунд ждать при отправке
    # connect_timeout=15 — сколько секунд на установку соединения
    # pool_timeout=15   — сколько секунд ждать свободного соединения из пула
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        read_timeout=30,
        write_timeout=30,
        connect_timeout=15,
        pool_timeout=15,
    )


# ==============================================================================
#  ТОЧКА ВХОДА
#
#  Если файл запускается напрямую (python bot.py), а не импортируется —
#  вызываем функцию main()
# ==============================================================================
if __name__ == "__main__":
    main()
