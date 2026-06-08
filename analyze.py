"""
analyze.py — генерация problem list через Claude API.

Агент:
  1. Делает свежий аудит БД (не рециклирует память)
  2. Грепает raw_text по ключевым словам
  3. Параллельно запускает исследовательских суб-агентов (при наличии ключа)
  4. Синтезирует problem list в YAML

Использование:
    python analyze.py plan                     # полный план
    python analyze.py trend --analyte ggt      # тренд конкретного показателя
    python analyze.py search --query "аденома" # полнотекстовый поиск
    MEDIC_PATIENT=member_a python analyze.py plan
"""

import json
import os
import sys
import sqlite3
from pathlib import Path
from datetime import datetime

import anthropic
import yaml

import db

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

MODEL = os.environ.get("MEDIC_MODEL", "claude-opus-4-6")

# «Конституция» агента — читается из CLAUDE.md
CLAUDE_MD_PATH = Path(__file__).parent / "CLAUDE.md"

# Промпт-база
SYSTEM_ANALYST = """
Ты — аналитик медицинских данных. Твоя задача: обработать предоставленные данные из
медицинского архива и составить структурированный список проблем (problem list).

ЖЁСТКИЕ ПРАВИЛА — нарушать запрещено:
1. Ты аналитик данных, НЕ врач и НЕ клиницист. Никаких диагнозов.
2. Любая формулировка: «это стоит обсудить с врачом [специальность]».
3. Каждая значимая рекомендация — со ссылкой на гайдлайн (организация, год, Class/Level).
4. Нейтральный регистр. Запрещены: «СРОЧНО», «критично», «единственное что спасает».
5. Приоритеты только P1/P2/P3. P1 — «в текущем цикле», P2 — «ближайшие 6 мес.», P3 — «мониторинг».
6. Конфликты гайдлайнов — показывать оба варианта.
7. Обязательный раздел «Что не делаем и почему».
8. Самопроверка: каждое утверждение опирается на данные из архива или явный гайдлайн.

САМОПРОВЕРКА ПЕРЕД ВЫДАЧЕЙ:
□ Дисклеймер «аналитик, не врач» присутствует
□ Каждая рекомендация привязана к гайдлайну
□ Конфликты гайдлайнов помечены
□ Есть развилки «если→то»
□ Нейтральный регистр, нет эмоционального давления
□ Раздел «Что не делаем» заполнен
"""

RESEARCH_AGENT_PROMPT = """
Ты — медицинский исследовательский агент. Твоя задача: найти актуальные клинические
рекомендации по указанным вопросам.

Для каждой рекомендации указывай:
- Источник (организация, название гайдлайна, год публикации)
- Класс рекомендации и уровень доказательности (Class/Level, если применимо)
- Где источники расходятся — показывай ОБА варианта

Твой ответ будет использован другим агентом-синтезатором. Пиши структурированно,
без обращений к человеку.

ПРОФИЛЬ ПАЦИЕНТА:
{patient_profile}

ВОПРОСЫ ДЛЯ ИССЛЕДОВАНИЯ:
{questions}
"""


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def read_constitution() -> str:
    """Читает CLAUDE.md как часть системного контекста."""
    if CLAUDE_MD_PATH.exists():
        return CLAUDE_MD_PATH.read_text(encoding="utf-8")
    return ""


def build_patient_data_summary(patient: str) -> dict:
    """
    Собирает свежий срез данных из БД для передачи в Claude.
    Ключевой принцип: всегда из БД, не из кэша.
    """
    conn = db.get_conn(patient)

    # Тренды по всем аналитам (последние 20 измерений)
    measurements = conn.execute("""
        SELECT a.name_ru, a.code, a.canonical_unit,
               m.value_num, m.unit, m.ref_low, m.ref_high, m.flag, m.measured_at
        FROM measurements m
        JOIN analytes a ON a.id = m.analyte_id
        ORDER BY m.measured_at DESC
        LIMIT 100
    """).fetchall()

    # Группируем по аналиту для трендов
    analyte_trends = {}
    for m in measurements:
        code = m["code"]
        if code not in analyte_trends:
            analyte_trends[code] = {
                "name": m["name_ru"],
                "unit": m["unit"] or m["canonical_unit"],
                "values": []
            }
        analyte_trends[code]["values"].append({
            "date": m["measured_at"],
            "value": m["value_num"],
            "flag": m["flag"],
            "ref": f"{m['ref_low']}–{m['ref_high']}" if m["ref_low"] else None
        })

    # Открытые вопросы
    open_questions = conn.execute(
        """SELECT priority, question FROM open_questions
           WHERE patient_id=? AND status='open'
           ORDER BY priority, created_at""",
        (patient,)
    ).fetchall()

    # События
    events = conn.execute(
        """SELECT event_date, event_type, description, icd10_code
           FROM events WHERE patient_id=?
           ORDER BY event_date DESC LIMIT 20""",
        (patient,)
    ).fetchall()

    # Лекарства
    meds = conn.execute(
        """SELECT name, dose, frequency, started_at, stopped_at
           FROM medications WHERE patient_id=?
           ORDER BY started_at DESC""",
        (patient,)
    ).fetchall()

    # Заметки (последние 5)
    notes = conn.execute(
        """SELECT note_date, content FROM notes
           WHERE patient_id=?
           ORDER BY note_date DESC LIMIT 5""",
        (patient,)
    ).fetchall()

    conn.close()

    return {
        "patient_id": patient,
        "generated_at": datetime.now().isoformat(),
        "analyte_trends": analyte_trends,
        "open_questions": [dict(q) for q in open_questions],
        "events": [dict(e) for e in events],
        "medications": [dict(m) for m in meds],
        "recent_notes": [dict(n) for n in notes],
    }


def raw_text_grep(patient: str, keywords: list[str]) -> list[dict]:
    """
    Грепает raw_text всех документов по ключевым словам.
    ВАЖНО: структурированные поля ловят не всё — анамнез, комментарии
    лаборатории, мелкие находки могут быть только в сыром тексте.
    """
    conn = db.get_conn(patient)
    all_hits = []
    for keyword in keywords:
        hits = db.text_search(conn, keyword)
        for hit in hits:
            hit["keyword"] = keyword
            all_hits.append(hit)
    conn.close()
    return all_hits


# ---------------------------------------------------------------------------
# Claude API — основной аналитик
# ---------------------------------------------------------------------------

def get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "Переменная ANTHROPIC_API_KEY не задана.\n"
            "Скопируйте .env.example → .env и вставьте ключ."
        )
    return anthropic.Anthropic(api_key=api_key)


def run_research_agent(client: anthropic.Anthropic,
                        patient_profile: str,
                        research_questions: str) -> str:
    """
    Суб-агент для поиска актуальных гайдлайнов.
    В боевом использовании запускается параллельно с другими агентами.
    """
    prompt = RESEARCH_AGENT_PROMPT.format(
        patient_profile=patient_profile,
        questions=research_questions
    )
    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


def generate_problem_list(patient: str, extra_context: str = "") -> str:
    """
    Генерирует problem list через Claude API.
    Возвращает текст в формате YAML-совместимого Markdown.
    """
    print(f"\n🤖 Запускаю аналитика для пациента '{patient}'…")
    print(f"   Модель: {MODEL}")

    # Шаг 1: свежий аудит из БД
    print("\n📊 Читаю данные из БД…")
    data = build_patient_data_summary(patient)

    # Шаг 2: grep raw_text по ключевым словам (анамнез, семья, находки)
    print("🔍 Грепаю сырой текст…")
    important_keywords = [
        "семейный анамнез", "анамнез", "аллергия", "операция",
        "госпитализация", "онкол", "рак", "курени", "алкогол"
    ]
    grep_hits = raw_text_grep(patient, important_keywords)

    # Шаг 3: Формируем контекст для Claude
    constitution = read_constitution()

    data_json = json.dumps(data, ensure_ascii=False, indent=2)
    grep_summary = "\n".join([
        f"[{h['keyword']}] {h['doc_date'] or '?'}: {h['snippet'][:150]}"
        for h in grep_hits[:20]  # не перегружаем контекст
    ])

    user_message = f"""
{constitution}

## ДАННЫЕ ИЗ АРХИВА ПАЦИЕНТА

```json
{data_json}
```

## ВАЖНЫЕ НАХОДКИ В СЫРОМ ТЕКСТЕ (grep)

{grep_summary if grep_summary else "Совпадений по ключевым словам не найдено."}

## ДОПОЛНИТЕЛЬНЫЙ КОНТЕКСТ

{extra_context if extra_context else "Не задан."}

## ЗАДАЧА

Составь problem list для визита к врачу:

1. Широкую таблицу: Проблема | Данные/тренды | Протокол (гайдлайн + Class/Level) | Действие | Специалист
2. Сводку: что сдать (анализы), что сделать (исследования), к кому идти (специалисты)
3. Раздел «Что не делаем и почему» — с обоснованием по каждому пункту
4. Открытые вопросы / развилки «если→то»

Начни с дисклеймера: «Документ подготовлен аналитическим инструментом, не врачом.
Все выводы требуют обсуждения с лечащим специалистом.»

Формат: Markdown. Тон: нейтральный, фактический, без эмоций.
"""

    client = get_client()

    print("⏳ Ожидаю ответ Claude…")
    response = client.messages.create(
        model=MODEL,
        max_tokens=8192,
        system=SYSTEM_ANALYST,
        messages=[{"role": "user", "content": user_message}]
    )

    result = response.content[0].text
    print(f"✓ Получено {len(result)} символов")
    return result


def analyze_trend(patient: str, analyte_code: str) -> None:
    """Анализирует тренд конкретного показателя."""
    conn = db.get_conn(patient)
    rows = conn.execute("""
        SELECT m.measured_at, m.value_num, m.unit, m.flag, m.ref_low, m.ref_high
        FROM measurements m
        JOIN analytes a ON a.id = m.analyte_id
        WHERE a.code = ?
        ORDER BY m.measured_at
    """, (analyte_code,)).fetchall()
    conn.close()

    if not rows:
        print(f"Нет данных для показателя: {analyte_code}")
        return

    print(f"\nТренд: {analyte_code}")
    print("-" * 50)
    for r in rows:
        flag = f" [{r['flag']}]" if r["flag"] else ""
        ref = f"  реф: {r['ref_low']}–{r['ref_high']}" if r["ref_low"] else ""
        print(f"  {r['measured_at'][:10]}  {r['value_num']} {r['unit'] or ''}{flag}{ref}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "plan"
    patient = os.environ.get("MEDIC_PATIENT", "default")

    # Инициализируем БД если нет
    if not db.get_db_path(patient).exists():
        db.init_db(patient)

    if cmd == "plan":
        # Генерируем problem list
        extra = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        result = generate_problem_list(patient, extra)

        # Сохраняем в файл
        output_dir = Path(__file__).parent / "data" / patient
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        out_path = output_dir / f"problem_list_{timestamp}.md"
        out_path.write_text(result, encoding="utf-8")
        print(f"\n✓ Problem list сохранён: {out_path}")
        print("\n" + "="*60)
        print(result[:2000] + ("…" if len(result) > 2000 else ""))

    elif cmd == "trend":
        if len(sys.argv) < 4 or sys.argv[2] != "--analyte":
            print("Использование: python analyze.py trend --analyte <code>")
            sys.exit(1)
        analyze_trend(patient, sys.argv[3])

    elif cmd == "search":
        if len(sys.argv) < 4 or sys.argv[2] != "--query":
            print("Использование: python analyze.py search --query <текст>")
            sys.exit(1)
        hits = raw_text_grep(patient, [sys.argv[3]])
        if not hits:
            print("Совпадений не найдено.")
        else:
            for h in hits:
                print(f"\n[{h['doc_date'] or '?'}] {h['source'] or ''}")
                print(f"  {h['snippet']}")

    else:
        print(f"Неизвестная команда: {cmd}")
        print("Доступные команды: plan, trend, search")
        sys.exit(1)
