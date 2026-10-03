# CHANGELOG — AI_Diag_UZ Bot

## [1.0.0] — 2026-10-03
### Базовая версия после аудита
- Первая зафиксированная версия
- Применены исправления из аудита стороннего программиста
- Установлены правила разработки (RULES.md)

### Открытые задачи (перенесены в v1.1.0)
- A1: auth_telethon — phone_code_hash
- A2: knowledge_manager — атомарная запись + save после мутаций
- A3: bot.py — 1 оставшийся bad kwarg, file_uploader не подключён
- B1: admin.py — 0.0.0.0, SHA256, XSS
- B2: file_manager.py — secure_filename
- B3: tg_downloader.py — receive_updates, is_authorized
- C1: main.py — ADMIN_DIR
- C3: requirements.txt — telethon
