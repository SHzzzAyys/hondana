"""书籍相关路由"""
import glob
import os
from datetime import datetime
from io import BytesIO

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from werkzeug.utils import secure_filename

from epub_meta import cover_ext_from_mime, extract_epub_metadata
from models import (
    Book,
    ReadingSession,
    Tag,
    STATUS_CHOICES,
    STATUS_FINISHED,
    STATUS_READING,
    STATUS_UNREAD,
    db,
    fts_normalize,
)

bp = Blueprint("books", __name__)

_VALID_STATUSES = {STATUS_UNREAD, STATUS_READING, STATUS_FINISHED}
_VALID_SORT_FIELDS = {"title", "author", "rating", "created_at", "last_read_at"}


# ---------------------------- 辅助函数 ----------------------------

def _parse_date(raw):
    """解析 YYYY-MM-DD；空或非法返回 None"""
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_tags(raw):
    """逗号/中文逗号分隔 → 唯一标签名列表"""
    if not raw:
        return []
    raw = raw.replace("，", ",")
    names = [n.strip() for n in raw.split(",")]
    seen = set()
    out = []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _collect_form_data(form):
    """从表单读取并构造 book 数据 + 错误字典"""
    data = {
        "title": (form.get("title") or "").strip(),
        "author": (form.get("author") or "").strip(),
        "isbn": (form.get("isbn") or "").strip(),
        "publisher": (form.get("publisher") or "").strip(),
        "publish_date_raw": (form.get("publish_date") or "").strip(),
        "cover_url": (form.get("cover_url") or "").strip(),
        "status": form.get("status") or STATUS_UNREAD,
        "rating_raw": (form.get("rating") or "").strip(),
        "tags_raw": (form.get("tags") or "").strip(),
    }
    errors = {}
    if not data["title"]:
        errors["title"] = "书名不能为空"
    if not data["author"]:
        errors["author"] = "作者不能为空"
    if data["status"] not in _VALID_STATUSES:
        data["status"] = STATUS_UNREAD
    return data, errors


def _parse_rating(raw):
    """解析评分 1-5；否则返回 None"""
    if not raw:
        return None
    try:
        r = int(raw)
        if 1 <= r <= 5:
            return r
    except (ValueError, TypeError):
        pass
    return None


# ---------------------------- 书籍文件辅助(原 EPUB 专用,P1-1 扩展为多格式) ----------------------------

# 格式对应的下载 MIME(用于 Content-Type / 浏览器下载)
_FORMAT_MIME = {
    "epub": "application/epub+zip",
    "pdf": "application/pdf",
    "txt": "text/plain; charset=utf-8",
    "mobi": "application/x-mobipocket-ebook",
}


def _epub_dir():
    """返回书籍文件上传目录绝对路径(历史命名沿用 epubs/,实际可放任何格式)"""
    return current_app.config["EPUB_UPLOAD_FOLDER"]


def _file_ext_of(filename):
    """从文件名提取小写后缀(无后缀返回 '')"""
    if not filename or "." not in filename:
        return ""
    return filename.rsplit(".", 1)[1].lower()


def _book_disk_path(book):
    """书的磁盘存储路径,按 file_format 决定后缀;未上传时返回基于 epub 的旧路径(兼容)"""
    ext = (book.file_format or "epub").lower()
    return os.path.join(_epub_dir(), f"{book.id}.{ext}")


def _find_book_file(book_id):
    """按 ID 查找已上传的书籍文件(任何格式),排除封面文件;无则 None"""
    pattern = os.path.join(_epub_dir(), f"{book_id}.*")
    for p in sorted(glob.glob(pattern)):
        if ".cover." not in os.path.basename(p):
            return p
    return None


def _delete_book_files_by_id(book_id):
    """按 ID 删除该书所有上传文件(任何格式 + 全部封面),忽略不存在"""
    pattern = os.path.join(_epub_dir(), f"{book_id}.*")
    for p in glob.glob(pattern):
        try:
            os.remove(p)
        except OSError:
            pass


def _is_allowed_book(filename):
    """校验后缀属于支持的格式"""
    ext = _file_ext_of(filename)
    if not ext:
        return False
    allowed = current_app.config.get(
        "ALLOWED_BOOK_EXTENSIONS",
        current_app.config.get("ALLOWED_EPUB_EXTENSIONS", {"epub"}),
    )
    return ext in allowed


def _handle_epub_upload(book, file_storage, remove_flag):
    """处理表单中的书籍文件上传 / 删除请求(EPUB / PDF / TXT / MOBI)。

    旧名沿用,内部已多格式化。删除时清掉所有 {id}.* 包括旧 epub 与封面。
    """
    if remove_flag:
        _delete_book_files_by_id(book.id)
        book.epub_filename = None
        book.file_format = None

    if file_storage is None or not file_storage.filename:
        return None

    if not _is_allowed_book(file_storage.filename):
        return "仅支持上传 .epub / .pdf / .txt / .mobi 格式的文件"

    ext = _file_ext_of(file_storage.filename)
    safe_name = secure_filename(file_storage.filename) or f"book.{ext}"

    # 切换格式前,先清掉旧文件(避免 {id}.epub 与 {id}.pdf 共存)
    _delete_book_files_by_id(book.id)

    book.file_format = ext
    target = _book_disk_path(book)
    try:
        file_storage.save(target)
    except OSError as e:
        return f"文件保存失败：{e}"

    book.epub_filename = safe_name
    # 仅 EPUB 能提取封面,其他格式留给用户自己设 cover_url
    if ext == "epub":
        _extract_and_save_cover(book.id, target)
    return None


def _extract_and_save_cover(book_id, epub_path):
    """从 EPUB 提取封面并保存到磁盘(失败静默忽略)"""
    try:
        with open(epub_path, "rb") as f:
            meta = extract_epub_metadata(f)
    except OSError:
        return
    data = meta.get("cover_image_bytes")
    if not data:
        return
    ext = cover_ext_from_mime(meta.get("cover_mime"))
    _delete_cover_files(book_id)
    path = os.path.join(_epub_dir(), f"{book_id}.cover.{ext}")
    try:
        with open(path, "wb") as out:
            out.write(data)
    except OSError:
        pass


def _delete_cover_files(book_id):
    """删除对应书的所有封面文件(不同后缀)"""
    pattern = os.path.join(_epub_dir(), f"{book_id}.cover.*")
    for p in glob.glob(pattern):
        try:
            os.remove(p)
        except OSError:
            pass


def _find_cover_file(book_id):
    """查找现有封面文件路径,无则返回 None"""
    pattern = os.path.join(_epub_dir(), f"{book_id}.cover.*")
    files = sorted(glob.glob(pattern))
    return files[0] if files else None


def _delete_epub_file(book_id):
    """删除 book 对应的磁盘文件与封面(忽略不存在)。沿用旧名,行为已多格式。"""
    _delete_book_files_by_id(book_id)


def _apply_book_data(book, data):
    """将已验证的 data 应用到 book 实例（不含 commit）"""
    book.title = data["title"]
    book.author = data["author"]
    book.isbn = data["isbn"] or None
    book.publisher = data["publisher"] or None
    book.publish_date = _parse_date(data["publish_date_raw"])
    book.cover_url = data["cover_url"] or None
    book.status = data["status"]
    book.rating = _parse_rating(data["rating_raw"])

    book.tags.clear()
    for tag_name in _parse_tags(data["tags_raw"]):
        tag = Tag.get_or_create(tag_name)
        if tag is not None:
            book.tags.append(tag)


def _book_to_form_data(book):
    """将 book 实例转为表单可用的 data 字典"""
    return {
        "title": book.title or "",
        "author": book.author or "",
        "isbn": book.isbn or "",
        "publisher": book.publisher or "",
        "publish_date_raw": book.publish_date.strftime("%Y-%m-%d") if book.publish_date else "",
        "cover_url": book.cover_url or "",
        "status": book.status or STATUS_UNREAD,
        "rating_raw": str(book.rating) if book.rating else "",
        "tags_raw": ", ".join(t.name for t in book.tags),
    }


def _base_query():
    """返回排除已软删除书籍的基础查询"""
    return Book.query.filter(Book.deleted_at.is_(None))


# ---------------------------- 路由 ----------------------------

@bp.route("/")
def index():
    """首页 / 书籍列表"""
    status = request.args.get("status", "all")
    tag_name = (request.args.get("tag") or "").strip()
    sort_by = request.args.get("sort", "created_at")
    order = request.args.get("order", "desc")
    page = request.args.get("page", 1, type=int)
    per_page = current_app.config.get("BOOKS_PER_PAGE", 24)

    query = _base_query()

    if status in _VALID_STATUSES:
        query = query.filter_by(status=status)

    active_tag = None
    if tag_name:
        active_tag = Tag.query.filter_by(name=tag_name).first()
        if active_tag is not None:
            query = query.filter(Book.tags.any(Tag.id == active_tag.id))
        else:
            query = query.filter(db.text("0"))

    # 排序
    if sort_by not in _VALID_SORT_FIELDS:
        sort_by = "created_at"
    sort_col = getattr(Book, sort_by)
    if order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    # 分页
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    books = pagination.items

    counts = {
        "all": _base_query().count(),
        STATUS_UNREAD: _base_query().filter_by(status=STATUS_UNREAD).count(),
        STATUS_READING: _base_query().filter_by(status=STATUS_READING).count(),
        STATUS_FINISHED: _base_query().filter_by(status=STATUS_FINISHED).count(),
    }

    # 标签云
    tag_rows = (
        db.session.query(Tag.name, db.func.count(Book.id))
        .outerjoin(Tag.books)
        .filter(Book.deleted_at.is_(None))
        .group_by(Tag.id, Tag.name)
        .order_by(db.func.count(Book.id).desc(), Tag.name.asc())
        .all()
    )
    tag_cloud = [{"name": n, "count": c} for n, c in tag_rows if c > 0]

    # "继续阅读" - 最近阅读的在读书
    continue_book = (
        _base_query()
        .filter_by(status=STATUS_READING)
        .filter(Book.last_read_at.isnot(None))
        .order_by(Book.last_read_at.desc())
        .first()
    )

    return render_template(
        "index.html",
        books=books,
        pagination=pagination,
        current_status=status,
        current_tag=tag_name if active_tag else "",
        counts=counts,
        status_choices=STATUS_CHOICES,
        tag_cloud=tag_cloud,
        continue_book=continue_book,
        sort_by=sort_by,
        order=order,
    )


@bp.route("/books/new", methods=["GET", "POST"])
def new():
    """添加新书"""
    if request.method == "POST":
        data, errors = _collect_form_data(request.form)
        if errors:
            return render_template(
                "book_form.html",
                mode="new",
                data=data,
                errors=errors,
                status_choices=STATUS_CHOICES,
            )

        book = Book(
            title=data["title"],
            author=data["author"],
            isbn=data["isbn"] or None,
            publisher=data["publisher"] or None,
            publish_date=_parse_date(data["publish_date_raw"]),
            cover_url=data["cover_url"] or None,
            status=data["status"],
            rating=_parse_rating(data["rating_raw"]),
        )
        db.session.add(book)

        for tag_name in _parse_tags(data["tags_raw"]):
            tag = Tag.get_or_create(tag_name)
            if tag is not None:
                book.tags.append(tag)

        db.session.flush()

        epub_file = request.files.get("epub_file")
        err = _handle_epub_upload(book, epub_file, remove_flag=False)
        if err:
            db.session.rollback()
            errors["epub_file"] = err
            return render_template(
                "book_form.html",
                mode="new",
                data=data,
                errors=errors,
                status_choices=STATUS_CHOICES,
            )

        db.session.commit()

        flash(f"《{book.title}》已加入书架", "success")
        return redirect(url_for("books.index"))

    default_data = {
        "title": "",
        "author": "",
        "isbn": "",
        "publisher": "",
        "publish_date_raw": "",
        "cover_url": "",
        "status": STATUS_UNREAD,
        "rating_raw": "",
        "tags_raw": "",
    }
    return render_template(
        "book_form.html",
        mode="new",
        data=default_data,
        errors={},
        status_choices=STATUS_CHOICES,
    )


@bp.route("/books/<int:book_id>")
def detail(book_id):
    """书籍详情页"""
    book = Book.query.get_or_404(book_id)
    from models import Shelf
    shelves = Shelf.query.order_by(Shelf.name).all()
    return render_template(
        "book_detail.html",
        book=book,
        status_choices=STATUS_CHOICES,
        shelves=shelves,
    )


@bp.route("/books/<int:book_id>/edit", methods=["GET", "POST"])
def edit(book_id):
    """编辑书籍"""
    book = Book.query.get_or_404(book_id)

    if request.method == "POST":
        data, errors = _collect_form_data(request.form)
        if errors:
            return render_template(
                "book_form.html",
                mode="edit",
                book=book,
                data=data,
                errors=errors,
                status_choices=STATUS_CHOICES,
            )

        _apply_book_data(book, data)

        remove_flag = request.form.get("remove_epub") == "1"
        epub_file = request.files.get("epub_file")
        err = _handle_epub_upload(book, epub_file, remove_flag=remove_flag)
        if err:
            db.session.rollback()
            errors["epub_file"] = err
            return render_template(
                "book_form.html",
                mode="edit",
                book=book,
                data=data,
                errors=errors,
                status_choices=STATUS_CHOICES,
            )

        db.session.commit()

        flash(f"《{book.title}》已更新", "success")
        return redirect(url_for("books.detail", book_id=book.id))

    data = _book_to_form_data(book)
    return render_template(
        "book_form.html",
        mode="edit",
        book=book,
        data=data,
        errors={},
        status_choices=STATUS_CHOICES,
    )


@bp.route("/books/<int:book_id>/delete", methods=["POST"])
def delete(book_id):
    """软删除书籍"""
    book = Book.query.get_or_404(book_id)
    book.deleted_at = datetime.utcnow()
    db.session.commit()
    flash(f"《{book.title}》已从书架移除", "success")
    return redirect(url_for("books.index"))


@bp.route("/books/<int:book_id>/restore", methods=["POST"])
def restore(book_id):
    """恢复软删除的书籍"""
    book = Book.query.get_or_404(book_id)
    book.deleted_at = None
    db.session.commit()
    return jsonify({"ok": True, "title": book.title})


@bp.route("/books/<int:book_id>/quick-update", methods=["POST"])
def quick_update(book_id):
    """详情页快速更新状态 / 评分"""
    book = Book.query.get_or_404(book_id)

    field = request.form.get("field")
    value = request.form.get("value", "").strip()

    if field == "status" and value in _VALID_STATUSES:
        book.status = value
        db.session.commit()
        flash("状态已更新", "success")
    elif field == "rating":
        book.rating = _parse_rating(value)
        db.session.commit()
        flash("评分已更新", "success")
    else:
        flash("无效的更新请求", "error")

    return redirect(url_for("books.detail", book_id=book.id))


def _fts_match_expr(q):
    # 把原查询 CJK 切字后,每个空白 token 包成 phrase, 内部双引号转义。
    # FTS5 默认多 phrase 之间为 AND 关系,正好满足多关键词组合搜索。
    normalized = fts_normalize(q)
    tokens = [t for t in normalized.split() if t]
    if not tokens:
        return None
    return " ".join(f'"{t.replace(chr(34), chr(34)*2)}"' for t in tokens)


@bp.route("/search")
def search():
    """关键词搜索 - 跨书名/作者/出版社/ISBN/笔记内容/批注"""
    q = (request.args.get("q") or "").strip()
    sort = request.args.get("sort", "relevance")

    if not q:
        return render_template("search.html", query="", results=[], sort=sort)

    match_expr = _fts_match_expr(q)
    result_map = {}

    def _entry(book):
        return result_map.setdefault(
            book.id,
            {"book": book, "hit_types": [], "note_snippets": [], "_score": 0.0},
        )

    if match_expr:
        # 1) 书籍字段:每列单独 MATCH 以标注 hit_type
        for col, label in (("title", "书名"), ("author", "作者"), ("publisher", "出版社")):
            rows = db.session.execute(
                db.text(
                    f"SELECT rowid, bm25(books_fts) AS s FROM books_fts "
                    f"WHERE books_fts MATCH :m"
                ),
                {"m": f"{{{col}}}: {match_expr}"},
            ).fetchall()
            for rowid, score in rows:
                book = Book.query.get(rowid)
                if book is None or book.deleted_at is not None:
                    continue
                entry = _entry(book)
                if label not in entry["hit_types"]:
                    entry["hit_types"].append(label)
                entry["_score"] = min(entry["_score"], score) if entry["_score"] else score

        # 2) 整表 MATCH:捕获跨列多关键词(如 q="村上 森林" 命中 title+author 散落)
        rows = db.session.execute(
            db.text(
                "SELECT rowid, bm25(books_fts) AS s FROM books_fts "
                "WHERE books_fts MATCH :m"
            ),
            {"m": match_expr},
        ).fetchall()
        for rowid, score in rows:
            book = Book.query.get(rowid)
            if book is None or book.deleted_at is not None:
                continue
            entry = _entry(book)
            if not entry["hit_types"]:
                # 跨列命中:把出现 token 的列都打标
                tokens = [t.lower() for t in fts_normalize(q).split() if t]
                for col, label in (("title", "书名"), ("author", "作者"), ("publisher", "出版社")):
                    val = (getattr(book, col) or "")
                    if any(t in fts_normalize(val).lower().split() for t in tokens):
                        entry["hit_types"].append(label)
            entry["_score"] = min(entry["_score"], score) if entry["_score"] else score

        # 3) 笔记
        from models import Note
        note_rows = db.session.execute(
            db.text(
                "SELECT rowid, bm25(notes_fts) AS s FROM notes_fts "
                "WHERE notes_fts MATCH :m"
            ),
            {"m": match_expr},
        ).fetchall()
        for note_id, score in note_rows:
            note = Note.query.get(note_id)
            if note is None:
                continue
            book = note.book
            if book is None or book.deleted_at is not None:
                continue
            entry = _entry(book)
            if "笔记" not in entry["hit_types"]:
                entry["hit_types"].append("笔记")
            entry["note_snippets"].append(_make_snippet(note.content, q))
            entry["_score"] = min(entry["_score"], score) if entry["_score"] else score

        # 4) 批注
        from models import Annotation
        ann_rows = db.session.execute(
            db.text(
                "SELECT rowid, bm25(annotations_fts) AS s FROM annotations_fts "
                "WHERE annotations_fts MATCH :m"
            ),
            {"m": match_expr},
        ).fetchall()
        for ann_id, score in ann_rows:
            ann = Annotation.query.get(ann_id)
            if ann is None:
                continue
            book = ann.book
            if book is None or book.deleted_at is not None:
                continue
            entry = _entry(book)
            if "批注" not in entry["hit_types"]:
                entry["hit_types"].append("批注")
            snippet_text = ann.quote or ann.note or ""
            entry["note_snippets"].append(_make_snippet(snippet_text, q))
            entry["_score"] = min(entry["_score"], score) if entry["_score"] else score

    # 5) ISBN 走 ilike(FTS 对数字串分词不可控)
    isbn_hits = _base_query().filter(Book.isbn.ilike(f"%{q}%")).all()
    for book in isbn_hits:
        entry = _entry(book)
        if "ISBN" not in entry["hit_types"]:
            entry["hit_types"].append("ISBN")

    results = list(result_map.values())
    if sort == "time":
        results.sort(key=lambda r: r["book"].created_at or datetime.min, reverse=True)
    else:
        # bm25 返回越小越相关;无 FTS 命中(纯 ISBN)给 0
        results.sort(key=lambda r: (r["_score"], -(r["book"].created_at or datetime.min).timestamp()))

    for r in results:
        r.pop("_score", None)

    return render_template("search.html", query=q, results=results, sort=sort)


def _make_snippet(content, q, radius=40):
    """生成匹配片段：命中词前后 radius 字符"""
    if not content:
        return ""
    # 取第一个 token 定位;多关键词时尽量贴近第一个命中
    needle = (q.split()[0] if q.split() else q).lower()
    idx = content.lower().find(needle)
    if idx < 0:
        return content[: radius * 2] + ("…" if len(content) > radius * 2 else "")
    start = max(0, idx - radius)
    end = min(len(content), idx + len(needle) + radius)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(content) else ""
    return prefix + content[start:end] + suffix


# ---------------------------- EPUB 阅读 ----------------------------

@bp.route("/books/<int:book_id>/read")
def read(book_id):
    """在线阅读页 - 按 file_format 分派到对应模板;MOBI 浏览器无法直接渲染,仍重定向。"""
    book = Book.query.get_or_404(book_id)
    if not book.epub_filename:
        flash("这本书还没有上传文件", "error")
        return redirect(url_for("books.detail", book_id=book.id))
    if not _find_book_file(book.id):
        flash("书籍文件丢失，请重新上传", "error")
        return redirect(url_for("books.edit", book_id=book.id))

    fmt = (book.file_format or "epub").lower()
    if fmt == "epub":
        return render_template("reader.html", book=book)
    if fmt == "pdf":
        return render_template("reader_pdf.html", book=book)
    if fmt == "txt":
        return render_template("reader_txt.html", book=book)
    flash(
        f"{fmt.upper()} 格式暂不支持在线阅读,请下载到本地查看",
        "error",
    )
    return redirect(url_for("books.detail", book_id=book.id))


@bp.route("/books/<int:book_id>/epub")
def epub_file(book_id):
    """流式返回书籍文件(任意格式 - URL 历史名称沿用 /epub)"""
    book = Book.query.get_or_404(book_id)
    if not book.epub_filename:
        abort(404)
    path = _find_book_file(book.id)
    if not path:
        abort(404)

    fmt = (book.file_format or "epub").lower()
    mimetype = _FORMAT_MIME.get(fmt, "application/octet-stream")
    as_download = request.args.get("download") == "1"
    return send_from_directory(
        _epub_dir(),
        os.path.basename(path),
        mimetype=mimetype,
        as_attachment=as_download,
        download_name=book.epub_filename,
        conditional=True,
    )


@bp.route("/books/<int:book_id>/epub/delete", methods=["POST"])
def delete_epub(book_id):
    """从详情页快速删除已上传的 EPUB"""
    book = Book.query.get_or_404(book_id)
    _delete_epub_file(book.id)
    book.epub_filename = None
    db.session.commit()
    flash("EPUB 文件已删除", "success")
    return redirect(url_for("books.detail", book_id=book.id))


@bp.route("/books/<int:book_id>/reading-progress", methods=["PATCH"])
def update_progress(book_id):
    """更新最后阅读位置(CFI) + 进度百分比"""
    book = Book.query.get_or_404(book_id)
    data = request.get_json(silent=True) or {}
    cfi = (data.get("cfi") or "").strip()
    if not cfi:
        return jsonify({"error": "cfi 必填"}), 400
    book.last_read_cfi = cfi
    book.last_read_at = datetime.utcnow()
    # 接受可选的进度百分比
    progress = data.get("progress")
    if progress is not None:
        try:
            p = float(progress)
            if 0.0 <= p <= 1.0:
                book.reading_progress = p
        except (ValueError, TypeError):
            pass
    db.session.commit()
    return jsonify({
        "ok": True,
        "last_read_at": book.last_read_at.isoformat() if book.last_read_at else None,
    })


@bp.route("/books/<int:book_id>/reading-time", methods=["PATCH"])
def update_reading_time(book_id):
    """累加阅读秒数"""
    book = Book.query.get_or_404(book_id)
    data = request.get_json(silent=True) or {}
    seconds = data.get("seconds", 0)
    try:
        seconds = int(seconds)
    except (ValueError, TypeError):
        seconds = 0
    if seconds > 0:
        book.total_reading_seconds = (book.total_reading_seconds or 0) + seconds
        # 同时写入会话片段,作为周/月/年时间窗统计的真源
        db.session.add(ReadingSession(book_id=book.id, seconds=seconds))
        db.session.commit()
    return jsonify({"ok": True, "total": book.total_reading_seconds or 0})


@bp.route("/books/<int:book_id>/cover")
def extracted_cover(book_id):
    """返回从 EPUB 提取的封面图"""
    book = Book.query.get_or_404(book_id)
    path = _find_cover_file(book.id)
    if not path:
        abort(404)
    directory, filename = os.path.split(path)
    ext = filename.rsplit(".", 1)[-1].lower()
    mime_map = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png", "gif": "image/gif", "webp": "image/webp",
    }
    return send_from_directory(
        directory, filename,
        mimetype=mime_map.get(ext, "application/octet-stream"),
        conditional=True,
    )


# ---------------------------- EPUB 元数据 AJAX ----------------------------

@bp.route("/api/epub-metadata", methods=["POST"])
def api_epub_metadata():
    """上传 EPUB 并返回元数据 JSON"""
    f = request.files.get("epub_file")
    if not f or not f.filename:
        return jsonify({"error": "未收到文件"}), 400
    if not _is_allowed_epub(f.filename):
        return jsonify({"error": "仅支持 .epub 文件"}), 400

    buf = BytesIO(f.read())
    meta = extract_epub_metadata(buf)

    has_cover = meta.pop("cover_image_bytes", None) is not None
    meta.pop("cover_mime", None)
    meta["has_cover"] = has_cover

    return jsonify(meta)


# ---------------------------- 导出 ----------------------------

@bp.route("/export.json")
def export_json():
    """导出所有书籍为 JSON（含笔记与标签）"""
    from flask import jsonify

    books = _base_query().order_by(Book.created_at.asc()).all()
    payload = []
    for b in books:
        payload.append({
            "id": b.id,
            "title": b.title,
            "author": b.author,
            "isbn": b.isbn,
            "publisher": b.publisher,
            "publish_date": b.publish_date.isoformat() if b.publish_date else None,
            "cover_url": b.cover_url,
            "status": b.status,
            "rating": b.rating,
            "created_at": b.created_at.isoformat() if b.created_at else None,
            "updated_at": b.updated_at.isoformat() if b.updated_at else None,
            "tags": [t.name for t in b.tags],
            "notes": [
                {"content": n.content, "created_at": n.created_at.isoformat() if n.created_at else None}
                for n in b.notes
            ],
        })
    resp = jsonify(payload)
    resp.headers["Content-Disposition"] = 'attachment; filename="bookshelf_export.json"'
    return resp


@bp.route("/export.csv")
def export_csv():
    """导出书籍基本信息为 CSV"""
    import csv
    import io
    from flask import Response

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "id", "title", "author", "isbn", "publisher", "publish_date",
        "status", "rating", "tags", "notes_count",
        "created_at", "updated_at",
    ])
    books = _base_query().order_by(Book.created_at.asc()).all()
    for b in books:
        writer.writerow([
            b.id,
            b.title,
            b.author,
            b.isbn or "",
            b.publisher or "",
            b.publish_date.isoformat() if b.publish_date else "",
            b.status,
            b.rating if b.rating else "",
            "|".join(t.name for t in b.tags),
            len(b.notes),
            b.created_at.isoformat() if b.created_at else "",
            b.updated_at.isoformat() if b.updated_at else "",
        ])

    csv_bytes = ("\ufeff" + buf.getvalue()).encode("utf-8")
    return Response(
        csv_bytes,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="bookshelf_export.csv"'},
    )


# ---------------------------- 导入 ----------------------------

@bp.route("/import.json", methods=["POST"])
def import_json():
    """从 JSON 导入书籍数据"""
    import json as json_mod
    data = request.get_json(silent=True)
    if not data or not isinstance(data, list):
        return jsonify({"error": "无效的 JSON 数据,需要数组格式"}), 400

    imported = 0
    for item in data:
        title = (item.get("title") or "").strip()
        author = (item.get("author") or "").strip()
        if not title or not author:
            continue
        # 检查是否已存在(按标题+作者去重)
        existing = _base_query().filter_by(title=title, author=author).first()
        if existing:
            continue

        book = Book(
            title=title,
            author=author,
            isbn=(item.get("isbn") or "").strip() or None,
            publisher=(item.get("publisher") or "").strip() or None,
            cover_url=(item.get("cover_url") or "").strip() or None,
            status=item.get("status", STATUS_UNREAD),
            rating=_parse_rating(str(item.get("rating", ""))),
        )
        pd = item.get("publish_date")
        if pd:
            book.publish_date = _parse_date(pd)
        db.session.add(book)
        db.session.flush()

        # 标签
        for tag_name in (item.get("tags") or []):
            tag = Tag.get_or_create(tag_name)
            if tag is not None:
                book.tags.append(tag)

        # 笔记
        from models import Note
        for note_data in (item.get("notes") or []):
            content = (note_data.get("content") or "").strip()
            if content:
                note = Note(book_id=book.id, content=content)
                db.session.add(note)

        imported += 1

    db.session.commit()
    return jsonify({"ok": True, "imported": imported})
