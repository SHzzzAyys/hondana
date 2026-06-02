"""验证 P0-1 修复:周/月阅读时长走 reading_sessions 表,不会被全时段累计污染"""
import re
from datetime import datetime, timedelta


def _extract_card(html, label):
    """从 stats 页面里抓某个标签卡片的数值文本(本周/本月/总阅读时长 等)"""
    pattern = rf'{label}</p>\s*<p[^>]*>([^<]+)</p>'
    m = re.search(pattern, html)
    return m.group(1).strip() if m else None


def _make_book(app, total_seconds=0, last_read_at=None):
    from models import Book, db
    book = Book(
        title="t",
        author="a",
        status="reading",
        total_reading_seconds=total_seconds,
        last_read_at=last_read_at,
    )
    db.session.add(book)
    db.session.commit()
    return book


def _make_session(app, book_id, started_at, seconds):
    from models import ReadingSession, db
    s = ReadingSession(book_id=book_id, started_at=started_at, seconds=seconds)
    db.session.add(s)
    db.session.commit()
    return s


def test_weekly_reading_only_counts_sessions_in_window(app, client):
    """旧书全时段累计 100h,本周只读 30s。统计应返回 30s,不是 100h+30s。"""
    now = datetime.utcnow()
    with app.app_context():
        book = _make_book(
            app,
            total_seconds=100 * 3600,  # 100h 累计
            last_read_at=now,           # last_read_at 在本周内
        )
        # 一条很久以前的 session(在窗口外)
        _make_session(app, book.id, now - timedelta(days=120), 90 * 3600)
        # 一条本周内的 session(30 秒)
        _make_session(app, book.id, now - timedelta(hours=1), 30)

    resp = client.get("/stats")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    weekly = _extract_card(html, "本周")
    total = _extract_card(html, "总计")
    # 本周只该统计窗口内的 session(30s → "0 分钟"),不该是全时段累计 100h
    assert weekly == "0 分钟", f"本周卡片错误: {weekly!r}(bug: 把累计算进窗口)"
    # 总时长仍走 Book.total_reading_seconds,该显示 100h
    assert total == "100 小时 0 分钟", f"总时长卡片错误: {total!r}"


def test_update_reading_time_writes_session_row(app, client):
    """PATCH /books/<id>/reading-time 既要累加 total,也要写一条 session"""
    from models import Book, ReadingSession, db
    with app.app_context():
        book = Book(title="t", author="a", status="reading")
        db.session.add(book)
        db.session.commit()
        book_id = book.id

    resp = client.patch(
        f"/books/{book_id}/reading-time",
        json={"seconds": 30},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["total"] == 30

    with app.app_context():
        sessions = ReadingSession.query.filter_by(book_id=book_id).all()
        assert len(sessions) == 1
        assert sessions[0].seconds == 30
        # 累计字段也应被更新
        assert db.session.get(Book, book_id).total_reading_seconds == 30


def test_monthly_window_aggregates_sessions(app, client):
    """本月窗口聚合多本书 + 多条 session"""
    now = datetime.utcnow()
    # 用 month_start 作为锚点构造本月内/本月外时间戳,避免月初跑测试时 now-Nd 落到上月
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    with app.app_context():
        b1 = _make_book(app)
        b2 = _make_book(app)
        # b1 本月两条
        _make_session(app, b1.id, month_start + timedelta(hours=1), 60)
        _make_session(app, b1.id, month_start + timedelta(hours=2), 120)
        # b2 本月一条
        _make_session(app, b2.id, month_start + timedelta(hours=3), 90)
        # 上月一条(应被排除)
        _make_session(app, b1.id, month_start - timedelta(days=1), 9999)

    resp = client.get("/stats")
    html = resp.get_data(as_text=True)
    monthly = _extract_card(html, "本月")
    # 60+120+90 = 270s = 4 分钟 (整数除法)
    assert monthly == "4 分钟", f"本月卡片错误: {monthly!r}"


def test_deleted_book_sessions_excluded(app, client):
    """软删除书的 session 不计入统计(与全站 _base_query 语义一致)"""
    now = datetime.utcnow()
    with app.app_context():
        from models import db
        book = _make_book(app)
        _make_session(app, book.id, now - timedelta(hours=1), 600)
        book.deleted_at = now
        db.session.commit()

    resp = client.get("/stats")
    html = resp.get_data(as_text=True)
    # 软删除后 has_data 可能为 False,但本周/本月卡片仍渲染
    weekly = _extract_card(html, "本周")
    monthly = _extract_card(html, "本月")
    # 600s 都不该被算进任何窗口
    assert weekly == "0 分钟", f"软删除书的 session 仍计入本周: {weekly!r}"
    assert monthly == "0 分钟", f"软删除书的 session 仍计入本月: {monthly!r}"
