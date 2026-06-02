<div align="center">

# 本棚 · hondana

**一个人的图书馆，安静地读书。**

Personal EPUB bookshelf & online reader with Japanese-minimalist design.

[![Flask](https://img.shields.io/badge/Flask-3.x-A8C8B8?style=flat-square&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Python](https://img.shields.io/badge/Python-3.9+-C4D5E0?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![SQLite](https://img.shields.io/badge/SQLite-E8B4A0?style=flat-square&logo=sqlite&logoColor=white)](https://sqlite.org)
[![License](https://img.shields.io/badge/License-MIT-8A8680?style=flat-square)](LICENSE)

</div>

---

## Features

<table>
<tr>
<td width="50%">

### 📖 EPUB Online Reader
- Browser-based EPUB reader powered by epub.js
- Three reading themes — light / dark / sepia
- Keyboard shortcuts for efficient reading
- Auto-save reading progress & position

</td>
<td width="50%">

### ✍️ Annotations & Highlights
- Highlight text in 4 colors (pink / yellow / green / blue)
- Add notes to any highlighted passage
- Export annotations as Markdown / TXT / JSON / CSV

</td>
</tr>
<tr>
<td>

### 🌐 Built-in Translation
- Select text → instant translation
- Google Translate (free, no key needed)
- DeepSeek API (configurable in settings)

</td>
<td>

### 📊 Reading Statistics
- Status breakdown, rating distribution
- Yearly reading trends, popular tags
- Reading time tracking with heartbeat
- Annual reading goal with progress ring

</td>
</tr>
<tr>
<td>

### 📚 Book Management
- Add / edit / delete with soft-delete & undo
- Tags, ratings (1-5 stars), reading status
- Custom shelves & booklists
- Drag-and-drop EPUB upload with auto metadata extraction

</td>
<td>

### 🔍 Full-text Search
- Search across titles, authors, publishers, notes & annotations
- Highlighted results with hit-type badges
- Sort by relevance or time

</td>
</tr>
</table>

**And more** — grid / list / compact view modes, sorting, pagination, data import & export (JSON / CSV), auto database backup, search history, global keyboard shortcuts...

---

## Design

日系柔色设计 — Japanese-inspired soft color palette with generous whitespace.

| Color | Hex | Usage |
|-------|-----|-------|
| 🟩 柔雾绿 Matcha | `#A8C8B8` | Primary accent, buttons, progress |
| 🟧 樱花粉 Sakura | `#E8B4A0` | Ratings, highlights, warnings |
| 🟦 淡蓝 Sky | `#C4D5E0` | Tags, secondary accent |
| ⬜ 和纸 Washi | `#FAF8F3` | Background |
| ⬛ 炭灰 Ink | `#3D3D3D` | Text |

Typography: **Noto Serif SC** (headings) + **Noto Sans SC** (body) — clean CJK rendering.

---

## Quick Start

### 1. Clone & install

```bash
git clone https://github.com/shangzheng666/hondana.git
cd hondana
pip install -r requirements.txt
```

### 2. Set a SECRET_KEY (production)

A real, long, random `SECRET_KEY` is required when running outside of debug mode
— the app will refuse to boot with the default value. Generate one with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

```bash
# macOS / Linux
export FLASK_APP=app.py
export SECRET_KEY="<paste-the-generated-hex-string>"

# Windows PowerShell
$env:FLASK_APP = "app.py"
$env:SECRET_KEY = "<paste-the-generated-hex-string>"
```

(The desktop launcher `python desktop.py` generates a fresh random key
automatically — you only need to set this for `python app.py` / WSGI.)

### 3. Initialize database

```bash
flask init-db    # runs Alembic migrations to head; safe on fresh & existing DBs
```

Optional — seed with sample data:
```bash
flask seed
```

### 4. Optional: configure DeepSeek translation

```bash
export DEEPSEEK_API_KEY="sk-..."   # env var takes priority over settings.json
```

### 5. Run

```bash
python app.py
```

Open **http://127.0.0.1:5000** in your browser.

---

## Usage

| Action | How |
|--------|-----|
| Add a book | Nav → 「添加」, or drag-drop an EPUB anywhere on the shelf |
| Read EPUB | Book detail → 「在线阅读」 |
| Translate | Select text in reader → click 「译」 |
| Switch theme | Reader toolbar → theme toggle (☀️ → 🌙 → 📜) |
| Annotate | Select text in reader → click 「批注」→ pick color → save |
| Quick status/rating | Book detail → dropdown (auto-saves on change) |
| View stats | Nav → 「统计」 |
| Manage shelves | Nav → 「书单」 |
| Settings | Nav → 「设置」(translation engine, reading goal) |
| Keyboard shortcuts | `←` `→` pages, `T` TOC, `B` bookmarks, `N` annotations, `+` `-` font size, `Esc` exit reader |

---

## Tech Stack

```
Backend       Flask 3 · Flask-SQLAlchemy · SQLite · Alembic (Flask-Migrate)
Reader        epub.js  (+ jszip)
Charts        Apache ECharts
Styling       Tailwind CSS  (Play CDN)
Icons         Lucide Icons  (CDN)
Fonts         Google Fonts: Noto Serif SC / Noto Sans SC
Translation   Google Translate API · DeepSeek Chat API  (optional)
Security      Flask-WTF (CSRF)
```

### What runs locally vs. fetched

No external backend services are required — all data lives in your local SQLite
database (`instance/books.db`). However, the front-end currently pulls a few
assets from public CDNs on first page load:

| Asset | Host | Used for |
|-------|------|----------|
| Tailwind CSS | `cdn.tailwindcss.com` | Layout/styling (runtime JIT) |
| Lucide icons | `unpkg.com` | UI icons |
| ECharts | `cdn.jsdelivr.net` | Statistics charts |
| epub.js / jszip | `cdn.jsdelivr.net` | In-browser EPUB reader |
| Noto Serif/Sans SC | `fonts.googleapis.com` | Headings/body font |

These are cached by the browser after first load, so subsequent visits work
offline as long as the cache lives. For air-gapped / fully self-hosted
deployments, vendoring these assets into `static/vendor/` is on the roadmap
(see Phase 2 self-hosting work).

Translation is the only outbound call from the **backend**: Google Translate
(no key) or DeepSeek (configure via `DEEPSEEK_API_KEY` env var or the settings
page). Both are optional — without them, every other feature works fully
offline.

---

## Project Structure

```
hondana/
├── app.py                  # App factory, CLI commands, Jinja filters
├── config.py               # Configuration
├── models.py               # Book, Note, Tag, Annotation, Bookmark, Shelf
├── epub_meta.py            # EPUB metadata extraction
├── seed.py                 # Sample data seeder
├── requirements.txt
│
├── routes/
│   ├── books.py            # CRUD, search, import/export, progress
│   ├── notes.py            # Reading notes
│   ├── annotations.py      # Highlights & annotations
│   ├── bookmarks.py        # Bookmarks
│   ├── shelves.py          # Custom shelves
│   ├── stats.py            # Statistics & charts
│   └── translate.py        # Translation API & settings
│
├── templates/
│   ├── base.html           # Master layout
│   ├── index.html          # Bookshelf home
│   ├── reader.html         # EPUB reader
│   ├── book_form.html      # Add / edit book
│   ├── book_detail.html    # Book detail
│   ├── search.html         # Search results
│   ├── stats.html          # Reading statistics
│   ├── settings.html       # App settings
│   ├── shelf_list.html     # Shelf listing
│   └── shelf_detail.html   # Shelf detail
│
├── static/js/
│   └── charts.js           # ECharts config (soft-color theme)
│
└── instance/               # Auto-generated, git-ignored
    ├── books.db            # SQLite database
    ├── epubs/              # Uploaded EPUB files
    ├── covers/             # Extracted covers
    ├── backups/            # Auto database backups
    └── settings.json       # User preferences
```

---

## Data Backup

| Method | How |
|--------|-----|
| **JSON export** | Nav → 「导出」→ JSON (full backup with notes & tags) |
| **CSV export** | Nav → 「导出」→ CSV (Excel-compatible) |
| **JSON import** | Nav → 「导出」→ 「导入 JSON」 |
| **Auto backup** | Database is auto-backed up on startup (keeps last 3, 24h interval) |
| **Manual** | Copy `instance/books.db` to your preferred location |

---

## License

MIT — free to use, modify, and distribute.
