"""
app.py — Streamlit-интерфейс «Аналитик медицинских справок».

Запуск:
    python -m streamlit run app.py
"""

import os
import json
import tempfile
from pathlib import Path
from datetime import datetime

import streamlit as st

import db
import load as loader
import backends
from backends import SYSTEM_ANALYST

# ---------------------------------------------------------------------------
# Конфигурация страницы
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="МедАналитик — анализ медицинских справок",
    page_icon="⚕️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# CSS — медицинский стиль (ЕМИАС + mCare)
# ---------------------------------------------------------------------------

st.markdown("""
<style>
/* ── Импорт шрифта ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* ── Общий фон и типографика ── */
html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
    background-color: #FFFFFF !important;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    color: #1A2B45 !important;
}

/* ── Шапка ── */
[data-testid="stHeader"] {
    background-color: #FFFFFF !important;
    border-bottom: 1px solid #E1E8F5 !important;
}

/* ── Боковая панель ── */
[data-testid="stSidebar"] {
    background-color: #F0F4FB !important;
    border-right: 1px solid #D6E4F7 !important;
}
[data-testid="stSidebar"] * {
    color: #1A2B45 !important;
}
[data-testid="stSidebar"] .stRadio label,
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stTextInput label {
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    color: #5A6B7E !important;
    text-transform: uppercase !important;
    letter-spacing: 0.04em !important;
}

/* ── Кнопки — основные ── */
.stButton > button[kind="primary"],
.stButton > button[data-testid*="primary"] {
    background: linear-gradient(135deg, #1366D6 0%, #1A7FE8 100%) !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 0.9rem !important;
    padding: 0.55rem 1.4rem !important;
    box-shadow: 0 2px 8px rgba(19, 102, 214, 0.25) !important;
    transition: all 0.2s ease !important;
}
.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #0F54B8 0%, #1366D6 100%) !important;
    box-shadow: 0 4px 16px rgba(19, 102, 214, 0.35) !important;
    transform: translateY(-1px) !important;
}

/* ── Кнопки — вторичные ── */
.stButton > button[kind="secondary"],
.stButton > button:not([kind="primary"]) {
    background: #FFFFFF !important;
    color: #1366D6 !important;
    border: 1.5px solid #1366D6 !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
}
.stButton > button:not([kind="primary"]):hover {
    background: #EBF3FF !important;
}

/* ── Кнопки скачивания ── */
[data-testid="stDownloadButton"] > button {
    background: #FFFFFF !important;
    color: #1366D6 !important;
    border: 1.5px solid #1366D6 !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
    width: 100% !important;
}
[data-testid="stDownloadButton"] > button:hover {
    background: #EBF3FF !important;
}

/* ── Вкладки ── */
[data-testid="stTabs"] [role="tablist"] {
    background: #F0F4FB !important;
    border-radius: 10px !important;
    padding: 4px !important;
    gap: 2px !important;
    border-bottom: none !important;
}
[data-testid="stTabs"] button[role="tab"] {
    border-radius: 8px !important;
    font-weight: 500 !important;
    font-size: 0.88rem !important;
    color: #5A6B7E !important;
    padding: 0.45rem 1rem !important;
    border: none !important;
    background: transparent !important;
}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    background: #FFFFFF !important;
    color: #1366D6 !important;
    font-weight: 600 !important;
    box-shadow: 0 1px 6px rgba(0,0,0,0.08) !important;
}

/* ── Метрики ── */
[data-testid="stMetric"] {
    background: #F7F9FC !important;
    border: 1px solid #E1E8F5 !important;
    border-radius: 10px !important;
    padding: 0.75rem 1rem !important;
}
[data-testid="stMetricLabel"] {
    color: #5A6B7E !important;
    font-size: 0.78rem !important;
    font-weight: 500 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.04em !important;
}
[data-testid="stMetricValue"] {
    color: #1366D6 !important;
    font-weight: 700 !important;
    font-size: 1.6rem !important;
}

/* ── Поле загрузки файлов ── */
[data-testid="stFileUploader"] {
    border: 2px dashed #9BB8E8 !important;
    border-radius: 12px !important;
    background: #F7FAFF !important;
    padding: 1rem !important;
    transition: border-color 0.2s !important;
}
[data-testid="stFileUploader"]:hover {
    border-color: #1366D6 !important;
    background: #EBF3FF !important;
}
[data-testid="stFileUploaderDropzone"] {
    background: transparent !important;
}

/* ── Поля ввода ── */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stSelectbox"] > div > div {
    border: 1.5px solid #D6E4F7 !important;
    border-radius: 8px !important;
    background: #FFFFFF !important;
    color: #1A2B45 !important;
    font-size: 0.9rem !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
    border-color: #1366D6 !important;
    box-shadow: 0 0 0 3px rgba(19, 102, 214, 0.12) !important;
}

/* ── Алерты ── */
[data-testid="stAlert"][data-type="info"] {
    background: #EBF5FF !important;
    border-left: 4px solid #1366D6 !important;
    border-radius: 8px !important;
    color: #1A2B45 !important;
}
[data-testid="stAlert"][data-type="success"] {
    background: #E8F8F0 !important;
    border-left: 4px solid #0AADA0 !important;
    border-radius: 8px !important;
}
[data-testid="stAlert"][data-type="warning"] {
    background: #FFF8E8 !important;
    border-left: 4px solid #F39C12 !important;
    border-radius: 8px !important;
}
[data-testid="stAlert"][data-type="error"] {
    background: #FEF0F0 !important;
    border-left: 4px solid #E74C3C !important;
    border-radius: 8px !important;
}

/* ── Таблицы ── */
[data-testid="stDataFrame"] {
    border: 1px solid #E1E8F5 !important;
    border-radius: 10px !important;
    overflow: hidden !important;
}
[data-testid="stDataFrame"] thead tr th {
    background: #F0F4FB !important;
    color: #5A6B7E !important;
    font-weight: 600 !important;
    font-size: 0.8rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.04em !important;
    border-bottom: 1px solid #D6E4F7 !important;
}

/* ── Разделитель ── */
hr {
    border: none !important;
    border-top: 1px solid #E1E8F5 !important;
    margin: 1rem 0 !important;
}

/* ── Спиннер ── */
[data-testid="stSpinner"] > div {
    border-top-color: #1366D6 !important;
}

/* ── Прогресс-бар ── */
[data-testid="stProgressBar"] > div > div {
    background: linear-gradient(90deg, #1366D6, #0AADA0) !important;
    border-radius: 4px !important;
}

/* ── Радио-кнопки ── */
[data-testid="stRadio"] label span {
    color: #1A2B45 !important;
}

/* ── Карточки (кастомные) ── */
.med-card {
    background: #FFFFFF;
    border: 1px solid #E1E8F5;
    border-radius: 12px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1rem;
    box-shadow: 0 1px 4px rgba(26, 43, 69, 0.06);
}
.med-card-blue {
    background: linear-gradient(135deg, #1366D6 0%, #1A7FE8 100%);
    border-radius: 12px;
    padding: 1.25rem 1.5rem;
    color: #ffffff;
    margin-bottom: 1rem;
}
.med-card-teal {
    background: linear-gradient(135deg, #0AADA0 0%, #12C4B5 100%);
    border-radius: 12px;
    padding: 1.25rem 1.5rem;
    color: #ffffff;
    margin-bottom: 1rem;
}

/* ── Заголовок приложения ── */
.app-header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 0.5rem 0 1.5rem 0;
    border-bottom: 2px solid #E1E8F5;
    margin-bottom: 1.5rem;
}
.app-header-icon {
    width: 44px;
    height: 44px;
    background: linear-gradient(135deg, #1366D6, #0AADA0);
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.5rem;
    flex-shrink: 0;
}
.app-header-title {
    font-size: 1.4rem;
    font-weight: 700;
    color: #1A2B45;
    line-height: 1.2;
}
.app-header-sub {
    font-size: 0.85rem;
    color: #5A6B7E;
    margin-top: 2px;
}

/* ── Дисклеймер ── */
.disclaimer-box {
    background: #EBF5FF;
    border: 1px solid #9BB8E8;
    border-left: 4px solid #1366D6;
    border-radius: 8px;
    padding: 0.85rem 1.1rem;
    font-size: 0.87rem;
    color: #2A4A7F;
    margin-bottom: 1.25rem;
    line-height: 1.5;
}

/* ── Бейджи приоритетов ── */
.badge-p1 {
    display: inline-block;
    background: #FDECEA;
    color: #C0392B;
    border: 1px solid #F5C6C2;
    border-radius: 20px;
    padding: 2px 10px;
    font-size: 0.78rem;
    font-weight: 600;
}
.badge-p2 {
    display: inline-block;
    background: #FEF9E7;
    color: #B7770D;
    border: 1px solid #F9E4A0;
    border-radius: 20px;
    padding: 2px 10px;
    font-size: 0.78rem;
    font-weight: 600;
}
.badge-p3 {
    display: inline-block;
    background: #E8F8F0;
    color: #1E8449;
    border: 1px solid #A9DFBF;
    border-radius: 20px;
    padding: 2px 10px;
    font-size: 0.78rem;
    font-weight: 600;
}

/* ── Лого в сайдбаре ── */
.sidebar-logo {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 0.5rem 0 1rem 0;
}
.sidebar-logo-icon {
    width: 36px;
    height: 36px;
    background: linear-gradient(135deg, #1366D6, #0AADA0);
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.1rem;
    color: white;
}
.sidebar-logo-text {
    font-size: 1rem;
    font-weight: 700;
    color: #1A2B45;
    line-height: 1.1;
}
.sidebar-logo-sub {
    font-size: 0.72rem;
    color: #5A6B7E;
}

/* ── Секция ── */
.section-title {
    font-size: 1.05rem;
    font-weight: 600;
    color: #1A2B45;
    margin: 1.25rem 0 0.75rem 0;
    display: flex;
    align-items: center;
    gap: 8px;
}
.section-title::after {
    content: '';
    flex: 1;
    height: 1px;
    background: #E1E8F5;
    margin-left: 8px;
}

/* ── Убираем лишние паддинги Streamlit ── */
.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 2rem !important;
    max-width: 1200px !important;
}

/* Убрать красную полосу сверху */
[data-testid="stDecoration"] {
    display: none !important;
}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Состояние сессии
# ---------------------------------------------------------------------------

def init_session():
    defaults = {
        "patient": "default",
        "backend_mode": "anthropic",
        "api_key": "",
        "ollama_model": "",
        "analysis_result": "",
        "anthropic_model": "claude-sonnet-4-6",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()


def get_patient() -> str:
    return st.session_state.patient


def ensure_db():
    patient = get_patient()
    if not db.get_db_path(patient).exists():
        db.init_db(patient)


def get_db_stats() -> dict:
    ensure_db()
    conn = db.get_conn(get_patient())
    stats = {}
    for t in ("documents", "measurements", "open_questions"):
        (stats[t],) = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()
    row = conn.execute(
        "SELECT MIN(doc_date), MAX(doc_date) FROM documents WHERE doc_date IS NOT NULL"
    ).fetchone()
    stats["date_min"] = row[0]
    stats["date_max"] = row[1]
    conn.close()
    return stats


def get_backend() -> backends.LLMBackend:
    return backends.get_backend(
        mode=st.session_state.backend_mode,
        api_key=st.session_state.api_key,
        model=st.session_state.anthropic_model
              if st.session_state.backend_mode == "anthropic"
              else st.session_state.ollama_model,
    )


def build_analysis_prompt(patient: str) -> str:
    ensure_db()
    conn = db.get_conn(patient)
    measurements = conn.execute("""
        SELECT a.name_ru, a.code, m.value_num, m.unit, m.flag, m.measured_at,
               m.ref_low, m.ref_high
        FROM measurements m JOIN analytes a ON a.id = m.analyte_id
        ORDER BY a.code, m.measured_at LIMIT 200
    """).fetchall()
    trends = {}
    for m in measurements:
        code = m["code"]
        if code not in trends:
            trends[code] = {"name": m["name_ru"], "unit": m["unit"], "values": []}
        entry = {"date": m["measured_at"], "value": m["value_num"]}
        if m["flag"]:
            entry["flag"] = m["flag"]
        if m["ref_low"]:
            entry["ref"] = f"{m['ref_low']}–{m['ref_high']}"
        trends[code]["values"].append(entry)
    questions = conn.execute(
        "SELECT priority, question FROM open_questions WHERE patient_id=? AND status='open'",
        (patient,)
    ).fetchall()
    grep_hits = []
    for kw in ["семейный анамнез", "анамнез", "аллергия", "операция", "онкол", "рак"]:
        grep_hits.extend(db.text_search(conn, kw)[:2])
    conn.close()
    data_summary = json.dumps({
        "analyte_trends": trends,
        "open_questions": [dict(q) for q in questions],
        "raw_text_findings": [
            f"[{h.get('keyword','')}] {h['doc_date'] or '?'}: {h['snippet'][:120]}"
            for h in grep_hits[:12]
        ]
    }, ensure_ascii=False, indent=2)
    return f"""
## ДАННЫЕ ИЗ МЕДИЦИНСКОГО АРХИВА

```json
{data_summary}
```

## ЗАДАЧА

Составь problem list для визита к врачу:
1. Таблицу: Проблема | Данные/тренды | Протокол (гайдлайн + Class/Level) | Действие | Специалист
2. Сводку: анализы, исследования, специалисты
3. Раздел «Что не делаем и почему»
4. Открытые вопросы и развилки «если→то»

Формат: Markdown. Тон: нейтральный, фактический.
"""


# ---------------------------------------------------------------------------
# Боковая панель
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("""
    <div class="sidebar-logo">
        <div class="sidebar-logo-icon">⚕</div>
        <div>
            <div class="sidebar-logo-text">МедАналитик</div>
            <div class="sidebar-logo-sub">Подготовка к визиту</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # Профиль
    st.markdown('<div style="font-size:0.78rem;font-weight:600;color:#5A6B7E;text-transform:uppercase;letter-spacing:0.04em;margin-bottom:4px">👤 Профиль пациента</div>', unsafe_allow_html=True)
    patient_input = st.text_input(
        "Профиль", value=st.session_state.patient,
        placeholder="default", label_visibility="collapsed",
        help="Разные профили — разные базы данных. Удобно для семьи.",
    )
    if patient_input != st.session_state.patient:
        st.session_state.patient = patient_input
        st.rerun()

    st.divider()

    # Режим
    st.markdown('<div style="font-size:0.78rem;font-weight:600;color:#5A6B7E;text-transform:uppercase;letter-spacing:0.04em;margin-bottom:8px">⚙️ Режим анализа</div>', unsafe_allow_html=True)

    mode = st.radio(
        "Режим", ["anthropic", "ollama"],
        format_func=lambda x: "☁️ Облачный (Anthropic)" if x == "anthropic" else "💻 Локальный (Ollama)",
        index=0 if st.session_state.backend_mode == "anthropic" else 1,
        label_visibility="collapsed",
    )
    st.session_state.backend_mode = mode

    if mode == "anthropic":
        api_key = st.text_input(
            "API-ключ", type="password",
            value=st.session_state.api_key or os.environ.get("ANTHROPIC_API_KEY", ""),
            placeholder="sk-ant-...",
            help="Получить ключ: console.anthropic.com",
        )
        st.session_state.api_key = api_key
        model_choice = st.selectbox(
            "Модель",
            ["claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5-20251001"],
            help="Sonnet — оптимальный баланс. Opus — лучшее качество. Haiku — быстрее и дешевле.",
        )
        st.session_state.anthropic_model = model_choice
    else:
        st.markdown('<div style="background:#EBF5FF;border-radius:8px;padding:0.6rem 0.8rem;font-size:0.82rem;color:#2A4A7F;margin-bottom:8px">Требуется <b>ollama serve</b> на этом ПК</div>', unsafe_allow_html=True)
        ollama_b = backends.OllamaBackend()
        available = ollama_b.list_models()
        if available:
            ollama_model = st.selectbox("Модель", available)
            st.session_state.ollama_model = ollama_model
        else:
            st.warning("Нет моделей. Запустите:")
            st.code("ollama pull llama3.1")
            st.session_state.ollama_model = "llama3.1"

    if st.button("🔍 Проверить подключение", use_container_width=True):
        with st.spinner("Проверяю…"):
            b = get_backend()
            ok, msg = b.is_available()
            if ok:
                st.success(f"✓ {msg}")
            else:
                st.error(msg)

    st.divider()

    # Статистика
    st.markdown('<div style="font-size:0.78rem;font-weight:600;color:#5A6B7E;text-transform:uppercase;letter-spacing:0.04em;margin-bottom:8px">📊 Архив</div>', unsafe_allow_html=True)
    try:
        stats = get_db_stats()
        c1, c2 = st.columns(2)
        c1.metric("Документов", stats["documents"])
        c2.metric("Измерений", stats["measurements"])
        if stats["date_min"]:
            st.caption(f"📅 {stats['date_min'][:7]} — {stats['date_max'][:7]}")
    except Exception:
        st.caption("Архив пуст")


# ---------------------------------------------------------------------------
# Заголовок
# ---------------------------------------------------------------------------

st.markdown("""
<div class="app-header">
    <div class="app-header-icon">⚕️</div>
    <div>
        <div class="app-header-title">МедАналитик</div>
        <div class="app-header-sub">
            Структурированный список проблем для визита к врачу
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Вкладки
# ---------------------------------------------------------------------------

tab_upload, tab_archive, tab_analyze, tab_result = st.tabs([
    "📂  Загрузка документов",
    "🗂  Архив и тренды",
    "🤖  Анализ",
    "📋  Результат",
])


# ══════════════════════════════════════════════════════════════════════════════
# Вкладка 1 — Загрузка
# ══════════════════════════════════════════════════════════════════════════════

with tab_upload:
    st.markdown('<div class="section-title">📂 Загрузите медицинские документы</div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="color:#5A6B7E;font-size:0.9rem;margin-bottom:1.25rem">'
        'Поддерживаются PDF, JPG, PNG, TXT. '
        'Дубликаты определяются автоматически по содержимому — '
        'один и тот же файл не загрузится дважды.'
        '</div>',
        unsafe_allow_html=True
    )

    col_drop, col_meta = st.columns([3, 2], gap="large")

    with col_meta:
        st.markdown('<div class="med-card">', unsafe_allow_html=True)
        st.markdown("**Параметры загрузки**")
        doc_type = st.selectbox(
            "Тип документа",
            ["lab", "imaging", "discharge", "note", "other"],
            format_func=lambda x: {
                "lab": "🧪 Анализы крови / мочи",
                "imaging": "🔬 Снимки, УЗИ, КТ, МРТ",
                "discharge": "🏥 Выписной эпикриз",
                "note": "📝 Заключение специалиста",
                "other": "📄 Другой документ",
            }.get(x, x),
        )
        source_org = st.text_input(
            "Медицинская организация",
            placeholder="Гемотест, Инвитро, МЕДСИ…",
        )
        st.markdown('</div>', unsafe_allow_html=True)

    with col_drop:
        uploaded_files = st.file_uploader(
            "Перетащите файлы сюда или нажмите для выбора",
            accept_multiple_files=True,
            type=["pdf", "jpg", "jpeg", "png", "txt"],
        )

    if uploaded_files:
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:8px;margin:0.5rem 0">'
            f'<span style="background:#EBF5FF;color:#1366D6;border-radius:20px;'
            f'padding:3px 12px;font-size:0.85rem;font-weight:600">'
            f'✓ Выбрано файлов: {len(uploaded_files)}</span></div>',
            unsafe_allow_html=True
        )

        if st.button("⬆️ Загрузить в архив", type="primary", use_container_width=False):
            ensure_db()
            patient = get_patient()
            progress = st.progress(0)
            status_text = st.empty()
            ok_count = skipped = errors = 0

            for i, uf in enumerate(uploaded_files):
                progress.progress((i + 1) / len(uploaded_files))
                status_text.markdown(
                    f'<div style="color:#5A6B7E;font-size:0.85rem">⏳ {uf.name}</div>',
                    unsafe_allow_html=True
                )
                suffix = Path(uf.name).suffix
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    tmp.write(uf.read())
                    tmp_path = Path(tmp.name)
                try:
                    r = loader.load_file(tmp_path, patient, doc_type=doc_type, source_org=source_org)
                    if r:
                        ok_count += 1
                    else:
                        skipped += 1
                except Exception as e:
                    errors += 1
                    st.warning(f"⚠ {uf.name}: {e}")
                finally:
                    tmp_path.unlink(missing_ok=True)

            progress.empty()
            status_text.empty()

            cols = st.columns(3)
            if ok_count:
                cols[0].success(f"✓ Загружено: **{ok_count}**")
            if skipped:
                cols[1].info(f"⏭ Дублей пропущено: **{skipped}**")
            if errors:
                cols[2].error(f"✗ Ошибок: **{errors}**")
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# Вкладка 2 — Архив
# ══════════════════════════════════════════════════════════════════════════════

with tab_archive:
    ensure_db()
    patient = get_patient()
    conn = db.get_conn(patient)

    docs = conn.execute(
        "SELECT id, doc_date, doc_type, source_org, extraction_method, page_count "
        "FROM documents ORDER BY doc_date DESC NULLS LAST LIMIT 100"
    ).fetchall()

    if not docs:
        st.markdown("""
        <div class="med-card" style="text-align:center;padding:2.5rem;color:#5A6B7E">
            <div style="font-size:2.5rem;margin-bottom:0.5rem">📭</div>
            <div style="font-weight:600;margin-bottom:0.25rem">Архив пуст</div>
            <div style="font-size:0.88rem">Загрузите документы на вкладке «Загрузка»</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="section-title">📄 Документы в архиве — {len(docs)}</div>', unsafe_allow_html=True)
        type_icons = {"lab": "🧪", "imaging": "🔬", "discharge": "🏥", "note": "📝"}
        rows = [{
            "Дата": (d["doc_date"] or "—")[:10],
            "Тип": type_icons.get(d["doc_type"], "📄") + " " + (d["doc_type"] or ""),
            "Организация": d["source_org"] or "—",
            "Метод извлечения": d["extraction_method"] or "—",
            "Страниц": d["page_count"] or "—",
        } for d in docs]
        st.dataframe(rows, use_container_width=True, hide_index=True)

    st.divider()

    # Тренды
    st.markdown('<div class="section-title">📈 Тренды показателей</div>', unsafe_allow_html=True)
    analytes_list = conn.execute(
        "SELECT DISTINCT a.code, a.name_ru FROM analytes a "
        "JOIN measurements m ON m.analyte_id = a.id ORDER BY a.name_ru"
    ).fetchall()

    if analytes_list:
        selected = st.selectbox(
            "Показатель",
            [a["code"] for a in analytes_list],
            format_func=lambda c: next((a["name_ru"] for a in analytes_list if a["code"] == c), c),
            label_visibility="visible",
        )
        trend_rows = conn.execute("""
            SELECT m.measured_at, m.value_num, m.unit, m.flag, m.ref_low, m.ref_high
            FROM measurements m JOIN analytes a ON a.id = m.analyte_id
            WHERE a.code = ? ORDER BY m.measured_at
        """, (selected,)).fetchall()

        if trend_rows:
            import pandas as pd
            df = pd.DataFrame([dict(r) for r in trend_rows])
            df["measured_at"] = pd.to_datetime(df["measured_at"], errors="coerce")
            df = df.dropna(subset=["measured_at"]).set_index("measured_at")

            st.line_chart(
                df["value_num"],
                color="#1366D6",
                use_container_width=True,
            )

            display = [{
                "Дата": str(r["measured_at"] or "")[:10],
                "Значение": f"{r['value_num']} {r['unit'] or ''}",
                "Флаг": r["flag"] or "—",
                "Референс": f"{r['ref_low']}–{r['ref_high']}" if r["ref_low"] else "—",
            } for r in trend_rows]
            st.dataframe(display, use_container_width=True, hide_index=True)
    else:
        st.info("Данные об измерениях появятся после загрузки результатов анализов.")

    # Поиск
    st.divider()
    st.markdown('<div class="section-title">🔍 Поиск по документам</div>', unsafe_allow_html=True)
    search_query = st.text_input(
        "Поиск", placeholder="аденома, семейный анамнез, аллергия…",
        label_visibility="collapsed",
    )
    if search_query:
        hits = db.text_search(conn, search_query)
        if hits:
            st.markdown(f'<div style="color:#5A6B7E;font-size:0.85rem;margin-bottom:0.5rem">Найдено: {len(hits)}</div>', unsafe_allow_html=True)
            for h in hits:
                with st.expander(f"📄 {h['doc_date'] or '?'} — {h['source'] or 'документ'}"):
                    st.markdown(f'<div style="font-family:monospace;font-size:0.85rem;background:#F7F9FC;padding:0.75rem;border-radius:6px;white-space:pre-wrap">{h["snippet"]}</div>', unsafe_allow_html=True)
        else:
            st.info("По вашему запросу ничего не найдено.")

    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# Вкладка 3 — Анализ
# ══════════════════════════════════════════════════════════════════════════════

with tab_analyze:
    st.markdown('<div class="section-title">🤖 Генерация списка проблем</div>', unsafe_allow_html=True)

    st.markdown("""
    <div class="disclaimer-box">
        <strong>⚕️ Важно:</strong> МедАналитик — инструмент анализа данных, не медицинский специалист.
        Все выводы носят информационный характер и <strong>требуют обсуждения с лечащим врачом</strong>.
        Не используется для острых состояний и неотложной медицинской помощи.
    </div>
    """, unsafe_allow_html=True)

    # Как это работает
    col_a, col_b, col_c = st.columns(3)
    col_a.markdown("""
    <div class="med-card" style="text-align:center">
        <div style="font-size:1.8rem;margin-bottom:6px">📊</div>
        <div style="font-weight:600;font-size:0.9rem;margin-bottom:4px">Анализ архива</div>
        <div style="font-size:0.8rem;color:#5A6B7E">Тренды показателей, динамика за все годы</div>
    </div>
    """, unsafe_allow_html=True)
    col_b.markdown("""
    <div class="med-card" style="text-align:center">
        <div style="font-size:1.8rem;margin-bottom:6px">📋</div>
        <div style="font-weight:600;font-size:0.9rem;margin-bottom:4px">Problem list</div>
        <div style="font-size:0.8rem;color:#5A6B7E">По методике POMR с привязкой к гайдлайнам</div>
    </div>
    """, unsafe_allow_html=True)
    col_c.markdown("""
    <div class="med-card" style="text-align:center">
        <div style="font-size:1.8rem;margin-bottom:6px">📥</div>
        <div style="font-weight:600;font-size:0.9rem;margin-bottom:4px">DOCX для печати</div>
        <div style="font-size:0.8rem;color:#5A6B7E">Альбомный формат, готов для врача</div>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    with st.expander("➕ Добавить контекст (необязательно)", expanded=False):
        extra_context = st.text_area(
            "Что важно учесть",
            placeholder=(
                "Пример: планирую авиаперелёт 8 ч в декабре. "
                "У отца был инфаркт в 58 лет. "
                "Периодически болит голова по утрам."
            ),
            height=100,
            label_visibility="collapsed",
        )
    if "extra_context" not in dir():
        extra_context = ""

    stats = get_db_stats()
    has_docs = stats["documents"] > 0

    if not has_docs:
        st.markdown("""
        <div class="med-card" style="text-align:center;padding:2rem;border:2px dashed #9BB8E8">
            <div style="font-size:2rem;margin-bottom:8px">📭</div>
            <div style="font-weight:600;color:#1A2B45">Нет документов для анализа</div>
            <div style="color:#5A6B7E;font-size:0.88rem;margin-top:4px">
                Перейдите на вкладку «Загрузка» и добавьте медицинские документы
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        mode_label = "☁️ Anthropic API" if st.session_state.backend_mode == "anthropic" else "💻 Ollama (локально)"
        st.markdown(
            f'<div style="background:#F0F8FF;border:1px solid #9BB8E8;border-radius:8px;'
            f'padding:0.75rem 1rem;margin-bottom:1rem;font-size:0.88rem;color:#2A4A7F">'
            f'📂 В архиве: <b>{stats["documents"]} документов</b>, '
            f'<b>{stats["measurements"]} измерений</b> &nbsp;·&nbsp; '
            f'Режим: <b>{mode_label}</b>'
            f'</div>',
            unsafe_allow_html=True
        )

        if st.button("🤖 Сгенерировать список проблем", type="primary"):
            b = get_backend()
            ok, msg = b.is_available()
            if not ok:
                st.error(f"Бэкенд недоступен: {msg}")
            else:
                patient = get_patient()
                prompt = build_analysis_prompt(patient)
                if extra_context:
                    prompt += f"\n\n## ДОПОЛНИТЕЛЬНЫЙ КОНТЕКСТ\n{extra_context}"

                with st.spinner("Анализирую данные… Обычно занимает 30–90 секунд."):
                    try:
                        result = b.chat(user=prompt, system=SYSTEM_ANALYST, max_tokens=8192)
                        st.session_state.analysis_result = result

                        ensure_db()
                        out_dir = db.DATA_DIR / patient
                        out_dir.mkdir(parents=True, exist_ok=True)
                        ts = datetime.now().strftime("%Y%m%d_%H%M")
                        (out_dir / f"problem_list_{ts}.md").write_text(result, encoding="utf-8")

                        st.success("✓ Готово! Перейдите на вкладку **«Результат»**.")
                    except Exception as e:
                        st.error(f"Ошибка: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Вкладка 4 — Результат
# ══════════════════════════════════════════════════════════════════════════════

with tab_result:
    result = st.session_state.analysis_result

    if not result:
        st.markdown("""
        <div class="med-card" style="text-align:center;padding:2.5rem;color:#5A6B7E">
            <div style="font-size:2.5rem;margin-bottom:0.5rem">📋</div>
            <div style="font-weight:600;margin-bottom:0.25rem">Результат ещё не готов</div>
            <div style="font-size:0.88rem">Запустите анализ на вкладке «Анализ»</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown('<div class="section-title">📋 Список проблем для врача</div>', unsafe_allow_html=True)

        # Кнопки
        col_md, col_docx, _, _ = st.columns(4)
        with col_md:
            st.download_button(
                "⬇️ Скачать Markdown",
                data=result.encode("utf-8"),
                file_name=f"problem_list_{datetime.now().strftime('%Y%m%d')}.md",
                mime="text/markdown",
                use_container_width=True,
            )
        with col_docx:
            try:
                import render as renderer
                with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
                    tmp_path = Path(tmp.name)
                renderer.render_docx(result, tmp_path)
                docx_bytes = tmp_path.read_bytes()
                tmp_path.unlink(missing_ok=True)
                st.download_button(
                    "⬇️ Скачать DOCX",
                    data=docx_bytes,
                    file_name=f"problem_list_{datetime.now().strftime('%Y%m%d')}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                )
            except Exception as e:
                st.button("⬇️ DOCX", disabled=True, use_container_width=True, help=str(e))

        st.divider()

        # Рендер результата
        st.markdown(
            '<div style="background:#FFFFFF;border:1px solid #E1E8F5;border-radius:12px;'
            'padding:1.5rem 2rem;line-height:1.7">',
            unsafe_allow_html=True
        )
        st.markdown(result)
        st.markdown('</div>', unsafe_allow_html=True)
