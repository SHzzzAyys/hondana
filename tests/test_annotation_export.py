"""验证 Obsidian 格式批注导出"""


def _seed(app):
    from models import Annotation, Book, db
    with app.app_context():
        book = Book(title="人间失格", author="太宰治", status="reading")
        db.session.add(book)
        db.session.flush()
        db.session.add(Annotation(
            book_id=book.id,
            cfi_range="epubcfi(/6/4!/4/2/1:0,/4/2/1:10)",
            quote="生而为人,我很抱歉",
            note="读到此处心头一颤",
            color="sakura",
        ))
        db.session.add(Annotation(
            book_id=book.id,
            cfi_range="epubcfi(/6/4!/4/2/3:0,/4/2/3:10)",
            quote="多行原文行1\n多行原文行2",
            note=None,
            color="matcha",
        ))
        db.session.commit()
        return book.id


def test_obsidian_export_structure(app, client):
    book_id = _seed(app)
    resp = client.get(f"/books/{book_id}/annotations/export.obsidian")
    assert resp.status_code == 200
    assert "text/markdown" in resp.headers.get("Content-Type", "")
    cd = resp.headers.get("Content-Disposition", "")
    assert "attachment" in cd
    assert "obsidian" in cd

    body = resp.get_data(as_text=True)
    # YAML frontmatter
    assert body.startswith("---\n")
    assert "title: 人间失格" in body
    assert "author: 太宰治" in body
    assert "tags: [hondana, 书摘]" in body
    # wiki link 书名
    assert "# [[人间失格]]" in body
    # callout 语法
    assert "> [!quote] 批注 1" in body
    assert "> [!quote] 批注 2" in body
    # 原文每行都加 >
    assert "> 生而为人,我很抱歉" in body
    assert "> 多行原文行1" in body
    assert "> 多行原文行2" in body
    # 第 1 条 note 出现,第 2 条 note 缺失则不强制
    assert "读到此处心头一颤" in body


def test_obsidian_export_empty_book(app, client):
    from models import Book, db
    with app.app_context():
        book = Book(title="空书", author="无名")
        db.session.add(book)
        db.session.commit()
        bid = book.id
    resp = client.get(f"/books/{bid}/annotations/export.obsidian")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "# [[空书]]" in body
    # 没有批注则不应出现 callout
    assert "[!quote]" not in body
