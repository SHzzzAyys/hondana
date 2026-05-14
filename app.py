"""Flask 应用入口 - 工厂函数模式"""
import os
import shutil
from datetime import datetime

import click
from flask import Flask
from markupsafe import Markup, escape
from sqlalchemy import inspect, text

from config import Config
from models import db


def create_app(config_class=Config, instance_path=None):
    """应用工厂

    instance_path: 显式指定 instance 目录绝对路径(用于打包后把数据放到 %APPDATA%)。
    不传则用 Flask 默认(项目目录下的 instance/)。
    """
    app = Flask(
        __name__,
        instance_relative_config=True,
        instance_path=instance_path,
    )
    app.config.from_object(config_class)

    # 确保 instance 目录存在
    os.makedirs(app.instance_path, exist_ok=True)

    # 确保 EPUB 上传目录存在，并把绝对路径放进 config
    epub_dir = os.path.join(
        app.instance_path, app.config["EPUB_UPLOAD_FOLDER_NAME"]
    )
    os.makedirs(epub_dir, exist_ok=True)
    app.config["EPUB_UPLOAD_FOLDER"] = epub_dir

    # 注册 SQLAlchemy
    db.init_app(app)

    # 注册 Blueprint
    from routes.books import bp as books_bp
    from routes.notes import bp as notes_bp
    from routes.stats import bp as stats_bp
    from routes.annotations import bp as annotations_bp
    from routes.bookmarks import bp as bookmarks_bp
    from routes.translate import bp as translate_bp
    from routes.shelves import bp as shelves_bp

    app.register_blueprint(books_bp)
    app.register_blueprint(notes_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(annotations_bp)
    app.register_blueprint(bookmarks_bp)
    app.register_blueprint(translate_bp)
    app.register_blueprint(shelves_bp)

    # 注册 CLI 命令
    register_commands(app)

    # 注册模板过滤器
    register_filters(app)

    # 启动时自动备份
    _auto_backup(app)

    return app


def _auto_backup(app):
    """启动时自动备份数据库(最多保留 3 个，间隔 24 小时)"""
    db_path = os.path.join(app.instance_path, "books.db")
    if not os.path.exists(db_path):
        return
    backup_dir = os.path.join(app.instance_path, "backups")
    os.makedirs(backup_dir, exist_ok=True)

    # 检查最近备份时间
    existing = sorted(
        [f for f in os.listdir(backup_dir) if f.startswith("books_") and f.endswith(".db")],
        reverse=True,
    )
    if existing:
        # 解析最新备份的时间戳
        try:
            latest_name = existing[0]  # books_YYYYMMDD_HHMMSS.db
            ts_str = latest_name.replace("books_", "").replace(".db", "")
            latest_time = datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
            if (datetime.now() - latest_time).total_seconds() < 86400:
                return  # 距上次备份不到 24 小时
        except (ValueError, IndexError):
            pass

    # 执行备份
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"books_{ts}.db")
    try:
        shutil.copy2(db_path, backup_path)
    except OSError:
        return

    # 清理旧备份(保留最近 3 个)
    backups = sorted(
        [f for f in os.listdir(backup_dir) if f.startswith("books_") and f.endswith(".db")],
        reverse=True,
    )
    for old in backups[3:]:
        try:
            os.remove(os.path.join(backup_dir, old))
        except OSError:
            pass


def register_filters(app):
    """注册 Jinja 过滤器"""

    @app.template_filter("highlight")
    def highlight_filter(text, q):
        """不区分大小写地将 q 在 text 中的出现高亮。返回 Markup。"""
        if not text or not q:
            return Markup(escape(text or ""))
        t = str(text)
        qlow = q.lower()
        tlow = t.lower()
        qlen = len(q)
        out_parts = []
        i = 0
        while i < len(t):
            j = tlow.find(qlow, i)
            if j < 0:
                out_parts.append(escape(t[i:]))
                break
            out_parts.append(escape(t[i:j]))
            out_parts.append(
                Markup('<mark class="bg-sakura/40 text-ink rounded px-0.5">')
            )
            out_parts.append(escape(t[j : j + qlen]))
            out_parts.append(Markup("</mark>"))
            i = j + qlen
        return Markup("").join(out_parts)

    @app.template_filter("reading_time_fmt")
    def reading_time_fmt(seconds):
        """将秒数格式化为可读时间"""
        if not seconds:
            return "0 分钟"
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if hours > 0:
            return f"{hours} 小时 {minutes} 分钟"
        return f"{minutes} 分钟"


def register_commands(app):
    """注册 CLI 命令"""

    @app.cli.command("init-db")
    def init_db():
        """创建数据库表"""
        db.create_all()
        click.echo("[OK] database tables created")

    @app.cli.command("seed")
    def seed_cmd():
        """插入示例数据"""
        from seed import run_seed

        run_seed()

    @app.cli.command("upgrade-db")
    def upgrade_db():
        """为已有数据库补齐新字段 + 建立新表(非破坏性)。"""
        inspector = inspect(db.engine)
        # 1) books 新字段
        if "books" in inspector.get_table_names():
            columns = {c["name"] for c in inspector.get_columns("books")}
            missing = []
            if "epub_filename" not in columns:
                missing.append(("epub_filename", "VARCHAR(260)"))
            if "last_read_cfi" not in columns:
                missing.append(("last_read_cfi", "VARCHAR(500)"))
            if "last_read_at" not in columns:
                missing.append(("last_read_at", "DATETIME"))
            if "reading_progress" not in columns:
                missing.append(("reading_progress", "FLOAT"))
            if "total_reading_seconds" not in columns:
                missing.append(("total_reading_seconds", "INTEGER DEFAULT 0"))
            if "deleted_at" not in columns:
                missing.append(("deleted_at", "DATETIME"))
            if missing:
                with db.engine.begin() as conn:
                    for name, coldef in missing:
                        conn.execute(text(f"ALTER TABLE books ADD COLUMN {name} {coldef}"))
                        click.echo(f"[OK] added books.{name}")
            else:
                click.echo("[SKIP] books columns all present")

        # 2) notes 新字段
        if "notes" in inspector.get_table_names():
            columns = {c["name"] for c in inspector.get_columns("notes")}
            if "deleted_at" not in columns:
                with db.engine.begin() as conn:
                    conn.execute(text("ALTER TABLE notes ADD COLUMN deleted_at DATETIME"))
                    click.echo("[OK] added notes.deleted_at")

        # 3) 新表
        inspector = inspect(db.engine)
        tables = set(inspector.get_table_names())
        created_something = False
        for tbl in ("annotations", "bookmarks", "shelves", "shelf_books"):
            if tbl not in tables:
                created_something = True
        if created_something:
            db.create_all()  # 只建缺失的表
            click.echo("[OK] created missing tables")
        else:
            click.echo("[SKIP] all tables present")

    @app.cli.command("purge-deleted")
    @click.option("--days", default=30, help="清理多少天前软删除的数据")
    def purge_deleted(days):
        """真正删除超过指定天数的软删除数据"""
        from models import Book, Note
        cutoff = datetime.utcnow() - __import__("datetime").timedelta(days=days)
        deleted_books = Book.query.filter(
            Book.deleted_at.isnot(None),
            Book.deleted_at < cutoff,
        ).all()
        count = len(deleted_books)
        for book in deleted_books:
            from routes.books import _delete_epub_file
            _delete_epub_file(book.id)
            db.session.delete(book)
        db.session.commit()
        click.echo(f"[OK] purged {count} deleted books older than {days} days")

    @app.cli.command("backfill-covers")
    def backfill_covers():
        """为已上传 EPUB 但未提取封面的书,从 EPUB 重新提取封面"""
        from models import Book
        from routes.books import _epub_disk_path, _extract_and_save_cover, _find_cover_file

        done = 0
        skipped = 0
        for book in Book.query.filter(Book.epub_filename.isnot(None)).all():
            epub_path = _epub_disk_path(book.id)
            if not os.path.exists(epub_path):
                click.echo(f"[SKIP] book {book.id} ({book.title}): epub 文件丢失")
                skipped += 1
                continue
            if _find_cover_file(book.id):
                click.echo(f"[SKIP] book {book.id} ({book.title}): 已有封面")
                skipped += 1
                continue
            _extract_and_save_cover(book.id, epub_path)
            if _find_cover_file(book.id):
                click.echo(f"[OK]   book {book.id} ({book.title}): 封面已提取")
                done += 1
            else:
                click.echo(f"[WARN] book {book.id} ({book.title}): EPUB 中未找到封面")
                skipped += 1
        click.echo(f"\n完成: {done} 本提取成功,{skipped} 本跳过")


if __name__ == "__main__":
    app = create_app()
    app.run(host="127.0.0.1", port=5000, debug=True)
