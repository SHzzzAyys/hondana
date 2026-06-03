"""数据模型 - Book / Note / Tag / Shelf"""
import re
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event, inspect as sa_inspect, text

db = SQLAlchemy()

# unicode61 把 CJK 整段当成一个 token,这里手动按字符切开供 FTS 索引
_CJK_RE = re.compile(r'([㐀-䶿一-鿿豈-﫿])')


def fts_normalize(s):
    if not s:
        return ""
    return _CJK_RE.sub(r' \1 ', s)


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
    # 磁盘上的实际文件统一存为 instance/epubs/{book_id}.{ext}
    epub_filename = db.Column(db.String(260))

    # 文件格式 (epub / pdf / txt / mobi / other) - 仅在上传文件后非空
    # epub 仍是一等公民,其他格式当前只支持上传+下载,在线阅读会引导用户下载
    file_format = db.Column(db.String(16))

    # 阅读进度记忆
    last_read_cfi = db.Column(db.String(500))
    last_read_at = db.Column(db.DateTime)

    # 阅读进度百分比 (0.0 ~ 1.0)
    reading_progress = db.Column(db.Float)

    # 累计阅读秒数
    total_reading_seconds = db.Column(db.Integer, default=0)

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


class ReadingSession(db.Model):
    """阅读会话片段 - 按时间窗口聚合阅读时长的数据源

    阅读器每 30 秒发一次心跳,每次心跳写入一行 (started_at=收到时间, seconds=增量)。
    Book.total_reading_seconds 仍维护为全时段累计(便于详情页快速展示),
    周/月/年等时间窗统计走本表的 SUM(seconds) WHERE started_at BETWEEN ...。
    """

    __tablename__ = "reading_sessions"

    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(
        db.Integer,
        db.ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    started_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )
    seconds = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f"<ReadingSession {self.id} book={self.book_id} {self.seconds}s>"


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


# ---------------------------- FTS5 全文搜索同步 ----------------------------
# unicode61 + remove_diacritics=2 给出过得去的 CJK 字符级切分(无需额外分词器)。
# 三张 external-content 虚表:rowid 对齐源表主键,delete 走标准 'delete' 行命令。

FTS_DDL = [
    "CREATE VIRTUAL TABLE IF NOT EXISTS books_fts USING fts5("
    "title, author, publisher, "
    "content='books', content_rowid='id', "
    "tokenize='unicode61 remove_diacritics 2')",
    "CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5("
    "content, "
    "content='notes', content_rowid='id', "
    "tokenize='unicode61 remove_diacritics 2')",
    "CREATE VIRTUAL TABLE IF NOT EXISTS annotations_fts USING fts5("
    "quote, note, "
    "content='annotations', content_rowid='id', "
    "tokenize='unicode61 remove_diacritics 2')",
]


@event.listens_for(db.metadata, "after_create")
def _create_fts_tables(target, connection, **kw):
    for ddl in FTS_DDL:
        connection.execute(text(ddl))


# active_history 强制在 set 时加载旧值,以便 after_update 中的 FTS 'delete' 命令
# 能拿到正确的旧文本(否则对从 DB 重新加载后的对象,旧值不会进入 history.deleted)
def _noop_set(target, value, oldvalue, initiator):
    return value


for _col in (
    Book.title, Book.author, Book.publisher, Book.deleted_at,
    Note.content,
    Annotation.quote, Annotation.note,
):
    event.listen(_col, "set", _noop_set, active_history=True)


def _book_was_soft_deleted_change(book):
    # 返回 'insert' | 'delete' | None
    state = sa_inspect(book)
    hist = state.attrs.deleted_at.history
    if not hist.has_changes():
        return None
    old = hist.deleted[0] if hist.deleted else None
    new = hist.added[0] if hist.added else None
    if old is None and new is not None:
        return "delete"
    if old is not None and new is None:
        return "insert"
    return None


def _current_val(target, attr):
    return getattr(target, attr)


def _old_val(target, attr):
    # 取 SQLAlchemy 历史中的旧值;若该字段未变则旧值=当前值
    hist = sa_inspect(target).attrs[attr].history
    if hist.deleted:
        return hist.deleted[0]
    return getattr(target, attr)


def _book_params(b, old=False):
    pick = _old_val if old else _current_val
    return {
        "id": b.id,
        "title": fts_normalize(pick(b, "title")),
        "author": fts_normalize(pick(b, "author")),
        "publisher": fts_normalize(pick(b, "publisher")),
    }


def _note_params(n, old=False):
    pick = _old_val if old else _current_val
    return {"id": n.id, "content": fts_normalize(pick(n, "content"))}


def _ann_params(a, old=False):
    pick = _old_val if old else _current_val
    return {
        "id": a.id,
        "quote": fts_normalize(pick(a, "quote")),
        "note": fts_normalize(pick(a, "note")),
    }


@event.listens_for(Book, "after_insert")
def _book_after_insert(mapper, connection, target):
    if target.deleted_at is not None:
        return
    connection.execute(
        text("INSERT INTO books_fts(rowid, title, author, publisher) "
             "VALUES(:id, :title, :author, :publisher)"),
        _book_params(target),
    )


@event.listens_for(Book, "after_update")
def _book_after_update(mapper, connection, target):
    change = _book_was_soft_deleted_change(target)
    if change == "delete":
        connection.execute(
            text("INSERT INTO books_fts(books_fts, rowid, title, author, publisher) "
                 "VALUES('delete', :id, :title, :author, :publisher)"),
            _book_params(target, old=True),
        )
        return
    if change == "insert":
        connection.execute(
            text("INSERT INTO books_fts(rowid, title, author, publisher) "
                 "VALUES(:id, :title, :author, :publisher)"),
            _book_params(target),
        )
        return
    if target.deleted_at is not None:
        return
    # 外部内容表更新:用旧值 delete 索引,再插入新值
    connection.execute(
        text("INSERT INTO books_fts(books_fts, rowid, title, author, publisher) "
             "VALUES('delete', :id, :title, :author, :publisher)"),
        _book_params(target, old=True),
    )
    connection.execute(
        text("INSERT INTO books_fts(rowid, title, author, publisher) "
             "VALUES(:id, :title, :author, :publisher)"),
        _book_params(target),
    )


@event.listens_for(Book, "after_delete")
def _book_after_delete(mapper, connection, target):
    if target.deleted_at is not None:
        return
    connection.execute(
        text("INSERT INTO books_fts(books_fts, rowid, title, author, publisher) "
             "VALUES('delete', :id, :title, :author, :publisher)"),
        _book_params(target),
    )


@event.listens_for(Note, "after_insert")
def _note_after_insert(mapper, connection, target):
    connection.execute(
        text("INSERT INTO notes_fts(rowid, content) VALUES(:id, :content)"),
        _note_params(target),
    )


@event.listens_for(Note, "after_update")
def _note_after_update(mapper, connection, target):
    connection.execute(
        text("INSERT INTO notes_fts(notes_fts, rowid, content) "
             "VALUES('delete', :id, :content)"),
        _note_params(target, old=True),
    )
    connection.execute(
        text("INSERT INTO notes_fts(rowid, content) VALUES(:id, :content)"),
        _note_params(target),
    )


@event.listens_for(Note, "after_delete")
def _note_after_delete(mapper, connection, target):
    connection.execute(
        text("INSERT INTO notes_fts(notes_fts, rowid, content) "
             "VALUES('delete', :id, :content)"),
        _note_params(target),
    )


@event.listens_for(Annotation, "after_insert")
def _ann_after_insert(mapper, connection, target):
    connection.execute(
        text("INSERT INTO annotations_fts(rowid, quote, note) "
             "VALUES(:id, :quote, :note)"),
        _ann_params(target),
    )


@event.listens_for(Annotation, "after_update")
def _ann_after_update(mapper, connection, target):
    connection.execute(
        text("INSERT INTO annotations_fts(annotations_fts, rowid, quote, note) "
             "VALUES('delete', :id, :quote, :note)"),
        _ann_params(target, old=True),
    )
    connection.execute(
        text("INSERT INTO annotations_fts(rowid, quote, note) "
             "VALUES(:id, :quote, :note)"),
        _ann_params(target),
    )


@event.listens_for(Annotation, "after_delete")
def _ann_after_delete(mapper, connection, target):
    connection.execute(
        text("INSERT INTO annotations_fts(annotations_fts, rowid, quote, note) "
             "VALUES('delete', :id, :quote, :note)"),
        _ann_params(target),
    )
