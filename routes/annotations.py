"""批注(Annotation)路由 - 增删改查 + 导出"""
from __future__ import annotations

import csv
import io
import json
from urllib.parse import quote as urlquote

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from models import Annotation, Book, db

bp = Blueprint("annotations", __name__)


def _annotation_or_404(ann_id: int) -> Annotation:
    ann = Annotation.query.get(ann_id)
    if ann is None:
        abort(404)
    return ann


def _safe_filename(stem: str) -> str:
    """生成可用作文件名的纯文本字符串(去除 Windows 非法字符)"""
    bad = '<>:"/\\|?*\t\r\n'
    out = "".join(c for c in stem if c not in bad).strip()
    return out or "annotations"


def _content_disposition(filename: str) -> str:
    """生成 RFC 5987 兼容的 Content-Disposition 响应头值。

    HTTP headers 以 latin-1 编码,中文文件名需要通过 filename*=UTF-8'' 传递。
    同时提供 ASCII 回退名,避免旧客户端兼容问题。
    """
    encoded = urlquote(filename, safe="")
    ascii_fallback = filename.encode("ascii", errors="ignore").decode("ascii") or "annotations"
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}"


# ---------------------------- JSON API ----------------------------

@bp.route("/books/<int:book_id>/annotations", methods=["GET"])
def list_json(book_id: int):
    """列出某本书的所有批注(JSON)"""
    book = Book.query.get_or_404(book_id)
    anns = (
        Annotation.query
        .filter_by(book_id=book.id)
        .order_by(Annotation.created_at.asc())
        .all()
    )
    return jsonify([a.to_dict() for a in anns])


@bp.route("/books/<int:book_id>/annotations", methods=["POST"])
def create(book_id: int):
    """创建批注。

    前端发送 JSON: {cfi_range, quote, note?, color?}
    返回 201 + 批注 JSON。
    """
    book = Book.query.get_or_404(book_id)
    data = request.get_json(silent=True) or {}

    cfi_range = (data.get("cfi_range") or "").strip()
    quote = (data.get("quote") or "").strip()
    note = (data.get("note") or "").strip()
    color = (data.get("color") or "sakura").strip()[:20]

    if not cfi_range:
        return jsonify({"error": "cfi_range 必填"}), 400
    if not quote:
        return jsonify({"error": "quote 必填"}), 400

    ann = Annotation(
        book_id=book.id,
        cfi_range=cfi_range,
        quote=quote,
        note=note or None,
        color=color or "sakura",
    )
    db.session.add(ann)
    db.session.commit()
    return jsonify(ann.to_dict()), 201


@bp.route("/annotations/<int:ann_id>", methods=["PATCH"])
def update(ann_id: int):
    """更新批注(目前只支持改 note 和 color)"""
    ann = _annotation_or_404(ann_id)
    data = request.get_json(silent=True) or {}

    changed = False
    if "note" in data:
        ann.note = (data.get("note") or "").strip() or None
        changed = True
    if "color" in data:
        new_color = (data.get("color") or "").strip()[:20]
        if new_color:
            ann.color = new_color
            changed = True

    if changed:
        db.session.commit()
    return jsonify(ann.to_dict())


@bp.route("/annotations/<int:ann_id>", methods=["DELETE"])
def delete(ann_id: int):
    """删除批注"""
    ann = _annotation_or_404(ann_id)
    db.session.delete(ann)
    db.session.commit()
    return jsonify({"ok": True})


# ---------------------------- 导出 ----------------------------

@bp.route("/books/<int:book_id>/annotations/export.<string:fmt>")
def export(book_id: int, fmt: str):
    """导出批注。fmt 支持 md / txt / json / csv"""
    book = Book.query.get_or_404(book_id)
    anns = (
        Annotation.query
        .filter_by(book_id=book.id)
        .order_by(Annotation.created_at.asc())
        .all()
    )

    fmt = fmt.lower()
    base_name = _safe_filename(f"{book.title}_批注")

    if fmt == "json":
        payload = {
            "book": {
                "id": book.id,
                "title": book.title,
                "author": book.author,
            },
            "exported_at": None,  # 由前端 / 系统时间决定,这里留 null
            "count": len(anns),
            "annotations": [a.to_dict() for a in anns],
        }
        body = json.dumps(payload, ensure_ascii=False, indent=2)
        return Response(
            body,
            mimetype="application/json; charset=utf-8",
            headers={"Content-Disposition": _content_disposition(f"{base_name}.json")},
        )

    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["#", "quote(原文)", "note(感想)", "created_at"])
        for i, a in enumerate(anns, 1):
            w.writerow([
                i,
                a.quote.replace("\n", " "),
                (a.note or "").replace("\n", " "),
                a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else "",
            ])
        body = "\ufeff" + buf.getvalue()  # BOM 方便 Excel
        return Response(
            body.encode("utf-8"),
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": _content_disposition(f"{base_name}.csv")},
        )

    if fmt == "txt":
        lines = []
        lines.append(f"{book.title}")
        lines.append(f"作者: {book.author}")
        lines.append(f"批注条数: {len(anns)}")
        lines.append("=" * 60)
        lines.append("")
        for i, a in enumerate(anns, 1):
            lines.append(f"[{i}] {a.created_at.strftime('%Y-%m-%d %H:%M') if a.created_at else ''}")
            lines.append("原文:")
            lines.append(a.quote)
            if a.note:
                lines.append("")
                lines.append("感想:")
                lines.append(a.note)
            lines.append("")
            lines.append("-" * 60)
            lines.append("")
        body = "\n".join(lines)
        return Response(
            body.encode("utf-8"),
            mimetype="text/plain; charset=utf-8",
            headers={"Content-Disposition": _content_disposition(f"{base_name}.txt")},
        )

    if fmt == "md":
        lines = []
        lines.append(f"# {book.title}")
        lines.append("")
        lines.append(f"**作者**: {book.author}")
        lines.append("")
        lines.append(f"**批注条数**: {len(anns)}")
        lines.append("")
        lines.append("---")
        lines.append("")
        for i, a in enumerate(anns, 1):
            ts = a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else ""
            lines.append(f"## 批注 {i}" + (f" · {ts}" if ts else ""))
            lines.append("")
            # 原文用 blockquote
            for q_line in a.quote.splitlines() or [a.quote]:
                lines.append(f"> {q_line}")
            lines.append("")
            if a.note:
                lines.append(a.note)
                lines.append("")
            lines.append("---")
            lines.append("")
        body = "\n".join(lines)
        return Response(
            body.encode("utf-8"),
            mimetype="text/markdown; charset=utf-8",
            headers={"Content-Disposition": _content_disposition(f"{base_name}.md")},
        )

    return jsonify({"error": f"unsupported format: {fmt}"}), 400
