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
- Select text → instant translation (中⇄英 auto-direction)
- Three engines with auto-fallback: Google (free) · DeepSeek · local **Ollama** (offline)
- Bypasses stale system proxies so it just works

</td>
<td>

### 📊 Reading Statistics
- Status breakdown, rating distribution, yearly trends, tags
- Idle-aware reading-time tracking (pauses when you step away)
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
<tr>
<td>

### 🌸 Reading Rewards
- Earn a cherry blossom every 30 min of reading (interval configurable)
- A gentle, **skippable** reflection prompt at each milestone
- Per-book flower collection — read more, collect a branch of blossoms

</td>
<td>

### 📅 Reading Heatmap
- GitHub-style contribution calendar — color depth = minutes read that day
- Current / longest reading streak & total active days
- Recent milestone reflections gallery

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
git clone https://github.com/SHzzzAyys/hondana.git
cd hondana
pip install -r requirements.txt
```

### 2. Initialize database

```bash
# Windows PowerShell
$env:FLASK_APP = "app.py"
flask init-db

# macOS / Linux
export FLASK_APP=app.py
flask init-db
```

Optional — seed with sample data:
```bash
flask seed
```

### 3. Run

```bash
python app.py          # web mode → open http://127.0.0.1:5000
# or
python desktop.py      # desktop mode (native window via pywebview)
```

The desktop app auto-creates / migrates the database on launch — no manual `flask init-db` needed.

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
| Settings | Nav → 「设置」(translation engine + key/Ollama, reading goal, reward interval) |
| Keyboard shortcuts | `←` `→` pages, `T` TOC, `B` bookmarks, `N` annotations, `+` `-` font size, `Esc` exit reader |

---

## Tech Stack

```
Backend       Flask 3 · Flask-SQLAlchemy · SQLite
Reader        epub.js
Charts        Apache ECharts
Styling       Tailwind CSS (CDN)
Icons         Lucide Icons (CDN)
Fonts         Google Fonts (Noto Serif SC / Noto Sans SC)
Translation   Google Translate · DeepSeek Chat API · local Ollama (offline)
```

Zero external services required — translation can run fully offline via local Ollama.

---

## Project Structure

```
hondana/
├── app.py                  # App factory, CLI commands, Jinja filters
├── config.py               # Configuration
├── models.py               # Book, Note, Tag, Annotation, Bookmark, Shelf, ReadingDaily, ReadingReward
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
│   ├── stats.py            # Statistics, charts & reading heatmap
│   ├── translate.py        # Translation API & settings
│   └── rewards.py          # Reading-reward reflections
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
