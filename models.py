"""数据模型 - Book / Note / Tag / Shelf"""
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


# 状态常量
STATUS_UNREAD = "unread"
STATUS_READING = "reading"
STATUS_FINISHED = "finished"

STATUS_CHOICES = [
    (STATUS_UNREAD, "未读"),
    (STATUS_READING, "在读"),
    (STATUS_FINISHED, "已读"),
]

STATUS_LABELS = dict(STATUS_CHOICES)


# 多对多关联表：书籍 - 标签
book_tags = db.Table(
    "book_tags",
    db.Column("book_id", db.Integer, db.ForeignKey("books.id", ondelete="CASCADE"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

# 多对多关联表：书单 - 书籍
shelf_books = db.Table(
    "shelf_books",
    db.Column("shelf_id", db.Integer, db.ForeignKey("shelves.id", ondelete="CASCADE"), primary_key=True),
    db.Column("book_id", db.Integer, db.ForeignKey("books.id", ondelete="CASCADE"), primary_key=True),
)


class Book(db.Model):
    """书籍模型"""

    __tablename__ = "books"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False, index=True)
    author = db.Column(db.String(120), nullable=False, index=True)
    isbn = db.Column(db.String(32))
    publisher = db.Column(db.String(120))
    publish_date = db.Column(db.Date)
    cover_url = db.Column(db.String(500))

    status = db.Column(db.String(20), default=STATUS_UNREAD, nullable=False)
    rating = db.Column(db.Integer)  # 1-5, 可为空

    # EPUB 原始文件名（用户上传时的名字，用于显示和下载）
    # 磁盘上的实际文件统一存为 instance/epubs/{book_id}.epub
    epub_filename = db.Column(db.String(260))

    # 阅读进度记忆
    last_read_cfi = db.Column(db.String(500))
    last_read_at = db.Column(db.DateTime)

    # 阅读进度百分比 (0.0 ~ 1.0)
    reading_progress = db.Column(db.Float)

    # 累计阅读秒数
    total_reading_seconds = db.Column(db.Integer, default=0)

    # 时间里程碑奖励的计时基线(秒)。首次心跳时置为当时的累计时长,
    # 之后只对"基线之后新增"的阅读时长发🌸,避免历史时长(含挂机虚高)被一次性补发。
    reward_time_base = db.Column(db.Integer)

    # 软删除
    deleted_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # 关系
    notes = db.relationship(
        "Note",
        backref="book",
        cascade="all, delete-orphan",
        order_by="desc(Note.created_at)",
    )
    annotations = db.relationship(
        "Annotation",
        backref="book",
        cascade="all, delete-orphan",
        order_by="Annotation.created_at",
    )
    bookmarks = db.relationship(
        "Bookmark",
        backref="book",
        cascade="all, delete-orphan",
        order_by="desc(Bookmark.created_at)",
    )
    tags = db.relationship(
        "Tag",
        secondary=book_tags,
        back_populates="books",
    )
    shelves = db.relationship(
        "Shelf",
        secondary=shelf_books,
        back_populates="books",
    )
    rewards = db.relationship(
        "ReadingReward",
        backref="book",
        cascade="all, delete-orphan",
        order_by="ReadingReward.milestone",
    )

    def __repr__(self):
        return f"<Book {self.id}: {self.title} / {self.author}>"

    @property
    def status_label(self):
        return STATUS_LABELS.get(self.status, self.status)


class Note(db.Model):
    """读书笔记"""

    __tablename__ = "notes"

    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(
        db.Integer, db.ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content = db.Column(db.Text, nullable=False)
    deleted_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Note {self.id} for Book {self.book_id}>"


class Tag(db.Model):
    """标签"""

    __tablename__ = "tags"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False, index=True)

    books = db.relationship(
        "Book",
        secondary=book_tags,
        back_populates="tags",
    )

    def __repr__(self):
        return f"<Tag {self.name}>"

    @classmethod
    def get_or_create(cls, name):
        """获取或创建标签（去除首尾空格）"""
        name = (name or "").strip()
        if not name:
            return None
        tag = cls.query.filter_by(name=name).first()
        if tag is None:
            tag = cls(name=name)
            db.session.add(tag)
        return tag



class Annotation(db.Model):
    """EPUB 阅读批注 - 选中文字 + 感想

    - cfi_range: epub.js 的 EpubCFI 区间字符串,用于在阅读器中定位和渲染高亮
    - quote: 选中的原文文字(冗余保存,方便导出时不依赖 EPUB)
    - note: 用户写下的感想(可为空,只高亮不写感想也可以)
    - color: 高亮颜色标记,MVP 只用 sakura
    """

    __tablename__ = "annotations"

    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(
        db.Integer,
        db.ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cfi_range = db.Column(db.String(500), nullable=False)
    quote = db.Column(db.Text, nullable=False)
    note = db.Column(db.Text)
    color = db.Column(db.String(20), default="sakura", nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    def to_dict(self):
        return {
            "id": self.id,
            "book_id": self.book_id,
            "cfi_range": self.cfi_range,
            "quote": self.quote,
            "note": self.note or "",
            "color": self.color,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<Annotation {self.id} for Book {self.book_id}>"


class Bookmark(db.Model):
    """书签 - 标记阅读位置,可随时跳回"""

    __tablename__ = "bookmarks"

    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(
        db.Integer,
        db.ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cfi = db.Column(db.String(500), nullable=False)
    label = db.Column(db.String(200))   # 用户可自定义的标签
    preview = db.Column(db.Text)        # 页面文字预览片段,便于识别
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "book_id": self.book_id,
            "cfi": self.cfi,
            "label": self.label or "",
            "preview": self.preview or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<Bookmark {self.id} for Book {self.book_id}>"


class Shelf(db.Model):
    """自定义书单"""

    __tablename__ = "shelves"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    books = db.relationship(
        "Book",
        secondary=shelf_books,
        back_populates="shelves",
        order_by="desc(Book.created_at)",
    )

    def __repr__(self):
        return f"<Shelf {self.id}: {self.name}>"


class ReadingDaily(db.Model):
    """每日阅读聚合 —— 阅读热力图(记录板)的数据源。

    单用户桌面应用,全局每天一行。秒数由阅读器 30 秒心跳累加(见
    routes/books.py::update_reading_time)。日期用**本地日期**而非 UTC,
    避免清晨阅读被算到前一天、破坏"连续天数"。
    """

    __tablename__ = "reading_daily"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, unique=True, index=True)  # 本地日期
    seconds = db.Column(db.Integer, default=0, nullable=False)          # 当天阅读秒数
    pages = db.Column(db.Integer, default=0, nullable=False)            # 当天新增定位块(可选/备用)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    def __repr__(self):
        return f"<ReadingDaily {self.date}: {self.seconds}s>"


class ReadingReward(db.Model):
    """里程碑奖励(🌸) + 可选感想。

    kind="time"(当前):每读满 N 分钟(默认 30,见设置)给一朵樱花,milestone 为
    累计阅读分钟数(30,60,90...),以"每本书累计阅读时长"为准、服务端在心跳里判定。
    kind="page"(旧数据):早期按 epub 定位块每 10 个给一朵,milestone 为页里程碑。
    (book_id, kind, milestone) 唯一,兜底并发与重入。reflection 可为空(跳过)。
    """

    __tablename__ = "reading_rewards"

    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(
        db.Integer,
        db.ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    milestone = db.Column(db.Integer, nullable=False)  # time: 累计分钟; page: 页里程碑
    kind = db.Column(db.String(10), default="time", nullable=False)  # "time" | "page"
    reward_type = db.Column(db.String(20), default="sakura", nullable=False)  # 预留变体
    reflection = db.Column(db.Text)  # 可选感想,可为空
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("book_id", "kind", "milestone", name="uq_reward_book_kind_milestone"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "book_id": self.book_id,
            "milestone": self.milestone,
            "kind": self.kind,
            "reward_type": self.reward_type,
            "reflection": self.reflection or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<ReadingReward {self.id} book={self.book_id} {self.kind}={self.milestone}>"
