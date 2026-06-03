"""验证 P1-1: 多格式书籍文件上传/下载/路由调度

EPUB 仍走在线阅读;PDF/TXT/MOBI 上传后只支持下载,在线阅读引导到详情页。
"""
import io


def _upload(client, fmt, content=b"dummy content"):
    """上传 New 书 + 指定格式文件,返回创建的 book id"""
    data = {
        "title": f"multi-{fmt}",
        "author": "tester",
        "status": "unread",
        "epub_file": (io.BytesIO(content), f"my-book.{fmt}"),
    }
    resp = client.post(
        "/books/new",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    # 创建成功是 302
    assert resp.status_code == 302, resp.get_data(as_text=True)[:200]
    from models import Book
    book = Book.query.filter_by(title=f"multi-{fmt}").first()
    assert book is not None
    return book.id


def test_upload_pdf_sets_file_format(app, client):
    with app.app_context():
        book_id = _upload(client, "pdf")
        from models import Book, db
        book = db.session.get(Book, book_id)
        assert book.file_format == "pdf"
        assert book.epub_filename.endswith(".pdf")


def test_upload_txt_sets_file_format(app, client):
    with app.app_context():
        book_id = _upload(client, "txt", b"hello\nworld\n")
        from models import Book, db
        book = db.session.get(Book, book_id)
        assert book.file_format == "txt"


def test_upload_mobi_sets_file_format(app, client):
    with app.app_context():
        book_id = _upload(client, "mobi")
        from models import Book, db
        assert db.session.get(Book, book_id).file_format == "mobi"


def test_upload_unsupported_extension_rejected(app, client):
    data = {
        "title": "bad-ext",
        "author": "tester",
        "status": "unread",
        "epub_file": (io.BytesIO(b"x"), "thing.exe"),
    }
    resp = client.post("/books/new", data=data, content_type="multipart/form-data")
    # 表单回显 200(带 error),非 302
    assert resp.status_code == 200
    assert "仅支持" in resp.get_data(as_text=True)


def test_pdf_book_reader_renders(app, client):
    """P1-5: PDF 已支持在线阅读 - /read 渲染 reader_pdf 模板(200)"""
    with app.app_context():
        book_id = _upload(client, "pdf", b"%PDF-1.4 fake")
    resp = client.get(f"/books/{book_id}/read", follow_redirects=False)
    assert resp.status_code == 200


def test_epub_book_reader_renders(app, client):
    """合法 EPUB 上传后 /read 应渲染 reader 页(200),不重定向"""
    # 构造最小合法 EPUB zip
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>""")
        zf.writestr("OEBPS/content.opf", """<?xml version="1.0"?>
<package version="2.0" xmlns="http://www.idpf.org/2007/opf"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:title>x</dc:title><dc:creator>y</dc:creator></metadata><manifest/></package>""")
    with app.app_context():
        book_id = _upload(client, "epub", buf.getvalue())
    resp = client.get(f"/books/{book_id}/read", follow_redirects=False)
    assert resp.status_code == 200


def test_download_serves_correct_mimetype_per_format(app, client):
    with app.app_context():
        pdf_id = _upload(client, "pdf", b"%PDF-1.4 fake")
        txt_id = _upload(client, "txt", b"plain text")

    r1 = client.get(f"/books/{pdf_id}/epub?download=1")
    assert r1.status_code == 200
    assert r1.mimetype == "application/pdf"

    r2 = client.get(f"/books/{txt_id}/epub?download=1")
    assert r2.status_code == 200
    assert r2.mimetype == "text/plain"


def test_remove_file_clears_all_extensions(app, client):
    """切换格式或移除文件时,旧格式的磁盘文件应一并清掉"""
    with app.app_context():
        book_id = _upload(client, "pdf")
    # 用 edit 提交 remove_epub=1
    edit_data = {
        "title": "multi-pdf",
        "author": "tester",
        "status": "unread",
        "remove_epub": "1",
    }
    resp = client.post(f"/books/{book_id}/edit", data=edit_data,
                       content_type="multipart/form-data", follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        from models import Book, db
        book = db.session.get(Book, book_id)
        assert book.epub_filename is None
        assert book.file_format is None
