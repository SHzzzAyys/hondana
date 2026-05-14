"""数据库种子 - 插入示例书籍用于开发测试"""
from datetime import date

import click

from models import (
    Book,
    Note,
    Tag,
    STATUS_FINISHED,
    STATUS_READING,
    STATUS_UNREAD,
    db,
)


def run_seed():
    """插入 3 本示例书籍"""
    if Book.query.count() > 0:
        click.echo("[skip] database already has books, skip seeding.")
        return

    # 创建标签
    tag_literature = Tag.get_or_create("文学")
    tag_tech = Tag.get_or_create("技术")
    tag_history = Tag.get_or_create("历史")
    tag_essay = Tag.get_or_create("随笔")

    books = [
        Book(
            title="挪威的森林",
            author="村上春树",
            isbn="9787532735556",
            publisher="上海译文出版社",
            publish_date=date(2007, 7, 1),
            cover_url="",
            status=STATUS_FINISHED,
            rating=5,
            tags=[tag_literature, tag_essay],
        ),
        Book(
            title="流畅的 Python",
            author="Luciano Ramalho",
            isbn="9787115545091",
            publisher="人民邮电出版社",
            publish_date=date(2017, 5, 1),
            cover_url="",
            status=STATUS_READING,
            rating=4,
            tags=[tag_tech],
        ),
        Book(
            title="万历十五年",
            author="黄仁宇",
            isbn="9787108009821",
            publisher="生活·读书·新知三联书店",
            publish_date=date(1997, 5, 1),
            cover_url="",
            status=STATUS_UNREAD,
            rating=None,
            tags=[tag_history],
        ),
    ]

    for b in books:
        db.session.add(b)
    db.session.flush()

    # 为第一本书添加一条笔记
    note = Note(
        book_id=books[0].id,
        content="直子和绿子代表了两种截然不同的生命状态，读完之后久久不能平静。",
    )
    db.session.add(note)

    db.session.commit()
    click.echo(f"[OK] seeded {len(books)} books and 1 note")
