# 🏥 Аналитик медицинских справок

**Структурированный список проблем для визита к врачу — вместо пачки PDF.**

> *"Врач за 30 минут приёма не успевает разобраться в стопке документов за 12 лет. Решение — приносить не пачку, а один документ, который он прочитает за две минуты."*

---

## Проблема

У среднего взрослого за 10 лет накапливаются: выписки из нескольких клиник, анализы из разных лабораторий, снимки и УЗИ. Информация есть — но **формат не работает**.

Когда вы приходите на приём:
- Врач видит срез: жалобы сегодня + пара последних анализов, которые вы вспомнили взять
- Тренд «ГГТ растёт уже 8 лет» никто не замечает
- Узел щитовидки вырос на 60% за два года — но это видно только если смотреть все УЗИ подряд
- Назначают «общий чек-ап на 35 анализов», чтобы «посмотреть»

Это не «врач плохой» — это **формат визита не предусматривает анализ архива**.

## Решение

Инструмент читает ваш медицинский архив и составляет **problem list** по методике POMR (Лоренс Уид, 1968) — стандарту, которым врачи пользуются уже 60 лет.

На выходе — один документ на 2–3 страницы:

| Проблема | Данные / тренды | Протокол (гайдлайн + уровень доказательности) | Действие | Специалист |
|----------|----------------|-----------------------------------------------|----------|------------|
| Погранич. АД | 138/88 среднее, тренд ↑ с 2021 | ESC/ESH 2023, Class I Level A | СМАД, консультация | Кардиолог |
| Субклин. гипотиреоз | ТТГ: 5.8→6.2→7.1 мМЕ/л | ETA 2023: наблюдать или лечить | АТ-ТПО, УЗИ ЩЖ | Эндокринолог |

Плюс обязательный раздел **«Что не делаем и почему»** — потому что хороший чек-ап это не «сдать всё подряд», а сделать ровно нужное.

## Как это работает

```
Ваши PDF/JPG
    ↓
pdfplumber + OCR (для сканов)
    ↓
SQLite-архив (локально на вашем диске)
    ↓
Аналитик на Claude API
    ↓
Problem list → Markdown + DOCX (для печати)
```

**Принципы, от которых мы не отступаем:**
- Аналитик данных, не клиницист. Никаких диагнозов.
- Каждая рекомендация со ссылкой на гайдлайн (организация, год, Class/Level).
- Конфликты протоколов — показываем оба варианта.
- Нейтральный регистр: нет «СРОЧНО», «критично». Только P1/P2/P3.
- Данные хранятся локально. Никаких облаков.

---

## Запуск приложения (рекомендуется)

Проект включает полноценный веб-интерфейс с drag & drop загрузкой документов,
графиками трендов и двумя режимами анализа.

```bash
pip install -r requirements.txt
streamlit run app.py
```

Браузер откроется автоматически. В боковой панели выберите режим:

- **☁️ Облачный** — введите API-ключ Anthropic и анализируйте сразу
- **💻 Локальный** — установите [Ollama](https://ollama.com), запустите `ollama pull llama3.1`, затем `ollama serve`

---

## Быстрый старт (командная строка)

### 1. Клонируйте репозиторий

```bash
git clone https://github.com/YOUR_USERNAME/medical-analyst.git
cd "medical-analyst"
```

### 2. Установите зависимости

```bash
pip install -r requirements.txt
```

Для работы с отсканированными документами дополнительно установите [Tesseract OCR](https://github.com/tesseract-ocr/tesseract).

### 3. Настройте API-ключ

```bash
cp .env.example .env
# Откройте .env и вставьте ваш ANTHROPIC_API_KEY
# Получить ключ: https://console.anthropic.com/settings/keys
```

### 4. Инициализируйте базу данных

```bash
python db.py init
```

### 5. Загрузите медицинские документы

```bash
# Один файл
python load.py path/to/analysis.pdf

# Папка целиком
python load.py path/to/my_documents/
```

### 6. Получите брифинг и сгенерируйте план

```bash
# Что сейчас в архиве
python db.py briefing

# Сгенерировать problem list
python analyze.py plan
```

### 7. Отрендерьте в DOCX для печати

```bash
# Использует последний сгенерированный YAML
python render.py data/default/problem_list_*.yaml
```

---

## Несколько профилей (семья)

Проект поддерживает несколько пациентов — у каждого своя изолированная база данных:

```bash
# Переключение на профиль "mom"
set MEDIC_PATIENT=mom        # Windows
export MEDIC_PATIENT=mom     # Linux/Mac

python db.py init
python load.py mom_documents/
python analyze.py plan
```

---

## Структура проекта

```
├── db.py              # SQLite-архив: схема, CRUD, брифинг
├── load.py            # Загрузка PDF/JPG: pdfplumber + OCR
├── analyze.py         # Аналитик через Claude API
├── render.py          # YAML → Markdown → DOCX
├── analytes.yaml      # Каталог показателей с алиасами
├── CLAUDE.md          # «Конституция» агента — правила аналитика
├── .env.example       # Шаблон конфигурации
├── examples/
│   └── sample_problem_list.yaml   # Пример (синтетические данные)
└── data/              # Данные пациентов (в .gitignore!)
    └── default/
        └── medic.db
```

---

## Команды

| Команда | Описание |
|---------|----------|
| `python db.py init` | Создать схему БД |
| `python db.py briefing` | Показать состояние архива |
| `python load.py <файл>` | Загрузить документ |
| `python load.py <папка>` | Загрузить папку |
| `python analyze.py plan` | Сгенерировать problem list |
| `python analyze.py trend --analyte ggt` | Тренд конкретного показателя |
| `python analyze.py search --query "аденома"` | Полнотекстовый поиск |
| `python render.py <файл.yaml>` | Рендер YAML → MD + DOCX |

---

## Важные ограничения

Этот инструмент — **аналитик данных, не врач**. Он:
- Не ставит диагнозы
- Не заменяет консультацию специалиста
- Не подходит для острых состояний и неотложных ситуаций
- Может ошибаться — все рекомендации нужно обсуждать с врачом

Привязка каждого вывода к источнику снижает риск «галлюцинаций», но не обнуляет его. Перепроверяйте по первоисточнику всё, что кажется важным.

---

## Вдохновение

Проект вырос из статьи [«Медицинский архив семьи в SQLite: Claude как аналитик данных»](https://habr.com/ru/articles/1044576/) и методики POMR Лоренса Уида (1968).

---

---

# 🏥 Medical Records Analyst

**A structured problem list for your doctor visit — instead of a stack of PDFs.**

> *"A doctor can't analyze 12 years of documents in a 30-minute appointment. The solution is to bring one document they can read in two minutes."*

---

## The Problem

The average adult accumulates over years: discharge summaries from multiple clinics, lab results from different labs, scans, and ultrasounds. The information exists — but **the format doesn't work**.

When you see a doctor:
- They see a snapshot: today's complaints + a couple recent labs you remembered to bring
- The trend "GGT has been rising for 8 years" goes unnoticed
- A thyroid nodule that grew 60% over two years is only visible if you look at all the ultrasounds in sequence
- You get a "general checkup with 35 tests" just to "take a look"

This isn't about a bad doctor — the **visit format doesn't support archive analysis**.

## The Solution

This tool reads your medical archive and creates a **problem list** following the POMR methodology (Lawrence Weed, 1968) — a standard physicians have used for 60 years.

The output: one 2–3 page document:

| Problem | Data / Trends | Protocol (guideline + evidence level) | Action | Specialist |
|---------|--------------|--------------------------------------|--------|------------|
| Borderline BP | Mean 138/88, trend ↑ since 2021 | ESC/ESH 2023, Class I Level A | ABPM, consult | Cardiologist |
| Subclinical hypothyroidism | TSH: 5.8→6.2→7.1 mIU/L | ETA 2023: observe or treat | TPO-Ab, thyroid US | Endocrinologist |

Plus a mandatory **"What we're NOT doing and why"** section — because a good checkup is not "test everything," it's doing exactly what's indicated.

## How It Works

```
Your PDFs/JPGs
    ↓
pdfplumber + OCR (for scans)
    ↓
SQLite archive (local, on your machine)
    ↓
Analyst powered by Claude API
    ↓
Problem list → Markdown + DOCX (print-ready)
```

**Principles we never compromise on:**
- Data analyst, not clinician. No diagnoses.
- Every recommendation linked to a guideline (organization, year, Class/Level).
- Conflicting guidelines — both versions shown.
- Neutral register: no "URGENT", "critical". Only P1/P2/P3 priorities.
- Data stays local. No cloud storage.

---

## Running the App (recommended)

The project includes a full web interface with drag & drop uploads, trend charts, and two analysis modes.

```bash
pip install -r requirements.txt
streamlit run app.py
```

The browser opens automatically. In the sidebar, choose your mode:

- **☁️ Cloud** — enter your Anthropic API key and start analyzing
- **💻 Local** — install [Ollama](https://ollama.com), run `ollama pull llama3.1`, then `ollama serve`

---

## Quick Start (command line)

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/medical-analyst.git
cd "medical-analyst"
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

For scanned documents, additionally install [Tesseract OCR](https://github.com/tesseract-ocr/tesseract).

### 3. Set up your API key

```bash
cp .env.example .env
# Open .env and add your ANTHROPIC_API_KEY
# Get a key: https://console.anthropic.com/settings/keys
```

### 4. Initialize the database

```bash
python db.py init
```

### 5. Load your medical documents

```bash
# Single file
python load.py path/to/analysis.pdf

# Entire folder
python load.py path/to/my_documents/
```

### 6. Get a briefing and generate a plan

```bash
# What's currently in the archive
python db.py briefing

# Generate problem list
python analyze.py plan
```

### 7. Render to DOCX for printing

```bash
python render.py data/default/problem_list_*.yaml
```

---

## Multiple Profiles (Family)

The project supports multiple patients — each with their own isolated database:

```bash
# Switch to profile "mom"
set MEDIC_PATIENT=mom        # Windows
export MEDIC_PATIENT=mom     # Linux/Mac

python db.py init
python load.py mom_documents/
python analyze.py plan
```

---

## Project Structure

```
├── db.py              # SQLite archive: schema, CRUD, briefing
├── load.py            # PDF/JPG loading: pdfplumber + OCR
├── analyze.py         # Analyst via Claude API
├── render.py          # YAML → Markdown → DOCX
├── analytes.yaml      # Lab test catalog with aliases
├── CLAUDE.md          # Agent "constitution" — analyst rules
├── .env.example       # Configuration template
├── examples/
│   └── sample_problem_list.yaml   # Example (synthetic data)
└── data/              # Patient data (in .gitignore!)
    └── default/
        └── medic.db
```

---

## Important Limitations

This tool is a **data analyst, not a doctor**. It:
- Does not make diagnoses
- Does not replace professional medical consultation
- Is not suitable for acute conditions or emergencies
- Can make mistakes — all recommendations should be discussed with your doctor

Anchoring each statement to a source reduces "hallucination" risk but doesn't eliminate it. Verify anything important against the primary source.

---

## Inspiration

This project grew from the article ["Family Medical Archive in SQLite: Claude as a Data Analyst"](https://habr.com/ru/articles/1044576/) and Lawrence Weed's POMR methodology (1968).

---

## License

MIT
