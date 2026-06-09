"""统计图表路由"""
import json
import os
from collections import Counter
from datetime import datetime, timedelta

from flask import Blueprint, current_app, render_template

from models import (
    Book,
    ReadingDaily,
    ReadingReward,
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

    # 阅读时长统计
    # 本周阅读时长
    now = datetime.utcnow()
    week_start = now - timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    week_books = _base_query().filter(
        Book.last_read_at >= week_start,
        Book.total_reading_seconds > 0,
    ).all()
    weekly_reading_seconds = sum(b.total_reading_seconds or 0 for b in week_books)

    # 本月阅读时长
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_books = _base_query().filter(
        Book.last_read_at >= month_start,
        Book.total_reading_seconds > 0,
    ).all()
    monthly_reading_seconds = sum(b.total_reading_seconds or 0 for b in month_books)

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

    # ---- 阅读热力图(记录板)+ 连续天数 + 🌸 ----
    # 数据源:ReadingDaily(每日阅读秒数,由阅读器心跳累加)。
    # 用本地日期口径,和写入端(books.update_reading_time)保持一致。
    today_local = datetime.now().date()
    hm_start = today_local - timedelta(days=370)  # 近 ~53 周
    daily_rows = (
        ReadingDaily.query.filter(ReadingDaily.date >= hm_start)
        .order_by(ReadingDaily.date)
        .all()
    )
    by_date = {r.date: r for r in daily_rows}
    # ECharts calendar-heatmap 数据:[["2026-06-06", 42(分钟)], ...]
    heatmap_data = [
        [d.isoformat(), round((r.seconds or 0) / 60)]
        for d, r in sorted(by_date.items())
        if (r.seconds or 0) > 0
    ]
    heatmap_max = max((v for _, v in heatmap_data), default=0)
    heatmap_range = [hm_start.isoformat(), today_local.isoformat()]

    # 活跃天集合(当天有阅读)
    active_dates = {d for d, r in by_date.items() if (r.seconds or 0) > 0}
    active_days = len(active_dates)

    # 当前连续天数:从今天(或昨天)往回数连续有阅读的天
    current_streak = 0
    cursor = today_local
    if today_local not in active_dates:
        cursor = today_local - timedelta(days=1)  # 今天还没读,从昨天起算不算断
    while cursor in active_dates:
        current_streak += 1
        cursor -= timedelta(days=1)

    # 最长连续天数
    longest_streak = 0
    run = 0
    prev = None
    for d in sorted(active_dates):
        if prev is not None and (d - prev).days == 1:
            run += 1
        else:
            run = 1
        longest_streak = max(longest_streak, run)
        prev = d

    # 🌸 总数 + 最近的感想
    total_flowers = db.session.query(db.func.count(ReadingReward.id)).scalar() or 0
    recent_reward_rows = (
        db.session.query(ReadingReward, Book.title)
        .join(Book, Book.id == ReadingReward.book_id)
        .filter(ReadingReward.reflection.isnot(None), ReadingReward.reflection != "")
        .order_by(ReadingReward.created_at.desc())
        .limit(8)
        .all()
    )
    recent_reflections = [
        {
            "book": title,
            "milestone": rw.milestone,
            "reflection": rw.reflection,
            "created_at": rw.created_at.strftime("%Y-%m-%d") if rw.created_at else "",
        }
        for rw, title in recent_reward_rows
    ]

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
        heatmap_data=heatmap_data,
        heatmap_range=heatmap_range,
        heatmap_max=heatmap_max,
        current_streak=current_streak,
        longest_streak=longest_streak,
        active_days=active_days,
        total_flowers=total_flowers,
        recent_reflections=recent_reflections,
    )
