"""add FTS5 search

Revision ID: e64d399aa829
Revises: b7b28e4f0caf
Create Date: 2026-06-03 00:00:00.000000

"""
from alembic import op
from sqlalchemy import text

from models import fts_normalize


# revision identifiers, used by Alembic.
revision = 'e64d399aa829'
down_revision = 'b7b28e4f0caf'
branch_labels = None
depends_on = None


# unicode61 + remove_diacritics=2 给出过得去的 CJK 字符级切分(配合应用层 CJK 切字)
_TOKENIZE = "unicode61 remove_diacritics 2"


def upgrade():
    bind = op.get_bind()
    bind.exec_driver_sql(
        f"CREATE VIRTUAL TABLE books_fts USING fts5("
        f"title, author, publisher, "
        f"content='books', content_rowid='id', "
        f"tokenize='{_TOKENIZE}')"
    )
    bind.exec_driver_sql(
        f"CREATE VIRTUAL TABLE notes_fts USING fts5("
        f"content, "
        f"content='notes', content_rowid='id', "
        f"tokenize='{_TOKENIZE}')"
    )
    bind.exec_driver_sql(
        f"CREATE VIRTUAL TABLE annotations_fts USING fts5("
        f"quote, note, "
        f"content='annotations', content_rowid='id', "
        f"tokenize='{_TOKENIZE}')"
    )

    # 回填:跳过软删除的书,所有字段做 CJK 切字
    rows = bind.execute(text(
        "SELECT id, title, author, publisher FROM books WHERE deleted_at IS NULL"
    )).fetchall()
    for rid, title, author, publisher in rows:
        bind.execute(
            text("INSERT INTO books_fts(rowid, title, author, publisher) "
                 "VALUES(:id, :title, :author, :publisher)"),
            {"id": rid, "title": fts_normalize(title),
             "author": fts_normalize(author), "publisher": fts_normalize(publisher)},
        )

    rows = bind.execute(text("SELECT id, content FROM notes")).fetchall()
    for rid, content in rows:
        bind.execute(
            text("INSERT INTO notes_fts(rowid, content) VALUES(:id, :content)"),
            {"id": rid, "content": fts_normalize(content)},
        )

    rows = bind.execute(text("SELECT id, quote, note FROM annotations")).fetchall()
    for rid, quote, note in rows:
        bind.execute(
            text("INSERT INTO annotations_fts(rowid, quote, note) "
                 "VALUES(:id, :quote, :note)"),
            {"id": rid, "quote": fts_normalize(quote),
             "note": fts_normalize(note)},
        )


def downgrade():
    bind = op.get_bind()
    bind.exec_driver_sql("DROP TABLE IF EXISTS annotations_fts")
    bind.exec_driver_sql("DROP TABLE IF EXISTS notes_fts")
    bind.exec_driver_sql("DROP TABLE IF EXISTS books_fts")
