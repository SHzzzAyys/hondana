"""验证批注分享卡片 PNG 生成"""


def _seed_ann(app, color="sakura", quote="人间失格,生而为人,我很抱歉"):
    from models import Annotation, Book, db
    with app.app_context():
        book = Book(title="测试书", author="测试作者")
        db.session.add(book)
        db.session.flush()
        ann = Annotation(
            book_id=book.id,
            cfi_range="epubcfi(/6/4!/4/2/1:0,/4/2/1:10)",
            quote=quote,
            color=color,
        )
        db.session.add(ann)
        db.session.commit()
        return ann.id


def test_share_card_returns_png(app, client):
    ann_id = _seed_ann(app)
    resp = client.get(f"/annotations/{ann_id}/card.png")
    assert resp.status_code == 200
    assert resp.headers.get("Content-Type", "").startswith("image/png")
    data = resp.get_data()
    # PNG magic number
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    # Cache-Control 设置
    assert "max-age=3600" in resp.headers.get("Cache-Control", "")


def test_share_card_long_quote_truncated(app, client):
    long_quote = "甲" * 800
    ann_id = _seed_ann(app, quote=long_quote)
    resp = client.get(f"/annotations/{ann_id}/card.png")
    # 不该崩溃,正常 200
    assert resp.status_code == 200
    assert resp.get_data()[:4] == b"\x89PNG"


def test_share_card_unknown_color_falls_back(app, client):
    ann_id = _seed_ann(app, color="unknown-color")
    resp = client.get(f"/annotations/{ann_id}/card.png")
    assert resp.status_code == 200
    assert resp.get_data()[:4] == b"\x89PNG"


def test_share_card_404_for_missing(client):
    resp = client.get("/annotations/99999/card.png")
    assert resp.status_code == 404
