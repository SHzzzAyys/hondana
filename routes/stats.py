"""统计图表路由"""
import json
import os
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from flask import Blueprint, current_app, render_template

from models import (
    Annotation,
    Book,
    ReadingSession,
    Tag,
    STATUS_FINISHED,
    STATUS_READING,
    STATUS_UNREAD,
    book_tags,
    db,
)

bp = Blueprint("stats", __name__)


def _load_settings():
    path = os.path.join(current_app.instance_path, "settings.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _base_query():
    return Book.query.filter(Book.deleted_at.is_(None))


@bp.route("/stats")
def index():
    """统计首页 - 聚合数据给前端 ECharts"""
    total = _base_query().count()

    # 各状态计数
    status_counts = {
        STATUS_UNREAD: _base_query().filter_by(status=STATUS_UNREAD).count(),
        STATUS_READING: _base_query().filter_by(status=STATUS_READING).count(),
        STATUS_FINISHED: _base_query().filter_by(status=STATUS_FINISHED).count(),
    }

    # 年度已读
    year_counter = Counter()
    finished_books = _base_query().filter_by(status=STATUS_FINISHED).all()
    for b in finished_books:
        ts = b.updated_at or b.created_at
        if ts:
            year_counter[ts.year] += 1
    yearly = sorted(year_counter.items())

    # 标签 Top 10
    tag_rows = (
        db.session.query(Tag.name, db.func.count(book_tags.c.book_id))
        .join(book_tags, Tag.id == book_tags.c.tag_id)
        .join(Book, Book.id == book_tags.c.book_id)
        .filter(Book.deleted_at.is_(None))
        .group_by(Tag.id, Tag.name)
        .order_by(db.func.count(book_tags.c.book_id).desc())
        .limit(10)
        .all()
    )
    top_tags = [{"name": n, "count": c} for n, c in tag_rows]

    # 评分分布
    rating_rows = (
        db.session.query(Book.rating, db.func.count(Book.id))
        .filter(Book.rating.isnot(None), Book.deleted_at.is_(None))
        .group_by(Book.rating)
        .all()
    )
    rating_map = {r: c for r, c in rating_rows}
    rating_dist = [{"rating": r, "count": rating_map.get(r, 0)} for r in range(1, 6)]

    # 阅读时长统计 - 走 reading_sessions 表按时间窗 SUM,
    # 避免之前用 Book.total_reading_seconds(全时段累计)导致旧书在窗口内有 1s 心跳
    # 就把它历史全部时长算进当周的 bug。
    now = datetime.utcnow()
    week_start = now - timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def _sum_seconds_since(since):
        # 排除软删除书的会话,与全站基础查询的语义保持一致
        return (
            db.session.query(
                db.func.coalesce(db.func.sum(ReadingSession.seconds), 0)
            )
            .join(Book, Book.id == ReadingSession.book_id)
            .filter(Book.deleted_at.is_(None))
            .filter(ReadingSession.started_at >= since)
            .scalar()
        ) or 0

    weekly_reading_seconds = _sum_seconds_since(week_start)
    monthly_reading_seconds = _sum_seconds_since(month_start)

    # 总阅读时长
    total_reading = db.session.query(
        db.func.coalesce(db.func.sum(Book.total_reading_seconds), 0)
    ).filter(Book.deleted_at.is_(None)).scalar()

    # 阅读时长排行(Top 10)
    reading_time_books = (
        _base_query()
        .filter(Book.total_reading_seconds > 0)
        .order_by(Book.total_reading_seconds.desc())
        .limit(10)
        .all()
    )
    reading_time_data = {
        "names": [b.title[:12] for b in reading_time_books],
        "hours": [round((b.total_reading_seconds or 0) / 3600, 1) for b in reading_time_books],
    }

    # 阅读目标
    settings = _load_settings()
    reading_goal = settings.get("reading_goal_yearly", 0)
    current_year = now.year
    finished_this_year = year_counter.get(current_year, 0)

    # 数字卡片
    summary_cards = [
        {"label": "总藏书", "value": total, "icon": "library"},
        {"label": "在读", "value": status_counts[STATUS_READING], "icon": "book-open"},
        {"label": "已读", "value": status_counts[STATUS_FINISHED], "icon": "check-circle-2"},
        {"label": "未读", "value": status_counts[STATUS_UNREAD], "icon": "circle"},
    ]

    chart_data = {
        "status": [
            {"name": "未读", "value": status_counts[STATUS_UNREAD]},
            {"name": "在读", "value": status_counts[STATUS_READING]},
            {"name": "已读", "value": status_counts[STATUS_FINISHED]},
        ],
        "yearly": {
            "years": [str(y) for y, _ in yearly],
            "counts": [c for _, c in yearly],
        },
        "tags": {
            "names": [t["name"] for t in top_tags],
            "counts": [t["count"] for t in top_tags],
        },
        "rating": {
            "labels": [f"{r['rating']} 星" for r in rating_dist],
            "counts": [r["count"] for r in rating_dist],
        },
        "reading_time": reading_time_data,
    }

    return render_template(
        "stats.html",
        summary_cards=summary_cards,
        chart_data=chart_data,
        has_data=(total > 0),
        weekly_reading_seconds=weekly_reading_seconds,
        monthly_reading_seconds=monthly_reading_seconds,
        total_reading_seconds=total_reading,
        reading_goal=reading_goal,
        finished_this_year=finished_this_year,
        current_year=current_year,
    )


@bp.route("/stats/year/<int:year>")
def year_review(year):
    """年度回顾 - 基于 ReadingSession 的年内聚合视图"""
    year_start = datetime(year, 1, 1)
    year_end = datetime(year + 1, 1, 1)

    # 该年内所有 session(排除软删除书)
    sessions = (
        db.session.query(ReadingSession.started_at, ReadingSession.seconds)
        .join(Book, Book.id == ReadingSession.book_id)
        .filter(Book.deleted_at.is_(None))
        .filter(ReadingSession.started_at >= year_start)
        .filter(ReadingSession.started_at < year_end)
        .all()
    )

    has_sessions = bool(sessions)

    # 按日聚合
    day_totals = defaultdict(int)
    hour_totals = [0] * 24
    total_seconds = 0
    for started_at, secs in sessions:
        secs = secs or 0
        day_totals[started_at.date()] += secs
        hour_totals[started_at.hour] += secs
        total_seconds += secs

    days_with_reading = len(day_totals)
    longest_day_seconds = max(day_totals.values()) if day_totals else 0

    # 该年已读书籍(与 stats.index 一致:status=finished 且 updated_at 年份匹配)
    finished_books = []
    for b in (
        _base_query().filter_by(status=STATUS_FINISHED).all()
    ):
        ts = b.updated_at or b.created_at
        if ts and ts.year == year:
            finished_books.append(b)
    finished_books.sort(key=lambda b: (b.updated_at or b.created_at), reverse=True)
    finished_count = len(finished_books)

    # 该年热门标签(基于 last_read_at 在该年内的书)
    tag_counter = Counter()
    tag_books = (
        _base_query()
        .filter(Book.last_read_at >= year_start)
        .filter(Book.last_read_at < year_end)
        .all()
    )
    for b in tag_books:
        for t in b.tags:
            tag_counter[t.name] += 1
    top_tags = tag_counter.most_common(10)

    # 该年最长批注 Top 3(按 quote+note 长度)
    annotations = (
        db.session.query(Annotation)
        .join(Book, Book.id == Annotation.book_id)
        .filter(Book.deleted_at.is_(None))
        .filter(Annotation.created_at >= year_start)
        .filter(Annotation.created_at < year_end)
        .all()
    )
    annotations.sort(
        key=lambda a: len(a.quote or "") + len(a.note or ""), reverse=True
    )
    longest_annotations = annotations[:3]

    # 热力图数据:7×N 列(每列 = 一周,行 = 周一到周日)
    # 起点:年首日所在周的周一;终点:年末日所在周的周日
    first_day = date(year, 1, 1)
    last_day = date(year, 12, 31)
    grid_start = first_day - timedelta(days=first_day.weekday())
    grid_end = last_day + timedelta(days=(6 - last_day.weekday()))

    # 颜色阈值(秒):0 / >0 / >=15m / >=45m / >=2h
    def _bucket(secs):
        if secs <= 0:
            return 0
        if secs < 15 * 60:
            return 1
        if secs < 45 * 60:
            return 2
        if secs < 2 * 3600:
            return 3
        return 4

    heatmap_weeks = []
    cursor = grid_start
    while cursor <= grid_end:
        week_cells = []
        for i in range(7):
            d = cursor + timedelta(days=i)
            secs = day_totals.get(d, 0) if year_start.date() <= d <= last_day else None
            cell = {
                "date": d,
                "in_year": (year_start.date() <= d <= last_day),
                "seconds": secs or 0,
                "bucket": _bucket(secs or 0) if secs is not None else -1,
            }
            week_cells.append(cell)
        heatmap_weeks.append(week_cells)
        cursor += timedelta(days=7)

    return render_template(
        "stats_year.html",
        year=year,
        prev_year=year - 1,
        next_year=year + 1,
        has_sessions=has_sessions,
        total_seconds=total_seconds,
        finished_count=finished_count,
        days_with_reading=days_with_reading,
        longest_day_seconds=longest_day_seconds,
        finished_books=finished_books,
        top_tags=top_tags,
        longest_annotations=longest_annotations,
        heatmap_weeks=heatmap_weeks,
        hour_totals=hour_totals,
    )
