"""笔记相关路由"""
from flask import Blueprint, flash, redirect, request, url_for

from models import Book, Note, db

bp = Blueprint("notes", __name__)


@bp.route("/books/<int:book_id>/notes", methods=["POST"])
def create(book_id):
    """为书籍添加笔记"""
    book = Book.query.get_or_404(book_id)

    content = (request.form.get("content") or "").strip()
    if not content:
        flash("笔记内容不能为空", "error")
        return redirect(url_for("books.detail", book_id=book.id))

    note = Note(book_id=book.id, content=content)
    db.session.add(note)
    db.session.commit()

    flash("笔记已添加", "success")
    return redirect(url_for("books.detail", book_id=book.id))


@bp.route("/notes/<int:note_id>/delete", methods=["POST"])
def delete(note_id):
    """删除一条笔记"""
    note = Note.query.get_or_404(note_id)
    book_id = note.book_id
    db.session.delete(note)
    db.session.commit()

    flash("笔记已删除", "success")
    return redirect(url_for("books.detail", book_id=book_id))
