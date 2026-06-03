"""验证 FTS5 搜索:每种命中类型、软删除、跨字段多关键词"""
from datetime import datetime


def _add_book(app, **kw):
    from models import Book, db
    book = Book(
        title=kw.pop("title", "t"),
        author=kw.pop("author", "a"),
        status=kw.pop("status", "reading"),
        **kw,
    )
    db.session.add(book)
    db.session.commit()
    return book


def _add_note(book, content):
    from models import Note, db
    n = Note(book_id=book.id, content=content)
    db.session.add(n)
    db.session.commit()
    return n


def _add_annotation(book, quote, note=None):
    from models import Annotation, db
    a = Annotation(book_id=book.id, cfi_range="epubcfi(/6/4!/0)", quote=quote, note=note)
    db.session.add(a)
    db.session.commit()
    return a


# ---------- 基础命中 ----------

def test_title_hit(app, client):
    with app.app_context():
        _add_book(app, title="挪威的森林", author="村上春树")
    html = client.get("/search?q=挪威").get_data(as_text=True)
    assert "的森林" in html
    assert "书名" in html


def test_author_hit(app, client):
    with app.app_context():
        _add_book(app, title="某本书", author="村上春树")
    html = client.get("/search?q=村上").get_data(as_text=True)
    assert "某本书" in html
    assert "作者" in html


def test_publisher_hit(app, client):
    with app.app_context():
        _add_book(app, title="x", author="y", publisher="新潮文库")
    html = client.get("/search?q=新潮").get_data(as_text=True)
    assert "新潮" in html
    assert "出版社" in html


def test_note_hit_surfaces_parent_book(app, client):
    with app.app_context():
        book = _add_book(app, title="独立书名", author="某作者")
        _add_note(book, "里面提到了量子物理学")
    html = client.get("/search?q=量子").get_data(as_text=True)
    assert "独立书名" in html
    assert "笔记" in html


def test_annotation_quote_hit(app, client):
    with app.app_context():
        book = _add_book(app, title="无关书", author="无关作者")
        _add_annotation(book, quote="所谓的勇气", note="hello")
    html = client.get("/search?q=勇气").get_data(as_text=True)
    assert "无关书" in html
    assert "批注" in html


# ---------- 边界 ----------

def test_no_match_returns_empty(app, client):
    with app.app_context():
        _add_book(app, title="挪威的森林", author="村上")
    html = client.get("/search?q=完全不存在的关键词").get_data(as_text=True)
    assert "挪威的森林" not in html


def test_soft_deleted_book_excluded(app, client):
    with app.app_context():
        from models import db
        book = _add_book(app, title="将被软删除的书", author="作者X")
        book.deleted_at = datetime.utcnow()
        db.session.commit()
    html = client.get("/search?q=将被软删除").get_data(as_text=True)
    assert "将被软删除的书" not in html


def test_undelete_restores_to_index(app, client):
    with app.app_context():
        from models import db
        book = _add_book(app, title="可恢复的书", author="作者Y")
        book.deleted_at = datetime.utcnow()
        db.session.commit()
        book.deleted_at = None
        db.session.commit()
    html = client.get("/search?q=可恢复").get_data(as_text=True)
    # 查询命中片段会被 <mark> 拆开,断言书名尾部与命中计数
    assert "的书" in html
    assert "1 本书匹配" in html or "1</span> 本书匹配" in html


# ---------- 多关键词 / 跨列 ----------

def test_multi_keyword_across_columns(app, client):
    with app.app_context():
        _add_book(app, title="挪威的森林", author="村上春树")
        _add_book(app, title="无关", author="夏目漱石")
    html = client.get("/search?q=村上 森林").get_data(as_text=True)
    assert "挪威的森林" in html
    assert "夏目漱石" not in html


def test_isbn_hit_via_fallback(app, client):
    with app.app_context():
        _add_book(app, title="x", author="y", isbn="9784101001012")
    html = client.get("/search?q=9784101001012").get_data(as_text=True)
    assert "ISBN" in html


# ---------- 更新后索引保持一致 ----------

def test_updated_title_reindexed(app, client):
    with app.app_context():
        from models import db
        book = _add_book(app, title="旧标题", author="a")
        book.title = "新标题"
        db.session.commit()
    html = client.get("/search?q=新标题").get_data(as_text=True)
    assert "新标题" in html
    html_old = client.get("/search?q=旧标题").get_data(as_text=True)
    # 旧 token 已从索引清除
    assert "新标题" not in html_old or "旧标题" not in html_old


def test_deleted_note_drops_from_index(app, client):
    with app.app_context():
        from models import db
        book = _add_book(app, title="某书xyz", author="a")
        note = _add_note(book, "包含独特关键词喵喵喵")
        db.session.delete(note)
        db.session.commit()
    html = client.get("/search?q=喵喵喵").get_data(as_text=True)
    assert "某书xyz" not in html
