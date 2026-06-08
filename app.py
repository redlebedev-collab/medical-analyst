"""
app.py — Streamlit-интерфейс «Аналитик медицинских справок».

Запуск:
    streamlit run app.py

Режимы:
    Облачный  — Anthropic API (нужен ключ)
    Локальный — Ollama (нужен запущенный ollama serve)
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
    page_title="Аналитик медицинских справок",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Стили
# ---------------------------------------------------------------------------

st.markdown("""
<style>
    .main-header {
        font-size: 1.8rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        color: #888;
        font-size: 0.95rem;
        margin-bottom: 1.5rem;
    }
    .status-ok   { color: #4CAF50; font-weight: 600; }
    .status-err  { color: #f44336; font-weight: 600; }
    .disclaimer  {
        background: #1e3a5f;
        border-left: 4px solid #2196F3;
        padding: 0.75rem 1rem;
        border-radius: 4px;
        font-size: 0.9rem;
        margin-bottom: 1rem;
    }
    .metric-card {
        background: #1a1a2e;
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Сессия — состояние
# ---------------------------------------------------------------------------

def init_session():
    defaults = {
        "patient": "default",
        "backend_mode": "anthropic",
        "api_key": "",
        "ollama_model": "",
        "analysis_result": "",
        "last_docs_count": 0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_session()


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def get_patient() -> str:
    return st.session_state.patient


def ensure_db():
    """Инициализирует БД для текущего пациента если нужно."""
    patient = get_patient()
    if not db.get_db_path(patient).exists():
        db.init_db(patient)


def get_db_stats() -> dict:
    """Возвращает статистику архива."""
    ensure_db()
    patient = get_patient()
    conn = db.get_conn(patient)
    stats = {}
    for table in ("documents", "measurements", "open_questions"):
        (stats[table],) = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    # Диапазон дат
    row = conn.execute(
        "SELECT MIN(doc_date), MAX(doc_date) FROM documents WHERE doc_date IS NOT NULL"
    ).fetchone()
    stats["date_min"] = row[0]
    stats["date_max"] = row[1]
    conn.close()
    return stats


def get_backend() -> backends.LLMBackend:
    mode = st.session_state.backend_mode
    return backends.get_backend(
        mode=mode,
        api_key=st.session_state.api_key,
        model=st.session_state.ollama_model,
    )


def build_analysis_prompt(patient: str) -> str:
    """Собирает промпт для анализа из БД пациента."""
    ensure_db()
    conn = db.get_conn(patient)

    # Тренды измерений
    measurements = conn.execute("""
        SELECT a.name_ru, a.code, m.value_num, m.unit, m.flag, m.measured_at,
               m.ref_low, m.ref_high
        FROM measurements m
        JOIN analytes a ON a.id = m.analyte_id
        ORDER BY a.code, m.measured_at
        LIMIT 200
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

    # Открытые вопросы
    questions = conn.execute(
        "SELECT priority, question FROM open_questions WHERE patient_id=? AND status='open'",
        (patient,)
    ).fetchall()

    # Grep по ключевым словам в raw_text
    keywords = ["семейный анамнез", "анамнез", "аллергия", "операция",
                 "госпитализация", "онкол", "рак", "курени"]
    grep_hits = []
    for kw in keywords:
        hits = db.text_search(conn, kw)
        grep_hits.extend(hits[:3])

    conn.close()

    data_summary = json.dumps({
        "analyte_trends": trends,
        "open_questions": [dict(q) for q in questions],
        "raw_text_findings": [
            f"[{h['keyword']}] {h['doc_date'] or '?'}: {h['snippet'][:120]}"
            for h in grep_hits[:15]
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
4. Открытые вопросы / развилки «если→то»

Формат: Markdown. Тон: нейтральный, фактический.
"""


# ---------------------------------------------------------------------------
# Боковая панель
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### 🏥 Аналитик справок")
    st.divider()

    # Профиль пациента
    st.markdown("**👤 Пациент**")
    patient_input = st.text_input(
        "Имя профиля",
        value=st.session_state.patient,
        placeholder="default",
        help="Каждый профиль — отдельная БД. Переключайтесь между членами семьи.",
        label_visibility="collapsed",
    )
    if patient_input != st.session_state.patient:
        st.session_state.patient = patient_input
        st.rerun()

    st.divider()

    # Режим работы
    st.markdown("**⚙️ Режим анализа**")
    mode = st.radio(
        "Режим",
        options=["anthropic", "ollama"],
        format_func=lambda x: "☁️ Облачный (Anthropic)" if x == "anthropic" else "💻 Локальный (Ollama)",
        index=0 if st.session_state.backend_mode == "anthropic" else 1,
        label_visibility="collapsed",
    )
    st.session_state.backend_mode = mode

    if mode == "anthropic":
        api_key = st.text_input(
            "API-ключ Anthropic",
            value=st.session_state.api_key or os.environ.get("ANTHROPIC_API_KEY", ""),
            type="password",
            placeholder="sk-ant-...",
            help="Получить: https://console.anthropic.com/settings/keys",
        )
        st.session_state.api_key = api_key

        model_choice = st.selectbox(
            "Модель",
            ["claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5-20251001"],
            help="Opus — умнее, дороже. Haiku — дешевле, быстрее.",
        )

    else:  # ollama
        st.info("Требуется запущенный `ollama serve` на этом компьютере.")

        # Получаем список моделей
        backend_check = backends.OllamaBackend()
        available_models = backend_check.list_models()

        if available_models:
            ollama_model = st.selectbox("Модель", available_models)
            st.session_state.ollama_model = ollama_model
        else:
            st.warning("Модели не найдены. Запустите ollama и загрузите модель:")
            st.code("ollama pull llama3.1")
            st.session_state.ollama_model = "llama3.1"

    # Проверка доступности
    st.divider()
    if st.button("🔍 Проверить подключение", use_container_width=True):
        with st.spinner("Проверяю…"):
            b = get_backend()
            ok, msg = b.is_available()
            if ok:
                st.success(msg)
            else:
                st.error(msg)

    # Статистика архива
    st.divider()
    st.markdown("**📊 Архив**")
    try:
        stats = get_db_stats()
        col1, col2 = st.columns(2)
        col1.metric("Документов", stats["documents"])
        col2.metric("Измерений", stats["measurements"])
        if stats["date_min"]:
            st.caption(f"{stats['date_min'][:7]} → {stats['date_max'][:7]}")
    except Exception:
        st.caption("Архив пуст")


# ---------------------------------------------------------------------------
# Основной контент — вкладки
# ---------------------------------------------------------------------------

st.markdown('<div class="main-header">🏥 Аналитик медицинских справок</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Структурированный список проблем для визита к врачу</div>', unsafe_allow_html=True)

tab_upload, tab_archive, tab_analyze, tab_result = st.tabs([
    "📂 Загрузка",
    "🗂 Архив",
    "🤖 Анализ",
    "📋 Результат",
])


# ── Вкладка 1: Загрузка ──────────────────────────────────────────────────────

with tab_upload:
    st.markdown("### Загрузите медицинские документы")
    st.markdown("Поддерживаются PDF, JPG, PNG, TXT. Дубликаты определяются автоматически.")

    col_upload, col_meta = st.columns([2, 1])

    with col_meta:
        st.markdown("**Метаданные документов**")
        doc_type = st.selectbox(
            "Тип документа",
            ["lab", "imaging", "discharge", "note", "other"],
            format_func=lambda x: {
                "lab": "🧪 Анализы",
                "imaging": "🔬 Снимки / УЗИ",
                "discharge": "🏥 Выписка",
                "note": "📝 Заметка",
                "other": "📄 Другое",
            }.get(x, x),
        )
        source_org = st.text_input(
            "Организация",
            placeholder="Лаборатория Гемотест, МЕДСИ…",
            help="Откуда документ",
        )

    with col_upload:
        uploaded_files = st.file_uploader(
            "Перетащите файлы сюда или нажмите Browse",
            accept_multiple_files=True,
            type=["pdf", "jpg", "jpeg", "png", "txt"],
            label_visibility="collapsed",
        )

    if uploaded_files:
        st.markdown(f"**Выбрано файлов: {len(uploaded_files)}**")

        if st.button("⬆️ Загрузить в архив", type="primary", use_container_width=True):
            ensure_db()
            patient = get_patient()
            progress = st.progress(0)
            status = st.empty()
            ok_count = skipped_count = err_count = 0

            for i, uploaded_file in enumerate(uploaded_files):
                progress.progress((i + 1) / len(uploaded_files))
                status.text(f"Обрабатываю: {uploaded_file.name}…")

                # Сохраняем во временный файл
                suffix = Path(uploaded_file.name).suffix
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    tmp.write(uploaded_file.read())
                    tmp_path = Path(tmp.name)

                try:
                    result = loader.load_file(
                        tmp_path, patient,
                        doc_type=doc_type,
                        source_org=source_org,
                    )
                    if result:
                        ok_count += 1
                    else:
                        skipped_count += 1
                except Exception as e:
                    err_count += 1
                    st.warning(f"⚠ {uploaded_file.name}: {e}")
                finally:
                    tmp_path.unlink(missing_ok=True)

            progress.empty()
            status.empty()

            if ok_count:
                st.success(f"✓ Загружено: {ok_count}")
            if skipped_count:
                st.info(f"⏭ Пропущено (дубли): {skipped_count}")
            if err_count:
                st.error(f"✗ Ошибок: {err_count}")

            st.rerun()


# ── Вкладка 2: Архив ─────────────────────────────────────────────────────────

with tab_archive:
    st.markdown("### Архив документов")

    ensure_db()
    patient = get_patient()
    conn = db.get_conn(patient)

    # Документы
    docs = conn.execute(
        "SELECT id, doc_date, doc_type, source_org, extraction_method, page_count, loaded_at "
        "FROM documents ORDER BY doc_date DESC NULLS LAST LIMIT 100"
    ).fetchall()

    if not docs:
        st.info("Архив пуст. Загрузите документы на вкладке «Загрузка».")
    else:
        st.markdown(f"**Документов в архиве: {len(docs)}**")

        type_icons = {"lab": "🧪", "imaging": "🔬", "discharge": "🏥", "note": "📝"}
        rows = []
        for d in docs:
            rows.append({
                "Дата": d["doc_date"] or "—",
                "Тип": type_icons.get(d["doc_type"], "📄") + " " + (d["doc_type"] or ""),
                "Организация": d["source_org"] or "—",
                "Метод": d["extraction_method"] or "—",
                "Стр.": d["page_count"] or "—",
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)

    st.divider()

    # Тренды
    st.markdown("### Тренды показателей")
    analytes_list = conn.execute(
        "SELECT DISTINCT a.code, a.name_ru FROM analytes a "
        "JOIN measurements m ON m.analyte_id = a.id ORDER BY a.name_ru"
    ).fetchall()

    if analytes_list:
        selected = st.selectbox(
            "Выберите показатель",
            options=[a["code"] for a in analytes_list],
            format_func=lambda c: next(
                (a["name_ru"] for a in analytes_list if a["code"] == c), c
            ),
        )
        trend_data = conn.execute("""
            SELECT m.measured_at, m.value_num, m.unit, m.flag, m.ref_low, m.ref_high
            FROM measurements m
            JOIN analytes a ON a.id = m.analyte_id
            WHERE a.code = ?
            ORDER BY m.measured_at
        """, (selected,)).fetchall()

        if trend_data:
            import pandas as pd
            df = pd.DataFrame([dict(r) for r in trend_data])
            df["measured_at"] = pd.to_datetime(df["measured_at"])
            df = df.rename(columns={"measured_at": "Дата", "value_num": "Значение"})

            st.line_chart(df.set_index("Дата")["Значение"])

            # Таблица
            display_rows = []
            for r in trend_data:
                flag = f" [{r['flag']}]" if r["flag"] else ""
                ref = f"{r['ref_low']}–{r['ref_high']}" if r["ref_low"] else "—"
                display_rows.append({
                    "Дата": (r["measured_at"] or "")[:10],
                    "Значение": f"{r['value_num']} {r['unit'] or ''}{flag}",
                    "Референс": ref,
                })
            st.dataframe(display_rows, use_container_width=True, hide_index=True)
    else:
        st.info("Нет данных об измерениях. Загрузите результаты анализов.")

    # Полнотекстовый поиск
    st.divider()
    st.markdown("### Поиск по документам")
    search_query = st.text_input("Поиск в сырых текстах", placeholder="аденома, анамнез, аллергия…")
    if search_query:
        hits = db.text_search(conn, search_query)
        if hits:
            for h in hits:
                with st.expander(f"[{h['doc_date'] or '?'}] {h['source'] or 'документ'}"):
                    st.text(h["snippet"])
        else:
            st.info("Совпадений не найдено.")

    conn.close()


# ── Вкладка 3: Анализ ────────────────────────────────────────────────────────

with tab_analyze:
    st.markdown("### Генерация списка проблем")

    st.markdown("""
<div class="disclaimer">
⚕️ <strong>Важно:</strong> инструмент — аналитик данных, не врач.
Все выводы требуют обсуждения с лечащим специалистом.
Не используется для острых состояний и неотложной помощи.
</div>
""", unsafe_allow_html=True)

    # Дополнительный контекст
    with st.expander("➕ Дополнительный контекст (необязательно)"):
        extra_context = st.text_area(
            "Укажите что важно учесть",
            placeholder=(
                "Пример: планирую авиаперелёт в декабре, 8 часов. "
                "Семейный анамнез: у отца инфаркт в 58 лет. "
                "Текущие жалобы: периодические головные боли."
            ),
            height=120,
        )

    # Проверка готовности
    stats = get_db_stats()
    ready = stats["documents"] > 0

    if not ready:
        st.warning("Архив пуст. Сначала загрузите документы на вкладке «Загрузка».")
    else:
        st.markdown(f"В архиве: **{stats['documents']} документов**, **{stats['measurements']} измерений**")

        col_btn, col_info = st.columns([1, 2])
        with col_btn:
            run_analysis = st.button(
                "🤖 Запустить анализ",
                type="primary",
                use_container_width=True,
                disabled=not ready,
            )
        with col_info:
            mode_label = "☁️ Anthropic API" if st.session_state.backend_mode == "anthropic" else "💻 Ollama (локально)"
            st.markdown(f"Режим: **{mode_label}**")

        if run_analysis:
            # Проверяем бэкенд
            b = get_backend()
            ok, msg = b.is_available()
            if not ok:
                st.error(f"Бэкенд недоступен: {msg}")
            else:
                patient = get_patient()
                prompt = build_analysis_prompt(patient)
                if extra_context:
                    prompt += f"\n\n## ДОПОЛНИТЕЛЬНЫЙ КОНТЕКСТ\n{extra_context}"

                with st.spinner("Анализирую данные… Это займёт 30–120 секунд."):
                    try:
                        result = b.chat(
                            user=prompt,
                            system=SYSTEM_ANALYST,
                            max_tokens=8192,
                        )
                        st.session_state.analysis_result = result

                        # Сохраняем в файл
                        ensure_db()
                        out_dir = db.DATA_DIR / patient
                        out_dir.mkdir(parents=True, exist_ok=True)
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
                        out_path = out_dir / f"problem_list_{timestamp}.md"
                        out_path.write_text(result, encoding="utf-8")

                        st.success("✓ Анализ готов! Откройте вкладку «Результат».")
                    except Exception as e:
                        st.error(f"Ошибка при анализе: {e}")


# ── Вкладка 4: Результат ─────────────────────────────────────────────────────

with tab_result:
    st.markdown("### Список проблем")

    result = st.session_state.analysis_result

    if not result:
        st.info("Результат появится после запуска анализа на вкладке «Анализ».")
    else:
        # Кнопки скачивания
        col_md, col_docx, col_copy = st.columns(3)

        with col_md:
            st.download_button(
                "⬇️ Скачать Markdown",
                data=result.encode("utf-8"),
                file_name=f"problem_list_{datetime.now().strftime('%Y%m%d')}.md",
                mime="text/markdown",
                use_container_width=True,
            )

        with col_docx:
            # Генерируем DOCX на лету
            try:
                import render as renderer
                import io

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
                st.button("⬇️ Скачать DOCX", disabled=True, use_container_width=True,
                          help=f"Ошибка: {e}")

        with col_copy:
            st.button("📋 Скопировать", use_container_width=True,
                      help="Выделите текст ниже и скопируйте вручную (Ctrl+A, Ctrl+C)")

        st.divider()

        # Рендерим Markdown
        st.markdown(result)
