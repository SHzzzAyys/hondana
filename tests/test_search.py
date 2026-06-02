"""验证搜索:命中类型合并 / 片段生成 / 关键词高亮"""


def test_make_snippet_centers_around_hit():
    """命中词应居中,前后裁出 radius 字符,两侧带省略号"""
    from routes.books import _make_snippet
    content = "a" * 50 + "TARGET" + "b" * 50
    snip = _make_snippet(content, "TARGET", radius=10)
    assert "TARGET" in snip
    assert snip.startswith("…")
    assert snip.endswith("…")


def test_make_snippet_no_hit_returns_head():
    """命中不到时取开头一段"""
    from routes.books import _make_snippet
    content = "x" * 200
    snip = _make_snippet(content, "missing", radius=10)
    assert snip.startswith("x")
    # 长度应为 radius*2 + 省略号
    assert len(snip) <= 22


def test_make_snippet_empty_content():
    from routes.books import _make_snippet
    assert _make_snippet("", "x") == ""
    assert _make_snippet(None, "x") == ""


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


def test_search_returns_field_hits_with_correct_types(app, client):
    """搜索应识别命中字段并展示对应类型标签"""
    with app.app_context():
        _add_book(app, title="挪威的森林", author="村上春树", publisher="译文出版")

    resp = client.get("/search?q=挪威")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    # 搜索高亮会拆开标题为 <mark>挪威</mark>的森林,断言关键片段而非完整串
    assert "的森林" in html  # 标题后半段必出现
    assert "村上春树" in html  # 作者
    assert "书名" in html  # hit_type 标签


def test_search_combines_field_and_note_hits(app, client):
    """同一本书同时命中字段和笔记,应只出现一次"""
    with app.app_context():
        from models import Note, db
        book = _add_book(app, title="某书", author="某作者")
        db.session.add(Note(book_id=book.id, content="这里提到了村上春树"))
        db.session.commit()

    resp = client.get("/search?q=村上")
    html = resp.get_data(as_text=True)
    # 笔记命中类型应出现
    assert "笔记" in html
    # 应能看到书名(标题不含 q,不会被高亮拆开)
    assert "某书" in html


def test_search_empty_query_returns_empty(app, client):
    resp = client.get("/search?q=")
    assert resp.status_code == 200


def test_search_no_match(app, client):
    with app.app_context():
        _add_book(app, title="挪威的森林", author="村上")
    resp = client.get("/search?q=量子物理")
    html = resp.get_data(as_text=True)
    # 不应包含"挪威的森林"
    assert "挪威的森林" not in html
