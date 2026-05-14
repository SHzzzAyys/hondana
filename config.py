"""配置文件 - 个人图书管理系统"""
import os


class Config:
    """基础配置"""
    SECRET_KEY = os.environ.get("SECRET_KEY", "book-manager-dev-secret-change-me")

    # 数据库：instance/books.db（Flask 自动创建 instance 目录）
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "sqlite:///books.db",  # 相对 instance 路径
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 分页默认每页数量
    BOOKS_PER_PAGE = 24

    # ---------------------------- EPUB 上传 ----------------------------
    # 上传文件夹名（相对于 app.instance_path → instance/epubs/）
    EPUB_UPLOAD_FOLDER_NAME = "epubs"
    # 允许的上传后缀
    ALLOWED_EPUB_EXTENSIONS = {"epub"}
    # 单文件最大 100 MB
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024
