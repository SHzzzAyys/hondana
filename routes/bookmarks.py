"""书签(Bookmark)路由 - 增删改查"""
from __future__ import annotations

from flask import Blueprint, abort, jsonify, request

from models import Book, Bookmark, db

bp = Blueprint("bookmarks", __name__)


def _bookmark_or_404(bm_id: int) -> Bookmark:
    bm = Bookmark.query.get(bm_id)
    if bm is None:
        abort(404)
    return bm


@bp.route("/books/<int:book_id>/bookmarks", methods=["GET"])
def list_json(book_id: int):
    """列出某本书的所有书签(按时间倒序)"""
    book = Book.query.get_or_404(book_id)
    items = (
        Bookmark.query
        .filter_by(book_id=book.id)
        .order_by(Bookmark.created_at.desc())
        .all()
    )
    return jsonify([b.to_dict() for b in items])


@bp.route("/books/<int:book_id>/bookmarks", methods=["POST"])
def create(book_id: int):
    """创建书签。前端 JSON: {cfi, label?, preview?}"""
    book = Book.query.get_or_404(book_id)
    data = request.get_json(silent=True) or {}

    cfi = (data.get("cfi") or "").strip()
    label = (data.get("label") or "").strip()[:200]
    preview = (data.get("preview") or "").strip()

    if not cfi:
        return jsonify({"error": "cfi 必填"}), 400

    bm = Bookmark(
        book_id=book.id,
        cfi=cfi,
        label=label or None,
        preview=preview or None,
    )
    db.session.add(bm)
    db.session.commit()
    return jsonify(bm.to_dict()), 201


@bp.route("/bookmarks/<int:bm_id>", methods=["PATCH"])
def update(bm_id: int):
    """更新书签标签"""
    bm = _bookmark_or_404(bm_id)
    data = request.get_json(silent=True) or {}
    if "label" in data:
        bm.label = (data.get("label") or "").strip()[:200] or None
        db.session.commit()
    return jsonify(bm.to_dict())


@bp.route("/bookmarks/<int:bm_id>", methods=["DELETE"])
def delete(bm_id: int):
    """删除书签"""
    bm = _bookmark_or_404(bm_id)
    db.session.delete(bm)
    db.session.commit()
    return jsonify({"ok": True})
