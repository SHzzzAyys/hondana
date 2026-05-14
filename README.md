# 本棚 · 个人图书管理系统

> 一个日系清新风格的本地 Web 应用，用来管理你的藏书、记录阅读状态与笔记。

![style](https://img.shields.io/badge/style-日系清新-A8C8B8) ![stack](https://img.shields.io/badge/stack-Flask%20%7C%20SQLite%20%7C%20Tailwind-F5F1E8)

## ✨ 功能特性

- 📚 **书籍管理** — 添加 / 编辑 / 删除书籍，记录书名、作者、ISBN、出版社、出版日期与封面
- 🔖 **阅读状态** — 标记未读 / 在读 / 已读，支持 1-5 星评分
- 🏷️ **标签分类** — 自动去重的标签系统，点击标签快速筛选
- ✍️ **读书笔记** — 为每本书添加多条笔记或书评
- 🔍 **关键词检索** — 跨书名、作者、出版社、ISBN、笔记内容全文搜索，支持高亮
- 📊 **阅读统计** — 状态占比、年度已读、热门标签、评分分布 4 张日系柔色图表
- 💾 **数据导出** — JSON 完整备份 或 CSV 表格（兼容 Excel）

## 🎨 设计风格

日系清新 — 和纸米白底 `#FAF8F3`，柔雾绿 `#A8C8B8` / 樱花粉 `#E8B4A0` / 淡蓝 `#C4D5E0` 作为点缀色，明朝体标题 + 圆润正文，宽松留白。

## 📦 技术栈

| 模块 | 技术 |
|------|------|
| 后端 | Flask 3 + Flask-SQLAlchemy |
| 数据库 | SQLite |
| 模板 | Jinja2 |
| 样式 | Tailwind CSS (CDN) |
| 字体 | Noto Serif SC / Noto Sans SC |
| 图标 | Lucide Icons (CDN) |
| 图表 | Apache ECharts (CDN) |

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 初始化数据库

```bash
# Windows PowerShell
$env:FLASK_APP = "app.py"
flask init-db

# macOS / Linux
export FLASK_APP=app.py
flask init-db
```

可选：插入示例数据
```bash
flask seed
```

### 3. 启动服务器

```bash
python app.py
```

打开浏览器访问 <http://127.0.0.1:5000>

## 🧭 使用指南

| 操作 | 入口 |
|------|------|
| 浏览书架 | 顶部导航 → 「书架」 |
| 添加书籍 | 顶部导航 → 「添加」，或空状态下的按钮 |
| 查看/编辑书籍 | 点击任意书籍卡片 |
| 快速切换状态 / 评分 | 详情页快速操作区（下拉 onchange 自动保存） |
| 添加笔记 | 详情页底部 textarea |
| 按状态筛选 | 首页顶部 Tab（全部 / 未读 / 在读 / 已读） |
| 按标签筛选 | 首页标签云，或书籍详情页点击标签 |
| 关键词检索 | 顶部搜索栏，或导航 → 「搜索」 |
| 查看统计 | 导航 → 「统计」 |
| 导出数据 | 导航 → 「导出」 |

## 📁 项目结构

```
book_manager/
├── app.py                 # 应用工厂 + CLI 命令 + Jinja 过滤器
├── config.py              # 配置（数据库路径、secret key）
├── models.py              # Book / Note / Tag 模型
├── seed.py                # 示例数据种子
├── requirements.txt
├── README.md
├── routes/
│   ├── books.py           # 书籍 CRUD / 搜索 / 导出
│   ├── notes.py           # 笔记增删
│   └── stats.py           # 统计聚合
├── static/
│   └── js/charts.js       # ECharts 日系柔色主题
├── templates/
│   ├── base.html
│   ├── index.html         # 书架首页
│   ├── book_form.html     # 添加 / 编辑
│   ├── book_detail.html
│   ├── search.html
│   └── stats.html
└── instance/
    └── books.db           # SQLite 数据（自动生成）
```

## 🗃️ 数据模型

```
Book (id, title, author, isbn, publisher, publish_date, cover_url,
      status ∈ {unread, reading, finished}, rating 1-5,
      created_at, updated_at)
  ├── notes  ── Note (content, created_at)          (1-to-many, cascade)
  └── tags   ── Tag (name)                          (many-to-many via book_tags)
```

## 🔑 数据备份与恢复

- **导出**：顶部导航「导出」→ JSON 或 CSV
- **恢复**：直接备份 `instance/books.db` 文件即可
- **迁移到新环境**：拷贝 `instance/books.db` 到新环境的同名路径

## 📝 开发提示

- 数据库文件在 `instance/books.db`，已被 `.gitignore` 忽略
- Windows 终端若遇编码问题，设置 `PYTHONIOENCODING=utf-8`
- 所有 CDN 资源（Tailwind / 字体 / ECharts / Lucide）需要网络加载

## 📄 许可

个人项目，自由使用与修改。
