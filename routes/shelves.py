"""自定义书单路由"""
from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from models import Book, Shelf, db

bp = Blueprint("shelves", __name__)


@bp.route("/shelves")
def index():
    """书单列表页"""
    shelves = Shelf.query.order_by(Shelf.created_at.desc()).all()
    return render_template("shelf_list.html", shelves=shelves)


@bp.route("/shelves/new", methods=["POST"])
def create():
    """创建书单"""
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("书单名称不能为空", "error")
        return redirect(url_for("shelves.index"))
    description = (request.form.get("description") or "").strip()
    shelf = Shelf(name=name, description=description or None)
    db.session.add(shelf)
    db.session.commit()
    flash(f"书单「{name}」已创建", "success")
    return redirect(url_for("shelves.detail", shelf_id=shelf.id))


@bp.route("/shelves/<int:shelf_id>")
def detail(shelf_id):
    """书单详情页"""
    shelf = Shelf.query.get_or_404(shelf_id)
    # 获取不在这个书单中且未删除的书
    existing_ids = [b.id for b in shelf.books]
    available_books_query = Book.query.filter(Book.deleted_at.is_(None))
    if existing_ids:
        available_books_query = available_books_query.filter(Book.id.notin_(existing_ids))
    available_books = available_books_query.order_by(Book.title).all()
    return render_template("shelf_detail.html", shelf=shelf, available_books=available_books)


@bp.route("/shelves/<int:shelf_id>/edit", methods=["POST"])
def edit(shelf_id):
    """编辑书单"""
    shelf = Shelf.query.get_or_404(shelf_id)
    name = (request.form.get("name") or "").strip()
    if name:
        shelf.name = name
    description = (request.form.get("description") or "").strip()
    shelf.description = description or None
    db.session.commit()
    flash("书单已更新", "success")
    return redirect(url_for("shelves.detail", shelf_id=shelf.id))


@bp.route("/shelves/<int:shelf_id>/delete", methods=["POST"])
def delete(shelf_id):
    """删除书单"""
    shelf = Shelf.query.get_or_404(shelf_id)
    name = shelf.name
    db.session.delete(shelf)
    db.session.commit()
    flash(f"书单「{name}」已删除", "success")
    return redirect(url_for("shelves.index"))


@bp.route("/shelves/<int:shelf_id>/add-book", methods=["POST"])
def add_book(shelf_id):
    """向书单添加书籍"""
    shelf = Shelf.query.get_or_404(shelf_id)
    book_id = request.form.get("book_id", type=int)
    if not book_id:
        return jsonify({"error": "book_id 必填"}), 400
    book = Book.query.get_or_404(book_id)
    if book not in shelf.books:
        shelf.books.append(book)
        db.session.commit()
    flash(f"《{book.title}》已加入书单", "success")
    return redirect(url_for("shelves.detail", shelf_id=shelf.id))


@bp.route("/shelves/<int:shelf_id>/remove-book", methods=["POST"])
def remove_book(shelf_id):
    """从书单移除书籍"""
    shelf = Shelf.query.get_or_404(shelf_id)
    book_id = request.form.get("book_id", type=int)
    if not book_id:
        return jsonify({"error": "book_id 必填"}), 400
    book = Book.query.get(book_id)
    if book and book in shelf.books:
        shelf.books.remove(book)
        db.session.commit()
    flash("已从书单移除", "success")
    return redirect(url_for("shelves.detail", shelf_id=shelf.id))


@bp.route("/api/shelves/<int:shelf_id>/add-book", methods=["POST"])
def api_add_book(shelf_id):
    """API: 向书单添加书籍(从详情页使用)"""
    shelf = Shelf.query.get_or_404(shelf_id)
    body = request.get_json(silent=True) or {}
    book_id = body.get("book_id")
    if not book_id:
        return jsonify({"error": "book_id 必填"}), 400
    book = Book.query.get_or_404(book_id)
    if book not in shelf.books:
        shelf.books.append(book)
        db.session.commit()
    return jsonify({"ok": True})
