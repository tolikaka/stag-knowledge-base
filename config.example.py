# ══════════════════════════════════════════════════════
#  AI_Diag_UZ · Уста — Конфигурация
#  1. Скопируйте файл: config.example.py → config.py
#  2. Заполните все значения ниже
# ══════════════════════════════════════════════════════

# ── Telegram ───────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN   = "ВАШ_ТОКЕН_БОТА"       # Получить у @BotFather → /newbot
TELEGRAM_BOT_USERNAME = "cardiagUZ_bot"        # Без символа @
TELEGRAM_CHANNEL_ID  = ""                       # Старое поле; можно оставить пустым
TELEGRAM_ADMIN_IDS   = [123456789, 987654321]  # user_id администраторов (узнать у @userinfobot)
# Пустой список = работать во всех группах, куда добавлен бот.
# Для ограничения перечислите числовые ID: [-1001111111111, -1002222222222]
ALLOWED_CHAT_IDS     = []

# ── Anthropic Claude ───────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = "ВАШ_ANTHROPIC_КЛЮЧ"      # console.anthropic.com → API Keys

# ── GitHub (облачное хранилище БЗ) ────────────────────────────────────────────
GITHUB_TOKEN     = "ВАШ_GITHUB_TOKEN"          # GitHub → Settings → Developer settings
                                               # → Personal access tokens → Generate new
GITHUB_REPO      = "username/ai-diag-uz-kb"    # Имя вашего репозитория
GITHUB_FILE_PATH = "knowledge_base.json"       # Путь к файлу в репозитории
GITHUB_BRANCH    = "main"

# ── Локальный файл БЗ ─────────────────────────────────────────────────────────
LOCAL_KB_PATH = "knowledge_base/knowledge_base.json"

# ── Синхронизация ─────────────────────────────────────────────────────────────
SYNC_INTERVAL_MINUTES = 60  # Синхронизация с GitHub каждые N минут

# ── Веб-админка ───────────────────────────────────────────────────────────────
ADMIN_HOST       = "0.0.0.0"   # 0.0.0.0 = доступна из сети; 127.0.0.1 = только локально
ADMIN_PORT       = 8080
ADMIN_SECRET_KEY = "ЗАМЕНИТЕ_НА_СЛУЧАЙНУЮ_СТРОКУ_НЕ_МЕНЕЕ_32_СИМВОЛОВ"

# Логины и пароли администраторов.
# Хэш пароля генерируется так (запустите в cmd):
#   python -c "import hashlib; print(hashlib.sha256('ВАШ_ПАРОЛЬ'.encode()).hexdigest())"
ADMIN_USERS = {
    "admin": "ВСТАВЬТЕ_SHA256_ХЭШ_ВАШЕГО_ПАРОЛЯ",
}

# ── Пороги поиска в БЗ ────────────────────────────────────────────────────────
SIMILARITY_THRESHOLD = 0.45  # Минимальное семантическое совпадение (0.0–1.0)
TOP_K_RESULTS        = 3     # Сколько результатов возвращать из БЗ


# БЕСПЛАТНЫЕ AI
GROQ_API_KEY = ""
GEMINI_API_KEY = ""
DEEPSEEK_API_KEY = ""
KIMI_API_KEY = ""
