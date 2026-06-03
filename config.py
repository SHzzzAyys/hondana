"""配置文件 - 个人图书管理系统"""
import os

# 默认开发值,启动时若仍是这个值会触发 SECRET_KEY 校验告警/拒绝(见 app._enforce_secret_key)
DEFAULT_DEV_SECRET_KEY = "book-manager-dev-secret-change-me"


class Config:
    """基础配置"""
    SECRET_KEY = os.environ.get("SECRET_KEY", DEFAULT_DEV_SECRET_KEY)

    # 数据库：instance/books.db（Flask 自动创建 instance 目录）
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "sqlite:///books.db",  # 相对 instance 路径
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 分页默认每页数量
    BOOKS_PER_PAGE = 24

    # ---------------------------- 书籍文件上传 ----------------------------
    # 上传文件夹名(历史命名沿用 epubs/,文件夹下含各格式;改名要迁移磁盘,得不偿失)
    EPUB_UPLOAD_FOLDER_NAME = "epubs"
    # 允许上传的格式:epub 是一等公民,其他格式可上传/下载但暂不支持在线阅读
    ALLOWED_BOOK_EXTENSIONS = {"epub", "pdf", "txt", "mobi"}
    # 兼容旧代码引用(已废弃,新代码请用 ALLOWED_BOOK_EXTENSIONS)
    ALLOWED_EPUB_EXTENSIONS = ALLOWED_BOOK_EXTENSIONS
    # 单文件最大 100 MB
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024
