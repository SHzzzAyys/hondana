"""批注(Annotation)路由 - 增删改查 + 导出"""
from __future__ import annotations

import csv
import io
import json
from datetime import date
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

    if fmt == "obsidian":
        today = date.today().isoformat()
        lines = [
            "---",
            f"title: {book.title}",
            f"author: {book.author}",
            f"exported: {today}",
            "tags: [hondana, 书摘]",
            "---",
            "",
            f"# [[{book.title}]]",
            "",
        ]
        for i, a in enumerate(anns, 1):
            ts = a.created_at.strftime("%Y-%m-%d") if a.created_at else today
            lines.append(f"> [!quote] 批注 {i} · {ts}")
            for q_line in (a.quote.splitlines() or [a.quote]):
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
            headers={"Content-Disposition": _content_disposition(f"{_safe_filename(book.title)}_批注_obsidian.md")},
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


# ---------------------------- 分享卡片 (PNG) ----------------------------

_COLOR_BAND = {
    "sakura": "#E8B4A0",
    "matcha": "#A8C8B8",
    "sky":    "#C4D5E0",
    "washi":  "#FAF8F3",
}

_FONT_CANDIDATES = [
    "DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "C:\\Windows\\Fonts\\msyh.ttc",
]


def _load_font(size: int):
    from PIL import ImageFont
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size=size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _wrap_to_width(draw, text: str, font, max_width: int) -> list[str]:
    out: list[str] = []
    for para in text.splitlines() or [text]:
        # 中英混排:按字符级估算宽度
        line = ""
        for ch in para:
            trial = line + ch
            w = draw.textbbox((0, 0), trial, font=font)[2]
            if w > max_width and line:
                out.append(line)
                line = ch
            else:
                line = trial
        out.append(line)
    return out


@bp.route("/annotations/<int:ann_id>/card.png")
def share_card(ann_id: int):
    from PIL import Image, ImageDraw

    ann = _annotation_or_404(ann_id)
    book = Book.query.get_or_404(ann.book_id)

    W, H = 1080, 1350
    margin = 80
    band = _COLOR_BAND.get((ann.color or "").lower(), _COLOR_BAND["sakura"])

    img = Image.new("RGB", (W, H), "#FAF8F3")
    draw = ImageDraw.Draw(img)

    # 顶部色带
    draw.rectangle([0, 0, W, 16], fill=band)

    # 内嵌边框
    draw.rectangle([40, 40, W - 40, H - 40], outline="#E5E0D5", width=1)

    quote_text = ann.quote or ""
    if len(quote_text) > 500:
        quote_text = quote_text[:500].rstrip() + "…"

    quote_font = _load_font(40)
    meta_font = _load_font(28)
    watermark_font = _load_font(20)

    max_text_w = W - margin * 2
    lines = _wrap_to_width(draw, quote_text, quote_font, max_text_w)

    line_h = quote_font.getbbox("汉Aj")[3] + 14
    total_quote_h = line_h * len(lines)
    y0 = (H - total_quote_h) // 2 - 60
    for i, line in enumerate(lines):
        w = draw.textbbox((0, 0), line, font=quote_font)[2]
        x = (W - w) // 2
        draw.text((x, y0 + i * line_h), line, font=quote_font, fill="#3D3D3D")

    # 书名 · 作者
    meta = f"{book.title} · {book.author}"
    mw = draw.textbbox((0, 0), meta, font=meta_font)[2]
    mx = (W - mw) // 2
    my = y0 + total_quote_h + 80
    draw.text((mx, my), meta, font=meta_font, fill="#8A8680")

    # 水印
    wm = "本棚 · hondana"
    wb = draw.textbbox((0, 0), wm, font=watermark_font)
    draw.text((W - 60 - (wb[2] - wb[0]), H - 60 - (wb[3] - wb[1])), wm, font=watermark_font, fill="#8A8680")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(
        buf.getvalue(),
        mimetype="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


# ---------------------------- 全局批注列表 ----------------------------

@bp.route("/annotations")
def global_list():
    q = (request.args.get("q") or "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = 24

    query = Annotation.query.join(Book).filter(Book.deleted_at.is_(None))
    if q:
        query = query.filter(Annotation.quote.ilike(f"%{q}%"))
    query = query.order_by(Annotation.created_at.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return render_template(
        "annotations_global.html",
        pagination=pagination,
        annotations=pagination.items,
        q=q,
        color_map=_COLOR_BAND,
    )
