"""验证 JSON/CSV 导出 + JSON 导入(去重)"""
import json


def _add_book_with_notes(app, title, author, **kw):
    from models import Book, Note, Tag, db
    tag_names = kw.pop("tags", [])
    note_contents = kw.pop("notes", [])
    book = Book(title=title, author=author, status="reading", **kw)
    for name in tag_names:
        tag = Tag.get_or_create(name)
        book.tags.append(tag)
    db.session.add(book)
    db.session.flush()
    for c in note_contents:
        db.session.add(Note(book_id=book.id, content=c))
    db.session.commit()
    return book


# ---------- 导出 ----------

def test_export_json_includes_tags_and_notes(app, client):
    with app.app_context():
        _add_book_with_notes(
            app,
            title="挪威的森林",
            author="村上春树",
            tags=["小说", "日本"],
            notes=["这是一条笔记"],
        )
    resp = client.get("/export.json")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert len(payload) == 1
    item = payload[0]
    assert item["title"] == "挪威的森林"
    assert set(item["tags"]) == {"小说", "日本"}
    assert item["notes"][0]["content"] == "这是一条笔记"
    # 应有 Content-Disposition 触发下载
    assert "attachment" in resp.headers.get("Content-Disposition", "")


def test_export_csv_has_bom_for_excel(app, client):
    """CSV 应以 UTF-8 BOM 开头,Excel 双击不乱码"""
    with app.app_context():
        _add_book_with_notes(app, title="x", author="y")
    resp = client.get("/export.csv")
    assert resp.status_code == 200
    body = resp.get_data()
    assert body.startswith(b"\xef\xbb\xbf"), "CSV 缺少 UTF-8 BOM"


def test_export_excludes_soft_deleted(app, client):
    """软删除的书不应出现在导出里"""
    from datetime import datetime
    from models import db
    with app.app_context():
        b = _add_book_with_notes(app, title="will-delete", author="x")
        b.deleted_at = datetime.utcnow()
        db.session.commit()
    resp = client.get("/export.json")
    payload = resp.get_json()
    assert payload == []


# ---------- 导入 ----------

def test_import_json_creates_books(app, client):
    data = [
        {"title": "A", "author": "Author A", "tags": ["t1"], "status": "unread"},
        {"title": "B", "author": "Author B", "tags": ["t1", "t2"]},
    ]
    resp = client.post("/import.json", json=data)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["imported"] == 2

    with app.app_context():
        from models import Book
        assert Book.query.count() == 2
        a = Book.query.filter_by(title="A").first()
        assert {t.name for t in a.tags} == {"t1"}


def test_import_json_dedups_by_title_author(app, client):
    """已存在 (title, author) 应跳过,不创建副本"""
    with app.app_context():
        _add_book_with_notes(app, title="挪威的森林", author="村上春树")

    data = [
        {"title": "挪威的森林", "author": "村上春树"},  # 重复
        {"title": "海边的卡夫卡", "author": "村上春树"},  # 新
    ]
    resp = client.post("/import.json", json=data)
    body = resp.get_json()
    assert body["imported"] == 1

    with app.app_context():
        from models import Book
        assert Book.query.count() == 2


def test_import_json_skips_invalid_rows(app, client):
    """缺 title 或 author 应跳过,不应整体失败"""
    data = [
        {"title": "ok", "author": "ok"},
        {"title": "", "author": "x"},
        {"title": "y", "author": ""},
        {"author": "no title"},
    ]
    resp = client.post("/import.json", json=data)
    body = resp.get_json()
    assert body["imported"] == 1


def test_import_json_rejects_non_array(app, client):
    resp = client.post("/import.json", json={"not": "an array"})
    assert resp.status_code == 400
