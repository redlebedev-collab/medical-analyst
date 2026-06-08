"""
load.py — загрузка медицинских документов в SQLite-архив.

Pipeline:
    файл → sha256 (дедупликация) → pdfplumber
                                       ↓ (если нет текста — скан)
                                   OCR (pytesseract)
                                       ↓
                               raw_text в documents
                                       ↓
                           парсер лабораторных данных → measurements

Использование:
    python load.py path/to/file.pdf
    python load.py path/to/folder/     # загрузить всю папку
    MEDIC_PATIENT=member_a python load.py lab_results.pdf
"""

import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import yaml

import db

# Минимум символов для признания PDF «текстовым» (не сканом)
MIN_TEXT_CHARS = 50


# ---------------------------------------------------------------------------
# Извлечение текста
# ---------------------------------------------------------------------------

def extract_text_pdfplumber(path: Path) -> str:
    """Извлекает текстовый слой из PDF через pdfplumber."""
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            pages = []
            for page in pdf.pages:
                text = page.extract_text() or ""
                pages.append(text)
            return "\n\n".join(pages)
    except Exception as e:
        print(f"  ⚠ pdfplumber: {e}")
        return ""


def extract_text_ocr(path: Path) -> str:
    """
    OCR-резерв для сканов. Использует pytesseract.
    Требует установленного Tesseract: https://github.com/tesseract-ocr/tesseract
    """
    try:
        import pytesseract
        from PIL import Image
        from pdf2image import convert_from_path

        pages = convert_from_path(path, dpi=300)
        texts = []
        for i, page in enumerate(pages):
            print(f"    OCR страница {i+1}/{len(pages)}…")
            text = pytesseract.image_to_string(page, lang="rus+eng")
            texts.append(text)
        return "\n\n".join(texts)
    except ImportError:
        print("  ⚠ OCR недоступен. Установите: pip install pytesseract pdf2image pillow")
        print("    и Tesseract: https://github.com/tesseract-ocr/tesseract")
        return ""
    except Exception as e:
        print(f"  ⚠ OCR ошибка: {e}")
        return ""


def extract_text(path: Path) -> tuple[str, str]:
    """
    Извлекает текст из файла. Возвращает (text, method).
    Стратегия: сначала pdfplumber, при неудаче — OCR.
    """
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        text = extract_text_pdfplumber(path)
        if len(text.strip()) >= MIN_TEXT_CHARS:
            return text, "pdfplumber"
        print(f"  → Текстовый слой пуст, пробуем OCR…")
        return extract_text_ocr(path), "ocr"

    elif suffix in (".jpg", ".jpeg", ".png", ".tiff", ".bmp"):
        try:
            import pytesseract
            from PIL import Image
            image = Image.open(path)
            text = pytesseract.image_to_string(image, lang="rus+eng")
            return text, "ocr"
        except ImportError:
            print("  ⚠ pytesseract не установлен")
            return "", "manual"

    elif suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="ignore"), "manual"

    else:
        print(f"  ⚠ Неподдерживаемый формат: {suffix}")
        return "", "unknown"


# ---------------------------------------------------------------------------
# Определение даты документа
# ---------------------------------------------------------------------------

DATE_PATTERNS = [
    # 2024-03-15
    r"\b(\d{4}[-/]\d{2}[-/]\d{2})\b",
    # 15.03.2024
    r"\b(\d{2}[./]\d{2}[./]\d{4})\b",
    # 15 марта 2024
    r"\b(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})\b",
]

MONTHS_RU = {
    "января": "01", "февраля": "02", "марта": "03", "апреля": "04",
    "мая": "05", "июня": "06", "июля": "07", "августа": "08",
    "сентября": "09", "октября": "10", "ноября": "11", "декабря": "12",
}


def detect_date(text: str) -> str | None:
    """Пытается определить дату документа из текста."""
    # ISO / через точку
    for pattern in DATE_PATTERNS[:2]:
        match = re.search(pattern, text)
        if match:
            raw = match.group(1).replace("/", "-").replace(".", "-")
            parts = raw.split("-")
            if len(parts[0]) == 4:   # YYYY-MM-DD
                return raw
            else:                     # DD-MM-YYYY → YYYY-MM-DD
                return f"{parts[2]}-{parts[1]}-{parts[0]}"

    # Русский формат
    match = re.search(DATE_PATTERNS[2], text, re.IGNORECASE)
    if match:
        day, month_ru, year = match.group(1), match.group(2).lower(), match.group(3)
        month = MONTHS_RU.get(month_ru, "01")
        return f"{year}-{month}-{day.zfill(2)}"

    return None


# ---------------------------------------------------------------------------
# Парсер лабораторных показателей
# ---------------------------------------------------------------------------

def load_analytes_catalog() -> dict:
    """
    Загружает каталог аналитов из analytes.yaml.
    Возвращает словарь alias -> {code, name_ru, unit, category}.
    """
    catalog_path = Path(__file__).parent / "analytes.yaml"
    if not catalog_path.exists():
        return {}
    with catalog_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    # Строим инвертированный индекс по алиасам
    alias_map = {}
    for analyte in data.get("analytes", []):
        for alias in [analyte["code"]] + analyte.get("aliases", []):
            alias_map[alias.lower()] = analyte
    return alias_map


# Регулярка для строк лаб. анализов вида:
# "Глюкоза 5.4 ммоль/л 3.9-6.1"
# "ГГТ    47 Ед/л  [H]  10-55"
LAB_LINE_RE = re.compile(
    r"([А-Яа-яA-Za-z][А-Яа-яA-Za-z0-9\s\-/()]+?)"  # название
    r"\s+"
    r"(\d+[\.,]?\d*)"                                  # значение
    r"\s*"
    r"([А-Яа-яA-Za-z/%мкнпМКНП][^\s]*(?:/[^\s]+)?)?" # единицы
    r"\s*"
    r"(?:\[([HL]+)\])?"                                # флаг H/L
    r"\s*"
    r"(?:(\d+[\.,]?\d*)\s*[-–]\s*(\d+[\.,]?\d*))?",   # референс low-high
    re.UNICODE
)


def parse_lab_lines(text: str, alias_map: dict) -> list[dict]:
    """
    Извлекает структурированные измерения из сырого текста.
    Возвращает список словарей с полями analyte_code, value_num, unit, flag, ref_low, ref_high.
    """
    results = []
    for match in LAB_LINE_RE.finditer(text):
        name_raw = match.group(1).strip()
        value_str = match.group(2).replace(",", ".")
        unit = match.group(3) or ""
        flag = match.group(4) or ""
        ref_low_str = match.group(5)
        ref_high_str = match.group(6)

        # Ищем аналит в каталоге
        analyte_info = alias_map.get(name_raw.lower())
        if not analyte_info:
            continue  # не знаем этого аналита — пропускаем

        try:
            value_num = float(value_str)
        except ValueError:
            continue

        results.append({
            "analyte_code": analyte_info["code"],
            "analyte_name": analyte_info["name_ru"],
            "analyte_unit": analyte_info.get("unit", unit),
            "analyte_category": analyte_info.get("category", ""),
            "value_num": value_num,
            "unit": unit or analyte_info.get("unit", ""),
            "flag": flag,
            "ref_low": float(ref_low_str.replace(",", ".")) if ref_low_str else None,
            "ref_high": float(ref_high_str.replace(",", ".")) if ref_high_str else None,
        })

    return results


# ---------------------------------------------------------------------------
# Основная функция загрузки
# ---------------------------------------------------------------------------

def file_sha256(path: Path) -> str:
    """SHA-256 файла для дедупликации."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_file(path: Path, patient: str | None = None,
              doc_type: str = "lab", source_org: str = "") -> bool:
    """
    Загружает один файл в архив пациента.
    Возвращает True при успехе, False если файл уже был загружен.
    """
    patient = patient or db.get_patient()
    print(f"\n📄 {path.name}")

    # Дедупликация по hash
    file_hash = file_sha256(path)
    conn = db.get_conn(patient)

    existing = conn.execute(
        "SELECT id FROM documents WHERE file_hash=?", (file_hash,)
    ).fetchone()
    if existing:
        print(f"  ⏭ Уже в архиве (doc_id={existing['id']})")
        conn.close()
        return False

    # Инициализируем схему если нужно
    if not db.get_db_path(patient).exists():
        db.init_db(patient)

    # Извлекаем текст
    print(f"  → Извлечение текста…")
    raw_text, method = extract_text(path)
    print(f"  ✓ {len(raw_text)} символов [{method}]")

    # Определяем дату документа
    doc_date = detect_date(raw_text[:2000])  # ищем дату в начале документа
    if doc_date:
        print(f"  📅 Дата документа: {doc_date}")
    else:
        print(f"  ⚠ Дата не определена — укажите вручную")

    # Сохраняем документ
    with conn:
        cur = conn.execute(
            """INSERT INTO documents
               (file_hash, doc_date, doc_type, source_org, raw_text,
                extraction_method, page_count)
               VALUES (?,?,?,?,?,?,?)""",
            (file_hash, doc_date, doc_type, source_org, raw_text,
             method, raw_text.count("\f") + 1)
        )
        doc_id = cur.lastrowid

    print(f"  ✓ Документ сохранён (doc_id={doc_id})")

    # Парсим лабораторные показатели
    alias_map = load_analytes_catalog()
    if alias_map:
        measurements = parse_lab_lines(raw_text, alias_map)
        if measurements:
            with conn:
                for m in measurements:
                    analyte_id = db.get_or_create_analyte(
                        conn,
                        code=m["analyte_code"],
                        name_ru=m["analyte_name"],
                        unit=m["analyte_unit"],
                        category=m["analyte_category"],
                    )
                    db.add_measurement(
                        conn,
                        document_id=doc_id,
                        analyte_id=analyte_id,
                        value_num=m["value_num"],
                        unit=m["unit"],
                        ref_low=m["ref_low"],
                        ref_high=m["ref_high"],
                        flag=m["flag"],
                        measured_at=doc_date,
                    )
            print(f"  📊 Извлечено измерений: {len(measurements)}")

    conn.close()
    return True


def load_directory(folder: Path, patient: str | None = None,
                   extensions: tuple = (".pdf", ".jpg", ".jpeg", ".png")) -> None:
    """Рекурсивно загружает все файлы из папки."""
    files = [f for f in folder.rglob("*") if f.suffix.lower() in extensions]
    print(f"Найдено файлов: {len(files)}")
    ok = skipped = 0
    for f in files:
        if load_file(f, patient):
            ok += 1
        else:
            skipped += 1
    print(f"\n✓ Загружено: {ok}, пропущено (дубли): {skipped}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python load.py <file_or_folder>")
        sys.exit(1)

    target = Path(sys.argv[1])
    patient = os.environ.get("MEDIC_PATIENT", "default")

    # Инициализируем БД если нет
    if not db.get_db_path(patient).exists():
        db.init_db(patient)

    if target.is_dir():
        load_directory(target, patient)
    elif target.is_file():
        load_file(target, patient)
    else:
        print(f"Путь не найден: {target}")
        sys.exit(1)
