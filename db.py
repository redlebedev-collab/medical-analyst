"""
db.py — SQLite-архив медицинских данных.

Использование:
    python db.py init                   # создать схему
    python db.py briefing               # стартовый брифинг
    MEDIC_PATIENT=member_a python db.py briefing
"""

import os
import sqlite3
import sys
from pathlib import Path
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent / "data"


def get_patient() -> str:
    """Возвращает текущего пациента из переменной окружения."""
    patient = os.environ.get("MEDIC_PATIENT", "default")
    return patient


def get_db_path(patient: str | None = None) -> Path:
    """Возвращает путь к БД для пациента."""
    patient = patient or get_patient()
    patient_dir = DATA_DIR / patient
    patient_dir.mkdir(parents=True, exist_ok=True)
    return patient_dir / "medic.db"


def get_conn(patient: str | None = None) -> sqlite3.Connection:
    """Открывает соединение с БД пациента."""
    path = get_db_path(patient)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except Exception:
        pass  # WAL недоступен на некоторых ФС (сетевые диски)
    return conn


# ---------------------------------------------------------------------------
# Схема
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    file_hash       TEXT UNIQUE NOT NULL,       -- sha256, дедупликация
    doc_date        TEXT,                       -- дата документа (ISO 8601)
    doc_type        TEXT,                       -- lab / imaging / discharge / note
    source_org      TEXT,                       -- организация
    raw_text        TEXT,                       -- ВЕСЬ распознанный текст
    extraction_method TEXT,                     -- pdfplumber | ocr | manual
    page_count      INTEGER,
    loaded_at       TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS analytes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT UNIQUE NOT NULL,       -- ggt, ldl, tsh, ...
    name_ru         TEXT NOT NULL,
    canonical_unit  TEXT,
    category        TEXT                        -- biochemistry / hormones / hematology / ...
);

CREATE TABLE IF NOT EXISTS analyte_aliases (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    analyte_id  INTEGER NOT NULL REFERENCES analytes(id),
    alias       TEXT NOT NULL,
    UNIQUE(alias)
);

CREATE TABLE IF NOT EXISTS measurements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    analyte_id  INTEGER NOT NULL REFERENCES analytes(id),
    value_num   REAL,
    unit        TEXT,
    ref_low     REAL,
    ref_high    REAL,
    flag        TEXT,                   -- H / L / HH / LL / пусто
    measured_at TEXT,                   -- ISO 8601
    UNIQUE(document_id, analyte_id)
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id  TEXT NOT NULL,
    event_date  TEXT,
    event_type  TEXT,                   -- diagnosis / procedure / hospitalization / ...
    description TEXT,
    icd10_code  TEXT,
    document_id INTEGER REFERENCES documents(id)
);

CREATE TABLE IF NOT EXISTS medications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id  TEXT NOT NULL,
    name        TEXT NOT NULL,
    dose        TEXT,
    frequency   TEXT,
    started_at  TEXT,
    stopped_at  TEXT,
    reason      TEXT
);

CREATE TABLE IF NOT EXISTS open_questions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id  TEXT NOT NULL,
    priority    TEXT CHECK(priority IN ('P1','P2','P3')) DEFAULT 'P2',
    question    TEXT NOT NULL,
    status      TEXT CHECK(status IN ('open','resolved','cancelled')) DEFAULT 'open',
    created_at  TEXT DEFAULT (datetime('now')),
    resolved_at TEXT,
    document_id INTEGER REFERENCES documents(id)
);

CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id  TEXT NOT NULL,
    note_date   TEXT DEFAULT (datetime('now')),
    content     TEXT NOT NULL,
    tags        TEXT                    -- JSON-массив тегов
);

CREATE INDEX IF NOT EXISTS idx_measurements_analyte ON measurements(analyte_id);
CREATE INDEX IF NOT EXISTS idx_measurements_date    ON measurements(measured_at);
CREATE INDEX IF NOT EXISTS idx_events_patient       ON events(patient_id, event_date);
CREATE INDEX IF NOT EXISTS idx_oq_patient           ON open_questions(patient_id, status);
"""


def init_db(patient: str | None = None) -> None:
    """Создаёт схему БД для пациента."""
    conn = get_conn(patient)
    # Выполняем каждый CREATE TABLE/INDEX отдельно (executescript
    # несовместим с некоторыми монтированными файловыми системами)
    statements = [s.strip() for s in SCHEMA.split(";") if s.strip()]
    with conn:
        for stmt in statements:
            conn.execute(stmt)
    conn.close()
    print(f"✓ БД инициализирована: {get_db_path(patient)}")


# ---------------------------------------------------------------------------
# Briefing — стартовый брифинг из БД
# ---------------------------------------------------------------------------

def briefing(patient: str | None = None) -> None:
    """
    Генерирует стартовый брифинг из БД.
    Агент всегда стартует от актуального состояния, а не из памяти.
    """
    patient = patient or get_patient()
    conn = get_conn(patient)

    # --- Счётчики ---
    counts = {}
    for table in ("documents", "measurements", "events", "medications",
                  "open_questions", "notes"):
        (counts[table],) = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()

    print(f"\n{'='*60}")
    print(f"  Пациент: {patient}")
    print(f"  Дата:    {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")
    print(f"\n📊 Данные в архиве:")
    print(f"   документов:    {counts['documents']}")
    print(f"   измерений:     {counts['measurements']}")
    print(f"   событий:       {counts['events']}")
    print(f"   лекарств:      {counts['medications']}")
    print(f"   открытых вопросов: {counts['open_questions']}")
    print(f"   заметок:       {counts['notes']}")

    # --- Диапазон дат документов ---
    row = conn.execute(
        "SELECT MIN(doc_date), MAX(doc_date) FROM documents WHERE doc_date IS NOT NULL"
    ).fetchone()
    if row[0]:
        print(f"\n📅 Архив: {row[0]} → {row[1]}")

    # --- Открытые вопросы P1 ---
    p1 = conn.execute(
        "SELECT question FROM open_questions WHERE patient_id=? AND priority='P1' AND status='open' LIMIT 5",
        (patient,)
    ).fetchall()
    if p1:
        print(f"\n🔴 Открытые вопросы P1:")
        for q in p1:
            print(f"   • {q['question']}")

    # --- Последние заметки ---
    recent_notes = conn.execute(
        "SELECT note_date, content FROM notes WHERE patient_id=? ORDER BY note_date DESC LIMIT 3",
        (patient,)
    ).fetchall()
    if recent_notes:
        print(f"\n📝 Последние заметки:")
        for n in recent_notes:
            snippet = n["content"][:80].replace("\n", " ")
            print(f"   [{n['note_date'][:10]}] {snippet}…")

    # --- Топ изменившихся показателей за последние 90 дней ---
    cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    trending = conn.execute("""
        SELECT a.name_ru, m.value_num, m.unit, m.flag, m.measured_at
        FROM measurements m
        JOIN analytes a ON a.id = m.analyte_id
        WHERE m.measured_at >= ?
        ORDER BY m.measured_at DESC
        LIMIT 10
    """, (cutoff,)).fetchall()
    if trending:
        print(f"\n📈 Свежие измерения (последние 90 дней):")
        for t in trending:
            flag = f" [{t['flag']}]" if t["flag"] else ""
            print(f"   {t['name_ru']}: {t['value_num']} {t['unit'] or ''}{flag} ({t['measured_at'][:10]})")

    print(f"\n{'='*60}\n")
    conn.close()


# ---------------------------------------------------------------------------
# Вспомогательные функции для других модулей
# ---------------------------------------------------------------------------

def get_or_create_analyte(conn: sqlite3.Connection, code: str,
                           name_ru: str, unit: str = None,
                           category: str = None) -> int:
    """Возвращает id аналита, создаёт если нет."""
    row = conn.execute("SELECT id FROM analytes WHERE code=?", (code,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO analytes(code, name_ru, canonical_unit, category) VALUES(?,?,?,?)",
        (code, name_ru, unit, category)
    )
    return cur.lastrowid


def resolve_analyte_by_alias(conn: sqlite3.Connection, alias: str) -> int | None:
    """Ищет аналит по алиасу (без учёта регистра)."""
    row = conn.execute(
        """SELECT a.id FROM analytes a
           JOIN analyte_aliases aa ON aa.analyte_id = a.id
           WHERE LOWER(aa.alias) = LOWER(?)""",
        (alias,)
    ).fetchone()
    if row:
        return row["id"]
    # Пробуем по name_ru напрямую
    row = conn.execute(
        "SELECT id FROM analytes WHERE LOWER(name_ru) = LOWER(?)", (alias,)
    ).fetchone()
    return row["id"] if row else None


def add_measurement(conn: sqlite3.Connection, document_id: int,
                    analyte_id: int, value_num: float, unit: str,
                    ref_low: float = None, ref_high: float = None,
                    flag: str = None, measured_at: str = None) -> int:
    """Добавляет измерение, при конфликте обновляет."""
    cur = conn.execute(
        """INSERT INTO measurements
           (document_id, analyte_id, value_num, unit, ref_low, ref_high, flag, measured_at)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(document_id, analyte_id) DO UPDATE SET
               value_num=excluded.value_num,
               unit=excluded.unit,
               flag=excluded.flag""",
        (document_id, analyte_id, value_num, unit, ref_low, ref_high, flag, measured_at)
    )
    return cur.lastrowid


def text_search(conn: sqlite3.Connection, query: str,
                field: str = "raw_text") -> list[dict]:
    """
    Полнотекстовый grep по raw_text документов.
    Возвращает список совпадений с контекстом.
    """
    rows = conn.execute(
        f"SELECT id, doc_date, doc_type, source_org, {field} FROM documents"
    ).fetchall()
    results = []
    query_lower = query.lower()
    for row in rows:
        text = row[field] or ""
        if query_lower in text.lower():
            # Находим контекст вокруг совпадения
            idx = text.lower().index(query_lower)
            start = max(0, idx - 100)
            end = min(len(text), idx + len(query) + 100)
            results.append({
                "doc_id": row["id"],
                "doc_date": row["doc_date"],
                "doc_type": row["doc_type"],
                "source": row["source_org"],
                "snippet": text[start:end].strip()
            })
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "briefing"
    patient = os.environ.get("MEDIC_PATIENT", "default")

    if cmd == "init":
        init_db(patient)
    elif cmd == "briefing":
        # Автоматически инициализируем если нет БД
        if not get_db_path(patient).exists():
            init_db(patient)
        briefing(patient)
    else:
        print(f"Неизвестная команда: {cmd}")
        print("Доступные команды: init, briefing")
        sys.exit(1)
