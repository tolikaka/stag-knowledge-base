"""
admin.py — Веб-админка базы знаний AI_Diag_UZ
• Flask + Bootstrap 5
• Авторизация по логину/паролю
• CRUD для записей БЗ
• Просмотр и обработка "pending" (самообучение)
• Ручная синхронизация с GitHub
• Доступна по http://localhost:8080
  Для внешнего доступа: используйте ngrok или Cloudflare Tunnel
"""

import hashlib
import json
import asyncio
import sys
import os
import secrets
from functools import wraps
from datetime import datetime

# Корневая папка бота (где лежит admin.py)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from flask import (
    Flask, render_template_string, request, redirect, url_for,
    session, flash, jsonify,
)
from knowledge_manager import kb_manager

# ── Конфиг ────────────────────────────────────────────────────────────────────
try:
    from config import ADMIN_SECRET_KEY, ADMIN_USERS, ADMIN_HOST, ADMIN_PORT
except ImportError:
    ADMIN_SECRET_KEY = os.environ.get("ADMIN_SECRET_KEY") or secrets.token_hex(32)
    ADMIN_USERS = {}
    ADMIN_HOST = "127.0.0.1"  # Только локальный доступ (аудит C4)
    ADMIN_PORT = 8080

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 4 * 1024 * 1024 * 1024  # 4 GB макс. для веб-загрузки
app.secret_key = ADMIN_SECRET_KEY

# ── Auth ──────────────────────────────────────────────────────────────────────
def hash_password(pw: str) -> str:
    import hmac as _hmac
    _key = (app.secret_key if isinstance(app.secret_key, bytes)
            else app.secret_key.encode())
    return _hmac.new(_key, pw.encode(), 'sha256').hexdigest()

def check_auth(username: str, password: str) -> bool:
    expected = ADMIN_USERS.get(username)
    return expected is not None and expected == hash_password(password)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# ── HTML шаблоны ──────────────────────────────────────────────────────────────
BASE_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI_Diag_UZ — Админка</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css" rel="stylesheet">
<style>
  :root { --primary: #1a3c6e; --accent: #e8472a; }
  body { background: #f0f2f5; font-family: 'Segoe UI', sans-serif; }
  .navbar { background: var(--primary) !important; }
  .navbar-brand { font-weight: 700; letter-spacing: 1px; color: #fff !important; }
  .sidebar { background: #fff; min-height: calc(100vh - 56px); border-right: 1px solid #dee2e6; padding: 1.5rem 0; }
  .sidebar .nav-link { color: #444; padding: .5rem 1.5rem; border-radius: 0; }
  .sidebar .nav-link:hover, .sidebar .nav-link.active { background: #e8f0fe; color: var(--primary); font-weight: 600; }
  .sidebar .nav-link i { margin-right: .5rem; width: 18px; }
  .card { border: none; box-shadow: 0 1px 4px rgba(0,0,0,.08); border-radius: 10px; }
  .badge-kb { background: #198754; }
  .badge-ai { background: #0d6efd; }
  .badge-web { background: #fd7e14; }
  .stat-card { border-left: 4px solid var(--accent); }
  .table th { background: #f8f9fa; font-size: .8rem; text-transform: uppercase; letter-spacing: .5px; }
  .btn-accent { background: var(--accent); color: #fff; border: none; }
  .btn-accent:hover { background: #c73a20; color: #fff; }
  pre { white-space: pre-wrap; word-break: break-word; font-size: .85rem; }
</style>
</head>
<body>
<nav class="navbar navbar-dark px-3">
  <span class="navbar-brand"><i class="bi bi-gear-fill me-2"></i>AI_Diag_UZ · Уста · База знаний</span>
  <div class="d-flex align-items-center gap-3">
    <span class="text-white-50 small">{{ session.get('username','') }}</span>
    <a href="/logout" class="btn btn-sm btn-outline-light">Выход</a>
  </div>
</nav>
<div class="container-fluid">
<div class="row">
  <div class="col-md-2 sidebar">
    <ul class="nav flex-column">
      <li class="nav-item"><a class="nav-link {% if page=='dashboard' %}active{% endif %}" href="/"><i class="bi bi-speedometer2"></i>Дашборд</a></li>
      <li class="nav-item"><a class="nav-link {% if page=='entries' %}active{% endif %}" href="/entries"><i class="bi bi-journal-text"></i>База знаний</a></li>
      <li class="nav-item"><a class="nav-link {% if page=='add' %}active{% endif %}" href="/entries/add"><i class="bi bi-plus-circle"></i>Добавить</a></li>
      <li class="nav-item"><a class="nav-link {% if page=='pending' %}active{% endif %}" href="/pending"><i class="bi bi-clock-history"></i>На проверке <span class="badge bg-danger ms-1" id="pending-count"></span></a></li>
      <li class="nav-item"><a class="nav-link {% if page=='sync' %}active{% endif %}" href="/sync"><i class="bi bi-cloud-arrow-up"></i>Синхронизация</a></li>
      <li class="nav-item"><a class="nav-link {% if page=='files' %}active{% endif %}" href="/files"><i class="bi bi-folder2-open"></i>Файлы</a></li>
    </ul>
  </div>
  <div class="col-md-10 p-4">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% for cat, msg in messages %}
        <div class="alert alert-{{ cat }} alert-dismissible fade show"><i class="bi bi-info-circle me-2"></i>{{ msg }}<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>
      {% endfor %}
    {% endwith %}
    {% block content %}{% endblock %}
  </div>
</div>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script>
fetch('/api/stats').then(r=>r.json()).then(d=>{
  const el = document.getElementById('pending-count');
  if(el && d.pending_new > 0) el.textContent = d.pending_new;
});
</script>
</body></html>"""

LOGIN_HTML = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8">
<title>Вход — AI_Diag_UZ</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<style>
  body{background:linear-gradient(135deg,#1a3c6e 0%,#0d2245 100%);min-height:100vh;display:flex;align-items:center;justify-content:center;}
  .card{border:none;border-radius:16px;box-shadow:0 8px 32px rgba(0,0,0,.3);}
  .brand{font-weight:800;font-size:1.4rem;color:#1a3c6e;letter-spacing:1px;}
  .btn-login{background:#e8472a;border:none;font-weight:600;}
  .btn-login:hover{background:#c73a20;}
</style></head>
<body>
<div class="card p-4" style="min-width:340px">
  <div class="text-center mb-4">
    <div class="brand">⚙️ AI_Diag_UZ · Уста</div>
    <div class="text-muted small">Панель администратора</div>
  </div>
  {% if error %}<div class="alert alert-danger small">{{ error }}</div>{% endif %}
  <form method="post">
    <div class="mb-3"><label class="form-label small fw-semibold">Логин</label>
      <input name="username" class="form-control" autofocus required></div>
    <div class="mb-4"><label class="form-label small fw-semibold">Пароль</label>
      <input type="password" name="password" class="form-control" required></div>
    <button class="btn btn-login text-white w-100">Войти</button>
  </form>
</div></body></html>"""

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username","")
        p = request.form.get("password","")
        if check_auth(u, p):
            session["logged_in"] = True
            session["username"] = u
            return redirect(url_for("dashboard"))
        return render_template_string(LOGIN_HTML, error="Неверный логин или пароль")
    return render_template_string(LOGIN_HTML, error=None)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def dashboard():
    s = kb_manager.stats
    cats_html = "".join(
        f'<div class="d-flex justify-content-between"><span>{k}</span><strong>{v}</strong></div>'
        for k,v in s["categories"].items()
    )
    content = f"""
    {{% extends BASE_HTML %}}
    <div class="row g-3 mb-4">
      <div class="col-md-3"><div class="card stat-card p-3"><div class="text-muted small">Записей в БЗ</div><div class="fs-2 fw-bold text-primary">{s['total_entries']}</div></div></div>
      <div class="col-md-3"><div class="card stat-card p-3"><div class="text-muted small">На проверке</div><div class="fs-2 fw-bold text-warning">{s['pending_new']}</div></div></div>
      <div class="col-md-3"><div class="card stat-card p-3"><div class="text-muted small">Категорий</div><div class="fs-2 fw-bold text-success">{len(s['categories'])}</div></div></div>
      <div class="col-md-3"><div class="card stat-card p-3"><div class="text-muted small">Синхр. GitHub</div><div class="small text-muted mt-1">{s['last_sync'][:16] if s['last_sync'] != '—' else '—'}</div></div></div>
    </div>
    <div class="row g-3">
      <div class="col-md-6"><div class="card p-3"><h6 class="fw-bold mb-3">📂 По категориям</h6>{cats_html}</div></div>
      <div class="col-md-6"><div class="card p-3"><h6 class="fw-bold mb-3">⚡ Быстрые действия</h6>
        <a href="/entries/add" class="btn btn-accent mb-2 w-100"><i class="bi bi-plus-lg me-2"></i>Добавить запись</a>
        <a href="/pending" class="btn btn-outline-warning mb-2 w-100"><i class="bi bi-clock me-2"></i>Проверить вопросы</a>
        <a href="/sync" class="btn btn-outline-primary w-100"><i class="bi bi-cloud-upload me-2"></i>Синхронизировать</a>
      </div></div>
    </div>"""

    # Упрощённый рендер
    html = _render_page("dashboard", f"""
    <div class="row g-3 mb-4">
      <div class="col-md-3"><div class="card stat-card p-3"><div class="text-muted small">Записей в БЗ</div><div class="fs-2 fw-bold text-primary">{s['total_entries']}</div></div></div>
      <div class="col-md-3"><div class="card stat-card p-3"><div class="text-muted small">На проверке</div><div class="fs-2 fw-bold text-warning">{s['pending_new']}</div></div></div>
      <div class="col-md-3"><div class="card stat-card p-3"><div class="text-muted small">Категорий</div><div class="fs-2 fw-bold text-success">{len(s['categories'])}</div></div></div>
      <div class="col-md-3"><div class="card stat-card p-3"><div class="text-muted small">Синхр. GitHub</div><div class="small text-muted mt-1">{s['last_sync'][:16] if s['last_sync'] != '—' else '—'}</div></div></div>
    </div>
    <div class="row g-3">
      <div class="col-md-6"><div class="card p-3"><h6 class="fw-bold mb-3">📂 По категориям</h6>{cats_html or '<span class="text-muted">Нет данных</span>'}</div></div>
      <div class="col-md-6"><div class="card p-3"><h6 class="fw-bold mb-3">⚡ Быстрые действия</h6>
        <a href="/entries/add" class="btn btn-accent mb-2 w-100"><i class="bi bi-plus-lg me-2"></i>Добавить запись</a>
        <a href="/pending" class="btn btn-outline-warning mb-2 w-100"><i class="bi bi-clock me-2"></i>Проверить вопросы</a>
        <a href="/sync" class="btn btn-outline-primary w-100"><i class="bi bi-cloud-upload me-2"></i>Синхронизировать</a>
      </div></div>
    </div>""")
    return html

@app.route("/entries")
@login_required
def entries():
    q = request.args.get("q","").strip()
    cat = request.args.get("cat","")
    all_entries = kb_manager.get_all_entries()
    if q:
        all_entries = [e for e in all_entries if q.lower() in (e.get("question","") + e.get("answer","")).lower()]
    if cat:
        all_entries = [e for e in all_entries if e.get("category") == cat]
    rows = ""
    for e in all_entries:
        src_badge = {"manual":"<span class='badge bg-secondary'>manual</span>","admin":"<span class='badge bg-primary'>admin</span>"}.get(e.get("source",""), f"<span class='badge bg-info'>{e.get('source','')}</span>")
        # Читаем статистику оценок
        fb = e.get("feedback_stats", {})
        u_thanks  = fb.get("thanks", 0)
        u_clarify = fb.get("clarify", 0)
        u_wrong   = fb.get("wrong", 0)
        a_thanks  = fb.get("admin_thanks", 0)
        a_clarify = fb.get("admin_clarify", 0)
        a_wrong   = fb.get("admin_wrong", 0)
        # Подсветка: если много "неверно" — выделяем строку
        row_class = " table-warning" if (u_wrong + a_wrong) >= 2 else ""
        feedback_cell = (
            f"<small>"
            f"<span title='Пользователи: Спасибо'>✅{u_thanks}</span> "
            f"<span title='Пользователи: Уточнить'>🔧{u_clarify}</span> "
            f"<span title='Пользователи: Неверно' class='{'text-danger fw-bold' if u_wrong else ''}'>❌{u_wrong}</span>"
            f"<br>"
            f"<span title='Админ: Спасибо'>👑✅{a_thanks}</span> "
            f"<span title='Админ: Уточнить'>👑🔧{a_clarify}</span> "
            f"<span title='Админ: Неверно' class='{'text-danger fw-bold' if a_wrong else ''}'>👑❌{a_wrong}</span>"
            f"</small>"
        )
        rows += f"""<tr class="{row_class}">
          <td class="text-muted small">{e['id']}</td>
          <td>{e.get('question','')[:80]}</td>
          <td><span class="badge bg-secondary">{e.get('category','')}</span></td>
          <td>{src_badge}</td>
          <td class="text-center">{e.get('usage_count',0)}</td>
          <td>{feedback_cell}</td>
          <td>
            <a href="/entries/edit/{e['id']}" class="btn btn-sm btn-outline-primary me-1"><i class="bi bi-pencil"></i></a>
            <a href="/entries/delete/{e['id']}" class="btn btn-sm btn-outline-danger" onclick="return confirm('Удалить?')"><i class="bi bi-trash"></i></a>
          </td></tr>"""
    cats_options = "".join(f'<option {"selected" if c==cat else ""}>{c}</option>' for c in kb_manager.get_categories())
    html = _render_page("entries", f"""
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h5 class="fw-bold mb-0">📝 База знаний</h5>
      <a href="/entries/add" class="btn btn-accent btn-sm"><i class="bi bi-plus-lg me-1"></i>Добавить</a>
    </div>
    <div class="card p-3 mb-3">
      <form class="row g-2">
        <div class="col-md-6"><input name="q" class="form-control" placeholder="🔍 Поиск..." value="{q}"></div>
        <div class="col-md-4"><select name="cat" class="form-select"><option value="">Все категории</option>{cats_options}</select></div>
        <div class="col-md-2"><button class="btn btn-outline-primary w-100">Фильтр</button></div>
      </form>
    </div>
    <div class="card"><div class="table-responsive"><table class="table table-hover mb-0">
    <thead><tr><th>ID</th><th>Вопрос</th><th>Категория</th><th>Источник</th><th>Исп.</th><th>Оценки (пользов./админ.)</th><th>Действия</th></tr></thead>
    <tbody>{rows or '<tr><td colspan="7" class="text-center text-muted py-4">Нет записей</td></tr>'}</tbody>
    </table></div></div>""")
    return html

@app.route("/entries/add", methods=["GET","POST"])
@login_required
def entry_add():
    if request.method == "POST":
        q = request.form.get("question","").strip()
        a = request.form.get("answer","").strip()
        cat = request.form.get("category","").strip()
        kw_raw = request.form.get("keywords","").strip()
        if not q or not a or not cat:
            flash("Заполните все обязательные поля!", "danger")
        else:
            keywords = [k.strip() for k in kw_raw.split(",") if k.strip()]
            kb_manager.add_entry(cat, q, a, keywords, source="admin")
            flash("✅ Запись добавлена!", "success")
            return redirect(url_for("entries"))
    cats_options = "".join(f"<option>{c}</option>" for c in kb_manager.get_categories())
    html = _render_page("add", f"""
    <h5 class="fw-bold mb-4">➕ Добавить запись в базу знаний</h5>
    <div class="card p-4">
    <form method="post">
      <div class="mb-3"><label class="form-label fw-semibold">Вопрос *</label>
        <input name="question" class="form-control" placeholder="Как откалибровать STAG-4?" required></div>
      <div class="mb-3"><label class="form-label fw-semibold">Ответ *</label>
        <textarea name="answer" class="form-control" rows="8" required></textarea></div>
      <div class="row">
        <div class="col-md-6 mb-3"><label class="form-label fw-semibold">Категория *</label>
          <select name="category" class="form-select" required><option value="">-- Выберите --</option>{cats_options}</select></div>
        <div class="col-md-6 mb-3"><label class="form-label fw-semibold">Ключевые слова</label>
          <input name="keywords" class="form-control" placeholder="калибровка, настройка, auto calibration"></div>
      </div>
      <div class="d-flex gap-2">
        <button class="btn btn-accent text-white">Сохранить</button>
        <a href="/entries" class="btn btn-outline-secondary">Отмена</a>
      </div>
    </form></div>""")
    return html

@app.route("/entries/edit/<entry_id>", methods=["GET","POST"])
@login_required
def entry_edit(entry_id):
    e = kb_manager.get_entry_by_id(entry_id)
    if not e:
        flash("Запись не найдена", "danger")
        return redirect(url_for("entries"))
    if request.method == "POST":
        kb_manager.update_entry(
            entry_id,
            question=request.form.get("question","").strip(),
            answer=request.form.get("answer","").strip(),
            category=request.form.get("category","").strip(),
            keywords=[k.strip() for k in request.form.get("keywords","").split(",") if k.strip()],
        )
        flash("✅ Запись обновлена!", "success")
        return redirect(url_for("entries"))
    cats_options = "".join(
        f'<option {"selected" if c==e.get("category") else ""}>{c}</option>'
        for c in kb_manager.get_categories()
    )
    kw = ", ".join(e.get("keywords",[]))
    html = _render_page("entries", f"""
    <h5 class="fw-bold mb-4">✏️ Редактировать запись <code>{entry_id}</code></h5>
    <div class="card p-4">
    <form method="post">
      <div class="mb-3"><label class="form-label fw-semibold">Вопрос</label>
        <input name="question" class="form-control" value="{_esc(e.get('question',''))}" required></div>
      <div class="mb-3"><label class="form-label fw-semibold">Ответ</label>
        <textarea name="answer" class="form-control" rows="10" required>{_esc(e.get('answer',''))}</textarea></div>
      <div class="row">
        <div class="col-md-6 mb-3"><label class="form-label fw-semibold">Категория</label>
          <select name="category" class="form-select">{cats_options}</select></div>
        <div class="col-md-6 mb-3"><label class="form-label fw-semibold">Ключевые слова</label>
          <input name="keywords" class="form-control" value="{_esc(kw)}"></div>
      </div>
      <div class="d-flex gap-2">
        <button class="btn btn-accent text-white">Сохранить</button>
        <a href="/entries" class="btn btn-outline-secondary">Отмена</a>
      </div>
    </form></div>""")
    return html

@app.route("/entries/delete/<entry_id>")
@login_required
def entry_delete(entry_id):
    kb_manager.delete_entry(entry_id)
    flash("🗑️ Запись удалена.", "warning")
    return redirect(url_for("entries"))

@app.route("/pending")
@login_required
def pending():
    """
    Страница раздела 'На проверке'.
    Показывает все вопросы со статусом 'new'.
    Таблица содержит: время, вопрос, ответ бота О1,
    действие (кнопка), роль, язык, кнопки управления.
    """
    items = [p for p in kb_manager.get_pending() if p["status"] == "new"]
    rows = ""

    # Словарь иконок для кнопок оценки
    ACTION_ICONS = {
        "sat_ok":      "✅ Спасибо",
        "sat_wrong":   "❌ Не верно",
        "sat_clarify": "🔧 Уточнить",
    }
    # Словарь иконок ролей
    ROLE_ICONS = {
        "admin": "👤 Админ",
        "user":  "💬 Польз.",
    }

    for p in items:
        # Ответ бота — показываем первые 100 символов О1
        ai_ans = _esc(p.get("ai_answer", ""))[:100]
        ai_ans2 = p.get("ai_answer2", "")
        ai_cell = ai_ans if ai_ans else "<span class='text-muted'>—</span>"
        if ai_ans2:
            ai_cell += f"<br><small class='text-muted'>О2: {_esc(ai_ans2)[:80]}</small>"

        # Действие и роль
        action_badge = ACTION_ICONS.get(
            p.get("source_action",""), p.get("source_action","—"))
        role_badge = ROLE_ICONS.get(
            p.get("source_role",""), p.get("source_role","—"))

        # Язык
        lang_badge = p.get("lang","ru")

        rows += f"""<tr>
          <td class="small text-muted text-nowrap">{p['timestamp'][:16]}</td>
          <td><strong>{_esc(p.get('message_text', ''))[:100]}</strong>
              <br><small class="text-muted">{lang_badge}</small></td>
          <td class="small">{ai_cell}</td>
          <td class="small text-nowrap">{action_badge}</td>
          <td class="small text-nowrap">{role_badge}</td>
          <td>
            <a href="/pending/add/{p['id']}" class="btn btn-sm btn-outline-success me-1"
               title="Добавить в БЗ"><i class="bi bi-plus-lg"></i></a>
            <a href="/pending/reject/{p['id']}" class="btn btn-sm btn-outline-danger"
               title="Удалить"><i class="bi bi-x-lg"></i></a>
          </td></tr>"""

    html = _render_page("pending", f"""
    <h5 class="fw-bold mb-3">⏳ На проверке ({len(items)})</h5>
    <p class="text-muted small">Вопросы пользователей с ответами бота. Добавьте лучшие в базу знаний.</p>
    <div class="card"><div class="table-responsive">
    <table class="table table-hover table-sm mb-0">
    <thead class="table-light"><tr>
      <th>Время</th><th>Вопрос / Язык</th>
      <th>Ответ бота (О1/О2)</th>
      <th>Кнопка</th><th>Роль</th><th>Действия</th>
    </tr></thead>
    <tbody>{rows or
        '<tr><td colspan="6" class="text-center text-muted py-4">✅ Нет новых вопросов</td></tr>'
    }</tbody>
    </table></div></div>""")
    return html

@app.route("/pending/add/<pid>")
@login_required
def pending_add_form(pid):
    pending_items = kb_manager.get_pending()
    p = next((x for x in pending_items if x["id"] == pid), None)
    if not p:
        return redirect(url_for("pending"))
    cats_options = "".join(f"<option>{c}</option>" for c in kb_manager.get_categories())
    # Файлы из каталога для привязки к ответу
    file_catalog = kb_manager._kb.get("file_catalog", {}).get("files", [])
    files_options = "<option value=''>— без файла —</option>" + "".join(
        f"<option value='{f['id']}'>{_esc(f.get('name',''))}</option>"
        for f in file_catalog
    )
    # Ответ бота О1 и О2 для предзаполнения формы
    ai_answer  = _esc(p.get("ai_answer",  ""))
    ai_answer2 = _esc(p.get("ai_answer2", ""))
    action_label = {"sat_ok":"✅ Спасибо","sat_wrong":"❌ Не верно",
                    "sat_clarify":"🔧 Уточнить"}.get(p.get("source_action",""),"—")
    role_label = {"admin":"👤 Администратор","user":"💬 Пользователь"}.get(
                    p.get("source_role",""),"—")

    html = _render_page("pending", f"""
    <h5 class="fw-bold mb-4">➕ Добавить в БЗ</h5>
    <div class="alert alert-info d-flex gap-3 flex-wrap align-items-center">
      <span><strong>Кнопка:</strong> {action_label}</span>
      <span><strong>Роль:</strong> {role_label}</span>
      <div class="d-flex align-items-center gap-1">
        <strong>Язык:</strong>
        <select name="lang_override" class="form-select form-select-sm" style="width:auto">
          {"".join(f'<option value="{c}" {"selected" if c == p.get("lang","ru") else ""}>{c}</option>'
            for c in ["ru","uz_cyrillic","uz_latin","ru_translit","en","uk","be","de","kk","ky","tg","tk","pl"])}
        </select>
      </div>
    </div>
    <div class="card p-4">
    <form method="post" action="/pending/save/{pid}">
      <div class="mb-3">
        <label class="form-label fw-semibold">Вопрос (можно отредактировать)</label>
        <input name="question" class="form-control" value="{_esc(p['message_text'])}" required>
      </div>
      {'<div class="mb-3"><label class="form-label fw-semibold text-secondary">Ответ бота О1 (для справки)</label><textarea class="form-control form-control-sm bg-light" rows="4" readonly>' + ai_answer + '</textarea></div>' if ai_answer else ''}
      {'<div class="mb-3"><label class="form-label fw-semibold text-secondary">Ответ бота О2 (для справки)</label><textarea class="form-control form-control-sm bg-light" rows="4" readonly>' + ai_answer2 + '</textarea></div>' if ai_answer2 else ''}
      <div class="mb-3">
        <label class="form-label fw-semibold">Ответ для базы знаний *</label>
        <textarea name="answer" class="form-control" rows="8" required
          placeholder="Введите подробный ответ...">{ai_answer}</textarea>
      </div>
      <div class="row">
        <div class="col-md-4 mb-3">
          <label class="form-label fw-semibold">Категория</label>
          <select name="category" class="form-select">{cats_options}</select>
        </div>
        <div class="col-md-4 mb-3">
          <label class="form-label fw-semibold">Ключевые слова</label>
          <input name="keywords" class="form-control" placeholder="слово1, слово2">
        </div>
        <div class="col-md-4 mb-3">
          <label class="form-label fw-semibold">Файл из каталога</label>
          <select name="file_id" class="form-select">{files_options}</select>
        </div>
      </div>
      <button class="btn btn-accent text-white">💾 Сохранить в БЗ</button>
      <a href="/pending" class="btn btn-outline-secondary ms-2">Отмена</a>
    </form></div>""")
    return html

@app.route("/pending/save/<pid>", methods=["POST"])
@login_required
def pending_save(pid):
    """
    Сохраняет отредактированный ответ из 'На проверке' в базу знаний.
    Поддерживает привязку файла из каталога и переопределение языка.
    """
    q            = request.form.get("question",      "").strip()
    a            = request.form.get("answer",        "").strip()
    cat          = request.form.get("category",      "").strip()
    kw           = [k.strip() for k in request.form.get("keywords","").split(",") if k.strip()]
    file_id      = request.form.get("file_id",       "").strip()
    lang_override = request.form.get("lang_override", "").strip()
    if q and a and cat:
        entry = kb_manager.add_entry(cat, q, a, kw, source="learning")
        # Привязываем файл если выбран
        if file_id and entry:
            kb_manager.update_entry(entry["id"], {"file_id": file_id})
        kb_manager.resolve_pending(pid, "added")
        flash("✅ Запись добавлена в базу знаний!", "success")
    else:
        flash("⚠️ Заполните все обязательные поля.", "warning")
    return redirect(url_for("pending"))

@app.route("/pending/reject/<pid>")
@login_required
def pending_reject(pid):
    kb_manager.resolve_pending(pid, "rejected")
    return redirect(url_for("pending"))

@app.route("/sync")
@login_required
def sync_page():
    s = kb_manager.stats
    html = _render_page("sync", f"""
    <h5 class="fw-bold mb-4">☁️ Синхронизация с GitHub</h5>
    <div class="row g-3">

      <div class="col-md-6"><div class="card p-4">
        <h6 class="fw-bold">📚 База знаний</h6>
        <div class="mb-2"><span class="text-muted">Записей в БЗ:</span> <strong>{s['total_entries']}</strong></div>
        <div class="mb-2"><span class="text-muted">Последняя синхр.:</span> <strong>{s['last_sync'][:19] if s['last_sync'] != '—' else '—'}</strong></div>
        <div class="mb-4"><span class="text-muted">Автосинхр.:</span> <strong>каждый час</strong></div>
        <a href="/sync/now" class="btn btn-accent text-white w-100">
          <i class="bi bi-cloud-upload me-2"></i>Синхронизировать БЗ сейчас
        </a>
      </div></div>



      <div class="col-md-6"><div class="card p-4">
        <h6 class="fw-bold">Как настроить GitHub</h6>
        <ol class="small text-muted">
          <li>Создайте репозиторий на GitHub</li>
          <li>Settings → Developer settings → Personal access tokens → Generate</li>
          <li>Выберите права: <code>repo</code></li>
          <li>Вставьте токен в <code>config.py</code></li>
          <li>Укажите имя репозитория: <code>username/repo</code></li>
        </ol>
        <div class="mt-2 text-muted small">
          На GitHub хранятся: <code>knowledge_base.json</code>
          и <code>files_cache/file_catalog.json</code><br>
          Сами файлы (.exe, .doc) хранятся только локально.
        </div>
      </div></div>

    </div>""")
    return html

@app.route("/sync/catalog")
@login_required
def sync_catalog_now():
    """Принудительная синхронизация file_catalog.json на GitHub."""
    loop = asyncio.new_event_loop()
    ok   = loop.run_until_complete(kb_manager.sync_files_catalog_to_github())
    loop.close()
    if ok:
        flash("✅ file_catalog.json синхронизирован на GitHub", "success")
    else:
        flash("❌ Ошибка синхронизации каталога. Проверьте GITHUB_TOKEN.", "error")
    return redirect(url_for("sync_page"))


@app.route("/sync/now")
@login_required
def sync_now():
    loop = asyncio.new_event_loop()
    ok = loop.run_until_complete(kb_manager.sync_to_github())
    loop.close()
    if ok:
        flash("✅ База знаний успешно синхронизирована с GitHub!", "success")
    else:
        flash("❌ Ошибка синхронизации. Проверьте GITHUB_TOKEN и GITHUB_REPO в config.py", "danger")
    return redirect(url_for("sync_page"))

@app.route("/api/stats")
@login_required
def api_stats():
    return jsonify(kb_manager.stats)

# ── Вспомогательные ───────────────────────────────────────────────────────────

def _esc(text: str) -> str:
    return text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

def _render_page(page: str, content: str) -> str:
    """Рендер страницы с базовым шаблоном"""
    nav_items = [
        ("dashboard", "/", "bi-speedometer2", "Дашборд"),
        ("entries", "/entries", "bi-journal-text", "База знаний"),
        ("add", "/entries/add", "bi-plus-circle", "Добавить"),
        ("pending", "/pending", "bi-clock-history", "На проверке"),
        ("sync", "/sync", "bi-cloud-arrow-up", "Синхронизация"),
        ("files", "/files", "bi-folder2-open", "Файлы"),
    ]
    nav_html = "\n".join(
        f'<li class="nav-item"><a class="nav-link {"active" if p==page else ""}" href="{url}">'
        f'<i class="bi {icon} me-2"></i>{label}</a></li>'
        for p, url, icon, label in nav_items
    )
    from flask import get_flashed_messages
    flashes = ""
    for cat, msg in get_flashed_messages(with_categories=True):
        flashes += f'<div class="alert alert-{"success" if cat=="success" else "danger" if cat=="danger" else "warning"} alert-dismissible fade show"><i class="bi bi-info-circle me-2"></i>{msg}<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>'
    username = session.get("username","")
    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI_Diag_UZ — Админка</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css" rel="stylesheet">
<style>
:root{{--primary:#1a3c6e;--accent:#e8472a;}}
body{{background:#f0f2f5;font-family:'Segoe UI',sans-serif;}}
.navbar{{background:var(--primary)!important;}}
.sidebar{{background:#fff;min-height:calc(100vh - 56px);border-right:1px solid #dee2e6;padding:1.5rem 0;}}
.sidebar .nav-link{{color:#444;padding:.5rem 1.5rem;}}
.sidebar .nav-link:hover,.sidebar .nav-link.active{{background:#e8f0fe;color:var(--primary);font-weight:600;}}
.sidebar .nav-link i{{margin-right:.5rem;width:18px;}}
.card{{border:none;box-shadow:0 1px 4px rgba(0,0,0,.08);border-radius:10px;}}
.stat-card{{border-left:4px solid var(--accent);}}
.table th{{background:#f8f9fa;font-size:.8rem;text-transform:uppercase;}}
.btn-accent{{background:var(--accent);color:#fff;border:none;}}
.btn-accent:hover{{background:#c73a20;color:#fff;}}
</style></head><body>
<nav class="navbar navbar-dark px-3">
  <span class="navbar-brand fw-bold"><i class="bi bi-gear-fill me-2"></i>AI_Diag_UZ · Уста · База знаний</span>
  <div class="d-flex align-items-center gap-3">
    <span class="text-white-50 small">{username}</span>
    <a href="/logout" class="btn btn-sm btn-outline-light">Выход</a>
  </div>
</nav>
<div class="container-fluid"><div class="row">
  <div class="col-md-2 sidebar"><ul class="nav flex-column">{nav_html}</ul></div>
  <div class="col-md-10 p-4">{flashes}{content}</div>
</div></div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script>
fetch('/api/stats').then(r=>r.json()).then(d=>{{
  document.querySelectorAll('.pending-badge').forEach(el=>{{if(d.pending_new>0)el.textContent=d.pending_new;}});
}}).catch(()=>{{}});
</script></body></html>"""

# ── Запуск ────────────────────────────────────────────────────────────────────

def run_admin():
    import asyncio
    loop = asyncio.new_event_loop()
    loop.run_until_complete(kb_manager.load())
    loop.close()
    app.run(host=ADMIN_HOST, port=ADMIN_PORT, debug=False)



# ==============================================================================
#  УПРАВЛЕНИЕ ФАЙЛОВЫМ КАТАЛОГОМ
# ==============================================================================

@app.route("/files")
@login_required
def files_list():
    """Список файлов. Статус проверяется по реальному наличию файла на диске."""
    import os
    try:
        from file_manager import get_all_files
        files = get_all_files()
    except Exception as e:
        files = []
        rows_html = f"<div class='alert alert-danger'>Ошибка загрузки каталога: {e}</div>"
    else:
        if not files:
            rows_html = "<div class='alert alert-info'>Каталог пуст. <a href='/files/add'>Добавьте первый файл</a>.</div>"
        else:
            rows = []
            for f in files:
                fid      = f.get("id", "")
                name     = f.get("name", "")
                desc     = (f.get("description") or "")[:70]
                category = f.get("category", "")
                kws      = f.get("keywords", [])
                kw_str   = ", ".join(kws[:4]) + ("..." if len(kws) > 4 else "")
                lpath    = f.get("local_path", "")

                # Реальный статус — абсолютный путь через BASE_DIR
                abs_lpath = ""
                if lpath:
                    if os.path.isabs(lpath):
                        abs_lpath = lpath
                    else:
                        abs_lpath = os.path.join(BASE_DIR, lpath)

                if abs_lpath and os.path.exists(abs_lpath):
                    size_bytes = os.path.getsize(abs_lpath)
                    size_str   = f"{size_bytes // 1024 // 1024} MB" if size_bytes > 1024*1024 else f"{size_bytes // 1024} KB"
                    status = f"<span class='badge bg-success'>На диске ({size_str})</span>"
                elif f.get("telegram_file_id"):
                    status = "<span class='badge bg-primary'>Telegram</span>"
                elif f.get("source_url"):
                    status = "<span class='badge bg-secondary'>Ссылка</span>"
                else:
                    status = "<span class='badge bg-warning text-dark'>Файл отсутствует</span>"

                rows.append(f"""<tr>
                  <td><code style='font-size:.8em'>{fid}</code></td>
                  <td>
                    <strong>{name}</strong><br>
                    <small class='text-muted'>{desc}</small>
                  </td>
                  <td><span class='badge bg-info'>{category}</span></td>
                  <td>{status}</td>
                  <td><small>{kw_str}</small></td>
                  <td style='white-space:nowrap'>
                    <a href='/files/edit/{fid}' class='btn btn-outline-primary btn-sm me-1' title='Редактировать'>&#9998;</a>
                    <form method='POST' action='/files/delete/{fid}' style='display:inline'
                          onsubmit="return confirm('Удалить {name}?')">
                      <button class='btn btn-outline-danger btn-sm' title='Удалить'>&#128465;</button>
                    </form>
                  </td>
                </tr>""")

            rows_html = f"""<div class='table-responsive'>
            <table class='table table-hover align-middle'>
            <thead class='table-dark'><tr>
              <th>ID</th><th>Название / Описание</th>
              <th>Категория</th><th>Статус (реальный)</th>
              <th>Ключевые слова</th><th>Действия</th>
            </tr></thead>
            <tbody>{''.join(rows)}</tbody></table></div>"""

    # Показываем сообщение после синхронизации
    sync_msg = request.args.get("msg", "")
    sync_alert = (f"<div class='alert alert-info alert-dismissible fade show mb-3'>"
                  f"{sync_msg}"
                  f"<button type='button' class='btn-close' data-bs-dismiss='alert'></button>"
                  f"</div>") if sync_msg else ""

    # Статистика каталога
    import os
    from pathlib import Path
    try:
        cat_files    = files
        cat_total    = len(cat_files)
        cat_on_disk  = sum(1 for f in cat_files if f.get("downloaded"))
        cat_missing  = cat_total - cat_on_disk
        cat_size     = sum(f.get("size_bytes", 0) for f in cat_files if f.get("downloaded"))
        cat_size_str = f"{cat_size // 1024 // 1024} MB" if cat_size > 0 else "0 MB"
    except Exception:
        cat_total = cat_on_disk = cat_missing = 0
        cat_size_str = "—"

    stat_html = f"""
    <div class='row g-3 mb-4'>
      <div class='col-md-3'>
        <div class='card p-3 text-center'>
          <div class='fs-3 fw-bold text-primary'>{cat_total}</div>
          <div class='text-muted small'>Файлов в каталоге</div>
        </div>
      </div>
      <div class='col-md-3'>
        <div class='card p-3 text-center'>
          <div class='fs-3 fw-bold text-success'>{cat_on_disk}</div>
          <div class='text-muted small'>На диске ({cat_size_str})</div>
        </div>
      </div>
      <div class='col-md-3'>
        <div class='card p-3 text-center'>
          <div class='fs-3 fw-bold {"text-warning" if cat_missing else "text-success"}'>{cat_missing}</div>
          <div class='text-muted small'>Файлов отсутствует</div>
        </div>
      </div>
      <div class='col-md-3'>
        <div class='card p-3'>
          <div class='d-flex flex-column gap-2'>
            <a href='/files/sync' class='btn btn-outline-primary btn-sm'>
              🔍 Сканировать files_cache/
            </a>
            <a href='/sync/catalog' class='btn btn-primary btn-sm'>
              ☁️ Отправить каталог на GitHub
            </a>
          </div>
        </div>
      </div>
    </div>"""

    content = f"""
    {sync_alert}
    <div class='d-flex justify-content-between align-items-center mb-3'>
      <h2>Файловый каталог</h2>
      <a href='/files/add' class='btn btn-success'>+ Добавить файл</a>
    </div>
    {stat_html}
    {rows_html}"""
    return _render_page("files", content)


@app.route("/files/edit/<file_id>", methods=["GET", "POST"])
@login_required
def files_edit(file_id):
    """Редактирование метаданных файла в каталоге."""
    from file_manager import _load_catalog, _save_catalog
    catalog = _load_catalog()
    entry   = next((e for e in catalog["files"] if e["id"] == file_id), None)
    if not entry:
        return redirect(url_for("files_list"))

    error_msg = ""
    if request.method == "POST":
        try:
            entry["name"]        = request.form.get("name", "").strip() or entry["name"]
            entry["description"] = request.form.get("description", "").strip()
            entry["source_url"]  = request.form.get("source_url", "").strip()
            entry["category"]    = request.form.get("category", "software")
            kw_raw               = request.form.get("keywords", "").strip()
            entry["keywords"]    = [k.strip() for k in kw_raw.split(",") if k.strip()]
            # Если загружен новый файл — заменяем
            uploaded = request.files.get("file")
            if uploaded and uploaded.filename:
                import os
                from pathlib import Path
                cache_dir  = Path(BASE_DIR) / "files_cache"
                cache_dir.mkdir(exist_ok=True)
                save_path  = cache_dir / uploaded.filename
                uploaded.save(str(save_path))
                entry["filename"]   = uploaded.filename
                entry["local_path"] = f"files_cache/{uploaded.filename}"
                entry["size_bytes"] = save_path.stat().st_size
                entry["downloaded"] = True
            _save_catalog(catalog)
            return redirect(url_for("files_list"))
        except Exception as e:
            error_msg = str(e)

    kw_str    = ", ".join(entry.get("keywords", []))
    err_html  = f"<div class='alert alert-danger'>{error_msg}</div>" if error_msg else ""
    cats      = ["software", "firmware", "manual", "driver"]
    cat_opts  = "".join(
        f"<option value='{c}' {'selected' if c == entry.get('category') else ''}>{c}</option>"
        for c in cats
    )
    import os
    lpath     = entry.get("local_path", "")
    file_info = ""
    if lpath and os.path.exists(lpath):
        size = os.path.getsize(lpath)
        file_info = f"<div class='alert alert-success mb-3'>Файл на диске: <code>{lpath}</code> ({size // 1024} KB)</div>"
    elif lpath:
        file_info = f"<div class='alert alert-warning mb-3'>Файл не найден: <code>{lpath}</code><br>Загрузите файл ниже.</div>"

    form_html = f"""{err_html}
    <div class='d-flex justify-content-between align-items-center mb-3'>
      <h2>Редактировать файл</h2>
      <a href='/files' class='btn btn-outline-secondary'>Назад к каталогу</a>
    </div>
    <div class='row'><div class='col-md-8'>
    {file_info}
    <form method='POST' enctype='multipart/form-data'>
      <div class='mb-3'>
        <label class='form-label fw-bold'>ID</label>
        <input type='text' class='form-control' value='{entry["id"]}' disabled>
      </div>
      <div class='mb-3'>
        <label class='form-label fw-bold'>Название *</label>
        <input type='text' class='form-control' name='name'
               value='{entry.get("name","")}' required>
      </div>
      <div class='mb-3'>
        <label class='form-label fw-bold'>Описание</label>
        <textarea class='form-control' name='description' rows='3'>{entry.get("description","")}</textarea>
      </div>
      <div class='mb-3'>
        <label class='form-label fw-bold'>Ключевые слова (через запятую)</label>
        <input type='text' class='form-control' name='keywords' value='{kw_str}'>
        <div class='form-text'>По этим словам пользователи ищут файл в боте</div>
      </div>
      <div class='mb-3'>
        <label class='form-label fw-bold'>Ссылка для скачивания</label>
        <input type='url' class='form-control' name='source_url'
               value='{entry.get("source_url","")}' placeholder='https://...'>
      </div>
      <div class='mb-3'>
        <label class='form-label fw-bold'>Категория</label>
        <select class='form-select' name='category'>{cat_opts}</select>
      </div>
      <div class='mb-4'>
        <label class='form-label fw-bold'>Заменить файл (необязательно)</label>
        <input type='file' class='form-control' name='file'>
        <div class='form-text'>Оставьте пустым чтобы сохранить текущий файл</div>
      </div>
      <div class='d-flex gap-2'>
        <button type='submit' class='btn btn-primary'>Сохранить изменения</button>
        <a href='/files' class='btn btn-secondary'>Отмена</a>
      </div>
    </form>
    </div></div>"""
    return _render_page("files", form_html)


@app.route("/files/sync")
@login_required
def files_sync():
    """
    Полная синхронизация файлового каталога:
    1. Сканирует папку files_cache/ на диске
    2. Добавляет в каталог файлы которых там нет
    3. Обновляет статус/размер для существующих записей
    4. Помечает записи у которых файл не найден
    """
    import os, re
    from pathlib import Path
    from file_manager import _load_catalog, _save_catalog, add_file_to_catalog

    cache_dir = Path(BASE_DIR) / "files_cache"
    cache_dir.mkdir(exist_ok=True)
    catalog   = _load_catalog()

    # Расширения файлов которые добавляем в каталог
    KNOWN_EXT = {".exe", ".zip", ".rar", ".7z", ".pdf", ".doc", ".docx",
                 ".xls", ".xlsx", ".bin", ".hex", ".fw", ".img", ".iso"}

    # Строим индекс: filename -> entry
    idx_by_filename = {e.get("filename", ""): e for e in catalog["files"]}

    added   = 0
    updated = 0
    missing = 0

    # ── Шаг 1: сканируем папку files_cache/ ─────────────────────────────────
    for fpath in sorted(cache_dir.iterdir()):
        if not fpath.is_file():
            continue
        if fpath.suffix.lower() == ".json":
            continue  # file_catalog.json пропускаем
        if fpath.suffix.lower() not in KNOWN_EXT:
            continue

        fname     = fpath.name
        abs_path  = str(fpath)
        size      = fpath.stat().st_size
        rel_path  = f"files_cache/{fname}"

        if fname in idx_by_filename:
            # Файл есть в каталоге — обновляем статус и путь
            e = idx_by_filename[fname]
            e["local_path"] = rel_path
            e["downloaded"] = True
            e["size_bytes"] = size
            updated += 1
        else:
            # Файла НЕТ в каталоге — добавляем автоматически
            # Название из имени файла
            # Название: убираем версию из имени если есть буквы (человекочитаемое)
            raw_name  = fpath.stem.replace("_", " ").replace("-", " ")
            auto_name = " ".join(w for w in raw_name.split() if w)  # убираем двойные пробелы
            # Ключевые слова из имени файла — разбиваем по _ - и пробелу
            auto_kws = list(dict.fromkeys(
                w.lower() for w in re.split(r"[_\-\s]+", fpath.stem)
                if len(w) > 2
            ))[:8]
            new_id = add_file_to_catalog(
                name        = auto_name,
                filename    = fname,
                description = f"Автоимпорт из files_cache/",
                keywords    = auto_kws,
                source_url  = "",
                category    = "manual" if fpath.suffix.lower() in (".doc", ".docx", ".pdf", ".xls", ".xlsx") else "software",
            )
            # Сразу обновляем путь и размер
            catalog = _load_catalog()  # перечитываем после добавления
            for e in catalog["files"]:
                if e["id"] == new_id:
                    e["local_path"] = rel_path
                    e["downloaded"] = True
                    e["size_bytes"] = size
                    break
            idx_by_filename[fname] = e
            added += 1

    # ── Шаг 2: обновляем все записи каталога через абсолютный путь ──────────
    # Перечитываем каталог (мог обновиться в шаге 1)
    catalog = _load_catalog()
    for entry in catalog["files"]:
        lpath = entry.get("local_path", "")
        fname = entry.get("filename", "")

        # Пробуем найти файл: сначала по local_path, потом по имени в files_cache
        abs_lpath = ""
        if lpath:
            candidate = lpath if os.path.isabs(lpath) else os.path.join(BASE_DIR, lpath)
            if os.path.exists(candidate):
                abs_lpath = candidate
        if not abs_lpath and fname:
            candidate = os.path.join(BASE_DIR, "files_cache", fname)
            if os.path.exists(candidate):
                abs_lpath = candidate

        if abs_lpath:
            # Нормализуем local_path — всегда относительный с прямым слешем
            entry["local_path"] = "files_cache/" + os.path.basename(abs_lpath)
            entry["downloaded"]  = True
            entry["size_bytes"]  = os.path.getsize(abs_lpath)
            updated += 1
        elif lpath:
            entry["downloaded"] = False
            missing += 1

    _save_catalog(catalog)

    # ── Шаг 3: сообщение о результате ────────────────────────────────────────
    total = len(catalog["files"])
    msg   = (f"Добавлено новых: {added} | "
             f"Обновлено: {updated} | "
             f"Отсутствуют: {missing} | "
             f"Всего в каталоге: {total}")
    return redirect(url_for("files_list") + f"?msg={msg}")


@app.route("/files/delete/<file_id>", methods=["POST"])
@login_required
def files_delete(file_id):
    """Удаление файла из каталога (и с диска если есть)."""
    try:
        import os
        from file_manager import _load_catalog, _save_catalog
        catalog = _load_catalog()
        entry   = next((e for e in catalog["files"] if e["id"] == file_id), None)
        if entry:
            lpath = entry.get("local_path", "")
            if lpath:
                # Проверяем что путь внутри CACHE_DIR (аудит C5)
                cache_dir = Path(BASE_DIR) / "files_cache"
                resolved  = (cache_dir / Path(lpath).name).resolve()
                if resolved.is_relative_to(cache_dir.resolve()) and resolved.exists():
                    os.remove(str(resolved))
            catalog["files"] = [e for e in catalog["files"] if e["id"] != file_id]
            _save_catalog(catalog)
    except Exception as e:
        pass
    return redirect(url_for("files_list"))



if __name__ == "__main__":
    run_admin()
