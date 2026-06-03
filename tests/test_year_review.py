"""年度回顾页面 /stats/year/<year> 的端到端测试"""
import re
from datetime import datetime, timedelta


def _make_book(app, **kwargs):
    from models import Book, db
    defaults = dict(title="t", author="a", status="reading")
    defaults.update(kwargs)
    book = Book(**defaults)
    db.session.add(book)
    db.session.commit()
    return book


def _make_session(app, book_id, started_at, seconds):
    from models import ReadingSession, db
    s = ReadingSession(book_id=book_id, started_at=started_at, seconds=seconds)
    db.session.add(s)
    db.session.commit()
    return s


def _extract_hero(html, label):
    pattern = rf'{label}</p>\s*<p[^>]*>([^<]+)</p>'
    m = re.search(pattern, html)
    return m.group(1).strip() if m else None


def test_current_year_renders_200(app, client):
    year = datetime.utcnow().year
    resp = client.get(f"/stats/year/{year}")
    assert resp.status_code == 200


def test_empty_year_renders_empty_state(app, client):
    # 没有 session 的年份(用很早的过去年份避免和其它数据冲突)
    resp = client.get("/stats/year/1990")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "1990 还没有阅读记录" in html
    # 必须包含回到 stats 的链接
    assert "/stats" in html


def test_hero_numbers_aggregate_correctly(app, client):
    year = 2024
    with app.app_context():
        book = _make_book(app)
        # day A: 2 sessions 1800s 合计
        day_a = datetime(year, 3, 5, 10, 0, 0)
        _make_session(app, book.id, day_a, 1200)
        _make_session(app, book.id, day_a + timedelta(hours=2), 600)
        # day B: 1 session 600s
        day_b = datetime(year, 6, 10, 14, 0, 0)
        _make_session(app, book.id, day_b, 600)

    resp = client.get(f"/stats/year/{year}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert _extract_hero(html, "本年阅读时长") == "40 分钟"
    assert _extract_hero(html, "有阅读的天数") == "2 天"
    assert _extract_hero(html, "最长单日") == "30 分钟"


def test_finished_list_filtered_by_status_and_year(app, client):
    from models import db
    year = 2024
    with app.app_context():
        in_year_finished = _make_book(
            app,
            title="InYearFinished",
            status="finished",
        )
        in_year_finished.updated_at = datetime(year, 5, 1, 12, 0, 0)

        in_year_reading = _make_book(
            app,
            title="InYearReading",
            status="reading",
        )
        in_year_reading.updated_at = datetime(year, 5, 1, 12, 0, 0)

        other_year_finished = _make_book(
            app,
            title="OtherYearFinished",
            status="finished",
        )
        other_year_finished.updated_at = datetime(year - 1, 5, 1, 12, 0, 0)

        # 给该年添加一条 session 让页面不进入空状态
        sess_book = _make_book(app, title="SessBook")
        _make_session(app, sess_book.id, datetime(year, 1, 5, 9, 0, 0), 60)

        db.session.commit()

    resp = client.get(f"/stats/year/{year}")
    html = resp.get_data(as_text=True)
    assert "InYearFinished" in html
    assert "InYearReading" not in html
    assert "OtherYearFinished" not in html


def test_deleted_book_sessions_excluded(app, client):
    year = 2024
    with app.app_context():
        from models import db
        book = _make_book(app)
        _make_session(app, book.id, datetime(year, 4, 1, 10, 0, 0), 1800)
        book.deleted_at = datetime.utcnow()
        db.session.commit()

    resp = client.get(f"/stats/year/{year}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    # 软删除后该年没有可统计的 session,应进入空状态
    assert f"{year} 还没有阅读记录" in html


def test_stats_index_links_to_current_year(app, client):
    resp = client.get("/stats")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    current_year = datetime.utcnow().year
    assert f"/stats/year/{current_year}" in html
    assert "查看年度回顾" in html
