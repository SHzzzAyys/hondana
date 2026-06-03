"""验证全局批注列表页:渲染、搜索、分页"""


def _seed_many(app, n: int, prefix: str = "原文条目"):
    from models import Annotation, Book, db
    with app.app_context():
        book = Book(title="集子", author="某人")
        db.session.add(book)
        db.session.flush()
        for i in range(n):
            db.session.add(Annotation(
                book_id=book.id,
                cfi_range=f"epubcfi(/6/4!/4/2/{i}:0,/4/2/{i}:5)",
                quote=f"{prefix}{i}",
                note=("感想" + str(i)) if i % 2 == 0 else None,
                color="sakura",
            ))
        db.session.commit()
        return book.id


def test_global_list_renders(app, client):
    _seed_many(app, 3, prefix="春樱")
    resp = client.get("/annotations")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "所有批注" in body
    assert "春樱0" in body
    assert "春樱1" in body
    assert "春樱2" in body


def test_global_list_search_filter(app, client):
    _seed_many(app, 3, prefix="夏蝉")
    # 多创建一条不匹配的
    from models import Annotation, Book, db
    with app.app_context():
        b = Book.query.first()
        db.session.add(Annotation(
            book_id=b.id,
            cfi_range="epubcfi(/x)",
            quote="不相干的句子",
            color="sakura",
        ))
        db.session.commit()

    resp = client.get("/annotations?q=夏蝉")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "夏蝉0" in body
    assert "不相干的句子" not in body


def test_global_list_pagination(app, client):
    _seed_many(app, 30, prefix="秋月")
    # per_page = 24
    resp = client.get("/annotations")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # 应出现下一页链接
    assert "下一页" in body

    resp2 = client.get("/annotations?page=2")
    assert resp2.status_code == 200
    body2 = resp2.get_data(as_text=True)
    # 第 2 页只剩 6 条
    assert "上一页" in body2


def test_global_list_empty_search(app, client):
    _seed_many(app, 2)
    resp = client.get("/annotations?q=绝不可能匹配xyzzy")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "没有匹配" in body


def test_global_list_excludes_deleted_books(app, client):
    from datetime import datetime
    from models import Book, db
    _seed_many(app, 2, prefix="不可见")
    with app.app_context():
        b = Book.query.first()
        b.deleted_at = datetime.utcnow()
        db.session.commit()
    resp = client.get("/annotations")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "不可见0" not in body
