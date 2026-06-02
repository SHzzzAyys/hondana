"""验证 P0-3: Alembic 迁移 + bootstrap_db 的三态行为

场景:
1. 全新库  : 无 alembic_version 也无 books → upgrade head 建全部表
2. 老库    : 有 books 无 alembic_version → stamp head 后 upgrade head(no-op)
3. 已迁移库: 有 alembic_version → upgrade head(no-op 或应用增量)
"""
import os

import pytest
from sqlalchemy import inspect


def _make_app(tmp_path, db_filename="t.db"):
    """构造一个非 TESTING 的 app 以便 bootstrap_db 真的跑迁移"""
    os.environ["SECRET_KEY"] = "test-secret-for-bootstrap"
    from app import create_app
    from config import Config

    class C(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / db_filename}"
        SECRET_KEY = "test-secret-for-bootstrap"

    return create_app(config_class=C, instance_path=str(tmp_path))


def test_bootstrap_on_empty_db_creates_all_tables(tmp_path):
    """全新库 → bootstrap 后应能看到全部 9 张应用表 + alembic_version"""
    from app import bootstrap_db
    flask_app = _make_app(tmp_path)
    bootstrap_db(flask_app)
    with flask_app.app_context():
        from models import db
        tables = set(inspect(db.engine).get_table_names())
    expected = {
        "books", "tags", "book_tags", "notes",
        "annotations", "bookmarks",
        "shelves", "shelf_books",
        "reading_sessions",
        "alembic_version",  # Alembic 自己的版本追踪表
    }
    assert expected.issubset(tables), f"missing: {expected - tables}"


def test_bootstrap_on_legacy_db_stamps_head(tmp_path):
    """老库(用 db.create_all 直接建的) → bootstrap 应 stamp head,不抛错"""
    from app import bootstrap_db
    flask_app = _make_app(tmp_path)

    # 模拟"已上线但从未跑过 Alembic"的库
    with flask_app.app_context():
        from models import db
        db.create_all()
        # 此时绝无 alembic_version
        assert "alembic_version" not in inspect(db.engine).get_table_names()

    bootstrap_db(flask_app)

    with flask_app.app_context():
        from models import db
        tables = set(inspect(db.engine).get_table_names())
        # stamp 后应该有 alembic_version,且其中记录的就是 head revision
        assert "alembic_version" in tables
        with db.engine.connect() as conn:
            from sqlalchemy import text
            ver = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert ver is not None and len(ver) > 0


def test_bootstrap_is_idempotent(tmp_path):
    """bootstrap 跑两次不应破坏数据库"""
    from app import bootstrap_db
    flask_app = _make_app(tmp_path)
    bootstrap_db(flask_app)
    # 写一行数据然后再 bootstrap
    with flask_app.app_context():
        from models import Book, db
        db.session.add(Book(title="x", author="y", status="reading"))
        db.session.commit()
    bootstrap_db(flask_app)
    with flask_app.app_context():
        from models import Book
        assert Book.query.count() == 1, "第二次 bootstrap 破坏了数据"


def test_legacy_data_preserved_after_bootstrap(tmp_path):
    """老库里已有数据,bootstrap stamp 后数据应原样保留"""
    from app import bootstrap_db
    flask_app = _make_app(tmp_path)
    with flask_app.app_context():
        from models import Book, db
        db.create_all()
        db.session.add(Book(title="legacy book", author="old author", status="finished"))
        db.session.commit()
    bootstrap_db(flask_app)
    with flask_app.app_context():
        from models import Book
        b = Book.query.first()
        assert b is not None and b.title == "legacy book"
