"""P1-5: 多格式在线阅读 - PDF/TXT 渲染各自模板,MOBI 仍重定向"""
import io


def _upload(client, fmt, content=b"dummy content"):
    data = {
        "title": f"reader-{fmt}",
        "author": "tester",
        "status": "unread",
        "epub_file": (io.BytesIO(content), f"file.{fmt}"),
    }
    resp = client.post(
        "/books/new",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert resp.status_code == 302, resp.get_data(as_text=True)[:200]
    from models import Book
    book = Book.query.filter_by(title=f"reader-{fmt}").first()
    assert book is not None
    return book.id


def test_pdf_reader_returns_html(app, client):
    with app.app_context():
        book_id = _upload(client, "pdf", b"%PDF-1.4 fake")
    resp = client.get(f"/books/{book_id}/read", follow_redirects=False)
    assert resp.status_code == 200
    assert resp.mimetype == "text/html"


def test_txt_reader_returns_html(app, client):
    with app.app_context():
        book_id = _upload(client, "txt", "你好，世界\nhello".encode("utf-8"))
    resp = client.get(f"/books/{book_id}/read", follow_redirects=False)
    assert resp.status_code == 200
    assert resp.mimetype == "text/html"


def test_mobi_reader_still_redirects(app, client):
    with app.app_context():
        book_id = _upload(client, "mobi")
    resp = client.get(f"/books/{book_id}/read", follow_redirects=False)
    assert resp.status_code == 302
    assert f"/books/{book_id}" in resp.headers["Location"]


def test_pdf_reader_includes_pdfjs_and_canvas(app, client):
    with app.app_context():
        book_id = _upload(client, "pdf", b"%PDF-1.4 fake")
    resp = client.get(f"/books/{book_id}/read")
    html = resp.get_data(as_text=True)
    assert "pdfjs-dist" in html or "pdf.min.js" in html
    assert "<canvas" in html
    assert 'id="pdf-canvas"' in html


def test_txt_reader_includes_container_and_csrf(app, client):
    with app.app_context():
        book_id = _upload(client, "txt", b"some text content")
    resp = client.get(f"/books/{book_id}/read")
    html = resp.get_data(as_text=True)
    assert 'id="txt-page"' in html
    assert 'id="viewer"' in html
    assert 'name="csrf-token"' in html


def test_pdf_reader_no_epubjs(app, client):
    with app.app_context():
        book_id = _upload(client, "pdf", b"%PDF-1.4 fake")
    resp = client.get(f"/books/{book_id}/read")
    html = resp.get_data(as_text=True)
    assert "epub.min.js" not in html
    assert "epubjs" not in html


def test_txt_reader_no_epubjs(app, client):
    with app.app_context():
        book_id = _upload(client, "txt", b"plain text body")
    resp = client.get(f"/books/{book_id}/read")
    html = resp.get_data(as_text=True)
    assert "epub.min.js" not in html
    assert "epubjs" not in html


def test_pdf_reader_wires_reading_time_heartbeat(app, client):
    with app.app_context():
        book_id = _upload(client, "pdf", b"%PDF-1.4 fake")
    resp = client.get(f"/books/{book_id}/read")
    html = resp.get_data(as_text=True)
    assert f"/books/{book_id}/reading-time" in html


def test_txt_reader_wires_reading_time_heartbeat(app, client):
    with app.app_context():
        book_id = _upload(client, "txt", b"hello")
    resp = client.get(f"/books/{book_id}/read")
    html = resp.get_data(as_text=True)
    assert f"/books/{book_id}/reading-time" in html


def test_pdf_reader_shows_title_and_author(app, client):
    with app.app_context():
        book_id = _upload(client, "pdf", b"%PDF-1.4 fake")
    resp = client.get(f"/books/{book_id}/read")
    html = resp.get_data(as_text=True)
    assert "reader-pdf" in html
    assert "tester" in html


def test_txt_reader_shows_title_and_author(app, client):
    with app.app_context():
        book_id = _upload(client, "txt", b"hello")
    resp = client.get(f"/books/{book_id}/read")
    html = resp.get_data(as_text=True)
    assert "reader-txt" in html
    assert "tester" in html
